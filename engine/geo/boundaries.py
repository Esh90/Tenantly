"""TIGER/Line boundaries (PLAN.md 10.2). Build-time only (pyogrio); runtime reads the artifacts.

Outputs (committed):
- ``artifacts/geo/pip.json``: full-resolution geometry (WKB hex) for point-in-polygon.
- ``artifacts/geo/jurisdictions.geojson``: 0.0002-degree simplified copy for display.
- ``artifacts/eval/geo_boundaries.json``: verified GEOIDs and the source files used.

Source: https://www2.census.gov/geo/tiger/TIGERYYYY/ (try 2025, then 2024); if a download keeps
failing, the cartographic boundary file is used and ``geo_source`` is set to ``cb``.
"""

from __future__ import annotations

import logging
import time
import urllib.request
from pathlib import Path

import shapely
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from engine import config
from engine.geo.jurisdictions import CITIES, COUNTIES, STATES, county_id
from engine.io import atomic_write_json

log = logging.getLogger("tenantly.geo")

YEARS = (2025, 2024)
BASE = "https://www2.census.gov/geo/tiger/TIGER{y}/"
CACHE = config.ARTIFACTS / "cache" / "tiger"
SIMPLIFY_DEGREES = 0.0002


def _tiger_urls(kind: str, fips: str | None, y: int) -> list[str]:
    base = BASE.format(y=y)
    if kind == "PLACE":
        return [f"{base}PLACE/tl_{y}_{fips}_place.zip"]
    if kind == "COUSUB":
        return [f"{base}COUSUB/tl_{y}_{fips}_cousub.zip"]
    if kind == "COUNTY":
        return [f"{base}COUNTY/tl_{y}_us_county.zip"]
    if kind == "STATE":
        return [f"{base}STATE/tl_{y}_us_state.zip"]
    raise ValueError(kind)


def _cb_url(kind: str, fips: str | None, y: int) -> str:
    base = f"https://www2.census.gov/geo/tiger/GENZ{y}/shp/"
    name = {
        "PLACE": f"cb_{y}_{fips}_place_500k.zip",
        "COUSUB": f"cb_{y}_{fips}_cousub_500k.zip",
        "COUNTY": f"cb_{y}_us_county_500k.zip",
        "STATE": f"cb_{y}_us_state_500k.zip",
    }[kind]
    return base + name


def _download(url: str, dest: Path, tries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tenantly-geo/0.1"})
            with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310
                data = resp.read()
            tmp = dest.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(dest)
            log.info("downloaded url=%s bytes=%d", url, len(data))
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("download failed url=%s attempt=%d reason=%s", url, attempt, exc)
            time.sleep(2 * attempt)
    return False


def fetch(kind: str, fips: str | None) -> tuple[Path, str]:
    """Return (zip path, geo_source). geo_source is tigerYYYY or cbYYYY."""
    for y in YEARS:
        for url in _tiger_urls(kind, fips, y):
            dest = CACHE / url.rsplit("/", 1)[1]
            if _download(url, dest):
                return dest, f"tiger{y}"
    for y in YEARS:
        url = _cb_url(kind, fips, y)
        dest = CACHE / url.rsplit("/", 1)[1]
        if _download(url, dest):
            return dest, f"cb{y}"
    raise RuntimeError(f"could not download {kind} boundaries for {fips}")


def read_layer(path: Path, columns: list[str]) -> list[dict]:
    """Rows of a shapefile zip as dicts with a shapely geometry under ``geometry``."""
    from pyogrio.raw import read

    meta, _fids, geometry, field_data = read(f"/vsizip/{path.as_posix()}", columns=columns)
    names = [str(n) for n in meta["fields"]]  # the file's own order, not the requested one
    geoms = shapely.from_wkb(geometry)
    rows = []
    for i, geom in enumerate(geoms):
        row = {names[k]: field_data[k][i] for k in range(len(names))}
        row["geometry"] = geom
        rows.append(row)
    return rows


def _geoid_of(row: dict, layer: str) -> str:
    if layer == "PLACE":
        return str(row["GEOID"])
    return str(row["STATEFP"]) + str(row["COUSUBFP"])  # 7 digits, as in PLAN.md 10.1


def build() -> dict:
    """Download, verify GEOIDs and write the artifacts. Returns the verification report."""
    features: list[dict] = []
    pip: dict[str, dict] = {}
    report: dict = {"cities": [], "counties": [], "states": [], "files": {}}

    def add(jid: str, level: str, name: str, label: str, state: str, geoid: str | None,
            geom: BaseGeometry, source: str) -> None:  # fmt: skip
        pip[jid] = {"level": level, "wkb": shapely.to_wkb(geom, hex=True)}
        simple = shapely.simplify(geom, SIMPLIFY_DEGREES, preserve_topology=True)
        features.append(
            {
                "type": "Feature",
                "id": jid,
                "geometry": mapping(simple),
                "properties": {"id": jid, "level": level, "name": name, "label": label,
                               "state": state, "geoid": geoid, "geo_source": source},
            }
        )  # fmt: skip

    cache: dict[tuple[str, str | None], tuple[list[dict], str]] = {}

    def layer(kind: str, fips: str | None, cols: list[str]) -> tuple[list[dict], str]:
        key = (kind, fips)
        if key not in cache:
            path, src = fetch(kind, fips)
            report["files"][path.name] = src
            cache[key] = (read_layer(path, cols), src)
        return cache[key]

    for code, (fips, name) in STATES.items():
        rows, src = layer("STATE", None, ["GEOID", "NAME"])
        row = next(r for r in rows if str(r["GEOID"]) == fips)
        add(code, "state", name, code, code, None, row["geometry"], src)
        report["states"].append({"id": code, "geoid": fips, "name": str(row["NAME"])})

    for cfips, cname, state in COUNTIES:
        rows, src = layer("COUNTY", None, ["GEOID", "NAME", "NAMELSAD"])
        row = next((r for r in rows if str(r["GEOID"]) == cfips), None)
        if row is None:
            raise RuntimeError(f"county {cfips} missing from TIGER")
        add(county_id(cfips, state), "county", cname, f"{cname}, {state}", state, cfips,
            row["geometry"], src)  # fmt: skip
        report["counties"].append(
            {"geoid": cfips, "name": cname, "tiger_name": str(row["NAMELSAD"])}
        )

    for c in CITIES:
        sfips = STATES[c.state][0]
        if c.layer == "PLACE":
            rows, src = layer("PLACE", sfips, ["GEOID", "NAME", "STATEFP"])
        else:
            rows, src = layer("COUSUB", sfips, ["STATEFP", "COUNTYFP", "COUSUBFP", "NAME"])
        matches = [r for r in rows if _geoid_of(r, c.layer) == c.place_geoid]
        if c.layer == "COUSUB":
            matches = [
                r for r in matches if str(r["STATEFP"]) + str(r["COUNTYFP"]) == c.county_fips
            ]
        if len(matches) != 1:
            raise RuntimeError(f"{c.label}: expected one {c.layer} match for {c.place_geoid}")
        row = matches[0]
        tiger_name = str(row["NAME"])
        if tiger_name.lower() != c.name.lower():
            raise RuntimeError(f"{c.label}: TIGER name {tiger_name!r} != {c.name!r}")
        add(c.id, "city", c.name, c.label, c.state, c.place_geoid, row["geometry"], src)
        entry = {"id": c.id, "geoid": c.place_geoid, "layer": c.layer, "tiger_name": tiger_name,
                 "geo_source": src}  # fmt: skip
        if c.layer == "COUSUB":  # cross-check against the Census place of the same GEOID
            prow, _ = layer("PLACE", sfips, ["GEOID", "NAME", "STATEFP"])
            place = next((r for r in prow if str(r["GEOID"]) == c.place_geoid), None)
            if place is not None:
                inter = place["geometry"].intersection(row["geometry"]).area
                union = place["geometry"].union(row["geometry"]).area
                entry["place_iou"] = round(inter / union, 4) if union else None
        report["cities"].append(entry)

    geo_dir = config.ARTIFACTS / "geo"
    atomic_write_json(geo_dir / "pip.json", pip)
    atomic_write_json(geo_dir / "jurisdictions.geojson",
                      {"type": "FeatureCollection", "features": features})  # fmt: skip
    atomic_write_json(config.ARTIFACTS / "eval" / "geo_boundaries.json", report)
    return report
