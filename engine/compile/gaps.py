"""Negative-space audit (PLAN.md D14): every jurisdiction x category cell ends with a verified
rule or a reasoned "no rule at this level" finding."""

from __future__ import annotations

import logging

from engine import config
from engine.compile.context import DocView, jurisdiction_for
from engine.compile.llm import LLM
from engine.compile.tools import EMIT_GAP, load_prompt
from engine.compile.verify import verify_quote
from engine.corpus.loader import LinkOnlyDoc
from engine.geo.jurisdictions import CITIES, STATES
from engine.ir import Citation, Finding, Relation, Rule
from engine.models import CATEGORIES
from engine.rules import templates as T

log = logging.getLogger("tenantly.gaps")


def all_jurisdiction_labels() -> list[str]:
    return list(STATES) + [c.label for c in CITIES]


def finding_text(reason: str, jurisdiction_label: str, category: str, state: str) -> dict[str, str]:
    cat_en, cat_es = T.CATEGORY_LABELS[category]
    if reason == "barred_by_state":
        return T.barred_headline(state)
    en = {
        "motion_only": f"Only a council motion exists for {jurisdiction_label}; a motion is not law.",
        "only_pending": f"Only a pending bill exists for {jurisdiction_label}; it is not law yet.",
        "failed_measure": f"The only measure for {jurisdiction_label} did not become law.",
        "text_not_supplied": f"A law may exist for {jurisdiction_label}, but its text was not supplied.",
        "none_in_sources": f"No {cat_en.lower()} rule for {jurisdiction_label} appears in our sources.",
    }[reason]
    es = {
        "motion_only": f"Solo existe una moción del concejo para {jurisdiction_label}; una moción no es ley.",
        "only_pending": f"Solo existe un proyecto de ley pendiente para {jurisdiction_label}; todavía no es ley.",
        "failed_measure": f"La única medida para {jurisdiction_label} no llegó a ser ley.",
        "text_not_supplied": f"Puede existir una ley para {jurisdiction_label}, pero no se proporcionó su texto.",
        "none_in_sources": f"No aparece en nuestras fuentes una regla de {cat_es.lower()} para {jurisdiction_label}.",
    }[reason]
    return T.bi(en, es)


def audit_gaps(
    llm: LLM,
    rules: list[Rule],
    relations: list[Relation],
    views: dict[str, DocView],
    links: list[LinkOnlyDoc],
) -> tuple[list[Finding], list[dict]]:
    system, version = load_prompt("gap")
    findings: list[Finding] = []
    report: list[dict] = []
    for label in all_jurisdiction_labels():
        jur = jurisdiction_for(label)
        for cat in CATEGORIES:
            cell = [r for r in rules if r.jurisdiction.id == jur.id and r.category == cat]
            if any(r.lifecycle == "enacted" and r.citation.tier in ("A", "B", "C") for r in cell):
                continue
            ev: list[Citation] = []
            reason: str | None = None
            note = ""
            # a state bar that reaches this cell is a finding without a model call
            for rel in relations:
                if rel.effect != "bar" or jur.level != "city" or not rel.target_scope:
                    continue
                s = rel.target_scope
                if (
                    s.get("category") == cat
                    and s.get("state", jur.state) == jur.state
                    and s.get("level", "city") == "city"
                ):
                    reason, ev = "barred_by_state", [rel.evidence]
                    break
            if reason is None:
                pend = [r for r in cell if r.lifecycle == "pending"]
                fail = [r for r in cell if r.lifecycle == "failed"]
                if pend and not fail:
                    reason, ev = "only_pending", [r.citation for r in pend][:2]
                elif fail and not pend:
                    reason, ev = "failed_measure", [r.citation for r in fail][:2]
            if reason is None:
                reason, ev, note = _ask_model(llm, system, version, jur, cat, rules, views, links)
            findings.append(
                Finding(
                    finding_id=f"F-{jur.id}-{cat}",
                    jurisdiction=jur,
                    category=cat,
                    reason_code=reason,  # type: ignore[arg-type]
                    explanation=finding_text(reason, jur.label, cat, jur.state),
                    evidence=ev,
                    searched_doc_ids=sorted(
                        {d for d, v in views.items() if v.jurisdiction.id in (jur.id, jur.state)}
                    ),
                )
            )
            report.append(
                {"jurisdiction": jur.label, "category": cat, "reason": reason, "note": note}
            )
    return findings, report


def _ask_model(llm, system, version, jur, cat, rules, views, links):
    docs = [v for v in views.values() if v.jurisdiction.id == jur.id]
    motions = [v for v in docs if v.doc_type == "motion"]
    lines = [f"Jurisdiction: {jur.label}; category: {cat}; level: {jur.level}"]
    for v in docs:
        lines.append(
            f"- {v.doc.doc_id} ({v.doc_type}): {v.doc.text[v.doc.body_start :][:160].strip()!r}"
        )
    for r in rules:
        if r.jurisdiction.id in (jur.id, jur.state) and r.category == cat:
            lines.append(f"- rule in this category: {r.rule_id} {r.title} ({r.lifecycle})")
    for link in links:
        if link.jurisdictions in (jur.label, jur.state):
            lines.append(f"- link-only (no text): {link.doc_id} {link.url}")
    res = llm.call(stage="gap", model=config.MODEL_FAST, system=system, user="\n".join(lines),
                   tool=EMIT_GAP, prompt_version=version, ref=f"{jur.id}:{cat}", max_tokens=1500)  # fmt: skip
    out = res.output
    result = out.get("result", "none_in_sources")
    ev: list[Citation] = []
    note = out.get("explanation", "")
    if result == "found":
        return "none_in_sources", [], f"MODEL SUGGESTS A RULE EXISTS (review): {note}"
    if result == "motion_only":
        v = motions[0] if motions else None
        if v is None:
            result = "none_in_sources"
        else:
            q = verify_quote(v.doc.text, out.get("quote") or "I THEREFORE MOVE", v.spans)
            if q:
                ev = [Citation(doc_id=v.doc.doc_id, cite="Council motion", url=v.doc.url, retrieved_at=v.doc.retrieved_at,
                               quote=q.text, char_start=q.start, char_end=q.end, doc_sha256=v.doc.sha256, tier="B",
                               low_signal=v.low_signal)]  # fmt: skip
            else:
                result = "none_in_sources"
    if result == "text_not_supplied" and not [
        link for link in links if link.jurisdictions in (jur.label, jur.state)
    ]:
        result = "none_in_sources"
    if result in ("only_pending", "failed_measure", "barred_by_state") and not ev:
        result = "none_in_sources"  # unsupported by evidence we can verify
    return result, ev, note
