"""FastAPI control plane. A LEX ticket or pull request starts a run. OpenCode starts after preflight."""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.logbook import Logbook
from app.pipeline import execute_run, startup_order
from app.runners import ensure_session
from app.settings import get_settings
from app.store import (
    cancel_all_runs,
    create_run,
    find_active_phase1,
    find_running_run,
    find_active_sha,
    get_run,
    list_runs,
    recover_runs,
    relocate_legacy_runs,
    run_dir,
    update_run,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("qa.api")
TICKET_RE = re.compile(r"^LEX-\d+$", re.IGNORECASE)
_queue: asyncio.Queue[str] = asyncio.Queue()


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    waiting_ids = recover_runs()
    relocate_legacy_runs()
    waiting = [row for row in (get_run(run_id) for run_id in waiting_ids) if row]
    for run_id in startup_order(waiting):
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


class DeployBody(BaseModel):
    pr: int | None = None
    pull_request: int | None = None
    ticket: str | None = None
    sha: str | None = None


def _enqueue(row: dict[str, Any]) -> dict[str, Any]:
    run_id = str(row["id"])
    folder = run_dir(run_id)
    book = Logbook(folder)
    if row.get("kind") == "phase1":
        book.row("server", "queued", 'E2E User Journey TCs  waiting for worker')
    else:
        ticket = row.get("ticket") or run_id
        book.row("server", "queued", f"Feature Specific TCs  {ticket}  waiting for worker")
    active = find_running_run()
    if active and active.get("id") != run_id:
        label = active.get("ticket") or active["id"]
        book.row(
            "server",
            "queue",
            f"behind {label}  {active['id']} ({active.get('status')})",
        )
    _queue.put_nowait(run_id)
    update_run(run_id, status="queued")
    return {"success": True, "runId": run_id, "ticketKey": row.get("ticket"), "status": "queued"}


def _queue_phase1_if_configured() -> str | None:
    """When QA_PHASE1_ON_START is true, queue E2E before a ticket. Never on container boot."""
    if not get_settings().phase1_on_start:
        return None
    existing = find_active_phase1()
    if existing:
        return existing["id"]
    row = create_run(ticket=None, pr=None, sha=None, kind="phase1")
    _enqueue(row)
    log.info("E2E User Journey TCs queued before ticket %s", row["id"])
    print(f"E2E User Journey TCs queued  {row['id']}", flush=True)
    return row["id"]


def _with_activity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        tail = Logbook(run_dir(row["id"])).tail(1)
        if tail:
            row["activity"] = tail[0]
    return rows


@app.get("/health")
def health() -> dict[str, Any]:
    settings = get_settings()
    running = find_running_run()
    return {
        "status": "ok",
        "port": settings.port,
        "runs": str(settings.runs),
        "phase1BeforeTicket": settings.phase1_on_start,
        "runningRun": (
            {
                "id": running["id"],
                "status": running.get("status"),
                "kind": running.get("kind"),
                "ticket": running.get("ticket"),
            }
            if running
            else None
        ),
    }


@app.post("/runs/cancel-all", status_code=200, dependencies=[Depends(require_secret)])
async def cancel_runs() -> dict[str, Any]:
    """Stop queued work and mark every active run failed. Restart the container to abort a run mid-flight."""
    stopped = cancel_all_runs()
    drained = 0
    while True:
        try:
            _queue.get_nowait()
            drained += 1
            _queue.task_done()
        except asyncio.QueueEmpty:
            break
    if stopped:
        log.info("cancelled %s run(s), drained %s queue item(s)", len(stopped), drained)
        print(f"cancelled {len(stopped)} run(s)  drained {drained} queue item(s)", flush=True)
    return {"success": True, "cancelled": stopped, "drained": drained}


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


@app.post("/run/phase1", status_code=202, dependencies=[Depends(require_secret)])
def run_phase1() -> dict[str, Any]:
    """Queue E2E User Journey TCs. An in-flight run is returned instead of a second one."""
    existing = find_active_phase1()
    if existing:
        return {
            "success": True,
            "skipped": True,
            "reason": "E2E User Journey TCs already queued",
            "runId": existing["id"],
            "status": existing["status"],
        }
    row = create_run(ticket=None, pr=None, sha=None, kind="phase1")
    queued = _enqueue(row)
    log.info("E2E User Journey TCs queued %s", row["id"])
    print(f"E2E User Journey TCs queued  {row['id']}", flush=True)
    return queued


@app.post("/run/{ticket_key}", status_code=202, dependencies=[Depends(require_secret)])
def run_ticket(ticket_key: str, body: RunBody | None = None) -> dict[str, Any]:
    if not TICKET_RE.match(ticket_key):
        raise HTTPException(status_code=400, detail="Ticket must look like LEX-1234")
    pr = body.pr if body else None
    phase1_id = _queue_phase1_if_configured()
    row = create_run(ticket=ticket_key.upper(), pr=pr, sha=None)
    payload = _enqueue(row)
    if phase1_id:
        payload["phase1RunId"] = phase1_id
    return payload


@app.post("/run/pr/{number}", status_code=202, dependencies=[Depends(require_secret)])
def run_pr(number: int, body: RunBody | None = None) -> dict[str, Any]:
    row = create_run(ticket=None, pr=number, sha=None)
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
    row = create_run(ticket=ticket, pr=pr, sha=body.sha)
    queued = _enqueue(row)
    queued["sha"] = body.sha
    return queued


class PersonaBody(BaseModel):
    persona: str
    fresh: bool = False


def persona_client_allowed(host: str | None) -> bool:
    return host in {"127.0.0.1", "::1"}


@app.post("/internal/persona")
def internal_persona(body: PersonaBody, request: Request) -> dict[str, Any]:
    """Sign in as admin, support, or viewer. Localhost only. The response has no cookies."""
    host = request.client.host if request.client else ""
    if not persona_client_allowed(host):
        raise HTTPException(status_code=403, detail="persona login is only available inside the harness")
    name = body.persona.strip().lower()
    if name not in {"admin", "support", "viewer"}:
        raise HTTPException(status_code=400, detail="Persona must be admin, support, or viewer")
    code, detail = ensure_session(fresh=body.fresh, persona=name)
    if code != 0:
        raise HTTPException(status_code=502, detail=detail or "could not sign in")
    return {"success": True, "persona": name, "line": detail}
