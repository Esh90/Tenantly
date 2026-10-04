"""Deterministic extraction repairs: quotes must verify; no cross-state overrides."""

from engine.compile.context import load_views
from engine.compile.repair import (
    drop_misfiled,
    enrich_citations,
    ensure_relations,
    recover_missing,
    repair_coverage,
    repair_ruleset,
    same_state_scope,
)
from engine.export.build import rule_record
from engine.ir import Citation, RuleSet
from tests import synth

VIEWS, _LINKS = load_views()


def _cite(cite="Cal. Civ. Code § 1946.2", doc="D023") -> Citation:
    return Citation(
        doc_id=doc, cite=cite, url="https://example.invalid", retrieved_at="2026-10-01T00:00Z",
        quote="x" * 24, tier="A",
    )  # fmt: skip


def test_same_state_scope_rejects_boston_versus_california():
    ca = synth.rule("CA-JCE-02", "just_cause_eviction", "CA")
    bos = synth.rule("BOS-JCE-01", "just_cause_eviction", synth.BOS)
    scope = {"category": "just_cause_eviction", "level": "city"}
    assert same_state_scope(scope, synth.rule("SF-JCE-01", "just_cause_eviction", synth.SF), ca)
    assert not same_state_scope(scope, bos, ca)


def test_export_does_not_let_boston_govern_california():
    rs = RuleSet(
        data_version="t",
        compiled_at="t",
        rules=[
            synth.rule("CA-JCE-02", "just_cause_eviction", "CA"),
            synth.rule("BOS-JCE-01", "just_cause_eviction", synth.BOS),
            synth.rule("SF-JCE-01", "just_cause_eviction", synth.SF),
        ],
        relations=[
            synth.rel(
                "REL-001",
                "yields_to",
                "CA-JCE-02",
                "supersede",
                scope={"category": "just_cause_eviction", "level": "city"},
            )
        ],
    )
    bos = rule_record(next(r for r in rs.rules if r.rule_id == "BOS-JCE-01"), rs)
    sf = rule_record(next(r for r in rs.rules if r.rule_id == "SF-JCE-01"), rs)
    assert "CA-JCE-02" not in bos["overrides"]
    assert "CA-JCE-02" in sf["overrides"]


def test_recover_cambridge_jce_and_ma_fees_from_corpus():
    recovered = recover_missing([], VIEWS)
    assert any(r.jurisdiction.id == "MA-2511000" and r.category == "just_cause_eviction" for r in recovered)
    cam = next(r for r in recovered if r.jurisdiction.id == "MA-2511000")
    assert "8.71" in cam.citation.cite
    assert cam.citation.char_start is not None
    fees = [r for r in recovered if r.jurisdiction.id == "MA" and r.category == "application_screening_fees"]
    cites = " ".join(r.citation.cite.lower() for r in fees)
    assert "15b" in cites and "112" in cites


def test_recover_sf_fair_chance_is_affordable_housing_only():
    recovered = recover_missing([], VIEWS)
    sf = next(r for r in recovered if r.jurisdiction.id == "CA-0667000" and r.category == "screening_restrictions")
    assert sf.coverage == {"fact": "subsidized_or_affordable", "op": "==", "value": True}


def test_drop_rent_cap_filed_as_a_deposit():
    bad = synth.rule("CA-DEP-01", "security_deposits", "CA")
    bad = bad.model_copy(
        update={"citation": _cite("Cal. Civ. Code § 1947.12 (as applied in Berkeley, CA)")}
    )
    kept = drop_misfiled([bad, synth.rule("CA-DEP-02", "security_deposits", "CA")])
    assert [r.rule_id for r in kept] == ["CA-DEP-02"]


def test_nj_fair_chance_cite_gains_public_law_number():
    r = synth.rule("NJ-SCR-01", "screening_restrictions", "NJ")
    r = r.model_copy(
        update={
            "citation": r.citation.model_copy(
                update={"url": "https://pub.njleg.gov/bills/2020/PL21/110_.HTM", "cite": "N.J.S.A. 46:8-56"}
            )
        }
    )
    out = enrich_citations([r])[0]
    assert "2021" in out.citation.cite and "110" in out.citation.cite


def test_sf_rent_coverage_is_not_always_true():
    sf = synth.rule("SF-RENT-01", "rent_increase_limits", synth.SF)
    assert sf.coverage == {"const": True}
    fixed = repair_coverage([sf], VIEWS)[0]
    assert fixed.coverage.get("fact") == "co_date"
    assert fixed.coverage.get("op") == "<="
    assert str(fixed.coverage.get("value")).startswith("1979")


def test_state_algorithmic_rule_does_not_inherit_a_city_cutoff():
    ca = synth.rule("CA-ALG-01", "algorithmic_rent_setting", "CA")
    ca = ca.model_copy(
        update={
            "coverage": {"fact": "co_date", "op": "<=", "value": "1979-06-13"},
            "provenance": {"notes": ["coverage repaired from sibling rule or same-jurisdiction source text"]},
        }
    )
    fixed = repair_coverage([ca], VIEWS)[0]
    assert fixed.coverage == {"const": True}


def test_ca_rent_yields_to_local_from_d024():
    ca = synth.rule("CA-RENT-01", "rent_increase_limits", "CA")
    ca = ca.model_copy(update={"citation": _cite("Cal. Civ. Code § 1947.12", "D024")})
    rels, _ = ensure_relations([], [ca], VIEWS)
    assert rels
    assert rels[0].source_rule_id == "CA-RENT-01"
    assert rels[0].effect == "supersede"
    assert rels[0].target_scope["state"] == "CA"


def test_repair_ruleset_is_idempotent():
    rs = RuleSet.model_validate(
        {
            "data_version": "t",
            "compiled_at": "t",
            "rules": [
                synth.rule("CA-RENT-01", "rent_increase_limits", "CA")
                .model_copy(update={"citation": _cite("Cal. Civ. Code § 1947.12", "D024")})
                .model_dump(mode="json")
            ],
        }
    )
    once = repair_ruleset(rs, VIEWS)
    twice = repair_ruleset(once, VIEWS)
    assert {r.rule_id for r in once.rules} == {r.rule_id for r in twice.rules}
    assert len(once.relations) == len(twice.relations)
