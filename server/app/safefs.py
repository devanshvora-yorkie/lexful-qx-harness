"""Server writes never follow a symlink the agent planted.

The server runs as root and writes into run folders (run.log, reports, prompts, summaries) while
agent sessions, which run as the `qa` user, can write there too. On Docker Desktop for macOS a bind
mount does not enforce file ownership, so the agent can create or replace anything under `runs/`.
A file the agent swapped for a symlink (`run.log -> /root/.bashrc`) would turn the server's next
write into a write anywhere on the machine.

`install()` makes every `Path.write_text`, `Path.write_bytes` and write-mode `Path.open` in this
process safe:

- the last path component is never followed: a symlink there is removed and a new file is written
  (`O_NOFOLLOW`);
- a path under the runs folder must resolve under the runs folder, so a parent directory swapped for
  a symlink (`e2e -> /etc`) is refused.

Reads are not changed. It is installed when the `app` package is imported.
"""

from __future__ import annotations

import io
import os
import pathlib
from typing import Any

_ORIGINAL_OPEN = pathlib.Path.open
_installed = False


class UnsafePath(PermissionError):
    pass


def _runs_roots() -> list[pathlib.Path]:
    roots = []
    raw = os.environ.get("QA_RUNS_DIR")
    if raw:
        roots.append(pathlib.Path(raw).expanduser())
    roots.append(pathlib.Path(__file__).resolve().parents[2] / "runs")
    return roots


def _inside(path: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def check(path: pathlib.Path) -> None:
    """Refuse a write whose parent folder escapes the runs folder through a symlink."""
    target = pathlib.Path(os.path.abspath(path))
    for root in _runs_roots():
        lexical = pathlib.Path(os.path.abspath(root))
        resolved_root = root.resolve()
        if not (_inside(target, lexical) or _inside(target, resolved_root)):
            continue
        parent = target.parent.resolve()
        if not _inside(parent, resolved_root):
            raise UnsafePath(f"refusing to write {path}: its folder resolves outside {root}")
        return


def _prepare(path: pathlib.Path) -> None:
    check(path)
    if os.path.islink(path):
        os.unlink(path)  # never write through a planted link; write a new file in its place


def _nofollow(file: str, flags: int) -> int:
    return os.open(file, flags | getattr(os, "O_NOFOLLOW", 0), 0o666)


def _open(self: pathlib.Path, mode: str = "r", buffering: int = -1, encoding: str | None = None,
          errors: str | None = None, newline: str | None = None) -> Any:
    if not any(flag in mode for flag in "wax+"):
        return _ORIGINAL_OPEN(self, mode, buffering, encoding, errors, newline)
    _prepare(self)
    if "b" not in mode:
        encoding = io.text_encoding(encoding)
    return open(self, mode, buffering, encoding, errors, newline, opener=_nofollow)  # noqa: SIM115


def _write_text(self: pathlib.Path, data: str, encoding: str | None = None, errors: str | None = None,
                newline: str | None = None) -> int:
    if not isinstance(data, str):
        raise TypeError(f"data must be str, not {type(data).__name__}")
    with _open(self, "w", encoding=encoding, errors=errors, newline=newline) as handle:
        return handle.write(data)


def _write_bytes(self: pathlib.Path, data: Any) -> int:
    view = memoryview(data)
    with _open(self, "wb") as handle:
        return handle.write(view)


def read_bytes(path: pathlib.Path) -> bytes:
    """Read a regular file that is not a symlink. For files the agent could have replaced, before the
    server copies them somewhere the agent can read, or sends them out (Linear uploads)."""
    import stat

    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise UnsafePath(f"{path} is not a regular file")
        check(pathlib.Path(path))
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 20)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def read_text(path: pathlib.Path) -> str:
    return read_bytes(path).decode("utf-8", errors="replace")


def install() -> None:
    global _installed
    if _installed:
        return
    pathlib.Path.open = _open  # type: ignore[method-assign]
    pathlib.Path.write_text = _write_text  # type: ignore[method-assign]
    pathlib.Path.write_bytes = _write_bytes  # type: ignore[method-assign]
    _installed = True
