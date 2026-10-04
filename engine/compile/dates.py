"""Deterministic effective dates, sunsets and lifecycle (PLAN.md D4, 11.7).

Code computes every date. A model-reported date is accepted only if the date text appears in the
source document, and a relative expression is evaluated by the legal calendar.
"""

from __future__ import annotations

import re
from datetime import date

from engine import config
from engine.compile import calendar as cal
from engine.compile.context import DocView
from engine.ir import DateValue

_APPROVED = re.compile(r"[Aa]pproved\s+(?:by\s+Governor\s+)?([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")
_NJ_EFFECT = re.compile(
    r"take\s+effect\s+on\s+the\s+(first\s+day\s+of\s+the\s+[a-z\- ]+?\s+month\s+next\s+following"
    r"\s+the\s+date\s+of\s+enactment)",
    re.I,
)
_URGENCY = re.compile(r"urgency\s+statute|take\s+effect\s+immediately", re.I)
_TERMINAL = re.compile(
    r"study\s+order|accompanied\s+a\s+study|no\s+further\s+action|rejected|vetoed|withdrawn|"
    r"discharged\s+to\s+the\s+committee\s+on\s+rules",
    re.I,
)


def _day(d: date, derivation: str, anchor: str | None = None) -> DateValue:
    return DateValue(lo=d, hi=d, precision="day", derivation=derivation, anchor_quote=anchor)  # type: ignore[arg-type]


def date_text_in_doc(d: date, text: str) -> bool:
    """A model-reported date counts only if the source shows it (month name or ISO form)."""
    month = d.strftime("%B")
    return bool(
        re.search(rf"{month}\s+0?{d.day},\s+{d.year}", text)
        or d.isoformat() in text
        or re.search(rf"{d.month}/{d.day}/{d.year}", text)
        or re.search(rf"{d.month:02d}/{d.day:02d}/{d.year}", text)
    )


def parse_partial(s: str | None) -> tuple[date, date, str] | None:
    """YYYY | YYYY-MM | YYYY-MM-DD to (lo, hi, precision)."""
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", s.strip())
    if not m:
        return None
    y, mo, d = int(m.group(1)), m.group(2), m.group(3)
    try:
        if d:
            x = date(y, int(mo), int(d))
            return x, x, "day"
        if mo:
            lo = date(y, int(mo), 1)
            hi = date(y + (int(mo) == 12), int(mo) % 12 + 1, 1)
            return lo, date.fromordinal(hi.toordinal() - 1), "month"
        return date(y, 1, 1), date(y, 12, 31), "year"
    except ValueError:
        return None


def lifecycle_for(view: DocView, model_value: str | None) -> str:
    """Bill pages are locked to pending (failed on a terminal action); the rest follow the text."""
    if view.doc_type == "bill_status":
        return "failed" if _TERMINAL.search(view.doc.text[view.doc.body_start :]) else "pending"
    if view.doc_type == "motion":
        return "pending"
    return model_value if model_value in ("enacted", "pending", "failed") else "enacted"


def resolve_dates(view: DocView, record: dict) -> tuple[DateValue, DateValue | None]:
    """Return (effective, sunset) for a rule record from this document."""
    text = view.doc.text
    body = text[view.doc.body_start :]
    sunset: DateValue | None = None
    effective = DateValue()

    notes = [n for n in cal.parse_ca_history_notes(body) if n.effective or n.repealed]
    repeals = [n.repealed for n in notes if n.repealed]
    if repeals:
        r = max(repeals)
        sunset = DateValue(lo=r, hi=r, precision="day", derivation="ca_history_note")

    if view.doc_type == "bill_status":
        return DateValue(), None

    # 1. California history notes (operative date wins when later)
    eff_notes = [n for n in notes if n.effective]
    if eff_notes and "leginfo" in view.doc.url and "codes_displaySection" in view.doc.url:
        last = eff_notes[-1]
        d = max(x for x in (last.effective, last.operative) if x)
        return _day(d, "ca_history_note", last.amended_by), sunset

    # 2. a relative clause in the text (NJ style), computed by the calendar
    m = _NJ_EFFECT.search(body)
    approved = _APPROVED.search(body)
    if m and approved:
        v = cal.evaluate_expression(m.group(1), approved.group(0))
        if v.lo:
            return v, sunset

    # 3. a chaptered California bill with no explicit date and no urgency clause
    if "billNavClient" in view.doc.url and approved and not _URGENCY.search(body):
        d = cal.parse_date(approved.group(1))
        if d:
            return (
                DateValue(lo=cal.ca_regular_session_default(d), hi=cal.ca_regular_session_default(d),
                          precision="day", derivation="ca_regular_session_default",
                          anchor_quote=approved.group(0)),
                sunset,
            )  # fmt: skip

    # 4. Massachusetts versions: the in-force segment's start
    for seg in view.segments:
        if seg.valid_from and seg.valid_on(date.fromisoformat(config.DEFAULT_AS_OF)):
            return _day(seg.valid_from, "text_explicit"), sunset

    # 5. "went into effect on ..." in guidance pages
    went = cal.went_into_effect(body)
    if went.lo:
        return went, sunset

    # 6. a date the model reported, only if the source text shows it
    parsed = parse_partial(record.get("effective_date"))
    if parsed:
        lo, hi, prec = parsed
        probe = lo if prec == "day" else None
        if prec != "day" or (probe and date_text_in_doc(probe, body)):
            if prec == "day" or str(lo.year) in body:
                return DateValue(lo=lo, hi=hi, precision=prec, derivation="text_explicit"), sunset  # type: ignore[arg-type]
    return effective, sunset
