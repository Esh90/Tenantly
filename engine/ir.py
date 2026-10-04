"""Internal rule IR (PLAN.md 8.1). Pydantic v2; official enums are used directly.

API response models live in ``engine/models.py``; the IR here is what the compiler produces
and the engine consumes. Only the types needed so far are defined; the rest arrive with the
Law Compiler in Phase 2.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

Precision = Literal["day", "month", "year", "unknown"]
Lifecycle = Literal["enacted", "pending", "failed"]
Derivation = Literal[
    "text_explicit",
    "nj_nth_month_next_following",
    "ca_regular_session_default",
    "ca_history_note",
    "nth_day_after_passage",
    "immediately_on_enactment",
    "went_into_effect",
    "readme_reference",
    "brief_reference",
]


class DateValue(BaseModel):
    """A date that may be an interval: lo == hi when exact, None bounds are unknown."""

    model_config = ConfigDict(frozen=True)

    lo: date | None = None
    hi: date | None = None
    precision: Precision = "unknown"
    derivation: Derivation | None = None
    anchor_quote: str | None = None
    alternatives: tuple[tuple[str, str | None], ...] = ()  # (date text, source) pairs

    @property
    def is_exact(self) -> bool:
        return self.lo is not None and self.lo == self.hi

    @property
    def is_known(self) -> bool:
        return self.lo is not None or self.hi is not None

    def output(self) -> str | None:
        """PartialDate for the submission: a day when exact, else the coarsest correct form."""
        if self.lo is None:
            return None
        if self.is_exact and self.precision == "day":
            return self.lo.isoformat()
        if self.precision == "month":
            return self.lo.strftime("%Y-%m")
        if self.precision == "year":
            return self.lo.strftime("%Y")
        return self.lo.isoformat() if self.is_exact else None
