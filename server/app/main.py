"""FastAPI control plane. A LEX ticket or pull request starts a run. OpenCode starts after preflight."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.logbook import Logbook
from app.pipeline import execute_run
from app.settings import get_settings
from app.store import create_run, find_active_sha, get_run, list_runs, recover_runs, run_dir, update_run

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("qa.api")
TICKET_RE = re.compile(r"^LEX-\d+$", re.IGNORECASE)
_queue: asyncio.Queue[str] = asyncio.Queue()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    for run_id in recover_runs():
        _queue.put_nowait(run_id)
    worker = asyncio.create_task(_worker())
    try:
        yield
    finally:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Lexful QA OpenCode", version="1.0.0", lifespan=_lifespan)


async def _worker() -> None:
    while True:
        run_id = await _queue.get()
        try:
            await asyncio.to_thread(execute_run, run_id)
        except Exception:
            log.exception("run %s crashed", run_id)
        finally:
            _queue.task_done()


def require_secret(
    x_harness_deploy_secret: str | None = Header(default=None, alias="x-harness-deploy-secret"),
    authorization: str | None = Header(default=None),
) -> None:
    settings = get_settings()
    expected = settings.deploy_secret
    if not expected:
        if settings.local_mode:
            return
        raise HTTPException(status_code=503, detail="HARNESS_DEPLOY_SECRET is not configured")
    provided = x_harness_deploy_secret
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="Invalid deploy trigger secret")


class RunBody(BaseModel):
    pr: int | None = None
    spec_count: int | None = Field(default=None, alias="specCount")


class DeployBody(BaseModel):
    pr: int | None = None
    pull_request: int | None = None
    ticket: str | None = None
    sha: str | None = None
    ref: str | None = None
    spec_count: int | None = Field(default=None, alias="specCount")


def _enqueue(row: dict[str, Any]) -> dict[str, Any]:
    _queue.put_nowait(row["id"])
    update_run(row["id"], status="queued")
    return {"success": True, "runId": row["id"], "ticketKey": row.get("ticket"), "status": "queued"}


def _with_activity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        tail = Logbook(run_dir(row["id"])).tail(1)
        if tail:
            row["activity"] = tail[0]
    return rows


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    return {"status": "ok", "port": settings.port, "runs": str(settings.runs)}


@app.get("/runs", dependencies=[Depends(require_secret)])
def runs(ticket: str | None = None) -> dict[str, Any]:
    return {"runs": _with_activity(list_runs(ticket))}


@app.get("/runs/{run_id}", dependencies=[Depends(require_secret)])
def run_detail(run_id: str) -> dict[str, Any]:
    row = get_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    row["log"] = Logbook(run_dir(run_id)).tail(40)
    return row


@app.get("/runs/{run_id}/log", dependencies=[Depends(require_secret)])
def run_log(run_id: str) -> PlainTextResponse:
    path = run_dir(run_id) / "run.log"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No log yet")
    return PlainTextResponse(path.read_text(encoding="utf-8", errors="replace"))


@app.post("/run/{ticket_key}", status_code=202, dependencies=[Depends(require_secret)])
def run_ticket(ticket_key: str, body: RunBody | None = None) -> dict[str, Any]:
    if not TICKET_RE.match(ticket_key):
        raise HTTPException(status_code=400, detail="Ticket must look like LEX-1234")
    spec_count = body.spec_count if body else None
    pr = body.pr if body else None
    row = create_run(ticket=ticket_key.upper(), pr=pr, sha=None, spec_count=spec_count)
    return _enqueue(row)


@app.post("/run/pr/{number}", status_code=202, dependencies=[Depends(require_secret)])
def run_pr(number: int, body: RunBody | None = None) -> dict[str, Any]:
    spec_count = body.spec_count if body else None
    row = create_run(ticket=None, pr=number, sha=None, spec_count=spec_count)
    return _enqueue(row)


@app.post("/trigger/uat-deploy", status_code=202, dependencies=[Depends(require_secret)])
def uat_deploy(body: DeployBody) -> dict[str, Any]:
    pr = body.pr or body.pull_request
    ticket = body.ticket.upper() if body.ticket else None
    if ticket and not TICKET_RE.match(ticket):
        raise HTTPException(status_code=400, detail="Ticket must look like LEX-1234")
    if body.sha:
        existing = find_active_sha(body.sha)
        if existing:
            return {"success": True, "skipped": True, "reason": "sha already accepted", "runId": existing["id"], "sha": body.sha}
    if not pr and not ticket and not body.sha:
        raise HTTPException(status_code=400, detail="Provide pr, ticket, or sha")
    row = create_run(ticket=ticket, pr=pr, sha=body.sha, spec_count=body.spec_count)
    queued = _enqueue(row)
    queued["sha"] = body.sha
    return queued
