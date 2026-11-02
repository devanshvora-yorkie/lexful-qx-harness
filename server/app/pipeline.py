"""Ticket run: preflight, coordinator, Playwright, then at most three heals."""

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

from app import checks, linear_report, prune, runners, store, summary as run_summary
from app.bugs import failure_kind, latest_triage, publish_bugs, publish_findings
from app.coverage import load_cases, write_coverage_index
from app.logbook import Logbook, echo_run, plain
from app.settings import get_settings
from app.ux_report import write_ux_report

log = logging.getLogger("qa.pipeline")

# Explore, Author, ticket heal and verify may not edit the checked-in suite (opencode.jsonc denies it).
# Promote and the E2E heal use `qa`, which may.
TICKET_AGENT = "qa-ticket"
SUITE_AGENT = "qa"
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
    issues: list[str] = []
    structured = checks.coverage_blockers(folder, _passing_title_list(folder))
    if structured is not None:
        # coverage.json maps every criterion to test ids or a gap; the server checks the ids passed.
        issues.extend(structured)
    else:
        passed = _content_words(_passing_titles(folder))
        for criterion in _acceptance_lines(folder):
            words = _content_words(criterion)
            if not words:
                continue
            needed = 1 if len(words) < 3 else 2
            if len(words & passed) < needed:
                issues.append(f"acceptance criterion not covered by a passing test (no coverage.json): {criterion}")
    _line, hypothesis_blockers = checks.hypothesis_report(folder)
    issues.extend(hypothesis_blockers)
    for gap in ([] if structured is not None else _feature_gaps(feature)):
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


def _passing_title_list(folder: Path) -> list[str]:
    """Final passing titles after every heal (test-outcomes.json), else from the last report."""
    path = folder / "playwright" / "test-outcomes.json"
    if path.is_file():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            rows = []
        if isinstance(rows, list):
            return [str(r.get("title")) for r in rows if isinstance(r, dict) and r.get("status") in {"passed", "flaky"}]
    return _passing_titles(folder).split(" \x1f ")


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
    return " \x1f ".join(titles)


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
    if row.get("status") in {"failed", "halted", "completed", "needs_revision"} and not row.get("resume"):
        return  # cancelled or finished while it waited in the queue
    folder = store.run_dir(run_id)
    book = Logbook(folder)
    run_summary.get(run_id)
    try:
        if row.get("kind") == "phase1":
            with SUITE_LOCK:
                _execute_phase1(run_id, row, folder, book)
        else:
            store.attach_e2e_log(folder)
            if (folder / "e2e" / "run.log").is_file():
                book.row("server", "e2e", "E2E User Journey log saved in e2e/run.log")
            _execute(run_id, row, folder, book)
    except RunCancelled:
        reason = "cancelled by user"
        book.row("server", "cancelled", "processes stopped; sealing the run")
        store.update_run(run_id, status="failed", error=reason)
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[reason])
        _seal(run_id, None, "HALTED", issues=[reason], error=reason, status="cancelled")
    except Exception as exc:
        book.row("server", "failed", str(exc)[:220])
        log.exception("run failed")
        store.update_run(run_id, status="failed", error=str(exc)[:500])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[str(exc)[:500]])
        _seal(run_id, None, "HALTED", issues=[str(exc)[:500]], error=str(exc)[:200])
    finally:
        with _CANCELLED_LOCK:
            _CANCELLED.discard(run_id)
        run_summary.drop(run_id)
        if row.get("kind") == "phase1":
            try:
                store.share_e2e_log(run_id)
            except Exception:
                log.exception("e2e log was not copied into the ticket folder")


def _explore_and_author(
    run_id: str, row: dict[str, Any], folder: Path, book: Logbook, settings: Any
) -> tuple[str, dict[str, Any], str, float] | None:
    """Preflight, then the qa agent walks and writes the specs. None means the run was sealed here."""
    store.update_run(run_id, status="preflight")
    _begin(run_id, book, "preflight")
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
        _end(run_id, "preflight", "failed", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket or None, "HALTED", summary, [detail])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[detail])
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
    store.update_run(run_id, status="agent", ticket=ticket, pr=preflight.get("primaryPr"))
    _begin(run_id, book, "explore + author")
    covered = write_coverage_index(settings.root / "e2e test cases", folder / "e2e-coverage.md")
    book.row("server", "coverage", f"{covered} checked-in cases")
    history = write_history(folder, ticket)
    if history:
        book.row("server", "history", f"{history} earlier run(s) of {ticket} in history.md")
    source = runners.prepare_source(folder)
    book.row("server", "source", "read-only worktree ready" if source else "no clone, agent greps the context pack")
    cli_config = runners.write_cli_config(folder)
    if cli_config:
        book.row("server", "browser", "playwright-cli config written")
    prompt = _lead_prompt(folder, ticket, preflight, run_id)
    (folder / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    started = time.time()
    suite_before = _suite_files()
    agent_code, session_id = _plan_then_explore(run_id, folder, ticket, prompt, settings, book)
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
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[reason])
        _seal(run_id, summary, "HALTED", issues=[reason])
        return None
    _end(run_id, "explore + author")
    return ticket, preflight, session_id, started


def _plan_then_explore(
    run_id: str, folder: Path, ticket: str, prompt: str, settings: Any, book: Logbook
) -> tuple[int, str]:
    """With QA_PLAN_MODEL set, the plan is its own turn (Phase: plan), then the walk continues in the same session.

    The model for the plan turn is QA_PLAN_MODEL (Haiku by default, like everything else). When the plan
    turn fails the whole job runs in one turn.
    """
    if settings.plan_model:
        book.row("server", "plan", f"feature map and plan with {settings.plan_model}")
        code, session_id = runners.run_opencode(
            folder, session_id=None, prompt=_plan_message(prompt), title=f"{ticket} {run_id}",
            log_name="agent-plan.jsonl", agent=TICKET_AGENT, model=settings.plan_model,
        )
        _check_cancel(run_id)
        if code == 0 and session_id and (folder / "feature-map.md").is_file():
            return runners.run_opencode(
                folder, session_id=session_id, prompt=prompt, title=f"{ticket} {run_id}",
                log_name="agent.jsonl", resume=True, agent=TICKET_AGENT,
            )
        book.row("server", "plan", f"plan turn failed ({_opencode_failure(folder, 'agent-plan.jsonl', code)}). The main model does the whole job")
    return runners.run_opencode(
        folder, session_id=None, prompt=prompt, title=f"{ticket} {run_id}",
        log_name="agent.jsonl", agent=TICKET_AGENT,
    )


def _plan_message(prompt: str) -> str:
    return prompt.replace("Phase: explore+author", "Phase: plan", 1)


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
        explored = _explore_and_author(run_id, row, folder, book, settings)
        if explored is None:
            return
        ticket, preflight, session_id, started = explored
        book.row("qa", "finished", "coordinator returned")
    specs = runners.planned_specs(folder, started)
    if not specs:
        detail = "the agent did not write a spec file"
        book.row("server", "halted", detail)
        store.update_run(run_id, status="halted", error=detail)
        summary = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
        _write_qa_result(folder, ticket, "HALTED", summary, [detail])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[detail])
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
            book.row("server", "ux-audit", "started beside Playwright. Its log is ux-audit.log")
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
        if settings.verify_findings:
            _verify_findings(run_id, folder, ticket, book, signals)
    finally:
        if ux_thread is not None:
            if ux_thread.is_alive():
                book.row("server", "ux-audit", "waiting for the UX audit to finish")
            ux_thread.join()
    _check_cancel(run_id)
    if settings.run_ux_audit and ticket and not settings.ux_parallel:
        _begin(run_id, book, "ui-ux audit")
        _run_ux_audit(run_id, folder, ticket, preflight, ux_state, False)
    ux_issue = _finish_ux(run_id, folder, ticket, book, ux_state) if settings.run_ux_audit and ticket else ""

    verdict = verdict_for(summary, preflight_ok=True, produced_specs=True)
    issues = [] if verdict == "PERFECT" else [_open_issue(summary)]
    blockers = signoff_blockers(folder) if ticket else []
    blockers.extend(affected)
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
    if _record_bugs(folder, store.get_run(run_id) or row, summary):
        book.row("server", "bugs", "bugs.md")
    _note_findings(run_id, folder)
    _write_qa_result(folder, ticket, verdict, summary, issues, specs)
    _write_report(folder, store.get_run(run_id) or row, verdict=verdict, summary=summary, issues=issues)
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
            agent="ux-auditor",
            book_name="ux-audit.log" if parallel else "run.log",
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
    if wrote:
        write_ux_report(folder, ticket)
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
    return ""


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
        _write_report(
            folder,
            store.get_run(run_id) or row,
            verdict="HALTED",
            summary=summary,
            issues=[detail],
            extra=_phase1_report_lines(),
        )
        _seal(run_id, summary, "HALTED", issues=[detail])
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
        _seal(run_id, summary, "HALTED", issues=[detail])
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
    _note_findings(run_id, folder)
    _seal(run_id, summary, verdict, issues=issues)


def _seal(
    run_id: str,
    summary: dict[str, Any] | None,
    verdict: str | None,
    *,
    issues: list[str] | None = None,
    error: str = "",
    status: str = "",
) -> None:
    """Write the run summary, then put the final counts in the folder name."""
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
    if row.get("kind") != "phase1":
        try:
            linear_report.write(folder, row, verdict=verdict or "HALTED", issues=issues or [])
        except Exception:
            log.exception("linear report was not written")
    try:
        runners.cleanup_source(folder)
    except Exception:
        log.exception("worktree was not removed")
    target = ""
    try:
        target = store.publish_folder(run_id, summary=summary, verdict=verdict)
        Logbook(store.runs_root() / target).row("server", "folder", f"runs/{target}")
    except Exception:
        log.exception("run folder was not renamed")
    try:
        sealed = store.runs_root() / target if target else folder
        finished = (status or str(row.get("status") or "")) in {"completed", "needs_revision"}
        freed = prune.prune_run(sealed, finished=finished)
        if freed:
            Logbook(sealed).row("server", "prune", f"removed {prune.mib(freed)} of scratch and duplicate files")
    except Exception:
        log.exception("run folder was not pruned")


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
    _begin(run_id, book, "playwright")
    book.row("playwright", "started", f"{len(specs)} files  {', '.join(specs)}"[:240])
    result = runners.run_playwright(folder, specs)
    _check_cancel(run_id)
    summary = result["summary"]
    book.row("playwright", "result", _counts(summary))
    _end(run_id, "playwright", "ok" if not result.get("setupError") else "failed", _counts(summary))
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
    verifier_hints_now: dict[str, str] = {}
    fresh_heal = not classify and get_settings().heal_fresh_session
    if fresh_heal:
        session_id = ""  # round 1 starts clean; later rounds resume that small session
    for attempt in range(1, heal_attempts + 1):
        store.update_run(run_id, status="heal", healAttempts=attempt)
        _begin(run_id, book, f"heal {attempt} of {heal_attempts}")
        who = "qa E2E heal" if classify else "qa feature heal"
        book.row("server", "heal", f"{attempt} of {heal_attempts}  {who}  {len(specs)} files")
        failing_now = failed_tests(_read_json(folder / "playwright" / "results.json"))
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
            agent=SUITE_AGENT if classify else TICKET_AGENT,
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
                    run_id, folder, "checked-in", book, {}, label=f"verify bugs after heal {attempt}")
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
        previous_report = _read_json(folder / "playwright" / "results.json")
        rerun = specs_for_failures(specs, previous_report) or specs
        if not baseline:
            baseline = outcomes_by_file(previous_report)
        store.update_run(run_id, status="execute")
        _begin(run_id, book, f"playwright after heal {attempt}")
        book.row("playwright", "started", f"re-running {len(rerun)} failed file(s) after heal {attempt}"[:240])
        result = runners.run_playwright(folder, rerun)
        _check_cancel(run_id)
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
        _end(run_id, None, "ok", _counts(summary))
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


SKILL = ".agents/skills/lexful-autonomous-agent-qa/SKILL.md"


def _message(phase: str, folder: Path, *facts: str) -> str:
    """The text the server sends OpenCode. Facts only: the rules for each phase are in the skill, section 7."""
    return "\n".join([
        f"Phase: {phase}",
        f"Run directory: {_display(folder)}",
        f"Follow {SKILL}, section 7, for this phase. Entry point: .agents/prompts/qa.md.",
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
    """history.md: earlier runs of this ticket, their verdict, bugs and open issues. Returns how many."""
    root = get_settings().runs / "tickets" / ticket
    if not ticket or not root.is_dir():
        return 0
    earlier = sorted((p for p in root.iterdir() if p.is_dir() and p.resolve() != folder.resolve()), reverse=True)[:5]
    lines = [f"# Earlier runs of {ticket}", "", "Newest first. Retest what failed or was filed before; do not trust an old pass.", ""]
    count = 0
    for run in earlier:
        result = _read_json(run / "qa-result.json")
        if not result:
            continue
        count += 1
        counts = result.get("test_results") or {}
        lines.append(f"## {run.name}")
        lines.append(f"- Verdict: {result.get('verdict')}  passed {counts.get('passed', 0)}  failed {counts.get('failed', 0)}")
        for issue in (result.get("open_issues") or [])[:5]:
            lines.append(f"- Open: {str(issue)[:200]}")
        bugs = _read_text(run / "bugs.md")
        for title in re.findall(r"^#+\s*(.+)$", bugs, re.MULTILINE)[:6]:
            lines.append(f"- Bug filed: {title[:160]}")
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
    line = f"{len(cases)} run, {len(failing)} failed"
    run_summary.get(run_id).note("affected", line)
    _end(run_id, "affected E2E cases", "ok" if not failing else "failed", line)
    by_title = {case.title: case.id for case in cases}
    return [
        f"affected E2E case failed, possible regression from this ticket: {by_title.get(item['title'], '')} {item['title']} — {item['error'][:120]}".strip()
        for item in failing
    ]


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
    code, session = runners.run_opencode(folder, session_id=None, prompt=prompt, title=f"{ticket} verify",
                                          log_name=log_name,
                                          agent=SUITE_AGENT if ticket == "checked-in" else TICKET_AGENT)
    _check_cancel(run_id)
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
            item["confidence"] = "confirmed"
            item["verifier"] = str(result.get("notes") or "reproduced")[:300]
            confirmed += 1
        elif result.get("reproduced") is False:
            item["status"] = "skipped"
            item["verifier"] = "not reproduced: " + str(result.get("notes") or "")[:300]
            dropped += 1
    if data:
        findings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    triage_files = sorted(folder.glob("triage-*.json"))
    if triage_files:
        triage = _read_json(triage_files[-1])
        bugs = [b for b in triage.get("bugs") or [] if isinstance(b, dict)]
        kept = 0
        for index, bug in enumerate(triage.get("bugs") or [], start=1):
            result = by_ref.get(f"bug:{index}")
            if not isinstance(bug, dict) or result is None:
                kept += 1 if isinstance(bug, dict) and bug.get("status") != "skipped" else 0
                continue
            if result.get("reproduced") is True:
                bug["confidence"] = "confirmed"
                bug["verifier"] = str(result.get("notes") or "reproduced")[:300]
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
        triage_files[-1].write_text(json.dumps(triage, indent=2) + "\n", encoding="utf-8")
    return f"{confirmed} confirmed, {dropped} not reproduced"


def _note_findings(run_id: str, folder: Path) -> None:
    """Counts for the run summary."""
    notes = run_summary.get(run_id)
    bugs = _read_text(folder / "bugs.md")
    filed = len(re.findall(r"^Title:", bugs, re.MULTILINE))
    notes.note("bugs", f"{filed} in bugs.md" if bugs else "none")
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
        agent=SUITE_AGENT,
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
    *,
    parallel: bool = False,
) -> str:
    relative = _display(folder)
    return "\n".join([
        "Phase: ux-audit",
        f"Run directory: {relative}",
        f"Ticket: {ticket}",
        f"App URL: {preflight.get('appUrl') or 'the appUrl in the context pack'}",
        "Follow .agents/prompts/ux-auditor.md.",
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
    failures = failed_tests(_read_json(folder / "playwright" / "results.json"))
    listed = "\n".join(
        f"- {item['title']}  ({_short_file(item['file'])})  {item['error']}".rstrip()
        for item in failures[:40]
    ) or "- the Playwright report has failures, but no test title was parsed"
    seen = [f"- {name}: {hint}" for name, hint in (hints or {}).items()]
    return _message(
        "e2e-heal", folder,
        "Suite: E2E User Journey TCs (not a ticket)",
        f"Heal attempt {attempt} of {total}",
        f"Specs: {', '.join(specs)}",
        f"Browser session name: {_browser_name(folder, 'heal')}",
        "Failures:",
        listed,
        *(["The verifier could not reproduce a product defect for these. The test or its data is outdated; fix it:", *seen] if seen else []),
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


def _record_bugs(folder: Path, row: dict[str, Any], summary: dict[str, int]) -> bool:
    triage, cycle = latest_triage(folder)
    pack = _read_json(folder / "context-pack.json")
    url = str(pack.get("appUrl") or get_settings().qa_url)
    deployment = pack.get("deployment") if isinstance(pack.get("deployment"), dict) else {}
    build = str(row.get("sha") or deployment.get("build") or "unknown")
    filed = publish_bugs(
        folder,
        ticket=str(row.get("ticket") or ""),
        run_id=str(row.get("id") or folder.name),
        url=url,
        build=build,
        failed=int(summary.get("failed") or 0),
        triage=triage,
        still_failing=failed_tests(_read_json(folder / "playwright" / "results.json")),
        cycle=cycle,
    )
    probed = publish_findings(
        folder,
        ticket=str(row.get("ticket") or ""),
        run_id=str(row.get("id") or folder.name),
        url=url,
        build=build,
    )
    return filed or probed > 0


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


_PHASE_OF_LOG = (
    ("agent-plan", "Plan"),
    ("agent", "Explore + Author"),
    ("verify", "Verify"),
    ("heal", "Heal"),
    ("ux-audit", "UX audit"),
    ("promote", "Promote"),
)


def phase_costs(folder: Path) -> dict[str, dict[str, float]]:
    """Per phase steps, output tokens, cache-read tokens, and cost, from the OpenCode logs of this run."""
    phases: dict[str, dict[str, float]] = {}
    for log in sorted((folder / "opencode").glob("*.jsonl")):
        label = next((name for prefix, name in _PHASE_OF_LOG if log.stem.startswith(prefix)), log.stem)
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


def _cost_section(folder: Path) -> list[str]:
    phases = phase_costs(folder)
    if not phases:
        return []
    (folder / "cost.json").write_text(json.dumps(phases, indent=2) + "\n", encoding="utf-8")
    total = sum(row["cost"] for row in phases.values())
    lines = ["## Cost", "", "| Phase | Steps | Output tokens | Cache-read tokens | Cost |", "|---|---|---|---|---|"]
    for label, row in phases.items():
        lines.append(f"| {label} | {int(row['steps'])} | {int(row['output']):,} | {int(row['cacheRead']):,} | ${row['cost']:.2f} |")
    lines.extend([f"| **Total** | | | | **${total:.2f}** |", ""])
    return lines


def _checks_section(folder: Path) -> list[str]:
    """Deployment, hypotheses, affected E2E cases, verifier results and heal expectation edits."""
    lines: list[str] = []
    deployment = _deployment_line(folder)
    if deployment:
        lines.append(f"- Deployment: {deployment}")
    if (folder / "hypotheses.json").is_file():
        lines.append(f"- Risk hypotheses: {checks.hypothesis_report(folder)[0]}")
    affected = _read_json(folder / "affected" / "playwright" / "results.json")
    if affected:
        stats = affected.get("stats") or {}
        lines.append(f"- Affected E2E cases: passed {stats.get('expected', 0)}, failed {stats.get('unexpected', 0)}, flaky {stats.get('flaky', 0)}")
    verified = [r for r in _read_json(folder / "verify.json").get("results") or [] if isinstance(r, dict)]
    if verified:
        yes = sum(1 for r in verified if r.get("reproduced") is True)
        lines.append(f"- Verifier: {yes} of {len(verified)} reproduced")
    edits = checks.assertion_edits(folder)
    for edit in edits[:8]:
        lines.append(f"- Heal changed an expectation: {edit}")
    return ["## Checks", "", *lines, ""] if lines else []


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
        f"- Score: {card.get('score') if card.get('score') is not None else 'not scored'} / 100",
        *([f"- Audit error: {card.get('error')}"] if card.get("error") else []),
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
    lines.extend(_checks_section(folder))
    lines.extend(checks.signals_section(folder))
    ux_section = _ux_report_section(folder)
    if ux_section:
        lines.extend(ux_section)
    cost_section = _cost_section(folder)
    if cost_section:
        lines.extend(cost_section)
    promoted = _promoted_section(folder)
    if promoted:
        lines.extend(promoted)
    lines.append("Artifacts in this folder include `preflight.json`, `opencode/`, `playwright/`, and `qa-result.json`. Product bugs are in `bugs.md` when a failure remains. The Stytch session is `runs/cache/stytch/session.json`.")
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
