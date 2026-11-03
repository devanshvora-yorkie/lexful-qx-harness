"""Score the UX audit from the auditor's JSON, render ux-report.html with the kit's generator, and check it.

The check is the kit's scripts/check_report_contract.py against .agents/ux/report-contract.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "scripts" / "generate_ux_report.py"
CONTRACT_CHECK = ROOT / "scripts" / "check_report_contract.py"

PENALTY = {"S0": 40, "S1": 25, "S2": 10, "S3": 3, "O": 0}
SEVERITY_ORDER = ("S0", "S1", "S2", "S3", "O")


def read_findings(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        combined: list[dict[str, Any]] = []
        for key in ("findings", "defects", "observations", "failures"):
            rows = data.get(key)
            if isinstance(rows, list):
                combined.extend(item for item in rows if isinstance(item, dict))
        if combined:
            return combined
    return []


def read_scorecard(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def score_findings(findings: list[dict[str, Any]]) -> tuple[dict[str, int], int, str]:
    counts = {key: 0 for key in SEVERITY_ORDER}
    for item in _unique_findings(findings):
        severity = _scored_severity(item)
        counts[severity] += 1
    deducted = sum(counts[key] * PENALTY[key] for key in SEVERITY_ORDER)
    score = max(0, 100 - deducted)
    if counts["S0"] or counts["S1"]:
        # The report contract's word for a release-blocking S0/S1 finding.
        verdict = "BLOCKED"
    elif counts["S2"] or counts["S3"]:
        verdict = "PASS WITH ADVISORIES"
    else:
        verdict = "PASS"
    return counts, score, verdict


def _from_card(card: dict[str, Any]) -> tuple[dict[str, int], int, str]:
    raw = card.get("counts") if isinstance(card.get("counts"), dict) else card
    counts = {key: int(raw.get(key) or 0) for key in SEVERITY_ORDER}
    return score_findings(
        [{"severity": key} for key, count in counts.items() for _ in range(count)]
    )


def rubric(counts: dict[str, int], score: int, verdict: str) -> str:
    parts = [
        f"{counts[key]} x {key} (-{counts[key] * PENALTY[key]})"
        for key in SEVERITY_ORDER
        if counts[key]
    ]
    detail = ", ".join(parts) if parts else "no findings"
    return (
        f"Start at 100. Subtract S0 40, S1 25, S2 10, S3 3, O 0. "
        f"{detail} = {score}. Verdict: {verdict}."
    )


def _resolved(item: dict[str, Any]) -> bool:
    return str(item.get("status") or "").strip().lower() in {"resolved", "verified fixed"}


def _scored_severity(item: dict[str, Any]) -> str:
    """A finding the stakeholders already fixed is verified, not scored."""
    severity = str(item.get("severity") or "O").strip().upper()
    if _resolved(item) or severity not in SEVERITY_ORDER:
        return "O"
    return severity


def write_ux_report(folder: Path, ticket: str) -> Path | None:
    """Score the findings, normalise the JSON, and let the kit's generator write ux-report.html.

    The auditor writes only ux-findings.json and ux-scorecard.json. The generator reads
    deductionPoints, totalDeduction, ticket and date from them.
    """
    findings_path = folder / "ux-findings.json"
    card_path = folder / "ux-scorecard.json"
    if not findings_path.is_file() and not card_path.is_file():
        return None
    findings = _unique_findings(read_findings(findings_path))
    previous = read_scorecard(card_path)
    if findings_path.is_file():
        counts, score, verdict = score_findings(findings)
    else:
        counts, score, verdict = _from_card(previous)
    for item in findings:
        item["deductionPoints"] = PENALTY[_scored_severity(item)]
    if findings_path.is_file():
        findings_path.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
    card = {
        "ticket": ticket or folder.name,
        "date": _run_date(folder),
        "score": score,
        "totalDeduction": 100 - score,
        "counts": counts,
        "verdict": verdict,
        "rubric": rubric(counts, score, verdict),
    }
    # What the auditor knows and the server does not: the journey scopes the report's checks matrix.
    for key in ("envNotes", "journey", "generatedAt"):
        if previous.get(key):
            card[key] = previous[key]
    card_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    report = folder / "ux-report.html"
    report.unlink(missing_ok=True)
    try:
        subprocess.run([sys.executable, str(GENERATOR), str(folder)], check=True, capture_output=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    return report if report.is_file() else None


def check_ux_report(folder: Path) -> list[str]:
    """Contract failures of the rendered ux-report.html, one line each. [] when it passes or was not rendered."""
    if not (folder / "ux-report.html").is_file():
        return []
    try:
        done = subprocess.run(
            [sys.executable, str(CONTRACT_CHECK), str(folder), "--json"],
            capture_output=True, text=True, timeout=120,
        )
        result = json.loads(done.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return ["the report contract check could not run"]
    if not isinstance(result, dict):
        return ["the report contract check returned no result"]
    failures = [item for item in result.get("failures") or [] if isinstance(item, dict)]
    lines = [f"{item.get('rule')}: {item.get('message')}" for item in failures]
    if not lines and done.returncode != 0:
        lines = [f"the report contract check exited {done.returncode}"]
    return lines


def _unique_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One deduction per check, route, and title. A second copy of the same defect does not score again."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for item in findings:
        check = str(item.get("checkId") or "").strip().lower()
        route = str(item.get("route") or item.get("screen") or item.get("journey") or "").strip().lower()
        title = str(item.get("title") or "").strip().lower()
        if check or title:
            key = (check, route, title)
            if key in seen:
                continue
            seen.add(key)
        unique.append(item)
    return unique


def _run_date(folder: Path) -> str:
    name = folder.name
    if len(name) >= 10 and name[4] == "-" and name[7] == "-":
        return name[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
