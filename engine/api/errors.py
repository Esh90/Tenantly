"""Error envelope (PLAN.md 14.2)."""

from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

STATUS = {
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "ADDRESS_NOT_FOUND": 404,
    "RULE_NOT_FOUND": 404,
    "DOC_NOT_FOUND": 404,
    "CHANGE_NOT_FOUND": 404,
    "JOB_NOT_FOUND": 404,
    "JOB_NOT_READY": 409,
    "ALREADY_PUBLISHED": 409,
    "DOCUMENT_TOO_LARGE": 413,
    "AS_OF_OUT_OF_RANGE": 422,
    "UNSUPPORTED_STATE": 422,
    "INVALID_FACTS": 422,
    "RATE_LIMITED": 429,
    "GEOCODER_UNAVAILABLE": 502,
    "BUDGET_EXCEEDED": 503,
    "NOT_READY": 503,
    "INTERNAL": 500,
}


class ApiError(Exception):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def _envelope(request: Request, code: str, message: str, details: dict) -> JSONResponse:
    rid = getattr(request.state, "request_id", "req_unknown")
    body = {"error": {"code": code, "message": message, "details": details, "request_id": rid}}
    return JSONResponse(body, status_code=STATUS[code], headers={"Cache-Control": "no-store"})


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return _envelope(request, exc.code, exc.message, exc.details)


async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errs = [{"loc": [str(x) for x in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
    return _envelope(request, "BAD_REQUEST", "The request was not valid.", {"errors": errs})


async def http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = {404: "BAD_REQUEST", 405: "BAD_REQUEST"}.get(exc.status_code, "INTERNAL")
    return _envelope(request, code, str(exc.detail), {})


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    return _envelope(request, "INTERNAL", "Something went wrong on our side.", {})
