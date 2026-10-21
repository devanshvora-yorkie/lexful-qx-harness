"""Ticket run: preflight, Sonnet coordinator, Playwright, then at most three Haiku heals."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from app import runners, store
from app.logbook import Logbook
from app.settings import get_settings

log = logging.getLogger("qa.pipeline")


def verdict_for(summary: dict[str, int], *, preflight_ok: bool, produced_specs: bool) -> str:
    if not preflight_ok:
        return "HALTED"
    if not produced_specs:
        return "HALTED"
    if summary.get("failed", 0) == 0 and summary.get("passed", 0) > 0:
        return "PERFECT"
    return "NEEDS_REVISION"


def execute_run(run_id: str) -> None:
    row = store.get_run(run_id)
    if row is None:
        raise KeyError(run_id)
    folder = store.run_dir(run_id)
    book = Logbook(folder)
    try:
        _execute(run_id, row, folder, book)
    except Exception as exc:
        book.row("server", "failed", str(exc)[:220])
        log.exception("run failed")
        store.update_run(run_id, status="failed", error=str(exc)[:500])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[str(exc)[:500]])


def _execute(run_id: str, row: dict[str, Any], folder: Path, book: Logbook) -> None:
    settings = get_settings()
    book.row("server", "queued", str(row.get("ticket") or run_id))
    store.update_run(run_id, status="preflight")
    book.row("server", "preflight", "started")
    code = runners.run_preflight(folder, ticket=row.get("ticket"), pr=row.get("pr"), sha=row.get("sha"))
    preflight = _read_json(folder / "preflight.json")
    preflight_ok = code == 0 and bool(preflight.get("ok"))
    ticket = str(preflight.get("ticket") or row.get("ticket") or "")
    if ticket and ticket != row.get("ticket"):
        store.update_run(run_id, ticket=ticket, pr=preflight.get("primaryPr"), sha=row.get("sha"))
    if not preflight_ok:
        detail = _failed_check(preflight) or "preflight failed"
        book.row("server", "preflight", f"failed  {detail}")
        store.update_run(run_id, status="halted", error=detail)
        _write_qa_result(folder, ticket or None, "HALTED", {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}, [detail])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[detail])
        return

    book.row(
        "server",
        "preflight",
        f"ok  {ticket or 'no ticket'}  PR {preflight.get('primaryPr') or 'none'}  "
        f"{len(preflight.get('checks') or [])} checks",
    )
    store.update_run(run_id, status="agent", ticket=ticket, pr=preflight.get("primaryPr"))
    session_id = _opencode_session(run_id, row)
    book.row("qa", "started", f"{settings.main_model}  {session_id}")
    prompt = _lead_prompt(folder, ticket, row.get("specCount"), preflight)
    (folder / "prompt.md").write_text(prompt + "\n", encoding="utf-8")
    started = time.time()
    agent_code = runners.run_opencode(
        folder,
        session_id=session_id,
        prompt=prompt,
        title=f"{ticket} {run_id}",
        log_name="agent.jsonl",
    )
    runners.export_session(folder, session_id)
    if agent_code != 0:
        reason = _opencode_failure(folder, "agent.jsonl", agent_code)
        book.row("qa", "failed", reason)
        log.error("%s", reason)
        store.update_run(run_id, status="failed", error=reason)
        _write_qa_result(folder, ticket, "HALTED", {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}, [reason])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[reason])
        return

    book.row("qa", "finished", "coordinator returned")
    specs = runners.planned_specs(folder, started)
    if not specs:
        detail = "the agent did not write a spec file"
        book.row("server", "halted", detail)
        store.update_run(run_id, status="halted", error=detail)
        _write_qa_result(folder, ticket, "HALTED", {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}, [detail])
        _write_report(folder, store.get_run(run_id) or row, verdict="HALTED", summary=None, issues=[detail])
        return

    book.row("server", "specs", f"{len(specs)} files")
    summary = _execute_and_heal(run_id, folder, ticket, specs, settings.heal_attempts, session_id, book)
    verdict = verdict_for(summary, preflight_ok=True, produced_specs=True)
    status = "completed" if verdict == "PERFECT" else "needs_revision"
    issues = [] if verdict == "PERFECT" else [f"{summary['failed']} test(s) still failing"]
    book.row(
        "server",
        "verdict",
        f"{verdict}  passed {summary['passed']}  failed {summary['failed']}  skipped {summary.get('skipped', 0)}",
    )
    store.update_run(run_id, status=status, error=None)
    _write_qa_result(folder, ticket, verdict, summary, issues, specs)
    _write_report(folder, store.get_run(run_id) or row, verdict=verdict, summary=summary, issues=issues)


def _opencode_session(run_id: str, row: dict[str, Any]) -> str:
    current = str(row.get("opencodeSession") or "")
    if current.startswith("ses"):
        return current
    session_id = store.new_opencode_session_id()
    store.update_run(run_id, opencodeSession=session_id)
    return session_id


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
) -> dict[str, int]:
    store.update_run(run_id, status="execute")
    book.row("playwright", "started", f"{len(specs)} files")
    result = runners.run_playwright(folder, specs)
    summary = result["summary"]
    book.row("playwright", "result", _counts(summary))
    if result["exitCode"] == 0 and summary["failed"] == 0 and summary["passed"] > 0:
        return summary
    for attempt in range(1, heal_attempts + 1):
        store.update_run(run_id, status="heal", healAttempts=attempt)
        book.row("server", "heal", f"{attempt} of {heal_attempts}")
        prompt = _heal_prompt(folder, ticket, attempt, heal_attempts, specs)
        (folder / f"heal-{attempt}.md").write_text(prompt + "\n", encoding="utf-8")
        runners.run_opencode(
            folder,
            session_id=session_id,
            prompt=prompt,
            title=f"{ticket} heal {attempt}",
            log_name=f"heal-{attempt}.jsonl",
        )
        runners.export_session(folder, session_id)
        store.update_run(run_id, status="execute")
        book.row("playwright", "started", f"after heal {attempt}")
        result = runners.run_playwright(folder, specs)
        summary = result["summary"]
        book.row("playwright", "result", _counts(summary))
        if result["exitCode"] == 0 and summary["failed"] == 0 and summary["passed"] > 0:
            return summary
    return summary


def _counts(summary: dict[str, int]) -> str:
    return (
        f"passed {summary.get('passed', 0)}  failed {summary.get('failed', 0)}  "
        f"skipped {summary.get('skipped', 0)}  flaky {summary.get('flaky', 0)}"
    )


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
        f"Auth cookies: {relative}/auth-state.json",
        f"The live URL is the appUrl in the context pack. Put snapshots in {relative}/explore/.",
        "Delegate Phase 1 to qa-explorer. It writes FEATURE.md with the URL, API calls, and action matrix.",
        "Then delegate Phase 2 to qa-author. It writes the POM, specs, and planned-specs.json.",
        f"planned-specs.json goes in {relative}/ and lists test_files, pom_files, and plan_file.",
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
        "Delegate only to qa-healer. Do not re-explore and do not add scenarios.",
        "Do not run the suite. The server will run it after you return.",
    ])


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
    (folder / "qa-result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_report(
    folder: Path,
    row: dict[str, Any],
    *,
    verdict: str,
    summary: dict[str, int] | None,
    issues: list[str],
) -> None:
    counts = summary or {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
    lines = [
        f"# {row.get('ticket') or row.get('id')}",
        "",
        f"- Run: `{row.get('id')}`",
        f"- Status: {row.get('status')}",
        f"- Verdict: {verdict}",
        f"- Models: {get_settings().main_model} coordinates, {get_settings().sub_model} does the subagent work",
        f"- Passed: {counts['passed']}",
        f"- Failed: {counts['failed']}",
        f"- Skipped: {counts['skipped']}",
        "",
    ]
    if issues:
        lines.append("## Open issues")
        lines.extend(f"- {issue}" for issue in issues)
        lines.append("")
    lines.append("Artifacts in this folder: `preflight.json`, `context-pack.json`, `auth-state.json`, `opencode/`, `playwright/`, `qa-result.json`.")
    (folder / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
