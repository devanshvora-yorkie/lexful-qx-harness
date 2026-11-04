"""Plain-text timeline for a run. Raw OpenCode JSON stays in opencode/*.jsonl."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_SESSION_ID = re.compile(r"\bses_[A-Za-z0-9]{10,}\b")
_ECHO: set[str] = set()
_ROUTES: dict[str, Path] = {}


def route(folder: Path, into: Path) -> None:
    """While a stage works in a subfolder (a ticket's e2e/), its run.log lines go to the ticket's run.log."""
    _ROUTES[str(folder.resolve())] = into


def unroute(folder: Path) -> None:
    _ROUTES.pop(str(folder.resolve()), None)


def echo_run(folder: Path) -> None:
    """Copy this run's log lines to the process terminal.

    When no client is tailing run.log, lines are copied to the harness process terminal here.
    """
    _ECHO.add(str(folder.resolve()))


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
    """The error text as a log line."""
    return plain(text)


def _short_path(path: str) -> str:
    marker = "lexful-qa-opencode/"
    index = path.find(marker)
    if index >= 0:
        return path[index + len(marker):]
    return path


def row(role: str, verb: str, detail: str = "") -> str:
    return f"{role[:16]:<16}  {verb[:14]:<14}  {detail}".rstrip()


def plain_error(text: str, role: str = "qa") -> str | None:
    """A readable error row for a non-JSON OpenCode line, or nothing for ordinary output."""
    cleaned = plain(text)
    if not cleaned or cleaned.startswith("{"):
        return None
    lowered = cleaned.lower()
    if lowered.startswith("error") or "not found" in lowered or lowered.startswith("exception"):
        return row(role, "error", _clip(_public(cleaned), 240))
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
    return _clip(json.dumps(payload, ensure_ascii=False))


def format_event(payload: dict[str, Any], role: str = "qa") -> str | None:
    """One readable line for an OpenCode JSON event, or nothing when the event is noise. `role` names the session."""
    kind = str(payload.get("type") or "")
    if kind == "error":
        error = payload.get("error")
        message = error.get("message") if isinstance(error, dict) else error
        return row(role, "error", _clip(_public(str(message or "unknown")), 220))
    part = payload.get("part") if isinstance(payload.get("part"), dict) else {}
    if kind == "tool_use":
        tool = str(part.get("tool") or "tool")
        state = part.get("state") if isinstance(part.get("state"), dict) else {}
        status = str(state.get("status") or "called")
        incoming = state.get("input") if isinstance(state.get("input"), dict) else {}
        detail = _tool_detail(tool, incoming)
        if status == "error":
            detail = _clip(f"{detail}  {_public(str(state.get('error') or ''))}".strip(), 200)
        verb = tool if status == "completed" else status
        return row(role, verb, detail)
    if kind == "step_finish":
        return row(role, "step", _step_detail(part))
    if kind == "text":
        text = part.get("text") or payload.get("text") or ""
        if str(text).strip():
            return row(role, "said", _clip(_public(str(text)), 220))
    return None


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


class Logbook:
    def __init__(self, folder: Path, name: str = "run.log", *, role: str = "qa") -> None:
        # `role` labels the lines of an agent session: qa, or ux-audit for the audit that runs beside it.
        if name == "run.log":
            folder = _ROUTES.get(str(folder.resolve()), folder)
        self.path = folder / name
        self.role = role
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def line(self, message: str, *, moment: datetime | None = None) -> None:
        text = f"{_stamp(moment)}  {message}"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(f"{text}\n")
            handle.flush()
        if str(self.path.parent.resolve()) in _ECHO:
            print(text, flush=True)

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
            note = plain_error(cleaned, self.role)
            if note:
                self.line(note)
            return
        if not isinstance(payload, dict):
            return
        text = format_event(payload, self.role)
        if text:
            self.line(text, moment=_when(payload))

    def tail(self, limit: int = 40) -> list[str]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-limit:]
