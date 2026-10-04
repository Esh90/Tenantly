"""Timelines: breakpoints, merged segments, upcoming changes, decisive question."""

from datetime import date

from engine.rules.decisive import decisive_question
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv
from engine.rules.timeline import (
    build_timeline,
    collect_breakpoints,
    segment_at,
    transitions,
)
from tests import synth

RS = synth.ruleset()
REC = synth.resolved()


def tl(aid, user=None):
    return build_timeline(RS, REC[aid], user)


def results_at(segs, d):
    return {o.rule_id: o.result for o in segment_at(segs, d).result.outcomes}


def test_sf_timeline_breaks_at_the_ca_ordinance_start():
    segs = tl("A0016")
    starts = [s.start for s in segs]
    assert date(2025, 1, 1) in starts and date(2026, 1, 1) in starts
    assert results_at(segs, date(2025, 12, 31))["CA-ALG-01"] == "not_yet_effective"
    assert results_at(segs, date(2026, 1, 2))["CA-ALG-01"] == "applies"
    assert segs[-1].end is None
    for a, b in zip(segs, segs[1:], strict=False):
        assert a.end == b.start  # contiguous


def test_sunset_is_a_breakpoint():
    rs = RS.model_copy(update={"rules": [r for r in RS.rules if r.rule_id == "CA-RENT-01"]})
    rec = REC["A0001"]
    rec_segs = build_timeline(rs, rec, end=date(2031, 12, 31))
    assert results_at(rec_segs, date(2029, 12, 31)).get("CA-RENT-01") == "applies"
    assert "CA-RENT-01" not in results_at(rec_segs, date(2030, 1, 1))


def test_adjacent_identical_segments_are_merged():
    segs = tl("A0001")  # LA 1927 building: only the 2026-01-01 change matters in range
    results = [tuple(sorted((o.rule_id, o.result) for o in s.result.outcomes)) for s in segs]
    assert all(a != b for a, b in zip(results, results[1:], strict=False))


def test_fair_act_conflict_appears_in_the_2027_07_01_segment():
    jc = next(a for a, r in REC.items() if r["city_id"] == synth.JC)
    segs = tl(jc)
    assert date(2027, 7, 1) in [s.start for s in segs]
    before = segment_at(segs, date(2027, 6, 30)).result.by_rule()["NJ-ALG-01"]
    after = segment_at(segs, date(2027, 7, 1)).result.by_rule()["NJ-ALG-01"]
    assert before.result == "not_yet_effective" and not before.conflict_flag
    assert after.result == "applies" and after.conflict_flag


def test_age_threshold_creates_a_breakpoint_for_a_2012_building():
    la_2012 = next(
        a
        for a, r in REC.items()
        if r["city_id"] == synth.LA and r["facts"]["year_built"]["lo"] == 2012
    )
    env = AddressEnv(REC[la_2012])
    bps = collect_breakpoints(RS, REC[la_2012], env)
    assert any("age" in b.kinds and b.date.year == 2027 for b in bps)  # 15-year window closes
    segs = tl(la_2012)
    assert "CA-RENT-01" not in results_at(segs, date(2026, 10, 1))  # exempt now
    assert results_at(segs, date(2027, 6, 1)).get("CA-RENT-01") == "unknown"  # inside the CO year
    assert results_at(segs, date(2028, 6, 1)).get("CA-RENT-01") in ("applies", "superseded")


def test_upcoming_changes_list_transitions_after_a_date():
    segs = tl("A0016")
    up = transitions(segs, date(2025, 6, 1))
    assert {"date": date(2026, 1, 1), "rule_id": "CA-ALG-01", "title": "[test fixture] CA-ALG-01",
            "from": "not_yet_effective", "to": "applies"} in up  # fmt: skip
    assert transitions(segs, date(2028, 12, 31)) == []


def test_timeline_for_user_supplied_facts_differs_from_the_data_default():
    sd = next(a for a, r in REC.items() if r["city_id"] == synth.SD)
    default = results_at(tl(sd), date(2026, 10, 1))
    user = results_at(tl(sd, {"year_built": 1985}), date(2026, 10, 1))
    assert default["SD-JCE-01"] == "unknown" and user["SD-JCE-01"] == "applies"


# ---- decisive question ----


def test_decisive_question_for_a_san_diego_row_asks_the_year():
    sd = next(a for a, r in REC.items() if r["city_id"] == synth.SD)
    rec = REC[sd]
    res = evaluate_address(RS, rec, AddressEnv(rec), date(2026, 10, 1))
    q = decisive_question(res)
    assert q["fact"] == "year_built" and q["input"] == "year"
    assert "SD-JCE-01" in q["resolves_rule_ids"]
    assert q["prompt"]["es"].startswith("¿En qué año")


def test_no_decisive_question_when_nothing_is_unknown():
    rec = REC["A0001"]  # LA 1927, 32 units: everything is decided
    res = evaluate_address(RS, rec, AddressEnv(rec), date(2026, 10, 1))
    assert not [
        o for o in res.outcomes if o.result == "unknown" and "location" not in o.missing_facts
    ]
    assert decisive_question(res) is None


def test_no_decisive_question_for_location_unknown_only():
    rec = REC["A0295"]
    res = evaluate_address(RS, rec, AddressEnv(rec), date(2026, 10, 1))
    assert decisive_question(res) is None
