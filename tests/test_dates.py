"""Deterministic dates from the real documents: code computes, the model never does."""

from datetime import date

import pytest

from engine.compile import dates
from engine.compile.context import cite_key, jurisdiction_for, load_views

VIEWS, LINKS = load_views()


def eff(doc_id, **record):
    e, s = dates.resolve_dates(VIEWS[doc_id], record)
    return e, s


@pytest.mark.parametrize(
    ("doc", "expected", "derivation"),
    [
        ("D069", date(2027, 7, 1), "nj_nth_month_next_following"),  # FAIR Act
        ("D066", date(2026, 5, 1), "nj_nth_month_next_following"),  # NJ screening-fee cap
        ("D065", date(2022, 1, 1), "nj_nth_month_next_following"),  # NJ Fair Chance in Housing
        ("D022", date(2026, 1, 1), "ca_regular_session_default"),  # AB 325
        ("D025", date(2026, 1, 1), "ca_history_note"),  # Civ. 1950.5, AB 414
        ("D026", date(2026, 1, 1), "ca_history_note"),
        ("D057", date(2025, 8, 1), "text_explicit"),  # MA version segment
    ],
)
def test_effective_dates_computed_from_the_text(doc, expected, derivation):
    e, _ = eff(doc)
    assert e.lo == e.hi == expected and e.derivation == derivation and e.precision == "day"


def test_civ_1947_12_operative_date_and_repeal():
    e, s = eff("D024")
    assert e.lo == date(2024, 4, 1)  # operative April 1, 2024 is later than effective 2024-01-01
    assert s.lo == date(2030, 1, 1)


def test_civ_1946_2_repeal_date():
    e, s = eff("D023")
    assert e.lo == date(2026, 1, 1) and s.lo == date(2030, 1, 1)


def test_bill_pages_have_no_effective_date_and_are_never_enacted():
    for d in ("D011", "D045", "D046", "D047"):
        assert eff(d)[0].lo is None
    assert dates.lifecycle_for(VIEWS["D045"], "enacted") == "pending"  # model cannot override
    assert dates.lifecycle_for(VIEWS["D046"], "enacted") == "pending"
    assert dates.lifecycle_for(VIEWS["D011"], "enacted") == "failed"  # study order, no law


def test_enacted_documents_follow_the_model_lifecycle():
    assert dates.lifecycle_for(VIEWS["D023"], "enacted") == "enacted"
    assert dates.lifecycle_for(VIEWS["D023"], None) == "enacted"


def test_model_date_is_accepted_only_if_the_source_shows_it():
    ok, _ = eff("D041", effective_date="2026-02-02")  # "Effective February 2, 2026" is in D041
    assert ok.lo == date(2026, 2, 2) and ok.derivation == "text_explicit"
    bad, _ = eff("D041", effective_date="2031-03-04")
    assert bad.lo is None  # not in the text: unknown, never guessed


def test_san_diego_algorithmic_draft_has_no_computed_date():
    e, _ = eff("D076")  # "30th day from final passage" with the passage date blank
    assert e.lo is None


def test_date_text_probe():
    assert dates.date_text_in_doc(date(2026, 2, 2), "Effective February 2, 2026.")
    assert not dates.date_text_in_doc(date(2026, 2, 3), "Effective February 2, 2026.")


def test_partial_dates():
    assert dates.parse_partial("2026-03") == (date(2026, 3, 1), date(2026, 3, 31), "month")
    assert dates.parse_partial("2025") == (date(2025, 1, 1), date(2025, 12, 31), "year")
    assert dates.parse_partial("soon") is None


def test_cite_keys_ignore_formatting_but_not_sections():
    assert cite_key("Cal. Civ. Code § 1947.12") == cite_key(
        "California Civil Code, section 1947.12"
    )
    assert cite_key("Cal. Civ. Code § 1947.12") != cite_key("Cal. Civ. Code § 1946.2")
    assert cite_key("M.G.L. c. 186, § 15B") == cite_key("MGL ch. 186 s. 15B")
    assert cite_key("N.J.S.A. 46:8-21.2") == "46:8-21.2"


def test_jurisdiction_mapping():
    assert jurisdiction_for("CA").level == "state"
    j = jurisdiction_for("Berkeley, CA")
    assert j.id == "CA-0606000" and j.level == "city" and j.state == "CA"


def test_views_cover_the_corpus_and_choose_the_in_force_text():
    assert len(VIEWS) == 54 and len(LINKS) == 33
    assert "effective until" not in VIEWS["D052"].model_text()
    assert "no lessor or agent of the lessor" in VIEWS["D052"].model_text()
    assert "Register for MyLegislature" not in VIEWS["D057"].model_text()
