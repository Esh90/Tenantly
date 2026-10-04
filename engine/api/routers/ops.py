"""Ingest (admin + SSE), alerts, proof and audit."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse

from engine.api.deps import engine_timer, get_store, require_admin
from engine.models import (
    AuditList,
    IngestAccepted,
    IngestJob,
    IngestRequest,
    ProofResponse,
    PublishResult,
    SubscriptionCreated,
    SubscriptionRequest,
)

router = APIRouter()


@router.post(
    "/ingest",
    status_code=202,
    response_model=IngestAccepted,
    dependencies=[Depends(require_admin)],
)
def ingest(body: IngestRequest):
    with engine_timer():
        return get_store().ingest_start(body)


@router.get("/ingest/{job_id}", response_model=IngestJob)
def ingest_job(job_id: str):
    return get_store().ingest_get(job_id)


@router.get("/ingest/{job_id}/events")
def ingest_events(job_id: str):
    job = get_store().ingest_get(job_id)

    def stream():
        for s in job["stages"]:
            yield f"event: stage\ndata: {json.dumps(s)}\n\n"
        impact = job["result"]["impact"] if job["result"] else {}
        yield f"event: impact\ndata: {json.dumps(impact)}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': job['status']})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post(
    "/ingest/{job_id}/publish",
    response_model=PublishResult,
    dependencies=[Depends(require_admin)],
)
def ingest_publish(job_id: str):
    return get_store().ingest_publish(job_id)


@router.post("/alerts/subscriptions", status_code=201, response_model=SubscriptionCreated)
def subscribe(body: SubscriptionRequest):
    return get_store().subscribe(body)


@router.delete("/alerts/subscriptions/{token}", status_code=204)
def unsubscribe(token: str):
    return Response(status_code=204)


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
