"""Facts deriver (PLAN.md 8.2, 9.4): intervals with provenance from assessor use codes.

Pure functions. Every fact records the sources it came from; sources are intersected, and an
empty intersection becomes a record conflict (the fact is then unknown).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field

from engine import config
from engine.facts.intervals import Interval, merge_sources
from engine.geo.zipsanity import zip_is_suspect

PROPERTY_TYPES = (
    "multifamily_2_4",
    "multifamily_5plus",
    "condo",
    "tic",
    "cooperative",
    "elderly_home",
    "mixed_use",
    "single_family",
    "other",
)

_UNITS_TOKEN = re.compile(r"(\d+)\s*U")


@dataclass(frozen=True)
class FactSource:
    """One piece of evidence for a numeric fact."""

    kind: str  # "assessor" (exact value in the data) | "assessor_derived" (use code / description)
    lo: int | None
    hi: int | None
    basis: str
    confidence: float = 1.0


@dataclass
class IntervalFact:
    interval: Interval = field(default_factory=Interval.unknown)
    sources: list[FactSource] = field(default_factory=list)
    record_conflict: bool = False

    @property
    def derived(self) -> bool:
        return bool(self.sources) and all(s.kind == "assessor_derived" for s in self.sources)

    @property
    def basis(self) -> str | None:
        return "; ".join(s.basis for s in self.sources) or None


@dataclass
class AddressFacts:
    address_id: str
    state: str
    postal_city: str
    zip: str
    zip_suspect: bool
    use_code: str
    use_description: str
    source_dataset: str
    units: IntervalFact
    year_built: IntervalFact
    property_type: str | None = None
    property_type_basis: str | None = None
    subsidized: bool | None = None
    subsidized_basis: str | None = None
    review_flags: list[str] = field(default_factory=list)


def nj_units_from_description(desc: str) -> int | None:
    """Sum the ``(\\d+)U`` token over every '/' part of a MOD-IV building description."""
    total, found = 0, False
    for part in desc.split("/"):
        m = _UNITS_TOKEN.search(part)
        if m:
            total += int(m.group(1))
            found = True
    return total if found else None


def _src(kind: str, lo, hi, basis: str, conf: float = 1.0) -> FactSource:
    return FactSource(kind, lo, hi, basis, conf)


def _derive_from_code(
    row: dict,
) -> tuple[list[FactSource], str | None, str | None, bool | None, list[str]]:
    """Returns (unit sources, property_type, basis, subsidized, review_flags) from the use code."""
    ds, code, desc = row["source_dataset"], row["use_code"].strip(), row["use_description"].strip()
    flags: list[str] = []
    sources: list[FactSource] = []
    ptype: str | None = None
    subsidized: bool | None = None
    basis = f"{code} ({desc})"

    if ds.startswith("LA County"):
        if code in {"0500", "0501", "050V", "050C", "0551"}:
            sources.append(_src("assessor_derived", 5, None, f"LA use code {code}: 5+ apartments"))
            ptype = "multifamily_5plus"
    elif ds.startswith("DataSF"):
        if code in {"A5", "F5"}:
            sources.append(_src("assessor_derived", 5, 14, f"SF use code {code}: 5 to 14 units"))
            ptype = "multifamily_5plus"
        elif code == "FS5":
            sources.append(
                _src("assessor_derived", 5, 14, "SF use code FS5: flats and store, 5 to 14")
            )
            ptype = "mixed_use"
        elif code == "A15":
            sources.append(_src("assessor_derived", 15, None, "SF use code A15: 15 units or more"))
            ptype = "multifamily_5plus"
        elif code == "TIC":
            sources.append(_src("assessor_derived", 1, 4, "SF use code TIC: 4 units or less"))
            ptype = "tic"
    elif ds.startswith("SANDAG"):
        if code in {"14", "15", "16"}:
            sources.append(_src("assessor_derived", 5, None, f"SANDAG land use {code}: 5+ units"))
            ptype = "multifamily_5plus"
    elif ds.startswith("Alameda"):
        if code in {"7200", "7700", "7800"}:
            sources.append(_src("assessor_derived", 5, None, f"Alameda use code {code}: 5+ units"))
            ptype = "multifamily_5plus"
    elif ds.startswith("Boston"):
        if code == "A/112":
            sources.append(
                _src("assessor_derived", 7, 30, "Boston A/112: apartments, 7 to 30 units")
            )
            ptype = "multifamily_5plus"
        elif code == "A/118":
            sources.append(_src("assessor_derived", 7, None, "Boston A/118: elderly home", 0.8))
            ptype = "elderly_home"
            flags.append("review_elderly_home")
        elif code.startswith("A/"):
            sources.append(
                _src("assessor_derived", 7, None, f"Boston {code}: class A is 7+ units", 0.8)
            )
            ptype = "multifamily_5plus"
            if code == "A/125":
                subsidized = True
    elif ds.startswith("Cambridge"):
        if code == "111":
            sources.append(_src("assessor_derived", 4, 8, "Cambridge 111: 4 to 8 unit apartments"))
        elif code == "112":
            sources.append(_src("assessor_derived", 9, None, "Cambridge 112: more than 8 units"))
            if "MXD" in desc.upper():
                ptype = "mixed_use"
    elif ds.startswith("NJOGIS"):
        if code == "4C":
            sources.append(
                _src("assessor_derived", 5, None, "MOD-IV class 4C: apartments, 5+ units")
            )
            ptype = "multifamily_5plus"
        n = nj_units_from_description(desc)
        if n is not None:
            sources.append(
                _src("assessor_derived", n, n, f"MOD-IV building description '{desc}': {n} units")
            )
        up = desc.upper()
        if "AFFORDABL" in up:
            subsidized = True
        if "CO-OP" in up or "CO OP" in up:
            ptype = "cooperative"
    return sources, ptype, basis, subsidized, flags


def _int_or_none(s: str) -> int | None:
    s = (s or "").strip()
    return int(s) if s else None


def derive_row(row: dict) -> AddressFacts:
    units_sources: list[FactSource] = []
    exact_units = _int_or_none(row["units"])
    if exact_units is not None:
        units_sources.append(_src("assessor", exact_units, exact_units, "assessor record"))
    code_sources, ptype, ptype_basis, subsidized, flags = _derive_from_code(row)
    units_sources.extend(code_sources)

    merged, conflict = merge_sources([Interval(s.lo, s.hi) for s in units_sources])
    units = IntervalFact(merged, units_sources, conflict)
    if conflict:
        flags.append("record_conflict_units")

    yb = _int_or_none(row["year_built"])
    year = IntervalFact(
        Interval.exact(yb) if yb is not None else Interval.unknown(),
        [_src("assessor", yb, yb, "assessor record")] if yb is not None else [],
    )

    if ptype is None and merged.lo is not None and merged.hi is not None and not conflict:
        if merged.hi <= 4:
            ptype, ptype_basis = "multifamily_2_4", f"derived from units {merged.lo}-{merged.hi}"
        elif merged.lo >= 5:
            ptype, ptype_basis = "multifamily_5plus", f"derived from units {merged.lo}-{merged.hi}"

    zip_code = row["zip"].strip()
    return AddressFacts(
        address_id=row["address_id"],
        state=row["state"],
        postal_city=row["postal_city"],
        zip=zip_code,
        zip_suspect=zip_is_suspect(row["state"], row["postal_city"], zip_code),
        use_code=row["use_code"],
        use_description=row["use_description"],
        source_dataset=row["source_dataset"],
        units=units,
        year_built=year,
        property_type=ptype,
        property_type_basis=ptype_basis,
        subsidized=subsidized,
        subsidized_basis=(
            "use code / description flags subsidized or affordable" if subsidized else None
        ),  # fmt: skip
        review_flags=flags,
    )


def load_rows() -> list[dict]:
    with open(config.ADDRESSES_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def derive_all() -> list[AddressFacts]:
    return [derive_row(r) for r in load_rows()]


def facts_report(facts: list[AddressFacts]) -> dict:
    """Counts for artifacts/eval/facts_report.json (measured, never estimated)."""
    conflicts = [f for f in facts if f.units.record_conflict]
    return {
        "addresses": len(facts),
        "derived_units": sum(1 for f in facts if f.units.derived and f.units.interval.is_exact),
        "units_with_interval_only": sum(
            1 for f in facts if f.units.derived and not f.units.interval.is_exact
        ),
        "units_exact_from_data": sum(
            1 for f in facts if any(s.kind == "assessor" for s in f.units.sources)
        ),
        "units_unknown": sum(1 for f in facts if f.units.interval.is_unknown),
        "record_conflicts": len(conflicts),
        "record_conflict_ids": sorted(f.address_id for f in conflicts),
        "zip_suspect": sum(1 for f in facts if f.zip_suspect),
        "missing_year_built": sum(1 for f in facts if f.year_built.interval.is_unknown),
        "subsidized_true": sum(1 for f in facts if f.subsidized),
        "property_types": _count(f.property_type for f in facts),
        "review_flags": _count(flag for f in facts for flag in f.review_flags),
    }


def _count(items) -> dict:
    out: dict = {}
    for i in items:
        key = str(i)
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))
