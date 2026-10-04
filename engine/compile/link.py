"""Precedence linker (PLAN.md 8.6): relations between rules, only where the text states them.

The model proposes; code verifies the evidence quote byte-for-byte, checks rule ids, validates
conditions, and computes ``active_from`` from the source rule's own effective date.
"""

from __future__ import annotations

import logging
import re

from engine import config
from engine.compile.context import DocView
from engine.compile.llm import LLM
from engine.compile.tools import EMIT_RELATIONS, load_prompt
from engine.compile.verify import verify_quote
from engine.ir import Citation, Relation, Rule
from engine.rules import dsl

log = logging.getLogger("tenantly.link")

PASSAGE = re.compile(
    r"local|municipal|ordinance|city or town|rent control|supersed|preempt|conflict|prohibited from enacting|"
    r"more protective|governed by|shall not apply",
    re.I,
)
MAX_PASSAGE_CHARS = 14_000
EFFECT_FOR = {
    "yields_to": "supersede",
    "preempts": "bar",
    "bars": "bar",
    "conflicts_with": "conflict_flag",
}


def passages(view: DocView) -> str:
    lines = view.model_text().split("\n")
    keep: set[int] = set()
    for i, ln in enumerate(lines):
        if PASSAGE.search(ln):
            keep.update({max(0, i - 1), i, min(len(lines) - 1, i + 1)})
    text = "\n".join(lines[i] for i in sorted(keep))
    return text[:MAX_PASSAGE_CHARS]


def link_state(llm: LLM, state: str, rules: list[Rule], views: dict[str, DocView]) -> list[dict]:
    """One model call for a state: its rules plus the interaction passages of its law documents."""
    mine = [r for r in rules if r.jurisdiction.state == state and r.lifecycle != "failed"]
    if len(mine) < 2:
        return []
    listing = "\n".join(
        f"{r.rule_id} | {r.jurisdiction.label} | {r.jurisdiction.level} | {r.category} | {r.title} | "
        f"{r.citation.quote[:160]!r}"
        for r in mine
    )
    docs = sorted({r.citation.doc_id for r in mine if r.citation.doc_id in views})
    blocks = []
    for d in docs:
        v = views[d]
        if v.doc_type in ("statute", "ordinance", "guidance", "draft_materials"):
            p = passages(v)
            if p.strip():
                blocks.append(v.wrapper(p))
    system, version = load_prompt("link")
    user = f"State: {state}\n\nCompiled rules:\n{listing}\n\nPassages:\n" + "\n\n".join(blocks)
    res = llm.call(stage="link", model=config.MODEL_STRONG, system=system, user=user, tool=EMIT_RELATIONS,
                   prompt_version=version, ref=state, max_tokens=8000, effort="low")  # fmt: skip
    return list(res.output.get("relations", []))


def verify_relations(
    raw: list[dict], rules: list[Rule], views: dict[str, DocView]
) -> tuple[list[Relation], list[dict]]:
    by_id = {r.rule_id: r for r in rules}
    ok: list[Relation] = []
    rejected: list[dict] = []
    seen: set[tuple] = set()
    for rec in raw:
        why = None
        view = views.get(rec.get("doc_id", ""))
        src = by_id.get(rec.get("source_rule_id", ""))
        if src is None:
            why = "unknown source rule id"
        elif rec.get("target_rule_id") and rec["target_rule_id"] not in by_id:
            why = "unknown target rule id"
        elif not rec.get("target_rule_id") and not rec.get("target_scope"):
            why = "no target"
        elif view is None:
            why = "unknown evidence document"
        else:
            span = verify_quote(view.doc.text, rec.get("quote", ""), view.spans)
            if span is None:
                why = "QUOTE_NOT_FOUND"
            elif rec.get("condition") and dsl.validate(rec["condition"]):
                why = "invalid condition"
        effect = EFFECT_FOR.get(rec.get("type", ""), rec.get("effect"))
        if why is None and effect != rec.get("effect") and rec.get("type") in EFFECT_FOR:
            why = "effect does not match relation type"
        if why:
            rejected.append({**rec, "reason": why})
            continue
        key = (
            rec["type"],
            rec["source_rule_id"],
            rec.get("target_rule_id"),
            str(rec.get("target_scope")),
        )
        if key in seen:
            continue
        seen.add(key)
        ev = Citation(
            doc_id=view.doc.doc_id, cite=src.citation.cite, url=view.doc.url, retrieved_at=view.doc.retrieved_at,  # type: ignore[union-attr]
            quote=span.text, char_start=span.start, char_end=span.end, doc_sha256=view.doc.sha256,  # type: ignore[union-attr]
            tier=src.citation.tier, quote_source="corpus", version_label=view.version_label, low_signal=view.low_signal,
        )  # fmt: skip
        active = src.effective.lo if effect == "conflict_flag" else None
        ok.append(
            Relation(
                relation_id="", type=rec["type"], source_rule_id=rec["source_rule_id"],
                target_rule_id=rec.get("target_rule_id"), target_scope=rec.get("target_scope"),
                condition=rec.get("condition"), evidence=ev, effect=effect, active_from=active,
            )
        )  # fmt: skip
    ok.sort(key=lambda r: (r.source_rule_id, r.type, r.target_rule_id or "", str(r.target_scope)))
    ok = [r.model_copy(update={"relation_id": f"REL-{i:03d}"}) for i, r in enumerate(ok, start=1)]
    return ok, rejected
