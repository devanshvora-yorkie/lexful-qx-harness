"""Screenshots for the bugs a run files, kept in <run dir>/bug-evidence/.

Two sources, both real captures and neither made up by the server:
- the verifier session saves one screenshot per item it reproduces, named after the item's
  ref (`finding:F1` -> bug-evidence/finding-F1.png, `bug:2` -> bug-evidence/bug-2.png);
- Playwright's own failure screenshot of the tests the bug lists as affected.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

DIR = "bug-evidence"
MAX_PER_BUG = 3


def slug(ref: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", ref.strip()).strip("-") or "item"


def _results(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / "playwright" / "results.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _failure_pngs(folder: Path) -> list[tuple[str, Path]]:
    """(full test title, screenshot file) for each failed test in the last Playwright report."""
    found: list[tuple[str, Path]] = []

    def walk(node: Any, trail: list[str]) -> None:
        if not isinstance(node, dict):
            return
        here = trail + ([str(node["title"])] if node.get("title") and not str(node.get("file", "")) == str(node.get("title")) else [])
        for spec in node.get("specs") or []:
            if not isinstance(spec, dict):
                continue
            title = " › ".join([*here, str(spec.get("title") or "")])
            for test in spec.get("tests") or []:
                for result in (test or {}).get("results") or []:
                    if result.get("status") not in {"failed", "timedOut", "interrupted"}:
                        continue
                    for attachment in result.get("attachments") or []:
                        if str(attachment.get("contentType", "")).startswith("image/") and attachment.get("path"):
                            path = _local(folder, str(attachment["path"]))
                            if path is not None:
                                found.append((title, path))
        for child in node.get("suites") or []:
            walk(child, here)

    for suite in _results(folder).get("suites") or []:
        walk(suite, [])
    return found


def _local(folder: Path, recorded: str) -> Path | None:
    """The attachment path as it is now: the run folder is renamed when a run is sealed."""
    path = Path(recorded)
    if path.is_file():
        return path
    marker = "/playwright/"
    if marker in recorded:
        candidate = folder / "playwright" / recorded.split(marker, 1)[1]
        if candidate.is_file():
            return candidate
    return None


def _affected(bug: dict[str, Any]) -> list[str]:
    raw = bug.get("affectedTests") or bug.get("affected_tests") or []
    if isinstance(raw, str):
        raw = [raw]
    names = [str(item.get("title") or item.get("id") or "") if isinstance(item, dict) else str(item) for item in raw]
    for key in ("failure", "title", "test"):
        if bug.get(key):
            names.append(str(bug[key]))
    return [name.strip().lower() for name in names if name and name.strip()]


def screenshots_for(folder: Path, ref: str, bug: dict[str, Any]) -> list[str]:
    """Relative paths of the screenshots that show this bug. Failure screenshots are copied in."""
    out = folder / DIR
    shots: list[str] = []
    for path in sorted(out.glob(f"{slug(ref)}*.png")) if out.is_dir() else []:
        shots.append(f"{DIR}/{path.name}")
    names = _affected(bug)
    if names:
        count = 0
        for title, path in _failure_pngs(folder):
            lowered = title.lower()
            if not any(name in lowered or lowered.endswith(name) or lowered.split(" › ")[-1] in name for name in names):
                continue
            count += 1
            target = out / f"{slug(ref)}-failure-{count}.png"
            out.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copyfile(path, target)
            except OSError:
                continue
            shots.append(f"{DIR}/{target.name}")
            if count >= 2:
                break
    seen: list[str] = []
    for shot in shots:
        if shot not in seen:
            seen.append(shot)
    return seen[:MAX_PER_BUG]
