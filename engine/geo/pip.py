"""Point-in-polygon over the jurisdiction boundaries (PLAN.md D9). Runtime-safe: shapely only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import shapely
from shapely.geometry import Point
from shapely.strtree import STRtree

from engine import config

PIP_PATH = config.ARTIFACTS / "geo" / "pip.json"


@dataclass(frozen=True)
class Located:
    city_id: str | None
    county_id: str | None


class Locator:
    def __init__(self, path: Path = PIP_PATH):
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._ids: dict[str, list[str]] = {"city": [], "county": []}
        geoms: dict[str, list] = {"city": [], "county": []}
        for jid in sorted(raw):
            level = raw[jid]["level"]
            if level in geoms:
                self._ids[level].append(jid)
                geoms[level].append(shapely.from_wkb(raw[jid]["wkb"]))
        self._geoms = geoms
        self._trees = {k: STRtree(v) for k, v in geoms.items()}

    def _find(self, level: str, pt: Point) -> str | None:
        hits = sorted(int(i) for i in self._trees[level].query(pt, predicate="intersects"))
        return self._ids[level][hits[0]] if hits else None

    def locate(self, lat: float, lon: float) -> Located:
        pt = Point(lon, lat)
        return Located(self._find("city", pt), self._find("county", pt))


@lru_cache(maxsize=1)
def default_locator() -> Locator:
    return Locator()
