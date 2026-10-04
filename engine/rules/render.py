"""Render engine results as API ``LookupResponse`` dicts (PLAN.md 14.3).

Pure and deterministic. The same function serves the live API, the precomputed timelines and
the static snapshot, so every surface shows the same answer.
"""

from __future__ import annotations

from datetime import date

from engine import config
from engine.geo.jurisdictions import CITIES, COUNTIES, STATES
from engine.ir import Rule, RuleSet
from engine.models import CATEGORIES, RESULTS
from engine.rules import templates as T
from engine.rules.decisive import decisive_question
from engine.rules.engine import AddressResult, Outcome
from engine.rules.explain import explain
from engine.rules.facts_env import AddressEnv
from engine.rules.timeline import Segment, transitions

RESULT_ORDER = {"applies": 0, "superseded": 1, "unknown": 2, "not_yet_effective": 3}
GEOCODER = {
    "census_batch": "census_batch", "census_oneline": "census_oneline",
    "nominatim": "nominatim", "none": "none",
}  # fmt: skip


def title_case(street: str) -> str:
    return street.title() if street.isupper() else street


def address_label(rec: dict) -> str:
    zip_part = f" {rec['zip']}" if rec.get("zip") else ""
    return f"{title_case(rec['street'])}, {rec['postal_city']}, {rec['state']}{zip_part}"


def address_summary(rec: dict) -> dict:
    return {
        "address_id": rec["address_id"], "label": address_label(rec),
        "street": title_case(rec["street"]), "postal_city": rec["postal_city"], "zip": rec["zip"],
        "state": rec["state"], "lat": rec["lat"], "lon": rec["lon"], "legal_city": rec["legal_city"],
        "is_sample": True,
    }  # fmt: skip


def index_item(rec: dict) -> dict:
    return {
        "address_id": rec["address_id"], "label": address_label(rec),
        "postal_city": rec["postal_city"], "legal_city": rec["legal_city"], "state": rec["state"],
        "zip": rec["zip"], "lat": rec["lat"], "lon": rec["lon"],
    }  # fmt: skip


def jurisdiction_json(j) -> dict:
    return {"id": j.id, "level": j.level, "name": j.name, "label": j.label, "state": j.state,
            "geoid": j.geoid, "in_scope": True}  # fmt: skip


def state_jurisdiction(code: str) -> dict:
    return {"id": code, "level": "state", "name": STATES[code][1], "label": code, "state": code,
            "geoid": None, "in_scope": True}  # fmt: skip


def city_jurisdiction(jid: str) -> dict:
    c = next(c for c in CITIES if c.id == jid)
    return {"id": c.id, "level": "city", "name": c.name, "label": c.label, "state": c.state,
            "geoid": c.place_geoid, "in_scope": True}  # fmt: skip


def county_jurisdiction(jid: str) -> dict:
    fips = jid.split("-", 1)[1]
    name, state = next((n, s) for f, n, s in COUNTIES if f == fips)
    return {"id": jid, "level": "county", "name": name, "label": f"{name}, {state}", "state": state,
            "geoid": fips, "in_scope": False}  # fmt: skip


def jurisdiction_stack(rec: dict) -> dict:
    return {
        "state": state_jurisdiction(rec["state"]),
        "county": county_jurisdiction(rec["county_id"]) if rec["county_id"] else None,
        "city": city_jurisdiction(rec["city_id"]) if rec["city_id"] else None,
        "mailing_city": rec["postal_city"],
        "mailing_mismatch": rec["mailing_mismatch"],
        "note": rec["mailing_note"],
        "resolution": {
            "method": rec["resolution_method"],
            "geocoder": GEOCODER[rec["geocoder"]],
            "census_agrees": rec["census_agrees"],
        },
    }


def _fact_value(label: tuple[str, str], iv=None, scalar=None, source="missing", basis=None,
                conflict=False) -> dict:  # fmt: skip
    interval = None
    value = scalar
    if iv is not None and not iv.is_unknown:
        interval = [iv.lo, iv.hi]
        value = iv.lo if iv.is_exact else None
    return {"value": value, "interval": interval,
            "source": source if (value is not None or interval) else "missing",
            "basis": basis, "record_conflict": conflict, "label": T.bi(*label)}  # fmt: skip


def building_facts(rec: dict, env: AddressEnv, d: date) -> dict:
    def interval(name, label_en, label_es):
        v = env.get(name, d)
        return _fact_value((label_en, label_es), iv=v.interval, source=v.source, basis=v.basis,
                           conflict=v.record_conflict)  # fmt: skip

    pt = env.get("property_type", d)
    sub = env.get("subsidized_or_affordable", d)
    f = rec["facts"]
    return {
        "year_built": interval("year_built", "Year built", "Año de construcción"),
        "units": interval("units", "Number of units", "Número de unidades"),
        "property_type": _fact_value(("Property type", "Tipo de propiedad"), scalar=pt.scalar,
                                     source=pt.source, basis=pt.basis),  # fmt: skip
        "subsidized": _fact_value(("Subsidized or affordable", "Subsidiado o asequible"),
                                  scalar=sub.scalar, source=sub.source, basis=sub.basis),  # fmt: skip
        "use_code": f["use_code"], "use_description": f["use_description"],
        "source_dataset": f["source_dataset"], "zip_suspect": rec["zip_suspect"],
    }  # fmt: skip


def citation_json(c) -> dict:
    return c.model_dump(mode="json")


def rule_status(rule: Rule, d: date) -> str:
    if rule.lifecycle == "failed":
        return "failed"
    if rule.lifecycle == "pending":
        return "pending"
    if rule.effective.lo is not None and rule.effective.lo > d:
        return "not_yet_effective"
    return "in_force"


def effective_note(rule: Rule, d: date) -> dict | None:
    eff = rule.effective
    if rule.lifecycle != "enacted":
        return None
    if eff.lo is None and eff.hi is None:
        return T.bi(
            "The effective date is not in our sources.",
            "La fecha de entrada en vigor no está en nuestras fuentes.",
        )
    if eff.lo is not None and eff.hi is not None and eff.lo != eff.hi:
        a, b = T.date_long(eff.lo), T.date_long(eff.hi)
        return T.bi(
            f"Sources give dates from {a['en']} to {b['en']}.",
            f"Las fuentes dan fechas del {a['es']} al {b['es']}.",
        )
    if eff.lo is not None and eff.lo > d:
        return T.not_yet_headline(eff.lo)
    return None


def key_values_json(rule: Rule, d: date) -> list[dict]:
    out = []
    for kv in rule.key_values:
        in_window = (kv.valid_from is None or kv.valid_from <= d) and (
            kv.valid_to is None or d <= kv.valid_to
        )
        out.append(
            {
                "name": kv.name, "text": kv.text,
                "valid_from": kv.valid_from.isoformat() if kv.valid_from else None,
                "valid_to": kv.valid_to.isoformat() if kv.valid_to else None,
                "stale": not in_window,
                "stale_note": None if in_window else T.stale_note(kv.text, kv.valid_from, kv.valid_to, d),
            }
        )  # fmt: skip
    return out


def _trace_json(items) -> list[dict]:
    return [
        {
            "label": T.bi(t.label_en, t.label_es), "fact": t.fact, "op": t.op,
            "expected": t.expected, "actual": t.actual, "basis": t.basis, "result": t.result.value,
        }
        for t in items
    ]  # fmt: skip


def _plain(rule: Rule, key: str) -> dict:
    en = rule.plain.get(f"{key}_en")
    es = rule.plain.get(f"{key}_es")
    return T.bi(en, es) if en and es else None  # type: ignore[return-value]


def rule_result(o: Outcome, d: date, titles: dict[str, str]) -> dict:
    rule = o.rule
    summary = _plain(rule, "summary") or T.bi(rule.requirement, rule.requirement)
    who = _plain(rule, "who") or T.bi(rule.coverage_text, rule.coverage_text)
    conflicts = [
        {
            "with_rule_id": c.with_rule_id, "kind": c.kind,
            "explanation": T.conflict_explanation(c.kind, c.with_rule_id, c.active_from),
            "evidence": None,
            "active_from": c.active_from.isoformat() if c.active_from else None,
        }
        for c in o.conflicts
    ]  # fmt: skip
    return {
        "rule_id": rule.rule_id, "category": rule.category, "title": rule.title,
        "jurisdiction": _ref_json(rule), "result": o.result, "rule_status": rule_status(rule, d),
        "effective_date": rule.effective.output(), "effective_note": effective_note(rule, d),
        "summary": summary, "who": who, "reason": explain(o, d, titles),
        "key_values": key_values_json(rule, d),
        "conditions": _trace_json(o.trace + o.exemption_trace),
        "caveats": [T.bi(c, c) for c in o.caveats], "missing_facts": list(o.missing_facts),
        "superseded_by": o.superseded_by, "governs_over": list(o.governs_over),
        "conflicts": conflicts, "conflict_flag": o.conflict_flag,
        "citation": citation_json(rule.citation),
        "extra_citations": [citation_json(c) for c in rule.extra_citations],
        "confidence": rule.confidence, "review_flag": rule.review_flag,
        "open_question_ids": list(rule.open_question_ids),
        "audio": {"en": rule.audio.get("en"), "es": rule.audio.get("es")},
    }  # fmt: skip


def _ref_json(rule: Rule) -> dict:
    return jurisdiction_json(rule.jurisdiction)


def finding_json(f) -> dict:
    explanation = f.explanation
    if not explanation.get("en"):  # created by a state bar: wording is deterministic
        explanation = T.barred_headline(f.jurisdiction.state)
    return {
        "finding_id": f.finding_id, "category": f.category, "jurisdiction": jurisdiction_json(f.jurisdiction),
        "reason_code": f.reason_code, "explanation": T.bi(explanation["en"], explanation["es"]),
        "evidence": [citation_json(c) for c in f.evidence],
    }  # fmt: skip


def _headline(category: str, results: list[dict], findings: list[dict], state: str) -> dict:
    for r in results:
        if r["result"] == "applies":
            return T.applies_headline(category, r["title"])
    for r in results:
        if r["result"] == "unknown":
            return T.unknown_headline(r["missing_facts"] or ["co_date"])
    for r in results:
        if r["result"] == "superseded":
            return T.applies_headline(category, r["title"])
    for r in results:
        eff = r["effective_date"]
        if r["result"] == "not_yet_effective" and eff and len(eff) == 10:
            return T.not_yet_headline(date.fromisoformat(eff))
    for f in findings:
        if f["reason_code"] == "barred_by_state":
            return T.barred_headline(state)
    return T.nothing_found_headline()


def render_lookup(
    ruleset: RuleSet,
    rec: dict,
    result: AddressResult,
    env: AddressEnv,
    segments: list[Segment] | None = None,
    facts_source: str = "data",
    n_docs: int = 54,
) -> dict:
    d = result.as_of
    by_id = {r.rule_id: r for r in ruleset.rules}
    titles = {r.rule_id: r.title for r in ruleset.rules}
    rendered = {o.rule_id: rule_result(o, d, titles) for o in result.outcomes}
    findings = [finding_json(f) for f in result.findings]

    blocks = []
    for cat in CATEGORIES:
        rs = [
            rendered[o.rule_id]
            for o in result.outcomes
            if o.rule.category == cat and o.result != "pending"
        ]
        rs.sort(
            key=lambda r: (
                RESULT_ORDER[r["result"]],
                r["jurisdiction"]["level"] != "city",
                r["rule_id"],
            )
        )
        fs = sorted((f for f in findings if f["category"] == cat), key=lambda f: f["finding_id"])
        en, es = T.CATEGORY_LABELS[cat]
        blocks.append(
            {
                "category": cat,
                "label": T.bi(en, es),
                "headline": _headline(cat, rs, fs, rec["state"]),
                "results": rs,
                "findings": fs,
            }  # fmt: skip
        )
    pending = [rendered[o.rule_id] for o in result.outcomes if o.result == "pending"]
    failed = [
        {
            "rule_id": r.rule_id, "title": r.title,
            "note": T.failed_note(r.title, r.provenance.get("failed_reason")),
            "citation": citation_json(r.citation),
        }
        for r in sorted(result.failed, key=lambda r: r.rule_id)
    ]  # fmt: skip
    counts = dict.fromkeys(RESULTS, 0)
    for o in result.outcomes:
        counts[o.result] += 1
    upcoming = []
    if segments:
        for t in transitions(segments, d):
            rule = by_id[t["rule_id"]]
            upcoming.append(
                {
                    "date": t["date"].isoformat(), "rule_id": t["rule_id"], "title": rule.title,
                    "from": t["from"], "to": t["to"],
                    "summary": T.not_yet_headline(t["date"]) if t["to"] == "applies" else T.bi(
                        f"Status changes to {t['to'].replace('_', ' ')}.",
                        f"El estado cambia a {t['to'].replace('_', ' ')}.",
                    ),
                }
            )  # fmt: skip
    visible_ids = set(rendered)
    oqs = [
        {
            "oq_id": q.oq_id, "title": T.bi(q.title["en"], q.title["es"]),
            "detail": T.bi(q.detail["en"], q.detail["es"]), "rule_ids": list(q.rule_ids),
            "sources": [citation_json(c) for c in q.sources],
            "changes_answer_between": [x.isoformat() for x in q.changes_answer_between]
            if q.changes_answer_between else None,
        }
        for q in ruleset.open_questions
        if visible_ids & set(q.rule_ids)
    ]  # fmt: skip
    retrieved = T.date_long(date.fromisoformat(config.SOURCES_RETRIEVED_AT))
    return {
        "address": address_summary(rec), "jurisdiction": jurisdiction_stack(rec),
        "facts": building_facts(rec, env, d), "as_of": d.isoformat(), "categories": blocks,
        "pending": pending, "failed": failed, "upcoming": upcoming, "counts": counts,
        "decisive_question": decisive_question(result), "open_questions": oqs,
        "reasoning_boundary": T.reasoning_boundary(
            n_docs, retrieved["en"], facts_source, rec["resolution_method"] == "point_in_polygon"
        ),
        "facts_source": facts_source, "sources_retrieved_at": config.SOURCES_RETRIEVED_AT,
        "is_projection": d.isoformat() > config.SOURCES_RETRIEVED_AT,
        "data_version": ruleset.data_version, "disclaimer": config.DISCLAIMER, "fallback": False,
    }  # fmt: skip
