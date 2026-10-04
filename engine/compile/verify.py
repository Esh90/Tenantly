"""Quote verifier (PLAN.md 11.6). Deterministic; never accepts a fuzzy match.

A quote is accepted only if it is an exact substring of the raw file inside the in-force version
span, or matches after collapsing whitespace (hard-wrapped lines, non-breaking spaces) and maps
back to raw offsets. The stored span is always the raw text at those offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_QUOTE = 20
_WS = re.compile(r"\s+")


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    text: str  # raw text at [start, end)
    exact: bool  # True if the model's quote was already byte-identical


def _normalize(text: str, lo: int, hi: int) -> tuple[str, list[int]]:
    """Collapse whitespace runs (incl. NBSP) to one space; return text and raw index per char."""
    out: list[str] = []
    idx: list[int] = []
    i = lo
    while i < hi:
        ch = text[i]
        if ch.isspace():
            j = i
            while j < hi and text[j].isspace():
                j += 1
            if out:
                out.append(" ")
                idx.append(i)
            i = j
        else:
            out.append(ch)
            idx.append(i)
            i += 1
    return "".join(out), idx


def verify_quote(raw: str, quote: str, spans: list[tuple[int, int]]) -> Span | None:
    """Locate ``quote`` in ``raw`` within the in-force ``spans``. None means QUOTE_NOT_FOUND."""
    if len(quote.strip()) < MIN_QUOTE:
        return None
    for lo, hi in spans:
        pos = raw.find(quote, lo, hi)
        if pos >= 0:
            return Span(pos, pos + len(quote), raw[pos : pos + len(quote)], True)
    want = _WS.sub(" ", quote.strip())
    if len(want) < MIN_QUOTE:
        return None
    for lo, hi in spans:
        norm, idx = _normalize(raw, lo, hi)
        pos = norm.find(want)
        if pos >= 0:
            start = idx[pos]
            end = idx[pos + len(want) - 1] + 1
            return Span(start, end, raw[start:end], False)
    return None


def span_text_is_exact(raw: str, start: int, end: int, text: str) -> bool:
    """Recheck a stored citation: the raw file at the offsets must equal the stored span."""
    return 0 <= start < end <= len(raw) and raw[start:end] == text
