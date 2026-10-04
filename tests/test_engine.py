"""Lifecycle, exemptions, precedence, conflicts and bars (PLAN.md 8.5 and 8.6)."""

from datetime import date

import pytest

from engine.ir import KeyValue
from engine.rules.engine import Policy, evaluate_address
from engine.rules.facts_env import AddressEnv
from tests import synth

RS = synth.ruleset()
REC = synth.resolved()
D0 = date(2026, 10, 1)


def run(aid, d=D0, user=None, ruleset=RS, policy=None, ingested=frozenset()):
    rec = REC[aid]
    return evaluate_address(ruleset, rec, AddressEnv(rec, user), d, policy, ingested)


def results(aid, d=D0, **kw):
    return {o.rule_id: o.result for o in run(aid, d, **kw).outcomes}


def addresses_where(pred):
    return [a for a, r in REC.items() if pred(r)]


def la_built(year):
    return next(
        a for a, r in REC.items()
        if r["city_id"] == synth.LA and r["facts"]["year_built"]["lo"] == year
    )  # fmt: skip


# ---- lifecycle ----


def test_not_yet_effective_then_applies():
    assert results("A0016", date(2025, 12, 31))["CA-ALG-01"] == "not_yet_effective"
    assert results("A0016", date(2026, 1, 1))["CA-ALG-01"] == "applies"


def test_failed_rules_never_appear_but_are_reported():
    r = run("A0118")
    assert "MA-RENT-P1" not in {o.rule_id for o in r.outcomes}
    assert [x.rule_id for x in r.failed] == ["MA-RENT-P1"]


def test_pending_never_applies_and_would_reach_every_ma_address():
    for aid in addresses_where(lambda r: r["state"] == "MA" and r["city_id"]):
        out = run(aid).by_rule()
        for rid in ("MA-ALG-P1", "MA-ALG-P2"):
            assert out[rid].result == "pending" and out[rid].would_reach is True


def test_sunset_removes_the_rule_after_repeal():
    assert "CA-RENT-01" in results("A0001", date(2029, 12, 31))
    assert "CA-RENT-01" not in results("A0001", date(2030, 1, 1))


def test_effective_date_interval_makes_the_status_unknown_inside_it():
    iv = synth.rule("X-ALG-01", "algorithmic_rent_setting", "CA")
    iv = iv.model_copy(
        update={
            "effective": synth.DateValue(lo=date(2026, 1, 1), hi=date(2026, 3, 1), precision="day")
        }
    )
    rs = RS.model_copy(update={"rules": [iv]})
    assert results("A0016", date(2026, 2, 1), ruleset=rs) == {"X-ALG-01": "unknown"}
    assert results("A0016", date(2026, 3, 1), ruleset=rs) == {"X-ALG-01": "applies"}
    assert results("A0016", date(2025, 12, 31), ruleset=rs) == {"X-ALG-01": "not_yet_effective"}


# ---- exemptions and unknown ----


def test_certificate_of_occupancy_within_15_years_exempts():
    new = la_built(2012)
    assert "CA-RENT-01" not in results(new)  # built 2012: exempt on 2026-10-01
    old = la_built(1927)  # the LA rule governs this one, so the state cap is superseded
    assert results(old)["CA-RENT-01"] == "superseded"
    berkeley = addresses_where(lambda r: r["city_id"] == "CA-0606000")[0]  # no local rule here
    assert results(berkeley, user={"year_built": 1927})["CA-RENT-01"] == "applies"
    assert "CA-RENT-01" not in results(berkeley, user={"year_built": 2012})
    assert results(berkeley)["CA-RENT-01"] == "unknown"  # year built is not in the record


def test_cutoff_year_building_is_unknown_not_excluded():
    a1978 = la_built(1978)
    assert results(a1978)["LA-RENT-01"] == "unknown"
    assert results(la_built(1927))["LA-RENT-01"] == "applies"
    after = next(
        a for a, r in REC.items()
        if r["city_id"] == synth.LA and (r["facts"]["year_built"]["lo"] or 0) >= 1980
    )  # fmt: skip
    assert "LA-RENT-01" not in results(after)  # built after the cutoff


def test_unknown_year_built_gives_unknown_not_applies():
    sd = addresses_where(lambda r: r["city_id"] == synth.SD)[0]
    assert results(sd)["SD-JCE-01"] == "unknown"
    o = next(o for o in run(sd).outcomes if o.rule_id == "SD-JCE-01")
    assert "co_date" in o.missing_facts


def test_user_supplied_year_resolves_the_unknown():
    sd = addresses_where(lambda r: r["city_id"] == synth.SD)[0]
    assert results(sd, user={"year_built": 1985})["SD-JCE-01"] == "applies"
    assert "SD-JCE-01" not in results(sd, user={"year_built": 2020})


def test_small_landlord_exception_ruled_out_at_5_plus_units():
    a = "A0016"  # 21 units in the data
    o = next(o for o in run(a).outcomes if o.rule_id == "CA-DEP-01")
    assert o.result == "applies" and o.caveats == []  # exception cannot apply, so no caveat


def test_small_landlord_exception_becomes_a_caveat_when_units_unknown():
    a = "A0398"  # SF: the TIC record conflict leaves the unit count unknown
    o = next(o for o in run(a).outcomes if o.rule_id == "CA-DEP-01")
    assert o.result == "applies" and o.caveats == ["small landlord"]


def test_exemption_policy_switch_makes_missing_renter_facts_unknown():
    a = "A0398"  # SF: the TIC record conflict leaves the unit count unknown
    out = results(a, policy=Policy(exemption_missing_fact="unknown"))
    assert out["CA-DEP-01"] == "unknown"


def test_subsidized_exemption_from_the_data_flag():
    sub = {"subsidized_or_affordable": True}
    berkeley = addresses_where(lambda r: r["city_id"] == "CA-0606000")[0]
    assert results(berkeley, user={"year_built": 1927, **sub}).get("CA-RENT-01") is None


# ---- precedence ----


def test_local_rent_control_governs_and_state_cap_is_superseded():
    out = run("A0016").by_rule()  # SF, built 1926
    assert out["SF-RENT-01"].result == "applies"
    assert out["CA-RENT-01"].result == "superseded"
    assert out["CA-RENT-01"].superseded_by == "SF-RENT-01"
    assert out["SF-RENT-01"].governs_over == ["CA-RENT-01"]


def test_state_cap_governs_when_local_rule_does_not_cover_the_building():
    sf_new = next(
        a for a, r in REC.items()
        if r["city_id"] == synth.SF and (r["facts"]["year_built"]["lo"] or 0) >= 1990
    )  # fmt: skip
    out = results(sf_new)
    assert "SF-RENT-01" not in out and out["CA-RENT-01"] != "superseded"


def test_state_rule_is_unknown_when_the_local_rule_is_unknown():
    sf_missing = next(
        a for a, r in REC.items()
        if r["city_id"] == synth.SF and r["facts"]["year_built"]["lo"] is None
    )  # fmt: skip
    out = run(sf_missing).by_rule()
    assert out["SF-RENT-01"].result == "unknown"
    assert out["CA-RENT-01"].result == "unknown"
    assert "may_be_superseded_by:SF-RENT-01" in out["CA-RENT-01"].notes


def test_just_cause_yields_to_local_just_cause():
    out = results("A0016")
    assert out["SF-JCE-01"] == "applies" and out["CA-JCE-01"] == "superseded"


def test_stricter_rule_fallback_when_no_explicit_relation():
    kv = lambda v: [KeyValue(name="cap", text=f"{v}%", value=v, unit="percent")]  # noqa: E731
    rs = synth.RuleSet(
        data_version="t", compiled_at="t",
        rules=[
            synth.rule("CA-RENT-01", "rent_increase_limits", "CA", key_values=kv(10)),
            synth.rule("SF-RENT-01", "rent_increase_limits", synth.SF, key_values=kv(1.6)),
        ],
    )  # fmt: skip
    out = run("A0016", ruleset=rs).by_rule()
    assert (
        out["CA-RENT-01"].result == "superseded"
        and "superseded_by_stricter_rule" in out["CA-RENT-01"].notes
    )
    assert out["SF-RENT-01"].result == "applies"


# ---- conflicts ----


def test_fair_act_conflict_flags_only_after_it_takes_effect():
    jc = addresses_where(lambda r: r["city_id"] == synth.JC)[0]
    hob = addresses_where(lambda r: r["city_id"] == synth.HOB)[0]
    nwk = addresses_where(lambda r: r["city_id"] == synth.NWK)[0]
    for aid in (jc, hob):
        before = run(aid, D0).by_rule()
        assert not before["NJ-ALG-01"].conflict_flag  # relation not active before 2027-07-01
        after = run(aid, date(2027, 7, 2)).by_rule()
        assert after["NJ-ALG-01"].conflict_flag
        assert after["NJ-ALG-01"].conflicts[0].kind == "possible_preemption"
    assert not any(o.conflict_flag for o in run(nwk, date(2027, 7, 2)).outcomes)


def test_nj_state_rule_status_change_between_dates():
    jc = addresses_where(lambda r: r["city_id"] == synth.JC)[0]
    assert results(jc)["NJ-ALG-01"] == "not_yet_effective"
    assert results(jc, date(2027, 7, 2))["NJ-ALG-01"] == "applies"


# ---- bars and findings ----


def test_state_bar_removes_local_rent_rule_and_emits_a_finding():
    r = run("A0118")  # Boston (mailed as Dorchester)
    assert "BOS-RENT-01" not in {o.rule_id for o in r.outcomes}
    f = [x for x in r.findings if x.reason_code == "barred_by_state"]
    assert (
        len(f) == 1
        and f[0].jurisdiction.id == synth.BOS
        and f[0].category == "rent_increase_limits"
    )
    assert "MA-RENT-01" in {o.rule_id for o in r.outcomes}


def test_ingested_barred_rule_stays_visible_with_a_flag():
    r = run("A0118", ingested=frozenset({"BOS-RENT-01"}))
    o = r.by_rule()["BOS-RENT-01"]
    assert o.conflict_flag and o.conflicts[0].kind == "barred_by_state"
    assert not [x for x in r.findings if x.reason_code == "barred_by_state"]


def test_rules_outside_the_address_stack_are_omitted():
    out = results("A0016")  # SF
    assert not {"JC-ALG-01", "BOS-RENT-01", "LA-RENT-01", "NJ-ALG-01"} & set(out)


def test_unlocatable_address_gets_unknown_local_rules_and_state_rules():
    out = run("A0295").by_rule()  # MA address that could not be geocoded
    assert out["MA-RENT-01"].result == "applies"
    assert out["BOS-JCE-01"].result == "unknown" and out["BOS-JCE-01"].missing_facts == ["location"]


@pytest.mark.parametrize("aid", ["A0001", "A0016", "A0002", "A0118", "A0003"])
def test_engine_is_deterministic(aid):
    a = [(o.rule_id, o.result, o.missing_facts, o.notes) for o in run(aid).outcomes]
    b = [(o.rule_id, o.result, o.missing_facts, o.notes) for o in run(aid).outcomes]
    assert a == b
