"""Geocoding cascade (PLAN.md 10.3): Census batch, then Census one-line variants, then
Nominatim. Every network response is cached on disk, so reruns are free and deterministic.

The postal city never decides the legal city; point-in-polygon does. The postal city is only a
hint in the geocoder query, with fallback variants when it fails.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from engine import config

log = logging.getLogger("tenantly.geocode")

CACHE = config.ARTIFACTS / "cache" / "geocode"
CENSUS = "https://geocoding.geo.census.gov/geocoder/geographies"
BENCHMARK = {"benchmark": "Public_AR_Current", "vintage": "Current_Current"}
NOMINATIM = "https://nominatim.openstreetmap.org/search"
UA = "tenantly-geocoder/0.1 (housing-law lookup; contact via NOMINATIM_EMAIL)"

_RANGE = re.compile(r"^(\d+)(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s")
_SUFFIXES = {
    "STREET": "ST", "AVENUE": "AVE", "ROAD": "RD", "BOULEVARD": "BLVD", "DRIVE": "DR",
    "PLACE": "PL", "COURT": "CT", "LANE": "LN", "TERRACE": "TER", "PARKWAY": "PKWY",
}  # fmt: skip
BOSTON_NEIGHBORHOODS = {
    "allston", "brighton", "dorchester", "east boston", "hyde park", "jamaica plain",
    "mattapan", "roxbury", "south boston", "west roxbury", "roslindale", "charlestown",
    "mission hill", "south end", "back bay", "fenway", "north end", "west end",
}  # fmt: skip


def normalize_street(street: str) -> str:
    """Reduce a leading range to its first number, drop decimals, uppercase for geocoding."""
    s = street.strip()
    m = _RANGE.match(s)
    if m:
        s = m.group(1) + s[m.end() - 1 :]
    s = re.sub(r"^(\d+)\.\d+\b", r"\1", s)  # '322.5 Western' -> '322 Western'
    s = re.sub(r"\s+", " ", s).upper()
    s = re.sub(r"\b0+(\d+(?:ST|ND|RD|TH))\b", r"\1", s)  # '05TH' -> '5TH'
    s = re.sub(r"\bAV\b\.?", "AVE", s)  # SF assessor 'AV' -> 'AVE'
    return s.rstrip(".")


def street_variants(street: str) -> list[str]:
    """The normalized street plus the preferred-suffix alternatives (full and abbreviated)."""
    base = normalize_street(street)
    out = [base]
    words = base.split()
    if words:
        last = words[-1]
        if last in _SUFFIXES:
            out.append(" ".join(words[:-1] + [_SUFFIXES[last]]))
        inverse = {v: k for k, v in _SUFFIXES.items()}
        if last in inverse:
            out.append(" ".join(words[:-1] + [inverse[last]]))
    return list(dict.fromkeys(out))


def city_hint(postal_city: str, state: str) -> list[str]:
    """Cities to try in a query: the postal city first, then a geocoder-friendly fallback."""
    out = [postal_city]
    low = postal_city.strip().lower()
    if state == "MA" and low in BOSTON_NEIGHBORHOODS:
        out.append("Boston")
    if state == "CA" and low == "san ysidro":
        out.append("San Diego")
    return list(dict.fromkeys(out))


@dataclass
class GeoHit:
    lat: float
    lon: float
    tier: str  # census_batch | census_oneline | nominatim
    matched_address: str | None = None
    variant: str | None = None
    state_fips: str | None = None
    county_fips: str | None = None  # 5 digits
    place_geoid: str | None = None  # 7 digits when the geocoder returns one
    cousub_geoid: str | None = None  # 10 digits
    extra: dict = field(default_factory=dict)


def _cache_path(kind: str, key: str) -> Path:
    return CACHE / f"{kind}_{hashlib.sha256(key.encode('utf-8')).hexdigest()[:20]}.json"


def _cached(kind: str, key: str):
    p = _cache_path(kind, key)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _store(kind: str, key: str, value) -> None:
    p = _cache_path(kind, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def _get_json(url: str, timeout: int = 60) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


# ---- Census batch ----


def _multipart(fields: dict[str, str], file_field: str, filename: str, content: str):
    boundary = "----tenantly" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
        f'filename="{filename}"\r\nContent-Type: text/csv\r\n\r\n{content}\r\n'
    )
    parts.append(f"--{boundary}--\r\n")
    return "".join(parts).encode("utf-8"), f"multipart/form-data; boundary={boundary}"


def census_batch(rows: list[tuple[str, str, str, str, str]]) -> dict[str, GeoHit | None]:
    """rows: (id, street, city, state, zip). One request for all rows (limit 10,000)."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    body_text = buf.getvalue()
    cached = _cached("batch", body_text)
    if cached is None:
        data, ctype = _multipart(BENCHMARK, "addressFile", "addresses.csv", body_text)
        req = urllib.request.Request(
            CENSUS + "/addressbatch", data=data, headers={"Content-Type": ctype, "User-Agent": UA}
        )
        log.info("census batch request rows=%d", len(rows))
        with urllib.request.urlopen(req, timeout=600) as resp:  # noqa: S310
            cached = {"csv": resp.read().decode("utf-8")}
        _store("batch", body_text, cached)
    return parse_batch_csv(cached["csv"])


def parse_batch_csv(text: str) -> dict[str, GeoHit | None]:
    """Columns: id, input, match, exactness, matched address, 'lon,lat', tigerlineid, side,
    state fips, county fips, tract, block."""
    out: dict[str, GeoHit | None] = {}
    for rec in csv.reader(io.StringIO(text)):
        if not rec:
            continue
        rid = rec[0]
        if len(rec) < 6 or rec[2] != "Match" or "," not in rec[5]:
            out[rid] = None
            continue
        lon_s, lat_s = rec[5].split(",")
        out[rid] = GeoHit(
            lat=float(lat_s),
            lon=float(lon_s),
            tier="census_batch",
            matched_address=rec[4],
            state_fips=rec[8] if len(rec) > 8 else None,
            county_fips=(rec[8] + rec[9]) if len(rec) > 9 and rec[8] and rec[9] else None,
        )
    return out


# ---- Census one-line ----


def census_oneline(address: str) -> GeoHit | None:
    cached = _cached("oneline", address)
    if cached is None:
        q = urllib.parse.urlencode({"address": address, "format": "json", **BENCHMARK})
        try:
            cached = _get_json(f"{CENSUS}/onelineaddress?{q}")
        except Exception as exc:  # noqa: BLE001
            log.warning("census oneline failed address=%r reason=%s", address, exc)
            return None
        _store("oneline", address, cached)
    return parse_oneline(cached)


def parse_oneline(payload: dict) -> GeoHit | None:
    matches = payload.get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    m = matches[0]
    geos = m.get("geographies", {})
    county = (geos.get("Counties") or [{}])[0].get("GEOID")
    place = (geos.get("Incorporated Places") or [{}])[0].get("GEOID")
    cousub = (geos.get("County Subdivisions") or [{}])[0].get("GEOID")
    return GeoHit(
        lat=float(m["coordinates"]["y"]),
        lon=float(m["coordinates"]["x"]),
        tier="census_oneline",
        matched_address=m.get("matchedAddress"),
        state_fips=(geos.get("States") or [{}])[0].get("GEOID"),
        county_fips=county,
        place_geoid=place,
        cousub_geoid=cousub,
    )


# ---- Nominatim (1 request per second, cached) ----

_last_nominatim = 0.0


def nominatim(address: str) -> GeoHit | None:
    global _last_nominatim
    cached = _cached("nominatim", address)
    if cached is None:
        wait = 1.05 - (time.monotonic() - _last_nominatim)
        if wait > 0:
            time.sleep(wait)
        params = {"q": address, "format": "jsonv2", "countrycodes": "us", "limit": "1"}
        email = os.environ.get("NOMINATIM_EMAIL")
        if email:
            params["email"] = email
        try:
            req = urllib.request.Request(
                NOMINATIM + "?" + urllib.parse.urlencode(params), headers={"User-Agent": UA}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
                cached = {"results": json.loads(resp.read().decode("utf-8"))}
        except Exception as exc:  # noqa: BLE001
            log.warning("nominatim failed address=%r reason=%s", address, exc)
            return None
        finally:
            _last_nominatim = time.monotonic()
        _store("nominatim", address, cached)
    results = cached.get("results") or []
    if not results:
        return None
    r = results[0]
    return GeoHit(
        lat=float(r["lat"]),
        lon=float(r["lon"]),
        tier="nominatim",
        matched_address=r.get("display_name"),
    )


# ---- cascade ----


def cascade(street: str, postal_city: str, state: str, zip_code: str | None) -> GeoHit | None:
    """One-line retries then Nominatim, for an address the batch could not match."""
    zips = [zip_code] if zip_code else []
    queries: list[tuple[str, str]] = []
    for st in street_variants(street):
        for city in city_hint(postal_city, state):
            for z in zips + [""]:
                tail = f" {z}" if z else ""
                label = "with_zip" if z else "without_zip"
                if st != normalize_street(street):
                    label += "+suffix"
                if city != postal_city:
                    label += "+city_hint"
                queries.append((f"{st}, {city}, {state}{tail}".strip(), label))
    for addr, label in dict.fromkeys(queries):
        hit = census_oneline(addr)
        if hit:
            hit.variant = label
            return hit
    for addr, label in dict.fromkeys(queries):
        hit = nominatim(addr)
        if hit:
            hit.variant = label
            return hit
    return None
