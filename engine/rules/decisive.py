"""Decisive question (PLAN.md 14.5): ask the one missing fact that resolves the most unknowns.

Ties break in this order: year_built, units, property_type, subsidized, owner_occupied,
owner_is_natural_person.
"""

from __future__ import annotations

from engine.rules.engine import AddressResult

ASKABLE_ORDER = (
    "year_built",
    "units",
    "property_type",
    "subsidized_or_affordable",
    "owner_occupied",
    "owner_is_natural_person",
)
# derived facts are resolved by asking for the fact they come from
ASK_FOR = {"co_date": "year_built", "building_age_years": "year_built"}

PROMPTS = {
    "year_built": (
        "What year was the building built?",
        "¿En qué año se construyó el edificio?",
        "year",
    ),
    "units": (
        "How many apartments are in the building?",
        "¿Cuántos apartamentos hay en el edificio?",
        "integer",
    ),
    "property_type": ("What kind of building is it?", "¿Qué tipo de edificio es?", "select"),
    "subsidized_or_affordable": (
        "Is the building subsidized or income-restricted?",
        "¿El edificio recibe subsidios o tiene restricciones de ingresos?",
        "boolean",
    ),
    "owner_occupied": (
        "Does the owner live in the building?",
        "¿El dueño vive en el edificio?",
        "boolean",
    ),
    "owner_is_natural_person": (
        "Is the owner a person, not a company?",
        "¿El dueño es una persona y no una empresa?",
        "boolean",
    ),
}
PROPERTY_TYPE_OPTIONS = [
    ("multifamily_2_4", "Apartment building, 2 to 4 units", "Edificio de 2 a 4 unidades"),
    ("multifamily_5plus", "Apartment building, 5 or more units", "Edificio de 5 o más unidades"),
    ("condo", "Condominium", "Condominio"),
    ("tic", "Tenancy in common", "Copropiedad (TIC)"),
    ("cooperative", "Cooperative", "Cooperativa"),
    ("single_family", "Single-family home", "Casa unifamiliar"),
    ("mixed_use", "Apartments above a shop", "Apartamentos sobre un comercio"),
    ("elderly_home", "Housing for older adults", "Vivienda para personas mayores"),
    ("other", "Something else", "Otro"),
]


def _askable(missing: list[str]) -> set[str]:
    return {ASK_FOR.get(f, f) for f in missing if ASK_FOR.get(f, f) in ASKABLE_ORDER}


def decisive_question(result: AddressResult) -> dict | None:
    unknown = [
        o for o in result.outcomes if o.result == "unknown" and "location" not in o.missing_facts
    ]
    if not unknown:
        return None
    # a rule is resolved by one answer only if that fact is the only thing missing
    scores: dict[str, list[str]] = {f: [] for f in ASKABLE_ORDER}
    reach: dict[str, int] = dict.fromkeys(ASKABLE_ORDER, 0)
    for o in unknown:
        needed = _askable(o.missing_facts)
        for fact in needed:
            reach[fact] += 1
            if needed == {fact}:
                scores[fact].append(o.rule_id)
    best = max(ASKABLE_ORDER, key=lambda f: (len(scores[f]), reach[f], -ASKABLE_ORDER.index(f)))
    if reach[best] == 0:
        return None
    en, es, kind = PROMPTS[best]
    q = {
        "fact": best,
        "prompt": {"en": en, "es": es},
        "input": kind,
        "resolves_rule_ids": sorted(scores[best]),
    }
    if kind == "select":
        q["options"] = [
            {"value": v, "label": {"en": a, "es": b}} for v, a, b in PROPERTY_TYPE_OPTIONS
        ]
    return q
