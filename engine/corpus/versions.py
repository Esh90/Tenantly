"""Version segmenter (PLAN.md 9.3) for statute pages that carry several versions of a clause,
such as Massachusetts General Laws ("effective until August 1, 2025 ... effective August 1, 2025").

Pure functions over the raw text. Offsets are raw-file offsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from engine.compile.calendar import parse_date

MARKER_RE = re.compile(
    r"\[\s*(?P<what>[^\]]*?)\beffective\s+(?P<until>until\s+)?"
    r"(?P<date>[A-Z][a-z]+\s+\d{1,2},\s+\d{4})[^\]]*\]"
)


@dataclass(frozen=True)
class VersionSegment:
    label: str
    valid_from: date | None  # inclusive
    valid_to: date | None  # exclusive
    start: int  # first character after the marker
    end: int  # next marker, or the end of the text
    marker_start: int
    marker_end: int

    def valid_on(self, d: date) -> bool:
        return (self.valid_from is None or self.valid_from <= d) and (
            self.valid_to is None or d < self.valid_to
        )


def segment_versions(text: str) -> list[VersionSegment]:
    """Split a document at its version markers. Text before the first marker is common to all
    versions; text after the last marker belongs to the last version."""
    markers = list(MARKER_RE.finditer(text))
    segments: list[VersionSegment] = []
    for i, m in enumerate(markers):
        when = parse_date(m.group("date"))
        until = bool(m.group("until"))
        what = re.sub(r"\s+", " ", m.group("what")).strip(" ,.")
        end = markers[i + 1].start() if i + 1 < len(markers) else len(text)
        iso = when.isoformat() if when else "unknown date"
        label = f"{what}, effective until {iso}" if until else f"{what}, effective {iso}"
        segments.append(
            VersionSegment(
                label=label,
                valid_from=None if until else when,
                valid_to=when if until else None,
                start=m.end(),
                end=end,
                marker_start=m.start(),
                marker_end=m.end(),
            )
        )
    return segments


def in_force_spans(text: str, segments: list[VersionSegment], on: date) -> list[tuple[int, int]]:
    """Raw-offset spans that are in force on a date: the common text before the first marker
    plus every segment valid on that date. Marker brackets themselves are excluded."""
    if not segments:
        return [(0, len(text))]
    spans = [(0, segments[0].marker_start)]
    spans.extend((s.start, s.end) for s in segments if s.valid_on(on))
    return [(a, b) for a, b in spans if b > a]


def in_force_label(segments: list[VersionSegment], on: date) -> str | None:
    for s in segments:
        if s.valid_on(on):
            return s.label
    return None
