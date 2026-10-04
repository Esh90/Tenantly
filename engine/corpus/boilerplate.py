"""Boilerplate mask (PLAN.md 9.2). Marks spans; never deletes, so offsets stay raw-file offsets."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass

from engine.corpus.loader import Doc

SHORT_LINE = 25
SHORT_RUN = 8
REPEAT_DOCS = 3
_SKIP = re.compile(r"^\s*skip to\b", re.I)


@dataclass(frozen=True)
class Line:
    start: int  # raw offsets, end exclusive and excluding the newline
    end: int
    text: str


def split_lines(doc: Doc) -> list[Line]:
    """Lines of the body (after the SOURCE/RETRIEVED header) with raw offsets."""
    lines: list[Line] = []
    pos = doc.body_start
    for raw in doc.text[doc.body_start :].split("\n"):
        lines.append(Line(pos, pos + len(raw), raw))
        pos += len(raw) + 1
    return lines


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def repeated_lines(docs: list[Doc]) -> dict[str, set[str]]:
    """domain -> normalized lines seen in at least REPEAT_DOCS documents from that domain."""
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    for d in docs:
        for ln in split_lines(d):
            n = _norm(ln.text)
            if len(n) >= 3:
                seen[(d.domain, n)].add(d.doc_id)
    out: dict[str, set[str]] = defaultdict(set)
    for (domain, n), ids in seen.items():
        if len(ids) >= REPEAT_DOCS:
            out[domain].add(n)
    return out


def masked_line_indexes(doc: Doc, repeated: dict[str, set[str]]) -> set[int]:
    lines = split_lines(doc)
    masked: set[int] = set()

    # sign-in / registration modals on malegislature.gov begin at a lone multiplication sign
    if doc.domain.endswith("malegislature.gov"):
        for i, ln in enumerate(lines):
            if ln.text.strip() == "\u00d7":
                masked.update(range(i, len(lines)))
                break

    run: list[int] = []
    for i, ln in enumerate(lines):
        t = ln.text.strip()
        if _SKIP.match(t):
            masked.add(i)
        if t and len(t) < SHORT_LINE:
            run.append(i)
            continue
        if t == "":
            continue  # blank lines do not break a run of short lines
        if len(run) >= SHORT_RUN:
            masked.update(run)
        run = []
    if len(run) >= SHORT_RUN:
        masked.update(run)

    rep = repeated.get(doc.domain, set())
    for i, ln in enumerate(lines):
        if _norm(ln.text) in rep and len(_norm(ln.text)) >= 3:
            masked.add(i)
    return masked


@dataclass(frozen=True)
class MaskedDoc:
    doc_id: str
    lines: tuple[Line, ...]
    masked: frozenset[int]

    def kept_lines(self) -> list[Line]:
        return [ln for i, ln in enumerate(self.lines) if i not in self.masked and ln.text.strip()]

    def is_masked(self, offset: int) -> bool:
        """True if the raw offset falls inside a masked line."""
        for i in self.masked:
            ln = self.lines[i]
            if ln.start <= offset < ln.end:
                return True
        return False

    def model_view(self) -> tuple[str, list[tuple[int, int]]]:
        """Text for the model with masked lines removed, plus (model_pos, raw_pos) anchors so any
        model-text offset can be mapped back to a raw-file offset."""
        parts: list[str] = []
        anchors: list[tuple[int, int]] = []
        pos = 0
        for ln in self.kept_lines():
            anchors.append((pos, ln.start))
            parts.append(ln.text)
            pos += len(ln.text) + 1
        return "\n".join(parts), anchors


def mask_corpus(docs: list[Doc]) -> dict[str, MaskedDoc]:
    rep = repeated_lines(docs)
    out: dict[str, MaskedDoc] = {}
    for d in docs:
        out[d.doc_id] = MaskedDoc(
            d.doc_id, tuple(split_lines(d)), frozenset(masked_line_indexes(d, rep))
        )
    return out
