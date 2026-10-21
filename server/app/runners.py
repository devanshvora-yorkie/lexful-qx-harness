"""Subprocess runners. OpenCode never receives the Stytch, Linear, or GitHub secrets."""

from __future__ import annotations

import fcntl
import json
import os
import pty
import select
import signal
import struct
import subprocess
import termios
import time
from pathlib import Path
from typing import Any

from app.logbook import Logbook, SubagentTail
from app.settings import SECRET_ENV, get_settings


def _opencode_env(run_dir: Path) -> dict[str, str]:
    settings = get_settings()
    env = os.environ.copy()
    for key in SECRET_ENV:
        env.pop(key, None)
    env["OPENCODE_MAIN_MODEL"] = settings.main_model
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["QA_RUN_DIR"] = str(run_dir)
    env["AUTH_STATE"] = str(run_dir / "auth-state.json")
    return env


def _playwright_env(run_dir: Path) -> dict[str, str]:
    settings = get_settings()
    env = os.environ.copy()
    env["QA_RUN_DIR"] = str(run_dir)
    env["AUTH_STATE"] = str(run_dir / "auth-state.json")
    env["QA_ENV_URL"] = settings.qa_url
    return env


def reload_opencode() -> None:
    """The background server is what loads project agents. A private --standalone server does not."""
    settings = get_settings()
    subprocess.run(
        ["opencode", "reload"],
        cwd=settings.root,
        env=_opencode_env(settings.root),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def last_opencode_error(run_dir: Path, log_name: str) -> str:
    path = run_dir / "opencode" / log_name
    if not path.is_file():
        return ""
    message = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict) and error.get("message"):
            message = str(error["message"]).split("\n", 1)[0][:300]
    return message


def run_opencode(run_dir: Path, *, session_id: str, prompt: str, title: str, log_name: str) -> int:
    """Run OpenCode on a terminal so each JSON line is flushed into run.log immediately."""
    settings = get_settings()
    reload_opencode()
    book = Logbook(run_dir)
    tail = SubagentTail(session_id, book)
    log_path = run_dir / "opencode" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "opencode",
        "run",
        "--format",
        "json",
        "--session",
        session_id,
        "--agent",
        "qa",
        "--model",
        settings.main_model,
        "--title",
        title,
        "--auto",
        prompt,
    ]
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 200, 400, 0, 0))
    process = subprocess.Popen(
        command,
        cwd=settings.root,
        env=_opencode_env(run_dir),
        stdout=slave,
        stderr=slave,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    os.close(slave)
    deadline = time.monotonic() + settings.agent_timeout_seconds
    pending = b""
    timed_out = False
    with log_path.open("w", encoding="utf-8") as handle:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                break
            ready, _, _ = select.select([master], [], [], min(1.0, remaining))
            tail.poll()
            if not ready:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 8192)
            except OSError:
                break
            if not chunk:
                break
            pending += chunk
            while b"\n" in pending:
                raw, pending = pending.split(b"\n", 1)
                text = raw.decode("utf-8", errors="replace").replace("\r", "")
                handle.write(text + "\n")
                handle.flush()
                book.event(text)
        if pending.strip():
            text = pending.decode("utf-8", errors="replace").replace("\r", "")
            handle.write(text + "\n")
            handle.flush()
            book.event(text)
        if timed_out:
            handle.write("opencode timed out\n")
            book.row("qa", "error", "opencode timed out")
    os.close(master)
    tail.poll()
    tail.write_index(run_dir / "opencode" / "children.json")
    export_children(run_dir, tail.children, book)
    try:
        return 124 if timed_out else process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        return 124


def export_children(run_dir: Path, children: list[dict[str, Any]], book: Logbook) -> None:
    """Keep each subagent transcript in the run folder. The parent export does not include them."""
    pending = []
    dest = run_dir / "opencode" / "children"
    for child in children:
        session_id = str(child.get("id") or "")
        agent = str(child.get("agent") or "subagent")
        if session_id and not (dest / f"{agent}-{session_id}.json").is_file():
            pending.append(child)
    if not pending:
        return
    book.row("server", "export", f"{len(pending)} subagent transcript(s)")
    settings = get_settings()
    dest.mkdir(parents=True, exist_ok=True)
    for child in pending:
        session_id = str(child.get("id") or "")
        agent = str(child.get("agent") or "subagent")
        target = dest / f"{agent}-{session_id}.json"
        if target.is_file() and target.stat().st_size > 0:
            continue
        result = subprocess.run(
            ["opencode", "session", "export", session_id],
            cwd=settings.root,
            env=_opencode_env(run_dir),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            target.write_text(result.stdout, encoding="utf-8")
            continue
        book.row("server", "error", f"could not export {agent} {session_id}")


def export_session(run_dir: Path, session_id: str) -> None:
    settings = get_settings()
    result = subprocess.run(
        ["opencode", "session", "export", session_id],
        cwd=settings.root,
        env=_opencode_env(run_dir),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    target = run_dir / "opencode" / "session.json"
    if result.returncode == 0 and result.stdout.strip():
        target.write_text(result.stdout, encoding="utf-8")
        return
    note = {
        "exported": False,
        "exitCode": result.returncode,
        "stderr": (result.stderr or "")[:2000],
    }
    target.write_text(json.dumps(note, indent=2) + "\n", encoding="utf-8")


def run_preflight(run_dir: Path, *, ticket: str | None, pr: int | None, sha: str | None) -> int:
    settings = get_settings()
    command = ["node", "scripts/preflight.mjs", "--out", str(run_dir)]
    if ticket:
        command.append(ticket)
    elif pr:
        command.extend(["--pr", str(pr)])
    elif sha:
        command.extend(["--sha", sha])
    log_path = run_dir / "preflight.log"
    env = os.environ.copy()
    env["QA_RUN_DIR"] = str(run_dir)
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.run(
            command,
            cwd=settings.root,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return process.returncode


def run_playwright(run_dir: Path, specs: list[str]) -> dict[str, Any]:
    settings = get_settings()
    log_path = run_dir / "playwright" / "output.log"
    command = ["npx", "playwright", "test", "--workers=1", *specs]
    with log_path.open("w", encoding="utf-8") as handle:
        process = subprocess.run(
            command,
            cwd=settings.root,
            env=_playwright_env(run_dir),
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    return {"exitCode": process.returncode, "summary": read_playwright_summary(run_dir)}


def read_playwright_summary(run_dir: Path) -> dict[str, int]:
    report = run_dir / "playwright" / "results.json"
    empty = {"passed": 0, "failed": 0, "skipped": 0, "flaky": 0}
    if not report.is_file():
        return empty
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return empty
    stats = payload.get("stats") if isinstance(payload, dict) else None
    if not isinstance(stats, dict):
        return empty
    return {
        "passed": int(stats.get("expected") or 0),
        "failed": int(stats.get("unexpected") or 0),
        "skipped": int(stats.get("skipped") or 0),
        "flaky": int(stats.get("flaky") or 0),
    }


def planned_specs(run_dir: Path, started_at: float) -> list[str]:
    settings = get_settings()
    for name in ("planned-specs.json", "qa-result.json"):
        file = run_dir / name
        if not file.is_file():
            continue
        try:
            payload = json.loads(file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        files = payload.get("test_files") if isinstance(payload, dict) else None
        if isinstance(files, list):
            existing = [str(item) for item in files if (settings.root / str(item)).is_file()]
            if existing:
                return existing
    found: list[str] = []
    tests = settings.root / "tests"
    if not tests.is_dir():
        return found
    for spec in tests.rglob("*.spec.ts"):
        if spec.stat().st_mtime >= started_at - 1:
            found.append(str(spec.relative_to(settings.root)))
    return found
