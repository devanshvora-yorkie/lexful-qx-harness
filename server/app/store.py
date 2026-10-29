"""One index for every run.

E2E User Journey TCs live in runs/phase-1/. Feature Specific TCs live in runs/tickets/<ticket>/.
The folder name is the UTC start time plus the final counts once the run finishes.
The id stays stable for the API. Older paths under runs/regression/ and runs/LEX-*/
remain as links so a run that is already open still resolves.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.settings import get_settings


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def runs_root() -> Path:
    root = get_settings().runs
    root.mkdir(parents=True, exist_ok=True)
    return root


_GROUP = re.compile(r"^(LEX-\d+|pr-\d+|sha-[0-9a-fA-F]+|specs|manual|tools|regression)")


def run_group(run_id: str) -> str:
    match = _GROUP.match(run_id)
    return match.group(1) if match else "manual"


def _legacy_path(run_id: str) -> Path:
    """Where this id lived before phase-1/ and tickets/ existed."""
    flat = runs_root() / run_id
    nested = runs_root() / run_group(run_id) / run_id
    if flat.is_dir() and not nested.exists():
        return flat
    return nested


def run_dir(run_id: str) -> Path:
    """The folder recorded on the run, or the older runs/<group>/<id>/ path."""
    for row in _read_index()["runs"]:
        if row.get("id") == run_id and row.get("folder"):
            return runs_root() / str(row["folder"])
    return _legacy_path(run_id)


def relative_folder(
    row: dict[str, Any],
    *,
    summary: dict[str, Any] | None = None,
    verdict: str | None = None,
) -> str:
    """Readable path relative to runs/. Counts are added when the run has finished."""
    created = str(row.get("createdAt") or "")
    day = created[:10] if len(created) >= 10 else "unknown-date"
    clock = created[11:16].replace(":", "") if len(created) >= 16 else "0000"
    short = str(row.get("id") or "run").rsplit("-", 1)[-1]
    name = f"{day}_{clock}Z_{short}"
    score = _score_label(summary, verdict, str(row.get("status") or ""))
    if score:
        name = f"{name}_{score}"
    kind = row.get("kind") or "ticket"
    if kind == "phase1":
        return f"phase-1/{name}"
    ticket = row.get("ticket")
    if ticket:
        return f"tickets/{ticket}/{name}"
    pr = row.get("pr")
    if pr:
        return f"pull-requests/pr-{pr}/{name}"
    return f"manual/{name}"


def _score_label(summary: dict[str, Any] | None, verdict: str | None, status: str) -> str:
    parts: list[str] = []
    if isinstance(summary, dict) and ("passed" in summary or "failed" in summary):
        parts.append(f"{int(summary.get('passed') or 0)}-passed")
        parts.append(f"{int(summary.get('failed') or 0)}-failed")
        flaky = int(summary.get("flaky") or 0)
        skipped = int(summary.get("skipped") or 0)
        if flaky:
            parts.append(f"{flaky}-flaky")
        if skipped:
            parts.append(f"{skipped}-skipped")
    label = (verdict or status or "").strip().lower().replace("_", "-")
    if label and label not in {"accepted", "queued", "preflight", "agent", "execute", "heal"}:
        parts.append(label)
    return "_".join(parts)


def _index_path() -> Path:
    return runs_root() / "index.json"


def _locked(mutator):
    root = runs_root()
    lock = root / "index.lock"
    for _ in range(50):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > 15:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            time.sleep(0.04)
            continue
        try:
            return mutator()
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)
    raise TimeoutError("runs/index.json stayed locked")


def _read_index() -> dict[str, Any]:
    file = _index_path()
    if not file.is_file():
        return {"runs": []}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"runs": []}
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return {"runs": []}
    return data


def _write_index(data: dict[str, Any]) -> None:
    file = _index_path()
    file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def update_run(run_id: str, **fields: Any) -> dict[str, Any]:
    def mutate() -> dict[str, Any]:
        data = _read_index()
        found = None
        for row in data["runs"]:
            if row.get("id") == run_id:
                row.update(fields)
                row["updatedAt"] = _now()
                found = row
                break
        if found is None:
            raise KeyError(run_id)
        _write_index(data)
        _write_manifest(found)
        return dict(found)

    return _locked(mutate)


def _write_manifest(row: dict[str, Any], folder: Path | None = None) -> None:
    folder = folder or run_dir(str(row["id"]))
    folder.mkdir(parents=True, exist_ok=True)
    manifest = folder / "manifest.json"
    current: dict[str, Any] = {}
    if manifest.is_file():
        try:
            loaded = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except json.JSONDecodeError:
            current = {}
    current.update(row)
    manifest.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


def create_run(
    *,
    ticket: str | None,
    pr: int | None,
    sha: str | None,
    kind: str = "ticket",
) -> dict[str, Any]:
    label = "regression" if kind == "phase1" else ticket or (f"pr-{pr}" if pr else "manual")
    run_id = f"{label}-{_stamp()}-{os.urandom(2).hex()}"
    now = _now()
    row = {
        "id": run_id,
        "kind": kind,
        "ticket": None if kind == "phase1" else ticket,
        "pr": pr,
        "sha": sha,
        "status": "accepted",
        "createdAt": now,
        "updatedAt": now,
        "models": {
            "main": get_settings().main_model,
            "subagents": get_settings().sub_model,
        },
        "healAttempts": 0,
        "opencodeSession": None,
        "error": None,
    }
    row["folder"] = relative_folder(row)

    def mutate() -> dict[str, Any]:
        data = _read_index()
        data["runs"].insert(0, row)
        _write_index(data)
        folder = runs_root() / str(row["folder"])
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "opencode").mkdir(exist_ok=True)
        (folder / "playwright").mkdir(exist_ok=True)
        if kind != "phase1":
            (folder / "explore").mkdir(exist_ok=True)
            (folder / "specs").mkdir(exist_ok=True)
        _write_contents(folder, row)
        _write_guide()
        _write_manifest(row, folder)
        return dict(row)

    return _locked(mutate)


def publish_folder(
    run_id: str,
    *,
    summary: dict[str, Any] | None,
    verdict: str | None,
) -> str:
    """Rename the run folder so the directory name includes the final counts."""

    def mutate() -> str:
        data = _read_index()
        found = None
        for row in data["runs"]:
            if row.get("id") == run_id:
                found = row
                break
        if found is None:
            raise KeyError(run_id)
        target_rel = relative_folder(found, summary=summary, verdict=verdict)
        current = runs_root() / str(found["folder"]) if found.get("folder") else _legacy_path(run_id)
        target = runs_root() / target_rel
        if current.exists() and _same_path(current, target) is False:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise FileExistsError(target_rel)
            current.rename(target)
        target.mkdir(parents=True, exist_ok=True)
        found["folder"] = target_rel
        _write_index(data)
        _write_contents(target, found)
        _write_manifest(found, target)
        _write_guide()
        return target_rel

    return _locked(mutate)


def relocate_legacy_runs() -> list[str]:
    """Move finished runs into phase-1/ and tickets/. Leave the old path as a link."""

    def mutate() -> list[str]:
        data = _read_index()
        moved: list[str] = []
        active = {"accepted", "queued", "preflight", "agent", "execute", "heal"}
        for row in data["runs"]:
            if row.get("status") in active or not row.get("id"):
                continue
            if _relocate_row(row):
                moved.append(str(row["id"]))
        _write_index(data)
        _write_guide()
        return moved

    return _locked(mutate)


def _same_path(left: Path, right: Path) -> bool:
    if left.exists() and right.exists():
        return left.resolve() == right.resolve()
    return left.resolve() == right.resolve() and left.exists()


def _relocate_row(row: dict[str, Any]) -> bool:
    run_id = str(row["id"])
    had_folder = bool(row.get("folder"))
    current = runs_root() / str(row["folder"]) if had_folder else _legacy_path(run_id)
    if current.is_symlink() or not current.is_dir():
        return False
    summary, verdict = _saved_outcome(current)
    if verdict is None and row.get("status") in {"failed", "halted"}:
        verdict = str(row["status"]).upper()
    target_rel = relative_folder(row, summary=summary, verdict=verdict)
    target = runs_root() / target_rel
    if current.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return False
        current.rename(target)
    before = row.get("folder")
    row["folder"] = target_rel
    _write_contents(target, row)
    _write_manifest(row, target)
    legacy = _legacy_path(run_id)
    if not had_folder and not legacy.exists():
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to(os.path.relpath(target, legacy.parent), target_is_directory=True)
    return before != target_rel


def _saved_outcome(folder: Path) -> tuple[dict[str, Any] | None, str | None]:
    path = folder / "qa-result.json"
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    summary = data.get("test_results") if isinstance(data.get("test_results"), dict) else None
    verdict = data.get("verdict") if isinstance(data.get("verdict"), str) else None
    return summary, verdict


_PHASE1_CONTENTS = """\
This folder is one E2E User Journey TCs attempt. It runs the checked-in specs in "e2e test cases" against UAT.

The specs are not copied here. When a locator is healed, the edit is written into "e2e test cases/" in the repo. This folder only records what happened on this attempt.

contents.txt       this note
report.md          final counts and what the healer decided
run.log            the full log, one line per event
qa-result.json     passed, failed, skipped, and flaky counts
manifest.json      status, model, heal count, and timestamps
preflight.json     sign-in and toolchain checks
triage-N.json      healer classification for heal N: spec drift, or a product bug
bugs.md            product bugs for this attempt, when a failure remains
playwright/        results.json, output.log, and a screenshot when a test fails
opencode/          the agent session and the healer transcript
"""

_TICKET_CONTENTS = """\
This folder is one Feature Specific TCs attempt.

The specs written for this attempt stay in specs/. They are not copied into "e2e test cases/" by this run.

contents.txt         this note
report.md            final counts
run.log              the full log, one line per event
qa-result.json       passed, failed, skipped, and flaky counts
manifest.json        status, model, heal count, and timestamps
preflight.json       sign-in, Linear, and GitHub checks
context-pack.json    ticket, pull request, and files gathered before the agent
e2e-coverage.md      checked-in search, asset crud, and document editing cases already run
FEATURE.md           what the explorer observed on UAT, and which of those cases are new
bugs.md              product bugs for this attempt, when a failure remains
planned-specs.json   spec files the agent planned
specs/               specs written for this ticket
explore/             browser snapshots
ux-report.html       UI review, when that switch is on
ux-findings.json     findings behind the UI review
ux-scorecard.json    score and verdict for the UI review
e2e/run.log          E2E User Journey log from the journey run that preceded this attempt
e2e/report.md        that journey run's verdict
playwright/          results.json, output.log, and a screenshot when a test fails
opencode/            the agent session and subagent transcripts
"""

_GUIDE = """\
Where a run is stored

phase-1/
  E2E User Journey TCs. One folder per run of the checked-in suite in "e2e test cases".
  The name is the UTC start time, then the result.
  Example: 2026-10-23_1147Z_f35a_57-passed_2-failed_needs-revision
  Open report.md in that folder for the healer notes.

tickets/
  Feature Specific TCs. One folder per Linear ticket, then one folder per attempt.
  Example: tickets/LEX-2293/2026-10-21_1021Z_1722_18-passed_0-failed_perfect
  e2e/run.log in that folder is a copy of the E2E User Journey log.

pull-requests/
  A run started from a pull request number, when there is no ticket.

manual/
  Anything else.

cache/stytch/session.json
  The saved login. Shared by every run. Not a test result.

index.json
  The list the server uses. Each row has an id and a folder.

regression/ and LEX-*/
  Older paths. They are links to the folders above, so a file that is already open still resolves.
  Read phase-1/ and tickets/.

Inside a run, open contents.txt for what each file is.

A locator heal is written into "e2e test cases/" in the repo. The run folder keeps the triage note.
The spec Playwright runs next is the file in "e2e test cases/", not a copy inside the run.
"""


def _write_contents(folder: Path, row: dict[str, Any]) -> None:
    text = _PHASE1_CONTENTS if row.get("kind") == "phase1" else _TICKET_CONTENTS
    (folder / "contents.txt").write_text(text, encoding="utf-8")


def _write_guide() -> None:
    (runs_root() / "START-HERE.txt").write_text(_GUIDE, encoding="utf-8")


def get_run(run_id: str) -> dict[str, Any] | None:
    for row in _read_index()["runs"]:
        if row.get("id") == run_id:
            return dict(row)
    return None


def list_runs(ticket: str | None = None) -> list[dict[str, Any]]:
    rows = [dict(row) for row in _read_index()["runs"]]
    if ticket:
        key = ticket.upper()
        rows = [row for row in rows if str(row.get("ticket") or "").upper() == key]
    return rows


_E2E_LOG_FILES = ("run.log", "report.md", "qa-result.json", "bugs.md")
_FINISHED = {"completed", "needs_revision", "halted", "failed"}


def latest_finished_phase1() -> dict[str, Any] | None:
    """Newest E2E User Journey run that has a log. The index is newest first."""
    for row in list_runs():
        if row.get("kind") != "phase1" or row.get("status") not in _FINISHED:
            continue
        if (run_dir(str(row["id"])) / "run.log").is_file():
            return dict(row)
    return None


def _copy_e2e_log(source: Path, into: Path, phase1_id: str) -> bool:
    if not (source / "run.log").is_file():
        return False
    dest = into / "e2e"
    if (dest / "run.log").is_file():
        return False
    dest.mkdir(parents=True, exist_ok=True)
    for name in _E2E_LOG_FILES:
        src = source / name
        if src.is_file():
            shutil.copyfile(src, dest / name)
    folder = ""
    row = get_run(phase1_id)
    if row and row.get("folder"):
        folder = str(row["folder"])
    (dest / "source.txt").write_text(
        "E2E User Journey TCs. Copied from runs/" + (folder or source.name) + "\n",
        encoding="utf-8",
    )
    return True


def share_e2e_log(phase1_id: str) -> list[str]:
    """Copy the finished journey log into ticket attempts that are still waiting."""
    source = run_dir(phase1_id)
    copied: list[str] = []
    waiting = {"accepted", "queued"}
    for row in list_runs():
        folder = str(row.get("folder") or "")
        if row.get("kind") == "phase1" or not folder.startswith("tickets/"):
            continue
        if row.get("status") not in waiting:
            continue
        if _copy_e2e_log(source, runs_root() / folder, phase1_id):
            copied.append(str(row["id"]))
    return copied


def attach_e2e_log(ticket_folder: Path) -> bool:
    """Copy the latest journey log into this ticket attempt when it starts."""
    if (ticket_folder / "e2e" / "run.log").is_file():
        return False
    phase1 = latest_finished_phase1()
    if phase1 is None:
        return False
    return _copy_e2e_log(run_dir(str(phase1["id"])), ticket_folder, str(phase1["id"]))


def find_active_phase1() -> dict[str, Any] | None:
    """A checked-in suite run that has not finished. A second trigger follows this one."""
    active = {"accepted", "queued", "preflight", "agent", "execute", "heal"}
    for row in _read_index()["runs"]:
        if row.get("kind") == "phase1" and row.get("status") in active:
            return dict(row)
    return None


def find_running_run() -> dict[str, Any] | None:
    """Run the worker is executing now (not merely queued)."""
    running = {"preflight", "agent", "execute", "heal"}
    for row in _read_index()["runs"]:
        if row.get("status") in running:
            return dict(row)
    return None


def find_active_sha(sha: str) -> dict[str, Any] | None:
    """Skip a sha that is already running or already finished cleanly. A needs-revision run can be tried again."""
    closed = {"failed", "halted", "needs_revision"}
    for row in _read_index()["runs"]:
        if row.get("sha") == sha and row.get("status") not in closed:
            return dict(row)
    return None


def _write_halted(run_id: str, reason: str) -> None:
    """Write a minimal report when a run stops without a normal verdict."""
    row = get_run(run_id) or {}
    folder = run_dir(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "report.md").write_text(
        "\n".join([
            f"# {row.get('ticket') or run_id}",
            "",
            "- Status: failed",
            "- Verdict: HALTED",
            "",
            reason,
            "",
        ]),
        encoding="utf-8",
    )
    (folder / "qa-result.json").write_text(
        json.dumps(
            {
                "ticket_id": row.get("ticket"),
                "run_id": run_id,
                "verdict": "HALTED",
                "test_results": {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0},
                "open_issues": [reason],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    publish_folder(run_id, summary=None, verdict=None)


def _write_interrupted(run_id: str) -> None:
    _write_halted(run_id, "The server restarted during the run. This attempt has no finished suite verdict.")


_ACTIVE_RUN = {"accepted", "queued", "preflight", "agent", "execute", "heal"}


def cancel_all_runs(reason: str = "cancelled by user") -> list[str]:
    """Mark every in-flight or queued run as failed and write a halt report."""
    from app.logbook import Logbook

    stopped: list[str] = []
    for row in list(list_runs()):
        run_id = str(row.get("id") or "")
        if not run_id or row.get("status") not in _ACTIVE_RUN:
            continue
        folder = run_dir(run_id)
        Logbook(folder).row("server", "cancelled", reason[:220])
        update_run(run_id, status="failed", error=reason[:500])
        _write_halted(run_id, reason)
        stopped.append(run_id)
    return stopped


def recover_runs() -> list[str]:
    """After a restart, fail runs that were mid-flight and return the ones still waiting to start."""
    interrupted = {"preflight", "agent", "execute", "heal"}
    waiting = {"accepted", "queued"}
    requeue: list[str] = []
    for row in reversed(list_runs()):
        status = row.get("status")
        run_id = str(row.get("id") or "")
        if not run_id:
            continue
        if status in interrupted:
            update_run(run_id, status="failed", error="server restarted during the run")
            _write_interrupted(run_id)
        elif status in waiting:
            requeue.append(run_id)
    return requeue
