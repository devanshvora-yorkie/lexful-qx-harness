"""One index for every run. Folders live under runs/<ticket>/<run-id>/."""

from __future__ import annotations

import json
import os
import re
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


_GROUP = re.compile(r"^(LEX-\d+|pr-\d+|sha-[0-9a-fA-F]+|specs|manual|tools)")


def run_group(run_id: str) -> str:
    match = _GROUP.match(run_id)
    return match.group(1) if match else "manual"


def run_dir(run_id: str) -> Path:
    """New runs live at runs/<ticket>/<run-id>/. Older flat runs/<run-id>/ folders still resolve."""
    flat = runs_root() / run_id
    nested = runs_root() / run_group(run_id) / run_id
    if flat.is_dir() and not nested.is_dir():
        return flat
    return nested


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


def _write_manifest(row: dict[str, Any]) -> None:
    folder = run_dir(str(row["id"]))
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


def create_run(*, ticket: str | None, pr: int | None, sha: str | None, spec_count: int | None) -> dict[str, Any]:
    label = ticket or (f"pr-{pr}" if pr else "manual")
    run_id = f"{label}-{_stamp()}-{os.urandom(2).hex()}"
    now = _now()
    row = {
        "id": run_id,
        "ticket": ticket,
        "pr": pr,
        "sha": sha,
        "specCount": spec_count,
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

    def mutate() -> dict[str, Any]:
        data = _read_index()
        data["runs"].insert(0, row)
        _write_index(data)
        folder = run_dir(run_id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "opencode").mkdir(exist_ok=True)
        (folder / "playwright").mkdir(exist_ok=True)
        (folder / "explore").mkdir(exist_ok=True)
        (folder / "specs").mkdir(exist_ok=True)
        _write_manifest(row)
        return dict(row)

    return _locked(mutate)


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


def find_active_sha(sha: str) -> dict[str, Any] | None:
    """Skip a sha that is already running or already finished cleanly. A needs-revision run can be tried again."""
    closed = {"failed", "halted", "needs_revision"}
    for row in _read_index()["runs"]:
        if row.get("sha") == sha and row.get("status") not in closed:
            return dict(row)
    return None


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
        elif status in waiting:
            requeue.append(run_id)
    return requeue
