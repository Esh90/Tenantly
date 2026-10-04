"""Dependencies: the data store, admin auth and the engine timer."""

from __future__ import annotations

import contextvars
import os
import time
from contextlib import contextmanager
from functools import lru_cache

from fastapi import Header

from engine import config
from engine.api.errors import ApiError
from engine.api.fixtures.store import FixtureStore

# A mutable cell set per request by the middleware, so threadpool endpoints can add to it.
engine_cell: contextvars.ContextVar[list[float]] = contextvars.ContextVar(
    "engine_cell",
    default=[0.0],  # noqa: B039
)
@lru_cache(maxsize=1)
def get_store() -> FixtureStore:
    """The real store when compiled artifacts exist, else fixtures (or when forced for tests)."""
    if os.environ.get("TENANTLY_STORE") != "fixture":
        from engine.api import store

        if store.available():
            return store.load_store()
    return FixtureStore()


@contextmanager
def engine_timer():
    """Measure time spent in store/engine code for the Server-Timing header."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        engine_cell.get()[0] += (time.perf_counter() - t0) * 1000


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not x_admin_token or x_admin_token != config.ADMIN_TOKEN:
        raise ApiError("UNAUTHORIZED", "A valid admin token is required.")


def require_ingest_access(x_admin_token: str | None = Header(default=None)) -> None:
    """Hackathon demo: extract, review and publish with no token when PUBLIC_INGEST_ENABLED."""
    if x_admin_token and x_admin_token == config.ADMIN_TOKEN:
        return
    if not config.PUBLIC_INGEST_ENABLED:
        raise ApiError("UNAUTHORIZED", "Public law ingestion is not enabled.")
