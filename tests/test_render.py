"""The renderer's output validates against the API contract and says the right things."""

from datetime import date

import pytest

from engine import config
from engine.ir import KeyValue
from engine.models import LookupResponse
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv
from engine.rules.render import render_lookup
from engine.rules.timeline import build_timeline
from tests import synth

RS = synth.ruleset()
REC = synth.resolved()


def render(aid, d=date(2026, 10, 1), user=None, ruleset=RS):
    rec = REC[aid]
    env = AddressEnv(rec, user)
    res = evaluate_address(ruleset, rec, env, d)
    segs = build_timeline(ruleset, rec, user)
    return render_lookup(ruleset, rec, res, env, segs, facts_source="user" if user else "data")


def block(out, cat):
    return next(b for b in out["categories"] if b["category"] == cat)


@pytest.mark.parametrize("aid", ["A0001", "A0016", "A0002", "A0118", "A0003", "A0295", "A0398"])
@pytest.mark.parametrize("d", [date(2025, 1, 1), date(2026, 10, 1), date(2027, 7, 2)])
def test_every_render_validates_against_the_contract(aid, d):
    out = render(aid, d)
    model = LookupResponse.model_validate(out)
    assert len(model.categories) == 6
    assert model.disclaimer == config.DISCLAIMER
    assert set(model.counts) == {"applies", "unknown", "superseded", "not_yet_effective", "pending"}


def test_sf_lookup_matches_the_demo_story():
    out = render("A0016")
    rent = block(out, "rent_increase_limits")
    assert [r["rule_id"] for r in rent["results"]] == ["SF-RENT-01", "CA-RENT-01"]
    local, state = rent["results"]
    assert local["result"] == "applies" and state["result"] == "superseded"
    assert state["superseded_by"] == "SF-RENT-01" and local["governs_over"] == ["CA-RENT-01"]
    assert "local law takes precedence over state law" in state["reason"]["en"]
    assert "la ley local tiene prioridad" in state["reason"]["es"]
    assert rent["headline"]["en"].startswith("Your rent increases are limited by")
    assert out["jurisdiction"]["city"]["label"] == "San Francisco, CA"
    assert out["jurisdiction"]["mailing_mismatch"] is False
    assert out["facts"]["year_built"]["value"] == 1926 and out["facts"]["units"]["value"] == 21


def test_boston_lookup_has_bar_finding_and_mailing_note():
    out = render("A0118")
    assert out["jurisdiction"]["mailing_mismatch"] is True
    assert out["jurisdiction"]["note"]["en"] == "Mailed as Dorchester. Legally inside Boston."
    rent = block(out, "rent_increase_limits")
    assert [f["reason_code"] for f in rent["findings"]] == ["barred_by_state"]
    assert rent["headline"]["en"] == (
        "No local rent cap here. Massachusetts law bars cities from adopting one."
    ) or rent["headline"]["en"].startswith("Your rent increases")
    assert [p["rule_id"] for p in out["pending"]] == ["MA-ALG-P1", "MA-ALG-P2"]
    assert all(p["result"] == "pending" for p in out["pending"])
    assert out["failed"][0]["rule_id"] == "MA-RENT-P1"
    assert out["failed"][0]["note"]["en"].startswith("Not law:")
    assert out["counts"]["pending"] == 2


def test_unknown_result_names_the_missing_fact_and_asks_the_decisive_question():
    sd = next(a for a, r in REC.items() if r["city_id"] == synth.SD)
    out = render(sd)
    jce = block(out, "just_cause_eviction")["results"][0]
    assert jce["result"] == "unknown" and "co_date" in jce["missing_facts"]
    assert jce["reason"]["en"] == (
        "Unknown: the year the building was built is not in the public record."
    )
    assert jce["reason"]["es"].startswith("Desconocido:")
    assert block(out, "just_cause_eviction")["headline"]["en"].startswith("We can't tell yet.")
    q = out["decisive_question"]
    assert q["fact"] == "year_built" and q["input"] == "year"
    out2 = render(sd, user={"year_built": 1985})
    assert out2["facts_source"] == "user" and out2["decisive_question"] is None
    assert block(out2, "just_cause_eviction")["results"][0]["result"] == "applies"
    assert out2["facts"]["year_built"]["source"] == "user"


def test_not_yet_effective_and_upcoming_changes():
    out = render("A0016", date(2025, 12, 31))
    alg = block(out, "algorithmic_rent_setting")["results"][0]
    assert alg["result"] == "not_yet_effective"
    assert alg["effective_note"]["en"] == "Starts January 1, 2026."
    assert alg["effective_note"]["es"] == "Comienza el 1 de enero de 2026."
    assert alg["reason"]["en"].startswith("Not yet in effect: starts January 1, 2026")
    up = [u for u in out["upcoming"] if u["rule_id"] == "CA-ALG-01"]
    assert up and up[0]["date"] == "2026-01-01" and up[0]["from"] == "not_yet_effective"
    assert up[0]["to"] == "applies"
    assert LookupResponse.model_validate(out).upcoming[0].from_ is not None


def test_projection_flag_follows_the_retrieval_date():
    assert render("A0016", date(2026, 10, 1))["is_projection"] is False
    assert render("A0016", date(2026, 10, 2))["is_projection"] is True


def test_conflict_flag_is_rendered_with_an_explanation():
    jc = next(a for a, r in REC.items() if r["city_id"] == synth.JC)
    out = render(jc, date(2027, 7, 2))
    nj = block(out, "algorithmic_rent_setting")["results"][0]
    flagged = [r for r in block(out, "algorithmic_rent_setting")["results"] if r["conflict_flag"]]
    assert {r["rule_id"] for r in flagged} == {"NJ-ALG-01", "JC-ALG-01"}
    c = next(r for r in flagged if r["rule_id"] == "NJ-ALG-01")["conflicts"][0]
    assert c["kind"] == "possible_preemption" and c["with_rule_id"] == "JC-ALG-01"
    assert "possible preemption" in c["explanation"]["en"] and c["active_from"] == "2027-07-01"
    assert nj  # at least one result in the block


def test_stale_key_value_is_flagged_not_shown_as_current():
    kv = KeyValue(
        name="allowable_increase", text="3%", value=3, unit="percent",
        valid_from=date(2025, 7, 1), valid_to=date(2026, 6, 30),
    )  # fmt: skip
    r = synth.rule("LA-RENT-01", "rent_increase_limits", synth.LA, key_values=[kv])
    rs = RS.model_copy(update={"rules": [r]})
    la = next(
        a
        for a, rec in REC.items()
        if rec["city_id"] == synth.LA and rec["facts"]["year_built"]["lo"] == 1927
    )
    inside = render(la, date(2026, 6, 30), ruleset=rs)
    after = render(la, date(2026, 10, 1), ruleset=rs)
    k_in = block(inside, "rent_increase_limits")["results"][0]["key_values"][0]
    k_out = block(after, "rent_increase_limits")["results"][0]["key_values"][0]
    assert k_in["stale"] is False and k_in["stale_note"] is None
    assert k_out["stale"] is True
    assert "not in our sources" in k_out["stale_note"]["en"] and "3%" in k_out["stale_note"]["en"]


def test_unlocatable_address_explains_why_city_rules_are_unknown():
    out = render("A0295")
    jce = block(out, "just_cause_eviction")["results"][0]
    assert jce["reason"]["en"].startswith("Unknown: this address could not be placed on the map")
    assert out["address"]["lat"] is None
    assert out["jurisdiction"]["resolution"]["method"] == "state_only"
    assert any("could not be placed" in b["en"] for b in out["reasoning_boundary"]["not_checked"])


def test_render_is_deterministic():
    assert render("A0016") == render("A0016")


def test_no_banned_advice_phrases_in_generated_text():
    banned = ("avoid", "get around", "loophole", "workaround", "circumvent", "you should",
              "we recommend", "legal advice")  # fmt: skip
    for aid in ("A0016", "A0118", "A0002", "A0295"):
        for d in (date(2026, 10, 1), date(2027, 7, 2)):
            text = str(render(aid, d)).lower()
            body = text.replace(config.DISCLAIMER.lower(), "")
            for phrase in banned:
                assert phrase not in body, (aid, phrase)
