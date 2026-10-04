"""Rules, findings, open questions, sources, geography, changes and submission files."""

from __future__ import annotations

from fastapi import APIRouter, Query

from engine.api.deps import engine_timer, get_store
from engine.models import (
    ChangeEvent,
    ChangeList,
    FindingList,
    OpenQuestionList,
    RuleDetail,
    RuleList,
    SourceDoc,
)

router = APIRouter()


@router.get("/rules", response_model=RuleList)
def rules(
    state: str | None = None,
    jurisdiction_id: str | None = None,
    category: str | None = None,
    status: str | None = None,
    tier: str | None = None,
    q: str | None = None,
):
    with engine_timer():
        return get_store().rules(state, jurisdiction_id, category, status, tier, q)


@router.get("/rules/{rule_id}", response_model=RuleDetail)
def rule(rule_id: str):
    with engine_timer():
        return get_store().rule(rule_id)


@router.get("/findings", response_model=FindingList)
def findings(state: str | None = None):
    with engine_timer():
        return get_store().findings(state)


@router.get("/open-questions", response_model=OpenQuestionList)
def open_questions():
    with engine_timer():
        return get_store().open_questions()


@router.get("/sources/{doc_id}", response_model=SourceDoc)
def source(doc_id: str, rule_id: str | None = None, window: int = Query(1500, ge=1)):
    with engine_timer():
        return get_store().source(doc_id, rule_id, window)


@router.get("/geo/jurisdictions/{jurisdiction_id}")
def geo(jurisdiction_id: str, state: str | None = None):
    with engine_timer():
        if state:
            return get_store().geo_state(state)
        return get_store().geo(jurisdiction_id)


@router.get("/changes", response_model=ChangeList)
def changes():
    with engine_timer():
        return get_store().changes()


@router.get("/changes/{change_id}", response_model=ChangeEvent)
def change(change_id: str):
    with engine_timer():
        return get_store().change(change_id)


@router.get("/submission/{name}.json")
def submission(name: str):
    with engine_timer():
        return get_store().submission(name)
