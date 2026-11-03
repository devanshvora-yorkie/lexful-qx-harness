"""Product bugs a run files.

The agent describes each defect with the fields the skill names (`triage.json` `bugs[]` after a heal,
`api-findings.json` `findings[]` from probes). The server does not write bug text. It normalises those
objects into one record per defect, attaches the verifier's screenshots, and keeps them in
`bugs.json`. `bugs.md` is rendered from `bugs.json`, one ticket-ready markdown block per bug, so the
same text can later become the description of a new Linear issue.

A failure the healer did not describe in `bugs[]` is not filed: it stays an open issue of the run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import evidence

_SEVERITY = {
    "critical": ("Critical", "P0"),
    "p0": ("Critical", "P0"),
    "high": ("High", "P1"),
    "p1": ("High", "P1"),
    "medium": ("Medium", "P2"),
    "p2": ("Medium", "P2"),
    "low": ("Low", "P3"),
    "p3": ("Low", "P3"),
}
_SEVERITY_ORDER = ("Critical", "High", "Medium", "Low")
# Fields a triage bug that cites `finding: <id>` takes from that finding when it left them blank.
_FROM_FINDING = ("area", "failure", "title", "severity", "severityReason", "description", "persona",
                 "preconditions", "steps", "expected", "actual", "rootCause", "evidence", "url")


# ── filing ───────────────────────────────────────────────────────────────────────────────────


def publish_bugs(
    folder: Path,
    *,
    ticket: str,
    run_id: str,
    url: str,
    build: str,
    failed: int,
    triage: dict[str, Any],
    when: str | None = None,
) -> bool:
    """File the healer's `bugs[]` when a failure remains. Returns True when at least one was filed."""
    if failed <= 0:
        return False
    found = collect_bugs(triage)
    if not found:
        return False
    listed = [b for b in triage.get("bugs") or [] if isinstance(b, dict)]
    findings = {
        str(item.get("id")): item
        for item in _read_json(folder / "api-findings.json").get("findings") or []
        if isinstance(item, dict) and item.get("id")
    }
    records = []
    for bug in found:
        merged = _with_finding(bug, findings)
        shots = evidence.screenshots_for(folder, f"bug:{listed.index(bug) + 1}", merged)
        if merged.get("finding"):
            cited = evidence.screenshots_for(folder, f"finding:{merged['finding']}", {})
            shots = list(dict.fromkeys([*cited, *shots]))[: evidence.MAX_PER_BUG]
        records.append(record(merged, source="triage", ticket=ticket or run_id, url=url, build=build,
                              when=when, screenshots=shots))
    _save(folder, records)
    return True


def publish_findings(
    folder: Path,
    *,
    ticket: str,
    run_id: str,
    url: str,
    build: str,
    when: str | None = None,
) -> int:
    """File the findings in api-findings.json that have evidence and no triage bug citing them.

    Findings come from probes and the hypothesis hunt, not from a failed test, so they are filed
    even when every test passed.
    """
    triage, _ = latest_triage(folder)
    claimed = {str(b.get("finding")) for b in triage.get("bugs") or [] if isinstance(b, dict) and b.get("finding")}
    records = []
    for item in _read_json(folder / "api-findings.json").get("findings") or []:
        if not isinstance(item, dict) or _is_skipped(item) or str(item.get("id") or "") in claimed:
            continue
        if not (item.get("evidence") and item.get("expected") and item.get("actual")):
            continue
        shots = evidence.screenshots_for(folder, f"finding:{item.get('id')}", item)
        records.append(record(item, source="finding", ticket=ticket or run_id, url=url, build=build,
                              when=when, screenshots=shots, confidence="suspected"))
    if records:
        _save(folder, records)
    return len(records)


def collect_bugs(triage: dict[str, Any]) -> list[dict[str, Any]]:
    """The healer's `bugs[]`, without skipped ones and without any whose tests were all classed `gap`."""
    gaps = [str(item.get("title") or item.get("test") or "") for item in triage.get("failures") or []
            if isinstance(item, dict) and failure_kind(item) == "gap"]
    return [
        item for item in triage.get("bugs") or []
        if isinstance(item, dict) and not _is_skipped(item) and not _covered_by_gap(item, gaps)
    ]


def _with_finding(bug: dict[str, Any], findings: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A triage bug that cites `finding: <id>` takes the finding's detail for what it left blank."""
    item = findings.get(str(bug.get("finding") or ""))
    if not item:
        return bug
    out = dict(bug)
    for key in _FROM_FINDING:
        if not out.get(key) and item.get(key):
            out[key] = item[key]
    if not out.get("confidence") and item.get("confidence"):
        out["confidence"] = item["confidence"]
    return out


def _save(folder: Path, records: list[dict[str, Any]]) -> None:
    """Append to bugs.json and render bugs.md from the whole file."""
    path = folder / "bugs.json"
    existing = [b for b in _read_json(path).get("bugs") or [] if isinstance(b, dict)]
    everything = [*existing, *records]
    path.write_text(json.dumps({"bugs": everything}, indent=2) + "\n", encoding="utf-8")
    (folder / "bugs.md").write_text(render_bugs(everything), encoding="utf-8")


# ── the record ───────────────────────────────────────────────────────────────────────────────


def record(
    bug: dict[str, Any],
    *,
    source: str,
    ticket: str,
    url: str,
    build: str,
    when: str | None = None,
    screenshots: list[str] | None = None,
    confidence: str = "",
) -> dict[str, Any]:
    """One bug in the shape bugs.json keeps and a Linear issue will be created from."""
    severity, priority = severity_of(bug)
    return {
        "source": source,
        "id": str(bug.get("id") or bug.get("finding") or ""),
        "title": title_of(bug),
        "area": _text(bug.get("area")),
        "severity": severity,
        "priority": priority,
        "confidence": (_text(bug.get("confidence")).lower() or confidence),
        "description": _text(bug.get("description")),
        "severityReason": _text(bug.get("severityReason") or bug.get("severity_reason")),
        "persona": _text(bug.get("persona") or bug.get("role")),
        "preconditions": _lines(bug.get("preconditions")),
        "steps": _steps(bug.get("steps") or bug.get("repro")),
        "expected": _text(bug.get("expected")),
        "actual": _text(bug.get("actual")),
        "rootCause": _text(bug.get("rootCause") or bug.get("root_cause")),
        "evidence": _evidence(bug.get("evidence")),
        "verifier": _text(bug.get("verifier")),
        "screenshots": [str(shot) for shot in screenshots or []],
        "affectedTests": _tests(bug.get("affectedTests") or bug.get("affected_tests")),
        "ticket": ticket,
        "url": _text(bug.get("url")) or url,
        "build": _text(bug.get("build")) or build or "unknown",
        "date": when or datetime.now(timezone.utc).date().isoformat(),
    }


def title_of(bug: dict[str, Any]) -> str:
    """`<Area>: <what goes wrong>`. The ticket and test ids belong in the body, not the title.

    An area written as `Organization picker: search` reads `Organization picker › search: ...`.
    """
    area = _text(bug.get("area")).replace(": ", " › ")
    failure = _text(bug.get("failure") or bug.get("title")) or "Unnamed defect"
    if not area or failure.lower().startswith(area.lower()):
        return failure
    return f"{area}: {failure}"


def severity_of(bug: dict[str, Any]) -> tuple[str, str]:
    """The severity decides the priority: Critical P0, High P1, Medium P2, Low P3."""
    raw = _text(bug.get("severity") or bug.get("priority") or "medium").lower()
    return _SEVERITY.get(raw, ("Medium", "P2"))


def severity_rank(record_: dict[str, Any]) -> int:
    name = str(record_.get("severity") or "Medium")
    return _SEVERITY_ORDER.index(name) if name in _SEVERITY_ORDER else len(_SEVERITY_ORDER)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []


def _steps(value: Any) -> list[str]:
    """Steps as the agent wrote them, without a leading `1.` it may have typed itself."""
    steps = []
    for line in _lines(value):
        number, dot, rest = line.partition(". ")
        steps.append(rest.strip() if dot and number.isdigit() else line)
    return [step for step in steps if step]


def _evidence(value: Any) -> list[str]:
    if isinstance(value, (str, dict)):
        value = [value]
    out: list[str] = []
    for item in value or []:
        if isinstance(item, dict):
            where = " ".join(str(item.get(key)) for key in ("test", "step") if item.get(key))
            detail = _text(item.get("detail") or item.get("note"))
            if detail:
                out.append(f"{where}: {detail}" if where else detail)
        elif _text(item):
            out.append(_text(item))
    return out


def _tests(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.split(",")
    out: list[str] = []
    for item in value or []:
        name = _text(item.get("id") or item.get("title") or item.get("test")) if isinstance(item, dict) else _text(item)
        if name and name not in out:
            out.append(name)
    return out


# ── rendering ────────────────────────────────────────────────────────────────────────────────


def render_bugs(records: list[dict[str, Any]], prefix: str = "") -> str:
    """bugs.md: every bug, most severe first, one ticket-ready block each."""
    ordered = sorted(records, key=severity_rank)
    return "\n\n---\n\n".join(render_bug(item, prefix) for item in ordered).rstrip() + "\n"


def render_bug(bug: dict[str, Any], prefix: str = "") -> str:
    """The description of one bug ticket. `prefix` turns screenshot paths into links from elsewhere."""
    confidence = bug.get("confidence") or "not stated"
    tests = ", ".join(bug.get("affectedTests") or []) or "none"
    found_by = f"{bug.get('ticket')} · {tests}".replace("|", "/")
    lines = [
        f"## {bug.get('title')}",
        "",
        "| Severity | Priority | Confidence | Found by |",
        "|---|---|---|---|",
        f"| {bug.get('severity')} | {bug.get('priority')} | {confidence} | {found_by} |",
        "",
    ]
    if bug.get("description"):
        lines.extend(["**What happens**", "", bug["description"], ""])
    environment = [f"URL: {bug.get('url')}", f"Build: {bug.get('build')}", f"Date: {bug.get('date')}"]
    if bug.get("persona"):
        environment.insert(1, f"Signed in as: {bug['persona']}")
    lines.extend(["**Environment**", "", *[f"- {item}" for item in environment], ""])
    if bug.get("preconditions"):
        lines.extend(["**Before you start**", "", *[f"- {item}" for item in bug["preconditions"]], ""])
    lines.append("**Steps to reproduce**")
    lines.append("")
    if bug.get("steps"):
        lines.extend(f"{n}. {step}" for n, step in enumerate(bug["steps"], start=1))
    else:
        lines.append(f"Not recorded by the agent. Replay the affected test: {tests}.")
    lines.append("")
    lines.extend(["**Expected**", "", bug.get("expected") or "Not recorded.", ""])
    lines.extend(["**Actual**", "", bug.get("actual") or "Not recorded.", ""])
    if bug.get("severityReason"):
        lines.extend(["**Why it matters**", "", bug["severityReason"], ""])
    if bug.get("rootCause"):
        lines.extend(["**Likely cause**", "", bug["rootCause"], ""])
    notes = list(bug.get("evidence") or [])
    if bug.get("verifier"):
        notes.append(f"Reproduced by a fresh session: {bug['verifier']}")
    if notes or bug.get("screenshots"):
        lines.extend(["**Evidence**", ""])
        lines.extend(f"- {item}" for item in notes)
        lines.extend(f"- ![{Path(shot).name}]({prefix}{shot})" for shot in bug.get("screenshots") or [])
        lines.append("")
    return "\n".join(lines).rstrip()


# ── triage helpers ───────────────────────────────────────────────────────────────────────────


def latest_triage(folder: Path) -> tuple[dict[str, Any], int]:
    """The newest triage-<n>.json and its n, else triage.json as round 1."""
    rounds = []
    for path in folder.glob("triage-*.json"):
        number = path.stem.removeprefix("triage-")
        if number.isdigit():
            rounds.append((int(number), path))
    if rounds:
        number, path = max(rounds)
        return _read_json(path), number
    path = folder / "triage.json"
    if path.is_file():
        return _read_json(path), 1
    return {}, 1


def triage_files(folder: Path) -> list[Path]:
    """triage-1.json, triage-2.json, ... in round order."""
    rounds = []
    for path in folder.glob("triage-*.json"):
        number = path.stem.removeprefix("triage-")
        if number.isdigit():
            rounds.append((int(number), path))
    return [path for _number, path in sorted(rounds)]


def failure_kind(item: dict[str, Any]) -> str:
    """Healer label. The skill says `class`; models also write `classification`."""
    raw = item.get("class") or item.get("classification") or item.get("kind") or ""
    kind = str(raw).strip().lower()
    return kind if kind in {"spec", "bug", "timing", "gap"} else ""


def same_test(left: str, right: str) -> bool:
    """A test named by its id (`TC-7`) and by its full title (`TC-7: saves`) is the same test."""
    a, b = left.strip().lower(), right.strip().lower()
    if not a or not b:
        return False
    return a == b or a.startswith(b + ":") or b.startswith(a + ":")


def _covered_by_gap(item: dict[str, Any], gaps: list[str]) -> bool:
    if failure_kind(item) == "gap":
        return True
    names = _tests(item.get("affectedTests") or item.get("affected_tests"))
    return bool(names) and all(any(same_test(name, gap) for gap in gaps) for name in names)


def _is_skipped(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    action = str(item.get("action") or "").lower()
    if status in {"skip", "skipped", "deprecated"} or action in {"skip", "skipped", "deprecated"}:
        return True
    return item.get("deprecated") is True


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, list):
        return {"failures": data}
    return data if isinstance(data, dict) else {}
