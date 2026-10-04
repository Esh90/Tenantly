"""Address resolution (PLAN.md 10.3 and 9.5): facts + geocode + point-in-polygon.

Writes ``artifacts/addresses.resolved.json`` and ``artifacts/eval/geo_report.json``.
Point-in-polygon is authoritative for the legal city; the Census FIPS codes only cross-check it.
"""

from __future__ import annotations

import logging
from collections import Counter

from engine import config
from engine.facts.derive import AddressFacts, IntervalFact, derive_row, load_rows
from engine.geo import geocode
from engine.geo.jurisdictions import CITIES
from engine.geo.pip import Locator, default_locator
from engine.io import atomic_write_json
from engine.rules.templates import mailing_mismatch

log = logging.getLogger("tenantly.resolve")

CITY_BY_ID = {c.id: c for c in CITIES}


def _interval_json(f: IntervalFact) -> dict:
    return {
        "lo": f.interval.lo,
        "hi": f.interval.hi,
        "record_conflict": f.record_conflict,
        "basis": f.basis,
        "sources": [
            {"kind": s.kind, "lo": s.lo, "hi": s.hi, "basis": s.basis, "confidence": s.confidence}
            for s in f.sources
        ],
    }


def facts_json(f: AddressFacts) -> dict:
    return {
        "units": _interval_json(f.units),
        "year_built": _interval_json(f.year_built),
        "property_type": f.property_type,
        "property_type_basis": f.property_type_basis,
        "subsidized": f.subsidized,
        "subsidized_basis": f.subsidized_basis,
        "review_flags": f.review_flags,
        "use_code": f.use_code,
        "use_description": f.use_description,
        "source_dataset": f.source_dataset,
    }


def _norm_name(s: str) -> str:
    return " ".join(s.lower().split())


def _census_agrees(hit: geocode.GeoHit | None, city_id: str | None, county: str | None):
    """Cross-check the point-in-polygon result against the Census FIPS codes, when present."""
    if hit is None:
        return None
    checks: list[bool] = []
    if hit.county_fips and county:
        checks.append(county.split("-", 1)[1] == hit.county_fips)
    if city_id and (hit.place_geoid or hit.cousub_geoid):
        c = CITY_BY_ID[city_id]
        want = c.place_geoid
        if c.layer == "PLACE":
            got = hit.place_geoid or ""
        else:  # a county subdivision GEOID is state(2) + county(3) + subdivision(5)
            cs = hit.cousub_geoid or ""
            got = cs[:2] + cs[5:] if len(cs) == 10 else ""
        if got:
            checks.append(got == want)
    return all(checks) if checks else None


def resolve_all(locator: Locator | None = None, use_network: bool = True) -> tuple[dict, dict]:
    locator = locator or default_locator()
    rows = load_rows()
    facts = {r["address_id"]: derive_row(r) for r in rows}

    batch_in = []
    for r in rows:
        f = facts[r["address_id"]]
        zip_used = "" if f.zip_suspect else r["zip"].strip()
        batch_in.append(
            (
                r["address_id"],
                geocode.normalize_street(r["street_address"]),
                r["postal_city"],
                r["state"],
                zip_used,
            )  # fmt: skip
        )
    batch = geocode.census_batch(batch_in) if use_network else {}

    records: dict[str, dict] = {}
    for r in rows:
        aid = r["address_id"]
        f = facts[aid]
        zip_used = None if f.zip_suspect else (r["zip"].strip() or None)
        hit = batch.get(aid)
        if hit is None and use_network:
            hit = geocode.cascade(r["street_address"], r["postal_city"], r["state"], zip_used)
        located = locator.locate(hit.lat, hit.lon) if hit else None
        city_id = located.city_id if located else None
        county = located.county_id if located else None
        legal_city = CITY_BY_ID[city_id].name if city_id else None
        # a point in a city of another state would be a geocoding error
        if city_id and not city_id.startswith(r["state"] + "-"):
            city_id, legal_city = None, None
        mismatch = bool(legal_city and _norm_name(legal_city) != _norm_name(r["postal_city"]))
        agrees = _census_agrees(hit, city_id, county)
        records[aid] = {
            "address_id": aid,
            "state": r["state"],
            "street": r["street_address"],
            "postal_city": r["postal_city"],
            "zip": r["zip"].strip() or None,
            "zip_used": zip_used,
            "zip_suspect": f.zip_suspect,
            "lat": hit.lat if hit else None,
            "lon": hit.lon if hit else None,
            "geocoder": hit.tier if hit else "none",
            "geocode_variant": hit.variant if hit else None,
            "matched_address": hit.matched_address if hit else None,
            "city_id": city_id,
            "county_id": county,
            "legal_city": legal_city,
            "mailing_mismatch": mismatch,
            "mailing_note": mailing_mismatch(r["postal_city"], legal_city) if mismatch else None,
            "census_county_fips": hit.county_fips if hit else None,
            "census_agrees": agrees,
            "geo_conflict": agrees is False,
            "resolution_method": "point_in_polygon" if hit else "state_only",
            "stack_ids": [r["state"]]
            + ([county] if county else [])
            + ([city_id] if city_id else []),
            "facts": facts_json(f),
        }
    return records, geo_report(records)


def geo_report(records: dict) -> dict:
    by_tier = Counter(rec["geocoder"] for rec in records.values())
    by_city = Counter(rec["legal_city"] or "(outside the ten cities)" for rec in records.values())
    return {
        "addresses": len(records),
        "matched_batch": by_tier.get("census_batch", 0),
        "matched_oneline": by_tier.get("census_oneline", 0),
        "matched_nominatim": by_tier.get("nominatim", 0),
        "unmatched": by_tier.get("none", 0),
        "unmatched_ids": sorted(a for a, rec in records.items() if rec["geocoder"] == "none"),
        "mailing_mismatches": sum(rec["mailing_mismatch"] for rec in records.values()),
        "mailing_mismatch_by_postal_city": dict(
            sorted(
                Counter(r["postal_city"] for r in records.values() if r["mailing_mismatch"]).items()
            )
        ),
        "census_disagreements": sum(1 for rec in records.values() if rec["census_agrees"] is False),
        "census_disagreement_ids": sorted(
            a for a, rec in records.items() if rec["census_agrees"] is False
        ),
        "outside_known_cities_ids": sorted(
            a for a, rec in records.items() if rec["geocoder"] != "none" and not rec["city_id"]
        ),
        "legal_city_counts": dict(sorted(by_city.items())),
        "zip_suspect": sum(rec["zip_suspect"] for rec in records.values()),
        "geocode_variants": dict(
            sorted(Counter(rec["geocode_variant"] or "batch" for rec in records.values()).items())
        ),
    }


def write(use_network: bool = True) -> dict:
    records, report = resolve_all(use_network=use_network)
    atomic_write_json(config.ARTIFACTS / "addresses.resolved.json", records)
    atomic_write_json(config.ARTIFACTS / "eval" / "geo_report.json", report)
    return report
