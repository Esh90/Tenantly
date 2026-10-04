"""The rules engine (PLAN.md 8.5, 8.6): per address and date, which rules apply.

Pure: rules and an address environment in, outcomes out. No model call, no I/O. The model never
decides applicability; it only wrote the predicates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from engine import config
from engine.facts.intervals import Tri, any_
from engine.ir import Finding, Relation, Rule, RuleSet
from engine.rules import dsl

APPLIES, UNKNOWN, SUPERSEDED = "applies", "unknown", "superseded"
NOT_YET, PENDING = "not_yet_effective", "pending"
VISIBLE_UNKNOWN_SET = {APPLIES, UNKNOWN}


@dataclass(frozen=True)
class Policy:
    """Switches chosen by silver-key score (PLAN.md 21.4); defaults come from the environment."""

    exemption_missing_fact: str = config.EXEMPTION_MISSING_FACT  # caveat | unknown
    conflict_flag_mode: str = config.CONFLICT_FLAG_MODE  # explicit_only | overlap


@dataclass
class Exempt:
    value: str  # TRUE | FALSE | UNKNOWN_DATA | UNKNOWN_RENTER
    trace: list[dsl.TraceItem] = field(default_factory=list)
    unknown_descriptions: list[str] = field(default_factory=list)
    unknown_facts: set[str] = field(default_factory=set)


@dataclass
class ConflictFlag:
    with_rule_id: str | None
    kind: str  # possible_preemption | barred_by_state | overlap
    relation_id: str | None
    active_from: date | None


@dataclass
class Outcome:
    rule: Rule
    result: str  # applies | unknown | superseded | not_yet_effective | pending
    would_be: str | None = None  # not_yet_effective: what the result would be once in force
    would_reach: bool | None = None  # pending: would the bill reach this building if passed
    trace: list[dsl.TraceItem] = field(default_factory=list)  # coverage conditions
    exemption_trace: list[dsl.TraceItem] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    missing_facts: list[str] = field(default_factory=list)
    superseded_by: str | None = None
    governs_over: list[str] = field(default_factory=list)
    conflicts: list[ConflictFlag] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # machine-readable reasons
    effective_uncertain: bool = False

    @property
    def rule_id(self) -> str:
        return self.rule.rule_id

    @property
    def conflict_flag(self) -> bool:
        return bool(self.conflicts)


@dataclass
class AddressResult:
    address_id: str
    as_of: date
    outcomes: list[Outcome]  # every non-omitted rule in the address's stack
    failed: list[Rule]  # failed measures in the stack (never shown as results)
    findings: list[Finding]  # includes barred_by_state findings created here
    stack_ids: list[str]

    def by_rule(self) -> dict[str, Outcome]:
        return {o.rule_id: o for o in self.outcomes}


def certainly_after(d: date, sunset: dsl.Interval | None) -> bool:
    return sunset is not None and sunset.hi is not None and d >= sunset.hi


def eval_exemptions(rule: Rule, env: dsl.FactEnv, d: date) -> Exempt:
    if not rule.exemptions:
        return Exempt("FALSE")
    evals = [(ex, dsl.evaluate(dsl.parse(ex.predicate), env, d)) for ex in rule.exemptions]
    trace = [t for _, e in evals for t in e.trace]
    value = any_([e.value for _, e in evals])
    if value is Tri.TRUE:
        return Exempt("TRUE", trace)
    if value is Tri.FALSE:
        return Exempt("FALSE", trace)
    unknown_desc = [ex.description for ex, e in evals if e.value is Tri.UNKNOWN]
    unknown_facts = set().union(*(e.unknown_facts for _, e in evals if e.value is Tri.UNKNOWN))
    data_unknown = any(dsl.FACTS[f].known_from == "data" for f in unknown_facts)
    return Exempt("UNKNOWN_DATA" if data_unknown else "UNKNOWN_RENTER", trace, unknown_desc,
                  unknown_facts)  # fmt: skip


def _eff_bounds(rule: Rule) -> tuple[date | None, date | None]:
    return rule.effective.lo, rule.effective.hi


def resolve_rule(
    rule: Rule, env: dsl.FactEnv, d: date, policy: Policy, location_known: bool = True
) -> Outcome | None:
    """PLAN.md 8.5. Returns None when the rule does not apply (omitted from lookups)."""
    if rule.lifecycle == "failed":
        return None
    if not location_known and rule.jurisdiction.level == "city":
        return Outcome(rule, UNKNOWN, missing_facts=["location"], notes=["location_unknown"])

    cov = dsl.evaluate(dsl.parse(rule.coverage), env, d)
    if rule.lifecycle == "pending":
        return Outcome(
            rule, PENDING, would_reach=cov.value is not Tri.FALSE, trace=cov.trace,
            missing_facts=sorted(cov.unknown_facts),
        )  # fmt: skip
    sunset = rule.sunset
    if sunset is not None and certainly_after(d, dsl.Interval(sunset.lo, sunset.hi)):
        return None
    if cov.value is Tri.FALSE:
        return None
    ex = eval_exemptions(rule, env, d)
    if ex.value == "TRUE":
        return None

    base = UNKNOWN if (cov.value is Tri.UNKNOWN or ex.value == "UNKNOWN_DATA") else APPLIES
    caveats: list[str] = []
    missing = set(cov.unknown_facts)
    if ex.value == "UNKNOWN_DATA":
        missing |= {f for f in ex.unknown_facts if dsl.FACTS[f].known_from == "data"}
    if ex.value == "UNKNOWN_RENTER":
        if policy.exemption_missing_fact == "unknown":
            base = UNKNOWN
            missing |= ex.unknown_facts
        else:
            caveats = list(ex.unknown_descriptions)
    notes: list[str] = []
    uncertain = False
    if rule.citation.tier == "C1" and base == APPLIES:
        base = UNKNOWN  # one supplied signal is not enough to say a law applies
        notes.append("single_signal")
    lo, hi = _eff_bounds(rule)
    if lo is not None and d < lo:
        return Outcome(
            rule,
            NOT_YET,
            would_be=base,
            trace=cov.trace,
            exemption_trace=ex.trace,
            caveats=caveats,
            missing_facts=sorted(missing),
        )
    if lo is not None and hi is not None and lo <= d < hi:
        base, uncertain = UNKNOWN, True
        notes.append("effective_date_uncertain")
    if rule.effective.lo is None and rule.effective.hi is None:
        notes.append("effective_date_unknown")
    return Outcome(
        rule, base, trace=cov.trace, exemption_trace=ex.trace, caveats=caveats, missing_facts=sorted(missing),
        notes=notes, effective_uncertain=uncertain,
    )  # fmt: skip


# ---- precedence, conflicts and bars (PLAN.md 8.6) ----


def _scope_matches(scope: dict, rule: Rule, source: Rule | None = None) -> bool:
    j = rule.jurisdiction
    if source is not None and j.state != source.jurisdiction.state:
        return False
    if "category" in scope and rule.category != scope["category"]:
        return False
    if "level" in scope and j.level != scope["level"]:
        return False
    want_state = scope.get("state") or (source.jurisdiction.state if source else None)
    if want_state and j.state != want_state:
        return False
    if "jurisdiction_ids" in scope and j.id not in scope["jurisdiction_ids"]:
        return False
    return True


def _targets(rel: Relation, by_rule: dict[str, Outcome], source: Rule) -> list[Outcome]:
    if rel.target_rule_id:
        o = by_rule.get(rel.target_rule_id)
        return [o] if o else []
    if rel.target_scope:
        return [
            o for o in by_rule.values()
            if o.rule_id != source.rule_id and _scope_matches(rel.target_scope, o.rule, source)
        ]  # fmt: skip
    return []


def _condition(rel: Relation, env: dsl.FactEnv, d: date) -> Tri:
    if rel.condition is None:
        return Tri.TRUE
    return dsl.evaluate(dsl.parse(rel.condition), env, d).value


def apply_relations(
    outcomes: list[Outcome],
    relations: list[Relation],
    env: dsl.FactEnv,
    d: date,
    policy: Policy,
    ingested: frozenset[str] = frozenset(),
) -> tuple[list[Outcome], list[Finding]]:
    by_rule = {o.rule_id: o for o in outcomes}
    bar_findings: list[Finding] = []
    barred: set[str] = set()
    explicit_pairs: set[frozenset[str]] = set()

    for rel in sorted(relations, key=lambda r: r.relation_id):
        src = by_rule.get(rel.source_rule_id)
        if src is None:
            continue
        if rel.effect == "supersede":  # src yields to the target(s)
            for tgt in _targets(rel, by_rule, src.rule):
                explicit_pairs.add(frozenset({src.rule_id, tgt.rule_id}))
                if src.result not in VISIBLE_UNKNOWN_SET or tgt.result not in VISIBLE_UNKNOWN_SET:
                    continue
                cond = _condition(rel, env, d)
                if cond is Tri.FALSE:
                    continue
                if tgt.result == APPLIES and cond is Tri.TRUE:
                    src.result, src.superseded_by = SUPERSEDED, tgt.rule_id
                    src.notes.append("superseded")
                    if src.rule_id not in tgt.governs_over:
                        tgt.governs_over.append(src.rule_id)
                else:
                    if src.result == APPLIES:
                        src.result = UNKNOWN
                    src.notes.append(f"may_be_superseded_by:{tgt.rule_id}")
        elif rel.effect == "bar":  # src (a state rule) bars matching local rules
            if rel.active_from and d < rel.active_from:
                continue
            for tgt in _targets(rel, by_rule, src.rule):
                if tgt.rule_id in ingested:
                    tgt.conflicts.append(
                        ConflictFlag(src.rule_id, "barred_by_state", rel.relation_id, None)
                    )
                    continue
                barred.add(tgt.rule_id)
                bar_findings.append(
                    Finding(
                        finding_id=f"bar-{rel.relation_id}-{tgt.rule.jurisdiction.id}",
                        jurisdiction=tgt.rule.jurisdiction,
                        category=tgt.rule.category,
                        reason_code="barred_by_state",
                        explanation={"en": "", "es": ""},
                        evidence=[rel.evidence],
                    )
                )
        elif rel.effect == "conflict_flag":
            if rel.active_from is None or d < rel.active_from:
                continue
            for tgt in _targets(rel, by_rule, src.rule):
                live = {APPLIES, UNKNOWN, NOT_YET}
                if src.result in live and tgt.result in live:
                    explicit_pairs.add(frozenset({src.rule_id, tgt.rule_id}))
                    src.conflicts.append(
                        ConflictFlag(
                            tgt.rule_id, "possible_preemption", rel.relation_id, rel.active_from
                        )
                    )
                    tgt.conflicts.append(
                        ConflictFlag(
                            src.rule_id, "possible_preemption", rel.relation_id, rel.active_from
                        )
                    )

    kept = [o for o in outcomes if o.rule_id not in barred]
    _stricter_rule_fallback(kept, explicit_pairs, d)
    return kept, bar_findings


def _cap(o: Outcome, d: date) -> float | None:
    """The percent cap that is valid on the date, if the rule publishes a numeric one."""
    for kv in o.rule.key_values:
        if kv.unit in ("percent", "%") and isinstance(kv.value, int | float):
            if (kv.valid_from is None or kv.valid_from <= d) and (
                kv.valid_to is None or d <= kv.valid_to
            ):
                return float(kv.value)
    return None


def _stricter_rule_fallback(
    outcomes: list[Outcome], explicit_pairs: set[frozenset[str]], d: date
) -> None:
    """rent_increase_limits only: with no explicit relation and comparable percent caps, the
    lower cap governs (confidence 0.7)."""
    rent = [
        o for o in outcomes if o.rule.category == "rent_increase_limits" and o.result == APPLIES
    ]
    for a in rent:
        for b in rent:
            if a is b or frozenset({a.rule_id, b.rule_id}) in explicit_pairs:
                continue
            ca, cb = _cap(a, d), _cap(b, d)
            if ca is None or cb is None or ca <= cb:
                continue
            a.result, a.superseded_by = SUPERSEDED, b.rule_id  # a has the looser cap
            a.notes.append("superseded_by_stricter_rule")
            if a.rule_id not in b.governs_over:
                b.governs_over.append(a.rule_id)
            break


# ---- the lookup ----


def evaluate_address(
    ruleset: RuleSet,
    record: dict,
    env: dsl.FactEnv,
    d: date,
    policy: Policy | None = None,
    ingested: frozenset[str] = frozenset(),
) -> AddressResult:
    policy = policy or Policy()
    stack = record["stack_ids"]
    location_known = record["resolution_method"] == "point_in_polygon"
    in_state = record["state"]

    outcomes: list[Outcome] = []
    failed: list[Rule] = []
    for rule in ruleset.rules:
        jid = rule.jurisdiction.id
        in_stack = jid in stack
        local_unlocatable = (
            not location_known
            and rule.jurisdiction.level == "city"
            and rule.jurisdiction.state == in_state
        )
        if not (in_stack or local_unlocatable):
            continue
        if rule.lifecycle == "failed":
            failed.append(rule)
            continue
        o = resolve_rule(rule, env, d, policy, location_known=location_known or in_stack)
        if o is not None:
            outcomes.append(o)

    outcomes, bar_findings = apply_relations(outcomes, ruleset.relations, env, d, policy, ingested)
    visible = {(o.rule.jurisdiction.id, o.rule.category) for o in outcomes}
    findings = [
        f for f in ruleset.findings
        if f.jurisdiction.id in stack and (f.jurisdiction.id, f.category) not in visible
    ]  # fmt: skip
    seen = {(f.jurisdiction.id, f.category) for f in findings}
    findings += [f for f in bar_findings if (f.jurisdiction.id, f.category) not in seen]
    return AddressResult(record["address_id"], d, outcomes, failed, findings, list(stack))
