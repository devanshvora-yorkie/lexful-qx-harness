"""End-of-run summary: each phase with its status and time, where the run stopped, and the totals.

The pipeline calls `begin` and `end` around each phase. `write` runs when the run is sealed,
on every path (pass, revision, halt, crash, cancel), so run.log always ends with this block
and summary.json holds the same data.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.logbook import Logbook

_LOCK = threading.Lock()
_RUNS: dict[str, "RunSummary"] = {}


def _span(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


class RunSummary:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.started = time.time()
        self.phases: list[dict[str, Any]] = []
        self.notes: dict[str, Any] = {}
        self._lock = threading.Lock()

    def begin(self, name: str, *, parallel: bool = False) -> None:
        """Start a phase. A sequential phase closes the sequential phase before it."""
        with self._lock:
            if not parallel:
                for phase in self.phases:
                    if phase["status"] == "running" and not phase["parallel"]:
                        phase["status"] = "ok"
                        phase["ended"] = time.time()
            self.phases.append({
                "name": name, "status": "running", "detail": "", "parallel": parallel,
                "started": time.time(), "ended": None,
            })

    def end(self, name: str | None = None, status: str = "ok", detail: str = "") -> None:
        """Close the named phase, or the newest open one."""
        with self._lock:
            for phase in reversed(self.phases):
                if phase["status"] != "running":
                    continue
                if name is None or phase["name"] == name:
                    phase["status"] = status
                    phase["detail"] = detail
                    phase["ended"] = time.time()
                    return

    def note(self, key: str, value: Any) -> None:
        with self._lock:
            self.notes[key] = value

    def stopped_at(self) -> dict[str, Any] | None:
        """The first failed phase, else a phase that never closed."""
        for phase in self.phases:
            if phase["status"] in {"failed", "cancelled", "halted"}:
                return phase
        for phase in self.phases:
            if phase["status"] == "running":
                return phase
        return None

    def close_open(self, status: str, detail: str = "") -> None:
        with self._lock:
            for phase in self.phases:
                if phase["status"] == "running":
                    phase["status"] = status
                    phase["detail"] = phase["detail"] or detail
                    phase["ended"] = time.time()

    def as_dict(self, extra: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        return {
            "runId": self.run_id,
            "startedAt": datetime.fromtimestamp(self.started).isoformat(timespec="seconds"),
            "endedAt": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
            "seconds": int(now - self.started),
            "phases": [
                {
                    "name": p["name"], "status": p["status"], "detail": p["detail"],
                    "seconds": int((p["ended"] or now) - p["started"]), "parallel": p["parallel"],
                }
                for p in self.phases
            ],
            **self.notes,
            **extra,
        }


def get(run_id: str) -> RunSummary:
    with _LOCK:
        if run_id not in _RUNS:
            _RUNS[run_id] = RunSummary(run_id)
        return _RUNS[run_id]


def drop(run_id: str) -> None:
    with _LOCK:
        _RUNS.pop(run_id, None)


def write(
    run_id: str,
    folder: Path,
    book: Logbook,
    *,
    ticket: str,
    verdict: str,
    status: str,
    counts: dict[str, Any] | None,
    issues: list[str],
    costs: dict[str, dict[str, float]],
    error: str = "",
) -> dict[str, Any]:
    """Append the summary block to run.log and write summary.json. Returns the summary."""
    summary = get(run_id)
    if error:
        summary.close_open("failed", error)
    else:
        summary.close_open("ok" if verdict != "HALTED" else "halted")
    stop = summary.stopped_at()
    total_cost = sum(float(row.get("cost") or 0) for row in costs.values())
    data = summary.as_dict({
        "ticket": ticket, "verdict": verdict, "status": status,
        "tests": counts or {}, "openIssues": issues, "cost": round(total_cost, 4),
        "costByPhase": {name: round(float(row.get("cost") or 0), 4) for name, row in costs.items()},
        "stoppedAt": ({"phase": stop["name"], "status": stop["status"], "detail": stop["detail"]} if stop else None),
    })
    lines = ["── run summary"]
    lines.append(f"  {ticket or run_id}  run {run_id}  verdict {verdict}  status {status}  took {_span(data['seconds'])}{f'  cost ${total_cost:.2f}' if costs else ''}")
    for phase in data["phases"]:
        mark = "∥ " if phase["parallel"] else "  "
        detail = f"  {phase['detail']}" if phase["detail"] else ""
        lines.append(f"  {mark}{phase['name'][:24]:<24} {phase['status']:<10} {_span(phase['seconds']):>8}{detail}"[:240])
    if stop:
        lines.append(f"  stopped at: {stop['name']} ({stop['status']}){'  ' + stop['detail'] if stop['detail'] else ''}"[:240])
    else:
        lines.append("  stopped at: nowhere, every phase finished")
    if counts:
        lines.append(
            f"  tests: passed {counts.get('passed', 0)}  failed {counts.get('failed', 0)}  "
            f"skipped {counts.get('skipped', 0)}  flaky {counts.get('flaky', 0)}"
        )
    for key, label in (("bugs", "bugs filed"), ("findings", "API findings"), ("hypotheses", "hypotheses"),
                       ("ux", "UX audit"), ("promote", "promote"), ("affected", "affected E2E cases"),
                       ("deployment", "deployment"), ("assertions", "heal assertion edits"), ("signals", "runtime signals")):
        if key in data and data[key] not in (None, "", []):
            lines.append(f"  {label}: {data[key]}"[:240])
    if costs:
        parts = ", ".join(f"{name} ${float(row.get('cost') or 0):.2f}" for name, row in costs.items())
        lines.append(f"  cost: ${total_cost:.2f}  ({parts})"[:240])
    for issue in issues[:6]:
        lines.append(f"  open: {issue}"[:240])
    if len(issues) > 6:
        lines.append(f"  open: +{len(issues) - 6} more in report.md")
    for line in lines:
        book.line(line)
    (folder / "summary.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    drop(run_id)
    return data
