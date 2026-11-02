"""Remove what nobody reads from a finished run folder.

A sealed run keeps what a reader and the next run use: reports, bugs and their screenshots, the
specs, the plan and walk notes, the UX audit, the cost record, the test results and the model's
transcript (compressed). It drops files the server regenerates or that only mattered while the
run was alive. A halted or failed run keeps everything, because it may be resumed or debugged.
"""

from __future__ import annotations

import gzip
import shutil
from pathlib import Path

# Rebuilt from run.log, summary.json and the index, or the same data in another file.
ALWAYS = (
    "contents.txt", "toolchain.log", "preflight.log", "prompt.md", "ux-prompt.md", "promote-prompt.md",
    "verify-prompt.md", "heal-*.md",
)
# Only while the model was working: raw page snapshots and the browser config. The walk scripts stay: bugs cite them.
EXPLORE_SCRATCH = ("*.yml", "*.yaml", "*.txt", "pw-cli.json")
# Playwright's own debugging output. Failure screenshots and error-context.md stay.
PLAYWRIGHT_HEAVY = ("html", "report")
HEAVY_FILES = ("*.zip", "*.webm", "*.mp4", "*.trace")
# Duplicates of opencode/*.jsonl, and the child-session index.
OPENCODE_DUPLICATES = ("session*.json", "children.json", "children")


def _remove(path: Path) -> int:
    try:
        if path.is_dir():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            shutil.rmtree(path, ignore_errors=True)
            return size
        size = path.stat().st_size
        path.unlink()
        return size
    except OSError:
        return 0


def _gzip(path: Path) -> int:
    target = path.with_name(path.name + ".gz")
    try:
        before = path.stat().st_size
        with path.open("rb") as src, gzip.open(target, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        path.unlink()
        return before - target.stat().st_size
    except OSError:
        return 0


def prune_run(folder: Path, *, finished: bool = True) -> int:
    """Bytes freed. `finished` is False for a halted or failed run: only Playwright's heavy output goes."""
    freed = 0
    playwright = folder / "playwright"
    if playwright.is_dir():
        for name in PLAYWRIGHT_HEAVY:
            freed += _remove(playwright / name)
        for pattern in HEAVY_FILES:
            for path in playwright.rglob(pattern):
                freed += _remove(path)
    if not finished:
        return freed
    for pattern in ALWAYS:
        for path in folder.glob(pattern):
            freed += _remove(path)
    explore = folder / "explore"
    if explore.is_dir():
        for pattern in EXPLORE_SCRATCH:
            for path in explore.glob(pattern):
                freed += _remove(path)
    opencode = folder / "opencode"
    if opencode.is_dir():
        for pattern in OPENCODE_DUPLICATES:
            for path in opencode.glob(pattern):
                freed += _remove(path)
        for path in opencode.glob("*.jsonl"):
            freed += _gzip(path)
    # The brief is the digest the agent worked from; the full diffs are in GitHub.
    freed += _remove(folder / "context-pack.json")
    # An empty folder says nothing.
    for name in ("explore", "opencode", "playwright"):
        sub = folder / name
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()
    return freed


def mib(size: int) -> str:
    return f"{size / 1048576:.1f} MiB"
