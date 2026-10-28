"""Checked-in E2E cases the ticket author must not write again."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_JOURNEY_ORDER = ("search", "asset crud", "document editing")
_SUITE_LABEL = {
    "bvt": "BVT",
    "smoke": "Smoke",
    "sanity": "Sanity",
    "regression": "Regression",
}
_ID_SLUG = {
    "search": "SRCH",
    "asset crud": "AC",
    "document editing": "DOC",
}
_TC_ID = re.compile(r"(TC-[A-Za-z0-9-]+)")
_DESCRIBE = re.compile(r"test\.describe\(\s*([\"'`])(.+?)\1")
_TEST = re.compile(r"(?<![\w.])test\(\s*([\"'`])(.+?)\1")
_INVENTORY_HEADER = re.compile(r"\|\s*TC\s*\|\s*Title\s*\|\s*Type\s*\|\s*Suite\b", re.IGNORECASE)
_NEGATIVE = re.compile(
    r"\b(invalid|reject(?:ed|ion)?|blocked|empty|missing|no-results|no results|401|403|4xx|expired|forbidden)\b",
    re.IGNORECASE,
)
_EDGE = re.compile(
    r"\b(discard\w*|cancel\w*|clear\w*|edge|boundary|wrap\w*|reset\w*|debounc\w*|only the)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Case:
    journey: str
    id: str
    type: str
    suite: str
    group: str
    title: str
    file: str


def write_coverage_index(suite_root: Path, dest: Path) -> int:
    cases = load_cases(suite_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_coverage(suite_root), encoding="utf-8")
    return len(cases)


def render_coverage(suite_root: Path) -> str:
    cases = load_cases(suite_root)
    lines = [
        "# Checked-in E2E coverage",
        "",
        "E2E User Journey TCs already run these cases. The journeys are search, asset crud, and document editing.",
        "",
        "When this ticket changes one of those journeys, do not write a row again. Cite its id in FEATURE.md.",
        "Write a new case only for behavior this ticket adds or changes that no row already asserts.",
        "A new surface that is not one of these journeys has no baseline here, so plan that surface in full.",
        "There is no minimum number of new cases and no maximum. The number is the uncovered behavior.",
        "",
        "Type is what the case proves: positive, negative, or edge.",
        "Suite is when it runs: BVT, Smoke, Sanity, Regression. Tag a new test with one type and one suite.",
        "A new id looks like TC-<TICKET>-001. Do not reuse an id from this file.",
        "",
    ]
    if not cases:
        lines.append("No checked-in cases were found.")
        lines.append("")
        return "\n".join(lines)
    lines.append(f"{len(cases)} cases.")
    lines.append("")
    current = ""
    for case in cases:
        if case.journey != current:
            current = case.journey
            lines.extend([
                f"## {current}",
                "",
                f"Folder: `e2e test cases/{current}`",
                "",
                "| Id | Type | Suite | Group | Title | File |",
                "|---|---|---|---|---|---|",
            ])
        title = case.title.replace("|", "/")
        group = case.group.replace("|", "/")
        lines.append(
            f"| {case.id} | {case.type} | {_SUITE_LABEL.get(case.suite, case.suite)} | {group} | {title} | {case.file} |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def load_cases(suite_root: Path) -> list[Case]:
    if not suite_root.is_dir():
        return []
    folders = [path for path in suite_root.iterdir() if path.is_dir() and not path.name.startswith(".")]
    folders.sort(key=lambda path: (_JOURNEY_ORDER.index(path.name) if path.name in _JOURNEY_ORDER else 99, path.name))
    cases: list[Case] = []
    for folder in folders:
        cases.extend(_cases_for_journey(folder))
    return cases


def _cases_for_journey(folder: Path) -> list[Case]:
    from_specs = _parse_specs(folder)
    from_md = _parse_feature_table(folder / "FEATURE.md", folder.name)
    if not from_md:
        return _with_generated_ids(from_specs)
    by_id = {case.id: case for case in from_specs}
    ordered: list[Case] = []
    seen: set[str] = set()
    for row in from_md:
        spec = by_id.get(row.id)
        ordered.append(Case(
            journey=folder.name,
            id=row.id,
            type=row.type or (spec.type if spec else "positive"),
            suite=row.suite or (spec.suite if spec else "regression"),
            group=spec.group if spec else row.group,
            title=row.title or (spec.title if spec else row.id),
            file=spec.file if spec else row.file,
        ))
        seen.add(row.id)
    for case in from_specs:
        if case.id not in seen:
            ordered.append(case)
    return ordered


def _with_generated_ids(cases: list[Case]) -> list[Case]:
    slug = _ID_SLUG.get(cases[0].journey, "E2E") if cases else "E2E"
    numbered: list[Case] = []
    serial = 1
    for case in cases:
        if _TC_ID.fullmatch(case.id) or case.id.startswith("TC-"):
            numbered.append(case)
            continue
        numbered.append(Case(
            journey=case.journey,
            id=f"{slug}-{serial:03d}",
            type=case.type,
            suite=case.suite,
            group=case.group,
            title=case.title,
            file=case.file,
        ))
        serial += 1
    return numbered


def _parse_specs(folder: Path) -> list[Case]:
    found: list[Case] = []
    for path in sorted(folder.glob("*.spec.ts")):
        group = folder.name
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            described = _DESCRIBE.search(line)
            if described:
                group = described.group(2).strip()
                continue
            matched = _TEST.search(line)
            if not matched:
                continue
            raw = matched.group(2).strip()
            tc = _TC_ID.search(raw)
            title = raw
            case_id = ""
            if tc:
                case_id = tc.group(1)
                title = raw[tc.end():].lstrip(" :—-")
            found.append(Case(
                journey=folder.name,
                id=case_id,
                type=_type_for(group, title),
                suite=_suite_for(group),
                group=group,
                title=title or raw,
                file=path.name,
            ))
    return found


def _parse_feature_table(path: Path, journey: str) -> list[Case]:
    if not path.is_file():
        return []
    rows: list[Case] = []
    in_table = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if _INVENTORY_HEADER.search(line):
            in_table = True
            continue
        if not in_table:
            continue
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        if re.match(r"\|\s*-+", stripped):
            continue
        cells = [cell.strip().strip("`") for cell in stripped.strip("|").split("|")]
        if len(cells) < 4 or not cells[0] or cells[0].lower() == "tc":
            continue
        rows.append(Case(
            journey=journey,
            id=cells[0],
            type=_canonical_type(cells[2]),
            suite=_canonical_suite(cells[3]),
            group="",
            title=cells[1],
            file=cells[5] if len(cells) > 5 else "",
        ))
    return rows


def _type_for(group: str, title: str) -> str:
    lowered = group.lower()
    if "negative" in lowered:
        return "negative"
    if "edge" in lowered:
        return "edge"
    if "positive" in lowered:
        return "positive"
    if _NEGATIVE.search(title):
        return "negative"
    if _EDGE.search(title):
        return "edge"
    return "positive"


def _suite_for(group: str) -> str:
    lowered = group.lower()
    for name in ("bvt", "smoke", "sanity", "regression"):
        if name in lowered:
            return name
    return "regression"


def _canonical_type(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in {"positive", "negative", "edge"}:
        return lowered
    return _type_for("", value)


def _canonical_suite(value: str) -> str:
    lowered = value.strip().lower()
    if lowered in _SUITE_LABEL:
        return lowered
    return "regression"
