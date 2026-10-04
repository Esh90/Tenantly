"""Kleene truth tables, DSL parsing and validation, evaluation with traces."""

import itertools
import json
from datetime import date

import pytest

from engine import config
from engine.facts.intervals import Interval, Tri, all_, any_
from engine.rules import dsl
from engine.rules.facts_env import AddressEnv, InvalidFacts, validate_user_facts

T, F, U = Tri.TRUE, Tri.FALSE, Tri.UNKNOWN
AS_OF = date(2026, 10, 1)


class DictEnv(dsl.FactEnv):
    def __init__(self, **values):
        self.values = values

    def get(self, fact, as_of):
        v = self.values.get(fact)
        if v is None:
            return dsl.FactVal()
        if isinstance(v, Interval):
            return dsl.FactVal(interval=v, source="assessor", basis="test")
        return dsl.FactVal(scalar=v, source="assessor", basis="test")


# ---- Kleene truth tables ----


def test_not_table():
    assert (~T, ~F, ~U) == (F, T, U)


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (T, T, T), (T, F, F), (T, U, U),
        (F, T, F), (F, F, F), (F, U, F),
        (U, T, U), (U, F, F), (U, U, U),
    ],
)  # fmt: skip
def test_and_table(a, b, expected):
    assert all_([a, b]) is expected


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        (T, T, T), (T, F, T), (T, U, T),
        (F, T, T), (F, F, F), (F, U, U),
        (U, T, T), (U, F, U), (U, U, U),
    ],
)  # fmt: skip
def test_or_table(a, b, expected):
    assert any_([a, b]) is expected


def test_de_morgan_holds_for_all_three_valued_inputs():
    for a, b in itertools.product([T, F, U], repeat=2):
        assert ~all_([a, b]) is any_([~a, ~b])
        assert ~any_([a, b]) is all_([~a, ~b])


def test_empty_all_and_any():
    assert all_([]) is T and any_([]) is F


# ---- parsing ----


def test_roundtrip():
    d = {
        "all": [
            {"fact": "units", "op": ">=", "value": 5},
            {"any": [
                {"fact": "co_date", "op": "<=", "value": "1978-10-01"},
                {"not": {"fact": "property_type", "op": "in", "value": ["condo", "tic"]}},
            ]},
            {"exists": "year_built"},
            {"fact": "co_date", "op": ">", "value": {"as_of_minus_years": 15}},
        ]
    }  # fmt: skip
    assert dsl.to_dict(dsl.parse(d)) == d


@pytest.mark.parametrize(
    "bad",
    [
        {"fact": "favorite_color", "op": "==", "value": 1},  # unknown fact
        {"fact": "units", "op": "in", "value": [1, 2]},  # operator not allowed for numbers
        {"fact": "units", "op": ">=", "value": "five"},  # wrong type
        {"fact": "units", "op": ">=", "value": True},  # bool is not a number
        {"fact": "property_type", "op": "==", "value": "castle"},  # not in the enum
        {"fact": "owner_occupied", "op": "<", "value": True},  # operator not allowed for bool
        {"fact": "owner_occupied", "op": "==", "value": "yes"},
        {"fact": "co_date", "op": "<=", "value": "not-a-date"},
        {"all": []},
        {"const": "yes"},
        {"nonsense": 1},
        {"fact": "units", "op": ">="},  # missing value
        [],
    ],
)
def test_invalid_predicates_are_rejected(bad):
    assert dsl.validate(bad) != []


def test_registry_matches_the_plan():
    assert set(dsl.FACTS) == {
        "units", "year_built", "co_date", "building_age_years", "property_type",
        "subsidized_or_affordable", "owner_is_natural_person", "owner_occupied",
        "landlord_property_count", "landlord_unit_count", "unit_separately_alienable",
        "shares_kitchen_bath_with_owner",
    }  # fmt: skip


def test_facts_used():
    p = dsl.parse({"all": [{"fact": "units", "op": ">=", "value": 5}, {"exists": "year_built"}]})
    assert dsl.facts_used(p) == {"units", "year_built"}


# ---- evaluation ----


def ev(pred, **facts):
    return dsl.evaluate(dsl.parse(pred), DictEnv(**facts), AS_OF)


def test_small_landlord_exception_is_false_at_5_plus_units():
    """FALSE AND UNKNOWN = FALSE: units >= 5 rules the exception out even without owner facts."""
    pred = {"all": [
        {"fact": "landlord_unit_count", "op": "<=", "value": 4},
        {"fact": "owner_is_natural_person", "op": "==", "value": True},
    ]}  # fmt: skip
    r = ev(pred, landlord_unit_count=Interval(5, None))
    assert r.value is F and r.unknown_facts == set()


def test_unknown_when_nothing_is_known():
    pred = {"fact": "year_built", "op": "<", "value": 1980}
    r = ev(pred)
    assert r.value is U and r.unknown_facts == {"year_built"}
    assert r.trace[0].actual is None and r.trace[0].result is U


def test_cutoff_year_is_unknown():
    pred = {"fact": "co_date", "op": "<=", "value": "1978-10-01"}
    cy = Interval(date(1978, 1, 1), date(1978, 12, 31))
    assert ev(pred, co_date=cy).value is U
    assert ev(pred, co_date=Interval(date(1927, 1, 1), date(1927, 12, 31))).value is T
    assert ev(pred, co_date=Interval(date(1980, 1, 1), date(1980, 12, 31))).value is F


def test_fifteen_year_exemption_uses_the_query_date():
    pred = {"fact": "co_date", "op": ">", "value": {"as_of_minus_years": 15}}
    co = Interval(date(2012, 1, 1), date(2012, 12, 31))
    assert dsl.evaluate(dsl.parse(pred), DictEnv(co_date=co), date(2026, 10, 1)).value is T
    assert dsl.evaluate(dsl.parse(pred), DictEnv(co_date=co), date(2027, 6, 1)).value is U
    assert dsl.evaluate(dsl.parse(pred), DictEnv(co_date=co), date(2027, 1, 1)).value is U
    assert dsl.evaluate(dsl.parse(pred), DictEnv(co_date=co), date(2028, 1, 1)).value is F


def test_unknown_facts_report_only_what_kept_the_result_open():
    pred = {"any": [
        {"fact": "units", "op": ">=", "value": 5},
        {"fact": "owner_occupied", "op": "==", "value": True},
    ]}  # fmt: skip
    assert ev(pred, units=Interval(6, None)).unknown_facts == set()  # decided TRUE
    both = ev(pred)
    assert both.value is U and both.unknown_facts == {"units", "owner_occupied"}


def test_enum_and_bool_facts():
    assert (
        ev(
            {"fact": "property_type", "op": "in", "value": ["condo", "tic"]}, property_type="tic"
        ).value
        is T
    )
    assert (
        ev({"fact": "property_type", "op": "not_in", "value": ["condo"]}, property_type="tic").value
        is T
    )
    assert (
        ev({"fact": "property_type", "op": "==", "value": "condo"}, property_type="tic").value is F
    )
    assert ev({"fact": "property_type", "op": "==", "value": "condo"}).value is U
    assert (
        ev({"fact": "owner_occupied", "op": "==", "value": True}, owner_occupied=False).value is F
    )


def test_exists_is_never_unknown():
    assert ev({"exists": "year_built"}).value is F
    assert ev({"exists": "year_built"}, year_built=Interval.exact(1990)).value is T
    assert ev({"not": {"exists": "year_built"}}).value is T


def test_trace_labels_are_bilingual_and_name_values():
    r = ev({"fact": "units", "op": ">=", "value": 5}, units=Interval.exact(21))
    t = r.trace[0].as_dict()
    assert t["label_en"] == "Number of units is at least 5"
    assert t["label_es"] == "Número de unidades es al menos 5"
    assert t["actual"] == "21" and t["expected"] == "5" and t["result"] == "true"
    d = ev({"fact": "co_date", "op": "<=", "value": "1979-06-13"}).trace[0]
    assert d.label_en == "Certificate of occupancy date is on or before 1979-06-13"


def test_interval_actual_text():
    assert dsl.describe_interval(Interval(5, None), "int") == "5 or more"
    assert dsl.describe_interval(Interval(5, 14), "int") == "between 5 and 14"
    assert dsl.describe_interval(Interval.unknown(), "int") is None


def test_change_dates_for_relative_exemption():
    co = Interval(date(2012, 1, 1), date(2012, 12, 31))
    pred = dsl.parse({"fact": "co_date", "op": ">", "value": {"as_of_minus_years": 15}})
    ds = dsl.change_dates(pred, DictEnv(co_date=co), date(2025, 1, 1), date(2028, 12, 31))
    assert date(2027, 1, 1) in ds and date(2027, 12, 31) in ds


# ---- the environment built from real resolved addresses ----


@pytest.fixture(scope="module")
def resolved():
    return json.loads((config.ARTIFACTS / "addresses.resolved.json").read_text(encoding="utf-8"))


def test_env_for_la_1927_building(resolved):
    env = AddressEnv(resolved["A0001"])
    assert env.get("units", AS_OF).interval == Interval.exact(32)
    co = env.get("co_date", AS_OF).interval
    assert (co.lo, co.hi) == (date(1927, 1, 1), date(1927, 12, 31))
    age = env.get("building_age_years", AS_OF).interval
    assert age.lo == age.hi == 99
    assert env.get("owner_occupied", AS_OF).unknown  # renter-known, never in the data


def test_env_for_hoboken_units_from_description(resolved):
    env = AddressEnv(resolved["A0002"])
    v = env.get("units", AS_OF)
    assert v.interval == Interval.exact(20) and v.source == "assessor_derived"
    assert "6B-20U-G" in v.basis


def test_env_marks_record_conflicts_as_unknown(resolved):
    v = AddressEnv(resolved["A0398"]).get("units", AS_OF)
    assert v.record_conflict and v.interval.is_unknown


def test_env_missing_year_built_makes_co_date_unknown(resolved):
    env = AddressEnv(resolved["A0003"])
    assert env.get("year_built", AS_OF).unknown and env.get("co_date", AS_OF).unknown


def test_user_facts_override_and_validate(resolved):
    env = AddressEnv(resolved["A0003"], {"year_built": 1985, "owner_occupied": False})
    assert env.get("year_built", AS_OF).interval == Interval.exact(1985)
    assert env.get("year_built", AS_OF).source == "user"
    assert env.get("co_date", AS_OF).interval.lo == date(1985, 1, 1)
    assert env.get("owner_occupied", AS_OF).scalar is False
    with pytest.raises(InvalidFacts):
        validate_user_facts({"co_date": "1985-01-01"})  # derived facts are not accepted
    with pytest.raises(InvalidFacts):
        validate_user_facts({"units": "many"})
    with pytest.raises(InvalidFacts):
        validate_user_facts({"owner_occupied": "yes"})


def test_boston_subsidized_flag_flows_through(resolved):
    subsidized = [r for r in resolved.values() if r["facts"]["subsidized"]]
    assert len(subsidized) == 27
    env = AddressEnv(subsidized[0])
    assert env.get("subsidized_or_affordable", AS_OF).scalar is True
