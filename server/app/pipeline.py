"""Ticket run: preflight, coordinator, Playwright, then at most three heals."""

from __future__ import annotations

import difflib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import runners, store
from app.bugs import failure_kind, latest_triage, publish_bugs
from app.coverage import write_coverage_index
from app.logbook import Logbook, echo_run, plain
from app.settings import get_settings
from app.ux_report import write_ux_report

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


_GAP_SKIP = ("out of scope", "not changed", "existing draft", "existing behavior")
_STOP_WORDS = frozenset(
    "a an the and or of to for in on at by with from into over under than then this that those "
    "these it its is are was were be been being as if not no nor but so such per via when while "
    "before after until about your our their they them we you do does did has have had can may "
    "will just also only same each both any all some".split()
)


def signoff_blockers(folder: Path) -> list[str]:
    """Ticket requirements still open after a green Playwright run."""
    feature = _read_text(folder / "FEATURE.md")
    required = _required_text(folder)
    required_words = _content_words(required)
    passed = _content_words(_passing_titles(folder))
    issues: list[str] = []
    for criterion in _acceptance_lines(folder):
        words = _content_words(criterion)
        if not words:
            continue
        needed = 1 if len(words) < 3 else 2
        if len(words & passed) < needed:
            issues.append(f"acceptance criterion not covered by a passing test: {criterion}")
    for gap in _feature_gaps(feature):
        lowered = gap.lower()
        if any(phrase in lowered for phrase in _GAP_SKIP):
            continue
        overlap = _content_words(gap) & required_words
        if len(overlap) >= 2 or any(len(word) >= 8 for word in overlap):
            issues.append(f"gap: {gap}")
    for note in _leftover_notes(folder):
        issues.append(f"leftover fixtures: {note}")
    return issues


def heal_stopped_on_bugs(triage: dict[str, Any]) -> bool:
    """True when every remaining failure is a product bug, so another heal will not change the spec."""
    failures = triage.get("failures")
    if not isinstance(failures, list) or not failures:
        return False
    kinds = [failure_kind(item) for item in failures if isinstance(item, dict)]
    return bool(kinds) and all(kind == "bug" for kind in kinds)


def _content_words(text: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z0-9][a-z0-9-]{4,}", text.lower())
        if word not in _STOP_WORDS
    }


def _feature_gaps(text: str) -> list[str]:
    lines = text.splitlines()
    start = next((index + 1 for index, line in enumerate(lines) if line.strip().lower() == "## gaps"), None)
    if start is None:
        return []
    items: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("these are"):
            continue
        cleaned = re.sub(r"^(\d+\.|[-*])\s*", "", stripped)
        cleaned = cleaned.replace("**", "").strip()
        if cleaned:
            items.append(cleaned)
    return items


def _acceptance_lines(folder: Path) -> list[str]:
    pack = _read_json(folder / "context-pack.json")
    ticket = pack.get("ticket") if isinstance(pack.get("ticket"), dict) else {}
    text = str(ticket.get("acceptanceCriteria") or "")
    rows: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("*", "-", "•")) or re.match(r"\d+\.", stripped):
            rows.append(re.sub(r"^(\d+\.|[-*•])\s*", "", stripped))
    if not rows and text.strip():
        rows.append(text.strip())
    return rows


def _required_text(folder: Path) -> str:
    pack = _read_json(folder / "context-pack.json")
    ticket = pack.get("ticket") if isinstance(pack.get("ticket"), dict) else {}
    parts = [
        str(ticket.get("summary") or ""),
        str(ticket.get("description") or ""),
        str(ticket.get("acceptanceCriteria") or ""),
    ]
    pull_requests = pack.get("pullRequests")
    if isinstance(pull_requests, list):
        for pull_request in pull_requests:
            if isinstance(pull_request, dict):
                parts.append(str(pull_request.get("title") or ""))
                parts.append(str(pull_request.get("body") or ""))
    return "\n".join(parts)


def _passing_titles(folder: Path) -> str:
    report = _read_json(folder / "playwright" / "results.json")
    titles: list[str] = []

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for spec in node.get("specs") or []:
            if isinstance(spec, dict) and spec.get("ok") is True:
                titles.append(str(spec.get("title") or ""))
        for child in node.get("suites") or []:
            walk(child)

    for suite in report.get("suites") or []:
        walk(suite)
    return " ".join(titles)


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


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


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


def test_outcomes_from_report(report: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Spec file basename -> test title -> passed|failed|flaky|skipped."""

    def status_for(test: dict[str, Any]) -> str:
        raw = test.get("status")
        if raw == "expected":
            return "passed"
        if raw == "flaky":
            return "flaky"
        if raw == "skipped":
            return "skipped"
        return "failed"

    found: dict[str, dict[str, str]] = {}

    def walk(node: Any, current: str) -> None:
        if not isinstance(node, dict):
            return
        current = str(node.get("file") or current)
        for spec in node.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            file_key = _spec_name(str(spec.get("file") or current))
            title = str(spec.get("title") or "").strip() or "unnamed"
            tests = [item for item in (spec.get("tests") or []) if isinstance(item, dict)]
            bucket = found.setdefault(file_key, {})
            if tests:
                for test in tests:
                    bucket[title] = status_for(test)
            elif spec.get("ok") is False:
                bucket[title] = "failed"
        for child in node.get("suites") or []:
            walk(child, current)

    for suite in report.get("suites") or []:
        walk(suite, "")
    return found


def merge_test_outcomes(
    before: dict[str, dict[str, str]],
    report: dict[str, Any],
    rerun_specs: list[str],
) -> dict[str, dict[str, str]]:
    after = test_outcomes_from_report(report)
    merged = {name: dict(titles) for name, titles in before.items()}
    replaced = {_spec_name(spec) for spec in rerun_specs}
    for file_key, titles in after.items():
        if file_key in replaced or file_key not in merged:
            merged[file_key] = dict(titles)
        else:
            merged[file_key].update(titles)
    return merged


def write_test_outcomes_json(folder: Path, outcomes: dict[str, dict[str, str]]) -> None:
    rows = [
        {"file": file_key, "title": title, "status": status}
        for file_key in sorted(outcomes)
        for title, status in sorted(outcomes[file_key].items())
    ]
    target = folder / "playwright" / "test-outcomes.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")


def _spec_name(file: str) -> str:
    return Path(file).name


def outcomes_by_file(report: dict[str, Any]) -> dict[str, dict[str, int]]:
    """Pass and fail counts keyed by spec file name. A heal re-run replaces one file's counts."""
    found: dict[str, dict[str, int]] = {}

    def add(file: str, counts: dict[str, int]) -> None:
        key = _spec_name(file)
        if not key:
            return
        bucket = found.setdefault(key, {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0})
        for name in bucket:
            bucket[name] += counts[name]

    def count_spec(spec: dict[str, Any]) -> dict[str, int]:
        counts = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        tests = [item for item in (spec.get("tests") or []) if isinstance(item, dict)]
        if not tests:
            if spec.get("ok") is False:
                counts["failed"] += 1
            return counts
        for test in tests:
            status = test.get("status")
            if status == "expected":
                counts["passed"] += 1
            elif status == "flaky":
                counts["flaky"] += 1
            elif status == "skipped":
                counts["skipped"] += 1
            elif status in {"unexpected", "failed"}:
                counts["failed"] += 1
        return counts

    def walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        for spec in node.get("specs") or []:
            if isinstance(spec, dict):
                add(str(spec.get("file") or node.get("file") or ""), count_spec(spec))
        for child in node.get("suites") or []:
            walk(child)

    for suite in report.get("suites") or []:
        walk(suite)
    return found


def specs_for_failures(specs: list[str], report: dict[str, Any]) -> list[str]:
    """Spec files that still have a hard failure. A flaky pass stays out of the re-run."""
    failed_names = {_spec_name(item["file"]) for item in failed_tests(report) if item.get("file")}
    return [spec for spec in specs if _spec_name(spec) in failed_names]


def replace_outcomes(
    before: dict[str, dict[str, int]],
    after: dict[str, dict[str, int]],
    rerun_specs: list[str],
) -> dict[str, dict[str, int]]:
    """Keep files that were not re-run. A later heal must start from this map, not from the partial report."""
    merged = {name: dict(counts) for name, counts in before.items()}
    replaced = {_spec_name(spec) for spec in rerun_specs}
    for name, counts in after.items():
        if name in replaced or name not in merged:
            merged[name] = dict(counts)
    return merged


def sum_outcomes(files: dict[str, dict[str, int]]) -> dict[str, int]:
    totals = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
    for counts in files.values():
        for key in totals:
            totals[key] += int(counts.get(key) or 0)
    return totals


def merge_outcomes(
    before: dict[str, dict[str, int]],
    after: dict[str, dict[str, int]],
    rerun_specs: list[str],
) -> dict[str, int]:
    """Keep counts for files that were not re-run. Replace the files the healer just ran."""
    return sum_outcomes(replace_outcomes(before, after, rerun_specs))


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
            store.attach_e2e_log(folder)
            if (folder / "e2e" / "run.log").is_file():
                book.row("server", "e2e", "E2E User Journey log saved in e2e/run.log")
            _execute(run_id, row, folder, book)
    except Exception as exc:
        book.row("server", "failed", str(exc)[:220])
        log.exception("run failed")
        store.update_run(run_id, status="failed", error=str(exc)[:500])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[str(exc)[:500]])
        _seal(run_id, None, "HALTED")
    finally:
        if row.get("kind") == "phase1":
            try:
                store.share_e2e_log(run_id)
            except Exception:
                log.exception("e2e log was not copied into the ticket folder")


def _execute(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    settings = get_settings()
    echo_run(folder)
    book.phase(f"Feature Specific TCs  {row.get('ticket') or run_id}")
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
    covered = write_coverage_index(settings.root / "e2e test cases", folder / "e2e-coverage.md")
    book.row("server", "coverage", f"{covered} checked-in cases")
    prompt = _lead_prompt(folder, ticket, preflight)
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
    issues = [] if verdict == "PERFECT" else [_open_issue(summary)]

    if settings.run_ux_audit and ticket:
        book.phase("ui-ux audit")
        ux_prompt = _ux_audit_prompt(folder, ticket, preflight)
        (folder / "ux-prompt.md").write_text(ux_prompt + "\n", encoding="utf-8")
        ux_code, ux_session_id = runners.run_opencode(
            folder,
            session_id=session_id or None,
            prompt=ux_prompt,
            title=f"{ticket} ux-audit",
            log_name="ux-audit.jsonl",
            resume=bool(session_id),
            agent="ux-auditor",
        )
        if ux_session_id:
            store.update_run(run_id, opencodeSession=ux_session_id)
            runners.export_session(folder, ux_session_id)
        write_ux_report(folder, ticket)
        ux_card = _read_json(folder / "ux-scorecard.json")
        ux_findings = _read_findings(folder / "ux-findings.json")
        ux_verdict = str(ux_card.get("verdict") or ("PASS" if ux_code == 0 else "INCOMPLETE — NOT A PASS"))
        book.row(
            "server",
            "ux-audit",
            f"verdict {ux_verdict}  score {ux_card.get('score', 100)}  {len(ux_findings)} finding(s)",
        )
    elif ticket:
        book.row("server", "ux-audit", "off  QA_RUN_UX_AUDIT=false  functional QA only")

    blockers = signoff_blockers(folder) if ticket else []
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
        _promote_into_suite(folder, ticket, book)

    store.update_run(run_id, status=status, error=None)
    if _record_bugs(folder, store.get_run(run_id) or row, summary):
        book.row("server", "bugs", "bugs.md")
    _write_qa_result(folder, ticket, verdict, summary, issues, specs)
    _write_report(folder, store.get_run(run_id) or row, verdict=verdict, summary=summary, issues=issues)
    _seal(run_id, summary, verdict)


def _execute_phase1(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    """Run E2E User Journey TCs against UAT. Heal locators. Keep bugs in this folder."""
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
    if _record_bugs(folder, store.get_run(run_id) or row, summary):
        book.row("server", "bugs", "bugs.md")
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
    return {"name": "E2E User Journey TCs", "linear": False, "suite": "e2e test cases"}


def _phase1_report_lines() -> list[str]:
    return [
        "E2E User Journey TCs ran the checked-in Playwright specs in `e2e test cases` against UAT.",
        "Logged in this folder and on the harness terminal. Not sent to Linear.",
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
    test_outcomes = test_outcomes_from_report(_read_json(folder / "playwright" / "results.json"))
    if result.get("setupError"):
        book.row("playwright", "error", str(result["setupError"]))
        write_test_outcomes_json(folder, test_outcomes)
        return summary
    if _suite_passed(result["exitCode"], summary):
        write_test_outcomes_json(folder, test_outcomes)
        return summary
    baseline = outcomes_by_file(_read_json(folder / "playwright" / "results.json"))
    attempts_used: dict[str, int] = {}
    for attempt in range(1, heal_attempts + 1):
        store.update_run(run_id, status="heal", healAttempts=attempt)
        book.phase(f"heal {attempt} of {heal_attempts}")
        who = "qa E2E heal" if classify else "qa feature heal"
        book.row("server", "heal", f"{attempt} of {heal_attempts}  {who}  {len(specs)} files")
        failing_now = failed_tests(_read_json(folder / "playwright" / "results.json"))
        for item in failing_now:
            attempts_used[item["title"]] = attempts_used.get(item["title"], 0) + 1
        prompt = (
            _phase1_heal_prompt(folder, attempt, heal_attempts, specs)
            if classify
            else _heal_prompt(folder, ticket, attempt, heal_attempts, specs, failing_now, attempts_used)
        )
        (folder / f"heal-{attempt}.md").write_text(prompt + "\n", encoding="utf-8")
        before = _heal_revision(folder, classify)
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
        triage = _take_triage(folder, attempt)
        if classify and heal_code == 0:
            record_suite_edits(run_id, attempt, before_text, _suite_texts(), triage)
        if heal_code != 0:
            book.row("qa", "failed", _opencode_failure(folder, f"heal-{attempt}.jsonl", heal_code))
            continue
        changed = suite_files_changed(before, _heal_revision(folder, classify))
        for line in suspicious_patches(triage):
            book.row("server", "heal", line[:220])
        if not changed:
            book.row("server", "heal", _unchanged_heal_message(triage))
            if heal_stopped_on_bugs(triage):
                break
            continue
        book.row("server", "heal", f"patched {', '.join(changed)}"[:240])
        previous_report = _read_json(folder / "playwright" / "results.json")
        rerun = specs_for_failures(specs, previous_report) or specs
        if not baseline:
            baseline = outcomes_by_file(previous_report)
        store.update_run(run_id, status="execute")
        book.phase("playwright")
        book.row("playwright", "started", f"re-running {len(rerun)} failed file(s) after heal {attempt}"[:240])
        result = runners.run_playwright(folder, rerun)
        latest_report = _read_json(folder / "playwright" / "results.json")
        if rerun != specs and baseline:
            baseline = replace_outcomes(
                baseline,
                outcomes_by_file(latest_report),
                rerun,
            )
            test_outcomes = merge_test_outcomes(test_outcomes, latest_report, rerun)
            summary = sum_outcomes(baseline)
        else:
            summary = result["summary"]
            baseline = outcomes_by_file(latest_report)
            test_outcomes = test_outcomes_from_report(latest_report)
        book.row("playwright", "result", _counts(summary))
        if _suite_passed(result["exitCode"], summary):
            write_test_outcomes_json(folder, test_outcomes)
            return summary
    write_test_outcomes_json(folder, test_outcomes)
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


def _lead_prompt(folder: Path, ticket: str, preflight: dict[str, Any]) -> str:
    relative = _display(folder)
    connected = ", ".join(preflight.get("connectedTickets") or []) or "none"
    prs = ", ".join(str(number) for number in (preflight.get("pullRequests") or [])) or "none"
    return "\n".join([
        f"Run directory: {relative}",
        f"Ticket: {ticket}",
        f"Pull requests: {prs}",
        f"Connected Linear issues: {connected}",
        "Follow .agents/skills/lexful-autonomous-agent-qa/SKILL.md and .agents/prompts/qa.md. This is Feature Specific TCs. You own this session: Explore, Author, Heal, and Promote when asked. Do not spawn subagents.",
        f"Checked-in coverage: {relative}/e2e-coverage.md",
        "Those cases already run in E2E User Journey TCs for search, asset crud, and document editing.",
        "Do not write a case that file already lists. Cite its id.",
        "Write a new case for each acceptance criterion and each observed behavior that the coverage file does not already assert.",
        "There is no minimum and no maximum. The number of tests is the uncovered behavior of this ticket.",
        "Each new test has one type tag (@positive, @negative, or @edge) and one suite tag (@bvt, @smoke, @sanity, or @regression).",
        "A test that passes by skipping the assertion does not count. Do not write a skipped or deprecated test.",
        f"Preflight is already ok: {relative}/preflight.json",
        f"Context pack: {relative}/context-pack.json",
        "Auth cookies: runs/cache/stytch/session.json for the default persona, admin.",
        "When a case needs support or viewer, run `node scripts/persona.mjs support` or `node scripts/persona.mjs viewer` before browsing as that user.",
        "That writes runs/cache/stytch/<persona>.json. Do not read the file. Load it with playwright-cli state-load.",
        "A spec for that persona calls injectAuthCookies(page.context(), 'support') or 'viewer'. Other specs keep the default call.",
        f"The live URL is the appUrl in the context pack. Do not start a dev server. Put snapshots in {relative}/explore/.",
        f"Walk the app with playwright-cli. Write {relative}/FEATURE.md and append each successful step to {relative}/explore/flow.md. When the walk includes a listing, use references/listing-exploration-hints.md. A covered row cites an id from e2e-coverage.md. A new row is a control the walk reached. A control the walk did not reach is a Gap, not a test.",
        f"Then write specs and the POM under {relative}/specs/ from {relative}/FEATURE.md and {relative}/explore/flow.md. Open the app when a selector is missing. Do not write a Gap or a covered row.",
        f"Leave FEATURE.md at {relative}/FEATURE.md. Do not copy it into specs/ or tests/.",
        f"From a file in {relative}/specs/, import auth as '{_import_prefix(relative)}/auth-helper'. Put the POM in that same specs folder. Do not import anything from tests/.",
        f"planned-specs.json goes in {relative}/. plan_file is {relative}/FEATURE.md. test_files and pom_files are paths like {relative}/specs/<name>.spec.ts.",
        "Do not run preflight, do not call /auth/password, and do not run the official Playwright suite. Replaying one step with playwright-cli is part of writing the spec.",
    ])


def _promote_into_suite(folder: Path, ticket: str, book: Logbook) -> None:
    """Copy the passing journeys into the checked-in suite before the run is sealed."""
    book.phase("promote")
    prompt = _promote_prompt(folder, ticket)
    (folder / "promote-prompt.md").write_text(prompt + "\n", encoding="utf-8")
    code, _session = runners.run_opencode(
        folder,
        session_id=None,
        prompt=prompt,
        title=f"{ticket} promote",
        log_name="promote.jsonl",
    )
    promoted = _read_json(folder / "promoted.json")
    cases = promoted.get("cases") if isinstance(promoted.get("cases"), list) else []
    if code != 0:
        book.row("server", "promote", _opencode_failure(folder, "promote.jsonl", code))
        return
    if not cases:
        book.row("server", "promote", "no new journey copied")
        return
    book.row("server", "promote", f"{len(cases)} case(s) added to e2e test cases")


def _promote_prompt(folder: Path, ticket: str) -> str:
    relative = _display(folder)
    return "\n".join([
        f"Promote passing tests from ticket {ticket} into the checked-in suite before sign-off.",
        f"Run directory: {relative}",
        f"Final per-test status: {relative}/playwright/test-outcomes.json (use this after heals; not the partial results.json alone)",
        f"Playwright report: {relative}/playwright/results.json",
        f"Feature specs and POM: {relative}/specs/",
        f"Coverage already in the suite: {relative}/e2e-coverage.md",
        "Checked-in suite: `e2e test cases/`.",
        "Follow the Promote step in .agents/skills/lexful-autonomous-agent-qa/SKILL.md.",
        "Copy at most three tests that passed in this run: the positive path that completes the new behavior, the guard that keeps it safe, and the ordinary path that must keep working.",
        "Skip gaps, failures, skips, tooltip-only checks, and any title already listed in e2e-coverage.md.",
        "Document-editor flows go in `e2e test cases/document editing` with the next TC-DOC id.",
        "Record drawers and attachments go in `e2e test cases/asset crud` with the next free AC- id.",
        "Search-palette flows go in `e2e test cases/search`.",
        "Import auth as `../../auth-helper`. Keep the POM beside the spec. Keep afterEach cleanup.",
        "The test() title must match the FEATURE.md Title cell exactly, with no id prefix.",
        "Append one inventory row per new test to that folder's FEATURE.md.",
        f"Write {relative}/promoted.json as {{\"files\":[...],\"cases\":[{{\"id\":\"...\",\"title\":\"...\"}}]}}.",
        "If nothing qualifies, write promoted.json with empty files and cases.",
        "Do not run Playwright. Do not edit specs that were already in the suite. Do not change playwright.config.ts.",
    ])


def _promoted_section(folder: Path) -> list[str]:
    promoted = _read_json(folder / "promoted.json")
    cases = promoted.get("cases") if isinstance(promoted.get("cases"), list) else []
    if not cases:
        return []
    lines = ["## Promoted into e2e test cases", ""]
    for case in cases:
        if not isinstance(case, dict):
            continue
        lines.append(f"- `{case.get('id', '')}` {case.get('title', '')}".rstrip())
    lines.append("")
    return lines


def _ux_audit_prompt(
    folder: Path,
    ticket: str,
    preflight: dict[str, Any],
) -> str:
    relative = _display(folder)
    return "\n".join([
        f"UI/UX audit for ticket: {ticket}",
        f"Run directory: {relative}",
        f"App URL: {preflight.get('appUrl') or 'the appUrl in the context pack'}",
        f"Context pack: {relative}/context-pack.json",
        f"Feature map and explored routes: {relative}/FEATURE.md",
        f"Exploration snapshots: {relative}/explore/",
        f"Triage notes and healed locators: {relative}/triage.json",
        "Follow .agents/skills/ux-audit/SKILL.md and .agents/skills/design-system/SKILL.md.",
        "Read .agents/ux/rulebook.md, .agents/ux/pattern-library.md, .agents/ux/checks.yaml, .agents/ux/traceability.md, and .agents/ux/audit-preview-reference.html.",
        "The HTML file is a visual reference. Do not copy its example findings.",
        "Working UI passes. QA-expected behavior is at most an Observation (O).",
        "S2 and S3 do not fail the audit. With no S0 or S1, the verdict is PASS WITH ADVISORIES. Only S0 or S1 is BLOCKING FAIL.",
        f"Write ux-report.html, ux-findings.json, and ux-scorecard.json into {relative}/.",
        "Do not write test specs and do not edit product code.",
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
    relative = _display(folder)
    listed = ", ".join(specs)
    counts = attempts_used or {}
    failing_lines = [
        f"- {item['title']}  (attempt {counts.get(item['title'], attempt)} of {total})"
        for item in (failing or [])
    ] or ["- the Playwright report has failures, but no test title was parsed"]
    return "\n".join([
        f"Ticket {ticket}. Heal attempt {attempt} of {total}.",
        f"Playwright results: {relative}/playwright/results.json",
        f"Playwright log: {relative}/playwright/output.log",
        f"Specs: {listed}",
        "Follow the Feature Specific Heal step in .agents/skills/lexful-autonomous-agent-qa/SKILL.md. Stay in this session.",
        "Do not apply the E2E User Journey heal section.",
        f"Exploration: {relative}/explore/ and {relative}/FEATURE.md and {relative}/explore/flow.md.",
        "Replay each failing test below. Fix the locator, rewrite the step to a control this session saw, create the missing fixture, or remove the test.",
        f"Stop after {total} attempts at a failing test. class is spec, gap, or bug.",
        "A gap is a case the walk never reached. Remove or rewrite that test and leave the reason in FEATURE.md Gaps. Do not put it in bugs.",
        "A behavior this ticket requires stays a gap on the record. Removing the test does not make the run a pass.",
        "A bug is a step this session completed where the page then did the wrong thing. Do not change that expected outcome.",
        "If you are unsure, class it gap and do not file a bug.",
        "Add a bugs array to triage.json, one object per product defect. The server writes bugs.md from it.",
        "Do not put a skipped, deprecated, or gap test in bugs.",
        "Before you return, delete every record this session created.",
        "Do not run the official suite. The server re-runs the failed spec files when you change one.",
        "Each bug needs area, failure, context, severity (Critical, High, Medium, or Low), severityReason, description, affectedTests, steps, expected, actual, rootCause, and evidence.",
        "Severity decides priority: Critical is P0, High is P1, Medium is P2, Low is P3.",
        "Still failing:",
        *failing_lines,
    ])


def _phase1_heal_prompt(folder: Path, attempt: int, total: int, specs: list[str]) -> str:
    relative = _display(folder)
    failures = failed_tests(_read_json(folder / "playwright" / "results.json"))
    listed = "\n".join(
        f"- {item['title']}  ({_short_file(item['file'])})  {item['error']}".rstrip()
        for item in failures[:40]
    ) or "- the Playwright report has failures, but no test title was parsed"
    return "\n".join([
        "This is an E2E User Journey TCs heal. It is not Feature Specific TCs.",
        "Follow only the E2E User Journey heal section in .agents/skills/lexful-autonomous-agent-qa/SKILL.md.",
        "Do not apply Feature Specific Heal. Do not remove a test because you are unsure.",
        "Do not explore or write a new test. Do not call Linear, GitHub, or /auth/password.",
        "In this one return, patch every spec-drift failure in the checked-in suite, then stop.",
        "CloudFront 403 Request blocked on UAT is environment timing: class spec, retry navigation, do not file bugs.",
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
        "Add a bugs array for those product defects. One object can list several affectedTests when they are the same defect. The server writes bugs.md.",
        "Do not put a skipped or deprecated test in failures or in bugs.",
        "Each bug needs area, failure, context, severity (Critical, High, Medium, or Low), severityReason, description, affectedTests, steps, expected, actual, rootCause, and evidence.",
        "Severity decides priority: Critical is P0, High is P1, Medium is P2, Low is P3.",
        "Failures:",
        listed,
        f"Specs: {', '.join(specs)}",
        "Do not run the suite. The server re-runs the failed spec files only if you changed one.",
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
        kind = failure_kind(item) or "note"
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


def _record_bugs(folder: Path, row: dict[str, Any], summary: dict[str, int]) -> bool:
    triage, cycle = latest_triage(folder)
    pack = _read_json(folder / "context-pack.json")
    url = str(pack.get("appUrl") or get_settings().qa_url)
    return publish_bugs(
        folder,
        ticket=str(row.get("ticket") or ""),
        run_id=str(row.get("id") or folder.name),
        url=url,
        build=str(row.get("sha") or "unknown"),
        failed=int(summary.get("failed") or 0),
        triage=triage,
        still_failing=failed_tests(_read_json(folder / "playwright" / "results.json")),
        cycle=cycle,
    )


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
            text = f"- {failure_kind(item) or 'note'} / {item.get('action')}: {_failure_title(item)}"
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


def _ux_report_section(folder: Path) -> list[str]:
    card = _read_json(folder / "ux-scorecard.json")
    if not card and not (folder / "ux-report.html").is_file():
        return []
    findings = _read_findings(folder / "ux-findings.json")
    counts = card.get("counts") if isinstance(card.get("counts"), dict) else card
    lines = [
        "## UI/UX audit",
        "",
        f"- UX verdict: **{card.get('verdict', 'PASS')}**",
        f"- Score: {card.get('score', 100)} / 100",
        f"- Findings: S0={counts.get('S0', 0)}, S1={counts.get('S1', 0)}, S2={counts.get('S2', 0)}, S3={counts.get('S3', 0)}, Observations={counts.get('O', 0)}",
        "- Report: `ux-report.html`",
        "- Findings file: `ux-findings.json`",
    ]
    if findings:
        lines.append("")
        lines.append("### Key UX Findings")
        lines.append("")
        for f in findings[:10]:
            if isinstance(f, dict):
                sev = f.get("severity") or "O"
                cid = f.get("checkId") or f.get("id") or "UX"
                title = f.get("title") or f.get("issue") or ""
                lines.append(f"- **[{sev}] {cid}**: {title}")
    lines.append("")
    return lines


def _model_line() -> str:
    settings = get_settings()
    if settings.sub_model == settings.main_model:
        return settings.main_model
    return f"{settings.main_model}  subagents {settings.sub_model}"


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
    suite = "E2E User Journey TCs" if row.get("kind") == "phase1" else "Feature Specific TCs"
    lines = [
        f"# {row.get('ticket') or row.get('id')}",
        "",
        f"- Suite: {suite}",
        f"- Run: `{row.get('id')}`",
        f"- Status: {row.get('status')}",
        f"- Verdict: {verdict}",
        f"- Model: {_model_line()}",
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
    bugs = folder / "bugs.md"
    if bugs.is_file():
        lines.extend(["## Bugs", "", bugs.read_text(encoding="utf-8").rstrip(), ""])
    ux_section = _ux_report_section(folder)
    if ux_section:
        lines.extend(ux_section)
    promoted = _promoted_section(folder)
    if promoted:
        lines.extend(promoted)
    lines.append("Artifacts in this folder include `preflight.json`, `opencode/`, `playwright/`, and `qa-result.json`. Product bugs are in `bugs.md` when a failure remains. The Stytch session is `runs/cache/stytch/session.json`.")
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
