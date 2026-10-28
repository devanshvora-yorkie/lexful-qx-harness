"""Render the UX audit HTML report from the auditor's JSON."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / ".agents" / "skills" / "lexful-ux-audit-gate" / "audit-preview.html"
GAUGE = {"PASS": "#3f6212", "ADVISORY-FAIL": "#b45309", "BLOCKING-FAIL": "#9f1239"}

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
        for key in ("findings", "failures"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
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
    for item in findings:
        severity = str(item.get("severity") or "O").strip().upper()
        if severity not in counts:
            severity = "O"
        counts[severity] += 1
    deducted = sum(counts[key] * PENALTY[key] for key in SEVERITY_ORDER)
    score = max(0, 100 - deducted)
    if counts["S0"] or counts["S1"]:
        verdict = "BLOCKING-FAIL"
    elif counts["S2"] or counts["S3"]:
        verdict = "ADVISORY-FAIL"
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


def write_ux_report(folder: Path, ticket: str) -> Path | None:
    findings_path = folder / "ux-findings.json"
    card_path = folder / "ux-scorecard.json"
    if not findings_path.is_file() and not card_path.is_file():
        return None
    findings = read_findings(findings_path)
    previous = read_scorecard(card_path)
    if findings_path.is_file():
        counts, score, verdict = score_findings(findings)
    else:
        counts, score, verdict = _from_card(previous)
    card = {
        "score": score,
        "counts": counts,
        "verdict": verdict,
        "rubric": rubric(counts, score, verdict),
    }
    notes = previous.get("envNotes")
    if isinstance(notes, list) and notes:
        card["envNotes"] = notes
    card_path.write_text(json.dumps(card, indent=2) + "\n", encoding="utf-8")
    report = folder / "ux-report.html"
    report.write_text(
        render_html(
            ticket=ticket or folder.name,
            run_id=folder.name,
            run_date=_run_date(folder),
            score=score,
            verdict=verdict,
            counts=counts,
            findings=_ordered(findings),
            notes=card.get("envNotes") or [],
        ),
        encoding="utf-8",
    )
    return report


def _paragraphs(text: str) -> str:
    parts = re.split(r"(?<=[A-Za-z]{2}[.!?])\s+(?=[A-Z])", text.strip())
    return "".join(f"<p>{html.escape(part)}</p>" for part in parts if part.strip())


def _fill(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key in sorted(values, key=len, reverse=True):
        rendered = rendered.replace(f"__{key}__", values[key])
    return rendered


def render_html(
    *,
    ticket: str,
    run_id: str,
    run_date: str,
    score: int,
    verdict: str,
    counts: dict[str, int],
    findings: list[dict[str, Any]],
    notes: list[Any],
) -> str:
    numbered = list(enumerate(findings, start=1))
    defects = [(number, item) for number, item in numbered if _severity(item) != "O"]
    observations = [(number, item) for number, item in numbered if _severity(item) == "O"]
    defect_cards = "\n".join(_card(item, number) for number, item in defects) or (
        '<p class="empty">No defects on the screens this ticket touches.</p>'
    )
    observation_html = ""
    if observations:
        observation_cards = "\n".join(_card(item, number) for number, item in observations)
        observation_html = (
            '<section class="observations-section">'
            "<h2>Observations and design suggestions</h2>"
            "<p>These work as intended. They do not change the score or the release verdict.</p>"
            f"{observation_cards}</section>"
        )
    count_items = "".join(
        f'<li class="count-{html.escape(key)}"><span>{html.escape(key)}</span><strong>{counts.get(key, 0)}</strong></li>'
        for key in SEVERITY_ORDER
    )
    note_html = ""
    if notes:
        items = "".join(f"<li>{html.escape(str(note))}</li>" for note in notes)
        note_html = f"<details class='notes'><summary>Run notes</summary><ul>{items}</ul></details>"
    verdict_class = verdict.lower().replace(" ", "-")
    template = TEMPLATE.read_text(encoding="utf-8")
    return _fill(template, {
        "DATE": html.escape(run_date),
        "RUN_ID": html.escape(run_id),
        "TARGET": html.escape(ticket),
        "SCORE": str(score),
        "GAUGE": GAUGE.get(verdict, "#44403c"),
        "VERDICT": html.escape(verdict),
        "VERDICT_CLASS": html.escape(verdict_class),
        "COUNTS": count_items,
        "KICKER": html.escape(_kicker(verdict)),
        "DEFECT_INDEX": _index(defects),
        "OBSERVATION_INDEX": _index(observations),
        "DEFECTS": defect_cards,
        "OBSERVATIONS": observation_html,
        "NOTES": note_html,
    })


def _ordered(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {key: index for index, key in enumerate(SEVERITY_ORDER)}
    return sorted(
        findings,
        key=lambda item: rank.get(str(item.get("severity") or "O").strip().upper(), len(rank)),
    )


def _severity(item: dict[str, Any]) -> str:
    severity = str(item.get("severity") or "O").strip().upper()
    return severity if severity in PENALTY else "O"


def _anchor(item: dict[str, Any], number: int) -> str:
    raw = str(item.get("id") or f"finding-{number}")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "-", raw).strip("-")
    return safe or f"finding-{number}"


def _kicker(verdict: str) -> str:
    if verdict == "BLOCKING-FAIL":
        return "An S0 or S1 finding blocks release. Score starts at 100. S0 −40, S1 −25, S2 −10, S3 −3."
    if verdict == "ADVISORY-FAIL":
        return "No S0 or S1, so this does not block release. S2 and S3 are warnings. Score starts at 100. S0 −40, S1 −25, S2 −10, S3 −3."
    return "No scored findings. Score starts at 100. Observations do not change the score."


def _index(rows: list[tuple[int, dict[str, Any]]]) -> str:
    if not rows:
        return '<p class="empty">None</p>'
    return "\n".join(_index_link(item, number) for number, item in rows)


def _index_link(item: dict[str, Any], number: int) -> str:
    title = str(item.get("title") or item.get("issue") or "Untitled finding")
    severity = _severity(item)
    return (
        f'<a href="#{html.escape(_anchor(item, number))}">'
        f"{html.escape(severity)} · {html.escape(title)}</a>"
    )


def _card(item: dict[str, Any], number: int) -> str:
    severity = _severity(item)
    title = str(item.get("title") or item.get("issue") or "Untitled finding")
    check = str(item.get("checkId") or item.get("id") or "")
    lens = str(item.get("lens") or "")
    confidence = str(item.get("confidence") or "")
    pattern = str(item.get("relatedPattern") or "")
    kicker = " · ".join(part for part in (check, lens, pattern, confidence) if part)
    observed = _paragraphs(str(item.get("evidence") or ""))
    solution = _paragraphs(str(item.get("solution") or ""))
    extra = []
    implementation = str(item.get("implementationShadcn") or "").strip()
    rationale = str(item.get("fluentRationale") or "").strip()
    refs = item.get("qaRefs") or []
    if isinstance(refs, list):
        ref_text = ", ".join(str(ref) for ref in refs if ref)
    else:
        ref_text = str(refs).strip()
    if implementation:
        extra.append(("Implementation", implementation))
    if rationale:
        extra.append(("Design rationale", rationale))
    if ref_text:
        extra.append(("QA references", ref_text))
    extra_html = ""
    if extra:
        rows = "".join(
            f"<div><dt>{html.escape(label)}</dt><dd>{html.escape(text)}</dd></div>"
            for label, text in extra
        )
        extra_html = f"<dl class='plan-extra'>{rows}</dl>"
    return (
        f'<article class="finding-card severity-{html.escape(severity)}" id="{html.escape(_anchor(item, number))}">'
        f'<header class="finding-head"><span class="badge">{html.escape(severity)}</span>'
        f'<span class="card-kicker">{html.escape(kicker)}</span></header>'
        f'<h2 class="finding-title">{html.escape(title)}</h2>'
        f'<section class="section-box"><h3>Observed defect</h3>'
        f'<div class="section-box-content">{observed}</div></section>'
        f'<section class="section-box plan"><h3>Design &amp; Remediation Plan</h3>'
        f'<div class="section-box-content">{solution}{extra_html}</div></section>'
        f"</article>"
    )


def _run_date(folder: Path) -> str:
    name = folder.name
    if len(name) >= 10 and name[4] == "-" and name[7] == "-":
        return name[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
