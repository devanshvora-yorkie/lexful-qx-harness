"""Subprocess runners. OpenCode never receives the Stytch, Linear, or GitHub secrets."""

from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import select
import signal
import sqlite3
import struct
import subprocess
import termios
import time
from pathlib import Path
from typing import Any

from app.logbook import Logbook, SubagentTail, plain, row, session_id_from_text
from app.settings import SECRET_ENV, get_settings


def session_state_path() -> Path:
    """Default persona cookie file. A named persona lives beside it as <persona>.json."""
    return get_settings().root / "runs" / "cache" / "stytch" / "session.json"


_PERSONA_ARG = re.compile(
    r"injectAuthCookies\(\s*[^,]+,\s*['\"](admin|support|viewer)['\"]",
    re.IGNORECASE,
)


def personas_requested(specs: list[str]) -> list[str]:
    """Personas a spec asks for by name. The default session is signed in separately."""
    root = get_settings().root
    found: list[str] = []
    default = (os.environ.get("STYTCH_PERSONA") or "admin").strip().lower() or "admin"
    for spec in specs:
        path = Path(spec)
        if not path.is_file():
            path = root / spec
        if not path.is_file():
            continue
        for name in _PERSONA_ARG.findall(path.read_text(encoding="utf-8", errors="replace")):
            persona = name.lower()
            if persona != default and persona not in found:
                found.append(persona)
    return found


def _session_expired(log_text: str) -> bool:
    lowered = log_text.lower()
    return "stytch session expired" in lowered or "landed on login" in lowered


def _bedrock_token() -> str:
    return (os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or os.environ.get("BEDROCK_API_KEY") or "").strip()


def _opencode_env(run_dir: Path) -> dict[str, str]:
    settings = get_settings()
    env = os.environ.copy()
    for key in (*SECRET_ENV, "OPENROUTER_API_KEY", "BEDROCK_API_KEY"):
        env.pop(key, None)
    token = _bedrock_token()
    if token:
        env["AWS_BEARER_TOKEN_BEDROCK"] = token
    env["AWS_REGION"] = (os.environ.get("AWS_REGION") or "us-east-1").strip() or "us-east-1"
    env["OPENCODE_MAIN_MODEL"] = settings.main_model
    env["OPENCODE_SUB_MODEL"] = settings.sub_model
    env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
    env["QA_RUN_DIR"] = str(run_dir)
    env["AUTH_STATE"] = str(session_state_path())
    return env


def _playwright_env(run_dir: Path) -> dict[str, str]:
    """Playwright runs model-written specs, so it does not inherit API keys or passwords.

    Cookies are read from runs/cache/stytch/session.json. A spec that prints process.env cannot see the secrets.
    """
    settings = get_settings()
    env = os.environ.copy()
    for key in (*SECRET_ENV, "OPENROUTER_API_KEY", "BEDROCK_API_KEY", "AWS_BEARER_TOKEN_BEDROCK"):
        env.pop(key, None)
    env["QA_RUN_DIR"] = str(run_dir)
    env["AUTH_STATE"] = str(session_state_path())
    env["QA_ENV_URL"] = settings.qa_url
    return env


def ensure_session(*, fresh: bool = False, persona: str | None = None) -> tuple[int, str]:
    """Sign in as one persona. The server process still has the password."""
    settings = get_settings()
    name = (persona or os.environ.get("STYTCH_PERSONA") or "admin").strip().lower() or "admin"
    if name not in {"admin", "support", "viewer"}:
        return 1, f"persona must be admin, support, or viewer. Got {name}"
    env = os.environ.copy()
    env["PERSONA_DIRECT"] = "1"
    command = ["node", "scripts/persona.mjs", name]
    if fresh:
        command.append("--fresh")
    process = subprocess.run(
        command,
        cwd=settings.root,
        env=env,
        capture_output=True,
        text=True,
    )
    detail = (process.stderr or process.stdout or "").strip().splitlines()
    return process.returncode, (detail[-1] if detail else "")[:220]


def last_opencode_error(run_dir: Path, log_name: str) -> str:
    path = run_dir / "opencode" / log_name
    if not path.is_file():
        return ""
    message = ""
    plain_line = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        cleaned = plain(line)
        if not cleaned:
            continue
        if cleaned.startswith("{"):
            try:
                payload = json.loads(cleaned)
            except json.JSONDecodeError:
                payload = None
            error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(error, dict) and error.get("message"):
                message = str(error["message"]).split("\n", 1)[0][:300]
            elif isinstance(error, str) and error.strip():
                message = error.split("\n", 1)[0][:300]
            continue
        lowered = cleaned.lower()
        if lowered.startswith("error") or "not found" in lowered:
            plain_line = cleaned.split("\n", 1)[0][:300]
    return message or plain_line


def _recent_root_session(started_ms: int) -> str:
    database = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
    if not database.is_file():
        return ""
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1)
    except sqlite3.Error:
        return ""
    try:
        names = {item[0] for item in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        table = "session_v2" if "session_v2" in names else "session" if "session" in names else ""
        if not table:
            return ""
        found = connection.execute(
            f"""
            SELECT id FROM {table}
            WHERE parent_id IS NULL AND time_created >= ?
            ORDER BY time_created DESC
            LIMIT 1
            """,
            (started_ms - 2_000,),
        ).fetchone()
        return str(found[0]) if found and str(found[0]).startswith("ses_") else ""
    except sqlite3.Error:
        return ""
    finally:
        connection.close()


def run_opencode(
    run_dir: Path,
    *,
    session_id: str | None,
    prompt: str,
    title: str,
    log_name: str,
    resume: bool = False,
    agent: str = "qa",
) -> tuple[int, str]:
    """Run OpenCode on a terminal so each JSON line is flushed into run.log immediately.

    A new run omits ``--session``. OpenCode creates the session and prints its id.
    ``--session`` is only passed when resuming that real id.
    """
    settings = get_settings()
    book = Logbook(run_dir)
    active_session = session_id if resume and session_id else ""
    tail = SubagentTail(active_session, book)
    log_path = run_dir / "opencode" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["opencode", "run", "--format", "json"]
    if active_session:
        command.extend(["--session", active_session])
    model = settings.main_model if agent == "qa" else settings.sub_model
    command.extend([
        "--agent",
        agent,
        "--model",
        model,
        "--title",
        title,
        "--auto",
        prompt,
    ])
    book.row(agent, "launch", f"continue {active_session}" if active_session else f"new session  {model}")
    started_ms = int(time.time() * 1000)

    def remember(text: str) -> None:
        nonlocal active_session
        book.event(text)
        if active_session:
            return
        found = session_id_from_text(text)
        if not found:
            return
        active_session = found
        tail.parent_id = found
        book.row(agent, "session", found)
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
                remember(text)
        if pending.strip():
            text = pending.decode("utf-8", errors="replace").replace("\r", "")
            handle.write(text + "\n")
            handle.flush()
            remember(text)
        if timed_out:
            handle.write("opencode timed out\n")
            book.row("qa", "error", "opencode timed out")
    os.close(master)
    if not active_session:
        active_session = _recent_root_session(started_ms)
        if active_session:
            tail.parent_id = active_session
            book.row("qa", "session", active_session)
    tail.poll()
    tail.write_index(run_dir / "opencode" / "children.json")
    export_children(run_dir, tail.children, book)
    try:
        code = 124 if timed_out else process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        code = 124
    return code, active_session


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
    if not session_id:
        return
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


_PREFLIGHT_CHECK = re.compile(r"^(PASS|FAIL)\s{2}([^:]+):\s*(.*)$")


def _preflight_row(line: str) -> str | None:
    text = plain(line)
    match = _PREFLIGHT_CHECK.match(text)
    if match:
        verb = "pass" if match.group(1) == "PASS" else "fail"
        return row("preflight", verb, f"{match.group(2).strip()} — {match.group(3).strip()}")
    if text.startswith("ok →") or text.startswith("failed →"):
        verb = "ok" if text.startswith("ok") else "failed"
        return row("preflight", verb, text.split("→", 1)[-1].strip())
    return None


def run_preflight(
    run_dir: Path,
    *,
    ticket: str | None,
    pr: int | None,
    sha: str | None,
    session_only: bool = False,
) -> int:
    settings = get_settings()
    command = ["node", "scripts/preflight.mjs", "--out", str(run_dir)]
    if session_only:
        # Sign in only. The checked-in suite does not read or write Linear.
        command.append("--session-only")
    elif ticket:
        command.append(ticket)
    elif pr:
        command.extend(["--pr", str(pr)])
    elif sha:
        command.extend(["--sha", sha])
    log_path = run_dir / "preflight.log"
    env = os.environ.copy()
    env["QA_RUN_DIR"] = str(run_dir)
    book = Logbook(run_dir)
    process = subprocess.Popen(
        command,
        cwd=settings.root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert process.stdout is not None
    with log_path.open("w", encoding="utf-8") as handle:
        for line in process.stdout:
            handle.write(line)
            handle.flush()
            formatted = _preflight_row(line)
            if formatted:
                book.line(formatted)
    return process.wait()


def checked_in_specs() -> list[str]:
    """Specs under `e2e test cases`. The space stays inside one path; callers pass it as one argument."""
    settings = get_settings()
    root = settings.root / "e2e test cases"
    if not root.is_dir():
        return []
    found: list[str] = []
    for spec in sorted(root.rglob("*.spec.ts")):
        if spec.name.startswith("auth.spec."):
            continue
        found.append(spec.relative_to(settings.root).as_posix())
    return found


def common_test_dir(specs: list[str]) -> Path:
    """Directory that contains every spec. Playwright only collects files inside testDir."""
    settings = get_settings()
    dirs = [Path(spec).parent.as_posix() for spec in specs]
    if not dirs:
        return (settings.root / "tests").resolve()
    prefix = dirs[0].split("/")
    for directory in dirs[1:]:
        parts = directory.split("/")
        while prefix and prefix != parts[: len(prefix)]:
            prefix.pop()
    relative = "/".join(prefix) if prefix else "."
    return (settings.root / relative).resolve()


def _dot_progress(text: str) -> bool:
    return bool(text) and set(text) <= set("·.×xXF±T° ")


def _next_break(pending: bytes) -> int | None:
    indexes = [index for index in (pending.find(b"\n"), pending.find(b"\r")) if index >= 0]
    return min(indexes) if indexes else None


def _stream_playwright(process: subprocess.Popen[bytes], master: int, handle: Any, book: Logbook, deadline: float) -> bool:
    """Copy Playwright's terminal into the run log. A quiet stretch is logged as still working."""
    pending = b""
    last_beat = time.monotonic()
    last_text = "browser starting"
    timed_out = False
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            break
        ready, _, _ = select.select([master], [], [], min(15.0, remaining))
        if not ready:
            if process.poll() is not None:
                break
            if time.monotonic() - last_beat >= 20:
                book.row("playwright", "working", f"still in the browser  {last_text}"[:220])
                last_beat = time.monotonic()
            continue
        try:
            chunk = os.read(master, 8192)
        except OSError:
            break
        if not chunk:
            break
        handle.write(chunk.decode("utf-8", errors="replace"))
        handle.flush()
        pending += chunk
        while True:
            cut = _next_break(pending)
            if cut is None:
                break
            raw, pending = pending[:cut], pending[cut + 1:]
            text = plain(raw.decode("utf-8", errors="replace"))
            if not text or _dot_progress(text):
                continue
            last_text = text
            last_beat = time.monotonic()
            book.row("playwright", "test", text[:220])
    if pending.strip():
        text = plain(pending.decode("utf-8", errors="replace"))
        if text and not _dot_progress(text):
            book.row("playwright", "test", text[:220])
    return timed_out


def run_playwright(run_dir: Path, specs: list[str]) -> dict[str, Any]:
    book = Logbook(run_dir)
    ready, detail = ensure_session()
    if ready == 0:
        for name in personas_requested(specs):
            ready, detail = ensure_session(persona=name)
            if ready != 0:
                break
    if ready != 0:
        book.row("server", "session", f"failed  {detail or 'could not sign in'}")
        return {
            "exitCode": ready or 1,
            "summary": {"passed": 0, "failed": 1, "skipped": 0, "flaky": 0},
            "setupError": detail or "could not sign in",
        }
    result = _run_playwright_once(run_dir, specs)
    log_text = _playwright_log(run_dir)
    if result["exitCode"] == 0 or not _session_expired(log_text):
        return result
    book.row("server", "session", "session expired during the run. signing in again")
    targets = _expired_personas(log_text) or [None]
    refreshed = 0
    detail = ""
    for name in targets:
        refreshed, detail = ensure_session(fresh=True, persona=name)
        if refreshed != 0:
            break
    if refreshed != 0:
        book.row("server", "session", f"refresh failed  {detail or 'could not sign in'}")
        return result
    book.row("server", "session", "refreshed. resuming the same specs")
    return _run_playwright_once(run_dir, specs)


def _expired_personas(log_text: str) -> list[str]:
    if "for persona" not in log_text.lower():
        return []
    found: list[str] = []
    for name in re.findall(r"persona (admin|support|viewer)", log_text, re.IGNORECASE):
        persona = name.lower()
        if persona not in found:
            found.append(persona)
    return found


def _playwright_log(run_dir: Path) -> str:
    log_path = run_dir / "playwright" / "output.log"
    if not log_path.is_file():
        return ""
    return log_path.read_text(encoding="utf-8", errors="replace")


def _run_playwright_once(run_dir: Path, specs: list[str]) -> dict[str, Any]:
    settings = get_settings()
    book = Logbook(run_dir)
    log_path = run_dir / "playwright" / "output.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["npx", "playwright", "test", "--workers=1", "--project=e2e", *specs]
    env = _playwright_env(run_dir)
    env["QA_TEST_DIR"] = str(common_test_dir(specs))
    book.row(
        "playwright",
        "running",
        f"{len(specs)} files, one at a time. Each finished case is logged as done/total. A retry stays on that case.",
    )
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 80, 200, 0, 0))
    process = subprocess.Popen(
        command,
        cwd=settings.root,
        env=env,
        stdout=slave,
        stderr=slave,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )
    os.close(slave)
    deadline = time.monotonic() + settings.playwright_timeout_seconds
    with log_path.open("w", encoding="utf-8") as handle:
        timed_out = _stream_playwright(process, master, handle, book, deadline)
        if timed_out:
            handle.write("\nplaywright timed out\n")
    os.close(master)
    try:
        code = 124 if timed_out else process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        code = 124
    summary = read_playwright_summary(run_dir)
    setup_error = ""
    log_text = _playwright_log(run_dir)
    if "No tests found" in log_text:
        setup_error = "No tests found. The spec paths were outside the Playwright testDir."
    elif code != 0 and summary["failed"] == 0 and summary["passed"] == 0:
        summary["failed"] = 1
    return {"exitCode": code, "summary": summary, "setupError": setup_error}


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
            existing = [
                str(item) for item in files
                if _is_runnable_spec(settings.root / str(item))
            ]
            if existing:
                return existing
    found: list[str] = []
    specs_dir = run_dir / "specs"
    if not specs_dir.is_dir():
        return found
    for spec in sorted(specs_dir.rglob("*.spec.ts")):
        if spec.stat().st_mtime < started_at - 1:
            continue
        if not _is_runnable_spec(spec):
            continue
        try:
            found.append(str(spec.relative_to(settings.root)))
        except ValueError:
            continue
    return found


def _is_runnable_spec(path: Path) -> bool:
    """A Playwright file under the run's specs folder. The explore walk log is not a spec."""
    if not path.is_file():
        return False
    if "explore" in path.parts:
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "test(" in text
