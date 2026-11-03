"""linear-report.md and linear-report.html: the one report of a run.

Both files hold the same content, built from one list of blocks. The markdown is the comment for the
Linear issue the run tested; the HTML opens on its own in a browser and adds the full test list, the
screenshots and links that resolve beside it. Everything comes from files the run already wrote:
manifest.json (the trigger), qa-result.json, playwright/test-outcomes.json (each test, its tags and
its final result), promoted.json, bugs.json, ux-findings.json and ux-scorecard.json. Nothing is sent
from here.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from app.bugs import severity_rank
from app.logbook import plain

TYPES = ("positive", "negative", "edge")
SUITES = ("sanity", "bvt", "smoke", "regression")
TRIGGERS = {
    "ticket": "Ticket",
    "pr": "Pull request",
    "uat-deploy": "UAT deployment",
    "e2e": "E2E User Journey TCs, started on their own",
    "manual": "Manual run",
}


def _json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if default is None else default


def _span(seconds: Any) -> str:
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ""
    hours, rest = divmod(total, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def _clip(text: Any, n: int = 200) -> str:
    """One line without terminal colour codes, cut at a word boundary with an ellipsis when longer than n."""
    flat = " ".join(plain(str(text or "")).split())
    if len(flat) <= n:
        return flat
    cut = flat[:n].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:.") + "…"


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _pct(part: int, whole: int) -> str:
    return f"{round(100 * part / whole)}%" if whole else "n/a"


def _label(name: str) -> str:
    return "BVT" if name == "bvt" else name.capitalize()


# ── what started the run ─────────────────────────────────────────────────────────────────────


def _trigger_rows(row: dict[str, Any], folder: Path) -> list[list[str]]:
    manifest = _json(folder / "manifest.json")
    trigger = str(row.get("trigger") or manifest.get("trigger") or "")
    ticket = row.get("ticket") or manifest.get("ticket")
    pr = row.get("pr") or manifest.get("pr")
    sha = row.get("sha") or manifest.get("sha")
    if not trigger:
        trigger = "e2e" if (row.get("kind") or manifest.get("kind")) == "phase1" else "ticket" if ticket else "pr" if pr else "manual"
    rows = [["Trigger", TRIGGERS.get(trigger, trigger) + (f" {ticket}" if trigger == "ticket" and ticket else "")]]
    if trigger != "ticket" and ticket:
        rows.append(["Ticket", str(ticket)])
    if pr:
        rows.append(["Pull request", f"#{pr}" + _pr_state(folder, pr)])
    if sha:
        rows.append(["Deployed commit", f"`{str(sha)[:12]}`"])
    return rows


def _pr_state(folder: Path, number: Any) -> str:
    """` (merged)` or ` (open)` from the context pack, which exists until the run is sealed."""
    for pull in _json(folder / "context-pack.json").get("pullRequests") or []:
        if isinstance(pull, dict) and str(pull.get("number")) == str(number):
            return " (merged)" if pull.get("merged") else f" ({pull.get('state')})" if pull.get("state") else ""
    return ""


# ── tests ────────────────────────────────────────────────────────────────────────────────────


def _outcomes(path: Path) -> list[dict[str, Any]]:
    rows = _json(path, [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _cases(path: Path) -> list[dict[str, Any]]:
    """Each test with its type and suite from the tags the spec declared, and its final result."""
    cases = []
    for row in _outcomes(path):
        tags = {str(tag).lstrip("@").lower() for tag in row.get("tags") or []}
        cases.append({
            "title": _clip(row.get("title"), 160),
            "status": str(row.get("status") or "unknown"),
            "type": next((name for name in TYPES if name in tags), "untagged"),
            "suite": next((name for name in SUITES if name in tags), "untagged"),
        })
    return cases


def _passed(cases: list[dict[str, Any]]) -> int:
    return sum(1 for c in cases if c["status"] in {"passed", "flaky"})


def _failed(cases: list[dict[str, Any]]) -> int:
    return sum(1 for c in cases if c["status"] == "failed")


def _breakdown(cases: list[dict[str, Any]], key: str, order: tuple[str, ...]) -> list[list[str]]:
    names = list(order) + sorted({c[key] for c in cases} - set(order))
    rows = []
    for name in names:
        group = [c for c in cases if c[key] == name]
        if not group and name not in order:
            continue
        rows.append([_label(name), str(len(group)), str(_passed(group)), str(_failed(group)), _pct(_passed(group), len(group))])
    return rows


# ── bugs ─────────────────────────────────────────────────────────────────────────────────────


def _bugs(folder: Path) -> list[dict[str, Any]]:
    found = [b for b in _json(folder / "bugs.json").get("bugs") or [] if isinstance(b, dict)]
    return sorted(found, key=severity_rank)


def _bug_blocks(bugs: list[dict[str, Any]], prefix: str = "") -> list[tuple]:
    """A table of the bugs, then each one as its ticket will read: what happens, steps, expected, actual."""
    if not bugs:
        return [("p", "No product bug was filed.")]
    rows = []
    for index, bug in enumerate(bugs, start=1):
        shots = [f"{prefix}{shot}" for shot in bug.get("screenshots") or []]
        rows.append([str(index), _clip(bug.get("title"), 140), f"{bug.get('severity', '')} ({bug.get('priority', '')})",
                     bug.get("confidence") or "not stated", (f"{len(shots)} screenshot(s)", shots[0]) if shots else "none"])
    blocks: list[tuple] = [("table", ["#", "Bug", "Severity", "Confidence", "Evidence"], rows)]
    for index, bug in enumerate(bugs, start=1):
        blocks.append(("bug", f"{index}. {_clip(bug.get('title'), 180)}"))
        if bug.get("description"):
            blocks.append(("p", _clip(bug["description"], 500)))
        facts = [f"Found by: {bug.get('ticket') or 'this run'}" + (f" ({', '.join(bug['affectedTests'])})" if bug.get("affectedTests") else "")]
        if bug.get("persona"):
            facts.append(f"Signed in as: {bug['persona']}")
        facts.extend(f"Before you start: {_clip(item, 300)}" for item in bug.get("preconditions") or [])
        blocks.append(("list", facts))
        if bug.get("steps"):
            blocks.append(("ol", [_clip(step, 300) for step in bug["steps"]]))
        blocks.append(("list", [f"Expected: {_clip(bug.get('expected') or 'not recorded', 400)}",
                                f"Actual: {_clip(bug.get('actual') or 'not recorded', 400)}"]))
        shots = [f"{prefix}{shot}" for shot in bug.get("screenshots") or []]
        if shots:
            blocks.append(("images", [(Path(shot).name, shot) for shot in shots]))
    return blocks


# ── sections ─────────────────────────────────────────────────────────────────────────────────


def _e2e_blocks(e2e: Path, prefix: str, *, promoted: dict[str, Any] | None, open_issues: bool) -> list[tuple]:
    """The checked-in suite's result in `e2e` (a ticket's e2e/ or a standalone E2E run folder)."""
    result = _json(e2e / "qa-result.json")
    if not result:
        return [("p", "The E2E User Journey TCs did not run in this run (QA_PHASE1_ON_START=false, or the run stopped first).")]
    counts = result.get("test_results") or {}
    passed, failed = _int(counts.get("passed")), _int(counts.get("failed"))
    flaky, skipped = _int(counts.get("flaky")), _int(counts.get("skipped"))
    ran = passed + failed + flaky + skipped
    healed: dict[str, str] = {}
    for path in sorted(e2e.glob("triage-*.json")):
        for item in _json(path).get("failures") or []:
            if isinstance(item, dict) and str(item.get("class") or "").lower() == "spec" and item.get("action") == "patched":
                healed[str(item.get("title") or item.get("test") or "")] = _clip(item.get("reason"), 220)
    facts = [f"Updated in place because the app changed: {len(healed)}"]
    if promoted is not None:
        facts.insert(0, f"Test cases added to the E2E suite by this run: {len(promoted.get('cases') or [])}"
                        + (f" ({len(promoted.get('skipped') or [])} candidates not added)" if promoted.get("skipped") else ""))
    blocks: list[tuple] = [
        ("verdict", str(result.get("verdict", "unknown"))),
        ("table", ["Ran", "Passed", "Failed", "Flaky (passed on retry)", "Pass ratio"],
         [[str(ran), str(passed), str(failed), str(flaky), _pct(passed + flaky, ran)]]),
        ("list", facts),
    ]
    if open_issues and result.get("open_issues"):
        blocks.extend([("sub", "Still failing"), ("list", [_clip(issue, 240) for issue in result["open_issues"][:10]])])
    blocks.extend([("sub", "Bugs"), *_bug_blocks(_bugs(e2e), prefix)])
    cases = _cases(e2e / "playwright" / "test-outcomes.json")
    if cases:
        blocks.append(("details", f"All {len(cases)} E2E cases",
                       [("table", ["Test", "Result"], [[c["title"], c["status"]] for c in cases])]))
    if healed:
        blocks.append(("details", f"E2E cases updated in place ({len(healed)})",
                       [("list", [f"{title}: {reason}" for title, reason in healed.items()])]))
    if promoted and promoted.get("skipped"):
        blocks.append(("details", "Feature TCs not added to the E2E suite",
                       [("list", [f"{_clip(item.get('title'), 140)}: {_clip(item.get('reason'), 120)}"
                                  for item in promoted["skipped"] if isinstance(item, dict)])]))
    return blocks


def _feature_blocks(folder: Path) -> list[tuple]:
    result = _json(folder / "qa-result.json")
    cases = _cases(folder / "playwright" / "test-outcomes.json")
    generated, passed, failed = len(cases), _passed(cases), _failed(cases)
    blocks: list[tuple] = [
        ("verdict", str(result.get("verdict", "unknown"))),
        ("table", ["Generated", "Passed", "Failed", "Not run", "Pass ratio"],
         [[str(generated), str(passed), str(failed), str(generated - passed - failed), _pct(passed, generated)]]),
        ("sub", "By type"),
        ("table", ["Type", "Generated", "Passed", "Failed", "Pass ratio"], _breakdown(cases, "type", TYPES)),
        ("sub", "By suite"),
        ("table", ["Suite", "Generated", "Passed", "Failed", "Pass ratio"], _breakdown(cases, "suite", SUITES)),
    ]
    affected = _cases(folder / "affected" / "test-outcomes.json")
    if affected:
        blocks.append(("p", f"Checked-in cases this change touches: {len(affected)} ran, {_failed(affected)} failed."))
    blocks.extend([("sub", "Bugs"), *_bug_blocks(_bugs(folder))])
    if cases:
        blocks.append(("details", f"All {generated} feature TCs",
                       [("table", ["Test", "Type", "Suite", "Result"],
                         [[c["title"], _label(c["type"]), _label(c["suite"]), c["status"]] for c in cases])]))
    return blocks


def _ux_blocks(folder: Path) -> list[tuple]:
    card = _json(folder / "ux-scorecard.json")
    if not card:
        return [("p", "The UX audit did not run.")]
    score = card.get("score")
    counts = card.get("counts") or {}
    blocks: list[tuple] = [("verdict", f"{card.get('verdict')} · score {score if score is not None else 'not scored'}")]
    if counts:
        blocks.append(("p", "Findings: " + ", ".join(f"{key} {counts.get(key, 0)}" for key in ("S0", "S1", "S2", "S3", "O"))))
    if card.get("error"):
        blocks.append(("p", f"Audit problem: {_clip(card['error'], 200)}"))
    findings = _json(folder / "ux-findings.json", [])
    findings = findings if isinstance(findings, list) else findings.get("findings", [])
    open_items = [f for f in findings if isinstance(f, dict) and f.get("status") != "Resolved"]
    changes = [f for f in open_items if f.get("severity") in {"S0", "S1", "S2", "S3"}]
    if changes:
        rows = []
        for f in sorted(changes, key=lambda item: str(item.get("severity"))):
            title = _clip(f.get("title"), 150) + (" (held for review)" if f.get("status") == "Held for review" else "")
            fix = str(f.get("solution") or f.get("developerImplementation") or "").strip()
            fix = fix.removeprefix("What to fix (plain English):").strip()
            shot = f.get("screenshot")
            rows.append([str(f.get("severity")), title, _clip(fix[:1].upper() + fix[1:], 260), ("screenshot", shot) if shot else ""])
        blocks.append(("table", ["Severity", "Finding", "Suggested change", "Evidence"], rows))
    else:
        blocks.append(("p", "No S0 to S3 finding is open."))
    notes = [f for f in open_items if f.get("severity") == "O"]
    if notes:
        blocks.extend([("sub", "Observations"), ("list", [_clip(f.get("title"), 200) for f in notes])])
    return blocks


def _overview(folder: Path, row: dict[str, Any], verdict: str, issues: list[str], *, standalone_e2e: bool) -> list[tuple]:
    summary = _json(folder / "summary.json")
    cost = summary.get("cost")
    e2e_folder = folder if standalone_e2e else folder / "e2e"
    e2e = _json(e2e_folder / "qa-result.json").get("test_results") or {}
    e2e_ran = sum(_int(e2e.get(k)) for k in ("passed", "failed", "flaky", "skipped"))
    e2e_passed = _int(e2e.get("passed")) + _int(e2e.get("flaky"))
    table = [["E2E User Journey TCs", str(e2e_ran), str(e2e_passed), str(_int(e2e.get("failed"))),
              _pct(e2e_passed, e2e_ran), str(len(_bugs(e2e_folder)))]]
    if not standalone_e2e:
        cases = _cases(folder / "playwright" / "test-outcomes.json")
        table.append(["Feature Specific TCs", str(len(cases)), str(_passed(cases)), str(_failed(cases)),
                      _pct(_passed(cases), len(cases)), str(len(_bugs(folder)))])
    deployment = _json(folder / "context-pack.json").get("deployment") or {}
    facts = [
        *_trigger_rows(row, folder),
        ["Run", f"`{row.get('id') or folder.name}`"],
        *([["Started", str(summary["startedAt"])]] if summary.get("startedAt") else []),
        ["App", _json(folder / "preflight.json").get("appUrl") or "n/a"],
    ]
    if summary.get("deployment") or deployment.get("summary"):
        facts.append(["Deployment", str(summary.get("deployment") or deployment.get("summary"))])
    facts.append(["Took", (_span(summary.get("seconds")) or "n/a") + (f", cost ${cost:.2f}" if isinstance(cost, (int, float)) else "")])
    blocks: list[tuple] = [
        ("verdict", f"Verdict: {verdict}"),
        ("table", ["Area", "Ran", "Passed", "Failed", "Pass ratio", "Bugs"], table),
        ("table", ["Item", "Detail"], facts),
    ]
    if issues:
        blocks.extend([("sub", "Open issues"), ("list", [_clip(issue, 240) for issue in issues[:10]])])
    return blocks


def _sections(folder: Path, row: dict[str, Any], *, verdict: str, issues: list[str]) -> tuple[str, list[tuple]]:
    standalone_e2e = (row.get("kind") or _json(folder / "manifest.json").get("kind")) == "phase1"
    links = [("This report in a browser", "linear-report.html")]
    if (folder / "ux-report.html").is_file():
        links.append(("UI/UX audit, interactive", "ux-report.html"))
    if (folder / "bugs.md").is_file():
        links.append(("Bugs, written as tickets", "bugs.md"))
    if (folder / "bug-evidence").is_dir():
        links.append(("Bug screenshots", "bug-evidence/"))
    if (folder / "e2e" / "bug-evidence").is_dir():
        links.append(("E2E bug screenshots", "e2e/bug-evidence/"))
    overview = ("Overview", _overview(folder, row, verdict, issues, standalone_e2e=standalone_e2e))
    if standalone_e2e:
        title = "E2E User Journey TCs: QA report"
        sections = [overview, ("E2E User Journey TCs", _e2e_blocks(folder, "", promoted=None, open_issues=False))]
    else:
        subject = row.get("ticket") or (f"PR #{row['pr']}" if row.get("pr") else folder.name)
        title = f"{subject}: QA report"
        sections = [
            overview,
            ("1. E2E User Journey TCs", _e2e_blocks(folder / "e2e", "e2e/", promoted=_json(folder / "promoted.json"), open_issues=True)),
            ("2. Feature Specific TCs", _feature_blocks(folder)),
            ("3. Suggested UX changes", _ux_blocks(folder)),
        ]
    sections.append(("Files", [("links", links)]))
    return title, sections


# ── renderers ────────────────────────────────────────────────────────────────────────────────


def _md_cell(cell: Any) -> str:
    if isinstance(cell, tuple):
        label, href = cell
        return f"[{label}]({href})"
    return str(cell).replace("|", "/").replace("\n", " ")


def _markdown(title: str, sections: list[tuple]) -> str:
    out = [f"# {title}", ""]
    for heading, blocks in sections:
        out.extend([f"## {heading}", ""])
        for block in blocks:
            kind = block[0]
            if kind == "verdict":
                out.extend([f"**{block[1]}**", ""])
            elif kind == "p":
                out.extend([block[1], ""])
            elif kind == "sub":
                out.extend([f"### {block[1]}", ""])
            elif kind == "bug":
                out.extend([f"#### {block[1]}", ""])
            elif kind == "table":
                _, headers, rows = block
                out.append("| " + " | ".join(headers) + " |")
                out.append("|" + "---|" * len(headers))
                out.extend("| " + " | ".join(_md_cell(c) for c in row) + " |" for row in rows)
                out.append("")
            elif kind == "list":
                out.extend(f"- {item}" for item in block[1])
                out.append("")
            elif kind == "ol":
                out.extend(f"{n}. {item}" for n, item in enumerate(block[1], start=1))
                out.append("")
            elif kind == "links":
                out.extend(f"- [{label}]({href})" for label, href in block[1])
                out.append("")
            elif kind == "images":
                out.append("Screenshots: " + ", ".join(f"[{caption}]({href})" for caption, href in block[1]))
                out.append("")
            # details is for the HTML report only, so the Linear comment stays short
    return "\n".join(out).rstrip() + "\n"


CSS = """
body{font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem;color:#1f2328}
h1{font-size:1.6rem}h2{margin-top:2rem;padding-bottom:.3rem;border-bottom:1px solid #d0d7de}h3{font-size:1.05rem}
h4{margin:1.2rem 0 .3rem;font-size:1rem}
table{border-collapse:collapse;width:100%;margin:.5rem 0 1rem}th,td{border:1px solid #d0d7de;padding:.35rem .55rem;text-align:left;vertical-align:top}
th{background:#f6f8fa}.verdict{display:inline-block;padding:.2rem .6rem;border-radius:6px;background:#fff8c5;font-weight:600}
img{max-width:min(100%,520px);border:1px solid #d0d7de;border-radius:6px}
figure{margin:.5rem 0}figcaption{font-size:.85rem;color:#59636e}details{margin:.8rem 0}summary{cursor:pointer;font-weight:600}
code{background:#f6f8fa;padding:0 .25rem;border-radius:4px}
""".strip()


def _html_cell(cell: Any) -> str:
    if isinstance(cell, tuple):
        label, href = cell
        return f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
    text = html.escape(str(cell))
    if text.startswith("`") and text.endswith("`") and len(text) > 1:
        return f"<code>{text[1:-1]}</code>"
    return text


def _html_blocks(blocks: list[tuple]) -> list[str]:
    out: list[str] = []
    for block in blocks:
        kind = block[0]
        if kind == "verdict":
            out.append(f'<p><span class="verdict">{html.escape(block[1])}</span></p>')
        elif kind == "p":
            out.append(f"<p>{html.escape(block[1])}</p>")
        elif kind == "sub":
            out.append(f"<h3>{html.escape(block[1])}</h3>")
        elif kind == "bug":
            out.append(f"<h4>{html.escape(block[1])}</h4>")
        elif kind == "ol":
            out.append("<ol>" + "".join(f"<li>{html.escape(item)}</li>" for item in block[1]) + "</ol>")
        elif kind == "table":
            _, headers, rows = block
            out.append("<table><thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead><tbody>")
            out.extend("<tr>" + "".join(f"<td>{_html_cell(c)}</td>" for c in row) + "</tr>" for row in rows)
            out.append("</tbody></table>")
        elif kind == "list":
            out.append("<ul>" + "".join(f"<li>{html.escape(item)}</li>" for item in block[1]) + "</ul>")
        elif kind == "links":
            out.append("<ul>" + "".join(f'<li><a href="{html.escape(href, quote=True)}">{html.escape(label)}</a></li>' for label, href in block[1]) + "</ul>")
        elif kind == "images":
            for caption, href in block[1]:
                src = html.escape(href, quote=True)
                out.append(f'<figure><a href="{src}"><img src="{src}" alt="{html.escape(caption, quote=True)}"></a>'
                           f"<figcaption>{html.escape(caption)}</figcaption></figure>")
        elif kind == "details":
            out.append(f"<details><summary>{html.escape(block[1])}</summary>")
            out.extend(_html_blocks(block[2]))
            out.append("</details>")
    return out


def _html(title: str, sections: list[tuple]) -> str:
    body = [f"<h1>{html.escape(title)}</h1>"]
    for heading, blocks in sections:
        body.append(f"<h2>{html.escape(heading)}</h2>")
        body.extend(_html_blocks(blocks))
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head>\n"
        f"<body>\n{chr(10).join(body)}\n</body></html>\n"
    )


def build(folder: Path, row: dict[str, Any], *, verdict: str, issues: list[str]) -> str:
    """The Linear comment: markdown only, the same blocks as the HTML without the details."""
    title, sections = _sections(folder, row, verdict=verdict, issues=issues)
    return _markdown(title, sections)


def write(folder: Path, row: dict[str, Any], *, verdict: str, issues: list[str]) -> Path:
    title, sections = _sections(folder, row, verdict=verdict, issues=issues)
    target = folder / "linear-report.md"
    target.write_text(_markdown(title, sections), encoding="utf-8")
    (folder / "linear-report.html").write_text(_html(title, sections), encoding="utf-8")
    return target
