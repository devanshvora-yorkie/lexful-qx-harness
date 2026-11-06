"""Keep only what a reader needs once a run is sealed.

A finished run keeps its record: linear-report.md and .html (the one report), ux-report.html, bugs
and their screenshots, the specs, the plan and walk notes, what each test did (test-outcomes.json),
the triage and verify notes, and the transcripts of the sessions that wrote specs, healed them or
confirmed bugs. Everything else either only mattered while the run was alive or is already in one
of those files. A halted or failed run keeps everything except Playwright's traces and videos,
because it may be resumed or debugged.
"""

from __future__ import annotations

import gzip
import os
import shutil
from pathlib import Path

from app.settings import get_settings

# Only while the run was alive, or the same data is in summary.json, bugs.json or linear-report.md.
ALWAYS = (
    "contents.txt", "toolchain.log", "preflight.log", "prompt.md", "ux-prompt.md", "promote-prompt.md",
    "verify-prompt.md", "handoff-repair.md", "heal-*.md", "affected-heal-*.md", "context-pack.json", "context", "api-probes.jsonl",
    "ux-audit.log",  # runs from before the UX audit wrote into run.log
    "e2e-coverage.md", "planned-specs.json", "report.html", "tmp",
)
# Raw page snapshots and the browser config. The walk scripts stay: bugs cite them.
EXPLORE_SCRATCH = ("*.yml", "*.yaml", "*.txt", "pw-cli.json")
# Playwright's debugging output, removed from every run.
PLAYWRIGHT_HEAVY = ("html", "report")
HEAVY_FILES = ("*.zip", "*.webm", "*.mp4", "*.trace")
# What a sealed run keeps of playwright/: the final result of every test. Failure screenshots that
# show a bug were copied into bug-evidence/ when the bug was filed.
PLAYWRIGHT_KEEP = ("test-outcomes.json",)
# Transcripts kept (gzipped): the session that wrote the specs (agent), the heals, and the verifier.
TRANSCRIPTS_KEPT = ("heal-", "verify-", "agent-repair")
# The E2E User Journey stage of a ticket run keeps what ran, what failed and the bugs it filed.
E2E_KEEP = ("qa-result.json", "playwright", "bugs.json", "bugs.md", "bug-evidence", "verify.json", "summary.json")
# The checked-in cases a ticket's diff touches: what ran and what the heal said about them.
AFFECTED_KEEP = ("test-outcomes.json", "triage.json")


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
    if path.is_symlink() or target.is_symlink():
        return 0  # never compress or write through a link the agent planted
    try:
        before = path.stat().st_size
        with path.open("rb") as src, gzip.open(target, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
        path.unlink()
        return before - target.stat().st_size
    except OSError:
        return 0


def _transcript_kept(path: Path) -> bool:
    """agent.jsonl, heal-2.jsonl, verify-1-retry1.jsonl.gz yes; promote, ux-audit no."""
    stem = path.name.split(".", 1)[0].split("-retry", 1)[0]
    return stem == "agent" or stem.startswith(TRANSCRIPTS_KEPT)


def _heavy(playwright: Path) -> int:
    freed = 0
    for name in PLAYWRIGHT_HEAVY:
        freed += _remove(playwright / name)
    for pattern in HEAVY_FILES:
        for path in playwright.rglob(pattern):
            freed += _remove(path)
    return freed


def _keep_only(folder: Path, names: tuple[str, ...]) -> int:
    freed = 0
    for child in folder.iterdir() if folder.is_dir() else []:
        if child.name not in names and not child.name.startswith("triage"):
            freed += _remove(child)
    return freed


def _playwright(folder: Path) -> int:
    playwright = folder / "playwright"
    return _keep_only(playwright, PLAYWRIGHT_KEEP) if playwright.is_dir() else 0


def _opencode(folder: Path) -> int:
    freed = 0
    opencode = folder / "opencode"
    if not opencode.is_dir():
        return 0
    for child in opencode.iterdir():
        if child.is_dir() or not child.name.endswith((".jsonl", ".jsonl.gz")) or not _transcript_kept(child):
            freed += _remove(child)
    for path in opencode.glob("*.jsonl"):
        freed += _gzip(path)
    return freed


def prune_run(folder: Path, *, finished: bool = True) -> int:
    """Bytes freed. `finished` is False for a halted or failed run: only Playwright's heavy output goes."""
    freed = 0
    for playwright in (folder / "playwright", folder / "e2e" / "playwright", folder / "affected" / "playwright"):
        if playwright.is_dir():
            freed += _heavy(playwright)
    if not finished:
        return freed
    # A sealed run takes no more lookups, so its allow-list goes too.
    guard = Path(os.getenv("QA_GUARD_DIR") or get_settings().root / ".lookup-guard") / f"{folder.name}.json"
    guard.unlink(missing_ok=True)
    for pattern in ALWAYS:
        for path in folder.glob(pattern):
            freed += _remove(path)
    if (folder / "linear-report.md").is_file():
        # linear-report.md is the one report. Older runs also wrote report.md.
        freed += _remove(folder / "report.md")
    explore = folder / "explore"
    if explore.is_dir():
        for pattern in EXPLORE_SCRATCH:
            for path in explore.glob(pattern):
                freed += _remove(path)
    freed += _playwright(folder)
    freed += _opencode(folder)
    e2e = folder / "e2e"
    if e2e.is_dir():
        freed += _keep_only(e2e, E2E_KEEP)
        freed += _playwright(e2e)
    affected = folder / "affected"
    if affected.is_dir():
        freed += _keep_only(affected, AFFECTED_KEEP)
    # An empty folder says nothing.
    for sub in (explore, folder / "opencode", folder / "playwright", e2e, affected):
        if sub.is_dir() and not any(sub.iterdir()):
            sub.rmdir()
    return freed


def mib(size: int) -> str:
    return f"{size / 1048576:.1f} MiB"
