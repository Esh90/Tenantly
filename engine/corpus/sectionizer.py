"""Sectionizer (PLAN.md 11.3). Splits a document into sections with raw-file offsets.

Split points are heading-like lines (never inside masked boilerplate) plus version-marker
boundaries, so a section never straddles two versions of the law.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from engine.corpus.boilerplate import MaskedDoc
from engine.corpus.loader import Doc
from engine.corpus.versions import VersionSegment

LONG_SECTION = 12_000
WINDOW = 8_000
OVERLAP = 800

_HEADING = re.compile(
    r"^\s*(§|Sec\.|Section\b|SECTION\b|Article\b|ARTICLE\b|Chapter\b|CHAPTER\b"
    r"|\d+\.\d+(\.\d+)?\b"  # 37.9  1947.12  98.0704  13.63.030
    r"|\d+[A-Z]?:\d+[A-Z]?-\d+(\.\d+)?"  # 2A:18-61.1  46:8-21.2
    r"|40P\b"
    r"|\d+\.\s{2,}\S)"  # NJ act sections: "1.  Short title"
)
_SUBCLAUSE = re.compile(r"^\s*\((?:[a-z]|\d{1,2})\)\s")


@dataclass(frozen=True)
class Section:
    section_id: str
    doc_id: str
    version_label: str | None
    heading: str
    char_start: int
    char_end: int
    sha256: str

    def text(self, doc: Doc) -> str:
        return doc.text[self.char_start : self.char_end]


def _version_label(pos: int, segments: list[VersionSegment]) -> str | None:
    for s in segments:
        if s.marker_start <= pos < s.end:
            return s.label
    return None


def _split_long(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Split an over-long span on (a) / (1) sub-clause markers, falling back to windows."""
    if end - start <= LONG_SECTION:
        return [(start, end)]
    cuts = [start]
    pos = start
    for line in text[start:end].split("\n"):
        if pos > cuts[-1] and _SUBCLAUSE.match(line) and pos - cuts[-1] >= LONG_SECTION // 2:
            cuts.append(pos)
        pos += len(line) + 1
    cuts.append(end)
    spans: list[tuple[int, int]] = []
    for a, b in zip(cuts, cuts[1:], strict=False):
        spans.extend(_windows(a, b) if b - a > LONG_SECTION else [(a, b)])
    return spans


def _windows(start: int, end: int) -> list[tuple[int, int]]:
    spans, pos = [], start
    while pos < end:
        spans.append((pos, min(pos + WINDOW, end)))
        if pos + WINDOW >= end:
            break
        pos += WINDOW - OVERLAP
    return spans


def sectionize(
    doc: Doc, masked: MaskedDoc, segments: list[VersionSegment] | None = None
) -> list[Section]:
    segments = segments or []
    text = doc.text
    points: set[int] = set()
    for i, ln in enumerate(masked.lines):
        if i not in masked.masked and ln.text.strip() and _HEADING.match(ln.text):
            points.add(ln.start)
    points.update(s.marker_start for s in segments)
    ordered = sorted(p for p in points if doc.body_start <= p < len(text))

    if not ordered:
        spans = _windows(doc.body_start, len(text))
    else:
        bounds = [doc.body_start] + [p for p in ordered if p > doc.body_start] + [len(text)]
        spans = []
        for a, b in zip(bounds, bounds[1:], strict=False):
            spans.extend(_split_long(text, a, b))

    sections: list[Section] = []
    for n, (a, b) in enumerate(spans, start=1):
        chunk = text[a:b]
        if not chunk.strip():
            continue
        heading = next((ln.strip() for ln in chunk.split("\n") if ln.strip()), "")[:120]
        sections.append(
            Section(
                section_id=f"{doc.doc_id}-S{n:03d}",
                doc_id=doc.doc_id,
                version_label=_version_label(a, segments),
                heading=heading,
                char_start=a,
                char_end=b,
                sha256=hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
            )
        )
    return sections
