"""One index for every run.

A run's folder is chosen when the run is created and never moves or renames: everything the run
writes (its E2E User Journey stage in e2e/, the specs, the reports) stays in that one folder.
A run whose ticket is known when it starts (named, or read from its PR or deployed commit) lives in
runs/tickets/<ticket>/. Without a ticket it lives in pull-requests/, deploys/ or manual/.
runs/phase-1/ holds only E2E runs started on their own (npm run e2e).
The folder name is the UTC start time and a short id; the result is in manifest.json and index.json.
Older paths under runs/regression/ and runs/LEX-*/ remain as links so an old run still resolves.
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


def relative_folder(row: dict[str, Any]) -> str:
    """Path relative to runs/, fixed when the run is created: <group>/<UTC day>_<time>Z_<short id>."""
    created = str(row.get("createdAt") or "")
    day = created[:10] if len(created) >= 10 else "unknown-date"
    clock = created[11:16].replace(":", "") if len(created) >= 16 else "0000"
    short = str(row.get("id") or "run").rsplit("-", 1)[-1]
    name = f"{day}_{clock}Z_{short}"
    kind = row.get("kind") or "ticket"
    if kind == "phase1":
        return f"phase-1/{name}"
    ticket = row.get("ticket")
    if ticket:
        return f"tickets/{ticket}/{name}"
    pr = row.get("pr")
    if pr:
        return f"pull-requests/pr-{pr}/{name}"
    sha = str(row.get("sha") or "")
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", sha):
        return f"deploys/{sha[:12].lower()}/{name}"
    return f"manual/{name}"


def result_label(summary: dict[str, Any] | None, verdict: str | None) -> str:
    """`11 passed, 0 failed, needs revision`: the outcome as one phrase for the index and the manifest."""
    parts: list[str] = []
    if isinstance(summary, dict) and ("passed" in summary or "failed" in summary):
        parts.append(f"{int(summary.get('passed') or 0)} passed")
        parts.append(f"{int(summary.get('failed') or 0)} failed")
        for key in ("flaky", "skipped"):
            if int(summary.get(key) or 0):
                parts.append(f"{int(summary[key])} {key}")
    if verdict:
        parts.append(verdict.strip().lower().replace("_", " "))
    return ", ".join(parts)


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


def _parse_index(file: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        return None
    return data


def _read_index() -> dict[str, Any]:
    """A damaged index is never read as empty: the next write would erase every run."""
    file = _index_path()
    if not file.is_file():
        return {"runs": []}
    data = _parse_index(file)
    if data is not None:
        return data
    backup = file.with_name("index.json.bak")
    data = _parse_index(backup) if backup.is_file() else None
    if data is not None:
        return data
    raise RuntimeError(f"{file} is not valid JSON and has no usable backup. Fix it by hand before starting runs.")


def write_atomic(file: Path, text: str) -> None:
    """Write beside the target, then rename over it, so a crash leaves the old file or the new one."""
    tmp = file.with_name(f".{file.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, file)


def _write_index(data: dict[str, Any]) -> None:
    file = _index_path()
    if file.is_file() and _parse_index(file) is not None:
        shutil.copyfile(file, file.with_name("index.json.bak"))
    write_atomic(file, json.dumps(data, indent=2) + "\n")


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
    write_atomic(manifest, json.dumps(current, indent=2) + "\n")


def create_run(
    *,
    ticket: str | None,
    pr: int | None,
    sha: str | None,
    kind: str = "ticket",
    trigger: str = "",
) -> dict[str, Any]:
    """`trigger` is what started the run: `ticket` (a person named it), `pr`, `uat-deploy` (the deploy webhook) or `e2e`."""
    label = "regression" if kind == "phase1" else ticket or (f"pr-{pr}" if pr else "manual")
    run_id = f"{label}-{_stamp()}-{os.urandom(2).hex()}"
    now = _now()
    row = {
        "id": run_id,
        "kind": kind,
        "ticket": None if kind == "phase1" else ticket,
        "pr": pr,
        "sha": sha,
        "trigger": trigger or ("e2e" if kind == "phase1" else "ticket" if ticket else "pr" if pr else "manual"),
        "status": "accepted",
        "createdAt": now,
        "updatedAt": now,
        "models": {"main": get_settings().main_model},
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
        _write_guide()
        _write_manifest(row, folder)
        return dict(row)

    return _locked(mutate)


def record_outcome(
    run_id: str,
    *,
    summary: dict[str, Any] | None,
    verdict: str | None,
) -> str:
    """Write the final result into the index and manifest.json. The folder stays where it is."""

    def mutate() -> str:
        data = _read_index()
        found = next((row for row in data["runs"] if row.get("id") == run_id), None)
        if found is None:
            raise KeyError(run_id)
        if not found.get("folder"):
            found["folder"] = relative_folder(found)
        found["result"] = result_label(summary, verdict)
        _write_index(data)
        _write_manifest(found, runs_root() / str(found["folder"]))
        return str(found["folder"])

    return _locked(mutate)


def relocate_legacy_runs() -> list[str]:
    """Give runs from before the index kept a folder their place under phase-1/ and tickets/.

    A run that already has a folder is never moved. A legacy one keeps a link at its old path.
    """

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


def _relocate_row(row: dict[str, Any]) -> bool:
    if row.get("folder"):
        return False
    run_id = str(row["id"])
    current = _legacy_path(run_id)
    if current.is_symlink() or not current.is_dir():
        return False
    summary, verdict = _saved_outcome(current)
    if verdict is None and row.get("status") in {"failed", "halted"}:
        verdict = str(row["status"]).upper()
    target_rel = relative_folder(row)
    target = runs_root() / target_rel
    if current.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            return False
        current.rename(target)
    row["folder"] = target_rel
    row["result"] = result_label(summary, verdict)
    _write_manifest(row, target)
    legacy = _legacy_path(run_id)
    if not legacy.exists():
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to(os.path.relpath(target, legacy.parent), target_is_directory=True)
    return True


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


_GUIDE = """\
Where a run is stored

A run is written into one folder, chosen when it starts. It is never moved or renamed, so a file you
have open stays where it is. The folder name is the UTC start time and a short id, for example
tickets/LEX-3642/2026-11-03_0928Z_bc40. The result is in index.json ("result"), manifest.json and
linear-report.md.

tickets/
  One folder per Linear ticket, then one folder per attempt. A run started from a pull request or
  a UAT deploy lands here too: its ticket is read from GitHub before the folder is made.
  An attempt holds the ticket's Feature Specific TCs and, in e2e/, the E2E User Journey TCs
  that ran against the same build.

phase-1/
  E2E User Journey TCs started on their own (npm run e2e), not by a ticket.

pull-requests/
  A run started from a pull request whose title, branch and body name no LEX ticket, or when
  GitHub could not be read at start.

deploys/<commit>/
  A run started from a UAT deploy whose commit has no pull request with a ticket.

manual/
  Anything else.

cache/stytch/session.json
  The saved login. Shared by every run. Not a test result.

index.json
  The list the server uses. Each row has an id and a folder.

regression/ and LEX-*/
  Older paths. They are links to the folders above, so a file that is already open still resolves.
  Read phase-1/ and tickets/.

Inside a run, open linear-report.md (or linear-report.html in a browser). It is the one report:
what triggered the run, the E2E and Feature Specific results, the bugs, and the UX audit's suggested
changes, with links to ux-report.html and the screenshots. bugs.md has each bug written as a ticket.
run.log is the timeline and ends with a run summary; summary.json holds the same data.

A sealed attempt keeps:
  linear-report.md, linear-report.html, ux-report.html     the reports
  bugs.json, bugs.md, bug-evidence/                         the bugs and their screenshots
  playwright/test-outcomes.json                             every test, its tags and its final result
  specs/, FEATURE.md, feature-map.md, explore/              what was tested and how
  coverage.json, hypotheses.json, triage-*.json, verify.json   the agent's hand-off and the heal notes
  e2e/                                                      the E2E stage: results, triage, bugs
  affected/test-outcomes.json                               the checked-in cases the diff touches
  opencode/*.jsonl.gz                                       transcripts of explore, heal and verify
A halted or failed attempt keeps everything, so it can be resumed or debugged.

A locator heal is written into "e2e test cases/" in the repo. The run folder keeps the triage note.
The spec Playwright runs next is the file in "e2e test cases/", not a copy inside the run.
"""


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


RUNNING = frozenset({"preflight", "agent", "execute", "heal", "audit", "verify", "promote"})


def find_active_phase1() -> dict[str, Any] | None:
    """A checked-in suite run that has not finished. A second trigger follows this one."""
    active = {"accepted", "queued", *RUNNING}
    for row in _read_index()["runs"]:
        if row.get("kind") == "phase1" and row.get("status") in active:
            return dict(row)
    return None


def find_running_runs() -> list[dict[str, Any]]:
    """Runs a worker is executing now (not merely queued)."""
    return [dict(row) for row in _read_index()["runs"] if row.get("status") in RUNNING]


def find_running_run() -> dict[str, Any] | None:
    running = find_running_runs()
    return running[0] if running else None


def find_active_sha(sha: str) -> dict[str, Any] | None:
    """Skip a sha that is already running or already finished cleanly. A needs-revision run can be tried again."""
    closed = {"failed", "halted", "needs_revision"}
    for row in _read_index()["runs"]:
        if row.get("sha") == sha and row.get("status") not in closed:
            return dict(row)
    return None


def _write_halted(run_id: str, reason: str) -> None:
    """Seal a run that stopped without a normal verdict: qa-result.json and the one report."""
    from app import linear_report
    from app.logbook import Logbook

    row = get_run(run_id) or {}
    folder = run_dir(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    book = Logbook(folder)
    book.line("── run summary")
    book.line(f"  {row.get('ticket') or run_id}  run {run_id}  verdict HALTED")
    book.line(f"  stopped: {reason[:200]}")
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
    linear_report.write(folder, row, verdict="HALTED", issues=[reason])
    record_outcome(run_id, summary=None, verdict="HALTED")


def _write_interrupted(run_id: str, phase: str = "") -> None:
    where = f" while it was in {phase}" if phase else ""
    _write_halted(run_id, f"The server restarted during the run{where}. This attempt has no finished suite verdict.")


_ACTIVE_RUN = {"accepted", "queued", *RUNNING}


def cancel_all_runs(reason: str = "cancelled by user", *, skip: set[str] | None = None) -> list[str]:
    """Mark every queued run, and every in-flight run not in `skip`, as failed with a halt report.

    A run a worker is executing is in `skip`: the worker stops its processes and seals it,
    so a halt report is not written under a process that is still writing into the folder.
    """
    from app.logbook import Logbook

    stopped: list[str] = []
    for row in list(list_runs()):
        run_id = str(row.get("id") or "")
        if not run_id or row.get("status") not in _ACTIVE_RUN or run_id in (skip or set()):
            continue
        folder = run_dir(run_id)
        Logbook(folder).row("server", "cancelled", reason[:220])
        update_run(run_id, status="failed", error=reason[:500])
        _write_halted(run_id, reason)
        stopped.append(run_id)
    return stopped


def recover_runs() -> list[str]:
    """After a restart, fail runs that were mid-flight and return the ones still waiting to start."""
    interrupted = RUNNING
    waiting = {"accepted", "queued"}
    requeue: list[str] = []
    for row in reversed(list_runs()):
        status = row.get("status")
        run_id = str(row.get("id") or "")
        if not run_id:
            continue
        if status in interrupted:
            update_run(run_id, status="failed", error=f"server restarted during the run ({status})")
            _write_interrupted(run_id, str(status))
        elif status in waiting:
            requeue.append(run_id)
    return requeue
