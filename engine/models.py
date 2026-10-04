"""Pydantic v2 models. API contract types mirror PLAN.md section 14.3 exactly."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ISODate = str
PartialDate = str  # YYYY | YYYY-MM | YYYY-MM-DD
Lang = Literal["en", "es"]
Category = Literal[
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
]
CATEGORIES: tuple[str, ...] = (
    "rent_increase_limits",
    "just_cause_eviction",
    "security_deposits",
    "application_screening_fees",
    "screening_restrictions",
    "algorithmic_rent_setting",
)
Result = Literal["applies", "unknown", "superseded", "not_yet_effective", "pending"]
RESULTS: tuple[str, ...] = ("applies", "unknown", "superseded", "not_yet_effective", "pending")
RuleStatus = Literal["in_force", "not_yet_effective", "pending", "failed"]
Level = Literal["state", "county", "city"]
EvidenceTier = Literal["A", "B", "C", "C1"]
StateCode = Literal["CA", "NJ", "MA"]
ReasonCode = Literal[
    "barred_by_state",
    "none_in_sources",
    "motion_only",
    "only_pending",
    "failed_measure",
    "text_not_supplied",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Bilingual(Model):
    en: str
    es: str


class Jurisdiction(Model):
    id: str
    level: Level
    name: str
    label: str
    state: StateCode
    geoid: str | None
    in_scope: bool


class Resolution(Model):
    method: Literal["point_in_polygon", "state_only"]
    geocoder: Literal["census_batch", "census_oneline", "nominatim", "none"]
    census_agrees: bool | None


class JurisdictionStack(Model):
    state: Jurisdiction
    county: Jurisdiction | None
    city: Jurisdiction | None
    mailing_city: str | None
    mailing_mismatch: bool
    note: Bilingual | None
    resolution: Resolution


class FactValue(Model):
    value: float | str | bool | None
    interval: tuple[float | None, float | None] | None
    source: Literal["assessor", "assessor_derived", "user", "derived", "missing"]
    basis: str | None
    record_conflict: bool
    label: Bilingual


class BuildingFacts(Model):
    year_built: FactValue
    units: FactValue
    property_type: FactValue
    subsidized: FactValue
    use_code: str
    use_description: str
    source_dataset: str
    zip_suspect: bool


class AddressSummary(Model):
    address_id: str
    label: str
    street: str
    postal_city: str
    zip: str | None
    state: StateCode
    lat: float | None
    lon: float | None
    legal_city: str | None
    is_sample: bool


class Citation(Model):
    doc_id: str
    cite: str
    url: str
    retrieved_at: str
    quote: str
    char_start: int | None
    char_end: int | None
    doc_sha256: str | None
    tier: EvidenceTier
    quote_source: Literal["corpus", "supplementary"]
    supplementary_doc: str | None
    version_label: str | None
    low_signal: bool


class KeyValue(Model):
    name: str
    text: str
    valid_from: ISODate | None
    valid_to: ISODate | None
    stale: bool
    stale_note: Bilingual | None


class ConditionTrace(Model):
    label: Bilingual
    fact: str
    op: str
    expected: str
    actual: str | None
    basis: str | None
    result: Literal["true", "false", "unknown"]


class Conflict(Model):
    with_rule_id: str | None
    kind: Literal["possible_preemption", "barred_by_state", "overlap"]
    explanation: Bilingual
    evidence: Citation | None
    active_from: ISODate | None


class OpenQuestion(Model):
    oq_id: str
    title: Bilingual
    detail: Bilingual
    rule_ids: list[str]
    sources: list[Citation]
    changes_answer_between: tuple[ISODate, ISODate] | None


class ReasoningBoundary(Model):
    checked: list[Bilingual]
    not_checked: list[Bilingual]
    assumptions: list[Bilingual]


class Audio(Model):
    en: str | None
    es: str | None


class RuleResult(Model):
    rule_id: str
    category: Category
    title: str
    jurisdiction: Jurisdiction
    result: Result
    rule_status: RuleStatus
    effective_date: PartialDate | None
    effective_note: Bilingual | None
    summary: Bilingual
    who: Bilingual
    reason: Bilingual
    key_values: list[KeyValue]
    conditions: list[ConditionTrace]
    caveats: list[Bilingual]
    missing_facts: list[str]
    superseded_by: str | None
    governs_over: list[str]
    conflicts: list[Conflict]
    conflict_flag: bool
    citation: Citation
    extra_citations: list[Citation]
    confidence: float
    review_flag: bool
    open_question_ids: list[str]
    audio: Audio


class Finding(Model):
    finding_id: str
    category: Category
    jurisdiction: Jurisdiction
    reason_code: ReasonCode
    explanation: Bilingual
    evidence: list[Citation]


class CategoryBlock(Model):
    category: Category
    label: Bilingual
    headline: Bilingual
    results: list[RuleResult]
    findings: list[Finding]


class DecisiveOption(Model):
    value: str
    label: Bilingual


class DecisiveQuestion(Model):
    fact: str
    prompt: Bilingual
    input: Literal["year", "integer", "boolean", "select"]
    options: list[DecisiveOption] | None = None
    resolves_rule_ids: list[str]


class UpcomingChange(Model):
    date: ISODate
    rule_id: str
    title: str
    from_: Result | Literal["none"] = Field(alias="from")
    to: Result | Literal["none"]
    summary: Bilingual

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class FailedItem(Model):
    rule_id: str
    title: str
    note: Bilingual
    citation: Citation


class LookupResponse(Model):
    address: AddressSummary
    jurisdiction: JurisdictionStack
    facts: BuildingFacts
    as_of: ISODate
    categories: list[CategoryBlock]
    pending: list[RuleResult]
    failed: list[FailedItem]
    upcoming: list[UpcomingChange]
    counts: dict[Result, int]
    decisive_question: DecisiveQuestion | None
    open_questions: list[OpenQuestion]
    reasoning_boundary: ReasoningBoundary
    facts_source: Literal["data", "user"]
    sources_retrieved_at: ISODate
    is_projection: bool
    data_version: str
    disclaimer: str
    fallback: bool


class TimelineSegment(Model):
    start: ISODate
    end: ISODate | None
    lookup: LookupResponse


class DateRange(Model):
    start: ISODate
    end: ISODate


class Breakpoint(Model):
    date: ISODate
    label: Bilingual
    rule_ids: list[str]


class TimelineResponse(Model):
    address_id: str
    range: DateRange
    breakpoints: list[Breakpoint]
    segments: list[TimelineSegment]
    data_version: str


class AddressIndexItem(Model):
    address_id: str
    label: str
    postal_city: str
    legal_city: str | None
    state: StateCode
    zip: str | None
    lat: float | None
    lon: float | None


class ResolveResponse(Model):
    match_type: Literal["sample", "geocoded", "not_found"]
    address: AddressSummary | None
    jurisdiction: JurisdictionStack | None
    candidates: list[AddressIndexItem]
    geocoder: Literal["index", "census", "nominatim"] | None


class Exemption(Model):
    description: Bilingual
    citation: Citation | None


class Relation(Model):
    type: str
    other_rule_id: str | None
    explanation: Bilingual
    evidence: Citation
    active_from: ISODate | None


class Provenance(Model):
    models: list[str]
    prompt_versions: dict[str, str]
    votes: dict[str, str]
    adjudicated_fields: list[str]
    audit_ids: list[str]


class RuleDetail(Model):
    rule_id: str
    category: Category
    title: str
    jurisdiction: Jurisdiction
    rule_status: RuleStatus
    effective_date: PartialDate | None
    effective_note: Bilingual | None
    requirement: str
    summary: Bilingual
    who: Bilingual
    coverage_text: Bilingual
    exemptions: list[Exemption]
    key_values: list[KeyValue]
    penalty: str | None
    citation: Citation
    extra_citations: list[Citation]
    relations: list[Relation]
    confidence: float
    review_flag: bool
    open_question_ids: list[str]
    provenance: Provenance
    counts_at_default_date: dict[Result, int]


class SourceVersion(Model):
    label: str
    valid_from: ISODate | None
    valid_to: ISODate | None
    in_force_on_default: bool


class Highlight(Model):
    start: int
    end: int
    rule_id: str


class SourceWindow(Model):
    text: str
    start: int
    end: int
    highlights: list[Highlight]


class SourceDoc(Model):
    doc_id: str
    title: str
    url: str
    retrieved_at: str
    doc_sha256: str | None
    sha_ok: bool | None
    jurisdiction_label: str
    doc_type: str
    low_signal: bool
    versions: list[SourceVersion]
    window: SourceWindow
    total_chars: int


class RuleIdResult(Model):
    rule_id: str
    result: Result | Literal["none"]


class AffectedAddress(Model):
    address_id: str
    label: str
    lat: float | None
    lon: float | None
    legal_city: str | None
    before: list[RuleIdResult]
    after: list[RuleIdResult]
    conflict_flag: bool


class CompareBeforeAfter(Model):
    before: ISODate
    after: ISODate


class CompareOn(Model):
    on: ISODate


class CompareWithWithout(Model):
    mode: Literal["with_without"]
    on: ISODate


class ExpectedCheck(Model):
    passed: bool
    detail: str


class ChangeSummary(Model):
    change_id: str
    kind: Literal["test", "ingest", "watch"]
    test_id: str | None
    title: str
    test_type: Literal["as_of", "boundary", "pending", "negative", "with_without"]
    summary: Bilingual
    created_at: str
    rule_ids: list[str]
    compare: CompareBeforeAfter | CompareWithWithout | CompareOn
    affected_count: int
    conflict_count: int
    expected_check: ExpectedCheck | None


class ChangeEvent(ChangeSummary):
    affected: list[AffectedAddress]


IngestStage = Literal[
    "received",
    "sectionize",
    "triage",
    "extract",
    "verify",
    "crosscheck",
    "calendar",
    "link",
    "explain",
    "diff",
    "impact",
    "ready",
    "published",
    "failed",
]


class IngestStageState(Model):
    stage: IngestStage
    status: Literal["pending", "running", "done", "failed"]
    detail: str
    ms: int | None


class IngestImpact(Model):
    affected_count: int
    sample: list[AffectedAddress]
    effective_date: PartialDate | None
    conflicts: int


class IngestVerification(Model):
    quotes_checked: int
    quotes_verified: int
    rejected: int


class IngestResult(Model):
    rules: list[RuleDetail]
    findings: list[Finding]
    relations: list[Relation]
    impact: IngestImpact
    verification: IngestVerification
    cost_usd: float
    cache_hit: bool


class ErrorInfo(Model):
    code: str
    message: str


class IngestJob(Model):
    job_id: str
    status: Literal["running", "ready", "published", "failed"]
    stage: IngestStage
    started_at: str
    finished_at: str | None
    stages: list[IngestStageState]
    result: IngestResult | None
    error: ErrorInfo | None


class SelfScoreComponent(Model):
    name: str
    score: float
    max: float
    note: str


class SelfScore(Model):
    components: list[SelfScoreComponent]
    key: Literal["silver"]
    raw_report: str


class ChangeCheck(Model):
    test_id: str
    passed: bool
    affected: int
    expected: int
    conflicts: int
    expected_conflicts: int


class VerificationStats(Model):
    rules: int
    tier_counts: dict[EvidenceTier, int]
    quotes_verified: int
    rejected_candidates: int
    adjudicated_fields: int
    mean_confidence: float


class FactsStats(Model):
    derived_units: int
    record_conflicts: int
    zip_suspect: int
    missing_year_built: int


class GeoStats(Model):
    matched_batch: int
    matched_oneline: int
    matched_nominatim: int
    unmatched: int
    mailing_mismatches: int
    census_disagreements: int


class PlainLanguageStats(Model):
    mean_grade_en: float
    max_grade_en: float
    es_coverage: float


class LatencyStats(Model):
    measured_at: str
    lookup_p50_ms: float
    lookup_p95_ms: float
    custom_p50_ms: float
    llm_baseline_ms: float | None


class CostStats(Model):
    total_usd: float
    by_stage: dict[str, float]


class ProofResponse(Model):
    data_version: str
    compiled_at: str
    selfscore: SelfScore | None
    change_checks: list[ChangeCheck]
    verification: VerificationStats
    facts: FactsStats
    geo: GeoStats
    plain_language: PlainLanguageStats
    latency: LatencyStats | None
    cost: CostStats
    open_questions: list[OpenQuestion]
    limitations: list[Bilingual]


class CategoryInfo(Model):
    key: Category
    label: Bilingual


class MetaCounts(Model):
    rules: int
    findings: int
    addresses: int
    docs_text: int
    docs_link_only: int


class Meta(Model):
    app: Literal["Tenantly"]
    api_version: Literal["v1"]
    data_version: str
    compiled_at: str
    default_as_of: ISODate
    sources_retrieved_at: ISODate
    as_of_range: DateRange
    categories: list[CategoryInfo]
    jurisdictions: list[Jurisdiction]
    counts: MetaCounts
    persistence: Literal["memory", "postgres"]
    demo_mode: Literal["live", "replay"]
    disclaimer: str


# ---- request / envelope models (not in the TS block, but part of the contract) ----


class Health(Model):
    status: str
    data_version: str
    uptime_s: float


class AddressList(Model):
    items: list[AddressIndexItem]
    data_version: str


class AddressSearch(Model):
    items: list[AddressIndexItem]


class ResolveRequest(Model):
    query: str


class CustomLookupRequest(Model):
    address_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    as_of: ISODate
    facts: dict[str, float | str | bool | None]


class RuleList(Model):
    items: list[RuleDetail]
    total: int


class FindingList(Model):
    items: list[Finding]


class OpenQuestionList(Model):
    items: list[OpenQuestion]


class ChangeList(Model):
    items: list[ChangeSummary]


class IngestRequest(Model):
    title: str
    text: str
    jurisdiction_hint: str | None = None
    source_url: str | None = None
    retrieved_at: str | None = None


class IngestAccepted(Model):
    job_id: str
    status: str
    events_url: str


class PublishResult(Model):
    change_id: str
    published_at: str


class SubscriptionRequest(Model):
    email: str
    address_id: str
    lang: Lang


class SubscriptionFeeds(Model):
    atom: str
    ics: str


class SubscriptionCreated(Model):
    subscription_id: str
    unsubscribe_token: str
    feeds: SubscriptionFeeds


class AuditItem(Model):
    ts: str
    stage: str
    model: str | None
    prompt_version: str | None
    cache_hit: bool
    input_sha: str
    output_sha: str
    verifier: str | None
    cost_usd: float


class AuditList(Model):
    items: list[AuditItem]


class ErrorBody(Model):
    code: str
    message: str
    details: dict
    request_id: str


class ErrorEnvelope(Model):
    error: ErrorBody
