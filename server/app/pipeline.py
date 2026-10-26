"""Ticket run: preflight, Haiku coordinator, Playwright, then at most three Haiku heals."""

from __future__ import annotations

import difflib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import runners, store
from app.logbook import Logbook, plain
from app.settings import get_settings

log = logging.getLogger("qa.pipeline")


def verdict_for(summary: dict[str, int], *, preflight_ok: bool, produced_specs: bool) -> str:
    if not preflight_ok:
        return "HALTED"
    if not produced_specs:
        return "HALTED"
    if (
        summary.get("failed", 0) == 0
        and summary.get("skipped", 0) == 0
        and summary.get("passed", 0) > 0
    ):
        return "PERFECT"
    return "NEEDS_REVISION"


def _suite_passed(exit_code: int, summary: dict[str, int]) -> bool:
    return exit_code == 0 and verdict_for(summary, preflight_ok=True, produced_specs=True) == "PERFECT"


def _open_issue(summary: dict[str, int]) -> str:
    parts: list[str] = []
    if summary.get("failed", 0):
        parts.append(f"{summary['failed']} test(s) still failing")
    if summary.get("skipped", 0):
        parts.append(f"{summary['skipped']} test(s) skipped")
    if not parts:
        parts.append("no passing tests")
    return "; ".join(parts)


def startup_order(waiting: list[dict[str, Any]], fresh_phase1: str | None = None) -> list[str]:
    """Checked-in suite runs go first. Ticket runs wait behind them."""
    phase1: list[str] = []
    tickets: list[str] = []
    for row in waiting:
        run_id = str(row.get("id") or "")
        if not run_id:
            continue
        if row.get("kind") == "phase1":
            phase1.append(run_id)
        else:
            tickets.append(run_id)
    if fresh_phase1 and fresh_phase1 not in phase1:
        phase1.insert(0, fresh_phase1)
    return phase1 + tickets


def failed_tests(report: dict[str, Any]) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    def walk(node: Any, file_hint: str) -> None:
        if not isinstance(node, dict):
            return
        current = str(node.get("file") or file_hint)
        for spec in node.get("specs") or []:
            if not isinstance(spec, dict) or spec.get("ok") is True:
                continue
            message = ""
            unexpected = spec.get("ok") is False
            for test in spec.get("tests") or []:
                if not isinstance(test, dict):
                    continue
                if test.get("status") in {"unexpected", "failed"}:
                    unexpected = True
                for result in test.get("results") or []:
                    if not isinstance(result, dict):
                        continue
                    if result.get("status") in {"failed", "timedOut", "interrupted"}:
                        unexpected = True
                    error = result.get("error")
                    if isinstance(error, dict) and error.get("message") and not message:
                        message = str(error["message"]).split("\n", 1)[0][:240]
            if unexpected:
                found.append({
                    "title": str(spec.get("title") or "unnamed"),
                    "file": str(spec.get("file") or current),
                    "error": message,
                })
        for child in node.get("suites") or []:
            walk(child, current)

    for suite in report.get("suites") or []:
        walk(suite, "")
    return found


def spec_was_patched(triage: dict[str, Any]) -> bool:
    failures = triage.get("failures")
    if not isinstance(failures, list):
        return False
    return any(
        isinstance(item, dict) and item.get("class") == "spec" and item.get("action") == "patched"
        for item in failures
    )


def suspicious_patches(triage: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    failures = triage.get("failures")
    if not isinstance(failures, list):
        return lines
    for item in failures:
        if not isinstance(item, dict):
            continue
        if item.get("class") in {"bug", "timing"} and item.get("action") == "patched":
            lines.append(f"healer edited a {item.get('class')} failure: {item.get('title')}")
    return lines


def execute_run(run_id: str) -> None:
    row = store.get_run(run_id)
    if row is None:
        raise KeyError(run_id)
    folder = store.run_dir(run_id)
    book = Logbook(folder)
    try:
        if row.get("kind") == "phase1":
            _execute_phase1(run_id, row, folder, book)
        else:
            _execute(run_id, row, folder, book)
    except Exception as exc:
        book.row("server", "failed", str(exc)[:220])
        log.exception("run failed")
        store.update_run(run_id, status="failed", error=str(exc)[:500])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[str(exc)[:500]])
        _seal(run_id, None, "HALTED")


def _execute(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    settings = get_settings()
    book.phase(str(row.get("ticket") or run_id))
    book.row("server", "queued", str(row.get("ticket") or run_id))
    store.update_run(run_id, status="preflight")
    book.phase("preflight")
    book.row("server", "preflight", "started")
    code = runners.run_preflight(folder, ticket=row.get("ticket"), pr=row.get("pr"), sha=row.get("sha"))
    preflight = _read_json(folder / "preflight.json")
    preflight_ok = code == 0 and bool(preflight.get("ok"))
    ticket = str(preflight.get("ticket") or row.get("ticket") or "")
    if ticket and ticket != row.get("ticket"):
        store.update_run(run_id, ticket=ticket, pr=preflight.get("primaryPr"), sha=row.get("sha"))
    if not preflight_ok:
        detail = plain(_failed_check(preflight) or "preflight failed")
        book.row("server", "preflight", f"failed  {detail}")
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket or None, "HALTED", summary, [detail])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[detail])
        _seal(run_id, summary, "HALTED")
        return

    checks = [item for item in (preflight.get("checks") or []) if isinstance(item, dict)]
    passed = sum(1 for item in checks if item.get("status") == "pass")
    book.row(
        "server",
        "preflight",
        f"ok  {ticket or 'no ticket'}  PR {preflight.get('primaryPr') or 'none'}  "
        f"{passed}/{len(checks)} checks  {preflight.get('appUrl') or settings.qa_url}",
    )
    store.update_run(run_id, status="agent", ticket=ticket, pr=preflight.get("primaryPr"))
    book.phase("coordinator")
    prompt = _lead_prompt(folder, ticket, row.get("specCount"), preflight)
    (folder / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    started = time.time()
    agent_code, session_id = runners.run_opencode(
        folder,
        session_id=None,
        prompt=prompt,
        title=f"{ticket} {run_id}",
        log_name="agent.jsonl",
    )
    if session_id:
        store.update_run(run_id, opencodeSession=session_id)
    runners.export_session(folder, session_id)
    if agent_code != 0:
        reason = _opencode_failure(folder, "agent.jsonl", agent_code)
        book.row("qa", "failed", reason)
        log.error("%s", reason)
        store.update_run(run_id, status="failed", error=reason)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket, "HALTED", summary, [reason])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[reason])
        _seal(run_id, summary, "HALTED")
        return

    book.row("qa", "finished", "coordinator returned")
    book.phase("playwright")
    specs = runners.planned_specs(folder, started)
    if not specs:
        detail = "the agent did not write a spec file"
        book.row("server", "halted", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket, "HALTED", summary, [detail])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[detail])
        _seal(run_id, summary, "HALTED")
        return

    book.row("server", "specs", f"{len(specs)} files  {', '.join(specs)}"[:240])
    summary = _execute_and_heal(run_id, folder, ticket, specs, settings.heal_attempts, session_id, book)
    verdict = verdict_for(summary, preflight_ok=True, produced_specs=True)
    status = "completed" if verdict == "PERFECT" else "needs_revision"
    issues = [] if verdict == "PERFECT" else [_open_issue(summary)]
    book.row(
        "server",
        "verdict",
        f"{verdict}  passed {summary['passed']}  failed {summary['failed']}  skipped {summary.get('skipped', 0)}",
    )
    store.update_run(run_id, status=status, error=None)
    _write_qa_result(folder, ticket, verdict, summary, issues, specs)
    _write_report(folder, store.get_run(run_id) or row, verdict=verdict, summary=summary, issues=issues)
    _seal(run_id, summary, verdict)


def _execute_phase1(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    """Run the checked-in suite against UAT. Heal locators. Keep bugs in this folder."""
    settings = get_settings()
    book.phase("phase 1  checked-in e2e")
    book.row(
        "server",
        "queued",
        'suite "e2e test cases"  UAT  qa-healer only, no new tests  each test is logged below',
    )
    log.info("phase 1 %s started", run_id)
    store.update_run(run_id, status="preflight")
    book.phase("session")
    book.row("server", "session", "signing in. Linear is not called")
    code = runners.run_preflight(folder, ticket=None, pr=None, sha=None, session_only=True)
    preflight = _read_json(folder / "preflight.json")
    if code != 0 or not preflight.get("ok"):
        detail = plain(_failed_check(preflight) or "session failed")
        book.row("server", "session", f"failed  {detail}")
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, None, "HALTED", summary, [detail], extra=_phase1_meta())
        _write_report(
            folder,
            store.get_run(run_id) or row,
            verdict="HALTED",
            summary=summary,
            issues=[detail],
            extra=_phase1_report_lines(),
        )
        _seal(run_id, summary, "HALTED")
        return

    book.row("server", "session", f"ok  {preflight.get('appUrl') or settings.qa_url}")
    specs = runners.checked_in_specs()
    if not specs:
        detail = 'no specs under "e2e test cases"'
        book.row("server", "halted", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, None, "HALTED", summary, [detail], extra=_phase1_meta())
        _write_report(
            folder,
            store.get_run(run_id) or row,
            verdict="HALTED",
            summary=summary,
            issues=[detail],
            extra=_phase1_report_lines(),
        )
        _seal(run_id, summary, "HALTED")
        return

    book.row("server", "specs", f'{len(specs)} files in "e2e test cases"')
    summary = _execute_and_heal(
        run_id,
        folder,
        "checked-in",
        specs,
        settings.heal_attempts,
        "",
        book,
        classify=True,
    )
    hidden = _healer_hid_a_bug(folder)
    verdict = verdict_for(summary, preflight_ok=True, produced_specs=True)
    issues = _phase1_issues(folder, summary)
    if hidden and verdict == "PERFECT":
        verdict = "NEEDS_REVISION"
    status = "completed" if verdict == "PERFECT" else "needs_revision"
    book.row(
        "server",
        "verdict",
        f"{verdict}  passed {summary['passed']}  failed {summary['failed']}  skipped {summary.get('skipped', 0)}  not sent to Linear",
    )
    store.update_run(run_id, status=status, error=None)
    _write_qa_result(folder, None, verdict, summary, issues, specs, extra=_phase1_meta())
    _write_report(
        folder,
        store.get_run(run_id) or row,
        verdict=verdict,
        summary=summary,
        issues=issues,
        extra=_phase1_report_lines() + _triage_section(folder),
    )
    _seal(run_id, summary, verdict)


def _seal(run_id: str, summary: dict[str, Any] | None, verdict: str | None) -> None:
    """Put the final counts in the folder name after every file for this attempt is written."""
    try:
        store.publish_folder(run_id, summary=summary, verdict=verdict)
    except Exception:
        log.exception("run folder was not renamed")


def _phase1_meta() -> dict[str, Any]:
    return {"phase": "checked-in-suite", "linear": False, "suite": "e2e test cases"}


def _phase1_report_lines() -> list[str]:
    return [
        "Phase 1 ran the checked-in Playwright specs in `e2e test cases` against UAT.",
        "Logged in this folder. Not sent to Linear.",
        "",
    ]


def _opencode_failure(folder: Path, log_name: str, code: int) -> str:
    detail = runners.last_opencode_error(folder, log_name)
    if detail:
        return f"opencode exited {code}: {detail}"
    return f"opencode exited {code}"


def _execute_and_heal(
    run_id: str,
    folder: Path,
    ticket: str,
    specs: list[str],
    heal_attempts: int,
    session_id: str,
    book: Logbook,
    *,
    classify: bool = False,
) -> dict[str, int]:
    store.update_run(run_id, status="execute")
    book.row("playwright", "started", f"{len(specs)} files  {', '.join(specs)}"[:240])
    result = runners.run_playwright(folder, specs)
    summary = result["summary"]
    book.row("playwright", "result", _counts(summary))
    if result.get("setupError"):
        book.row("playwright", "error", str(result["setupError"]))
        return summary
    if _suite_passed(result["exitCode"], summary):
        return summary
    for attempt in range(1, heal_attempts + 1):
        store.update_run(run_id, status="heal", healAttempts=attempt)
        book.phase(f"heal {attempt} of {heal_attempts}")
        book.row("server", "heal", f"{attempt} of {heal_attempts}  calling qa-healer for spec drift  {len(specs)} files")
        prompt = (
            _phase1_heal_prompt(folder, attempt, heal_attempts, specs)
            if classify
            else _heal_prompt(folder, ticket, attempt, heal_attempts, specs)
        )
        (folder / f"heal-{attempt}.md").write_text(prompt + "\n", encoding="utf-8")
        before = _suite_revision()
        before_text = _suite_texts() if classify else {}
        heal_code, session_id = runners.run_opencode(
            folder,
            session_id=session_id or None,
            prompt=prompt,
            title=f"{ticket} heal {attempt}",
            log_name=f"heal-{attempt}.jsonl",
            resume=bool(session_id),
        )
        if session_id:
            store.update_run(run_id, opencodeSession=session_id)
        runners.export_session(folder, session_id)
        triage = _take_triage(folder, attempt) if classify and heal_code == 0 else {}
        if classify:
            record_suite_edits(run_id, attempt, before_text, _suite_texts(), triage)
        if heal_code != 0:
            book.row("qa", "failed", _opencode_failure(folder, f"heal-{attempt}.jsonl", heal_code))
            continue
        changed = suite_files_changed(before, _suite_revision())
        if classify and not changed:
            book.row("server", "heal", _unchanged_heal_message(triage))
            break
        for line in suspicious_patches(triage):
            book.row("server", "heal", line[:220])
        if changed:
            book.row("server", "heal", f"patched {', '.join(changed)}"[:240])
        store.update_run(run_id, status="execute")
        book.phase("playwright")
        why = (
            f"re-running after heal {attempt} because a spec file changed"
            if changed
            else f"re-running after heal {attempt}"
        )
        book.row("playwright", "started", why)
        result = runners.run_playwright(folder, specs)
        summary = result["summary"]
        book.row("playwright", "result", _counts(summary))
        if _suite_passed(result["exitCode"], summary):
            return summary
    return summary


def _counts(summary: dict[str, int]) -> str:
    return (
        f"passed {summary.get('passed', 0)}  failed {summary.get('failed', 0)}  "
        f"skipped {summary.get('skipped', 0)}  flaky {summary.get('flaky', 0)}"
    )


def _import_prefix(relative: str) -> str:
    depth = len(Path(relative).joinpath("specs").parts)
    return "/".join([".."] * depth) or "."


def _display(folder: Path) -> str:
    try:
        return str(folder.relative_to(get_settings().root))
    except ValueError:
        return str(folder)


def _lead_prompt(folder: Path, ticket: str, spec_count: int | None, preflight: dict[str, Any]) -> str:
    count = spec_count or 15
    relative = _display(folder)
    connected = ", ".join(preflight.get("connectedTickets") or []) or "none"
    prs = ", ".join(str(number) for number in (preflight.get("pullRequests") or [])) or "none"
    return "\n".join([
        f"Run directory: {relative}",
        f"Ticket: {ticket}",
        f"Pull requests: {prs}",
        f"Connected Linear issues: {connected}",
        "Follow .agents/skills/lexful-autonomous-agent-qa/SKILL.md. You coordinate. Do not browse and do not write specs.",
        f"Cover every acceptance criterion in the context pack. Write at least {count} tests.",
        "A test that passes by skipping the assertion does not count.",
        f"Preflight is already ok: {relative}/preflight.json",
        f"Context pack: {relative}/context-pack.json",
        "Auth cookies: runs/cache/stytch/session.json",
        f"The live URL is the appUrl in the context pack. Do not start a dev server. Put snapshots in {relative}/explore/.",
        f"Delegate Phase 1 to qa-explorer. It writes {relative}/FEATURE.md, with the URL, API calls, and action matrix. It does not write specs.",
        f"Read that file. Then delegate Phase 2 to qa-author. It writes the POM and specs only in {relative}/specs/.",
        f"Leave FEATURE.md at {relative}/FEATURE.md. Do not copy it into specs/ or tests/.",
        f"From a file in {relative}/specs/, import auth as '{_import_prefix(relative)}/auth-helper'. Put the POM in that same specs folder. Do not import anything from tests/.",
        f"planned-specs.json goes in {relative}/. plan_file is {relative}/FEATURE.md. test_files and pom_files are paths like {relative}/specs/<name>.spec.ts.",
        "Do not run preflight, do not call /auth/password, and do not run the Playwright suite.",
    ])


def _heal_prompt(folder: Path, ticket: str, attempt: int, total: int, specs: list[str]) -> str:
    relative = _display(folder)
    listed = ", ".join(specs)
    return "\n".join([
        f"Ticket {ticket}. Heal attempt {attempt} of {total}.",
        f"Playwright results: {relative}/playwright/results.json",
        f"Playwright log: {relative}/playwright/output.log",
        f"Specs: {listed}",
        "Follow the debug loop in .agents/skills/lexful-autonomous-agent-qa/SKILL.md.",
        "Delegate only to qa-healer for one patch. This is one heal of the whole suite, not three attempts per test.",
        "Do not re-explore and do not add scenarios.",
        "Do not run the suite. The server will run it after you return.",
        "If the control is on the page and the product did the wrong thing, do not edit the spec.",
    ])


def _phase1_heal_prompt(folder: Path, attempt: int, total: int, specs: list[str]) -> str:
    relative = _display(folder)
    failures = failed_tests(_read_json(folder / "playwright" / "results.json"))
    listed = "\n".join(
        f"- {item['title']}  ({_short_file(item['file'])})  {item['error']}".rstrip()
        for item in failures[:40]
    ) or "- the Playwright report has failures, but no test title was parsed"
    return "\n".join([
        "This is a checked-in suite heal. It is not a ticket.",
        "Do not call qa-explorer or qa-author. Do not write a new test. Do not call Linear, GitHub, or /auth/password.",
        "Delegate only to qa-healer. In this one return, patch every spec-drift failure, then stop.",
        f"Heal attempt {attempt} of {total}.",
        f"Run directory: {relative}",
        f"Playwright results: {relative}/playwright/results.json",
        f"Playwright log: {relative}/playwright/output.log",
        "Auth cookies: runs/cache/stytch/session.json",
        "The suite is \"e2e test cases\". Edit only a failing spec and the page object or fixture it imports.",
        "Read e2e test cases/changes.log before you edit. It lists locator updates already saved in the suite.",
        "Do not edit a locator that the log already records. Leave that file as it is.",
        "Do not edit e2e test cases/changes.log. The server appends to it after you return.",
        "Do not edit FEATURE.md, playwright.config.ts, or auth-helper.ts.",
        'Write {"failures":[...]} to triage.json in the run directory. class is "spec" or "bug". action is "patched" or "reported".',
        "spec: a renamed locator, a locator that matches several elements, or an existing wait that expired while the snapshot already shows that control. Narrow the locator or raise that timeout. Do not add waitForTimeout. Leave the expected outcome.",
        "bug: a loaded value is wrong, a blocked request was sent, or the page is an error response. Do not edit the spec.",
        "If you are unsure, class it as bug and do not edit.",
        "Failures:",
        listed,
        f"Specs: {', '.join(specs)}",
        "Do not run the suite. The server re-runs it only if you changed a spec file.",
    ])


def _short_file(file: str) -> str:
    marker = "e2e test cases"
    if marker in file:
        return file[file.index(marker):]
    return file


def suite_files_changed(
    before: tuple[tuple[str, int], ...],
    after: tuple[tuple[str, int], ...],
) -> list[str]:
    """Files saved during this heal. An old triage entry that says patched does not count."""
    previous = dict(before)
    return [name for name, mtime in after if previous.get(name) != mtime]


def _unchanged_heal_message(triage: dict[str, Any]) -> str:
    failures = triage.get("failures")
    if not isinstance(failures, list) or not failures:
        return "no spec file changed. Remaining failures stay in this folder."
    bugs = sum(1 for item in failures if isinstance(item, dict) and item.get("class") == "bug")
    specs = sum(1 for item in failures if isinstance(item, dict) and item.get("class") == "spec")
    parts = ["no spec file changed"]
    if bugs:
        parts.append(f"{bugs} product bug(s) logged in this folder")
    if specs:
        parts.append(f"{specs} spec note(s) had no file edit, so the suite is not re-run")
    return ". ".join(parts) + "."


def _suite_root() -> Path:
    return get_settings().root / "e2e test cases"


def _suite_sources() -> list[Path]:
    root = _suite_root()
    if not root.is_dir():
        return []
    return [
        path
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.suffix in {".ts", ".js"} and path.name != "changes.log"
    ]


def _suite_revision() -> tuple[tuple[str, int], ...]:
    root = _suite_root()
    return tuple((path.relative_to(root).as_posix(), path.stat().st_mtime_ns) for path in _suite_sources())


def _suite_texts() -> dict[str, str]:
    root = _suite_root()
    return {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8") for path in _suite_sources()}


def record_suite_edits(
    run_id: str,
    attempt: int,
    before: dict[str, str],
    after: dict[str, str],
    triage: dict[str, Any],
    *,
    log_path: Path | None = None,
) -> None:
    """Append one heal to e2e test cases/changes.log. The same locator is not rewritten from this file."""
    target = log_path or (_suite_root() / "changes.log")
    names = sorted(set(before) | set(after))
    changed: list[str] = []
    diffs: list[str] = []
    for name in names:
        old = before.get(name, "")
        new = after.get(name, "")
        if old == new:
            continue
        changed.append(name)
        diff = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                new.splitlines(keepends=True),
                fromfile=f"e2e test cases/{name}",
                tofile=f"e2e test cases/{name}",
                n=2,
            )
        )
        if len(diff) > 6000:
            diff = diff[:6000] + "\n... diff truncated\n"
        if diff:
            diffs.append(diff.rstrip())
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"{stamp}  {run_id}  heal {attempt}"]
    if changed:
        lines.append("  files: " + ", ".join(f"e2e test cases/{name}" for name in changed))
    else:
        lines.append("  no file changes")
    lines.extend(f"  - {note}" for note in _triage_notes(triage))
    body = "\n".join(lines)
    if diffs:
        body += "\n\n" + "\n\n".join(diffs)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(body.rstrip() + "\n\n")


def _triage_notes(triage: dict[str, Any]) -> list[str]:
    failures = triage.get("failures")
    if not isinstance(failures, list):
        return []
    notes: list[str] = []
    for item in failures:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("test") or "failure")
        kind = str(item.get("class") or "note")
        action = str(item.get("action") or "")
        reason = " ".join(str(item.get("reason") or "").split())
        if len(reason) > 240:
            reason = reason[:240] + "..."
        note = f"{kind} / {action}: {title}" if action else f"{kind}: {title}"
        if reason:
            note = f"{note} — {reason}"
        notes.append(note)
    return notes


def _read_triage(path: Path) -> dict[str, Any]:
    """Accept the object the prompt asks for, or the array the healer wrote."""
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if isinstance(data, list):
        return {"failures": data}
    if isinstance(data, dict):
        if isinstance(data.get("failures"), list):
            return data
        if data.get("class"):
            return {"failures": [data]}
        return data
    return {}


def _failure_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("test") or "unnamed")


def _failure_reason(item: dict[str, Any]) -> str:
    return str(item.get("reason") or item.get("evidence") or "").strip()


def _take_triage(folder: Path, attempt: int) -> dict[str, Any]:
    path = folder / "triage.json"
    data = _read_triage(path)
    if path.is_file():
        path.replace(folder / f"triage-{attempt}.json")
    return data


def _healer_hid_a_bug(folder: Path) -> list[str]:
    lines: list[str] = []
    for path in sorted(folder.glob("triage-*.json")):
        lines.extend(suspicious_patches(_read_triage(path)))
    return lines


def _phase1_issues(folder: Path, summary: dict[str, int]) -> list[str]:
    issues = _healer_hid_a_bug(folder)
    if (
        summary.get("failed", 0) == 0
        and summary.get("skipped", 0) == 0
        and summary.get("passed", 0) > 0
    ):
        return issues
    triages = sorted(folder.glob("triage-*.json"))
    last = _read_triage(triages[-1]) if triages else {}
    lines: list[str] = []
    failures = last.get("failures")
    if isinstance(failures, list):
        for item in failures:
            if not isinstance(item, dict) or item.get("class") not in {"bug", "timing"}:
                continue
            reason = _failure_reason(item)
            text = f"{item.get('class')}: {_failure_title(item)}"
            if reason:
                text += f" — {reason}"
            lines.append(text)
    if not lines:
        lines.append(_open_issue(summary))
    return issues + lines


def _triage_section(folder: Path) -> list[str]:
    triages = sorted(folder.glob("triage-*.json"))
    if not triages:
        return []
    lines = ["## Healer triage", ""]
    for path in triages:
        data = _read_triage(path)
        failures = data.get("failures")
        lines.append(f"### {path.name}")
        lines.append("")
        if not isinstance(failures, list) or not failures:
            lines.append("- healer returned no classified failures")
            lines.append("")
            continue
        for item in failures:
            if not isinstance(item, dict):
                continue
            reason = _failure_reason(item)
            text = f"- {item.get('class')} / {item.get('action')}: {_failure_title(item)}"
            if reason:
                text += f" — {reason}"
            lines.append(text)
        lines.append("")
    return lines


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _failed_check(preflight: dict[str, Any]) -> str:
    for row in preflight.get("checks") or []:
        if isinstance(row, dict) and row.get("status") == "fail":
            return f"{row.get('name')}: {row.get('detail')}"
    return ""


def _write_qa_result(
    folder: Path,
    ticket: str | None,
    verdict: str,
    summary: dict[str, int],
    issues: list[str],
    specs: list[str] | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    settings = get_settings()
    drafted = _read_json(folder / "qa-result.json")
    planned = _read_json(folder / "planned-specs.json")
    payload = {
        "ticket_id": ticket,
        "run_id": folder.name,
        "plan_file": planned.get("plan_file") or drafted.get("plan_file"),
        "test_files": specs or planned.get("test_files") or drafted.get("test_files") or [],
        "pom_files": planned.get("pom_files") or drafted.get("pom_files") or [],
        "verdict": verdict,
        "test_results": summary,
        "models": {"main": settings.main_model, "subagents": settings.sub_model},
        "open_issues": issues or drafted.get("open_issues") or [],
    }
    if extra:
        payload.update(extra)
    (folder / "qa-result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_report(
    folder: Path,
    row: dict[str, Any],
    *,
    verdict: str,
    summary: dict[str, int] | None,
    issues: list[str],
    extra: list[str] | None = None,
) -> None:
    counts = summary or {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
    lines = [
        f"# {row.get('ticket') or row.get('id')}",
        "",
        f"- Run: `{row.get('id')}`",
        f"- Status: {row.get('status')}",
        f"- Verdict: {verdict}",
        f"- Model: {get_settings().main_model} for every step",
        f"- Passed: {counts['passed']}",
        f"- Failed: {counts['failed']}",
        f"- Skipped: {counts['skipped']}",
        "",
    ]
    if extra:
        lines.extend(extra)
        if extra[-1] != "":
            lines.append("")
    if issues:
        lines.append("## Open issues")
        lines.extend(f"- {issue}" for issue in issues)
        lines.append("")
    lines.append("Artifacts in this folder include `preflight.json`, `opencode/`, `playwright/`, and `qa-result.json`. The Stytch session is `runs/cache/stytch/session.json`.")
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
