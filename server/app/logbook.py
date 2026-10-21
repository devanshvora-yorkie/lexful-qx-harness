"""Plain-text timeline for a run. Raw OpenCode JSON stays in opencode/*.jsonl."""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SESSION_ID = re.compile(r"\bses_[A-Za-z0-9]{10,}\b")


def plain(text: str) -> str:
    return _ANSI.sub("", text).replace("\r", "").strip()


def _stamp(moment: datetime | None = None) -> str:
    return (moment or datetime.now()).strftime("%H:%M:%S")


def _when(payload: dict[str, Any]) -> datetime | None:
    raw = payload.get("timestamp")
    if isinstance(raw, (int, float)) and raw > 1_000_000_000_000:
        return datetime.fromtimestamp(raw / 1000)
    return None


def _clip(text: str, limit: int = 180) -> str:
    one = " ".join(text.split())
    if len(one) <= limit:
        return one
    return one[: limit - 1] + "…"


def _public(text: str) -> str:
    """Drop provider key URLs. The rest of the error is what the run failed on."""
    return re.sub(r"https://openrouter\.ai/\S+", "openrouter", plain(text))


def _short_path(path: str) -> str:
    marker = "lexful-qa-opencode/"
    index = path.find(marker)
    if index >= 0:
        return path[index + len(marker):]
    return path


def _span(milliseconds: float) -> str:
    seconds = max(0, int(milliseconds / 1000))
    if seconds < 60:
        return f"{seconds}s"
    minutes, rest = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rest:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _duration(state: dict[str, Any]) -> str:
    clock = state.get("time") if isinstance(state.get("time"), dict) else {}
    start = clock.get("start")
    end = clock.get("end")
    if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end >= start:
        return _span(end - start)
    return ""


def row(role: str, verb: str, detail: str = "") -> str:
    return f"{role[:16]:<16}  {verb[:14]:<14}  {detail}".rstrip()


def plain_error(text: str) -> str | None:
    """A readable error row for a non-JSON OpenCode line, or nothing for ordinary output."""
    cleaned = plain(text)
    if not cleaned or cleaned.startswith("{"):
        return None
    lowered = cleaned.lower()
    if lowered.startswith("error") or "not found" in lowered or lowered.startswith("exception"):
        return row("qa", "error", _clip(_public(cleaned), 240))
    return None


def session_id_from_text(text: str) -> str:
    """The first real OpenCode session id in one event. Ignores ordinary prose."""
    cleaned = plain(text)
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        found = _session_id(payload)
        if found:
            return found
    if cleaned.startswith("{"):
        match = _SESSION_ID.search(cleaned)
        if match:
            return match.group(0)
    return ""


def _session_id(payload: dict[str, Any]) -> str:
    for key in ("sessionID", "sessionId", "session_id"):
        value = payload.get(key)
        if isinstance(value, str) and value.startswith("ses_"):
            return value
    for key in ("session", "info", "properties", "part"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            found = _session_id(nested)
            if found:
                return found
        if isinstance(nested, str) and nested.startswith("ses_"):
            return nested
    return ""


def _shell_summary(command: str) -> str:
    text = " ".join(command.split())
    text = re.sub(r"^(?:cd\s+\S+\s+&&\s+)+", "", text)
    match = re.search(r"playwright-cli\s+(\S+)(?:\s+(\S+))?", text)
    if match:
        action = match.group(1)
        target = match.group(2) or ""
        if target.startswith("http") or target.startswith("-"):
            return _clip(f"playwright-cli {action} {target}")
        return f"playwright-cli {action}"
    return _clip(text, 140)


def _tool_detail(tool: str, payload: dict[str, Any]) -> str:
    if tool in {"shell", "bash"}:
        return _shell_summary(str(payload.get("command") or payload.get("description") or ""))
    if tool in {"read", "write", "edit"}:
        path = str(payload.get("filePath") or payload.get("path") or "")
        return _clip(_short_path(path))
    if tool in {"task", "agent", "subagent"}:
        name = str(payload.get("agent") or payload.get("subagent") or "")
        description = str(payload.get("description") or "")
        return _clip(f"{name}  {description}".strip())
    return _clip(json.dumps(payload, ensure_ascii=False))


def _first_sentence(text: str) -> str:
    cleaned = re.sub(r"<subagent[^>]*>", "", text)
    cleaned = cleaned.replace("**", "").replace("`", "")
    cleaned = " ".join(cleaned.split())
    if not cleaned:
        return ""
    stop = cleaned.find(". ")
    sentence = cleaned[: stop + 1] if 0 <= stop <= 160 else cleaned
    return _clip(sentence, 160)


def format_event(payload: dict[str, Any]) -> str | None:
    """One readable line for an OpenCode JSON event, or nothing when the event is noise."""
    kind = str(payload.get("type") or "")
    if kind == "error":
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        return row("qa", "error", _clip(_public(str(message or "unknown")), 220))
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    if kind == "tool_use":
        tool = str(part.get("tool") or "tool")
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        status = str(state.get("status") or "called")
        incoming = state.get("input") if isinstance(state.get("input"), dict) else {}
        if tool in {"task", "agent", "subagent"}:
            return row("qa", "subagent", _subagent_detail(state, status, incoming))
        detail = _tool_detail(tool, incoming)
        if status == "error":
            detail = _clip(f"{detail}  {_public(str(state.get('error') or ''))}".strip(), 200)
        verb = tool if status == "completed" else status
        return row("qa", verb, detail)
    if kind == "step_finish":
        return row("qa", "step", _step_detail(part))
    if kind == "text":
        text = part.get("text") or payload.get("text") or ""
        if str(text).strip():
            return row("qa", "said", _clip(_public(str(text)), 220))
    return None


def _subagent_detail(state: dict[str, Any], status: str, incoming: dict[str, Any]) -> str:
    name = str(incoming.get("agent") or incoming.get("subagent") or "subagent")
    description = str(incoming.get("description") or "")
    pieces = [status, name, description, _duration(state)]
    error = state.get("error")
    if error:
        pieces.append(_public(str(error).split(":", 1)[-1].strip()))
    output = state.get("output")
    if status == "completed" and isinstance(output, str):
        pieces.append(_first_sentence(output))
    return _clip("  ".join(piece for piece in pieces if piece), 240)


def _step_detail(part: dict[str, Any]) -> str:
    reason = str(part.get("reason") or "done")
    cost = part.get("cost")
    tokens = part.get("tokens") if isinstance(part.get("tokens"), dict) else {}
    pieces: list[str] = []
    if isinstance(cost, (int, float)):
        pieces.append(f"${cost:.4f}")
    incoming = tokens.get("input")
    outgoing = tokens.get("output")
    if isinstance(incoming, int) or isinstance(outgoing, int):
        pieces.append(f"in {incoming or 0} out {outgoing or 0}")
    pieces.append(reason)
    return "  ".join(pieces)


def child_message_lines(agent: str, message: dict[str, Any]) -> list[str]:
    """Readable lines for one stored subagent message. Skips the spawn prompt and reasoning blobs."""
    if str(message.get("type") or "") == "user":
        return []
    content = message.get("content")
    if not isinstance(content, list):
        return []
    lines: list[str] = []
    speech: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text" and str(item.get("text") or "").strip():
            speech.append(str(item["text"]))
            continue
        if item.get("type") != "tool":
            continue
        state = item.get("state") if isinstance(item.get("state"), dict) else {}
        status = str(state.get("status") or "")
        if status not in {"completed", "error"}:
            continue
        name = str(item.get("name") or item.get("tool") or "tool")
        incoming = state.get("input") if isinstance(state.get("input"), dict) else {}
        detail = _tool_detail(name, incoming)
        if status == "error":
            detail = _clip(f"{detail}  {_public(str(state.get('error') or 'failed'))}".strip(), 200)
            lines.append(row(agent, "error", detail))
        else:
            lines.append(row(agent, name, detail))
    said = _clip(_public(" ".join(speech)), 220)
    if len(said) >= 8:
        lines.append(row(agent, "said", said))
    return lines


class Logbook:
    def __init__(self, folder: Path) -> None:
        self.path = folder / "run.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def line(self, message: str, *, moment: datetime | None = None) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"{_stamp(moment)}  {message}\n")
            handle.flush()

    def row(self, role: str, verb: str, detail: str = "", *, moment: datetime | None = None) -> None:
        self.line(row(role, verb, detail), moment=moment)

    def phase(self, title: str) -> None:
        self.line(f"── {title}")

    def event(self, raw: str) -> None:
        cleaned = plain(raw)
        if not cleaned:
            return
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            note = plain_error(cleaned)
            if note:
                self.line(note)
            return
        if not isinstance(payload, dict):
            return
        text = format_event(payload)
        if text:
            self.line(text, moment=_when(payload))

    def tail(self, limit: int = 40) -> list[str]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-limit:]


def _session_table(connection: sqlite3.Connection) -> str | None:
    names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "session_v2" in names:
        return "session_v2"
    if "session" in names:
        return "session"
    return None


class SubagentTail:
    """Follow child sessions in the OpenCode database and write their tool calls into the run log.

    The parent stream only reports a subagent when it returns. The work itself (pages opened,
    files written) lands in session_message while that call is still running.
    """

    def __init__(self, parent_id: str, book: Logbook, db_path: Path | None = None) -> None:
        self.parent_id = parent_id
        self.book = book
        self.db_path = db_path or Path.home() / ".local" / "share" / "opencode" / "opencode.db"
        self.opened_at = int(time.time() * 1000)
        self.started: set[str] = set()
        self.finished: set[str] = set()
        self.seen: set[tuple[str, int, str]] = set()
        self.children: list[dict[str, Any]] = []

    def poll(self) -> None:
        if not self.parent_id or not self.db_path.is_file():
            return
        try:
            connection = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=1)
        except sqlite3.Error:
            return
        try:
            table = _session_table(connection)
            if table is None:
                return
            idle = "time_idle" if table == "session_v2" else "time_archived"
            rows = connection.execute(
                f"""
                SELECT id, agent, title, cost, tokens_input, tokens_output, tokens_reasoning,
                       time_created, time_updated, {idle}
                FROM {table}
                WHERE parent_id = ?
                ORDER BY time_created
                """,
                (self.parent_id,),
            ).fetchall()
            self.children = [
                {
                    "id": row[0],
                    "agent": row[1] or "subagent",
                    "title": row[2] or "",
                    "cost": row[3] or 0,
                    "tokens": {"input": row[4] or 0, "output": row[5] or 0, "reasoning": row[6] or 0},
                    "timeCreated": row[7],
                    "timeUpdated": row[8],
                    "timeIdle": row[9],
                }
                for row in rows
            ]
            for child in self.children:
                self._follow(connection, child)
        except sqlite3.Error:
            return
        finally:
            connection.close()

    def write_index(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.children, indent=2) + "\n", encoding="utf-8")

    def _follow(self, connection: sqlite3.Connection, child: dict[str, Any]) -> None:
        session_id = str(child["id"])
        agent = str(child["agent"])
        created = int(child.get("timeCreated") or 0)
        if created < self.opened_at - 2_000:
            self.started.add(session_id)
            self.finished.add(session_id)
            return
        if session_id not in self.started:
            self.started.add(session_id)
            self.book.row(agent, "started", _clip(f"{child['title']}  {session_id}".strip()))
        messages = connection.execute(
            "SELECT seq, data FROM session_message WHERE session_id = ? ORDER BY seq",
            (session_id,),
        ).fetchall()
        for seq, raw in messages:
            key = (session_id, int(seq), "message")
            if key in self.seen:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                self.seen.add(key)
                continue
            if not isinstance(message, dict):
                self.seen.add(key)
                continue
            pending = False
            for item in message.get("content") or []:
                if isinstance(item, dict) and item.get("type") == "tool":
                    state = item.get("state") if isinstance(item.get("state"), dict) else {}
                    if str(state.get("status") or "") not in {"completed", "error"}:
                        pending = True
            if pending:
                continue
            for line in child_message_lines(agent, message):
                self.book.line(line)
            self.seen.add(key)
        if child.get("timeIdle") and session_id not in self.finished:
            self.finished.add(session_id)
            created = child.get("timeCreated") or child.get("timeIdle")
            idle = child.get("timeIdle")
            elapsed = _span(idle - created) if isinstance(created, int) and isinstance(idle, int) else ""
            tokens = child["tokens"]
            detail = f"${float(child['cost']):.4f}  in {tokens['input']} out {tokens['output']}  {elapsed}  {session_id}"
            self.book.row(agent, "finished", " ".join(detail.split()))
