"""Closed intervals and Kleene three-valued logic (PLAN.md 8.3, 8.4). Pure functions.

An interval ``[lo, hi]`` may have a ``None`` bound meaning unbounded. A fact with no information
is the fully unbounded interval, so every comparison on it is UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Tri(Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    def __invert__(self) -> Tri:
        if self is Tri.TRUE:
            return Tri.FALSE
        if self is Tri.FALSE:
            return Tri.TRUE
        return Tri.UNKNOWN

    @staticmethod
    def of(value: bool) -> Tri:
        return Tri.TRUE if value else Tri.FALSE


def all_(values: list[Tri]) -> Tri:
    """FALSE if any is FALSE; else UNKNOWN if any is UNKNOWN; else TRUE (empty is TRUE)."""
    if any(v is Tri.FALSE for v in values):
        return Tri.FALSE
    if any(v is Tri.UNKNOWN for v in values):
        return Tri.UNKNOWN
    return Tri.TRUE


def any_(values: list[Tri]) -> Tri:
    """TRUE if any is TRUE; else UNKNOWN if any is UNKNOWN; else FALSE (empty is FALSE)."""
    if any(v is Tri.TRUE for v in values):
        return Tri.TRUE
    if any(v is Tri.UNKNOWN for v in values):
        return Tri.UNKNOWN
    return Tri.FALSE


@dataclass(frozen=True)
class Interval:
    lo: Any = None
    hi: Any = None

    @staticmethod
    def exact(x: Any) -> Interval:
        return Interval(x, x)

    @staticmethod
    def unknown() -> Interval:
        return Interval(None, None)

    @property
    def is_exact(self) -> bool:
        return self.lo is not None and self.lo == self.hi

    @property
    def is_unknown(self) -> bool:
        return self.lo is None and self.hi is None

    def is_empty(self) -> bool:
        return self.lo is not None and self.hi is not None and self.lo > self.hi

    def intersect(self, other: Interval) -> Interval:
        """Intersection; the result may be empty (check ``is_empty``)."""
        los = [v for v in (self.lo, other.lo) if v is not None]
        his = [v for v in (self.hi, other.hi) if v is not None]
        return Interval(max(los) if los else None, min(his) if his else None)

    def contains(self, t: Any) -> bool:
        return (self.lo is None or self.lo <= t) and (self.hi is None or t <= self.hi)

    def compare(self, op: str, t: Any) -> Tri:
        """Compare the (uncertain) value against a threshold with Kleene semantics."""
        lo, hi = self.lo, self.hi
        if op == "<":
            if hi is not None and hi < t:
                return Tri.TRUE
            if lo is not None and lo >= t:
                return Tri.FALSE
        elif op == "<=":
            if hi is not None and hi <= t:
                return Tri.TRUE
            if lo is not None and lo > t:
                return Tri.FALSE
        elif op == ">":
            if lo is not None and lo > t:
                return Tri.TRUE
            if hi is not None and hi <= t:
                return Tri.FALSE
        elif op == ">=":
            if lo is not None and lo >= t:
                return Tri.TRUE
            if hi is not None and hi < t:
                return Tri.FALSE
        elif op == "==":
            if lo is not None and lo == hi == t:
                return Tri.TRUE
            if not self.contains(t):
                return Tri.FALSE
        elif op == "!=":
            return ~self.compare("==", t)
        else:
            raise ValueError(f"unknown operator {op!r}")
        return Tri.UNKNOWN


def merge_sources(sources: list[Interval]) -> tuple[Interval, bool]:
    """Intersect all sources. An empty intersection is a record conflict: the fact becomes
    unknown (fully unbounded) and the flag is True."""
    merged = Interval.unknown()
    for s in sources:
        merged = merged.intersect(s)
    if merged.is_empty():
        return Interval.unknown(), True
    return merged, False
