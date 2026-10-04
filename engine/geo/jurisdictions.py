"""The jurisdictions in scope (PLAN.md 10.1). GEOIDs are verified against TIGER by ``make geo``."""

from __future__ import annotations

from dataclasses import dataclass

STATES = {"CA": ("06", "California"), "NJ": ("34", "New Jersey"), "MA": ("25", "Massachusetts")}


@dataclass(frozen=True)
class City:
    name: str
    state: str
    place_geoid: str  # 7 digits: state FIPS + place FIPS (the Census place or county subdivision)
    layer: str  # PLACE (CA) or COUSUB (NJ, MA)
    county_fips: str  # 5 digits
    county_name: str
    has_addresses: bool = True  # Santa Ana is laws only

    @property
    def id(self) -> str:
        return f"{self.state}-{self.place_geoid}"

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}"


CITIES: tuple[City, ...] = (
    City("Los Angeles", "CA", "0644000", "PLACE", "06037", "Los Angeles County"),
    City("San Francisco", "CA", "0667000", "PLACE", "06075", "San Francisco County"),
    City("San Diego", "CA", "0666000", "PLACE", "06073", "San Diego County"),
    City("Berkeley", "CA", "0606000", "PLACE", "06001", "Alameda County"),
    City("Santa Ana", "CA", "0669000", "PLACE", "06059", "Orange County", has_addresses=False),
    City("Jersey City", "NJ", "3436000", "COUSUB", "34017", "Hudson County"),
    City("Hoboken", "NJ", "3432250", "COUSUB", "34017", "Hudson County"),
    City("Newark", "NJ", "3451000", "COUSUB", "34013", "Essex County"),
    City("Boston", "MA", "2507000", "COUSUB", "25025", "Suffolk County"),
    City("Cambridge", "MA", "2511000", "COUSUB", "25017", "Middlesex County"),
)

COUNTIES: tuple[tuple[str, str, str], ...] = tuple(
    sorted({(c.county_fips, c.county_name, c.state) for c in CITIES})
)  # (fips, name, state): the nine counties


def city_by_id(jid: str) -> City:
    for c in CITIES:
        if c.id == jid:
            return c
    raise KeyError(jid)


def county_id(fips: str, state: str) -> str:
    return f"{state}-{fips}"
