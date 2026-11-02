"""linear-report.md: one report per ticket run, written for the Linear issue.

It joins the three things a reviewer needs and nothing else: the E2E User Journey run (and its
bugs), the Feature Specific run (and its bugs), and the UI/UX audit (and its findings). Bug
screenshots are in bug-evidence/ beside it, the audit in ux-report.html. Paste the markdown into
Linear and drag the files listed at the end onto the issue. Nothing is sent from here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _span(seconds: Any) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ""
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _counts(result: dict[str, Any]) -> str:
    counts = result.get("test_results") or {}
    if not counts:
        return "not run"
    flaky = f", {counts['flaky']} flaky" if counts.get("flaky") else ""
    return f"{counts.get('passed', 0)} passed, {counts.get('failed', 0)} failed, {counts.get('skipped', 0)} skipped{flaky}"


def _clip(text: Any, n: int = 200) -> str:
    return " ".join(str(text or "").split())[:n].replace("|", "/")


def _bug_section(bugs: list[dict[str, Any]], prefix: str = "") -> list[str]:
    if not bugs:
        return ["No product bug was filed.", ""]
    lines = ["| # | Severity | Bug | Confidence |", "|---|---|---|---|"]
    for index, bug in enumerate(bugs, start=1):
        lines.append(f"| {index} | {bug.get('severity', '')} ({bug.get('priority', '')}) | {_clip(bug.get('title'), 150)} | {bug.get('confidence') or 'n/a'} |")
    lines.append("")
    for index, bug in enumerate(bugs, start=1):
        lines.append(f"**{index}. {_clip(bug.get('title'), 180)}**")
        lines.append("")
        if bug.get("url") or bug.get("build"):
            lines.append(f"- Environment: {bug.get('url', '')}  build {bug.get('build', 'unknown')}")
        steps = bug.get("steps") or []
        if steps:
            lines.append("- Steps:")
            lines.extend(f"  {n}. {_clip(step, 300)}" for n, step in enumerate(steps, start=1))
        if bug.get("expected"):
            lines.append(f"- Expected: {_clip(bug['expected'], 400)}")
        if bug.get("actual"):
            lines.append(f"- Actual: {_clip(bug['actual'], 400)}")
        if bug.get("rootCause"):
            lines.append(f"- Root cause: {_clip(bug['rootCause'], 300)}")
        shots = bug.get("screenshots") or []
        if shots:
            lines.append("- Screenshots: " + ", ".join(f"`{prefix}{shot}`" for shot in shots))
            lines.extend(f"\n  ![{Path(shot).stem}]({prefix}{shot})" for shot in shots)
        else:
            lines.append("- Screenshots: none captured")
        lines.append("")
    return lines


def _e2e_section(folder: Path) -> list[str]:
    e2e = folder / "e2e"
    result = _json(e2e / "qa-result.json")
    lines = ["## 1. E2E User Journey TCs (search, asset crud, document editing)", ""]
    if not result:
        return lines + ["The checked-in suite did not run before this ticket.", ""]
    summary = _json(e2e / "summary.json")
    source = _text(e2e / "source.txt").strip()
    lines.append(f"- Result: **{result.get('verdict', 'unknown')}**, {_counts(result)}")
    if summary.get("seconds"):
        lines.append(f"- Took {_span(summary['seconds'])}, started {summary.get('startedAt', '')}")
    if source:
        lines.append(f"- {source}")
    healed: list[tuple[str, str]] = []
    for path in sorted(e2e.glob("triage-*.json")):
        for item in _json(path).get("failures") or []:
            if isinstance(item, dict) and str(item.get("class") or "").lower() == "spec" and item.get("action") == "patched":
                healed.append((str(item.get("title") or item.get("test") or ""), _clip(item.get("reason"), 220)))
    seen: dict[str, str] = dict(healed)
    if seen:
        lines.append(f"- Updated in place because the app changed: **{len(seen)}** case(s)")
        lines.extend(f"  - {title}: {reason}" for title, reason in list(seen.items())[:12])
    open_issues = result.get("open_issues") or []
    if open_issues:
        lines.append("- Still failing after the heal:")
        lines.extend(f"  - {_clip(issue, 220)}" for issue in open_issues[:10])
        if len(open_issues) > 10:
            lines.append(f"  - +{len(open_issues) - 10} more in e2e/report.md")
    lines.append("")
    lines.append("### E2E bugs")
    lines.append("")
    lines.extend(_bug_section(_json(e2e / "bugs.json").get("bugs") or [], prefix="e2e/"))
    return lines


def _feature_section(folder: Path) -> list[str]:
    result = _json(folder / "qa-result.json")
    lines = ["## 2. Feature Specific TCs", ""]
    lines.append(f"- Result: **{result.get('verdict', 'unknown')}**, {_counts(result)}")
    outcomes = _json(folder / "playwright" / "test-outcomes.json", [])
    if isinstance(outcomes, list) and outcomes:
        lines.extend(["", "| Test | Result |", "|---|---|"])
        lines.extend(f"| {_clip(row.get('title'), 130)} | {row.get('status')} |" for row in outcomes if isinstance(row, dict))
    coverage = _json(folder / "coverage.json")
    if coverage.get("criteria"):
        lines.extend(["", "Acceptance criteria:", ""])
        for item in coverage["criteria"]:
            if not isinstance(item, dict):
                continue
            state = ", ".join(item.get("tests") or []) or (f"gap: {_clip(item['gap'], 140)}" if item.get("gap") else f"n/a: {_clip(item.get('na'), 80)}")
            lines.append(f"- {item.get('ac')}: {state}")
    hypotheses = _json(folder / "hypotheses.json").get("hypotheses") or []
    if hypotheses:
        tried = [h for h in hypotheses if isinstance(h, dict) and h.get("outcome") in {"confirmed", "refuted"}]
        confirmed = [h for h in tried if h.get("outcome") == "confirmed"]
        lines.extend(["", f"Risks tried: {len(tried)} of {len(hypotheses)}, {len(confirmed)} confirmed as bugs."])
    lines.extend(["", "### Feature bugs", ""])
    lines.extend(_bug_section(_json(folder / "bugs.json").get("bugs") or []))
    return lines


def _ux_section(folder: Path) -> list[str]:
    card = _json(folder / "ux-scorecard.json")
    lines = ["## 3. UI/UX audit", ""]
    if not card:
        return lines + ["The UX audit did not run.", ""]
    score = card.get("score")
    counts = card.get("counts") or {}
    lines.append(f"- Verdict: **{card.get('verdict')}**, score {score if score is not None else 'not scored'}")
    if counts:
        lines.append("- Findings: " + ", ".join(f"{key} {counts.get(key, 0)}" for key in ("S0", "S1", "S2", "S3", "O")))
    if card.get("error"):
        lines.append(f"- Audit problem: {_clip(card['error'], 200)}")
    if (folder / "ux-report.html").is_file():
        lines.append("- Full interactive report: `ux-report.html` (attach it)")
    findings = _json(folder / "ux-findings.json", [])
    findings = findings if isinstance(findings, list) else findings.get("findings", [])
    rows = [f for f in findings if isinstance(f, dict) and f.get("severity") in {"S0", "S1", "S2", "S3"} and f.get("status") != "Resolved"]
    if rows:
        lines.extend(["", "| Severity | Finding | Rule | Screenshot |", "|---|---|---|---|"])
        for f in rows:
            lines.append(f"| {f['severity']} | {_clip(f.get('title'), 150)} | {_clip(f.get('checkId'), 40)} | {f.get('screenshot') or ''} |")
    notes = [f for f in findings if isinstance(f, dict) and f.get("severity") == "O"]
    if notes:
        lines.append(f"\n{len(notes)} observation(s) are in the full report.")
    lines.append("")
    return lines


def build(folder: Path, row: dict[str, Any], *, verdict: str, issues: list[str]) -> str:
    ticket = str(row.get("ticket") or folder.name)
    summary = _json(folder / "summary.json")
    pack_deploy = _text(folder / "pr-brief.md").split("Deployment:", 1)
    deployment = pack_deploy[1].splitlines()[0].strip() if len(pack_deploy) > 1 else ""
    cost = summary.get("cost")
    head = [
        f"# {ticket}: QA report",
        "",
        f"**Verdict: {verdict}**",
        "",
        f"- Run: `{row.get('id')}`  {summary.get('startedAt', '')}",
        f"- App: {_json(folder / 'preflight.json').get('appUrl', '')}",
        f"- Deployment: {deployment or 'not checked'}",
    ]
    if summary.get("seconds"):
        head.append(f"- Took {_span(summary['seconds'])}" + (f", cost ${cost:.2f}" if isinstance(cost, (int, float)) else ""))
    feature_bugs = _json(folder / "bugs.json").get("bugs") or []
    e2e_bugs = _json(folder / "e2e" / "bugs.json").get("bugs") or []
    head.extend([
        f"- Bugs filed: {len(e2e_bugs)} from E2E, {len(feature_bugs)} from this ticket",
        "",
    ])
    if issues:
        head.extend(["## Open issues", ""])
        head.extend(f"- {_clip(issue, 240)}" for issue in issues[:10])
        if len(issues) > 10:
            head.append(f"- +{len(issues) - 10} more in report.md")
        head.append("")
    attachments = ["`linear-report.md` (this report)"]
    if (folder / "ux-report.html").is_file():
        attachments.append("`ux-report.html`")
    shots = sorted(p.name for p in (folder / "bug-evidence").glob("*.png")) if (folder / "bug-evidence").is_dir() else []
    shots_e2e = sorted(p.name for p in (folder / "e2e" / "bug-evidence").glob("*.png")) if (folder / "e2e" / "bug-evidence").is_dir() else []
    if shots:
        attachments.append(f"`bug-evidence/` ({len(shots)} screenshot(s))")
    if shots_e2e:
        attachments.append(f"`e2e/bug-evidence/` ({len(shots_e2e)} screenshot(s))")
    tail = ["## Attach to the Linear issue", "", *[f"- {item}" for item in attachments], ""]
    return "\n".join([*head, *_e2e_section(folder), *_feature_section(folder), *_ux_section(folder), *tail])


def write(folder: Path, row: dict[str, Any], *, verdict: str, issues: list[str]) -> Path:
    target = folder / "linear-report.md"
    target.write_text(build(folder, row, verdict=verdict, issues=issues) + "\n", encoding="utf-8")
    return target
