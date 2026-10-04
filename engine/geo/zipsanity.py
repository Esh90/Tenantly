"""ZIP-to-city consistency check (PLAN.md 9.5). Pure functions."""

from __future__ import annotations

NJ_VALID_ZIPS: dict[str, set[str]] = {
    "hoboken": {"07030"},
    "jersey city": {f"{z:05d}" for z in range(7302, 7312)},
    "newark": {f"{z:05d}" for z in range(7101, 7200)},
}


def zip_is_suspect(state: str, postal_city: str, zip_code: str | None) -> bool:
    """True when a non-empty ZIP is inconsistent with the state/city. Empty ZIPs are fine."""
    z = (zip_code or "").strip()
    if not z:
        return False
    if state == "NJ":
        valid = NJ_VALID_ZIPS.get(postal_city.strip().lower())
        return valid is not None and z not in valid
    if state == "CA":
        return not z.startswith("9")
    if state == "MA":
        return not (z.startswith("01") or z.startswith("02"))
    return False
