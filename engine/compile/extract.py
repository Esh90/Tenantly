"""Extraction (PLAN.md 11.5, 11.6, D12): two independent passes, deterministic verification,
field-level voting, adjudication of disagreements only.

Budget note (DATASET_NOTES.md): pass A is Sonnet over the (triaged) in-force sections; pass B is a
cheaper Haiku read of the whole in-force document, which also serves as the cross-check.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date

from engine import config
from engine.compile import dates
from engine.compile.context import DocView, cite_key
from engine.compile.llm import LLM
from engine.compile.tools import (
    EMIT_DECISION,
    EMIT_RULES,
    EMIT_TRIAGE,
    load_prompt,
)
from engine.compile.verify import verify_quote
from engine.ir import Citation, Exemption, KeyValue, Rule
from engine.rules import dsl

log = logging.getLogger("tenantly.extract")

TRIAGE_OVER_CHARS = 30_000
SKIP_TYPES = {"motion", "news"}
TIER_BY_TYPE = {
    "statute": "A", "ordinance": "A", "draft_materials": "B", "bill_status": "B",
    "guidance": "B", "policy": "B",
}  # fmt: skip
ACRONYM = re.compile(r"[^a-z0-9]+")


@dataclass
class Rejection:
    doc_id: str
    stage: str
    reason: str
    title: str
    quote: str = ""


@dataclass
class Candidate:
    """A verified record from one pass, before merging."""

    rule: Rule
    pass_name: str  # "A" | "B"
    raw: dict = field(default_factory=dict)


# ---- triage (only for long documents) ----


def triage_sections(llm: LLM, view: DocView, sections) -> set[str] | None:
    """Return the section ids to keep, or None to keep the whole document."""
    if view.doc.chars <= TRIAGE_OVER_CHARS:
        return None
    system, version = load_prompt("triage")
    lines = []
    for s in sections:
        body = view.doc.text[s.char_start : s.char_end]
        lines.append(f"[{s.section_id}] {s.heading}\n{body[:350].strip()}")
    user = view.wrapper("\n\n".join(lines))
    res = llm.call(stage="triage", model=config.MODEL_FAST, system=system, user=user,
                   tool=EMIT_TRIAGE, prompt_version=version, ref=view.doc.doc_id, max_tokens=12000)  # fmt: skip
    keep = {s["section_id"] for s in res.output.get("sections", []) if s.get("keep")}
    # refs pull in the sections a kept section depends on
    for s in res.output.get("sections", []):
        if s.get("keep"):
            keep.update(s.get("refs") or [])
    valid = {s.section_id for s in sections}
    keep &= valid
    return keep or None


def text_for_pass_a(view: DocView, sections, keep: set[str] | None) -> str:
    if keep is None:
        return view.model_text()
    kept_ranges = [(s.char_start, s.char_end) for s in sections if s.section_id in keep]
    parts = []
    for ln in view.masked.kept_lines():
        in_span = any(a <= ln.start < b for a, b in view.spans)
        if in_span and any(a <= ln.start < b for a, b in kept_ranges):
            parts.append(ln.text)
    return "\n".join(parts)


# ---- the model passes ----


def run_pass(llm: LLM, view: DocView, text: str, pass_name: str) -> list[dict]:
    system, version = load_prompt("extract")
    model = config.MODEL_STRONG if pass_name == "A" else config.MODEL_FAST
    user = view.wrapper(text)
    if view.doc_type == "bill_status":
        user += (
            "\n\nThis document is a legislative bill status page, not statute text. Report the bill itself "
            "as ONE rule record: category = the category its title concerns, quote = the bill title sentence "
            'copied exactly, cite = the bill number (for example H.5222), coverage = {"const": true}, and '
            "lifecycle from its history."
        )
    res = llm.call(
        stage=f"extract_{pass_name.lower()}", model=model, system=system, user=user,
        tool=EMIT_RULES, prompt_version=version, ref=view.doc.doc_id, max_tokens=32000,
        effort="low",
    )  # fmt: skip
    return list(res.output.get("rules", []))


# ---- deterministic finalization ----


def _parse_kv_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def finalize(view: DocView, rec: dict, pass_name: str) -> Rule | Rejection:
    """Verify one model record and convert it to a Rule, or explain the rejection."""
    doc = view.doc
    title = str(rec.get("title", ""))[:120]
    span = verify_quote(doc.text, str(rec.get("quote", "")), view.spans)
    if span is None:
        return Rejection(
            doc.doc_id, pass_name, "QUOTE_NOT_FOUND", title, str(rec.get("quote", ""))[:200]
        )
    tier = TIER_BY_TYPE.get(view.doc_type)
    if tier is None or view.doc_type in SKIP_TYPES:
        return Rejection(doc.doc_id, pass_name, f"DOC_TYPE_{view.doc_type}", title)

    review = False
    notes: list[str] = []
    coverage = rec.get("coverage") or {"const": True}
    errs = dsl.validate(coverage)
    if errs:
        coverage, review = {"const": True}, True
        notes.append(f"coverage rejected by the DSL validator: {errs[0]}")
    exemptions: list[Exemption] = []
    dropped: list[str] = []
    for ex in rec.get("exemptions") or []:
        pe = dsl.validate(ex.get("predicate") or {})
        if pe:
            dropped.append(str(ex.get("description", "")))
            review = True
            continue
        q = ex.get("quote")
        eq = verify_quote(doc.text, q, view.spans) if q else None
        predicate = ex["predicate"]
        if predicate == {"const": True}:
            # "an exemption exists but the facts cannot express it": unknown, never TRUE for everyone
            predicate = {"const": "unknown"}
            notes.append(f"exemption not expressible: {str(ex.get('description', ''))[:80]}")
        exemptions.append(
            Exemption(
                description=str(ex.get("description", "")),
                predicate=predicate,
                quote=eq.text if eq else None,
            )  # fmt: skip
        )
    kvs = []
    for kv in rec.get("key_values") or []:
        kvs.append(
            KeyValue(
                name=str(kv.get("name", ""))[:80], text=str(kv.get("text", "")),
                value=kv.get("value"), unit=kv.get("unit"),
                valid_from=_parse_kv_date(kv.get("valid_from")),
                valid_to=_parse_kv_date(kv.get("valid_to")), source_doc_id=doc.doc_id,
            )
        )  # fmt: skip
    effective, sunset = dates.resolve_dates(view, rec)
    lifecycle = dates.lifecycle_for(view, rec.get("lifecycle"))
    cite = Citation(
        doc_id=doc.doc_id, cite=str(rec.get("cite", "")).strip() or view.doc.doc_id, url=doc.url,
        retrieved_at=doc.retrieved_at, quote=span.text, char_start=span.start, char_end=span.end,
        doc_sha256=doc.sha256, tier=tier, quote_source="corpus", version_label=view.version_label,
        low_signal=view.low_signal,
    )  # fmt: skip
    ex_text = "; ".join(e.description for e in exemptions) or None
    if dropped:
        ex_text = ((ex_text + "; ") if ex_text else "") + "unparsed: " + "; ".join(dropped)
    rule = Rule(
        rule_id=f"tmp-{doc.doc_id}-{cite_key(cite.cite)}-{rec.get('category')}",
        category=rec["category"], jurisdiction=view.jurisdiction, title=title or cite.cite,
        requirement=str(rec.get("requirement", "")), key_values=kvs, coverage=coverage,
        coverage_text=str(rec.get("coverage_text", "")), exemptions=exemptions,
        exemptions_text=ex_text, tenancy_conditions=[str(t) for t in rec.get("tenancy_conditions") or []],
        lifecycle=lifecycle, effective=effective, sunset=sunset, penalty=rec.get("penalty"),
        citation=cite, doc_type=view.doc_type, review_flag=review,
        provenance={"pass": pass_name, "notes": notes, "uncertain_fields": rec.get("uncertain_fields") or [],
                    "model_lifecycle": rec.get("lifecycle"), "relations_hint": rec.get("relations_hint") or []},
    )  # fmt: skip
    return rule


def finalize_all(view: DocView, raw: list[dict], pass_name: str):
    ok: list[Candidate] = []
    rej: list[Rejection] = []
    for rec in raw:
        if not isinstance(rec, dict):
            rej.append(Rejection(view.doc.doc_id, pass_name, "MALFORMED", str(rec)[:80]))
            continue
        if rec.get("category") not in dsl_categories():
            rej.append(
                Rejection(view.doc.doc_id, pass_name, "BAD_CATEGORY", str(rec.get("title", "")))
            )
            continue
        try:
            out = finalize(view, rec, pass_name)
        except (KeyError, TypeError, ValueError) as exc:
            out = Rejection(
                view.doc.doc_id,
                pass_name,
                f"MALFORMED_{type(exc).__name__}",
                str(rec.get("title", "")),
            )
        if isinstance(out, Rejection):
            rej.append(out)
        else:
            ok.append(Candidate(out, pass_name, rec))
    return ok, rej


def dsl_categories() -> set[str]:
    from engine.models import CATEGORIES

    return set(CATEGORIES)


# ---- merging and voting ----


def key_of(r: Rule) -> tuple[str, str, str]:
    return (r.jurisdiction.id, r.category, cite_key(r.citation.cite))


def _canon(d: dict) -> str:
    return json.dumps(dsl.to_dict(dsl.parse(d)), sort_keys=True)


def _digits(s: str) -> str:
    return ",".join(re.findall(r"\d+(?:\.\d+)?", s))


def disagreements(a: Rule, b: Rule) -> list[str]:
    out = []
    if _canon(a.coverage) != _canon(b.coverage):
        out.append("coverage")
    if (
        a.key_values
        and b.key_values
        and _digits(a.key_values[0].text) != _digits(b.key_values[0].text)
    ):
        out.append("key_value")
    return out


def adjudicate(llm: LLM, view: DocView, a: Rule, b: Rule, field_name: str) -> tuple[Rule, bool]:
    """Pick A or B for one field. Returns (winner, determined)."""
    system, version = load_prompt("adjudicate")
    if field_name == "coverage":
        opt_a, opt_b = (
            json.dumps(dsl.to_dict(dsl.parse(a.coverage))),
            json.dumps(dsl.to_dict(dsl.parse(b.coverage))),
        )
        coverage_text = f"A: {a.coverage_text}\nB: {b.coverage_text}"
    else:
        opt_a, opt_b = a.key_values[0].text, b.key_values[0].text
        coverage_text = ""
    q = a.citation.quote
    pos = view.doc.text.find(q)
    ctx = (
        view.doc.text[max(0, pos - 2500) : pos + len(q) + 2500]
        if pos >= 0
        else view.model_text()[:6000]
    )
    user = (
        f"Field: {field_name}\nRule: {a.title} ({a.citation.cite})\n"
        f"Option A: {opt_a}\nOption B: {opt_b}\n{coverage_text}\n\n" + view.wrapper(ctx)
    )
    res = llm.call(stage="adjudicate", model=config.MODEL_JUDGE, system=system, user=user,
                   tool=EMIT_DECISION, prompt_version=version, ref=f"{view.doc.doc_id}:{field_name}",
                   max_tokens=2000)  # fmt: skip
    out = res.output
    evidence_ok = bool(out.get("evidence_quote")) and verify_quote(
        view.doc.text, out["evidence_quote"], view.spans
    )
    if out.get("undetermined") or not evidence_ok:
        return a, False
    return (a if str(out.get("choice", "")).strip().upper().startswith("A") else b), True


def merge_passes(
    llm: LLM, view: DocView, cand_a: list[Candidate], cand_b: list[Candidate]
) -> list[Rule]:
    by_a: dict[tuple, Candidate] = {}
    for c in cand_a:
        by_a.setdefault(key_of(c.rule), c)
    by_b: dict[tuple, Candidate] = {}
    for c in cand_b:
        by_b.setdefault(key_of(c.rule), c)
    merged: list[Rule] = []
    for key in sorted(set(by_a) | set(by_b)):
        ca, cb = by_a.get(key), by_b.get(key)
        votes: dict = {}
        adjudicated: list[str] = []
        undetermined = False
        if ca and cb:
            chosen = ca.rule
            diffs = disagreements(ca.rule, cb.rule)
            votes = {"cite": "agree", "coverage": "agree", "key_value": "agree"}
            for f in diffs:
                winner, determined = adjudicate(llm, view, ca.rule, cb.rule, f)
                votes[f] = "adjudicated" if determined else "undetermined"
                adjudicated.append(f)
                undetermined |= not determined
                if f == "coverage":
                    chosen = chosen.model_copy(update={"coverage": winner.coverage,
                                                       "coverage_text": winner.coverage_text})  # fmt: skip
                else:
                    chosen = chosen.model_copy(update={"key_values": winner.key_values})
            rule = chosen
            conf_delta = 0.05 if not diffs else -0.15 * len(diffs) - (0.25 if undetermined else 0)
        elif ca:
            rule, votes, conf_delta = ca.rule, {"pass": "A only"}, 0.0
        else:
            rule, votes, conf_delta = cb.rule, {"pass": "B only"}, -0.1  # type: ignore[union-attr]
        prov = dict(rule.provenance)
        prov.update({"votes": votes, "adjudicated_fields": adjudicated, "conf_delta": conf_delta,
                     "passes": [p for p, c in (("A", ca), ("B", cb)) if c]})  # fmt: skip
        merged.append(rule.model_copy(update={"provenance": prov, "votes": votes,
                                              "review_flag": rule.review_flag or undetermined}))  # fmt: skip
    return merged


# ---- driver for one document ----


def compile_document(llm: LLM, view: DocView, sections) -> tuple[list[Rule], list[Rejection]]:
    if view.doc_type in SKIP_TYPES:
        return [], []
    keep = triage_sections(llm, view, sections)
    text_a = text_for_pass_a(view, sections, keep)
    text_b = view.model_text()
    raw_a = run_pass(llm, view, text_a, "A")
    raw_b = run_pass(llm, view, text_b, "B")
    ok_a, rej_a = finalize_all(view, raw_a, "A")
    ok_b, rej_b = finalize_all(view, raw_b, "B")
    rules = merge_passes(llm, view, ok_a, ok_b)
    return rules, rej_a + rej_b
