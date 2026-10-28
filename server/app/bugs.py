"""Render product bugs into the run's bugs.md record."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TC_ID = re.compile(r"TC-[A-Za-z0-9-]+")
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
def publish_bugs(
    folder: Path,
    *,
    ticket: str,
    run_id: str,
    url: str,
    build: str,
    failed: int,
    triage: dict[str, Any],
    still_failing: list[dict[str, str]],
    when: str | None = None,
    cycle: int = 1,
) -> bool:
    """Write bugs.md when a product failure remains. Skip and deprecated cases are left out."""
    if failed <= 0:
        return False
    bugs = collect_bugs(triage, still_failing)
    if not bugs:
        return False
    text = render_bugs(
        bugs,
        ticket=ticket or run_id,
        url=url,
        build=build or "unknown",
        when=when or datetime.now(timezone.utc).date().isoformat(),
        cycle=str(cycle),
    )
    (folder / "bugs.md").write_text(text, encoding="utf-8")
    return True


def latest_triage(folder: Path) -> tuple[dict[str, Any], int]:
    files = sorted(folder.glob("triage-*.json"))
    if files:
        match = re.search(r"triage-(\d+)", files[-1].name)
        cycle = int(match.group(1)) if match else 1
        return _read_json(files[-1]), cycle
    path = folder / "triage.json"
    if path.is_file():
        return _read_json(path), 1
    return {}, 1


def collect_bugs(triage: dict[str, Any], still_failing: list[dict[str, str]] | None = None) -> list[dict[str, Any]]:
    explicit = [item for item in (triage.get("bugs") or []) if isinstance(item, dict) and not _is_skipped(item)]
    if explicit:
        return explicit
    filed: list[dict[str, Any]] = []
    spec_titles: set[str] = set()
    for item in triage.get("failures") or []:
        if not isinstance(item, dict) or _is_skipped(item):
            continue
        if item.get("class") == "spec":
            spec_titles.add(str(item.get("title") or item.get("test") or ""))
            continue
        if item.get("class") == "bug":
            filed.append(item)
    if filed:
        return filed
    fallback: list[dict[str, Any]] = []
    for item in still_failing or []:
        title = str(item.get("title") or "")
        if not title or title in spec_titles or _is_skipped(item):
            continue
        test_id = _tc_from_title(title)
        area = _area_from_path(str(item.get("file") or ""))
        error = str(item.get("error") or "The test failed.")
        fallback.append({
            "area": area,
            "failure": title,
            "severity": "Medium",
            "severityReason": "Unclassified failure. Medium until the impact is confirmed.",
            "description": "Playwright reported this test as failed and the healer did not classify it as spec drift. The observed outcome does not match the expected result.",
            "affectedTests": [test_id],
            "expected": "The assertion in this test passes.",
            "actual": error,
            "rootCause": "Unknown — requires investigation",
            "evidence": [{"test": test_id, "step": 1, "detail": error}],
            "labels": [area.lower()],
        })
    return fallback


def render_bugs(
    bugs: list[dict[str, Any]],
    *,
    ticket: str,
    url: str,
    build: str,
    when: str,
    cycle: str,
) -> str:
    blocks = [
        _render_one(bug, ticket=ticket, url=url, build=build, when=when, cycle=cycle)
        for bug in bugs
        if isinstance(bug, dict) and not _is_skipped(bug)
    ]
    return "\n\n---\n\n".join(blocks).rstrip() + "\n"


def _render_one(
    bug: dict[str, Any],
    *,
    ticket: str,
    url: str,
    build: str,
    when: str,
    cycle: str,
) -> str:
    cases = _cases(bug)
    severity, priority = _severity(bug)
    title = _bug_title(bug, ticket)
    description = _description(bug, title)
    expected = str(bug.get("expected") or "The behavior asserted by the affected test cases.").strip()
    actual = str(bug.get("actual") or bug.get("error") or "The test failed.").strip()
    cause = str(bug.get("rootCause") or bug.get("root_cause") or "Unknown — requires investigation").strip()
    env_url = str(bug.get("url") or url).strip()
    env_build = str(bug.get("build") or build or "unknown").strip() or "unknown"
    lines = [
        _row("Title", title),
        _row("Type", "Bug"),
        _row("Severity", severity),
        _row("Priority", priority),
        "Environment:",
        f"  URL:     {env_url}",
        f"  Build:   {env_build}",
        f"  Date:    {when}",
        "Description:",
        *[f"  {part}" for part in description],
        "Steps to Reproduce:",
    ]
    for index, step in enumerate(_steps(bug, env_url), start=1):
        lines.append(f"  {index}. {step}")
    lines.extend([
        "Expected Result:",
        f"  {expected}",
        "Actual Result:",
        f"  {actual}",
        "Root Cause:",
        f"  {cause}",
        "Evidence:",
    ])
    for item in _evidence(bug, cases, actual):
        lines.append(f"  - {item}")
    lines.append(_row("Labels", _labels(bug, cases)))
    return "\n".join(lines)


def _cases(bug: dict[str, Any]) -> list[dict[str, str]]:
    raw = bug.get("affectedTests") or bug.get("affected_tests") or []
    if isinstance(raw, str):
        raw = [part.strip() for part in raw.split(",") if part.strip()]
    cases: list[dict[str, str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                cases.append({
                    "id": _tc_from_title(item) if _TC_ID.search(item) else item.strip(),
                    "suite": _suite_label(str(bug.get("suite") or "")),
                    "title": str(bug.get("failure") or bug.get("title") or item).strip(),
                    "note": "",
                })
            elif isinstance(item, dict):
                label = str(item.get("id") or item.get("test") or item.get("testId") or "").strip()
                cases.append({
                    "id": label or "TC",
                    "suite": _suite_label(str(item.get("suite") or bug.get("suite") or "")),
                    "title": str(item.get("title") or bug.get("failure") or label).strip(),
                    "note": str(item.get("note") or item.get("detail") or "").strip(),
                })
    if cases:
        return cases
    blob = f"{bug.get('testId') or ''} {bug.get('test') or ''} {bug.get('title') or ''}"
    found = _TC_ID.search(blob)
    return [{
        "id": found.group(0) if found else "TC",
        "suite": _suite_label(str(bug.get("suite") or "")),
        "title": str(bug.get("failure") or bug.get("title") or "failure").strip(),
        "note": "",
    }]


def _evidence(bug: dict[str, Any], cases: list[dict[str, str]], actual: str) -> list[str]:
    raw = bug.get("evidence") or []
    lines: list[str] = []
    if isinstance(raw, str) and raw.strip():
        lines.append(raw.strip())
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                lines.append(item.strip())
            elif isinstance(item, dict):
                test = str(item.get("test") or item.get("id") or cases[0]["id"])
                step = item.get("step") or item.get("stepN") or 1
                detail = str(item.get("detail") or item.get("note") or "see playwright/output.log").strip()
                lines.append(f"[{test} step {step}]: {detail}")
    if lines:
        return lines
    return [f"[{cases[0]['id']} step 1]: {actual}"]


def _steps(bug: dict[str, Any], url: str) -> list[str]:
    raw = bug.get("steps") or bug.get("repro") or []
    if isinstance(raw, str):
        raw = [line.strip() for line in raw.splitlines() if line.strip()]
    steps = []
    if isinstance(raw, list):
        for item in raw:
            text = re.sub(r"^\d+\.\s*", "", str(item).strip())
            if text:
                steps.append(text)
    if steps:
        return steps
    role = str(bug.get("role") or "the signed-in persona")
    return [
        f"Navigate to {url} as {role}",
        "Repeat the actions in the affected test",
        "Observe the actual result below",
    ]


def _description(bug: dict[str, Any], title: str) -> list[str]:
    text = " ".join(str(bug.get("description") or "").split())
    reason = " ".join(str(bug.get("severityReason") or bug.get("severity_reason") or "").split())
    sentences = [part for part in _sentences(text) if part and part != title]
    if reason and reason != title and reason not in text:
        if not reason.endswith((".", "!", "?")):
            reason += "."
        sentences.append(reason)
    if not sentences:
        sentences = [
            "The product did not produce the result this test asserts.",
            "The user or the system sees the actual result below.",
        ]
    return sentences[:3]


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    return parts or [text]


def _bug_title(bug: dict[str, Any], ticket: str) -> str:
    area = str(bug.get("area") or "App").strip()
    failure = str(bug.get("failure") or "").strip()
    context = str(bug.get("context") or ticket or "ticket").strip()
    if failure:
        return f"{area} — {failure} — {context}"
    raw = str(bug.get("title") or "failure").strip()
    if raw.count("—") >= 2:
        return raw
    return f"{area} — {raw} — {context}"


def _severity(bug: dict[str, Any]) -> tuple[str, str]:
    raw = str(bug.get("severity") or bug.get("priority") or "medium").strip().lower()
    return _SEVERITY.get(raw, ("Medium", "P2"))


def _labels(bug: dict[str, Any], cases: list[dict[str, str]]) -> str:
    raw = bug.get("labels") or []
    if isinstance(raw, str):
        parts = raw.replace(",", " ").split()
    else:
        parts = []
        for item in raw:
            parts.extend(str(item).replace(",", " ").split())
    tokens: list[str] = []
    for token in parts:
        cleaned = token.strip().lower()
        if cleaned and cleaned not in tokens:
            tokens.append(cleaned)
    if any(case.get("suite", "").lower() == "regression" for case in cases) and "regression" not in tokens:
        tokens.append("regression")
    if "qa-generated" not in tokens:
        tokens.append("qa-generated")
    return " ".join(tokens)


def _suite_label(value: str) -> str:
    lowered = value.strip().lower()
    labels = {"bvt": "BVT", "smoke": "Smoke", "sanity": "Sanity", "regression": "Regression"}
    if lowered in labels:
        return labels[lowered]
    if value.strip() in labels.values():
        return value.strip()
    return value.strip()


def _tc_from_title(title: str) -> str:
    found = _TC_ID.search(title)
    return found.group(0) if found else title.strip() or "TC"


def _area_from_path(path: str) -> str:
    lowered = path.lower()
    if "document editing" in lowered or "docedit" in lowered:
        return "Documents"
    if "asset crud" in lowered or "assets-crud" in lowered:
        return "Assets"
    if "search" in lowered:
        return "Search"
    name = Path(path).name if path else "App"
    return name or "App"


def _is_skipped(item: dict[str, Any]) -> bool:
    status = str(item.get("status") or "").lower()
    action = str(item.get("action") or "").lower()
    title = str(item.get("title") or "").lower()
    if status in {"skip", "skipped", "deprecated"} or action in {"skip", "skipped", "deprecated"}:
        return True
    if "deprecated" in title or item.get("deprecated") is True:
        return True
    return False


def _row(label: str, value: str) -> str:
    return f"{label + ':':<15} {value}"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, list):
        return {"failures": data}
    return data if isinstance(data, dict) else {}
