"""Health, meta, address search, resolve, lookup and timeline."""

from __future__ import annotations

from fastapi import APIRouter, Query

from engine import config
from engine.api.deps import engine_timer, get_store
from engine.models import (
    AddressList,
    AddressSearch,
    CustomLookupRequest,
    Health,
    LookupResponse,
    Meta,
    ResolveRequest,
    ResolveResponse,
    TimelineResponse,
)

router = APIRouter()


@router.get("/health", response_model=Health)
def health():
    return get_store().health()


@router.get("/meta", response_model=Meta)
def meta():
    with engine_timer():
        return get_store().meta()


@router.get("/addresses", response_model=AddressList)
def addresses():
    with engine_timer():
        return get_store().addresses()


@router.get("/addresses/search", response_model=AddressSearch)
def search(q: str = Query(min_length=1), limit: int = Query(8, ge=1, le=50)):
    with engine_timer():
        return get_store().search(q, limit)


@router.post("/resolve", response_model=ResolveResponse)
def resolve(body: ResolveRequest):
    with engine_timer():
        return get_store().resolve(body.query)


@router.post("/lookup/custom", response_model=LookupResponse)
def lookup_custom(body: CustomLookupRequest):
    with engine_timer():
        return get_store().custom(body)


@router.get("/lookup/{address_id}", response_model=LookupResponse)
def lookup(address_id: str, as_of: str | None = None):
    with engine_timer():
        return get_store().lookup(address_id, as_of or config.DEFAULT_AS_OF)


@router.get("/timeline/{address_id}", response_model=TimelineResponse)
def timeline(address_id: str):
    with engine_timer():
        return get_store().timeline(address_id)
