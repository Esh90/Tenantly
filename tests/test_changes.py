"""T1 to T5 against PLAN.md 3.3, computed from resolved cities, plus the id mapping rules.

The ruleset here is synthetic (tests/synth.py): it exercises the runner and the engine with the
same structure the compiled law will have. The real compiled rules are checked in Phase 2.
"""

import json

import pytest

from engine import config
from engine.ir import RuleSet
from engine.rules.changes import AmbiguousMapping, map_test_rule, run_all, run_test
from tests import synth

RS = synth.ruleset()
REC = synth.resolved()
TESTS = json.loads(config.CHANGE_TESTS.read_text(encoding="utf-8"))
OUT = run_all(TESTS, RS, REC)


def ids_where(pred):
    return sorted(a for a, r in REC.items() if pred(r))


def test_t1_all_california_addresses():
    t = OUT["T1"]
    assert t.affected_ids == ids_where(lambda r: r["state"] == "CA")
    assert len(t.affected_ids) == 250 and t.conflict_ids == []
    assert all(a.before == [("CA-ALG-01", "not_yet_effective")] for a in t.affected)
    assert all(a.after == [("CA-ALG-01", "applies")] for a in t.affected)
    assert "250 of 250" in t.notes


def test_t2_hoboken_and_jersey_city_only():
    t = OUT["T2"]
    hob = ids_where(lambda r: r["city_id"] == synth.HOB)
    jc = ids_where(lambda r: r["city_id"] == synth.JC)
    assert len(hob) == 40 and len(jc) == 50
    assert t.affected_ids == sorted(hob + jc) and len(t.affected_ids) == 90
    assert not set(t.affected_ids) & set(ids_where(lambda r: r["city_id"] == synth.NWK))
    assert "JC-ALG-01 reaches 50" in t.notes and "HOB-ALG-01 reaches 40" in t.notes
    assert t.conflict_ids == []


def test_t3_all_nj_addresses_and_90_conflict_flags():
    t = OUT["T3"]
    assert t.affected_ids == ids_where(lambda r: r["state"] == "NJ") and len(t.affected_ids) == 140
    expected = ids_where(lambda r: r["city_id"] in (synth.JC, synth.HOB))
    assert t.conflict_ids == expected and len(expected) == 90
    assert all(a.before == [("NJ-ALG-01", "not_yet_effective")] for a in t.affected)
    assert all(a.after == [("NJ-ALG-01", "applies")] for a in t.affected)
    assert "90 carry a conflict flag" in t.notes


def test_t4_all_massachusetts_addresses():
    t = OUT["T4"]
    # every MA address in a located city; the one that could not be geocoded is still state MA
    assert len(t.affected_ids) == 110
    assert t.affected_ids == ids_where(lambda r: r["state"] == "MA")


def test_t5_negative_is_empty_and_records_the_failed_rule():
    t = OUT["T5"]
    assert t.affected_ids == [] and t.conflict_ids == []
    assert "MA-RENT-P1 recorded as failed" in t.notes


def test_every_test_has_the_three_keys_and_sorted_ids():
    for t in OUT.values():
        assert t.affected_ids == sorted(t.affected_ids)
        assert t.conflict_ids == sorted(t.conflict_ids)
        assert t.notes


def test_conflict_flag_requires_the_after_date():
    """On 2026-10-01 the FAIR Act conflict is not yet active (lookups.json has no flags)."""
    t = run_test(
        {"test_id": "X", "title": "x", "type": "as_of", "rule_ids": ["NJ-ALG-01"],
         "as_of_before": "2026-10-01", "as_of_after": "2026-10-02", "states": ["NJ"],
         "conflict_with": ["JC-ALG-01", "HOB-ALG-01"]},
        RS, REC,
    )  # fmt: skip
    assert t.conflict_ids == [] and t.affected_ids == []


# ---- mapping ----


def _ruleset(*rules):
    return RuleSet(data_version="t", compiled_at="t", rules=list(rules))


def test_exact_team_rule_id_wins():
    assert map_test_rule("CA-ALG-01", {"title": ""}, RS) == "CA-ALG-01"


def test_prefix_and_token_mapping_when_ids_differ():
    rs = _ruleset(
        synth.rule("JC-ALG-07", "algorithmic_rent_setting", synth.JC),
        synth.rule("HOB-ALG-03", "algorithmic_rent_setting", synth.HOB),
    )
    assert map_test_rule("JC-ALG-01", {"title": ""}, rs) == "JC-ALG-07"
    assert map_test_rule("HOB-ALG-01", {"title": ""}, rs) == "HOB-ALG-03"


def test_ambiguous_mapping_raises():
    rs = _ruleset(
        synth.rule("CA-ALG-02", "algorithmic_rent_setting", "CA"),
        synth.rule("CA-ALG-03", "algorithmic_rent_setting", "CA"),
    )
    with pytest.raises(AmbiguousMapping):
        map_test_rule("CA-ALG-01", {"title": ""}, rs)
    with pytest.raises(AmbiguousMapping):
        map_test_rule("ZZ-ALG-01", {"title": ""}, rs)
    with pytest.raises(AmbiguousMapping):
        map_test_rule("JC-ALG-01", {"title": ""}, _ruleset())  # nothing to map to


def test_pending_ids_map_in_bill_order_of_the_test_title():
    def pending(rid, cite):
        r = synth.rule(rid, "algorithmic_rent_setting", "MA", lifecycle="pending")
        return r.model_copy(update={"citation": r.citation.model_copy(update={"cite": cite})})

    rs = _ruleset(pending("MA-ALG-P7", "H.5222"), pending("MA-ALG-P8", "S.2983"))
    title = "Massachusetts pending bills S.2983 and H.5222"
    assert map_test_rule("MA-ALG-P1", {"title": title}, rs) == "MA-ALG-P8"  # S.2983 first
    assert map_test_rule("MA-ALG-P2", {"title": title}, rs) == "MA-ALG-P7"  # H.5222 second


def test_failed_ballot_question_maps_by_category_and_state():
    failed = synth.rule("MA-RENT-P3", "rent_increase_limits", "MA", lifecycle="failed")
    boston_failed = synth.rule("BOS-RENT-P1", "rent_increase_limits", synth.BOS, lifecycle="failed")
    rs = _ruleset(failed, boston_failed)
    assert map_test_rule("MA-RENT-P1", {"title": "ballot question struck"}, rs) == "MA-RENT-P3"
