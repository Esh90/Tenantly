"""Deterministic EN/ES text (PLAN.md 14.5). No model is involved at lookup time.

Every function returns a ``{"en": ..., "es": ...}`` pair unless noted. Wording describes the
law and the facts; it never advises and never suggests ways around a rule.
"""

from __future__ import annotations

from datetime import date

from engine.rules import dsl

MONTHS_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
    "octubre", "noviembre", "diciembre",
]  # fmt: skip

CATEGORY_LABELS = {
    "rent_increase_limits": ("Rent increase limits", "Límites a los aumentos de renta"),
    "just_cause_eviction": ("Just-cause eviction", "Desalojo con causa justa"),
    "security_deposits": ("Security deposits", "Depósitos de seguridad"),
    "application_screening_fees": (
        "Application and screening fees", "Cuotas de solicitud y evaluación",
    ),
    "screening_restrictions": ("Screening restrictions", "Restricciones de evaluación"),
    "algorithmic_rent_setting": ("Algorithmic rent setting", "Fijación algorítmica de rentas"),
}  # fmt: skip

# the noun phrase used in "Your {category} are limited by ..."
CATEGORY_PHRASE = {
    "rent_increase_limits": ("rent increases", "los aumentos de renta"),
    "just_cause_eviction": ("evictions", "los desalojos"),
    "security_deposits": ("security deposit", "el depósito de seguridad"),
    "application_screening_fees": ("application fees", "las cuotas de solicitud"),
    "screening_restrictions": ("tenant screening", "la evaluación de inquilinos"),
    "algorithmic_rent_setting": ("rent-setting software", "el software para fijar rentas"),
}  # fmt: skip

STATE_NAMES = {"CA": "California", "NJ": "New Jersey", "MA": "Massachusetts"}


def bi(en: str, es: str) -> dict[str, str]:
    return {"en": en, "es": es}


def date_long(d: date) -> dict[str, str]:
    return bi(
        f"{d.strftime('%B')} {d.day}, {d.year}", f"{d.day} de {MONTHS_ES[d.month - 1]} de {d.year}"
    )


def fact_label(fact: str) -> dict[str, str]:
    spec = dsl.FACTS.get(fact)
    if spec is None:
        return bi(fact.replace("_", " "), fact.replace("_", " "))
    return bi(
        spec.label_en[0].lower() + spec.label_en[1:], spec.label_es[0].lower() + spec.label_es[1:]
    )


def missing_fact_label(fact: str) -> dict[str, str]:
    """Label for a fact in 'It depends on ...' sentences. Derived facts name what they derive from."""
    if fact in ("co_date", "building_age_years"):
        return bi("the year the building was built", "el año en que se construyó el edificio")
    if fact == "location":
        return bi("where the address is on the map", "dónde queda la dirección en el mapa")
    return fact_label(fact)


def join_en(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def join_es(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " y " + items[-1]


# ---- 14.5 templates ----


def mailing_mismatch(mailing_city: str, legal_city: str) -> dict[str, str]:
    return bi(
        f"Mailed as {mailing_city}. Legally inside {legal_city}.",
        f"Enviado como {mailing_city}. Legalmente dentro de {legal_city}.",
    )


def applies_headline(category: str, title_short: str) -> dict[str, str]:
    en, es = CATEGORY_PHRASE[category]
    return bi(
        f"Your {en} are limited by {title_short}.",
        f"{es.capitalize()} están limitados por {title_short}.",
    )


def unknown_headline(missing: list[str]) -> dict[str, str]:
    en = join_en([missing_fact_label(m)["en"] for m in missing])
    es = join_es([missing_fact_label(m)["es"] for m in missing])
    return bi(f"We can't tell yet. It depends on {en}.", f"Todavía no lo sabemos. Depende de {es}.")


def barred_headline(state: str) -> dict[str, str]:
    name = STATE_NAMES.get(state, state)
    return bi(
        f"No local rent cap here. {name} law bars cities from adopting one.",
        f"No hay límite local de renta aquí. La ley de {name} impide que las ciudades lo adopten.",
    )


def not_yet_headline(d: date) -> dict[str, str]:
    dl = date_long(d)
    return bi(f"Starts {dl['en']}.", f"Comienza el {dl['es']}.")


def pending_headline() -> dict[str, str]:
    return bi(
        "Proposed, not law. It would cover this building if passed.",
        "Propuesta, no es ley. Cubriría este edificio si se aprueba.",
    )


def failed_note(title: str, reason: str | None) -> dict[str, str]:
    return bi(
        f"Not law: {title} {reason or 'did not become law'}.",
        f"No es ley: {title} {'no llegó a ser ley' if not reason else reason}.",
    )


def projection_note() -> dict[str, str]:
    return bi(
        "Based on sources retrieved October 1, 2026. Laws may have changed since.",
        "Basado en fuentes consultadas el 1 de octubre de 2026. Las leyes pueden haber cambiado.",
    )


def nothing_found_headline() -> dict[str, str]:
    return bi(
        "No rule found in our sources for this category.",
        "No encontramos una regla en nuestras fuentes para esta categoría.",
    )


def finding_headline(reason_code: str, state: str) -> dict[str, str]:
    if reason_code == "barred_by_state":
        return barred_headline(state)
    return nothing_found_headline()


def conflict_explanation(
    kind: str, other_id: str | None, active_from: date | None
) -> dict[str, str]:
    if kind == "barred_by_state":
        return bi(
            "State law bars this kind of local rule. Flagged for human review.",
            "La ley estatal impide este tipo de regla local. Señalado para revisión humana.",
        )
    when = date_long(active_from) if active_from else None
    other = other_id or "another rule"
    return bi(
        f"{other} may conflict with this rule (possible preemption)"
        + (f" from {when['en']}" if when else "")
        + ". Flagged for human review.",
        f"{other} podría entrar en conflicto con esta regla (posible prevalencia de otra norma)"
        + (f" desde el {when['es']}" if when else "")
        + ". Señalado para revisión humana.",
    )


# ---- key-value staleness (PLAN.md D15) ----


def stale_note(
    text: str, valid_from: date | None, valid_to: date | None, d: date
) -> dict[str, str]:
    if valid_to is not None and valid_to < d:
        dl = date_long(valid_to)
        return bi(
            f"The figure for this date is not in our sources (last published: {text} through {dl['en']}).",
            f"La cifra para esta fecha no está en nuestras fuentes (última publicada: {text} hasta el {dl['es']}).",
        )
    dl = date_long(valid_from) if valid_from else date_long(d)
    return bi(
        f"This figure is published from {dl['en']} ({text}).",
        f"Esta cifra se publica desde el {dl['es']} ({text}).",
    )


# ---- reasoning boundary ----


def reasoning_boundary(
    n_docs: int, retrieved: str, facts_source: str, location_known: bool
) -> dict[str, list[dict[str, str]]]:
    checked = [
        bi(
            f"Rules quoted from {n_docs} public legal documents retrieved on {retrieved}.",
            f"Reglas citadas de {n_docs} documentos legales públicos consultados el {retrieved}.",
        ),
        bi(
            "Which city and state the address is legally in, by map boundary, not by mailing name.",
            "En qué ciudad y estado queda legalmente la dirección, por límites del mapa y no por el nombre postal.",
        ),
        bi(
            "Building size and year built from the public assessor record"
            if facts_source == "data"
            else "Building facts you provided, with public records for the rest.",
            "Tamaño y año de construcción del registro público del asesor"
            if facts_source == "data"
            else "Datos del edificio que usted indicó y registros públicos para el resto.",
        ),
    ]
    not_checked = [
        bi(
            "Facts that are not in public records, such as who owns the building, unless you tell us.",
            "Datos que no están en registros públicos, como quién es el dueño, a menos que usted los indique.",
        ),
        bi(
            "Court decisions, agency guidance and your lease terms.",
            "Decisiones judiciales, guías de agencias y los términos de su contrato.",
        ),
        bi(
            "Local laws in cities outside our ten, and laws whose text we could not retrieve.",
            "Leyes locales de ciudades fuera de nuestras diez y leyes cuyo texto no pudimos obtener.",
        ),
    ]
    if not location_known:
        not_checked.insert(
            0,
            bi(
                "City laws: this address could not be placed on the map.",
                "Leyes de la ciudad: no pudimos ubicar esta dirección en el mapa.",
            ),
        )
    assumptions = [
        bi(
            "A certificate of occupancy is assumed to fall in the year the building was built.",
            "Se supone que el certificado de ocupación corresponde al año de construcción.",
        ),
        bi(
            "Dates after October 1, 2026 are projections from the sources we retrieved.",
            "Las fechas posteriores al 1 de octubre de 2026 son proyecciones a partir de las fuentes consultadas.",
        ),
    ]
    return {"checked": checked, "not_checked": not_checked, "assumptions": assumptions}
