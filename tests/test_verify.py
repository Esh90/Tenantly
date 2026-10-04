"""Near-miss quotes are rejected; wrapped text is matched and mapped back to raw offsets."""

import pytest

from engine import config
from engine.compile.verify import span_text_is_exact, verify_quote

RAW = (
    "SOURCE: x\n\nSection 1.  A landlord shall not require a deposit\nin excess of one month's "
    "rent.  This applies to all units.\nSection 2. Other text entirely."
)
FULL = [(0, len(RAW))]


def test_exact_quote_is_accepted_with_offsets():
    q = "A landlord shall not require a deposit"
    s = verify_quote(RAW, q, FULL)
    assert s and s.exact and RAW[s.start : s.end] == q and s.text == q


def test_wrapped_and_nbsp_text_matches_and_maps_back_to_raw():
    q = "A landlord shall not require a deposit in excess of one month's rent. This applies"
    s = verify_quote(RAW, q, FULL)
    assert s and not s.exact
    assert s.text == RAW[s.start : s.end]
    assert s.text.startswith("A landlord") and s.text.endswith("This applies")
    assert "\n" in s.text and " " in s.text  # the span is raw corpus text, not the model's


@pytest.mark.parametrize(
    "bad",
    [
        "A landlord shall not require a deposit in excess of one month's rents.",  # typo
        "A landlord must not require a deposit in excess of one month's rent.",  # paraphrase
        "A landlord shall not require a deposit. This applies to all units.",  # joined text
        "a landlord shall not require a deposit in excess",  # case change
        "too short",  # under the 20-character floor
        "",
    ],
)
def test_near_misses_are_rejected(bad):
    assert verify_quote(RAW, bad, FULL) is None


def test_quote_outside_the_in_force_span_is_rejected():
    q = "Other text entirely."
    pos = RAW.find("Section 2")
    assert verify_quote(RAW, q + " " * 0, [(0, pos)]) is None
    assert verify_quote(RAW, "Other text entirely.", [(pos, len(RAW))]) is not None


def test_stored_span_recheck():
    s = verify_quote(RAW, "Other text entirely.", FULL)
    assert span_text_is_exact(RAW, s.start, s.end, s.text)
    assert not span_text_is_exact(RAW, s.start, s.end, s.text + "x")
    assert not span_text_is_exact(RAW, -1, 5, "x")


def test_real_wrapped_sentence_in_the_fair_act():
    raw = (config.TEXT_DIR / "D069.txt").read_text(encoding="utf-8")
    q = (
        "A municipality shall be prohibited from enacting an ordinance "
        "that conflicts with this act."
    )
    s = verify_quote(raw, q, [(0, len(raw))])
    assert s is not None and s.text == raw[s.start : s.end]
    assert verify_quote(raw, q.replace("prohibited", "forbidden"), [(0, len(raw))]) is None


def test_ma_old_version_text_is_rejected_when_only_the_new_version_is_in_force():
    from datetime import date

    from engine.corpus.versions import in_force_spans, segment_versions

    raw = (config.TEXT_DIR / "D052.txt").read_text(encoding="utf-8")
    spans = in_force_spans(raw, segment_versions(raw), date(2026, 10, 1))
    old = "no lessor may require a tenant or prospective tenant to pay any amount in excess"
    new = "no lessor or agent of the lessor may require a tenant or prospective tenant to pay"
    assert verify_quote(raw, old, spans) is None
    assert verify_quote(raw, new, spans) is not None
