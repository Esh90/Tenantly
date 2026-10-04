"""Every example in PLAN.md 11.7, plus the real history notes in the corpus."""

from datetime import date

import pytest

from engine import config
from engine.compile import calendar as cal
from engine.ir import DateValue


@pytest.mark.parametrize(
    ("enacted", "n", "expected"),
    [
        (date(2026, 7, 20), 12, date(2027, 7, 1)),  # NJ FAIR Act
        (date(2026, 1, 20), 4, date(2026, 5, 1)),  # NJ screening-fee cap
        (date(2021, 6, 18), 7, date(2022, 1, 1)),  # NJ Fair Chance in Housing Act
        (date(2026, 12, 31), 1, date(2027, 1, 1)),  # month rollover
        (date(2026, 1, 1), 12, date(2027, 1, 1)),
    ],
)
def test_nth_month_next_following(enacted, n, expected):
    assert cal.nth_month_next_following(enacted, n) == expected


@pytest.mark.parametrize(
    ("expr", "anchor", "expected"),
    [
        (
            "the first day of the twelfth month next following the date of enactment",
            "approved July 20, 2026",
            date(2027, 7, 1),
        ),
        (
            "first day of the fourth month next following the date of enactment",
            "Approved January 20, 2026.",
            date(2026, 5, 1),
        ),
        (
            "first day of the seventh month next following the date of enactment",
            "Approved June 18, 2021.",
            date(2022, 1, 1),
        ),
    ],
)
def test_expression_evaluation(expr, anchor, expected):
    v = cal.evaluate_expression(expr, anchor)
    assert v.lo == v.hi == expected
    assert v.precision == "day" and v.derivation == "nj_nth_month_next_following"
    assert v.output() == expected.isoformat()


def test_missing_anchor_gives_unknown_date():
    v = cal.evaluate_expression(
        "first day of the fourth month next following the date of enactment", None
    )
    assert v.lo is None and v.output() is None


def test_passage_date_unknown_gives_unknown():
    v = cal.evaluate_expression(
        "shall take effect and be in force on the thirtieth day from and after its final passage",
        None,
    )
    assert v.lo is None and v.derivation == "nth_day_after_passage"


def test_nth_day_after_passage_known():
    v = cal.evaluate_expression(
        "on the thirtieth day from and after its final passage", "Passed June 3, 2025"
    )
    assert v.lo == date(2025, 7, 3)
    assert cal.nth_day_after_passage(None, 30) is None


def test_take_effect_immediately():
    v = cal.evaluate_expression("This act shall take effect immediately.", "Approved May 5, 2026")
    assert v.lo == date(2026, 5, 5) and v.derivation == "immediately_on_enactment"


def test_ca_regular_session_default_ab325():
    assert cal.ca_regular_session_default(date(2025, 10, 6)) == date(2026, 1, 1)
    assert cal.parse_date("October 06, 2025.") == date(2025, 10, 6)


def test_went_into_effect():
    v = cal.went_into_effect("Section 37.10C went into effect on October 14, 2024.")
    assert v.lo == date(2024, 10, 14) and v.derivation == "went_into_effect"
    assert cal.went_into_effect("nothing to see").lo is None


def test_history_note_parsing_synthetic():
    text = (
        "(Repealed (in Sec. 3) and added by Stats. 2023, Ch. 290, Sec. 4.   (SB 567)   "
        "Effective January 1, 2024.   Operative April 1, 2024, by its own provisions.   "
        "Repealed as of January 1, 2030, by its own provisions.)"
    )
    (n,) = cal.parse_ca_history_notes(text)
    assert n.effective == date(2024, 1, 1)
    assert n.operative == date(2024, 4, 1)
    assert n.repealed == date(2030, 1, 1)
    assert n.amended_by == "Stats. 2023, Ch. 290"


def _read(doc_id: str) -> str:
    return (config.TEXT_DIR / f"{doc_id}.txt").read_text(encoding="utf-8")


def test_corpus_history_notes_match_expected_dates():
    def effective(doc):
        notes = [n for n in cal.parse_ca_history_notes(_read(doc)) if n.effective]
        return notes[-1]

    n1946 = effective("D023")  # Civ. 1946.2, AB 1529
    assert n1946.effective == date(2026, 1, 1) and n1946.repealed == date(2030, 1, 1)
    n1947 = effective("D024")  # Civ. 1947.12, SB 567
    assert n1947.effective == date(2024, 1, 1) and n1947.repealed == date(2030, 1, 1)
    assert n1947.operative == date(2024, 4, 1)
    assert effective("D025").effective == date(2026, 1, 1)  # AB 414
    assert effective("D026").effective == date(2026, 1, 1)  # AB 1170


def test_ca_default_rule_is_corroborated_by_corpus_history_notes():
    """Stats. 2025 chapters say Effective January 1, 2026; Stats. 2023 say 2024 (the rule)."""
    checked = 0
    for doc in ("D023", "D024", "D025", "D026", "D027"):
        for n in cal.parse_ca_history_notes(_read(doc)):
            if n.effective and n.amended_by and n.effective.month == 1 and n.effective.day == 1:
                year = int(n.amended_by.split()[1].rstrip(","))
                assert n.effective.year == year + 1
                checked += 1
    assert checked >= 4


def test_interval_for_several_published_dates():
    v = cal.interval_from_dates(
        [date(2026, 3, 1), date(2026, 1, 1)], alternatives=(("March 1, 2026", "ordinance"),)
    )
    assert (v.lo, v.hi) == (date(2026, 1, 1), date(2026, 3, 1))
    assert not v.is_exact and v.output() is None


@pytest.mark.parametrize(
    ("lifecycle", "eff_lo", "d", "expected"),
    [
        ("failed", date(2020, 1, 1), date(2026, 10, 1), "failed"),
        ("pending", None, date(2026, 10, 1), "pending"),
        ("enacted", date(2027, 7, 1), date(2026, 10, 1), "not_yet_effective"),
        ("enacted", date(2027, 7, 1), date(2027, 7, 2), "in_force"),
        ("enacted", date(2026, 1, 1), date(2026, 1, 1), "in_force"),
        ("enacted", date(2026, 1, 1), date(2025, 12, 31), "not_yet_effective"),
        ("enacted", None, date(2026, 10, 1), "in_force"),
    ],
)
def test_status_at(lifecycle, eff_lo, d, expected):
    eff = DateValue(lo=eff_lo, hi=eff_lo, precision="day") if eff_lo else DateValue()
    assert cal.status_at(lifecycle, eff, d) == expected


def test_output_precision():
    assert DateValue(lo=date(2025, 1, 1), hi=date(2025, 1, 1), precision="year").output() == "2025"
    assert (
        DateValue(lo=date(2025, 6, 1), hi=date(2025, 6, 1), precision="month").output() == "2025-06"
    )
