"""Predicate DSL over a fixed fact registry, evaluated with Kleene logic (PLAN.md 8.2 to 8.4).

The model never decides applicability: it only writes predicates in this DSL, and the engine
evaluates them. Pure functions; every evaluation returns ``(value, trace)``.

JSON syntax::

    {"const": true}
    {"all": [p, ...]}   {"any": [p, ...]}   {"not": p}
    {"exists": "units"}
    {"fact": "units", "op": ">=", "value": 5}
    {"fact": "co_date", "op": "<=", "value": "1978-10-01"}
    {"fact": "co_date", "op": ">", "value": {"as_of_minus_years": 15}}
    {"fact": "property_type", "op": "in", "value": ["condo", "tic"]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from engine.facts.intervals import Interval, Tri, all_, any_

DSL_VERSION = 1
PROPERTY_TYPES = (
    "multifamily_2_4", "multifamily_5plus", "condo", "tic", "cooperative", "elderly_home",
    "mixed_use", "single_family", "other",
)  # fmt: skip


class DslError(ValueError):
    pass


@dataclass(frozen=True)
class FactSpec:
    name: str
    kind: str  # int | date | enum | bool
    known_from: str  # data | renter
    label_en: str
    label_es: str


FACTS: dict[str, FactSpec] = {
    f.name: f
    for f in [
        FactSpec("units", "int", "data", "Number of units", "Número de unidades"),
        FactSpec("year_built", "int", "data", "Year built", "Año de construcción"),
        FactSpec("co_date", "date", "data", "Certificate of occupancy date",
                 "Fecha del certificado de ocupación"),
        FactSpec("building_age_years", "int", "data", "Building age in years",
                 "Antigüedad del edificio en años"),
        FactSpec("property_type", "enum", "data", "Property type", "Tipo de propiedad"),
        FactSpec("subsidized_or_affordable", "bool", "renter", "Subsidized or affordable housing",
                 "Vivienda subsidiada o asequible"),
        FactSpec("owner_is_natural_person", "bool", "renter", "Owner is a natural person",
                 "El dueño es una persona física"),
        FactSpec("owner_occupied", "bool", "renter", "Owner lives in the building",
                 "El dueño vive en el edificio"),
        FactSpec("landlord_property_count", "int", "renter", "Properties the landlord owns",
                 "Propiedades del arrendador"),
        FactSpec("landlord_unit_count", "int", "renter", "Units the landlord owns in total",
                 "Unidades totales del arrendador"),
        FactSpec("unit_separately_alienable", "bool", "renter", "Unit can be sold separately",
                 "La unidad se puede vender por separado"),
        FactSpec("shares_kitchen_bath_with_owner", "bool", "renter",
                 "Shares a kitchen or bathroom with the owner",
                 "Comparte cocina o baño con el dueño"),
    ]
}  # fmt: skip

NUMERIC_OPS = ("<", "<=", ">", ">=", "==", "!=")
ENUM_OPS = ("==", "!=", "in", "not_in")
BOOL_OPS = ("==", "!=")

_OP_EN = {"<": "is less than", "<=": "is at most", ">": "is more than", ">=": "is at least",
          "==": "is", "!=": "is not", "in": "is one of", "not_in": "is not one of"}  # fmt: skip
_OP_ES = {"<": "es menor que", "<=": "es como máximo", ">": "es mayor que", ">=": "es al menos",
          "==": "es", "!=": "no es", "in": "es uno de", "not_in": "no es uno de"}  # fmt: skip
_DATE_OP_EN = {"<": "is before", "<=": "is on or before", ">": "is after", ">=": "is on or after",
               "==": "is", "!=": "is not"}  # fmt: skip
_DATE_OP_ES = {"<": "es anterior a", "<=": "es el o antes del", ">": "es posterior a",
               ">=": "es el o después del", "==": "es", "!=": "no es"}  # fmt: skip


# ---- AST ----


@dataclass(frozen=True)
class AsOfMinusYears:
    years: int


@dataclass(frozen=True)
class Const:
    value: bool | None  # None is the explicit "unknown" constant: an exemption we cannot express


@dataclass(frozen=True)
class AllOf:
    children: tuple


@dataclass(frozen=True)
class AnyOf:
    children: tuple


@dataclass(frozen=True)
class NotOf:
    child: object


@dataclass(frozen=True)
class Exists:
    fact: str


@dataclass(frozen=True)
class Cmp:
    fact: str
    op: str
    value: Any  # int | date | str | bool | tuple[str, ...] | AsOfMinusYears


Node = Const | AllOf | AnyOf | NotOf | Exists | Cmp


def _parse_date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError) as exc:
        raise DslError(f"bad date {s!r}") from exc


def parse(d: dict) -> Node:
    """Parse and validate a JSON predicate. Raises DslError with a precise message."""
    if not isinstance(d, dict):
        raise DslError(f"predicate must be an object, got {type(d).__name__}")
    keys = set(d)
    if keys == {"const"}:
        if d["const"] == "unknown":
            return Const(None)
        if not isinstance(d["const"], bool):
            raise DslError("const must be true, false or 'unknown'")
        return Const(d["const"])
    if keys == {"all"} or keys == {"any"}:
        kids = d["all"] if "all" in d else d["any"]
        if not isinstance(kids, list) or not kids:
            raise DslError("all/any need a non-empty list")
        children = tuple(parse(k) for k in kids)
        return AllOf(children) if "all" in d else AnyOf(children)
    if keys == {"not"}:
        return NotOf(parse(d["not"]))
    if keys == {"exists"}:
        if d["exists"] not in FACTS:
            raise DslError(f"unknown fact {d['exists']!r}")
        return Exists(d["exists"])
    if keys == {"fact", "op", "value"}:
        return _parse_cmp(d["fact"], d["op"], d["value"])
    raise DslError(f"unrecognized predicate keys {sorted(keys)}")


def _parse_cmp(fact: str, op: str, value: Any) -> Cmp:
    spec = FACTS.get(fact)
    if spec is None:
        raise DslError(f"unknown fact {fact!r}")
    if spec.kind in ("int", "date"):
        if op not in NUMERIC_OPS:
            raise DslError(f"operator {op!r} not allowed for {fact}")
        if spec.kind == "int":
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise DslError(f"{fact} needs a number, got {value!r}")
            return Cmp(fact, op, value)
        if isinstance(value, dict):
            years = value.get("as_of_minus_years")
            if set(value) != {"as_of_minus_years"} or not isinstance(years, int):
                raise DslError("date value object must be {'as_of_minus_years': int}")
            return Cmp(fact, op, AsOfMinusYears(years))
        return Cmp(fact, op, _parse_date(value))
    if spec.kind == "enum":
        if op not in ENUM_OPS:
            raise DslError(f"operator {op!r} not allowed for {fact}")
        vals = value if op in ("in", "not_in") else [value]
        if not isinstance(vals, list) or not vals:
            raise DslError(f"{op} needs a non-empty list")
        for v in vals:
            if v not in PROPERTY_TYPES:
                raise DslError(f"unknown property_type {v!r}")
        return Cmp(fact, op, tuple(vals) if op in ("in", "not_in") else value)
    if op not in BOOL_OPS:
        raise DslError(f"operator {op!r} not allowed for {fact}")
    if not isinstance(value, bool):
        raise DslError(f"{fact} needs true or false")
    return Cmp(fact, op, value)


def validate(d: dict) -> list[str]:
    try:
        parse(d)
    except DslError as exc:
        return [str(exc)]
    return []


def to_dict(node: Node) -> dict:
    if isinstance(node, Const):
        return {"const": "unknown" if node.value is None else node.value}
    if isinstance(node, AllOf):
        return {"all": [to_dict(c) for c in node.children]}
    if isinstance(node, AnyOf):
        return {"any": [to_dict(c) for c in node.children]}
    if isinstance(node, NotOf):
        return {"not": to_dict(node.child)}
    if isinstance(node, Exists):
        return {"exists": node.fact}
    v = node.value
    if isinstance(v, AsOfMinusYears):
        v = {"as_of_minus_years": v.years}
    elif isinstance(v, date):
        v = v.isoformat()
    elif isinstance(v, tuple):
        v = list(v)
    return {"fact": node.fact, "op": node.op, "value": v}


def facts_used(node: Node) -> set[str]:
    if isinstance(node, Const):
        return set()
    if isinstance(node, AllOf | AnyOf):
        return set().union(*(facts_used(c) for c in node.children))
    if isinstance(node, NotOf):
        return facts_used(node.child)
    return {node.fact}


# ---- environment and evaluation ----


@dataclass(frozen=True)
class FactVal:
    """What the environment knows about one fact on one date."""

    interval: Interval | None = None  # int and date facts
    scalar: Any = None  # enum and bool facts
    source: str = "missing"  # assessor | assessor_derived | user | derived | missing
    basis: str | None = None
    record_conflict: bool = False

    @property
    def unknown(self) -> bool:
        if self.interval is not None:
            return self.interval.is_unknown
        return self.scalar is None


class FactEnv:
    """Interface: ``get(fact, as_of) -> FactVal``. Implemented by engine/rules/facts_env.py."""

    def get(self, fact: str, as_of: date) -> FactVal:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class TraceItem:
    label_en: str
    label_es: str
    fact: str
    op: str
    expected: str
    actual: str | None
    basis: str | None
    result: Tri

    def as_dict(self) -> dict:
        return {
            "label_en": self.label_en, "label_es": self.label_es, "fact": self.fact,
            "op": self.op, "expected": self.expected, "actual": self.actual,
            "basis": self.basis, "result": self.result.value,
        }  # fmt: skip


@dataclass
class Evaluation:
    value: Tri
    trace: list[TraceItem] = field(default_factory=list)
    unknown_facts: set[str] = field(default_factory=set)  # facts that left the result open


def _years_before(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # Feb 29
        return d.replace(year=d.year - years, day=28)


def _threshold(value: Any, as_of: date) -> Any:
    return _years_before(as_of, value.years) if isinstance(value, AsOfMinusYears) else value


def describe_interval(iv: Interval | None, kind: str) -> str | None:
    if iv is None or iv.is_unknown:
        return None
    fmt = (lambda x: x.isoformat()) if kind == "date" else (lambda x: f"{x:g}")
    if iv.is_exact:
        return fmt(iv.lo)
    if iv.hi is None:
        return f"{fmt(iv.lo)} or more" if kind != "date" else f"on or after {fmt(iv.lo)}"
    if iv.lo is None:
        return f"{fmt(iv.hi)} or less" if kind != "date" else f"on or before {fmt(iv.hi)}"
    return f"between {fmt(iv.lo)} and {fmt(iv.hi)}"


def _expected_text(spec: FactSpec, op: str, value: Any) -> str:
    if isinstance(value, AsOfMinusYears):
        return f"{value.years} years before the date checked"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, tuple):
        return ", ".join(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    return f"{value:g}" if isinstance(value, int | float) else str(value)


def _eval_cmp(node: Cmp, env: FactEnv, as_of: date) -> Evaluation:
    spec = FACTS[node.fact]
    fv = env.get(node.fact, as_of)
    if spec.kind in ("int", "date"):
        iv = fv.interval or Interval.unknown()
        result = iv.compare(node.op, _threshold(node.value, as_of))
        actual = describe_interval(iv, spec.kind)
    elif spec.kind == "enum":
        if fv.scalar is None:
            result = Tri.UNKNOWN
        elif node.op in ("in", "not_in"):
            result = Tri.of((fv.scalar in node.value) == (node.op == "in"))
        else:
            result = Tri.of((fv.scalar == node.value) == (node.op == "=="))
        actual = None if fv.scalar is None else str(fv.scalar)
    else:
        if fv.scalar is None:
            result = Tri.UNKNOWN
        else:
            result = Tri.of((fv.scalar == node.value) == (node.op == "=="))
        actual = None if fv.scalar is None else ("yes" if fv.scalar else "no")
    ops_en = _DATE_OP_EN if spec.kind == "date" else _OP_EN
    ops_es = _DATE_OP_ES if spec.kind == "date" else _OP_ES
    expected = _expected_text(spec, node.op, node.value)
    item = TraceItem(
        label_en=f"{spec.label_en} {ops_en[node.op]} {expected}",
        label_es=f"{spec.label_es} {ops_es[node.op]} {expected}",
        fact=node.fact, op=node.op, expected=expected, actual=actual, basis=fv.basis, result=result,
    )  # fmt: skip
    missing = {node.fact} if result is Tri.UNKNOWN else set()
    return Evaluation(result, [item], missing)


def evaluate(node: Node, env: FactEnv, as_of: date) -> Evaluation:
    """Kleene evaluation. ``unknown_facts`` lists only the facts that kept the result open:
    an FALSE ``all`` or a TRUE ``any`` is decided, so it reports none."""
    if isinstance(node, Const):
        return Evaluation(Tri.UNKNOWN if node.value is None else Tri.of(node.value))
    if isinstance(node, Exists):
        known = not env.get(node.fact, as_of).unknown
        spec = FACTS[node.fact]
        item = TraceItem(
            f"{spec.label_en} is known", f"{spec.label_es}: se conoce", node.fact, "exists",
            "known", "known" if known else None, None, Tri.of(known),
        )  # fmt: skip
        return Evaluation(Tri.of(known), [item])
    if isinstance(node, NotOf):
        inner = evaluate(node.child, env, as_of)
        return Evaluation(~inner.value, inner.trace, inner.unknown_facts)
    if isinstance(node, Cmp):
        return _eval_cmp(node, env, as_of)
    parts = [evaluate(c, env, as_of) for c in node.children]
    trace = [t for p in parts for t in p.trace]
    values = [p.value for p in parts]
    if isinstance(node, AllOf):
        value = all_(values)
        decided_by = Tri.FALSE
    else:
        value = any_(values)
        decided_by = Tri.TRUE
    unknown: set[str] = set()
    if value is Tri.UNKNOWN:
        unknown = set().union(*(p.unknown_facts for p in parts if p.value is Tri.UNKNOWN))
    elif value is not decided_by:
        unknown = set()
    return Evaluation(value, trace, unknown)


# ---- timeline support ----


def change_dates(node: Node, env: FactEnv, start: date, end: date) -> set[date]:
    """Dates in [start, end] where a date-relative or age-based comparison can flip."""
    out: set[date] = set()
    if isinstance(node, Const | Exists):
        return out
    if isinstance(node, AllOf | AnyOf):
        for c in node.children:
            out |= change_dates(c, env, start, end)
        return out
    if isinstance(node, NotOf):
        return change_dates(node.child, env, start, end)
    spec = FACTS[node.fact]
    if spec.kind == "date" and isinstance(node.value, AsOfMinusYears):
        iv = env.get("co_date", start).interval
        if iv is None:
            return out
        for bound in (iv.lo, iv.hi):
            if bound is not None:
                flip = bound.replace(year=bound.year + node.value.years)
                out |= {flip, flip + timedelta(days=1)}
    elif node.fact == "building_age_years" and not isinstance(node.value, AsOfMinusYears):
        iv = env.get("year_built", start).interval
        if iv is not None:
            for bound in (iv.lo, iv.hi):
                if bound is not None:
                    y = int(bound) + int(node.value)
                    out |= {date(y, 1, 1), date(y + 1, 1, 1)}
    return {d for d in out if start <= d <= end}
