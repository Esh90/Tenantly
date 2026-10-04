"""MA version segments (D052 c.186 s.15B, D057 c.112 s.87DDD1/2): quote the version in force."""

from datetime import date

import pytest

from engine import config
from engine.corpus.versions import in_force_label, in_force_spans, segment_versions

DEFAULT = date(2026, 10, 1)


def _text(doc: str) -> str:
    return (config.TEXT_DIR / f"{doc}.txt").read_text(encoding="utf-8")


def _in_force_text(doc: str, on: date) -> str:
    t = _text(doc)
    return "".join(t[a:b] for a, b in in_force_spans(t, segment_versions(t), on))


@pytest.mark.parametrize("doc", ["D052", "D057"])
def test_two_segments_with_aug_2025_boundary(doc):
    segs = segment_versions(_text(doc))
    assert len(segs) == 2
    old, new = segs
    assert old.valid_from is None and old.valid_to == date(2025, 8, 1)
    assert new.valid_from == date(2025, 8, 1) and new.valid_to is None
    assert old.end == new.marker_start  # contiguous, no overlap
    assert not old.valid_on(date(2025, 8, 1)) and new.valid_on(date(2025, 8, 1))
    assert old.valid_on(date(2025, 7, 31)) and not new.valid_on(date(2025, 7, 31))


def test_d052_default_date_quotes_only_the_new_intro():
    on = _in_force_text("D052", DEFAULT)
    assert "no lessor or agent of the lessor may require" in on
    assert "no lessor may require a tenant or prospective tenant" not in on
    assert "(iv) the purchase and installation cost for a key and lock." in on
    assert "effective until August 1, 2025" not in on  # marker brackets are excluded


def test_d052_before_boundary_quotes_the_old_intro():
    before = _in_force_text("D052", date(2025, 7, 31))
    assert "no lessor may require a tenant or prospective tenant" in before
    assert "no lessor or agent of the lessor may require" not in before


def test_d057_default_date_is_the_amended_text():
    segs = segment_versions(_text("D057"))
    assert in_force_label(segs, DEFAULT).startswith(
        "Text of section as amended by 2025, 9, Sec. 43"
    )
    assert in_force_label(segs, date(2025, 1, 1)) == "Text of section, effective until 2025-08-01"


def test_documents_without_markers_are_entirely_in_force():
    t = _text("D048")
    segs = segment_versions(t)
    assert segs == []
    assert in_force_spans(t, segs, DEFAULT) == [(0, len(t))]
    assert in_force_label(segs, DEFAULT) is None


def test_only_ma_statute_pages_have_markers():
    with_markers = {
        p.stem for p in config.TEXT_DIR.glob("D*.txt") if segment_versions(p.read_text("utf-8"))
    }
    assert with_markers == {"D052", "D057"}
