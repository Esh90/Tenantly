"""Build artifacts/corpus/docs.jsonl and sections.jsonl (PLAN.md 8.8). Deterministic."""

from __future__ import annotations

from datetime import date

from engine import config
from engine.corpus import boilerplate, doctype, sectionizer, signal, versions
from engine.corpus.loader import load_corpus
from engine.io import atomic_write_jsonl

DEFAULT_DATE = date.fromisoformat(config.DEFAULT_AS_OF)


def build() -> tuple[list[dict], list[dict]]:
    docs, _links = load_corpus()
    masked = boilerplate.mask_corpus(docs)
    doc_rows: list[dict] = []
    section_rows: list[dict] = []
    for d in docs:
        m = masked[d.doc_id]
        segs = versions.segment_versions(d.text)
        score = signal.signal_score(m)
        cls = doctype.classify(d)
        doc_rows.append(
            {
                "doc_id": d.doc_id,
                "url": d.url,
                "retrieved_at": d.retrieved_at,
                "manifest_sha256": d.manifest_sha256,
                "sha256": d.sha256,
                "sha_ok": d.sha_ok,
                "header_mismatch": d.header_mismatch,
                "doc_type": cls.doc_type,
                "doc_type_reason": cls.reason,
                "jurisdiction_label": d.jurisdictions,
                "chars": d.chars,
                "masked_lines": len(m.masked),
                "signal_score": round(score, 4),
                "low_signal": signal.is_low_signal(score),
                "versions": [
                    {
                        "label": s.label,
                        "valid_from": s.valid_from.isoformat() if s.valid_from else None,
                        "valid_to": s.valid_to.isoformat() if s.valid_to else None,
                        "in_force_on_default": s.valid_on(DEFAULT_DATE),
                    }
                    for s in segs
                ],
            }
        )
        for sec in sectionizer.sectionize(d, m, segs):
            section_rows.append(
                {
                    "section_id": sec.section_id,
                    "doc_id": sec.doc_id,
                    "version_label": sec.version_label,
                    "heading": sec.heading,
                    "char_start": sec.char_start,
                    "char_end": sec.char_end,
                    "sha256": sec.sha256,
                }
            )
    return doc_rows, section_rows


def write() -> tuple[int, int]:
    doc_rows, section_rows = build()
    atomic_write_jsonl(config.ARTIFACTS / "corpus" / "docs.jsonl", doc_rows)
    atomic_write_jsonl(config.ARTIFACTS / "corpus" / "sections.jsonl", section_rows)
    return len(doc_rows), len(section_rows)
