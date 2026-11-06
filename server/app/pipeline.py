"""One run, from preflight to the sealed folder.

A ticket run: preflight, the E2E User Journey stage (stored in <run>/e2e/), Explore and Author,
Playwright with up to three heals, the affected checked-in cases, verify, the UX audit, promote.
A standalone E2E run: sign in, then the E2E User Journey stage in its own folder under runs/phase-1/.
What each agent phase does is in the skill; the server only sends facts and checks the files.
"""

from __future__ import annotations

import difflib
import json
import logging
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import checks, linear_log, linear_report, prune, runners, store, summary as run_summary
from app.bugs import failure_kind, latest_triage, publish_bugs, publish_findings, same_test, triage_files
from app.coverage import load_cases, write_coverage_index
from app.logbook import Logbook, echo_run, plain, route, unroute
from app.settings import get_settings
from app.ux_report import check_ux_report, write_ux_report

log = logging.getLogger("qa.pipeline")

# One agent (`qa` in opencode.jsonc) runs every phase on the one model. It may write to `e2e test cases/` because the
# E2E heal, the affected heal and promote must. A ticket session may not, so `_guard_suite` puts the suite back.
# E2E heal and promote both rewrite `e2e test cases`; with several runs at once they take turns.
SUITE_LOCK = threading.Lock()


class RunCancelled(Exception):
    """The user cancelled this run while a worker was executing it."""


_CANCELLED: set[str] = set()
_CANCELLED_LOCK = threading.Lock()


def request_cancel(run_id: str) -> int:
    """Flag the run and stop the processes it started. The worker seals it as cancelled."""
    with _CANCELLED_LOCK:
        _CANCELLED.add(run_id)
    return runners.kill_run(store.run_dir(run_id))


def _check_cancel(run_id: str) -> None:
    with _CANCELLED_LOCK:
        cancelled = run_id in _CANCELLED
    if cancelled:
        raise RunCancelled(run_id)


def _begin(run_id: str, book: Logbook, title: str, *, parallel: bool = False) -> None:
    """A phase header in run.log and a row in the end-of-run summary."""
    _check_cancel(run_id)
    book.phase(title)
    run_summary.get(run_id).begin(title, parallel=parallel)


def _end(run_id: str, title: str | None = None, status: str = "ok", detail: str = "") -> None:
    run_summary.get(run_id).end(title, status, detail[:200])


def prompt_files_digest() -> str:
    """One hash of every prompt, skill and reference file, and the OpenCode config."""
    import hashlib

    root = get_settings().root
    digest = hashlib.sha256()
    files = sorted((root / ".agents").rglob("*")) + [root / "opencode.jsonc"]
    for path in files:
        if path.is_file() and not path.is_symlink():
            try:
                digest.update(str(path.relative_to(root)).encode() + b"\0" + path.read_bytes())
            except OSError:
                continue
    return digest.hexdigest()


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


def signoff_blockers(folder: Path) -> list[str]:
    """Ticket requirements still open after a green Playwright run.

    The agent's hand-off files are the contract (`phases/explore-author.md`, hand-off files): coverage.json maps every acceptance
    criterion to passing tests, a gap or `na`; hypotheses.json records every risk tried. The server
    checks those files. It does not guess coverage from the wording of titles.
    """
    issues = checks.unreadable_files(folder)
    issues.extend(checks.coverage_blockers(folder, _passing_title_list(folder)))
    _line, hypothesis_blockers = checks.hypothesis_report(folder)
    issues.extend(hypothesis_blockers)
    issues.extend(f"leftover fixtures: {note}" for note in _leftover_notes(folder))
    return issues


def heal_stopped_on_bugs(triage: dict[str, Any]) -> bool:
    """True when every remaining failure is a product bug, so another heal will not change the spec."""
    failures = triage.get("failures")
    if not isinstance(failures, list) or not failures:
        return False
    kinds = [failure_kind(item) for item in failures if isinstance(item, dict)]
    return bool(kinds) and all(kind == "bug" for kind in kinds)


def _passing_title_list(folder: Path) -> list[str]:
    """Final passing titles after every heal, from test-outcomes.json."""
    try:
        rows = json.loads((folder / "playwright" / "test-outcomes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(rows, list):
        return []
    return [str(r.get("title")) for r in rows if isinstance(r, dict) and r.get("status") in {"passed", "flaky"}]


def _leftover_notes(folder: Path) -> list[str]:
    card = _read_json(folder / "ux-scorecard.json")
    notes = card.get("envNotes")
    if not isinstance(notes, list):
        return []
    found: list[str] = []
    for note in notes:
        text = str(note)
        lowered = text.lower()
        if "leftover" in lowered and ("fixture" in lowered or "attachment" in lowered):
            found.append(text)
    return found


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
    """E2E User Journey TCs go first. Feature Specific TCs wait behind them."""
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
                        message = plain(str(error["message"]).split("\n", 1)[0])[:240]
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


def test_outcomes_from_report(report: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Spec file basename -> test name -> {status: passed|failed|flaky|skipped, tags: ['positive', 'smoke']}.

    The name is the describe titles and the test title (`Bulk Actions › clear selection`), so two tests with
    the same title in different describes stay apart. The tags are the ones the spec declares, as Playwright
    reports them.
    """

    def status_for(test: dict[str, Any]) -> str:
        raw = test.get("status")
        if raw == "expected":
            return "passed"
        if raw == "flaky":
            return "flaky"
        if raw == "skipped":
            return "skipped"
        return "failed"

    found: dict[str, dict[str, dict[str, Any]]] = {}

    def walk(node: Any, current: str, path: tuple[str, ...]) -> None:
        if not isinstance(node, dict):
            return
        current = str(node.get("file") or current)
        if node.get("title") and str(node.get("title")) != str(node.get("file") or ""):
            path = (*path, str(node["title"]))
        for spec in node.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            file_key = _spec_name(str(spec.get("file") or current))
            title = test_key(path, str(spec.get("title") or ""))
            tags = [str(tag) for tag in spec.get("tags") or []]
            tests = [item for item in (spec.get("tests") or []) if isinstance(item, dict)]
            bucket = found.setdefault(file_key, {})
            if tests:
                for test in tests:
                    bucket[title] = {"status": status_for(test), "tags": tags}
            elif spec.get("ok") is False:
                bucket[title] = {"status": "failed", "tags": tags}
        for child in node.get("suites") or []:
            walk(child, current, path)

    for suite in report.get("suites") or []:
        walk(suite, "", ())
    return found


test_outcomes_from_report.__test__ = False  # not a test, although pytest collects names that start with test_


def test_key(describes: tuple[str, ...], title: str) -> str:
    return " › ".join([*describes, title.strip() or "unnamed"])


def test_title(key: str) -> str:
    """The test's own title, without its describes: what Playwright's --grep matches inside the full title."""
    return key.rsplit(" › ", 1)[-1]


def merge_test_outcomes(
    before: dict[str, dict[str, dict[str, Any]]],
    report: dict[str, Any],
    listed: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Each test the rerun ran replaces its earlier result; every other test keeps its result.

    `listed` is what the rerun files hold now (test_outcomes_from_report of a `--list` report): a test a
    heal renamed or removed from those files is dropped instead of staying failed forever.
    """
    merged = {name: dict(tests) for name, tests in before.items()}
    for file_key, tests in test_outcomes_from_report(report).items():
        merged.setdefault(file_key, {}).update(tests)
    for file_key, tests in (listed or {}).items():
        merged[file_key] = {name: row for name, row in merged.get(file_key, {}).items() if name in tests}
    return merged


def outcome_counts(outcomes: dict[str, dict[str, dict[str, Any]]]) -> dict[str, int]:
    """passed, failed, skipped, flaky over every test's latest result."""
    totals = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
    for tests in outcomes.values():
        for row in tests.values():
            status = str(row.get("status"))
            totals[status if status in totals else "failed"] += 1
    return totals


def write_test_outcomes_json(
    folder: Path, outcomes: dict[str, dict[str, dict[str, Any]]], target: Path | None = None,
) -> None:
    """playwright/test-outcomes.json: the final result and tags of every test, after every heal."""
    rows = [
        {"file": file_key, "title": title, "status": row["status"], "tags": row.get("tags") or []}
        for file_key in sorted(outcomes)
        for title, row in sorted(outcomes[file_key].items())
    ]
    target = target or folder / "playwright" / "test-outcomes.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _spec_name(file: str) -> str:
    return Path(file).name


def spec_was_patched(triage: dict[str, Any]) -> bool:
    failures = triage.get("failures")
    if not isinstance(failures, list):
        return False
    return any(
        isinstance(item, dict) and failure_kind(item) == "spec" and item.get("action") == "patched"
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
        kind = failure_kind(item)
        if kind in {"bug", "timing"} and item.get("action") == "patched":
            lines.append(f"healer edited a {kind} failure: {item.get('title')}")
    return lines


def create_triggered_run(*, ticket: str | None, pr: int | None, sha: str | None, trigger: str) -> dict[str, Any]:
    """Create a run in the folder it keeps for good.

    A PR number or a deployed commit is resolved to its ticket first, so the run starts under
    runs/tickets/<ticket>/ and is never moved. When GitHub names no ticket it stays under
    pull-requests/ or deploys/, and preflight's answer is recorded in the index only.
    """
    if not ticket and (pr or sha):
        found = runners.resolve_trigger(pr=pr, sha=None if pr else sha)
        ticket = found.get("ticket") or None
        pr = pr or found.get("pr")
    return store.create_run(ticket=ticket, pr=pr, sha=sha, trigger=trigger)


def execute_run(run_id: str) -> None:
    row = store.get_run(run_id)
    if row is None:
        raise KeyError(run_id)
    if row.get("status") in {"failed", "halted", "completed", "needs_revision"} and not row.get("resume"):
        return  # cancelled or finished while it waited in the queue
    folder = store.run_dir(run_id)
    book = Logbook(folder)
    run_summary.get(run_id)
    prompts_at_start = prompt_files_digest()
    try:
        if row.get("kind") == "phase1":
            with SUITE_LOCK:
                _execute_phase1(run_id, row, folder, book)
        else:
            _execute(run_id, row, folder, book)
    except RunCancelled:
        reason = "cancelled by user"
        book.row("server", "cancelled", "processes stopped; sealing the run")
        store.update_run(run_id, status="failed", error=reason)
        _seal(run_id, None, "HALTED", issues=[reason], error=reason, status="cancelled")
    except Exception as exc:
        book.row("server", "failed", str(exc)[:220])
        log.exception("run failed")
        store.update_run(run_id, status="failed", error=str(exc)[:500])
        _seal(run_id, None, "HALTED", issues=[str(exc)[:500]], error=str(exc)[:200])
    finally:
        if prompt_files_digest() != prompts_at_start:
            # A session that starts or resumes later reads the new text: the phases of this run may disagree.
            book.row("server", "warning", "prompt files under .agents/ or opencode.jsonc changed during this run")
        with _CANCELLED_LOCK:
            _CANCELLED.discard(run_id)
        run_summary.drop(run_id)


def _preflight(run_id: str, row: dict[str, Any], folder: Path, book: Logbook, settings: Any) -> tuple[str, dict[str, Any]] | None:
    """Tools, session, Linear and GitHub context, and the deployment check. None means the run was sealed here."""
    store.update_run(run_id, status="preflight")
    _begin(run_id, book, "preflight")
    book.row("server", "preflight", "started")
    # A named ticket stays the ticket: its PRs come from the context pack. A PR or a deploy keeps its PR primary.
    pr = None if row.get("trigger") == "ticket" else row.get("pr")
    code = runners.run_preflight(folder, ticket=row.get("ticket"), pr=pr, sha=row.get("sha"))
    preflight = _read_json(folder / "preflight.json")
    preflight_ok = code == 0 and bool(preflight.get("ok"))
    ticket = str(preflight.get("ticket") or row.get("ticket") or "")
    if ticket and ticket != row.get("ticket"):
        store.update_run(run_id, ticket=ticket, pr=preflight.get("primaryPr"), sha=row.get("sha"))
    if not preflight_ok:
        detail = plain(_failed_check(preflight) or "preflight failed")
        book.row("server", "preflight", f"failed  {detail}")
        _end(run_id, "preflight", "failed", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket or None, "HALTED", summary, [detail])
        _seal(run_id, summary, "HALTED", issues=[detail])
        return None

    checks_rows = [item for item in (preflight.get("checks") or []) if isinstance(item, dict)]
    passed = sum(1 for item in checks_rows if item.get("status") == "pass")
    book.row(
        "server",
        "preflight",
        f"ok  {ticket or 'no ticket'}  PR {preflight.get('primaryPr') or 'none'}  "
        f"{passed}/{len(checks_rows)} checks  {preflight.get('appUrl') or settings.qa_url}",
    )
    deployment = _deployment_line(folder)
    if deployment:
        book.row("server", "deployment", deployment[:220])
        run_summary.get(run_id).note("deployment", deployment)
    _end(run_id, "preflight")
    store.update_run(run_id, ticket=ticket or None, pr=preflight.get("primaryPr"))
    return ticket, preflight


def _e2e_stage(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    """E2E User Journey TCs as the first stage of a ticket run. Its files go to <run>/e2e/, its log lines to run.log.

    The checked-in suite runs against the build this ticket is tested on, so its result belongs to this run.
    A ticket run never starts a separate E2E run folder.
    """
    e2e = folder / "e2e"
    if (e2e / "qa-result.json").is_file():
        book.row("server", "e2e", "already ran in this folder; continuing")
        return
    e2e.mkdir(parents=True, exist_ok=True)
    book.phase("E2E User Journey TCs")
    route(e2e, folder)
    try:
        with SUITE_LOCK:
            summary, verdict, _issues = _e2e_suite(run_id, row, e2e, book, stage="e2e ", context=folder)
    finally:
        unroute(e2e)
    run_summary.get(run_id).note("e2e", f"{verdict}  {_counts(summary)}")
    book.phase(f"Feature Specific TCs  {row.get('ticket') or run_id}")


def _explore_and_author(
    run_id: str, folder: Path, book: Logbook, ticket: str, preflight: dict[str, Any], settings: Any,
) -> tuple[str, float] | None:
    """The qa agent maps the feature, walks the app and writes the specs. None means the run was sealed here."""
    store.update_run(run_id, status="agent")
    _begin(run_id, book, "explore + author")
    covered = write_coverage_index(settings.root / "e2e test cases", folder / "e2e-coverage.md")
    book.row("server", "coverage", f"{covered} checked-in cases")
    history = write_history(folder, ticket)
    if history:
        book.row("server", "history", f"{history} earlier run(s) of {ticket} in history.md")
    index = _read_json(folder / "context" / "index.json")
    if index:
        images = index.get("images") or []
        saved = sum(1 for image in images if image.get("file"))
        named = len(index.get("tickets") or []) + len(index.get("pulls") or [])
        book.row("server", "context", f"{len(index.get('files') or [])} files, {saved} of {len(images)} images, {named} more named, {len(index.get('readFirst') or [])} to read first")
    else:
        book.row("server", "context", "no context/ folder, the brief is all there is")
    source = runners.prepare_source(folder)
    book.row("server", "source", "read-only worktree ready" if source else "no clone, agent greps the context pack")
    cli_config = runners.write_cli_config(folder)
    if cli_config:
        book.row("server", "browser", "playwright-cli config written")
    prompt = _lead_prompt(folder, ticket, preflight, run_id)
    (folder / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    started = time.time()
    suite_before = _suite_files()
    agent_code, session_id = runners.run_opencode(
        folder, session_id=None, prompt=prompt, title=f"{ticket} {run_id}", log_name="agent.jsonl",
    )
    _guard_suite(suite_before, book, "explore")
    _check_cancel(run_id)
    if session_id:
        store.update_run(run_id, opencodeSession=session_id)
    runners.export_session(folder, session_id)
    if agent_code != 0 and _handoff_written(folder, started):
        # The agent finished and wrote its handoff; only the connection dropped afterwards.
        book.row("server", "agent", f"opencode exited {agent_code} after the handoff was written. Continuing to Playwright")
        agent_code = 0
    if agent_code != 0:
        reason = _opencode_failure(folder, "agent.jsonl", agent_code)
        book.row("qa", "failed", reason)
        _end(run_id, "explore + author", "failed", reason)
        log.error("%s", reason)
        store.update_run(run_id, status="failed", error=reason)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket, "HALTED", summary, [reason])
        _seal(run_id, summary, "HALTED", issues=[reason])
        return None
    _repair_handoff(run_id, folder, book, ticket, session_id)
    _end(run_id, "explore + author")
    return session_id, started


def _repair_handoff(run_id: str, folder: Path, book: Logbook, ticket: str, session_id: str) -> None:
    """One short turn in the explore session when its hand-off is incomplete or a spec has a known bad pattern.

    The session still holds the walk, so it can write a missing coverage.json or swap a selector for a
    few cents. Problems left after the turn stay in the run: the sign-off checks report them.
    """
    problems = checks.handoff_problems(folder)
    lint = checks.spec_lint(folder)
    if not problems and not lint:
        return
    book.row("server", "handoff", f"{len(problems)} hand-off problem(s), {len(lint)} spec pattern(s); one repair turn")
    prompt = _message(
        "explore+author", folder,
        "The server checked your hand-off. Fix only what is listed, then stop. Do not walk again unless an item needs it.",
        *(["Hand-off:", *[f"- {p}" for p in problems]] if problems else []),
        *(["Spec patterns to replace:", *[f"- {line}" for line in lint[:30]]] if lint else []),
    )
    (folder / "handoff-repair.md").write_text(prompt + "\n", encoding="utf-8")
    suite_before = _suite_files()
    code, _session = runners.run_opencode(
        folder, session_id=session_id or None, prompt=prompt, title=f"{ticket} hand-off repair",
        log_name="agent-repair.jsonl",
    )
    _guard_suite(suite_before, book, "explore")
    _check_cancel(run_id)
    left = checks.handoff_problems(folder)
    left_lint = checks.spec_lint(folder)
    book.row("server", "handoff", (
        "repaired" if not left and not left_lint
        else f"after repair: {len(left)} hand-off problem(s), {len(left_lint)} spec pattern(s) left"
    ) + ("" if code == 0 else f" (opencode exited {code})"))
    for line in left_lint[:5]:
        book.row("server", "lint", line[:220])


def _guard_suite(before: dict[str, str], book: Logbook, phase: str) -> None:
    """A ticket session may not change `e2e test cases/`. Put it back when this is the only run."""
    after = _suite_files()
    if after == before:
        return
    changed = sorted(set(before) ^ set(after) | {name for name in before if name in after and before[name] != after[name]})
    if get_settings().max_parallel_runs == 1:
        _restore_suite(before)
        book.row("server", "suite", f"{phase} changed the checked-in suite; reverted {', '.join(changed)}"[:220])
    else:
        book.row("server", "suite", f"the checked-in suite changed during {phase} (another run may own it): {', '.join(changed)}"[:220])


def _handoff_written(folder: Path, started: float) -> bool:
    """True when this run wrote planned-specs.json and at least one runnable spec."""
    plan = folder / "planned-specs.json"
    return plan.is_file() and plan.stat().st_mtime >= started and bool(runners.planned_specs(folder, started))


def _execute(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    settings = get_settings()
    echo_run(folder)
    book.phase(f"Feature Specific TCs  {row.get('ticket') or run_id}")
    book.row("server", "queued", str(row.get("ticket") or run_id))
    if row.get("resume") and (folder / "planned-specs.json").is_file():
        # Explore and Author already finished in this folder. Continue from Playwright.
        book.row("server", "resume", "continuing from Playwright; Explore and Author already ran")
        run_summary.get(run_id).begin("explore + author (earlier attempt)")
        _end(run_id, "explore + author (earlier attempt)", "skipped", "resumed")
        preflight = _read_json(folder / "preflight.json")
        ticket = str(preflight.get("ticket") or row.get("ticket") or "")
        session_id = str(row.get("opencodeSession") or "")
        started = 0.0
        store.update_run(run_id, status="agent", resume=False, error=None)
    else:
        checked = _preflight(run_id, row, folder, book, settings)
        if checked is None:
            return
        ticket, preflight = checked
        if settings.e2e_with_ticket:
            _e2e_stage(run_id, store.get_run(run_id) or row, folder, book)
        explored = _explore_and_author(run_id, folder, book, ticket, preflight, settings)
        if explored is None:
            return
        session_id, started = explored
        book.row("qa", "finished", "coordinator returned")
    specs = runners.planned_specs(folder, started)
    if not specs:
        detail = "the agent did not write a spec file"
        book.row("server", "halted", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket, "HALTED", summary, [detail])
        _seal(run_id, summary, "HALTED", issues=[detail])
        return

    # The UX audit reads only the Explore files, so it runs while Playwright and heal run.
    ux_thread: threading.Thread | None = None
    ux_state: dict[str, Any] = {}
    if settings.run_ux_audit and ticket:
        if settings.ux_parallel:
            ux_thread = threading.Thread(
                target=_run_ux_audit, args=(run_id, folder, ticket, preflight, ux_state, True), daemon=True,
            )
            _begin(run_id, book, "ui-ux audit", parallel=True)
            book.row("server", "ux-audit", "started beside Playwright. Its lines are marked ux-audit")
            ux_thread.start()
    elif ticket:
        book.row("server", "ux-audit", "off  QA_RUN_UX_AUDIT=false  functional QA only")

    try:
        book.row("server", "specs", f"{len(specs)} files  {', '.join(specs)}"[:240])
        summary = _execute_and_heal(run_id, folder, ticket, specs, settings.heal_attempts, session_id, book)
        affected = _run_affected_cases(run_id, folder, book)
        signals = checks.summarize_signals(folder)
        if signals["count"]:
            book.row("server", "signals", signals["line"][:220])
            run_summary.get(run_id).note("signals", signals["line"])
    finally:
        if ux_thread is not None:
            if ux_thread.is_alive():
                book.row("server", "ux-audit", "waiting for the UX audit to finish")
            ux_thread.join()
    _check_cancel(run_id)
    if settings.run_ux_audit and ticket and not settings.ux_parallel:
        _begin(run_id, book, "ui-ux audit")
        _run_ux_audit(run_id, folder, ticket, preflight, ux_state, False)
    # After the audit: it may raise suspected defects, and everything in api-findings.json is filed unless verified away.
    if settings.verify_findings:
        _verify_findings(run_id, folder, ticket, book, signals)
        _check_cancel(run_id)
    ux_issue = _finish_ux(run_id, folder, ticket, book, ux_state) if settings.run_ux_audit and ticket else ""

    # Bugs are filed before the verdict, so a bug found while every test passed still blocks sign-off.
    bugs_filed = _record_bugs(folder, store.get_run(run_id) or row, summary)
    verdict = verdict_for(summary, preflight_ok=True, produced_specs=True)
    issues = [] if verdict == "PERFECT" else [_open_issue(summary)]
    blockers = signoff_blockers(folder) if ticket else []
    blockers.extend(affected)
    blockers.extend(filed_bug_blockers(folder))
    blockers.extend(e2e_stage_blockers(folder))
    blockers.extend(reported_but_passed(folder))
    blockers.extend(unstable_notes(folder))
    edits = checks.assertion_edits(folder)
    if edits:
        run_summary.get(run_id).note("assertions", f"{len(edits)} expectation(s) changed by heal")
        blockers.extend(f"heal changed an expectation, review it: {line}" for line in edits[:5])
    if ux_issue:
        blockers.append(ux_issue)
    if blockers:
        issues = [*issues, *blockers]
        if verdict == "PERFECT":
            verdict = "NEEDS_REVISION"
    status = "completed" if verdict == "PERFECT" else "needs_revision"
    book.row(
        "server",
        "verdict",
        f"{verdict}  passed {summary['passed']}  failed {summary['failed']}  skipped {summary.get('skipped', 0)}",
    )
    for blocker in blockers:
        book.row("server", "signoff", blocker[:220])

    if ticket and int(summary.get("passed") or 0) > 0:
        _begin(run_id, book, "promote")
        store.update_run(run_id, status="promote")
        with SUITE_LOCK:
            outcome = _promote_into_suite(run_id, folder, ticket, book)
        run_summary.get(run_id).note("promote", outcome)
        _end(run_id, "promote", "reverted" if outcome.startswith("reverted") else "ok", outcome)

    store.update_run(run_id, status=status, error=None)
    if bugs_filed:
        book.row("server", "bugs", "bugs.json and bugs.md")
    _note_findings(run_id, folder)
    _write_qa_result(folder, ticket, verdict, summary, issues, specs)
    _seal(run_id, summary, verdict, issues=issues)


def _run_ux_audit(
    run_id: str, folder: Path, ticket: str, preflight: dict[str, Any], state: dict[str, Any], parallel: bool,
) -> None:
    """One UX audit session. Errors are kept in `state`; the run goes on without the audit."""
    state["started"] = time.time()
    try:
        ux_prompt = _ux_audit_prompt(folder, ticket, preflight, parallel=parallel)
        (folder / "ux-prompt.md").write_text(ux_prompt + "\n", encoding="utf-8")
        code, session = runners.run_opencode(
            folder,
            session_id=None,
            prompt=ux_prompt,
            title=f"{ticket} ux-audit",
            log_name="ux-audit.jsonl",
            role="ux-audit",
        )
        state["code"] = code
        runners.export_session(folder, session, "session-ux.json")
        if code != 0:
            state["error"] = _opencode_failure(folder, "ux-audit.jsonl", code)
    except Exception as exc:  # the audit must not take the functional run down with it
        log.exception("ux audit crashed")
        state["code"] = 1
        state["error"] = f"ux audit crashed: {exc}"[:240]


def _finish_ux(run_id: str, folder: Path, ticket: str, book: Logbook, state: dict[str, Any]) -> str:
    """Score and render the audit. Returns an open issue when the audit did not finish."""
    code = int(state.get("code", 1))
    started = float(state.get("started") or 0)
    findings_file = folder / "ux-findings.json"
    wrote = findings_file.is_file() and findings_file.stat().st_mtime >= started - 1
    error = str(state.get("error") or ("" if code == 0 else f"opencode exited {code}"))
    contract: list[str] = []
    if wrote:
        write_ux_report(folder, ticket)
        contract = check_ux_report(folder)
        if contract:
            for failure in contract[:5]:
                book.row("server", "ux-contract", f"FAIL  {failure[:200]}")
        elif (folder / "ux-report.html").is_file():
            book.row("server", "ux-contract", "ux-report.html passed the report contract check")
    card = _read_json(folder / "ux-scorecard.json")
    if not wrote:
        card = {"ticket": ticket, "verdict": "NOT RUN", "score": None, "error": error or "the auditor wrote no ux-findings.json"}
        (folder / "ux-scorecard.json").write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    elif code != 0:
        card["verdict"] = f"INCOMPLETE ({card.get('verdict', 'unscored')})"
        card["error"] = error
        (folder / "ux-scorecard.json").write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    count = len(_read_findings(findings_file)) if wrote else 0
    score = card.get("score")
    line = f"verdict {card.get('verdict')}  score {score if score is not None else 'not scored'}  {count} finding(s)"
    book.row("server", "ux-audit", line + (f"  {error}" if error else ""))
    run_summary.get(run_id).note("ux", line)
    _end(run_id, "ui-ux audit", "ok" if code == 0 and wrote else "failed", error)
    if not wrote:
        return f"UX audit did not run to the end: {error or 'no findings written'}"
    if code != 0:
        return f"UX audit stopped early, findings are partial: {error}"
    if contract:
        more = f" (and {len(contract) - 1} more)" if len(contract) > 1 else ""
        return f"ux-report.html failed the report contract check: {contract[0][:200]}{more}"
    return ""


def _execute_phase1(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    """E2E User Journey TCs on their own (npm run e2e): sign in, run and heal the suite, seal under runs/phase-1/."""
    settings = get_settings()
    echo_run(folder)
    book.phase("E2E User Journey TCs")
    book.row(
        "server",
        "queued",
        'suite "e2e test cases"  UAT  qa heal only, no new tests  each test is logged below',
    )
    log.info("E2E User Journey TCs %s started", run_id)
    store.update_run(run_id, status="preflight")
    _begin(run_id, book, "session")
    book.row("server", "session", "signing in. Linear is not called")
    code = runners.run_preflight(folder, ticket=None, pr=None, sha=None, session_only=True)
    preflight = _read_json(folder / "preflight.json")
    if code != 0 or not preflight.get("ok"):
        detail = plain(_failed_check(preflight) or "session failed")
        book.row("server", "session", f"failed  {detail}")
        _end(run_id, "session", "failed", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, None, "HALTED", summary, [detail], extra=_phase1_meta())
        _seal(run_id, summary, "HALTED", issues=[detail])
        return
    book.row("server", "session", f"ok  {preflight.get('appUrl') or settings.qa_url}")
    _end(run_id, "session")
    summary, verdict, issues = _e2e_suite(run_id, row, folder, book)
    status = "completed" if verdict == "PERFECT" else "halted" if verdict == "HALTED" else "needs_revision"
    store.update_run(run_id, status=status, error=None)
    _note_findings(run_id, folder)
    _seal(run_id, summary, verdict, issues=issues)


def _e2e_suite(
    run_id: str, row: dict[str, Any], folder: Path, book: Logbook, *, stage: str = "", context: Path | None = None,
) -> tuple[dict[str, int], str, list[str]]:
    """Run the checked-in suite with `folder` as its run directory, heal it, verify and file its bugs.

    Shared by the standalone E2E run and the E2E stage of a ticket run. It writes qa-result.json,
    playwright/test-outcomes.json, triage and bugs into `folder` and does not seal anything.
    `context` is the folder whose context pack names the deployed build (the ticket run).
    """
    settings = get_settings()
    specs = runners.checked_in_specs()
    if not specs:
        detail = 'no specs under "e2e test cases"'
        book.row("server", "halted", detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, None, "HALTED", summary, [detail], extra=_phase1_meta())
        return summary, "HALTED", [detail]
    book.row("server", "specs", f'{len(specs)} files in "e2e test cases"')
    runners.write_cli_config(folder)
    summary = _execute_and_heal(run_id, folder, "checked-in", specs, settings.heal_attempts, "", book,
                                classify=True, stage=stage)
    decisions = suite_decisions()
    outcomes = _outcomes_from_file(folder)
    waiting = decided_failures(outcomes, decisions)
    judged = {**summary, "failed": max(0, int(summary.get("failed") or 0) - len(waiting))}
    verdict = verdict_for(judged, preflight_ok=True, produced_specs=True)
    issues = _phase1_issues(folder, judged) + unstable_notes(folder)
    issues += [f"waiting for a decision (decisions.json): {line}" for line in waiting]
    if _healer_hid_a_bug(folder) and verdict == "PERFECT":
        verdict = "NEEDS_REVISION"
    book.row("server", "verdict", f"{stage}{verdict}  {_counts(summary)}")
    # A bug in the checked-in suite is not this ticket's bug: it is filed under the E2E suite.
    if _record_bugs(folder, {"id": run_id, "ticket": None, "sha": row.get("sha")}, summary, context=context or folder):
        book.row("server", "bugs", f"{stage}bugs.json and bugs.md")
    dropped = _drop_decided_bugs(folder, decisions)
    if dropped:
        book.row("server", "bugs", f"{stage}{dropped} bug(s) not filed: their cases wait for a decision")
    _write_qa_result(folder, None, verdict, summary, issues, specs, extra=_phase1_meta())
    return summary, verdict, issues


def _seal(
    run_id: str,
    summary: dict[str, Any] | None,
    verdict: str | None,
    *,
    issues: list[str] | None = None,
    error: str = "",
    status: str = "",
) -> None:
    """Write the run summary and reports, record the result in the index, and prune. The folder stays put."""
    folder = store.run_dir(run_id)
    book = Logbook(folder)
    row = store.get_run(run_id) or {}
    try:
        run_summary.write(
            run_id, folder, book,
            ticket=str(row.get("ticket") or ("E2E User Journey TCs" if row.get("kind") == "phase1" else "")),
            verdict=verdict or "HALTED",
            status=status or str(row.get("status") or ""),
            counts=summary,
            issues=issues or [],
            costs=phase_costs(folder),
            error=error,
        )
    except Exception:
        log.exception("run summary was not written")
    try:
        linear_report.write(folder, row, verdict=verdict or "HALTED", issues=issues or [])
    except Exception:
        log.exception("linear report was not written")
    _log_to_linear(run_id, folder, row, status or str(row.get("status") or ""))
    try:
        runners.cleanup_source(folder)
    except Exception:
        log.exception("worktree was not removed")
    try:
        target = store.record_outcome(run_id, summary=summary, verdict=verdict)
        Logbook(folder).row("server", "folder", f"runs/{target}")
    except Exception:
        log.exception("run outcome was not recorded")
    try:
        finished = (status or str(row.get("status") or "")) in {"completed", "needs_revision"}
        freed = prune.prune_run(folder, finished=finished)
        if freed:
            Logbook(folder).row("server", "prune", f"removed {prune.mib(freed)} of scratch and duplicate files")
    except Exception:
        log.exception("run folder was not pruned")


def _log_to_linear(run_id: str, folder: Path, row: dict[str, Any], status: str) -> None:
    """Optional last step of a finished run: tracking ticket, comment, bug tickets. Never fails the run."""
    if not linear_log.is_enabled():
        return
    book = Logbook(folder)
    if status not in linear_log.FINISHED:
        book.row("server", "linear", f"not filed: the run ended as {status or 'unknown'}")
        return
    try:
        manifest = store.get_run(run_id) or row
        attempt, total = linear_log.attempt_of(manifest, store.list_runs())
        result = linear_log.file_run(folder, store.relative_folder(manifest), manifest, attempt, total)
        bugs = len(result["feature_bugs"]) + len(result["e2e_bugs"])
        book.row("server", "linear", f"{result['ticket']['identifier']}: comment added, {bugs} bug(s) handled")
    except Exception as exc:
        log.exception("run was not logged to Linear")
        book.row("server", "linear", f"not filed: {str(exc)[:200]}. Retry: python -m app.linear_log {run_id}")


def _phase1_meta() -> dict[str, Any]:
    return {"name": "E2E User Journey TCs", "linear": False, "suite": "e2e test cases"}


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
    stage: str = "",
) -> dict[str, int]:
    """Playwright on every spec, then up to `heal_attempts` heals. `stage` prefixes the phase names ("e2e ").

    After a heal only the tests that did not pass run again (and any test the heal added or renamed),
    not their whole files. Once the heals are done, every spec in a folder a heal edited, and every file
    that still fails, runs in full one time, so a page-object fix that broke a passing test is caught.
    """
    store.update_run(run_id, status="execute")
    _begin(run_id, book, f"{stage}playwright")
    book.row("playwright", "started", f"{len(specs)} files  {', '.join(specs)}"[:240])
    result = runners.run_playwright(folder, specs)
    _check_cancel(run_id)
    summary = result["summary"]
    book.row("playwright", "result", _counts(summary))
    _end(run_id, f"{stage}playwright", "ok" if not result.get("setupError") else "failed", _counts(summary))
    test_outcomes = test_outcomes_from_report(_read_json(folder / "playwright" / "results.json"))
    if result.get("setupError"):
        book.row("playwright", "error", str(result["setupError"]))
        write_test_outcomes_json(folder, test_outcomes)
        return summary
    if _suite_passed(result["exitCode"], summary):
        write_test_outcomes_json(folder, test_outcomes)
        return summary
    attempts_used: dict[str, int] = {}
    edited: set[Path] = set()
    edited_files: set[Path] = set()
    verifier_hints_now: dict[str, str] = {}
    fresh_heal = not classify and get_settings().heal_fresh_session
    if fresh_heal:
        session_id = ""  # round 1 starts clean; later rounds resume that small session
    for attempt in range(1, heal_attempts + 1):
        store.update_run(run_id, status="heal", healAttempts=attempt)
        _begin(run_id, book, f"{stage}heal {attempt} of {heal_attempts}")
        who = "qa E2E heal" if classify else "qa feature heal"
        book.row("server", "heal", f"{attempt} of {heal_attempts}  {who}  {len(specs)} files")
        failing_now = failed_tests(_read_json(folder / "playwright" / "results.json"))
        if classify:
            decisions = suite_decisions()
            waiting = [f for f in failing_now if decision_for(f["title"], decisions)]
            if waiting and len(waiting) == len(failing_now):
                book.row("server", "heal", f"skipped: {len(waiting)} failing case(s) wait for a decision in decisions.json")
                _end(run_id, None, "skipped", "every failure waits for a decision")
                break
        for item in failing_now:
            attempts_used[item["title"]] = attempts_used.get(item["title"], 0) + 1
        prompt = (
            _phase1_heal_prompt(folder, attempt, heal_attempts, specs, verifier_hints_now)
            if classify
            else _heal_prompt(folder, ticket, attempt, heal_attempts, specs, failing_now, attempts_used)
        )
        (folder / f"heal-{attempt}.md").write_text(prompt + "\n", encoding="utf-8")
        before = _heal_revision(folder, classify)
        before_text = _suite_texts() if classify else {}
        before_specs = checks.spec_texts(folder) if not classify else {}
        suite_before = _suite_files() if not classify else {}
        heal_code, session_id = runners.run_opencode(
            folder,
            session_id=session_id or None,
            prompt=prompt,
            title=f"{ticket} heal {attempt}",
            log_name=f"heal-{attempt}.jsonl",
            resume=bool(session_id),
        )
        _check_cancel(run_id)
        if not classify:
            _guard_suite(suite_before, book, f"heal {attempt}")
            edits = checks.record_assertion_edits(folder, attempt, before_specs, checks.spec_texts(folder))
            for line in edits[:3]:
                book.row("server", "assertion", f"heal {attempt} changed an expectation: {line}"[:220])
        if session_id and not fresh_heal:
            store.update_run(run_id, opencodeSession=session_id)
        runners.export_session(folder, session_id, "session-heal.json" if fresh_heal else "session.json")
        triage = _take_triage(folder, attempt)
        if classify and heal_code == 0:
            record_suite_edits(run_id, attempt, before_text, _suite_texts(), triage)
            # A checked-in case that fails is outdated until a person-style reproduction says otherwise.
            if get_settings().verify_findings and any(isinstance(b, dict) for b in triage.get("bugs") or []):
                verifier_hints_now = _verify_findings(
                    run_id, folder, "checked-in", book, {}, label=f"{stage}verify bugs after heal {attempt}")
                triage = latest_triage(folder)[0]
        if heal_code != 0:
            reason = _opencode_failure(folder, f"heal-{attempt}.jsonl", heal_code)
            book.row("qa", "failed", reason)
            _end(run_id, None, "failed", reason)
            continue
        changed = suite_files_changed(before, _heal_revision(folder, classify))
        for line in suspicious_patches(triage):
            book.row("server", "heal", line[:220])
        if not changed:
            message = _unchanged_heal_message(triage)
            book.row("server", "heal", message)
            _end(run_id, None, "ok", message)
            if heal_stopped_on_bugs(triage) and not verifier_hints_now:
                break
            continue
        book.row("server", "heal", f"patched {', '.join(changed)}"[:240])
        base = _suite_root() if classify else folder / "specs"
        edited.update((base / name).resolve().parent for name in changed)
        edited_files.update((base / name).resolve() for name in changed)
        store.update_run(run_id, status="execute")
        _begin(run_id, book, f"{stage}playwright after heal {attempt}")
        test_outcomes = _rerun_not_passed(folder, specs, test_outcomes, book, attempt)
        _check_cancel(run_id)
        summary = outcome_counts(test_outcomes)
        book.row("playwright", "result", _counts(summary))
        _end(run_id, None, "ok", _counts(summary))
        if verdict_for(summary, preflight_ok=True, produced_specs=True) == "PERFECT":
            break
    if edited:
        store.update_run(run_id, status="execute")
        _begin(run_id, book, f"{stage}playwright confirm")
        test_outcomes = _confirm_after_heals(folder, specs, test_outcomes, edited, book, edited_files)
        _check_cancel(run_id)
        summary = outcome_counts(test_outcomes)
        book.row("playwright", "result", _counts(summary))
        _end(run_id, None, "ok", _counts(summary))
    write_test_outcomes_json(folder, test_outcomes)
    return summary


_RELATIVE_IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"](\.{1,2}/[^'"]+)['"]""")


def spec_dependencies(spec: Path, limit: int = 60) -> set[Path]:
    """The spec and every local file it imports, followed through relative imports (`./x-pom`)."""
    seen: set[Path] = set()
    todo = [spec.resolve()]
    while todo and len(seen) < limit:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        try:
            text = current.read_text(encoding="utf-8")
        except OSError:
            continue
        for target in _RELATIVE_IMPORT.findall(text):
            base = (current.parent / target).resolve()
            for candidate in (base, *(base.with_name(base.name + ext) for ext in (".ts", ".tsx", ".js", ".mjs"))):
                if candidate.is_file():
                    todo.append(candidate)
                    break
    return seen


def _outcomes_from_file(folder: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """test-outcomes.json back into {file: {test: row}}."""
    try:
        rows = json.loads((folder / "playwright" / "test-outcomes.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found: dict[str, dict[str, dict[str, Any]]] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            found.setdefault(str(row.get("file") or ""), {})[str(row.get("title") or "")] = row
    return found


def _not_passed(outcomes: dict[str, dict[str, dict[str, Any]]]) -> dict[str, set[str]]:
    """Spec file -> the tests whose latest result is failed or skipped."""
    found = {
        file_key: {name for name, row in tests.items() if row.get("status") in {"failed", "skipped"}}
        for file_key, tests in outcomes.items()
    }
    return {file_key: names for file_key, names in found.items() if names}


def _rerun_not_passed(
    folder: Path, specs: list[str], outcomes: dict[str, dict[str, dict[str, Any]]], book: Logbook, attempt: int,
) -> dict[str, dict[str, dict[str, Any]]]:
    """After a heal, run the tests that did not pass, and any test the heal added or renamed. Nothing else.

    The files are listed first (`playwright test --list`), so a renamed test runs under its new name and a
    removed one leaves the record. When the list cannot be read, the failing files run whole.
    """
    pending = _not_passed(outcomes)
    files = [spec for spec in specs if _spec_name(spec) in pending] or specs
    listing = runners.list_tests(files)
    if listing is None:
        book.row("playwright", "started", f"re-running {len(files)} file(s) in full after heal {attempt} (the test list could not be read)"[:240])
        runners.run_playwright(folder, files)
        report = _read_json(folder / "playwright" / "results.json")
        return merge_test_outcomes(outcomes, report, test_outcomes_from_report(report))
    listed = test_outcomes_from_report(listing)
    wanted = sorted({
        test_title(name)
        for file_key, tests in listed.items()
        for name in tests
        if name in pending.get(file_key, set()) or name not in outcomes.get(file_key, {})
    })
    if not wanted:
        book.row("server", "heal", f"heal {attempt} removed the tests that did not pass; nothing to re-run")
        return merge_test_outcomes(outcomes, {}, listed)
    book.row("playwright", "started", f"re-running {len(wanted)} test(s) that did not pass, in {len(files)} file(s), after heal {attempt}"[:240])
    runners.run_playwright(folder, files, grep="|".join(re.escape(title) for title in wanted))
    return merge_test_outcomes(outcomes, _read_json(folder / "playwright" / "results.json"), listed)


def _confirm_after_heals(
    folder: Path, specs: list[str], outcomes: dict[str, dict[str, dict[str, Any]]], edited: set[Path], book: Logbook,
    edited_files: set[Path] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """One full run of every spec in a folder a heal edited, and of every file that still fails.

    The heal reruns only ran what had failed. A page object or helper the heal changed is shared by the
    other specs in its folder, so they run once more before the result is final. The last results.json
    then holds every remaining failure, which the bug screenshots are taken from.
    """
    root = get_settings().root
    pending = _not_passed(outcomes)
    files = [spec for spec in specs if (root / spec).resolve().parent in edited or _spec_name(spec) in pending]
    if not files:
        return outcomes
    book.row("playwright", "started", f"confirming {len(files)} file(s) in full after the heals: {', '.join(files)}"[:240])
    runners.run_playwright(folder, files)
    report = _read_json(folder / "playwright" / "results.json")
    merged = merge_test_outcomes(outcomes, report, test_outcomes_from_report(report))
    return mark_unstable(folder, outcomes, merged, files, edited, book, edited_files)


def mark_unstable(
    folder: Path,
    before: dict[str, dict[str, dict[str, Any]]],
    after: dict[str, dict[str, dict[str, Any]]],
    files: list[str],
    edited: set[Path],
    book: Logbook | None = None,
    edited_files: set[Path] | None = None,
) -> dict[str, dict[str, dict[str, Any]]]:
    """A test that passed earlier in this run and fails only in the confirm pass is unstable, not failed.

    It ran again only because a heal edited its folder or another test in its file still failed. When
    no heal edited its spec or a file the spec imports, the code is the one that passed: the difference
    is data left by other tests, timing or UAT. It counts as flaky and is reported. A test whose spec or
    imports a heal edited keeps its failure: the edit may have broken it. Without the list of edited
    files (`edited_files`), any edit in its folder counts.
    """
    root = get_settings().root
    path_of = {_spec_name(spec): (root / spec).resolve() for spec in files}
    names: list[str] = []
    for file_key, tests in after.items():
        spec_path = path_of.get(file_key)
        if spec_path is None:
            continue
        if edited_files is None:
            if spec_path.parent in edited:
                continue
        elif spec_dependencies(spec_path) & edited_files:
            continue
        for name, row in list(tests.items()):
            earlier = (before.get(file_key) or {}).get(name) or {}
            if row.get("status") == "failed" and earlier.get("status") in {"passed", "flaky"}:
                tests[name] = {**row, "status": "flaky", "unstable": True}
                names.append(f"{file_key} › {name}")
    if names:
        (folder / "playwright").mkdir(parents=True, exist_ok=True)
        (folder / "playwright" / "unstable.json").write_text(json.dumps({"tests": names}, indent=2) + "\n", encoding="utf-8")
        if book is not None:
            book.row("playwright", "unstable", f"{len(names)} test(s) passed before and failed only in the confirm pass; counted flaky"[:220])
    return after


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


PHASES = ".agents/skills/lexful-autonomous-agent-qa/phases"
# The file with the rules for each phase. The agent reads .agents/prompts/qa.md (shared rules) and this one file.
PHASE_FILES = {
    "explore+author": "explore-author.md",
    "heal": "heal.md",
    "e2e-heal": "e2e-heal.md",
    "affected-heal": "e2e-heal.md",
    "verify": "verify.md",
    "promote": "promote.md",
}


def _message(phase: str, folder: Path, *facts: str) -> str:
    """The text the server sends OpenCode. Facts only: the rules for each phase are in its phase file."""
    return "\n".join([
        f"Phase: {phase}",
        f"Run directory: {_display(folder)}",
        f"Rules: .agents/prompts/qa.md, then {PHASES}/{PHASE_FILES[phase]}.",
        *facts,
    ])


def _browser_name(folder: Path, kind: str = "qa") -> str:
    return f"{kind}-{runners._key(folder).split('_')[-1]}"


def _lead_prompt(folder: Path, ticket: str, preflight: dict[str, Any], run_id: str = "") -> str:
    prs = ", ".join(str(number) for number in (preflight.get("pullRequests") or [])) or "none"
    connected = ", ".join(preflight.get("connectedTickets") or []) or "none"
    return _message(
        "explore+author", folder,
        f"Ticket: {ticket}",
        f"Pull requests: {prs}",
        f"Connected Linear issues: {connected}",
        f"Import prefix for specs: {_import_prefix(_display(folder))}",
        f"Browser session name: {_browser_name(folder)}",
    )


def _deployment_line(folder: Path) -> str:
    """One line from the deployment check preflight wrote into the context pack."""
    deployment = _read_json(folder / "context-pack.json").get("deployment")
    if not isinstance(deployment, dict):
        return ""
    return str(deployment.get("summary") or "")


def write_history(folder: Path, ticket: str) -> int:
    """history.md: earlier runs of this ticket, their verdict, bugs and open issues. Returns how many.

    Runs come from the index, so a run of this ticket started from a PR or a deploy is listed
    wherever its folder is. Each heading is the run folder, for the UX audit's prior findings.
    """
    if not ticket:
        return 0
    rows = sorted(store.list_runs(ticket), key=lambda row: str(row.get("createdAt") or ""), reverse=True)
    folders = (store.run_dir(str(row["id"])) for row in rows if row.get("id"))
    earlier = [p for p in folders if p.is_dir() and p.resolve() != folder.resolve()][:5]
    lines = [f"# Earlier runs of {ticket}", "", "Newest first. Retest what failed or was filed before; do not trust an old pass.", ""]
    count = 0
    for run in earlier:
        result = _read_json(run / "qa-result.json")
        if not result:
            continue
        count += 1
        counts = result.get("test_results") or {}
        lines.append(f"## {_display(run)}")
        lines.append(f"- Verdict: {result.get('verdict')}  passed {counts.get('passed', 0)}  failed {counts.get('failed', 0)}")
        for issue in (result.get("open_issues") or [])[:5]:
            lines.append(f"- Open: {str(issue)[:200]}")
        for bug in (_read_json(run / "bugs.json").get("bugs") or [])[:6]:
            if isinstance(bug, dict):
                lines.append(f"- Bug filed: {str(bug.get('title') or '')[:160]}")
        triage, _cycle = latest_triage(run)
        for item in (triage.get("failures") or [])[:6]:
            if isinstance(item, dict):
                lines.append(f"- Heal: {failure_kind(item) or 'note'} / {item.get('action', '')}: {str(item.get('test') or item.get('title') or '')[:120]}")
        lines.append("")
    if not count:
        return 0
    (folder / "history.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return count


def _run_affected_cases(run_id: str, folder: Path, book: Logbook) -> list[str]:
    """Run the checked-in cases the agent said the diff touches. A failure is a possible regression."""
    data = _read_json(folder / "affected-cases.json")
    wanted = {str(case).strip() for case in data.get("cases") or [] if str(case).strip()}
    if not wanted:
        return []
    cases = [case for case in load_cases(get_settings().root / "e2e test cases") if case.id in wanted]
    if not cases:
        book.row("server", "affected", f"none of {', '.join(sorted(wanted))[:120]} is in the suite")
        return []
    _begin(run_id, book, "affected E2E cases")
    store.update_run(run_id, status="execute")
    root = get_settings().root / "e2e test cases"
    files = sorted({f"e2e test cases/{case.journey}/{case.file}" for case in cases if (root / case.journey / case.file).is_file()})
    grep = "|".join(re.escape(case.title) for case in cases)
    book.row("playwright", "affected", f"{len(cases)} checked-in case(s) in {len(files)} file(s): {', '.join(c.id for c in cases)}"[:220])
    result = runners.run_playwright(folder, files, out_dir=folder / "affected", grep=grep)
    _check_cancel(run_id)
    failing = failed_tests(_read_json(folder / "affected" / "playwright" / "results.json"))
    book.row("playwright", "affected", _counts(result["summary"]))
    notes: dict[str, str] = {}
    healed = 0
    if failing and get_settings().heal_attempts > 0:
        healed, failing, notes = _heal_affected_cases(run_id, folder, book, files, grep)
    write_test_outcomes_json(folder, test_outcomes_from_report(_read_json(folder / "affected" / "playwright" / "results.json")),
                             target=folder / "affected" / "test-outcomes.json")
    line = f"{len(cases)} run, {len(failing)} failed" + (f", {healed} fixed by heal" if healed else "")
    run_summary.get(run_id).note("affected", line)
    _end(run_id, "affected E2E cases", "ok" if not failing else "failed", line)
    by_title = {case.title: case.id for case in cases}
    return [
        f"affected E2E case still failing after heal: {by_title.get(item['title'], '')} {item['title']} — {item['error'][:120]}"
        f"{' | ' + notes[item['title']] if notes.get(item['title']) else ''}".strip()
        for item in failing
    ]


def _heal_affected_cases(
    run_id: str, folder: Path, book: Logbook, files: list[str], grep: str,
) -> tuple[int, list[dict[str, str]], dict[str, str]]:
    """A checked-in case that fails beside a ticket is outdated until shown otherwise, as in the E2E run.

    A fresh qa session may edit the suite in place (changes.log records it), then the cases run again.
    Returns (cases fixed, cases still failing, the healer's reason per case).
    """
    report = folder / "affected" / "playwright" / "results.json"
    first = failed_tests(_read_json(report))
    still = first
    notes: dict[str, str] = {}
    session = ""
    rounds = min(2, get_settings().heal_attempts)
    for attempt in range(1, rounds + 1):
        _begin(run_id, book, f"affected heal {attempt} of {rounds}")
        store.update_run(run_id, status="heal")
        listed = "\n".join(f"- {item['title']}  ({_short_file(item['file'])})  {item['error']}".rstrip() for item in still[:20])
        prompt = _message(
            "affected-heal", folder,
            "Suite: checked-in E2E cases that ran beside this ticket",
            f"Heal attempt {attempt} of {rounds}",
            f"Specs: {', '.join(files)}",
            f"Browser session name: {_browser_name(folder, 'heal')}",
            "Playwright report: affected/playwright/results.json",
            "Write triage to: affected/triage.json",
            "Failures:",
            listed,
        )
        (folder / f"affected-heal-{attempt}.md").write_text(prompt + "\n", encoding="utf-8")
        before_text = _suite_texts()
        before = _suite_revision()
        (folder / "affected" / "triage.json").unlink(missing_ok=True)
        code, session = runners.run_opencode(
            folder, session_id=session or None, prompt=prompt, title=f"checked-in affected heal {attempt}",
            log_name=f"affected-heal-{attempt}.jsonl", resume=bool(session),
        )
        _check_cancel(run_id)
        triage = _read_triage(folder / "affected" / "triage.json")
        for item in triage.get("failures") or []:
            if isinstance(item, dict):
                key = str(item.get("title") or item.get("test") or "")
                if key and item.get("reason"):
                    notes[key] = f"heal: {failure_kind(item) or 'note'}: {str(item['reason'])[:160]}"
        if code != 0:
            _end(run_id, None, "failed", _opencode_failure(folder, f"affected-heal-{attempt}.jsonl", code))
            break
        record_suite_edits(run_id, attempt, before_text, _suite_texts(), triage)
        changed = suite_files_changed(before, _suite_revision())
        if not changed:
            _end(run_id, None, "ok", "no spec file changed")
            break
        book.row("server", "heal", f"affected: patched {', '.join(changed)}"[:240])
        _begin(run_id, book, f"affected after heal {attempt}")
        result = runners.run_playwright(folder, files, out_dir=folder / "affected", grep=grep)
        _check_cancel(run_id)
        book.row("playwright", "affected", _counts(result["summary"]))
        still = failed_tests(_read_json(report))
        _end(run_id, None, "ok", _counts(result["summary"]))
        if not still:
            break
    return max(0, len(first) - len(still)), still, notes


def _verify_findings(
    run_id: str, folder: Path, ticket: str, book: Logbook, signals: dict[str, Any], *, label: str = "verify findings",
) -> dict[str, str]:
    """A fresh session reproduces every defect the run is about to file, and screenshots it.

    Items: each finding, each triage bug, and server errors the specs recorded. What it cannot
    reproduce is not filed. Returns {title: hint} for the tests whose "bug" was not reproduced, so
    the next heal fixes the spec or its data instead.
    """
    items: list[str] = []
    for item in _read_json(folder / "api-findings.json").get("findings") or []:
        if isinstance(item, dict) and item.get("id") and not item.get("status") == "skipped":
            items.append(f"finding:{item['id']} — {str(item.get('failure') or item.get('description') or '')[:160]}")
    triage, _cycle = latest_triage(folder)
    for index, bug in enumerate(triage.get("bugs") or [], start=1):
        if isinstance(bug, dict) and not bug.get("finding") and bug.get("status") != "skipped":
            items.append(f"bug:{index} — {str(bug.get('failure') or bug.get('description') or '')[:160]}")
    for index, sample in enumerate(s for s in signals.get("samples") or [] if int(s.get("status") or 0) >= 500 or s.get("kind") == "pageerror"):
        if index >= 5:
            break
        items.append(f"signal:{index + 1} — {sample.get('kind')} {sample.get('method', '')} {sample.get('status', '')} {sample.get('path') or str(sample.get('text') or '')[:120]} in {sample.get('test', '')}")
    if not items:
        return {}
    _begin(run_id, book, label)
    store.update_run(run_id, status="verify")
    prompt = _message(
        "verify", folder,
        f"Ticket: {ticket}",
        f"Browser session name: {_browser_name(folder, 'verify')}",
        "Items:",
        *[f"- {line}" for line in items[:12]],
    )
    log_name = f"verify-{len(list(folder.glob('opencode/verify-*.jsonl'))) + 1}.jsonl"
    (folder / "verify.json").unlink(missing_ok=True)
    suite_before = _suite_files() if ticket != "checked-in" else {}
    code, session = runners.run_opencode(folder, session_id=None, prompt=prompt, title=f"{ticket} verify",
                                          log_name=log_name)
    _check_cancel(run_id)
    if ticket != "checked-in":
        _guard_suite(suite_before, book, "verify")
    applied = apply_verification(folder)
    book.row("server", "verify", f"{len(items)} item(s) checked: {applied}" if code == 0 else _opencode_failure(folder, log_name, code))
    _end(run_id, label, "ok" if code == 0 else "failed", applied)
    return verifier_hints(folder)


def verifier_hints(folder: Path) -> dict[str, str]:
    """{test title: what the verifier saw} for bugs it could not reproduce."""
    hints: dict[str, str] = {}
    results = {str(r.get("ref")): r for r in _read_json(folder / "verify.json").get("results") or [] if isinstance(r, dict)}
    triage, _cycle = latest_triage(folder)
    for index, bug in enumerate(triage.get("bugs") or [], start=1):
        result = results.get(f"bug:{index}")
        if isinstance(bug, dict) and result and result.get("reproduced") is False:
            hint = str(result.get("specFix") or result.get("notes") or "not reproduced")[:300]
            for name in _affected_titles(bug):
                hints[name] = hint
    return hints


def _affected_titles(bug: dict[str, Any]) -> list[str]:
    raw = bug.get("affectedTests") or bug.get("affected_tests") or []
    if isinstance(raw, str):
        raw = [raw]
    return [str(item) for item in raw if isinstance(item, str) and item.strip()]


def _confirm(item: dict[str, Any], result: dict[str, Any]) -> None:
    """A reproduced defect is confirmed, and keeps the steps and persona the verifier actually used."""
    item["confidence"] = "confirmed"
    item["verifier"] = str(result.get("notes") or "reproduced")[:300]
    if isinstance(result.get("steps"), list) and result["steps"]:
        item["steps"] = [str(step) for step in result["steps"]]
    if result.get("persona"):
        item["persona"] = str(result["persona"])


def apply_verification(folder: Path) -> str:
    """Confirm what was reproduced. What was not reproduced is not filed: a finding is skipped, a triage
    bug is skipped and its failures become spec work, so the healer fixes the test or its data."""
    results = [r for r in _read_json(folder / "verify.json").get("results") or [] if isinstance(r, dict)]
    if not results:
        return "no verify.json"
    by_ref = {str(r.get("ref") or "").strip(): r for r in results}
    confirmed = dropped = 0
    findings_path = folder / "api-findings.json"
    data = _read_json(findings_path)
    for item in data.get("findings") or []:
        if not isinstance(item, dict):
            continue
        result = by_ref.get(f"finding:{item.get('id')}")
        if result is None:
            continue
        if result.get("reproduced") is True:
            _confirm(item, result)
            confirmed += 1
        elif result.get("reproduced") is False:
            item["status"] = "skipped"
            item["verifier"] = "not reproduced: " + str(result.get("notes") or "")[:300]
            dropped += 1
    if data:
        findings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    rounds = triage_files(folder)
    if rounds:
        triage = _read_json(rounds[-1])
        bugs = [b for b in triage.get("bugs") or [] if isinstance(b, dict)]
        kept = 0
        for index, bug in enumerate(triage.get("bugs") or [], start=1):
            result = by_ref.get(f"bug:{index}")
            if not isinstance(bug, dict) or result is None:
                kept += 1 if isinstance(bug, dict) and bug.get("status") != "skipped" else 0
                continue
            if result.get("reproduced") is True:
                _confirm(bug, result)
                confirmed += 1
                kept += 1
            else:
                bug["status"] = "skipped"
                bug["verifier"] = "not reproduced: " + str(result.get("notes") or "")[:300]
                dropped += 1
                names = {n.lower() for n in _affected_titles(bug)}
                for failure in triage.get("failures") or []:
                    title = str(failure.get("title") or failure.get("test") or "").lower() if isinstance(failure, dict) else ""
                    if title and failure_kind(failure) == "bug" and any(title in n or n in title for n in names):
                        failure["class"] = "spec"
                        failure["action"] = "reported"
                        failure["reason"] = "verifier could not reproduce a product defect: " + str(result.get("notes") or "")[:200]
        if bugs and kept == 0:
            # Every filed bug failed to reproduce: no failure keeps a "bug" label that would file it again.
            for failure in triage.get("failures") or []:
                if isinstance(failure, dict) and failure_kind(failure) == "bug":
                    failure["class"] = "spec"
                    failure["action"] = "reported"
                    failure["reason"] = "verifier could not reproduce a product defect"
        rounds[-1].write_text(json.dumps(triage, indent=2) + "\n", encoding="utf-8")
    return f"{confirmed} confirmed, {dropped} not reproduced"


def _note_findings(run_id: str, folder: Path) -> None:
    """Counts for the run summary."""
    notes = run_summary.get(run_id)
    filed = len(_read_json(folder / "bugs.json").get("bugs") or [])
    notes.note("bugs", f"{filed} in bugs.json" if filed else "none")
    findings = [f for f in _read_json(folder / "api-findings.json").get("findings") or [] if isinstance(f, dict)]
    if findings:
        confirmed = sum(1 for f in findings if str(f.get("confidence") or "").lower() == "confirmed")
        notes.note("findings", f"{len(findings)} ({confirmed} confirmed)")
    if (folder / "hypotheses.json").is_file():
        notes.note("hypotheses", checks.hypothesis_report(folder)[0])


def _promote_into_suite(run_id: str, folder: Path, ticket: str, book: Logbook) -> str:
    """Copy the passing journeys into the checked-in suite before the run is sealed.

    The suite is snapshotted first. A promotion that fails, or that adds a spec Playwright
    cannot load, is reverted so it never breaks the next E2E run. Every promotion is logged.
    """
    prompt = _promote_prompt(folder, ticket)
    (folder / "promote-prompt.md").write_text(prompt + "\n", encoding="utf-8")
    before = _suite_files()
    code, _session = runners.run_opencode(
        folder,
        session_id=None,
        prompt=prompt,
        title=f"{ticket} promote",
        log_name="promote.jsonl",
    )
    promoted = _read_json(folder / "promoted.json")
    cases = promoted.get("cases") if isinstance(promoted.get("cases"), list) else []
    after = _suite_files()
    reverted = ""
    if code != 0:
        reverted = _opencode_failure(folder, "promote.jsonl", code)
    else:
        touched = sorted(
            f"e2e test cases/{name}"
            for name in after
            if name.endswith(".spec.ts") and before.get(name) != after[name]
        )
        loadable, detail = runners.list_specs(touched)
        if not loadable:
            reverted = f"a promoted spec does not load: {detail}"
    if reverted:
        _restore_suite(before)
        record_promotion(run_id, ticket, before, before, {**promoted, "cases": []}, reverted=reverted)
        book.row("server", "promote", f"reverted  {reverted}"[:240])
        return f"reverted: {reverted}"[:200]
    record_promotion(run_id, ticket, before, after, promoted)
    if not cases:
        book.row("server", "promote", "no new journey copied")
        return "nothing promoted"
    book.row("server", "promote", f"{len(cases)} case(s) added to e2e test cases")
    return f"{len(cases)} case(s) added: " + ", ".join(str(c.get("id", "")) for c in cases if isinstance(c, dict))


def _promote_prompt(folder: Path, ticket: str) -> str:
    return _message("promote", folder, f"Ticket: {ticket}")


def _ux_audit_prompt(
    folder: Path,
    ticket: str,
    preflight: dict[str, Any],
    *,
    parallel: bool = False,
) -> str:
    relative = _display(folder)
    return "\n".join([
        "Phase: ux-audit",
        f"Run directory: {relative}",
        f"Ticket: {ticket}",
        f"App URL: {preflight.get('appUrl') or 'the appUrl in the context pack'}",
        "Rules: .agents/prompts/qa.md, then .agents/prompts/ux-auditor.md.",
        f"Browser session name: {_browser_name(folder, 'ux')}",
        *(["Playwright and heal run beside you: do not read playwright/ or triage.json."] if parallel else []),
    ])


def _heal_prompt(
    folder: Path,
    ticket: str,
    attempt: int,
    total: int,
    specs: list[str],
    failing: list[dict[str, str]] | None = None,
    attempts_used: dict[str, int] | None = None,
) -> str:
    counts = attempts_used or {}
    failing_lines = [
        f"- {item['title']}  (attempt {counts.get(item['title'], attempt)} of {total})"
        for item in (failing or [])
    ] or ["- the Playwright report has failures, but no test title was parsed"]
    return _message(
        "heal", folder,
        f"Ticket: {ticket}",
        f"Heal attempt {attempt} of {total}",
        f"Specs: {', '.join(specs)}",
        f"Browser session name: {_browser_name(folder, 'heal')}",
        "Still failing:",
        *failing_lines,
    )


def _phase1_heal_prompt(
    folder: Path, attempt: int, total: int, specs: list[str], hints: dict[str, str] | None = None,
) -> str:
    decisions = suite_decisions()
    every = failed_tests(_read_json(folder / "playwright" / "results.json"))
    failures = [f for f in every if not decision_for(f["title"], decisions)]
    waiting = [f"- {f['title']}" for f in every if decision_for(f["title"], decisions)]
    listed = "\n".join(
        f"- {item['title']}  ({_short_file(item['file'])})  {item['error']}".rstrip()
        for item in failures[:40]
    ) or "- the Playwright report has failures, but no test title was parsed"
    seen = [f"- {name}: {hint}" for name, hint in (hints or {}).items()]
    if waiting:
        seen_note = ["These wait for a person's decision (decisions.json). Do not heal them and do not file them:", *waiting]
    else:
        seen_note = []
    return _message(
        "e2e-heal", folder,
        "Suite: E2E User Journey TCs (not a ticket)",
        f"Heal attempt {attempt} of {total}",
        f"Specs: {', '.join(specs)}",
        f"Browser session name: {_browser_name(folder, 'heal')}",
        "Failures:",
        listed,
        *(["The verifier could not reproduce a product defect for these. The test or its data is outdated; fix it:", *seen] if seen else []),
        *seen_note,
    )


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
    bugs = sum(1 for item in failures if isinstance(item, dict) and failure_kind(item) == "bug")
    specs = sum(1 for item in failures if isinstance(item, dict) and failure_kind(item) == "spec")
    gaps = sum(1 for item in failures if isinstance(item, dict) and failure_kind(item) == "gap")
    parts = ["no spec file changed"]
    if bugs:
        parts.append(f"{bugs} product bug(s) logged in this folder")
    if gaps:
        parts.append(f"{gaps} gap(s) were not removed from the spec, so the suite is not re-run")
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


def _heal_revision(folder: Path, classify: bool) -> tuple[tuple[str, int], ...]:
    """E2E heals edit the checked-in suite. A ticket heal edits that run's specs/ folder."""
    if classify:
        return _suite_revision()
    root = folder / "specs"
    if not root.is_dir():
        return ()
    files = sorted(
        path for path in root.rglob("*") if path.is_file() and path.suffix in {".ts", ".js"}
    )
    return tuple((path.relative_to(root).as_posix(), path.stat().st_mtime_ns) for path in files)


def _suite_texts() -> dict[str, str]:
    root = _suite_root()
    return {path.relative_to(root).as_posix(): path.read_text(encoding="utf-8") for path in _suite_sources()}


def _suite_files(root: Path | None = None) -> dict[str, str]:
    """Every spec, page object, and FEATURE.md in the checked-in suite, by path."""
    base = root or _suite_root()
    if not base.is_dir():
        return {}
    return {
        path.relative_to(base).as_posix(): path.read_text(encoding="utf-8")
        for path in sorted(base.rglob("*"))
        if path.is_file() and path.suffix in {".ts", ".js", ".md"}
    }


def _restore_suite(before: dict[str, str], root: Path | None = None) -> None:
    """Put the suite back exactly as `before`: drop files a failed promotion added, rewrite files it changed."""
    base = root or _suite_root()
    for name, text in _suite_files(base).items():
        if name not in before:
            (base / name).unlink()
        elif before[name] != text:
            (base / name).write_text(before[name], encoding="utf-8")
    for name, text in before.items():
        if not (base / name).exists():
            (base / name).parent.mkdir(parents=True, exist_ok=True)
            (base / name).write_text(text, encoding="utf-8")


def record_promotion(
    run_id: str,
    ticket: str,
    before: dict[str, str],
    after: dict[str, str],
    promoted: dict[str, Any],
    *,
    reverted: str = "",
    log_path: Path | None = None,
) -> None:
    """Append what a ticket run added to the suite, so changes.log shows every change and not only heals."""
    added = sorted(name for name in after if name not in before)
    changed = sorted(name for name in after if name in before and after[name] != before[name])
    cases = [c for c in promoted.get("cases") or [] if isinstance(c, dict)]
    skipped = [c for c in promoted.get("skipped") or [] if isinstance(c, dict)]
    if not (added or changed or cases or skipped or reverted):
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [f"{stamp}  {run_id}  promote from {ticket}"]
    if added:
        lines.append("  added: " + ", ".join(f"e2e test cases/{name}" for name in added))
    if changed:
        lines.append("  changed: " + ", ".join(f"e2e test cases/{name}" for name in changed))
    lines.extend(f"  - added / {c.get('id', '')}: {c.get('title', '')}".rstrip() for c in cases)
    lines.extend(f"  - skipped: {c.get('title', '')} — {c.get('reason', '')}".rstrip(" —") for c in skipped)
    if reverted:
        lines.append(f"  - reverted, the suite is unchanged: {reverted}")
    target = log_path or (_suite_root() / "changes.log")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n\n")
    _trim_changes_log(target)


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
    _trim_changes_log(target)


CHANGES_LOG_KEEP = 40_000
_ENTRY_START = re.compile(r"\n\n(?=\d{4}-\d\d-\d\dT)")


def _trim_changes_log(path: Path, keep: int = CHANGES_LOG_KEEP) -> None:
    """Keep the two header lines and the newest entries within `keep` characters.

    A heal reads this file at the start of every session, so a log that only grows costs every run. Older
    entries are in git history.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    if len(text) <= keep:
        return
    head, _, rest = text.partition("\n\n")
    entries = _ENTRY_START.split("\n\n" + rest) if rest else []
    kept: list[str] = []
    size = len(head)
    for entry in reversed(entries):
        entry = entry.strip("\n")
        if not entry:
            continue
        if size + len(entry) > keep and kept:
            break
        kept.append(entry)
        size += len(entry) + 2
    path.write_text(head + "\n\n" + "\n\n".join(reversed(kept)) + "\n\n", encoding="utf-8")


def _triage_notes(triage: dict[str, Any]) -> list[str]:
    """One line per kind of failure. Tests that share a reason are listed together, not repeated."""
    failures = triage.get("failures")
    if not isinstance(failures, list):
        return []
    groups: dict[tuple[str, str, str], list[str]] = {}
    for item in failures:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("test") or "failure")
        kind = failure_kind(item) or "note"
        reason = " ".join(str(item.get("reason") or "").split())
        if len(reason) > 240:
            reason = reason[:240] + "..."
        groups.setdefault((kind, str(item.get("action") or ""), reason), []).append(title)
    notes: list[str] = []
    for (kind, action, reason), titles in groups.items():
        head = f"{kind} / {action}" if action else kind
        shown = "; ".join(titles[:3]) + (f"; +{len(titles) - 3} more" if len(titles) > 3 else "")
        label = f"{head} ({len(titles)} tests): {shown}" if len(titles) > 1 else f"{head}: {shown}"
        notes.append(f"{label} — {reason}" if reason else label)
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
        if failure_kind(data):
            return {"failures": [data]}
        return data
    return {}


def _failure_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("test") or "unnamed")


def _failure_reason(item: dict[str, Any]) -> str:
    return str(item.get("reason") or item.get("evidence") or "").strip()


def _take_triage(folder: Path, attempt: int) -> dict[str, Any]:
    """Read triage.json and keep a copy at triage-<attempt>.json for the bug record."""
    path = folder / "triage.json"
    data = _read_triage(path)
    if path.is_file():
        (folder / f"triage-{attempt}.json").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return data


def _record_bugs(folder: Path, row: dict[str, Any], summary: dict[str, int], *, context: Path | None = None) -> bool:
    """File the healer's bugs and the run's findings into bugs.json and bugs.md.

    A ticket's bugs say `found by` that ticket; the checked-in suite's bugs say E2E User Journey TCs.
    """
    triage, _round = latest_triage(folder)
    pack = _read_json((context or folder) / "context-pack.json")
    url = str(pack.get("appUrl") or get_settings().qa_url)
    deployment = pack.get("deployment") if isinstance(pack.get("deployment"), dict) else {}
    build = str(row.get("sha") or deployment.get("build") or "unknown")
    found_by = str(row.get("ticket") or "E2E User Journey TCs")
    filed = publish_bugs(
        folder,
        ticket=found_by,
        run_id=str(row.get("id") or folder.name),
        url=url,
        build=build,
        failed=int(summary.get("failed") or 0),
        triage=triage,
    )
    probed = publish_findings(folder, ticket=found_by, run_id=str(row.get("id") or folder.name), url=url, build=build)
    return filed or probed > 0


def suite_decisions() -> list[dict[str, str]]:
    """`e2e test cases/decisions.json`: checked-in cases that wait for a person's decision.

    `{"decisions": [{"test": "TC-DOC-010", "note": "the product now defaults the name", "since": "2026-11-06"}]}`
    A listed case that fails is not healed, not filed as a bug and does not fail the E2E verdict. It is
    reported as waiting for a decision until a person updates the test or the product and removes it.
    """
    items = _read_json(_suite_root() / "decisions.json").get("decisions")
    if not isinstance(items, list):
        return []
    return [
        {"test": str(d["test"]).strip(), "note": str(d.get("note") or "").strip()}
        for d in items if isinstance(d, dict) and str(d.get("test") or "").strip()
    ]


def decision_for(title: str, decisions: list[dict[str, str]]) -> dict[str, str] | None:
    """The decision that names this test by id (`TC-DOC-010`) or by its full title."""
    lowered = title.lower()
    for decision in decisions:
        key = decision["test"].lower()
        if key == lowered or lowered.startswith(key + ":") or f"› {key}" in lowered or f"{key}:" in lowered:
            return decision
    return None


def decided_failures(outcomes: dict[str, dict[str, dict[str, Any]]], decisions: list[dict[str, str]]) -> list[str]:
    """Failing tests that wait for a decision, as `<test>: <note>`."""
    found: list[str] = []
    for tests in outcomes.values():
        for name, row in tests.items():
            if row.get("status") == "failed":
                decision = decision_for(name, decisions)
                if decision:
                    found.append(f"{decision['test']}: {decision['note'] or 'waiting for a decision'}")
    return found


def _drop_decided_bugs(folder: Path, decisions: list[dict[str, str]]) -> int:
    """Remove bugs whose every affected test waits for a decision; render bugs.md again."""
    if not decisions:
        return 0
    data = _read_json(folder / "bugs.json")
    records = [b for b in data.get("bugs") or [] if isinstance(b, dict)]
    def decided(bug: dict[str, Any]) -> bool:
        tests = [str(t) for t in bug.get("affectedTests") or []]
        return bool(tests) and all(decision_for(t, decisions) for t in tests)
    kept = [b for b in records if not decided(b)]
    if len(kept) == len(records):
        return 0
    from app.bugs import render_bugs

    (folder / "bugs.json").write_text(json.dumps({"bugs": kept}, indent=2) + "\n", encoding="utf-8")
    (folder / "bugs.md").write_text(render_bugs(kept), encoding="utf-8")
    return len(records) - len(kept)


def unstable_notes(folder: Path) -> list[str]:
    """Tests that passed earlier in this run and failed only in the confirm pass (see `_confirm_after_heals`)."""
    data = _read_json(folder / "playwright" / "unstable.json")
    names = data.get("tests") if isinstance(data.get("tests"), list) else []
    return [f"unstable: {name} passed earlier in this run and failed in the confirm pass" for name in names]


def reported_but_passed(folder: Path) -> list[str]:
    """The healer left a test for a person to decide, and a later rerun passed it anyway.

    That pass is not evidence the question was answered: the test may pass by timing. It stays a
    sign-off item until a person looks at it.
    """
    triage, _round = latest_triage(folder)
    passing = _passing_title_list(folder)
    lines: list[str] = []
    for item in triage.get("failures") or []:
        if not isinstance(item, dict) or str(item.get("action") or "").lower() != "reported":
            continue
        name = str(item.get("test") or item.get("title") or "")
        if name and any(same_test(name, title.split(" › ")[-1]) or same_test(name, title) for title in passing):
            lines.append(f"{name} passed after the healer left it for a person to decide: {_failure_reason(item)[:160]}")
    return lines


def e2e_stage_blockers(folder: Path) -> list[str]:
    """A ticket run's E2E User Journey stage that did not pass blocks the ticket's sign-off.

    The deploy is what is tested: a ticket can be right while the build broke search.
    """
    result = _read_json(folder / "e2e" / "qa-result.json")
    verdict = str(result.get("verdict") or "")
    if not verdict or verdict == "PERFECT":
        return []
    counts = result.get("test_results") if isinstance(result.get("test_results"), dict) else {}
    line = f"E2E User Journey TCs {verdict}: {_counts(counts)}" if counts else f"E2E User Journey TCs {verdict}"
    first = next((str(i) for i in result.get("open_issues") or [] if str(i).strip()), "")
    return [f"{line}. {first}"[:300] if first else line]


def filed_bug_blockers(folder: Path) -> list[str]:
    """A product bug filed by this run blocks sign-off, even when every test passed."""
    bugs = [b for b in _read_json(folder / "bugs.json").get("bugs") or [] if isinstance(b, dict)]
    if not bugs:
        return []
    titles = "; ".join(str(b.get("title") or "")[:90] for b in bugs[:3])
    return [f"{len(bugs)} product bug(s) filed: {titles}"]


def _healer_hid_a_bug(folder: Path) -> list[str]:
    lines: list[str] = []
    for path in triage_files(folder):
        lines.extend(suspicious_patches(_read_triage(path)))
    return lines


def patched_but_failing(folder: Path) -> list[str]:
    """Cases the last heal called patched that the final Playwright report still fails: the patch did not work."""
    failing = {item["title"] for item in failed_tests(_read_json(folder / "playwright" / "results.json"))}
    triages = triage_files(folder)
    last = _read_triage(triages[-1]) if triages else {}
    out: list[str] = []
    for item in last.get("failures") or []:
        if not isinstance(item, dict) or str(item.get("action") or "").lower() != "patched":
            continue
        title = str(item.get("title") or item.get("test") or "")
        if title in failing and title not in out:
            out.append(title)
    return [f"healer patched this case but it still fails, so the patch did not work: {title}" for title in out]


def _phase1_issues(folder: Path, summary: dict[str, int]) -> list[str]:
    issues = _healer_hid_a_bug(folder) + patched_but_failing(folder)
    if (
        summary.get("failed", 0) == 0
        and summary.get("skipped", 0) == 0
        and summary.get("passed", 0) > 0
    ):
        return issues
    triages = triage_files(folder)
    last = _read_triage(triages[-1]) if triages else {}
    lines: list[str] = []
    failures = last.get("failures")
    if isinstance(failures, list):
        for item in failures:
            if not isinstance(item, dict):
                continue
            kind = failure_kind(item)
            if kind not in {"bug", "timing"}:
                continue
            reason = _failure_reason(item)
            text = f"{kind}: {_failure_title(item)}"
            if reason:
                text += f" — {reason}"
            lines.append(text)
    if not lines:
        lines.append(_open_issue(summary))
    return issues + lines


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
        "models": {"main": settings.main_model},
        "open_issues": issues or drafted.get("open_issues") or [],
    }
    ux_card = _read_json(folder / "ux-scorecard.json")
    if ux_card:
        payload["ux"] = {
            "verdict": ux_card.get("verdict"),
            "score": ux_card.get("score"),
            "findings_count": len(_read_findings(folder / "ux-findings.json")),
            "report_file": "ux-report.html" if (folder / "ux-report.html").is_file() else None,
        }
    if extra:
        payload.update(extra)
    if (folder / "bugs.md").is_file():
        payload["bugs_file"] = "bugs.md"
    (folder / "qa-result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _read_findings(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("failures"), list):
        return data["failures"]
    if isinstance(data, dict) and isinstance(data.get("findings"), list):
        return data["findings"]
    return []


_PHASE_OF_LOG = (
    ("agent", "Explore + Author"),
    ("verify", "Verify"),
    ("heal", "Heal"),
    ("ux-audit", "UX audit"),
    ("promote", "Promote"),
)


def phase_costs(folder: Path) -> dict[str, dict[str, float]]:
    """Per phase steps, output tokens, cache-read tokens, and cost, from the OpenCode logs of this run.

    A ticket run's E2E stage keeps its logs in e2e/opencode; they are counted as "E2E <phase>".
    """
    phases: dict[str, dict[str, float]] = {}
    logs = [("", log) for log in sorted((folder / "opencode").glob("*.jsonl"))]
    if folder.name != "e2e":
        logs += [("E2E ", log) for log in sorted((folder / "e2e" / "opencode").glob("*.jsonl"))]
    for stage, log in logs:
        label = stage + next((name for prefix, name in _PHASE_OF_LOG if log.stem.startswith(prefix)), log.stem)
        row = phases.setdefault(label, {"steps": 0, "output": 0, "cacheRead": 0, "cost": 0.0})
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                part = json.loads(line).get("part") or {}
            except ValueError:
                continue
            if part.get("type") != "step-finish":
                continue
            tokens = part.get("tokens") or {}
            row["steps"] += 1
            row["output"] += tokens.get("output") or 0
            row["cacheRead"] += (tokens.get("cache") or {}).get("read") or 0
            row["cost"] += part.get("cost") or 0
    return phases
