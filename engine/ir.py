"""Internal rule IR (PLAN.md 8.1). Pydantic v2; official enums are used directly.

API response models live in ``engine/models.py``; the IR here is what the compiler produces
and the engine consumes. Only the types needed so far are defined; the rest arrive with the
Law Compiler in Phase 2.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Precision = Literal["day", "month", "year", "unknown"]
Lifecycle = Literal["enacted", "pending", "failed"]
Derivation = Literal[
    "text_explicit",
    "nj_nth_month_next_following",
    "ca_regular_session_default",
    "ca_history_note",
    "nth_day_after_passage",
    "immediately_on_enactment",
    "went_into_effect",
    "readme_reference",
    "brief_reference",
]


class DateValue(BaseModel):
    """A date that may be an interval: lo == hi when exact, None bounds are unknown."""

    model_config = ConfigDict(frozen=True)

    lo: date | None = None
    hi: date | None = None
    precision: Precision = "unknown"
    derivation: Derivation | None = None
    anchor_quote: str | None = None
    alternatives: tuple[tuple[str, str | None], ...] = ()  # (date text, source) pairs

    @property
    def is_exact(self) -> bool:
        return self.lo is not None and self.lo == self.hi

    @property
    def is_known(self) -> bool:
        return self.lo is not None or self.hi is not None

    def output(self) -> str | None:
        """PartialDate for the submission: a day when exact, else the coarsest correct form."""
        if self.lo is None:
            return None
        if self.is_exact and self.precision == "day":
            return self.lo.isoformat()
        if self.precision == "month":
            return self.lo.strftime("%Y-%m")
        if self.precision == "year":
            return self.lo.strftime("%Y")
        return self.lo.isoformat() if self.is_exact else None


# ---- Rule IR (PLAN.md 8.1) ----

Category = Literal[
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]
Tier = Literal["A", "B", "C", "C1"]
DocType = Literal[
    "statute", "ordinance", "draft_materials", "bill_status", "guidance", "news", "motion", "policy"
]
RelationType = Literal["yields_to", "preempts", "bars", "conflicts_with", "supplements", "amends"]
RelationEffect = Literal["supersede", "conflict_flag", "bar"]
ReasonCode = Literal[
    "barred_by_state",
    "none_in_sources",
    "motion_only",
    "only_pending",
    "failed_measure",
    "text_not_supplied",
]


class IRModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JurisdictionRef(IRModel):
    id: str  # "CA" | "CA-0667000" | "NJ-3436000"
    level: Literal["state", "county", "city"]
    name: str
    label: str  # "CA" | "San Francisco, CA"
    state: Literal["CA", "NJ", "MA"]
    geoid: str | None = None


class Citation(IRModel):
    doc_id: str
    cite: str
    url: str
    retrieved_at: str
    quote: str
    char_start: int | None = None
    char_end: int | None = None
    doc_sha256: str | None = None
    tier: Tier
    quote_source: Literal["corpus", "supplementary"] = "corpus"
    supplementary_doc: str | None = None
    version_label: str | None = None
    low_signal: bool = False


class KeyValue(IRModel):
    name: str
    text: str
    value: float | str | None = None
    unit: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    source_doc_id: str | None = None


class Exemption(IRModel):
    description: str
    predicate: dict  # DSL
    quote: str | None = None
    citation: Citation | None = None


class Rule(IRModel):
    rule_id: str
    category: Category
    jurisdiction: JurisdictionRef
    title: str
    requirement: str
    key_values: list[KeyValue] = []
    coverage: dict  # DSL predicate
    coverage_text: str
    exemptions: list[Exemption] = []
    exemptions_text: str | None = None
    tenancy_conditions: list[str] = []
    lifecycle: Lifecycle
    effective: DateValue = DateValue()
    sunset: DateValue | None = None
    penalty: str | None = None
    citation: Citation
    extra_citations: list[Citation] = []
    doc_type: DocType
    plain: dict[str, str] = {}
    grade_level_en: float | None = None
    audio: dict[str, str | None] = {}
    confidence: float = 0.0
    votes: dict = {}
    review_flag: bool = False
    open_question_ids: list[str] = []
    provenance: dict = {}


class Relation(IRModel):
    relation_id: str
    type: RelationType
    source_rule_id: str
    target_rule_id: str | None = None
    target_scope: dict | None = None
    condition: dict | None = None  # DSL predicate
    evidence: Citation
    effect: RelationEffect
    active_from: date | None = None


class Finding(IRModel):
    finding_id: str
    jurisdiction: JurisdictionRef
    category: Category
    reason_code: ReasonCode
    explanation: dict[str, str]
    evidence: list[Citation] = []
    searched_doc_ids: list[str] = []


class OpenQuestion(IRModel):
    oq_id: str
    title: dict[str, str]
    detail: dict[str, str]
    rule_ids: list[str] = []
    sources: list[Citation] = []
    changes_answer_between: tuple[date, date] | None = None


class RuleSet(IRModel):
    """The compiled output: artifacts/rules.compiled.json."""

    data_version: str
    compiled_at: str
    rules: list[Rule]
    relations: list[Relation] = []
    findings: list[Finding] = []
    open_questions: list[OpenQuestion] = []
