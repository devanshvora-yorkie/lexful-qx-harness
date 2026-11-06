"""Checks the server makes on what the agent and the specs left behind.

- Runtime signals: console errors, page errors and failed API calls that `qa-fixtures.ts`
  records during every test, even when the test passes.
- Expectation edits: a heal may fix a locator or a wait, not what a test expects. Every
  matcher (`.toBe(...)`, `.toHaveText(...)`) of a test that still exists is compared
  before and after each heal.
- coverage.json and hypotheses.json: the agent's own account of which criteria are covered
  and which risks it tried. The server checks the ids against the Playwright results.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# ---- runtime signals ------------------------------------------------------------------------


def read_signals(folder: Path) -> list[dict[str, Any]]:
    path = folder / "playwright" / "signals.jsonl"
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _is_noise(item: dict[str, Any]) -> bool:
    """CDN blocks and expired sessions are environment, not product."""
    text = f"{item.get('text', '')} {item.get('url', '')}".lower()
    if "request blocked" in text or "cloudfront" in text:
        return True
    return item.get("kind") == "response" and int(item.get("status") or 0) in {401, 403}


def summarize_signals(folder: Path) -> dict[str, Any]:
    """Counts by kind, the distinct failing endpoints, and one log line."""
    rows = [item for item in read_signals(folder) if not _is_noise(item)]
    by_kind = Counter(str(item.get("kind") or "other") for item in rows)
    endpoints = Counter(
        f"{item.get('method', '')} {item.get('status', '')} {re.sub(r'[0-9a-f-]{8,}', ':id', str(item.get('path') or ''))}".strip()
        for item in rows
        if item.get("kind") == "response"
    )
    server_errors = [item for item in rows if item.get("kind") == "response" and int(item.get("status") or 0) >= 500]
    line = ", ".join(f"{count} {kind}" for kind, count in by_kind.most_common())
    if endpoints:
        line += "; " + "; ".join(f"{name} x{count}" for name, count in endpoints.most_common(4))
    return {
        "count": len(rows),
        "byKind": dict(by_kind),
        "endpoints": dict(endpoints),
        "serverErrors": len(server_errors),
        "line": line,
        "samples": rows[:20],
    }


# ---- expectation edits ----------------------------------------------------------------------

_TEST = re.compile(r"(?<![\w.])test(?:\.only)?\(\s*([\"'`])(.+?)\1")
_MATCHER = re.compile(r"\.(?:not\.)?to[A-Z]\w*\((?:[^()]|\([^()]*\))*\)")


def spec_texts(folder: Path) -> dict[str, str]:
    root = folder / "specs"
    if not root.is_dir():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_text(encoding="utf-8", errors="replace")
        for path in sorted(root.rglob("*.spec.ts"))
    }


def _matchers_by_test(text: str) -> dict[str, Counter[str]]:
    found: dict[str, Counter[str]] = {}
    marks = list(_TEST.finditer(text))
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[mark.end():end]
        found[mark.group(2)] = Counter(" ".join(m.group(0).split()) for m in _MATCHER.finditer(body))
    return found


def expectation_changes(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Matchers that left a test which is still there. A removed test (a gap) is not counted."""
    changes: list[str] = []
    for name, old_text in before.items():
        new_text = after.get(name)
        if new_text is None or new_text == old_text:
            continue
        old_tests = _matchers_by_test(old_text)
        new_tests = _matchers_by_test(new_text)
        for title, old in old_tests.items():
            if title not in new_tests:
                continue
            gone = old - new_tests[title]
            for matcher in gone:
                added = new_tests[title] - old
                now = ", ".join(sorted(added)) or "nothing"
                changes.append(f"{name} › {title[:80]}: {matcher[:80]} → {now[:80]}")
    return changes


def record_assertion_edits(folder: Path, attempt: int, before: dict[str, str], after: dict[str, str]) -> list[str]:
    changes = expectation_changes(before, after)
    if not changes:
        return []
    path = folder / "assertion-edits.json"
    data = _read(path, {"edits": []})
    data.setdefault("edits", []).extend({"heal": attempt, "change": line} for line in changes)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changes


def assertion_edits(folder: Path) -> list[str]:
    data = _read(folder / "assertion-edits.json", {"edits": []})
    return [str(item.get("change")) for item in data.get("edits") or [] if isinstance(item, dict)]


# ---- coverage.json and hypotheses.json ------------------------------------------------------


def brief_criteria(folder: Path) -> list[str]:
    """Acceptance criteria numbered the way pr-brief.md numbers them (AC1, AC2, ...)."""
    pack = _read(folder / "context-pack.json", {})
    ticket = pack.get("ticket") if isinstance(pack.get("ticket"), dict) else {}
    lines = [line.strip() for line in str(ticket.get("acceptanceCriteria") or "").split("\n") if line.strip()]
    return [line.lstrip("-*• ") for line in lines[:30]]


def coverage_blockers(folder: Path, passing_titles: list[str]) -> list[str]:
    """Issues from coverage.json. The file is the agent's hand-off (`phases/explore-author.md`, hand-off files); without it nothing is signed off."""
    data = _read(folder / "coverage.json", None)
    # The contract is {"criteria": [...]}. Agents have also written a bare list or {"coverage": [...]}; accept those.
    rows = data if isinstance(data, list) else (data.get("criteria") or data.get("coverage")) if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return ["coverage.json is missing or has no criteria: no acceptance criterion is mapped to a test"]
    criteria = brief_criteria(folder)
    mapped: dict[str, dict[str, Any]] = {}
    for item in rows:
        if isinstance(item, dict) and item.get("ac"):
            mapped[str(item["ac"]).upper().replace(" ", "")] = item
    issues: list[str] = []
    for number, text in enumerate(criteria, start=1):
        key = f"AC{number}"
        item = mapped.get(key)
        if item is None:
            issues.append(f"{key} is not in coverage.json: {text[:140]}")
            continue
        if item.get("na"):
            continue
        tests = [str(t) for t in item.get("tests") or [] if str(t).strip()]
        if not tests:
            issues.append(f"gap: {key} {text[:100]} — {str(item.get('gap') or 'no test')[:120]}")
            continue
        missing = [t for t in tests if not any(t in title for title in passing_titles)]
        if len(missing) == len(tests):
            issues.append(f"{key} has no passing test ({', '.join(missing)[:80]}): {text[:100]}")
    return issues


def hypothesis_report(folder: Path) -> tuple[str, list[str]]:
    """One summary line and the blockers: risks listed but none tried, or a confirmed risk with no finding.

    Every Risk in feature-map.md is a hypothesis in hypotheses.json (`phases/explore-author.md`, Hypotheses), so the file is the count.
    """
    data = _read(folder / "hypotheses.json", {})
    items = [item for item in data.get("hypotheses") or [] if isinstance(item, dict)] if isinstance(data, dict) else []
    outcomes = Counter(str(item.get("outcome") or "planned").lower() for item in items)
    tried = sum(count for outcome, count in outcomes.items() if outcome in {"confirmed", "refuted"})
    line = f"{len(items)} listed, {tried} tried ({outcomes.get('confirmed', 0)} confirmed, {outcomes.get('refuted', 0)} refuted, {outcomes.get('unreached', 0)} unreached)"
    blockers: list[str] = []
    if (folder / "feature-map.md").is_file() and not items:
        blockers.append("hypotheses.json is missing: the risks in feature-map.md were not listed as hypotheses")
    elif items and not tried:
        blockers.append(f"no risk hypothesis was tried: hypotheses.json lists {len(items)}, none confirmed or refuted")
    for item in items:
        if str(item.get("outcome") or "").lower() == "confirmed" and not item.get("finding") and not item.get("bug"):
            blockers.append(f"hypothesis {item.get('id', '?')} was confirmed but no finding or bug cites it")
    return line, blockers


HANDOFF_JSON = ("coverage.json", "hypotheses.json", "api-findings.json", "triage.json", "affected-cases.json")


def unreadable_files(folder: Path) -> list[str]:
    """Hand-off files that exist but do not parse. The server would otherwise read them as empty and lose what they hold."""
    bad: list[str] = []
    for name in HANDOFF_JSON:
        path = folder / name
        if not path.is_file():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            bad.append(f"{name} is not valid JSON ({str(error)[:80]}), so everything in it was ignored: write it again")
    return bad


REQUIRED_HANDOFF = ("coverage.json", "hypotheses.json", "affected-cases.json", "api-findings.json", "planned-specs.json")


def handoff_problems(folder: Path) -> list[str]:
    """What the explore+author hand-off is missing, as instructions the agent can act on.

    Checked as soon as the session returns, so one short repair turn can fix it. Found only at
    sign-off, a missing coverage.json turns a run whose tests all passed into NEEDS_REVISION.
    """
    problems = unreadable_files(folder)
    for name in REQUIRED_HANDOFF:
        if not (folder / name).is_file():
            problems.append(f"{name} is missing: write it as phases/explore-author.md section 10 says")
    data = _read(folder / "coverage.json", None)
    rows = data if isinstance(data, list) else (data.get("criteria") or data.get("coverage")) if isinstance(data, dict) else None
    if (folder / "coverage.json").is_file() and isinstance(data, (dict, list)):
        if not isinstance(rows, list) or not rows:
            problems.append('coverage.json has no criteria: write {"criteria": [...]} with every AC from pr-brief.md once')
        else:
            mapped = {str(item.get("ac") or "").upper().replace(" ", "") for item in rows if isinstance(item, dict)}
            absent = [f"AC{n}" for n in range(1, len(brief_criteria(folder)) + 1) if f"AC{n}" not in mapped]
            if absent:
                problems.append(f"coverage.json does not list {', '.join(absent[:12])}: map each to tests, a gap or na")
    hyp = _read(folder / "hypotheses.json", None)
    if isinstance(hyp, dict):
        for item in hyp.get("hypotheses") or []:
            if isinstance(item, dict) and str(item.get("outcome") or "").lower() not in {"confirmed", "refuted", "unreached"}:
                problems.append(f"hypothesis {item.get('id', '?')} has no outcome (confirmed, refuted or unreached)")
    return problems


# Spec patterns that broke real runs. Each line: (regex, what to do instead).
SPEC_LINT = (
    (re.compile(r"""locator\(\s*['"`][^'"`]*\[role=['"]?(checkbox|button|row|radio|switch|option|tab)"""),
     "a CSS [role=...] selector does not match native elements (an <input type=checkbox> has no role attribute): use getByRole(...)"),
    (re.compile(r"networkidle"), "waitUntil 'networkidle' is banned (multi-minute hangs): wait for a response or a visible state"),
    (re.compile(r"\bwaitForTimeout\(\s*([2-9]\d{3}|\d{5,})"), "a fixed sleep of 2s or more: wait for the condition (expect.poll, waitForResponse, toBeVisible)"),
    (re.compile(r"\btest\.only\(|\bdescribe\.only\("), ".only would skip every other test in the run"),
)


def spec_lint(folder: Path) -> list[str]:
    """Patterns in the run's specs and page objects that have made tests fail or hang on UAT."""
    found: list[str] = []
    for path in sorted((folder / "specs").glob("*.ts")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, start=1):
            if line.lstrip().startswith("//"):
                continue
            for pattern, advice in SPEC_LINT:
                if pattern.search(line):
                    found.append(f"specs/{path.name}:{number}: {advice}")
    return found


def _read(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return default
