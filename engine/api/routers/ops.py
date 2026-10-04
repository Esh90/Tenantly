"""Ingest (admin + SSE), alerts, proof and audit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from engine import config
from engine.api.deps import engine_timer, get_store, require_ingest_access
from engine.models import (
    AuditList,
    ExtractTextResponse,
    IngestAccepted,
    IngestEdit,
    IngestJob,
    IngestRequest,
    ProofResponse,
    PublishResult,
    SubscriptionCreated,
    SubscriptionRequest,
    WatchStatus,
)

router = APIRouter()


@router.post(
    "/ingest",
    status_code=202,
    response_model=IngestAccepted,
    dependencies=[Depends(require_ingest_access)],
)
def ingest(body: IngestRequest, x_admin_token: str | None = Header(default=None)):
    with engine_timer():
        allowed = config.PUBLIC_INGEST_ENABLED or x_admin_token == config.ADMIN_TOKEN
        if body.auto_publish and not allowed:
            body = body.model_copy(update={"auto_publish": False})
        return get_store().ingest_start(body)


@router.get("/ingest/{job_id}", response_model=IngestJob)
def ingest_job(job_id: str):
    return get_store().ingest_get(job_id)


@router.get("/ingest/{job_id}/events")
def ingest_events(job_id: str):
    store = get_store()
    store.ingest_get(job_id)  # 404 if unknown
    return StreamingResponse(
        store.ingest_events(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post(
    "/ingest/{job_id}/publish",
    response_model=PublishResult,
    dependencies=[Depends(require_ingest_access)],
)
def ingest_publish(job_id: str, approve: bool = False):
    return get_store().ingest_publish(job_id, approve)


@router.post("/ingest/{job_id}/reject", dependencies=[Depends(require_ingest_access)])
def ingest_reject(job_id: str):
    return get_store().ingest_reject(job_id)


@router.post("/ingest/{job_id}/rejudge", dependencies=[Depends(require_ingest_access)])
def ingest_rejudge(job_id: str):
    return get_store().ingest_rejudge(job_id)


@router.post("/ingest/{job_id}/edit", dependencies=[Depends(require_ingest_access)])
def ingest_edit(job_id: str, body: IngestEdit):
    return get_store().ingest_edit(job_id, body.rules)


@router.post(
    "/ingest/extract-text",
    response_model=ExtractTextResponse,
    dependencies=[Depends(require_ingest_access)],
)
async def ingest_extract_text(request: Request, filename: str = ""):
    """Turn an uploaded PDF, DOCX or TXT into text. The browser then sends the text to /ingest."""
    from engine.api.ingest_parts import extract_text

    out = extract_text(filename, await request.body())
    return {**out, "chars": len(out["text"])}


@router.post("/alerts/subscriptions", status_code=201, response_model=SubscriptionCreated)
def subscribe(body: SubscriptionRequest):
    return get_store().subscribe(body)


@router.get("/alerts/subscriptions/{token}", response_model=WatchStatus)
def subscription_status(token: str):
    return get_store().alert_status(token)


@router.delete("/alerts/subscriptions/{token}")
def unsubscribe(token: str):
    return get_store().unsubscribe(token)


@router.get("/alerts/feed/{address_id}.atom")
def feed(address_id: str):
    return Response(get_store().atom(address_id), media_type="application/atom+xml")


@router.get("/alerts/calendar/{address_id}.ics")
def calendar(address_id: str):
    return Response(get_store().ics(address_id), media_type="text/calendar")


@router.get("/proof", response_model=ProofResponse)
def proof():
    with engine_timer():
        return get_store().proof()


@router.get("/audit", response_model=AuditList)
def audit(rule_id: str | None = None, limit: int = Query(50, ge=1, le=500)):
    with engine_timer():
        return get_store().audit(rule_id, limit)
