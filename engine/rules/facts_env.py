"""Fact environment for one address on one date (PLAN.md 8.2, 8.3).

Built from a record in ``artifacts/addresses.resolved.json`` plus optional renter-supplied facts.
Derived facts (certificate-of-occupancy date, building age) are computed per as-of date.
"""

from __future__ import annotations

from datetime import date

from engine import config
from engine.facts.intervals import Interval
from engine.rules.dsl import FACTS, FactEnv, FactVal

# Facts a renter may supply. Derived facts (co_date, building_age_years) never come from users.
USER_FACTS = {k for k in FACTS if k not in ("co_date", "building_age_years")}


class InvalidFacts(ValueError):
    def __init__(self, problems: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in problems.items()))
        self.problems = problems


def validate_user_facts(facts: dict) -> dict:
    """Check keys and types of renter-supplied facts. Raises InvalidFacts."""
    problems: dict[str, str] = {}
    for key, value in facts.items():
        spec = FACTS.get(key)
        if key not in USER_FACTS or spec is None:
            problems[key] = "unknown fact"
            continue
        if value is None:
            continue
        if spec.kind == "int" and (isinstance(value, bool) or not isinstance(value, int | float)):
            problems[key] = "must be a number"
        elif spec.kind == "bool" and not isinstance(value, bool):
            problems[key] = "must be true or false"
        elif spec.kind == "enum" and not isinstance(value, str):
            problems[key] = "must be text"
    if problems:
        raise InvalidFacts(problems)
    return facts


class AddressEnv(FactEnv):
    def __init__(self, record: dict, user: dict | None = None):
        self.record = record
        self.user = validate_user_facts(user or {})
        self.facts = record["facts"]
        self.proxy = config.PROXY_CO_FROM_YEAR_BUILT

    # -- helpers --
    def _interval(self, name: str) -> FactVal:
        if name in self.user and self.user[name] is not None:
            v = self.user[name]
            return FactVal(interval=Interval.exact(v), source="user", basis="provided by you")
        f = self.facts[name]
        if f["record_conflict"]:
            return FactVal(
                interval=Interval.unknown(), source="missing", record_conflict=True,
                basis=f"public records disagree: {f['basis']}",
            )  # fmt: skip
        iv = Interval(f["lo"], f["hi"])
        if iv.is_unknown:
            return FactVal(interval=iv, source="missing", basis=None)
        derived = bool(f["sources"]) and all(s["kind"] == "assessor_derived" for s in f["sources"])
        return FactVal(
            interval=iv, source="assessor_derived" if derived else "assessor", basis=f["basis"]
        )

    def _year(self) -> FactVal:
        return self._interval("year_built")

    def get(self, fact: str, as_of: date) -> FactVal:
        if fact in ("units", "year_built"):
            return self._interval(fact)
        if fact == "co_date":
            y = self._year()
            if y.interval is None or y.interval.is_unknown:
                return FactVal(interval=Interval.unknown(), source="missing")
            lo, hi = int(y.interval.lo), int(y.interval.hi)
            return FactVal(
                interval=Interval(date(lo, 1, 1), date(hi, 12, 31)), source="derived",
                basis="certificate of occupancy assumed to fall in the year built",
            )  # fmt: skip
        if fact == "building_age_years":
            y = self._year()
            if y.interval is None or y.interval.is_unknown:
                return FactVal(interval=Interval.unknown(), source="missing")
            return FactVal(
                interval=Interval(as_of.year - int(y.interval.hi), as_of.year - int(y.interval.lo)),
                source="derived", basis="calendar years since the year built",
            )  # fmt: skip
        if fact in self.user and self.user[fact] is not None:
            spec = FACTS[fact]
            if spec.kind == "int":
                return FactVal(interval=Interval.exact(self.user[fact]), source="user",
                               basis="provided by you")  # fmt: skip
            return FactVal(scalar=self.user[fact], source="user", basis="provided by you")
        if fact == "property_type":
            pt = self.facts.get("property_type")
            if pt is None or self.facts["units"]["record_conflict"]:
                return FactVal(source="missing")
            return FactVal(
                scalar=pt, source="assessor_derived", basis=self.facts.get("property_type_basis")
            )
        if fact == "subsidized_or_affordable":
            if self.facts.get("subsidized"):
                return FactVal(scalar=True, source="assessor_derived",
                               basis=self.facts.get("subsidized_basis"))  # fmt: skip
            return FactVal(source="missing")
        if fact in ("landlord_unit_count", "landlord_property_count"):
            # The landlord owns at least this building, so the building's own size is a floor.
            units = self._interval("units").interval
            floor = units.lo if fact == "landlord_unit_count" and units is not None else None
            floor = 1 if fact == "landlord_property_count" else floor
            if floor is None:
                return FactVal(interval=Interval.unknown(), source="missing")
            return FactVal(
                interval=Interval(floor, None), source="derived",
                basis="at least the size of this building",
            )  # fmt: skip
        if FACTS[fact].kind == "int":
            return FactVal(interval=Interval.unknown(), source="missing")
        return FactVal(source="missing")  # renter-known: never in the public record
