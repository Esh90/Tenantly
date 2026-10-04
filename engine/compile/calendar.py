"""Deterministic legal calendar (PLAN.md 11.7). Pure functions; the model only extracts the
date *expression* and its *anchor*, code computes the date.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from engine.ir import DateValue, Lifecycle

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],  # fmt: skip
        start=1,
    )
}
ORDINALS = {
    w: i
    for i, w in enumerate(
        [
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
            "eleventh",
            "twelfth",
        ],  # fmt: skip
        start=1,
    )
}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90}
_ONES = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7,
    "eighth": 8, "ninth": 9, "tenth": 10, "eleventh": 11, "twelfth": 12,
}  # fmt: skip

DATE_RE = re.compile(r"\b([A-Z][a-z]+)\s+(\d{1,2}),\s+(\d{4})\b")


def parse_date(text: str) -> date | None:
    """Parse the first 'Month d, yyyy' in the text ('October 06, 2025' is fine)."""
    for m in DATE_RE.finditer(text):
        month = MONTHS.get(m.group(1).lower())
        if month:
            try:
                return date(int(m.group(3)), month, int(m.group(2)))
            except ValueError:
                continue
    return None


def parse_all_dates(text: str) -> list[date]:
    out: list[date] = []
    for m in DATE_RE.finditer(text):
        month = MONTHS.get(m.group(1).lower())
        if month:
            try:
                out.append(date(int(m.group(3)), month, int(m.group(2))))
            except ValueError:
                continue
    return out


def add_months_first_day(d: date, n: int) -> date:
    """First day of the month that is n months after d's month."""
    idx = d.year * 12 + (d.month - 1) + n
    return date(idx // 12, idx % 12 + 1, 1)


def nth_month_next_following(enactment: date, n: int) -> date:
    """NJ: 'first day of the Nth month next following the date of enactment'."""
    return add_months_first_day(enactment, n)


def nth_day_after_passage(passage: date | None, n: int) -> date | None:
    """'the Nth day from and after its final passage'. Unknown passage gives an unknown date."""
    if passage is None:
        return None
    return date.fromordinal(passage.toordinal() + n)


def ca_regular_session_default(approved: date) -> date:
    """A chaptered CA regular-session bill without urgency clause or explicit date takes effect
    on January 1 of the year after approval."""
    return date(approved.year + 1, 1, 1)


def _ordinal_number(word: str) -> int | None:
    word = word.lower().replace("-", " ").strip()
    if word in _ONES:
        return _ONES[word]
    parts = word.split()
    if len(parts) == 2 and parts[0] in _TENS and parts[1] in _ONES:
        return _TENS[parts[0]] + _ONES[parts[1]]
    # "thirtieth", "twentieth", ...
    tens_ord = {"twentieth": 20, "thirtieth": 30, "fortieth": 40, "fiftieth": 50, "sixtieth": 60}
    return tens_ord.get(word)


_NTH_MONTH_RE = re.compile(
    r"first\s+day\s+of\s+the\s+([a-z\- ]+?)\s+month\s+next\s+following"
    r"\s+the\s+date\s+of\s+enactment",
    re.I,
)
_NTH_DAY_RE = re.compile(r"([a-z\- ]+?)\s+day\s+from\s+and\s+after\s+its\s+final\s+passage", re.I)
_IMMEDIATE_RE = re.compile(r"take\s+effect\s+immediately", re.I)


def evaluate_expression(expression: str, anchor_quote: str | None) -> DateValue:
    """Compute an effective date from a relative expression plus the quoted anchor."""
    anchor = parse_date(anchor_quote) if anchor_quote else None

    m = _NTH_MONTH_RE.search(expression)
    if m:
        n = _ordinal_number(m.group(1))
        if n is not None and anchor is not None:
            d = nth_month_next_following(anchor, n)
            return DateValue(
                lo=d, hi=d, precision="day", derivation="nj_nth_month_next_following",
                anchor_quote=anchor_quote,
            )  # fmt: skip
        return DateValue(derivation="nj_nth_month_next_following", anchor_quote=anchor_quote)

    m = _NTH_DAY_RE.search(expression)
    if m:
        n = _ordinal_number(m.group(1).split()[-1])
        d = nth_day_after_passage(anchor, n) if n is not None else None
        if d is None:
            return DateValue(derivation="nth_day_after_passage", anchor_quote=anchor_quote)
        return DateValue(
            lo=d, hi=d, precision="day", derivation="nth_day_after_passage",
            anchor_quote=anchor_quote,
        )  # fmt: skip

    if _IMMEDIATE_RE.search(expression) and anchor is not None:
        return DateValue(
            lo=anchor, hi=anchor, precision="day", derivation="immediately_on_enactment",
            anchor_quote=anchor_quote,
        )  # fmt: skip
    return DateValue()


@dataclass(frozen=True)
class CaHistoryNote:
    effective: date | None
    operative: date | None
    repealed: date | None
    amended_by: str | None  # e.g. "Stats. 2025, Ch. 340"


_NOTE_RE = re.compile(r"^\(.*?Stats\.\s*(\d{4}),\s*Ch\.\s*(\d+).*\)\s*$", re.M)
_EFFECTIVE_RE = re.compile(r"\bEffective\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")
_OPERATIVE_RE = re.compile(r"\bOperative\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")
_REPEALED_RE = re.compile(r"\bRepealed\s+as\s+of\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})")


def parse_ca_history_notes(text: str) -> list[CaHistoryNote]:
    """Parse CA code-page history notes such as
    '(Amended by Stats. 2025, Ch. 203, Sec. 1. (AB 1529) Effective January 1, 2026. Repealed as
    of January 1, 2030, by its own provisions.)'"""
    notes: list[CaHistoryNote] = []
    for m in _NOTE_RE.finditer(text):
        body = m.group(0)
        eff = _EFFECTIVE_RE.search(body)
        op = _OPERATIVE_RE.search(body)
        rep = _REPEALED_RE.search(body)
        notes.append(
            CaHistoryNote(
                effective=parse_date(eff.group(1)) if eff else None,
                operative=parse_date(op.group(1)) if op else None,
                repealed=parse_date(rep.group(1)) if rep else None,
                amended_by=f"Stats. {m.group(1)}, Ch. {m.group(2)}",
            )
        )
    return notes


_WENT_RE = re.compile(r"went\s+into\s+effect\s+on\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", re.I)


def went_into_effect(text: str) -> DateValue:
    m = _WENT_RE.search(text)
    d = parse_date(m.group(1)) if m else None
    if d is None:
        return DateValue()
    return DateValue(
        lo=d, hi=d, precision="day", derivation="went_into_effect", anchor_quote=m.group(0)
    )


def interval_from_dates(dates: list[date], alternatives: tuple = ()) -> DateValue:
    """Several published dates become an interval [min, max] with the alternatives kept."""
    if not dates:
        return DateValue()
    lo, hi = min(dates), max(dates)
    return DateValue(lo=lo, hi=hi, precision="day", alternatives=alternatives)


def status_at(lifecycle: Lifecycle, effective: DateValue, d: date) -> str:
    """Rule status at date d: in_force | not_yet_effective | pending | failed."""
    if lifecycle == "failed":
        return "failed"
    if lifecycle == "pending":
        return "pending"
    if effective.lo is not None and effective.lo > d:
        return "not_yet_effective"
    return "in_force"
