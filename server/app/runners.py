"""Subprocess runners. OpenCode never receives the Stytch, Linear, or GitHub secrets."""

from __future__ import annotations

import base64
import fcntl
import json
import os
import pty
import pwd
import re
import select
import shutil
import signal
import sqlite3
import struct
import subprocess
import termios
import threading
import time
from pathlib import Path
from typing import Any

from app.logbook import Logbook, SubagentTail, plain, row, session_id_from_text
from app.settings import SECRET_ENV, get_settings


# ---- Agent identity -------------------------------------------------------------------------
# The server holds every secret in its environment. Model-driven processes (OpenCode, the
# Playwright specs it writes, playwright-cli) run as an unprivileged user, so they cannot read
# /proc/<server pid>/environ. The cookie files and run folders are handed to that user.


def agent_identity() -> tuple[int, int, str] | None:
    """(uid, gid, home) of QA_AGENT_USER when the server runs as root, else None (same user)."""
    name = get_settings().agent_user
    if not name or os.geteuid() != 0:
        return None
    try:
        entry = pwd.getpwnam(name)
    except KeyError:
        return None
    return entry.pw_uid, entry.pw_gid, entry.pw_dir


def _as_agent() -> dict[str, Any]:
    """Popen keyword arguments that drop to the agent user."""
    identity = agent_identity()
    if identity is None:
        return {}
    uid, gid, _home = identity
    return {"user": uid, "group": gid, "extra_groups": []}


def _agent_home() -> Path:
    identity = agent_identity()
    return Path(identity[2]) if identity else Path.home()


def opencode_db() -> Path:
    return _agent_home() / ".local" / "share" / "opencode" / "opencode.db"


def hand_over(*paths: Path) -> None:
    """Give the agent user ownership of the paths it must write. Symlinks are not followed."""
    identity = agent_identity()
    if identity is None:
        return
    uid, gid, _home = identity
    for base in paths:
        if not base.exists():
            continue
        targets = [base] if base.is_file() else [base, *base.rglob("*")]
        for target in targets:
            try:
                if target.is_symlink():
                    continue
                stat = target.lstat()
                if stat.st_uid != uid:
                    os.chown(target, uid, gid, follow_symlinks=False)
            except OSError:
                continue


def _agent_env(env: dict[str, str]) -> dict[str, str]:
    identity = agent_identity()
    if identity is not None:
        name = get_settings().agent_user
        env["HOME"] = identity[2]
        env["USER"] = name
        env["LOGNAME"] = name
        env.pop("XDG_DATA_HOME", None)
        env.pop("XDG_CONFIG_HOME", None)
    return env


# ---- Process registry: cancel stops what a run started -----------------------------------------

_PROCS_LOCK = threading.Lock()
_PROCS: dict[str, set[int]] = {}


def _key(run_dir: Path) -> str:
    """Date, time and short id: the run folder's name (older runs also carry their counts after it).

    A stage that works in a subfolder of the run (the ticket's e2e/) shares the run's key, so
    cancelling the run stops its processes too.
    """
    if run_dir.name == "e2e":
        run_dir = run_dir.parent
    parts = run_dir.name.split("_")
    return "_".join(parts[:3]) if len(parts) >= 3 else run_dir.name


def _track(run_dir: Path, pid: int) -> None:
    with _PROCS_LOCK:
        _PROCS.setdefault(_key(run_dir), set()).add(pid)


def _untrack(run_dir: Path, pid: int) -> None:
    with _PROCS_LOCK:
        _PROCS.get(_key(run_dir), set()).discard(pid)


def kill_run(run_dir: Path) -> int:
    """Stop every process group this run started. Returns how many were signalled."""
    with _PROCS_LOCK:
        pids = list(_PROCS.get(_key(run_dir), set()))
    for pid in pids:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except (ProcessLookupError, PermissionError):
                break
            time.sleep(0.5)
    return len(pids)


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


def write_cli_config(folder: Path) -> Path | None:
    """Point playwright-cli at the Chromium that @playwright/test installed.

    The CLI bundles its own Playwright build and looks for a different Chromium
    revision. Without this file the agent loses minutes finding the executable.
    """
    probe = (
        "import { chromium } from 'playwright';"
        "import { existsSync } from 'node:fs';"
        "const p = chromium.executablePath();"
        "if (!existsSync(p)) process.exit(1); console.log(p);"
    )
    try:
        done = subprocess.run(
            ["node", "--input-type=module", "-e", probe],
            cwd=get_settings().root, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    executable = done.stdout.strip().splitlines()[-1] if done.returncode == 0 and done.stdout.strip() else ""
    if not executable:
        return None
    target = folder / "explore" / "pw-cli.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"browser": {"browserName": "chromium", "launchOptions": {
        "headless": True, "executablePath": executable}}}, indent=2) + "\n", encoding="utf-8")
    return target


_REPO_LOCKS: dict[str, threading.Lock] = {}
_REPO_LOCKS_GUARD = threading.Lock()


def _repo_lock(name: str) -> threading.Lock:
    with _REPO_LOCKS_GUARD:
        return _REPO_LOCKS.setdefault(name, threading.Lock())


def _git_env() -> dict[str, str] | None:
    """The GitHub token travels in the environment of the server's own git process.

    It is never on a command line (readable in /proc/<pid>/cmdline) and never in a config file.
    """
    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token:
        return None
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env = {key: value for key, value in os.environ.items() if key not in SECRET_ENV}
    env.update({
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.extraHeader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {auth}",
        "GIT_TERMINAL_PROMPT": "0",
    })
    return env


def _repos_of(pack: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Pull requests grouped by owner/repo. A PR without a repo is in the default repo."""
    default = f"{os.environ.get('GITHUB_ORG', 'Lexful-ai')}/{os.environ.get('GITHUB_REPO', 'docu-stack')}"
    grouped: dict[str, list[dict[str, Any]]] = {}
    for pull in pack.get("pullRequests") or []:
        if isinstance(pull, dict) and pull.get("number"):
            grouped.setdefault(str(pull.get("repo") or default), []).append(pull)
    return grouped or {default: []}


def worktree_root(folder: Path) -> Path:
    return get_settings().root / "runs" / "source" / "worktrees" / _key(folder)


def _deployed_targets(pack: dict[str, Any], pulls: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """(UAT environments, sha) for each build UAT runs of this repo's pull requests, from preflight's deployment check."""
    numbers = {p.get("number") for p in pulls}
    deployment = pack.get("deployment") if isinstance(pack.get("deployment"), dict) else {}
    by_sha: dict[str, list[str]] = {}
    for item in deployment.get("components") or []:
        if isinstance(item, dict) and item.get("deployedSha") and item.get("pr") in numbers:
            envs = by_sha.setdefault(str(item["deployedSha"]), [])
            if item.get("env") and item["env"] not in envs:
                envs.append(str(item["env"]))
    return [(", ".join(envs) or "uat", sha) for sha, envs in by_sha.items()]


def prepare_source(folder: Path) -> Path | None:
    """One read-only clone per product repo, refreshed on every run, and worktrees of it for this run.

    Every run fetches main and each pull request (refs/heads/pr-<n>), so the clone is never stale.
    The worktree is the code UAT runs: one per distinct sha the deployment record names for the PRs
    (docu-app-uat and docu-service-uat can run different commits). Without a deployment record it is
    the primary PR while it is open, otherwise main. Returns the first worktree, or None when git or
    GitHub is unavailable; the agent then greps the pack.
    """
    settings = get_settings()
    try:
        pack = json.loads((folder / "context-pack.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    env = _git_env()
    if env is None:
        return None
    lines: list[str] = []
    first: Path | None = None
    for full_name, pulls in _repos_of(pack).items():
        repo = full_name.split("/")[-1]
        clone = settings.root / "runs" / "source" / repo

        def git(args: list[str], timeout: int = 300, where: Path = clone) -> bool:
            done = subprocess.run(["git", "-C", str(where), *args], capture_output=True, text=True, timeout=timeout, env=env)
            return done.returncode == 0

        trees: list[tuple[Path, str, str]] = []
        try:
            with _repo_lock(repo):
                if not (clone / ".git").is_dir():
                    clone.mkdir(parents=True, exist_ok=True)
                    git(["init", "-q"]) and git(["remote", "add", "origin", f"https://github.com/{full_name}.git"])
                refs = ["+refs/heads/main:refs/remotes/origin/main"] + [
                    f"+refs/pull/{p['number']}/head:refs/heads/pr-{p['number']}" for p in pulls
                ]
                if not git(["fetch", "-q", "--force", "origin", *refs], timeout=600):
                    lines.append(f"{full_name}: fetch failed, grep the context pack instead")
                    continue
                targets = []
                for envs, sha in _deployed_targets(pack, pulls):
                    # A deployed commit is normally on main; fetch it by sha when it is not.
                    if git(["cat-file", "-e", f"{sha}^{{commit}}"]) or git(["fetch", "-q", "origin", sha], timeout=300):
                        targets.append((f"{repo}@{sha[:8]}", sha, f"deployed on {envs} ({sha[:8]})"))
                if not targets:
                    primary = next((p for p in pulls if p["number"] == pack.get("primaryPr")), None)
                    ref = f"pr-{primary['number']}" if primary and primary.get("state") == "open" else "origin/main"
                    targets = [(repo, ref, f"{ref}: no deployed sha in the deployment record")]
                git(["worktree", "prune"])
                for name, ref, note in targets:
                    tree = worktree_root(folder) / name
                    if tree.exists():
                        git(["worktree", "remove", "--force", str(tree)])
                    tree.parent.mkdir(parents=True, exist_ok=True)
                    if git(["worktree", "add", "-q", "--detach", str(tree), ref], timeout=600):
                        trees.append((tree, ref, note))
        except (OSError, subprocess.TimeoutExpired):
            lines.append(f"{full_name}: git unavailable, grep the context pack instead")
            continue
        if not trees:
            lines.append(f"{full_name}: worktree failed, grep the context pack instead")
            continue
        first = first or trees[0][0]
        branches = ", ".join(f"pr-{p['number']} ({'merged' if p.get('merged') else p.get('state')})" for p in pulls)
        worktrees = "\n".join(f"  Worktree: {_relative_to_root(tree)}  ({note})" for tree, _ref, note in trees)
        lines.append(
            f"{full_name}\n{worktrees}\n"
            f"  Branches: origin/main (fetched now); {branches or 'no PRs in this repo'}\n"
            f"  History and other branches: git -C {_relative_to_root(trees[0][0])} log|show|blame|grep|diff"
        )
    if first is None:
        return None
    (folder / "source-info.md").write_text(
        "Read-only source for this run, checked out at the commits UAT runs. Browse with Read, Grep, Glob\n"
        "and git log|show|blame|grep|diff. Never checkout, fetch, commit, or edit.\n\n" + "\n\n".join(lines) + "\n",
        encoding="utf-8",
    )
    return first


def cleanup_source(folder: Path) -> None:
    """Remove this run's worktrees. The clones stay for the next run."""
    root = worktree_root(folder)
    if not root.is_dir():
        return
    for tree in root.iterdir():
        clone = get_settings().root / "runs" / "source" / tree.name.split("@", 1)[0]
        try:
            subprocess.run(["git", "-C", str(clone), "worktree", "remove", "--force", str(tree)],
                           capture_output=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            pass
    shutil.rmtree(root, ignore_errors=True)


def _relative_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(get_settings().root))
    except ValueError:
        return str(path)


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
    return _agent_env(env)


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
    return _agent_env(env)


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
    with _SESSION_LOCK:
        process = subprocess.run(
            command,
            cwd=settings.root,
            env=env,
            capture_output=True,
            text=True,
        )
        # The agent user loads these cookies with playwright-cli and the specs read them.
        hand_over(session_state_path().parent)
    detail = (process.stderr or process.stdout or "").strip().splitlines()
    return process.returncode, (detail[-1] if detail else "")[:220]


# Two runs refreshing the same cookie file at once would race; one sign-in at a time.
_SESSION_LOCK = threading.Lock()


def _newest_log(run_dir: Path, log_name: str) -> Path:
    """The log of the last attempt: heal-1.jsonl, or heal-1-retry1.jsonl after a retry."""
    stem = Path(log_name).stem
    tries = sorted((run_dir / "opencode").glob(f"{stem}-retry*.jsonl"))
    return tries[-1] if tries else run_dir / "opencode" / log_name


def last_opencode_error(run_dir: Path, log_name: str) -> str:
    path = _newest_log(run_dir, log_name)
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


def _recent_root_session(started_ms: int, title: str = "") -> str:
    """Fallback when the stream never printed a session id. Matches the title so a parallel run's session is not taken."""
    database = opencode_db()
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
        columns = {item[1] for item in connection.execute(f"PRAGMA table_info({table})")}
        where = "parent_id IS NULL AND time_created >= ?"
        params: list[Any] = [started_ms - 2_000]
        if title and "title" in columns:
            where += " AND title = ?"
            params.append(title)
        found = connection.execute(
            f"SELECT id FROM {table} WHERE {where} ORDER BY time_created DESC LIMIT 1",
            params,
        ).fetchone()
        return str(found[0]) if found and str(found[0]).startswith("ses_") else ""
    except sqlite3.Error:
        return ""
    finally:
        connection.close()


# A dropped connection, a DNS failure, a throttle, or an idle kill. The work so far is in the
# session, so the server resumes it once instead of failing the phase.
_TRANSIENT = re.compile(
    r"ECONNRESET|ETIMEDOUT|ETIMEOUT|EAI_AGAIN|ENOTFOUND|ECONNREFUSED|socket hang up|Connection lost|"
    r"network|inactivity|timed out|throttl|Too many requests|429|5\d\d|ServiceUnavailable|overloaded",
    re.IGNORECASE,
)


def is_transient(detail: str) -> bool:
    return bool(detail) and bool(_TRANSIENT.search(detail))


_RESUME_NOTE = "Phase: resume\nThe connection to the model dropped. Follow section 7 of .agents/skills/lexful-autonomous-agent-qa/SKILL.md for the phase you were in."


def run_opencode(
    run_dir: Path,
    *,
    session_id: str | None,
    prompt: str,
    title: str,
    log_name: str,
    resume: bool = False,
    agent: str = "qa",
    model: str | None = None,
    book_name: str = "run.log",
) -> tuple[int, str]:
    """Run one OpenCode turn. A transient failure resumes the same session up to QA_AGENT_RETRIES times."""
    settings = get_settings()
    book = Logbook(run_dir, book_name, role="ux-audit" if agent == "ux-auditor" else "qa")
    code, session = _run_opencode_once(
        run_dir, session_id=session_id, prompt=prompt, title=title, log_name=log_name,
        resume=resume, agent=agent, model=model, book=book,
    )
    for attempt in range(1, settings.agent_retries + 1):
        if code == 0:
            break
        detail = last_opencode_error(run_dir, log_name) or ("opencode timed out" if code == 124 else "")
        if code == 124 or not session or not is_transient(detail):
            break
        book.row("server", "retry", f"{agent}: {detail[:120]}  resuming {session} ({attempt} of {settings.agent_retries})")
        code, session = _run_opencode_once(
            run_dir, session_id=session, prompt=_RESUME_NOTE, title=title,
            log_name=f"{Path(log_name).stem}-retry{attempt}.jsonl", resume=True,
            agent=agent, model=model, book=book,
        )
    return code, session


def _run_opencode_once(
    run_dir: Path,
    *,
    session_id: str | None,
    prompt: str,
    title: str,
    log_name: str,
    resume: bool,
    agent: str,
    model: str | None,
    book: Logbook,
) -> tuple[int, str]:
    """Run OpenCode on a terminal so each JSON line is flushed into the log immediately.

    A new run omits ``--session``. OpenCode creates the session and prints its id.
    ``--session`` is only passed when resuming that real id.
    """
    settings = get_settings()
    active_session = session_id if resume and session_id else ""
    tail = SubagentTail(active_session, book, db_path=opencode_db())
    log_path = run_dir / "opencode" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["opencode", "run", "--format", "json"]
    if active_session:
        command.extend(["--session", active_session])
    model = model or (settings.main_model if agent.startswith("qa") else settings.sub_model)
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
    hand_over(run_dir, get_settings().root / "e2e test cases")
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
        **_as_agent(),
    )
    _track(run_dir, process.pid)
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
            book.row(agent, "error", "opencode timed out")
    os.close(master)
    if not active_session:
        active_session = _recent_root_session(started_ms, title)
        if active_session:
            tail.parent_id = active_session
            book.row(agent, "session", active_session)
    tail.poll()
    tail.write_index(run_dir / "opencode" / "children.json")
    export_children(run_dir, tail.children, book)
    try:
        code = 124 if timed_out else process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        code = 124
    finally:
        _untrack(run_dir, process.pid)
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
            **_as_agent(),
        )
        if result.returncode == 0 and result.stdout.strip():
            target.write_text(result.stdout, encoding="utf-8")
            continue
        book.row("server", "error", f"could not export {agent} {session_id}")


def export_session(run_dir: Path, session_id: str, name: str = "session.json") -> None:
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
        **_as_agent(),
    )
    target = run_dir / "opencode" / name
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


def resolve_trigger(*, pr: int | None = None, sha: str | None = None) -> dict[str, Any]:
    """The ticket (and pull request) GitHub names for a PR number or a deployed commit, before the run exists.

    The run folder is chosen from this once and never moves. {} when GitHub cannot be read.
    """
    if not pr and not sha:
        return {}
    command = ["node", "scripts/resolve-trigger.mjs", *(["--pr", str(pr)] if pr else ["--sha", str(sha)])]
    try:
        done = subprocess.run(command, cwd=get_settings().root, capture_output=True, text=True, timeout=60)
        found = json.loads(done.stdout.strip().splitlines()[-1]) if done.stdout.strip() else {}
    except (OSError, subprocess.TimeoutExpired, ValueError, IndexError):
        return {}
    if not isinstance(found, dict) or found.get("error"):
        return {}
    ticket = str(found.get("ticket") or "").upper() or None
    number = found.get("pr") if isinstance(found.get("pr"), int) else pr
    return {"ticket": ticket, "pr": number}


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
    else:
        # A run started from a PR or a deploy knows its ticket from the trigger; the PR stays the primary one.
        if ticket:
            command.append(ticket)
        if pr:
            command.extend(["--pr", str(pr)])
        if sha:
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


def list_specs(specs: list[str]) -> tuple[bool, str]:
    """Load specs without running them. Catches bad imports and syntax before a spec joins the suite."""
    if not specs:
        return True, ""
    try:
        # Model-written specs are loaded as the agent user, never as the server.
        hand_over(get_settings().root / "e2e test cases")
        done = subprocess.run(
            ["node_modules/.bin/playwright", "test", "--list", *specs],
            cwd=get_settings().root, capture_output=True, text=True, timeout=120,
            env=_agent_env({k: v for k, v in os.environ.items() if k not in SECRET_ENV}),
            **_as_agent(),
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return False, str(err)[:200]
    if done.returncode == 0:
        return True, ""
    lines = [line.strip() for line in (done.stderr or done.stdout).splitlines() if line.strip()]
    return False, (lines[0] if lines else "playwright could not load the specs")[:240]


def list_tests(specs: list[str]) -> dict[str, Any] | None:
    """The tests in `specs` as Playwright's JSON report shape, without running them (`--list`).

    A heal can rename or add a test; the server lists the files to know which tests exist now.
    None when Playwright cannot load them.
    """
    if not specs:
        return {}
    env = _agent_env({k: v for k, v in os.environ.items() if k not in SECRET_ENV and k != "QA_RUN_DIR"})
    env["QA_TEST_DIR"] = str(common_test_dir(specs))
    try:
        hand_over(get_settings().root / "e2e test cases")
        done = subprocess.run(
            ["node_modules/.bin/playwright", "test", "--list", "--reporter=json", "--project=e2e", *specs],
            cwd=get_settings().root, capture_output=True, text=True, timeout=120, env=env, **_as_agent(),
        )
        report = json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return report if isinstance(report, dict) else None


def run_playwright(
    run_dir: Path,
    specs: list[str],
    *,
    out_dir: Path | None = None,
    grep: str = "",
    workers: int | None = None,
) -> dict[str, Any]:
    """Run specs. `out_dir` keeps a second report apart (the affected E2E cases); `grep` picks tests by title."""
    book = Logbook(run_dir)
    out = out_dir or run_dir
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
    result = _run_playwright_once(run_dir, specs, out, grep, workers)
    if result["exitCode"] == 0:
        return result
    log_text = _playwright_log(out)
    if _session_expired(log_text):
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
    elif not _revoked_sessions(specs, book):
        return result
    book.row("server", "session", "refreshed. resuming the same specs")
    return _run_playwright_once(run_dir, specs, out, grep, workers)


def _revoked_sessions(specs: list[str], book: Logbook) -> bool:
    """After a failed run: sign in again as any persona whose saved cookies the API now rejects.

    A revoked session still has a valid expiry, so the specs fail with an unrelated message. ensure_session
    asks the API whether each saved session is alive and signs in again when it is not.
    """
    revoked = False
    for name in [None, *personas_requested(specs)]:
        code, line = ensure_session(persona=name)
        if code == 0 and "refreshed" in line:
            book.row("server", "session", f"the saved session for {name or 'the default persona'} was rejected by the API. Signed in again")
            revoked = True
    return revoked


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


def _run_playwright_once(
    run_dir: Path, specs: list[str], out: Path, grep: str = "", workers: int | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    book = Logbook(run_dir)
    log_path = out / "playwright" / "output.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    # Tests go to the next free worker (playwright.config.ts fullyParallel), so one file can use every worker;
    # Playwright starts no more workers than it has tests. With QA_PW_FULLY_PARALLEL=false a file is the unit.
    wanted = workers or settings.pw_workers
    count = max(1, wanted if settings.pw_fully_parallel else min(wanted, len(specs)))
    command = ["npx", "playwright", "test", f"--workers={count}", "--project=e2e", *specs]
    if grep:
        command.extend(["--grep", grep])
    env = _playwright_env(out)
    env["QA_TEST_DIR"] = str(common_test_dir(specs))
    env["QA_PW_WORKERS"] = str(count)
    env["QA_PW_FULLY_PARALLEL"] = "true" if settings.pw_fully_parallel else "false"
    hand_over(out, settings.root / "e2e test cases")
    book.row(
        "playwright",
        "running",
        f"{len(specs)} files on {count} worker(s), {'each test to the next free worker' if settings.pw_fully_parallel else 'one file per worker'}. "
        "Each finished case is logged as done/total. A retry stays on that case.",
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
        **_as_agent(),
    )
    _track(run_dir, process.pid)
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
    finally:
        _untrack(run_dir, process.pid)
    summary = read_playwright_summary(out)
    setup_error = ""
    log_text = _playwright_log(out)
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
            existing = [found for found in (_rerooted(run_dir, str(item)) for item in files) if found]
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


def _rerooted(run_dir: Path, item: str) -> str:
    """A planned spec path, still valid after the run folder was renamed (resume after a seal)."""
    root = get_settings().root
    if _is_runnable_spec(root / item):
        return item
    marker = "/specs/"
    normalized = "/" + item.replace("\\", "/").lstrip("/")
    if marker in normalized:
        candidate = run_dir / "specs" / normalized.split(marker, 1)[1]
        if _is_runnable_spec(candidate):
            try:
                return str(candidate.relative_to(root))
            except ValueError:
                return str(candidate)
    return ""


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
