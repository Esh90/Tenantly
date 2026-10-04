"""Phase 0 slice: ZIP sanity. Use-code derivation and record conflicts arrive in Phase 1."""

import csv

from engine import config
from engine.geo.zipsanity import zip_is_suspect


def _rows():
    with open(config.ADDRESSES_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_83_suspect_zips_all_nj():
    suspect = [r for r in _rows() if zip_is_suspect(r["state"], r["postal_city"], r["zip"])]
    assert len(suspect) == 83
    assert {r["state"] for r in suspect} == {"NJ"}


def test_empty_zip_is_not_suspect():
    assert not zip_is_suspect("CA", "San Francisco", "")
    assert not zip_is_suspect("MA", "Cambridge", None)


def test_known_bad_zip_examples():
    assert zip_is_suspect("NJ", "Newark", "11219")  # A0003: Brooklyn ZIP
    assert not zip_is_suspect("NJ", "Hoboken", "07030")
    assert not zip_is_suspect("NJ", "Jersey City", "07304")


# ---- use-code derivations and record conflicts (Phase 1) ----
import pytest  # noqa: E402

from engine.facts.derive import derive_all, facts_report, nj_units_from_description  # noqa: E402


@pytest.fixture(scope="module")
def facts():
    return {f.address_id: f for f in derive_all()}


@pytest.mark.parametrize(
    ("desc", "units"),
    [
        ("6B-20U-G", 20),
        ("3B-7U/4B-24U-G", 31),  # sum across '/' parts
        ("2F-4U/2F-2U", 6),
        ("3SF3UG", 3),
        ("13B-93U-2C-G", 93),
        ("4SB", None),
        ("Apartments (class 4C)", None),
        ("5B-1OU", None),  # letter O, not a digit: never guess
    ],
)
def test_nj_description_units(desc, units):
    assert nj_units_from_description(desc) == units


def test_hoboken_a0002_has_20_units_from_description(facts):
    f = facts["A0002"]
    assert (f.units.interval.lo, f.units.interval.hi) == (20, 20)
    assert f.units.derived and "6B-20U-G" in f.units.basis
    assert f.year_built.interval.lo == 2001


def test_la_use_codes_are_5plus(facts):
    f = facts["A0001"]  # 0500, 32 units in the data
    assert f.units.interval.lo == f.units.interval.hi == 32
    assert f.property_type == "multifamily_5plus"


def test_boston_classes(facts):
    boston = [f for f in facts.values() if f.source_dataset.startswith("Boston")]
    assert len(boston) == 60 and all(f.units.interval.lo >= 7 for f in boston)
    assert sum(1 for f in boston if f.subsidized) == 26  # A/125 rows
    elderly = [f for f in boston if f.property_type == "elderly_home"]
    assert len(elderly) == 1 and "review_elderly_home" in elderly[0].review_flags


def test_nj_flags(facts):
    assert facts["A0049"].subsidized is True  # "3S-6U-AFFORDABL"
    assert facts["A0125"].property_type == "cooperative"  # "5B-5U-H-(CO-OP)"
    assert facts["A0136"].property_type == "cooperative"  # "5B-26U-H-CO-OP"


def test_year_built_missing_is_unknown_not_zero(facts):
    missing = [f for f in facts.values() if f.year_built.interval.is_unknown]
    assert len(missing) == 212
    assert facts["A0003"].year_built.interval.is_unknown


@pytest.mark.parametrize("aid", ["A0398", "A0028", "A0076"])
def test_record_conflicts_named_in_the_atlas(facts, aid):
    f = facts[aid]
    assert f.units.record_conflict and f.units.interval.is_unknown
    assert "record_conflict_units" in f.review_flags


def test_a0398_sf_tic_conflict_sources(facts):
    spans = sorted((s.lo, s.hi) for s in facts["A0398"].units.sources)
    assert spans == [(1, 4), (5, 5)]  # data says 5 units, TIC code says 4 or less
    assert facts["A0398"].property_type == "tic"


def test_facts_report_counts(facts):
    r = facts_report(list(facts.values()))
    assert r["addresses"] == 500
    assert r["zip_suspect"] == 83
    assert r["missing_year_built"] == 212
    assert r["record_conflicts"] >= 3
    assert {"A0398", "A0028", "A0076"} <= set(r["record_conflict_ids"])
