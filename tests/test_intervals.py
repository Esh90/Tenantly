"""Interval comparisons, merging and conflicts (PLAN.md 8.3)."""

from datetime import date

import pytest

from engine.facts.intervals import Interval, Tri, merge_sources

T, F, U = Tri.TRUE, Tri.FALSE, Tri.UNKNOWN


@pytest.mark.parametrize(
    ("iv", "op", "t", "expected"),
    [
        # exact values behave like plain comparisons
        (Interval.exact(5), "<", 5, F),
        (Interval.exact(4), "<", 5, T),
        (Interval.exact(5), "<=", 5, T),
        (Interval.exact(5), ">", 4, T),
        (Interval.exact(5), ">=", 6, F),
        (Interval.exact(5), "==", 5, T),
        (Interval.exact(5), "==", 6, F),
        # NJ class 4C: units in [5, inf)
        (Interval(5, None), ">=", 5, T),
        (Interval(5, None), "<", 5, F),
        (Interval(5, None), "<=", 4, F),
        (Interval(5, None), ">", 4, T),
        (Interval(5, None), "<=", 5, U),
        (Interval(5, None), "<", 100, U),
        # DataSF A5: units in [5, 14]
        (Interval(5, 14), "<", 15, T),
        (Interval(5, 14), ">=", 15, F),
        (Interval(5, 14), ">", 10, U),
        (Interval(5, 14), "==", 20, F),
        (Interval(5, 14), "==", 10, U),
        # TIC: units in [1, 4]
        (Interval(1, 4), "<=", 4, T),
        (Interval(1, 4), ">=", 5, F),
        # nothing known
        (Interval.unknown(), "<", 5, U),
        (Interval.unknown(), "==", 5, U),
        (Interval.unknown(), ">=", 0, U),
    ],
)
def test_compare(iv, op, t, expected):
    assert iv.compare(op, t) is expected


def test_not_equal_is_negated_equality():
    assert Interval.exact(5).compare("!=", 6) is T
    assert Interval(5, 14).compare("!=", 20) is T
    assert Interval(5, 14).compare("!=", 10) is U


def test_year_built_1978_is_the_whole_calendar_year():
    """LA RSO cutoff 1978-10-01 vs a building built in 1978 (certificate-of-occupancy proxy)."""
    co = Interval(date(1978, 1, 1), date(1978, 12, 31))
    cutoff = date(1978, 10, 1)
    assert co.compare("<=", cutoff) is U
    assert Interval(date(1927, 1, 1), date(1927, 12, 31)).compare("<=", cutoff) is T
    assert Interval(date(1980, 1, 1), date(1980, 12, 31)).compare("<=", cutoff) is F


def test_unknown_kleene_with_cutoff_year_edges():
    assert Interval(date(1978, 1, 1), date(1978, 12, 31)).compare(">", date(1978, 10, 1)) is U


def test_merge_intersects():
    merged, conflict = merge_sources([Interval(5, None), Interval(5, 14)])
    assert (merged.lo, merged.hi, conflict) == (5, 14, False)
    merged, conflict = merge_sources([Interval.exact(20), Interval(5, None)])
    assert merged.is_exact and merged.lo == 20 and not conflict


def test_merge_empty_intersection_is_record_conflict():
    merged, conflict = merge_sources([Interval.exact(5), Interval(1, 4)])  # A0398
    assert conflict and merged.is_unknown
    merged, conflict = merge_sources([Interval.exact(3), Interval(5, None)])  # A0028
    assert conflict and merged.is_unknown


def test_merge_no_sources_is_unknown_not_conflict():
    merged, conflict = merge_sources([])
    assert merged.is_unknown and not conflict


def test_bad_operator_rejected():
    with pytest.raises(ValueError):
        Interval.exact(1).compare("~", 1)
