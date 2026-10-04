"""Synthetic rules for engine tests. These are test fixtures only: titles say so, quotes are
placeholders, and none of this is used by the pipeline."""

from __future__ import annotations

import json
from datetime import date

from engine import config
from engine.geo.jurisdictions import CITIES, STATES
from engine.ir import (
    Citation,
    DateValue,
    Exemption,
    JurisdictionRef,
    Relation,
    Rule,
    RuleSet,
)

QUOTE = "[test fixture] placeholder quote used only by tests, not taken from any law."


def jref(jid: str) -> JurisdictionRef:
    if jid in STATES:
        return JurisdictionRef(
            id=jid,
            level="state",
            name=STATES[jid][1],
            label=jid,
            state=jid,  # type: ignore[arg-type]
        )
    for c in CITIES:
        if c.id == jid:
            return JurisdictionRef(
                id=c.id, level="city", name=c.name, label=c.label, state=c.state,  # type: ignore[arg-type]
                geoid=c.place_geoid,
            )  # fmt: skip
    raise KeyError(jid)


def cite(doc="D000", tier="A") -> Citation:
    return Citation(
        doc_id=doc, cite="[test fixture]", url="https://example.invalid/t",
        retrieved_at="2026-10-01T00:00Z", quote=QUOTE, tier=tier,
    )  # fmt: skip


def day(y, m, d) -> DateValue:
    x = date(y, m, d)
    return DateValue(lo=x, hi=x, precision="day")


def rule(rid, cat, jid, *, coverage=None, exemptions=(), lifecycle="enacted", effective=None,
         sunset=None, key_values=(), tier="A") -> Rule:  # fmt: skip
    return Rule(
        rule_id=rid, category=cat, jurisdiction=jref(jid), title=f"[test fixture] {rid}",
        requirement="[test fixture]", key_values=list(key_values),
        coverage=coverage or {"const": True}, coverage_text="[test fixture]",
        exemptions=[Exemption(description=d, predicate=p) for d, p in exemptions],
        lifecycle=lifecycle, effective=effective or DateValue(), sunset=sunset,
        citation=cite(tier=tier), doc_type="statute", confidence=0.9,
    )  # fmt: skip


def rel(rid, typ, src, effect, *, target=None, scope=None, condition=None, active_from=None):
    return Relation(
        relation_id=rid, type=typ, source_rule_id=src, target_rule_id=target,
        target_scope=scope, condition=condition, evidence=cite(), effect=effect,
        active_from=active_from,
    )  # fmt: skip


SF, LA, SD = "CA-0667000", "CA-0644000", "CA-0666000"
JC, HOB, NWK = "NJ-3436000", "NJ-3432250", "NJ-3451000"
BOS, CAM = "MA-2507000", "MA-2511000"

FIFTEEN_YEARS = {"fact": "co_date", "op": ">", "value": {"as_of_minus_years": 15}}


def ruleset() -> RuleSet:
    rules = [
        rule("CA-ALG-01", "algorithmic_rent_setting", "CA", effective=day(2026, 1, 1)),
        rule(
            "CA-RENT-01",
            "rent_increase_limits",
            "CA",
            exemptions=[
                ("CO within 15 years", FIFTEEN_YEARS),
                (
                    "affordable housing",
                    {"fact": "subsidized_or_affordable", "op": "==", "value": True},
                ),
            ],
            effective=day(2024, 4, 1),
            sunset=day(2030, 1, 1),
        ),  # fmt: skip
        rule(
            "CA-DEP-01",
            "security_deposits",
            "CA",
            exemptions=[
                (
                    "small landlord",
                    {
                        "all": [
                            {"fact": "landlord_unit_count", "op": "<=", "value": 4},
                            {"fact": "owner_is_natural_person", "op": "==", "value": True},
                        ]
                    },
                )
            ],
        ),  # fmt: skip
        rule(
            "SF-RENT-01",
            "rent_increase_limits",
            SF,
            coverage={"fact": "co_date", "op": "<=", "value": "1979-06-13"},
        ),
        rule("SF-JCE-01", "just_cause_eviction", SF),
        rule(
            "CA-JCE-01",
            "just_cause_eviction",
            "CA",
            exemptions=[("CO within 15 years", FIFTEEN_YEARS)],
        ),
        rule(
            "LA-RENT-01",
            "rent_increase_limits",
            LA,
            coverage={"fact": "co_date", "op": "<=", "value": "1978-10-01"},
        ),
        rule(
            "SD-JCE-01",
            "just_cause_eviction",
            SD,
            exemptions=[("CO within 15 years", FIFTEEN_YEARS)],
        ),
        rule("NJ-ALG-01", "algorithmic_rent_setting", "NJ", effective=day(2027, 7, 1)),
        rule("JC-ALG-01", "algorithmic_rent_setting", JC, tier="C"),
        rule("HOB-ALG-01", "algorithmic_rent_setting", HOB, tier="C"),
        rule("MA-RENT-01", "rent_increase_limits", "MA"),
        rule("BOS-RENT-01", "rent_increase_limits", BOS),
        rule("BOS-JCE-01", "just_cause_eviction", BOS),
        rule("MA-ALG-P1", "algorithmic_rent_setting", "MA", lifecycle="pending"),
        rule("MA-ALG-P2", "algorithmic_rent_setting", "MA", lifecycle="pending"),
        rule("MA-RENT-P1", "rent_increase_limits", "MA", lifecycle="failed"),
    ]
    relations = [
        rel("R1", "yields_to", "CA-RENT-01", "supersede",
            scope={"category": "rent_increase_limits", "level": "city"}),
        rel("R2", "yields_to", "CA-JCE-01", "supersede",
            scope={"category": "just_cause_eviction", "level": "city"}),
        rel("R3", "conflicts_with", "NJ-ALG-01", "conflict_flag", target="JC-ALG-01",
            active_from=date(2027, 7, 1)),
        rel("R4", "conflicts_with", "NJ-ALG-01", "conflict_flag", target="HOB-ALG-01",
            active_from=date(2027, 7, 1)),
        rel("R5", "bars", "MA-RENT-01", "bar",
            scope={"state": "MA", "level": "city", "category": "rent_increase_limits"}),
    ]  # fmt: skip
    return RuleSet(data_version="test", compiled_at="2026-10-01T00:00:00Z", rules=rules,
                   relations=relations)  # fmt: skip


def resolved() -> dict:
    return json.loads((config.ARTIFACTS / "addresses.resolved.json").read_text(encoding="utf-8"))
