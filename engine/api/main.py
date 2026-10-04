"""FastAPI app: PLAN.md section 14. Served from fixtures until real data lands."""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from engine import config
from engine.api import errors
from engine.api.deps import engine_cell, get_store
from engine.api.routers import core, law, ops

log = logging.getLogger("tenantly.api")

app = FastAPI(title="Tenantly API", version="v1")

app.add_exception_handler(errors.ApiError, errors.api_error_handler)
app.add_exception_handler(RequestValidationError, errors.validation_handler)
app.add_exception_handler(StarletteHTTPException, errors.http_handler)
app.add_exception_handler(Exception, errors.unhandled_handler)

for r in (core.router, law.router, ops.router):
    app.include_router(r, prefix="/v1")


@app.middleware("http")
async def plumbing(request: Request, call_next):
    t0 = time.perf_counter()
    request.state.request_id = "req_" + uuid.uuid4().hex[:12]
    cell = [0.0]
    engine_cell.set(cell)
    response = await call_next(request)
    total = (time.perf_counter() - t0) * 1000
    path = request.url.path
    response.headers["X-Request-Id"] = request.state.request_id
    response.headers["Server-Timing"] = f"engine;dur={cell[0]:.2f}, total;dur={total:.2f}"
    response.headers["ETag"] = f'"{get_store().health()["data_version"]}"'
    cacheable = request.method == "GET" and "/ingest" not in path and path != "/v1/health"
    if cacheable and response.status_code < 400:
        response.headers["Cache-Control"] = "public, max-age=300, stale-while-revalidate=86400"
    else:
        response.headers["Cache-Control"] = "no-store"
    log.info(
        "request id=%s method=%s path=%s status=%s ms=%.1f",
        request.state.request_id,
        request.method,
        path,
        response.status_code,
        total,
    )
    return response


app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)
