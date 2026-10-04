"""Loader, boilerplate mask, signal score, doc-type classifier and sectionizer (Phase 1)."""

import hashlib

import pytest

from engine.corpus import boilerplate, doctype, sectionizer, signal, versions
from engine.corpus.build import build
from engine.corpus.loader import load_corpus


@pytest.fixture(scope="module")
def corpus():
    docs, links = load_corpus()
    return {d.doc_id: d for d in docs}, links


@pytest.fixture(scope="module")
def masks(corpus):
    return boilerplate.mask_corpus(list(corpus[0].values()))


def test_loader_counts(corpus):
    docs, links = corpus
    assert len(docs) == 54 and len(links) == 33
    assert {link.doc_id for link in links if link.status != "link-only"} == {"D056"}
    assert all(not d.header_mismatch for d in docs.values())
    assert docs["D001"].url.startswith("https://berkeleyca.gov/")


def test_manifest_hash_mismatch_is_recorded_not_fatal(corpus):
    docs, _ = corpus
    assert not any(d.sha_ok for d in docs.values())  # see DATASET_NOTES.md
    d = docs["D048"]
    assert d.sha256 == hashlib.sha256(d.text.encode("utf-8")).hexdigest()  # we hash what we read


def test_link_only_slug_tokens(corpus):
    _, links = corpus
    d035 = next(link for link in links if link.doc_id == "D035")
    assert "realpage" in d035.slug_tokens and "jersey" in d035.slug_tokens


def test_offsets_are_raw_file_offsets(corpus):
    d = corpus[0]["D048"]
    assert d.text.startswith("SOURCE: ")
    assert d.text[d.body_start :].startswith("General Law")


@pytest.mark.parametrize(
    ("doc_id", "phrase"),
    [
        ("D048", "No city or town may enact, maintain or enforce rent control"),
        ("D052", "(iv) the purchase and installation cost for a key and lock."),
        ("D069", "A municipality shall be prohibited from enacting"),
    ],
)
def test_mask_never_hides_operative_text(corpus, masks, doc_id, phrase):
    doc = corpus[0][doc_id]
    pos = doc.text.find(phrase)
    assert pos >= 0
    assert not masks[doc_id].is_masked(pos)


def test_mask_hides_sign_in_modal_and_skip_lines(corpus, masks):
    d, m = corpus[0]["D057"], masks["D057"]
    assert m.is_masked(d.text.find("Register for MyLegislature"))
    assert m.is_masked(d.text.find("Skip to Content"))


def test_mask_preserves_offsets(corpus, masks):
    d, m = corpus[0]["D036"], masks["D036"]
    text, anchors = m.model_view()
    assert len(text) < len(d.text) and anchors
    for model_pos, raw_pos in anchors[:25]:
        assert text[model_pos : model_pos + 12] == d.text[raw_pos : raw_pos + 12]


def test_signal_flags_the_atlas_low_signal_captures(masks):
    low = {i for i, m in masks.items() if signal.is_low_signal(signal.signal_score(m))}
    assert {"D036", "D078"} <= low  # CORPUS_ATLAS 3.3
    for statute in ("D023", "D024", "D025", "D048", "D065", "D069", "D073"):
        assert statute not in low


def test_doc_types(corpus):
    docs = corpus[0]
    got = {i: doctype.classify(d).doc_type for i, d in docs.items()}
    assert got["D039"] == "motion"  # LA motion 24-1031 is not law
    assert {got[i] for i in ("D011", "D045", "D046", "D047")} == {"bill_status"}
    assert got["D076"] == "draft_materials"  # blank adoption number
    assert got["D001"] == "ordinance" and got["D073"] == "ordinance"
    assert {got[i] for i in ("D022", "D023", "D048", "D052", "D065", "D069")} == {"statute"}
    assert got["D010"] == "policy"
    assert got["D041"] == "guidance" and got["D067"] == "guidance"
    assert set(got.values()) <= set(doctype.DOC_TYPES)


def test_sections_have_valid_offsets_and_hashes(corpus, masks):
    for doc_id, doc in corpus[0].items():
        segs = versions.segment_versions(doc.text)
        secs = sectionizer.sectionize(doc, masks[doc_id], segs)
        assert secs, doc_id
        prev_end = doc.body_start
        for s in secs:
            assert doc.body_start <= s.char_start < s.char_end <= len(doc.text)
            assert hashlib.sha256(s.text(doc).encode("utf-8")).hexdigest() == s.sha256
            assert s.char_start >= prev_end - sectionizer.OVERLAP
            prev_end = s.char_end


def test_sections_never_straddle_versions(corpus, masks):
    doc = corpus[0]["D052"]
    segs = versions.segment_versions(doc.text)
    secs = sectionizer.sectionize(doc, masks["D052"], segs)
    for s in secs:
        for seg in segs:
            assert not (s.char_start < seg.marker_start < s.char_end)
    labels = {s.version_label for s in secs}
    assert None in labels and any(lbl and "effective 2025-08-01" in lbl for lbl in labels)


def test_long_sections_are_split(corpus, masks):
    for doc_id, doc in corpus[0].items():
        for s in sectionizer.sectionize(doc, masks[doc_id], versions.segment_versions(doc.text)):
            assert s.char_end - s.char_start <= sectionizer.LONG_SECTION * 2, (doc_id, s.section_id)


def test_corpus_build_is_deterministic():
    a, b = build(), build()
    assert a == b
    row = next(r for r in a[0] if r["doc_id"] == "D039")
    assert row["doc_type"] == "motion"
    assert len(a[0]) == 54 and len(a[1]) > 54
