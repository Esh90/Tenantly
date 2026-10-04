"""One deterministic sentence per result (PLAN.md 12.3), in English and Spanish.

The sentence names the deciding facts and the precedence that applies. Examples:
"Covered: built in 1926; the state rule CA-RENT-01 yields to it (local law over state law)."
"Unknown: the year the building was built is not in the public record."
"""

from __future__ import annotations

from datetime import date

from engine.facts.intervals import Tri
from engine.rules import templates as T
from engine.rules.engine import Outcome


def _actual(item) -> tuple[str, str] | None:
    """A short human phrase for a true condition, or None to skip it."""
    if item.result != Tri.TRUE or item.actual is None:
        return None
    if item.fact == "co_date":
        years = {p[:4] for p in item.actual.replace("between ", "").replace(" and ", " ").split()}
        years = {y for y in years if y.isdigit()}
        if len(years) == 1:
            y = next(iter(years))
            return (f"built in {y}", f"construido en {y}")
    return (
        f"{item.label_en.lower()[0] + item.label_en[1:]}",
        f"{item.label_es[0].lower() + item.label_es[1:]}",
    )


def _facts_phrase(o: Outcome) -> tuple[str, str]:
    seen: set[str] = set()
    en: list[str] = []
    es: list[str] = []
    for item in o.trace:
        got = _actual(item)
        if got and got[0] not in seen:
            seen.add(got[0])
            en.append(got[0])
            es.append(got[1])
    if not en:
        j = o.rule.jurisdiction.label
        return (
            f"applies to residential rentals in {j}",
            f"se aplica a viviendas en alquiler en {j}",
        )
    return (T.join_en(en), T.join_es(es))


def _missing_phrase(o: Outcome) -> tuple[str, str]:
    en = [T.missing_fact_label(f)["en"] for f in o.missing_facts]
    es = [T.missing_fact_label(f)["es"] for f in o.missing_facts]
    # derived facts collapse to one label
    en = list(dict.fromkeys(en))
    es = list(dict.fromkeys(es))
    return T.join_en(en), T.join_es(es)


def explain(o: Outcome, d: date, rule_titles: dict[str, str] | None = None) -> dict[str, str]:
    titles = rule_titles or {}
    flag_en = flag_es = ""
    for c in o.conflicts:
        if c.kind == "possible_preemption" and c.with_rule_id:
            when = T.date_long(c.active_from) if c.active_from else None
            flag_en += (
                f" Flagged for review: {c.with_rule_id} may conflict with this rule (possible preemption)"
                + (f" from {when['en']}." if when else ".")
            )
            flag_es += (
                f" Señalado para revisión: {c.with_rule_id} podría entrar en conflicto con esta regla (posible preferencia federal o estatal)"
                + (f" desde el {when['es']}." if when else ".")
            )
        elif c.kind == "barred_by_state":
            flag_en += " Flagged for review: state law bars this kind of local rule."
            flag_es += " Señalado para revisión: la ley estatal impide este tipo de regla local."

    if o.result == "superseded":
        gov = o.superseded_by
        gt = titles.get(gov or "", gov)
        if "superseded_by_stricter_rule" in o.notes:
            return T.bi(
                f"Superseded: {gov} ({gt}) sets a lower cap and governs here, so this rule yields to it.",
                f"Reemplazada: {gov} ({gt}) fija un límite menor y rige aquí; esta regla cede ante ella.",
            )
        return T.bi(
            f"Superseded: {gov} ({gt}) governs here; local law takes precedence over state law.{flag_en}",
            f"Reemplazada: {gov} ({gt}) rige aquí; la ley local tiene prioridad sobre la ley estatal.{flag_es}",
        )
    if o.result == "applies":
        en, es = _facts_phrase(o)
        extra_en = extra_es = ""
        if o.governs_over:
            ids = ", ".join(o.governs_over)
            extra_en = f" It governs over {ids} (local law over state law)."
            extra_es = f" Rige sobre {ids} (la ley local sobre la estatal)."
        if o.caveats:
            extra_en += f" An exemption could apply if: {'; '.join(o.caveats)}."
            extra_es += f" Podría aplicar una exención si: {'; '.join(o.caveats)}."
        return T.bi(f"Covered: {en}.{extra_en}{flag_en}", f"Cubierto: {es}.{extra_es}{flag_es}")
    if o.result == "unknown":
        if "location_unknown" in o.notes:
            return T.bi(
                "Unknown: this address could not be placed on the map, so city rules cannot be checked.",
                "Desconocido: no pudimos ubicar esta dirección en el mapa, así que no se pueden revisar las reglas de la ciudad.",
            )
        parts_en, parts_es = [], []
        if o.missing_facts:
            men, mes = _missing_phrase(o)
            parts_en.append(
                f"{men} is not in the public record"
                if len(o.missing_facts) == 1 or " and " not in men
                else f"{men} are not in the public record"
            )
            parts_es.append(f"{mes} no figura en el registro público")
        sup = [n.split(":", 1)[1] for n in o.notes if n.startswith("may_be_superseded_by:")]
        if sup:
            parts_en.append(f"it may be superseded by {sup[0]}")
            parts_es.append(f"podría ser reemplazada por {sup[0]}")
        if o.effective_uncertain:
            parts_en.append("the effective date is uncertain on this day")
            parts_es.append("la fecha de entrada en vigor es incierta en este día")
        if not parts_en:
            parts_en, parts_es = (
                ["the sources do not settle whether it covers this building"],
                ["las fuentes no aclaran si cubre este edificio"],
            )
        return T.bi(
            f"Unknown: {'; '.join(parts_en)}.{flag_en}",
            f"Desconocido: {'; '.join(parts_es)}.{flag_es}",
        )
    if o.result == "not_yet_effective":
        eff = o.rule.effective.lo
        when = T.date_long(eff) if eff else None
        tail_en = " Coverage of this building is not settled." if o.would_be == "unknown" else ""
        tail_es = (
            " La cobertura de este edificio no está definida." if o.would_be == "unknown" else ""
        )
        if when:
            return T.bi(
                f"Not yet in effect: starts {when['en']}.{tail_en}{flag_en}",
                f"Aún no está vigente: comienza el {when['es']}.{tail_es}{flag_es}",
            )
        return T.bi("Not yet in effect.", "Aún no está vigente.")
    if o.result == "pending":
        reach = o.would_reach
        return T.bi(
            "Pending: a proposed bill, not law. It "
            + ("would" if reach else "would not")
            + " reach this building if passed.",
            "Pendiente: un proyecto de ley, no es ley. "
            + ("Cubriría" if reach else "No cubriría")
            + " este edificio si se aprueba.",
        )
    return T.bi("", "")
