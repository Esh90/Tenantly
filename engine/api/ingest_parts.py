"""Building blocks of the ingestion flow: jurisdiction inference, deterministic validation,
jurisdiction hierarchy, knowledge graph and the autonomous Judge (PLAN.md D17).

Pure functions over real data. Nothing here invents a result: every check reads the staged rules,
the source text or the existing rule set, and every graph edge comes from a stored relation,
a rule field or a computed precedence.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from collections import Counter
from datetime import date

from engine import config
from engine.api.errors import ApiError
from engine.compile import calendar as cal
from engine.compile.context import DocView, cite_key
from engine.compile.llm import LLM
from engine.compile.tools import load_prompt
from engine.compile.verify import span_text_is_exact, verify_quote
from engine.export.build import rule_record
from engine.export.submission import validate_rules
from engine.geo.jurisdictions import CITIES, COUNTIES, STATES
from engine.ir import Relation, Rule, RuleSet
from engine.models import CATEGORIES
from engine.rules import dsl
from engine.rules import templates as T

MIN_CONFIDENCE_DEFAULT = 0.85

# ---------------------------------------------------------------- upload parsing


def extract_text(filename: str, data: bytes) -> dict:
    """Plain text from a TXT, PDF or DOCX upload. Raises ApiError for anything else."""
    name = (filename or "").lower()
    if len(data) > 10_000_000:
        raise ApiError("DOCUMENT_TOO_LARGE", "Uploads are limited to 10 MB.", {"bytes": len(data)})
    if name.endswith(".pdf") or data[:5] == b"%PDF-":
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        pages = [p.extract_text() or "" for p in reader.pages]
        return {"text": "\n\n".join(pages).strip(), "format": "pdf", "pages": len(pages)}
    if name.endswith(".docx") or data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        xml = re.sub(r"<w:tab/>", "\t", xml)
        text = re.sub(r"<[^>]+>", "", xml)
        for a, b in (
            ("&amp;", "&"),
            ("&lt;", "<"),
            ("&gt;", ">"),
            ("&quot;", '"'),
            ("&apos;", "'"),
        ):
            text = text.replace(a, b)
        return {"text": text.strip(), "format": "docx", "pages": None}
    if name.endswith((".txt", ".md", ".text")) or not name:
        return {"text": data.decode("utf-8", "replace").strip(), "format": "text", "pages": None}
    raise ApiError(
        "BAD_REQUEST", "Upload a PDF, DOCX or TXT file, or paste the text.", {"filename": filename}
    )


# ---------------------------------------------------------------- jurisdiction inference


def infer_jurisdiction(text: str) -> tuple[str | None, str]:
    """Pick the jurisdiction a document is about from how often it names one. Returns
    (label, explanation); label is None when the text does not settle it."""
    low = text.lower()
    scores: Counter = Counter()
    for c in CITIES:
        n = len(re.findall(rf"\b{re.escape(c.name.lower())}\b", low))
        if n:
            scores[c.label] += (
                n * 3 + len(re.findall(rf"city of {re.escape(c.name.lower())}", low)) * 3
            )
    for code, (_, name) in STATES.items():
        n = len(re.findall(rf"\b{re.escape(name.lower())}\b", low))
        if n:
            scores[code] += n
    if not scores:
        return None, "no covered city or state is named in the text"
    (top, s1), *rest = scores.most_common(2)
    if rest and rest[0][1] * 2 > s1 and rest[0][0] != top:
        return None, f"the text names {top} and {rest[0][0]} about equally"
    return (
        top,
        f"{top} is named {s1 // 3 if '(' not in top and ',' in top else s1} time(s) in the text",
    )


# ---------------------------------------------------------------- deterministic validation


def _check(cid: str, label: str, problems: list[str], detail_ok: str, warn: bool = False) -> dict:
    status = "pass" if not problems else ("warn" if warn else "fail")
    return {"id": cid, "label": label, "status": status,
            "detail": detail_ok if not problems else problems[0], "items": problems}  # fmt: skip


def validate_staged(
    view: DocView,
    new_rules: list[Rule],
    overlay: RuleSet,
    base: RuleSet,
    new_relations: list[Relation],
) -> dict:
    """Run every deterministic gate. ``passed`` is False if any check fails (warnings pass)."""
    checks: list[dict] = []
    all_ids = [r.rule_id for r in overlay.rules]

    # required fields
    missing = []
    for r in new_rules:
        for fld in ("title", "requirement", "coverage_text"):
            if not getattr(r, fld, "").strip():
                missing.append(f"{r.rule_id}: {fld} is empty")
        if len(r.citation.quote.strip()) < 20:
            missing.append(f"{r.rule_id}: quoted span is under 20 characters")
        if not r.citation.cite.strip():
            missing.append(f"{r.rule_id}: citation is empty")
    checks.append(
        _check(
            "required_fields",
            "Required fields present",
            missing,
            f"all {len(new_rules)} rules have title, requirement, coverage and a quote",
        )
    )

    # official schema
    errs: list[str] = []
    for r in new_rules:
        errs += validate_rules({"rules": [rule_record(r, overlay)]})
    checks.append(
        _check(
            "schema",
            "Valid against the official rule schema",
            errs,
            "every rule record validates (JSON Schema 2020-12)",
        )
    )

    # citations point to real source text
    bad_cites = []
    for r in new_rules:
        c = r.citation
        if c.quote_source == "corpus":
            if c.char_start is None or not span_text_is_exact(
                view.doc.text, c.char_start, c.char_end, c.quote
            ):
                bad_cites.append(f"{r.rule_id}: quote is not at its stored offsets in the source")
        elif verify_quote(view.doc.text, c.quote, [(0, len(view.doc.text))]) is None:
            bad_cites.append(f"{r.rule_id}: quote not found in the source text")
    checks.append(
        _check(
            "citations",
            "Citations verified byte for byte",
            bad_cites,
            f"{len(new_rules)} quotes found at their stored offsets in the source",
        )
    )

    # jurisdiction
    jur_problems = []
    valid_ids = {c.id for c in CITIES} | set(STATES)
    for r in new_rules:
        if r.jurisdiction.id not in valid_ids:
            jur_problems.append(f"{r.rule_id}: jurisdiction {r.jurisdiction.id} is not covered")
    checks.append(
        _check(
            "jurisdiction",
            "Jurisdiction resolved",
            jur_problems,
            f"resolved to {view.jurisdiction.label}",
        )
    )

    # dates
    date_problems = []
    for r in new_rules:
        e, s = r.effective, r.sunset
        for label, d in (("effective", e.lo), ("effective", e.hi), ("sunset", s.lo if s else None)):
            if d and not (1900 <= d.year <= 2100):
                date_problems.append(f"{r.rule_id}: {label} date {d} is implausible")
        if e.lo and e.hi and e.lo > e.hi:
            date_problems.append(f"{r.rule_id}: effective interval is reversed")
        if e.lo and s and s.lo and s.lo <= e.lo:
            date_problems.append(
                f"{r.rule_id}: sunset {s.lo} is not after the effective date {e.lo}"
            )
    undated = [r.rule_id for r in new_rules if r.lifecycle == "enacted" and r.effective.lo is None]
    checks.append(
        _check(
            "dates",
            "Dates valid and consistent",
            date_problems,
            "effective and sunset dates are plausible and in order",
        )
    )
    if undated:
        checks.append(
            _check(
                "dates_known",
                "Effective date found in the text",
                [
                    f"{i}: no effective date could be computed; it is treated as already in force"
                    for i in undated
                ],
                "",
                warn=True,
            )
        )

    # references
    ref_problems = []
    for rel in new_relations:
        for rid in (rel.source_rule_id, rel.target_rule_id):
            if rid and rid not in set(all_ids):
                ref_problems.append(f"relation {rel.relation_id} refers to unknown rule {rid}")
        if rel.evidence.char_start is not None and not span_text_is_exact(
            view.doc.text, rel.evidence.char_start, rel.evidence.char_end, rel.evidence.quote
        ):
            ref_problems.append(f"relation {rel.relation_id}: evidence quote is not in the source")
    checks.append(
        _check(
            "references",
            "References resolved",
            ref_problems,
            f"{len(new_relations)} relations point to existing rules with verified evidence",
        )
    )

    # unique ids
    dup_ids = [i for i, n in Counter(all_ids).items() if n > 1]
    checks.append(
        _check(
            "unique_ids",
            "No duplicate rule IDs",
            [f"duplicate id {i}" for i in dup_ids],
            f"{len(all_ids)} rule ids are unique",
        )
    )

    # duplicates of existing rules
    dups, supersedes = [], []
    for r in new_rules:
        for old in base.rules:
            if (old.jurisdiction.id, old.category, cite_key(old.citation.cite)) == (
                r.jurisdiction.id,
                r.category,
                cite_key(r.citation.cite),
            ):
                (dups if old.citation.quote == r.citation.quote else supersedes).append(
                    f"{r.rule_id} vs {old.rule_id}"
                )
    checks.append(
        _check(
            "duplicates",
            "No duplicate rules",
            [f"{x}: identical quote already in the live set" for x in dups],
            "no rule repeats a live rule",
        )
    )
    if supersedes:
        checks.append(
            _check(
                "supersedes",
                "Replaces earlier text of the same provision",
                [f"{x}: same provision, new text; the new rule supersedes it" for x in supersedes],
                "",
                warn=True,
            )
        )

    # coverage structure
    dsl_problems = []
    for r in new_rules:
        for label, pred in [("coverage", r.coverage)] + [
            (f"exemption '{e.description[:40]}'", e.predicate) for e in r.exemptions
        ]:
            for err in dsl.validate(pred):
                dsl_problems.append(f"{r.rule_id} {label}: {err}")
    checks.append(
        _check(
            "coverage_structure",
            "Coverage conditions well formed",
            dsl_problems,
            "every coverage and exemption predicate parses over the fact registry",
        )
    )

    # priority relationships possible
    prio = []
    for rel in new_relations:
        src = next((r for r in overlay.rules if r.rule_id == rel.source_rule_id), None)
        if src is None:
            continue
        if rel.effect == "bar" and src.jurisdiction.level != "state":
            prio.append(
                f"{rel.relation_id}: only a state rule can bar local rules ({src.rule_id} is {src.jurisdiction.level})"
            )
        if rel.target_rule_id == rel.source_rule_id:
            prio.append(f"{rel.relation_id}: a rule cannot relate to itself")
    checks.append(
        _check(
            "priority",
            "Priority relationships possible",
            prio,
            "no impossible precedence (state bars come from state rules; no self references)",
        )
    )

    passed = all(c["status"] != "fail" for c in checks)
    return {"passed": passed, "checks": checks}


# ---------------------------------------------------------------- hierarchy and graph


def _stack(jid: str) -> list[dict]:
    """State, county, city for a jurisdiction id, with priority 1 to 3."""
    if jid in STATES:
        return [{"level": "state", "id": jid, "label": STATES[jid][1], "priority": 1}]
    city = next(c for c in CITIES if c.id == jid)
    county = next((f, n) for f, n, s in COUNTIES if f == city.county_fips)
    return [
        {"level": "state", "id": city.state, "label": STATES[city.state][1], "priority": 1},
        {"level": "county", "id": f"{city.state}-{county[0]}", "label": county[1], "priority": 2},
        {"level": "city", "id": city.id, "label": city.name, "priority": 3},
    ]


def _scope_hit(scope: dict | None, r: Rule) -> bool:
    if not scope:
        return False
    j = r.jurisdiction
    return (scope.get("category", r.category) == r.category and scope.get("level", j.level) == j.level
            and scope.get("state", j.state) == j.state)  # fmt: skip


def related_relations(
    overlay: RuleSet, new_ids: set[str]
) -> list[tuple[Relation, Rule, list[Rule]]]:
    """(relation, source rule, targets) for every stored relation that touches a new rule."""
    by_id = {r.rule_id: r for r in overlay.rules}
    out = []
    for rel in overlay.relations:
        src = by_id.get(rel.source_rule_id)
        if src is None:
            continue
        if rel.target_rule_id:
            targets = [by_id[rel.target_rule_id]] if rel.target_rule_id in by_id else []
        else:
            targets = [
                r
                for r in overlay.rules
                if r.rule_id != src.rule_id and _scope_hit(rel.target_scope, r)
            ]
        if src.rule_id in new_ids or any(t.rule_id in new_ids for t in targets):
            out.append(
                (rel, src, [t for t in targets if t.rule_id in new_ids or src.rule_id in new_ids])
            )
    return out


def relation_sentence(rel: Relation, src: Rule, tgt: Rule) -> dict[str, str]:
    state = T.STATE_NAMES.get(src.jurisdiction.state, src.jurisdiction.state)
    if rel.effect == "bar":
        return T.bi(
            f"{state} law ({src.rule_id}) bars cities from adopting this kind of rule, so {tgt.rule_id} would not be shown to renters.",
            f"La ley de {state} ({src.rule_id}) impide que las ciudades adopten este tipo de regla, así que {tgt.rule_id} no se mostraría a los inquilinos.",
        )
    if rel.effect == "supersede":
        return T.bi(
            f"{src.rule_id} yields to {tgt.rule_id} where the local rule applies (local law over state law).",
            f"{src.rule_id} cede ante {tgt.rule_id} donde se aplica la regla local (la ley local sobre la estatal).",
        )
    when = rel.active_from.isoformat() if rel.active_from else "its start"
    return T.bi(
        f"{src.rule_id} may preempt {tgt.rule_id} from {when}; both are flagged for human review.",
        f"{src.rule_id} podría prevalecer sobre {tgt.rule_id} desde {when}; ambas se señalan para revisión humana.",
    )


def build_hierarchy(view: DocView, new_rules: list[Rule], overlay: RuleSet, base: RuleSet) -> dict:
    new_ids = {r.rule_id for r in new_rules}
    cats = {r.category for r in new_rules}
    levels = []
    for lvl in _stack(view.jurisdiction.id):
        rules = [
            r
            for r in overlay.rules
            if r.jurisdiction.id == lvl["id"] and r.category in cats and r.lifecycle != "failed"
        ]
        levels.append({**lvl, "rules": [{"rule_id": r.rule_id, "title": r.title, "category": r.category,
                                         "new": r.rule_id in new_ids, "lifecycle": r.lifecycle} for r in rules]})  # fmt: skip
    relations = []
    for rel, src, targets in related_relations(overlay, new_ids):
        for tgt in targets:
            relations.append({"from": src.rule_id, "to": tgt.rule_id, "effect": rel.effect, "type": rel.type,
                              "explanation": relation_sentence(rel, src, tgt)})  # fmt: skip
    notes = []
    if not relations:
        notes.append(
            T.bi(
                "No stated precedence relation reaches this document: its rules sit alongside the other levels and are all shown.",
                "Ninguna relación de precedencia alcanza este documento: sus reglas conviven con los otros niveles y se muestran todas.",
            )
        )
    return {"levels": levels, "relations": relations, "notes": notes}


def _cond_label(leaf: dict) -> str:
    f = leaf.get("fact")
    spec = dsl.FACTS.get(f)
    name = spec.label_en if spec else str(f)
    v = leaf.get("value")
    if isinstance(v, dict):
        v = f"{v.get('as_of_minus_years')} years before the date"
    return f"{name} {leaf.get('op')} {v}"


def _leaves(pred: dict) -> list[dict]:
    if "fact" in pred:
        return [pred]
    out = []
    for k in ("all", "any"):
        for c in pred.get(k, []):
            out += _leaves(c)
    if "not" in pred:
        out += _leaves(pred["not"])
    return out


def build_graph(view: DocView, new_rules: list[Rule], overlay: RuleSet, base: RuleSet) -> dict:
    new_ids = {r.rule_id for r in new_rules}
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid: str, kind: str, label: str, status: str = "new", **detail) -> str:
        nodes.setdefault(
            nid, {"id": nid, "type": kind, "label": label, "status": status, "detail": detail}
        )
        return nid

    def edge(src: str, dst: str, typ: str, label: str) -> None:
        eid = f"{src}>{typ}>{dst}"
        if not any(e["id"] == eid for e in edges):
            edges.append({"id": eid, "source": src, "target": dst, "type": typ, "label": label})

    doc = node(
        f"doc:{view.doc.doc_id}",
        "document",
        view.doc.url.rsplit("/", 1)[-1][:40] or view.doc.doc_id,
        url=view.doc.url,
        sha256=view.doc.sha256,
        doc_type=view.doc_type,
        chars=view.doc.chars,
    )
    stack = _stack(view.jurisdiction.id)
    prev = None
    for lvl in stack:
        j = node(
            f"jur:{lvl['id']}",
            "jurisdiction",
            lvl["label"],
            status="existing",
            level=lvl["level"],
            priority=lvl["priority"],
        )
        if prev:
            edge(j, prev, "WITHIN", "is within")
        prev = j
    for r in new_rules:
        rn = node(
            f"rule:{r.rule_id}",
            "rule",
            r.rule_id,
            rule_id=r.rule_id,
            title=r.title,
            category=r.category,
            lifecycle=r.lifecycle,
            confidence=r.confidence,
            cite=r.citation.cite,
            tier=r.citation.tier,
            quote=r.citation.quote[:240],
        )
        edge(rn, doc, "DERIVED_FROM", "derived from")
        jid = f"jur:{r.jurisdiction.id}"
        node(
            jid, "jurisdiction", r.jurisdiction.name, status="existing", level=r.jurisdiction.level
        )
        edge(rn, jid, "APPLIES_TO", "applies to")
        out = r.effective.output()
        if out:
            dn = node(f"date:{out}", "date", out, effective=out, derivation=r.effective.derivation)
            edge(rn, dn, "EFFECTIVE_ON", "effective on")
        for leaf in _leaves(r.coverage)[:6]:
            cn = node(
                f"cond:{r.rule_id}:{_cond_label(leaf)}",
                "condition",
                _cond_label(leaf),
                fact=leaf.get("fact"),
            )
            edge(rn, cn, "REQUIRES", "requires")
        for i, ex in enumerate(r.exemptions[:4]):
            en = node(
                f"ex:{r.rule_id}:{i}", "exemption", ex.description[:60], description=ex.description
            )
            edge(en, rn, "EXEMPTS", "exempts")
        for old in base.rules:  # same provision, new text
            if (
                old.rule_id != r.rule_id
                and (old.jurisdiction.id, old.category, cite_key(old.citation.cite))
                == (r.jurisdiction.id, r.category, cite_key(r.citation.cite))
                and old.citation.quote != r.citation.quote
            ):
                on = node(
                    f"rule:{old.rule_id}",
                    "rule",
                    old.rule_id,
                    status="existing",
                    rule_id=old.rule_id,
                    title=old.title,
                    category=old.category,
                )
                edge(rn, on, "SUPERSEDES", "supersedes")
    for rel, src, targets in related_relations(overlay, new_ids):
        for tgt in targets:
            sn = node(
                f"rule:{src.rule_id}",
                "rule",
                src.rule_id,
                status="new" if src.rule_id in new_ids else "existing",
                rule_id=src.rule_id,
                title=src.title,
                category=src.category,
            )
            tn = node(
                f"rule:{tgt.rule_id}",
                "rule",
                tgt.rule_id,
                status="new" if tgt.rule_id in new_ids else "existing",
                rule_id=tgt.rule_id,
                title=tgt.title,
                category=tgt.category,
            )
            if rel.effect == "supersede":  # the yielding rule is overridden by the governing one
                edge(tn, sn, "OVERRIDES", "overrides where it applies")
            else:
                edge(sn, tn, "PREEMPTS", "bars" if rel.effect == "bar" else "may preempt")
    return {"nodes": list(nodes.values()), "edges": edges,
            "delta": {"nodes": sum(1 for n in nodes.values() if n["status"] == "new"),
                      "edges": len(edges)}}  # fmt: skip


# ---------------------------------------------------------------- the autonomous Judge

JUDGE_CHECKS = [
    ("exists_in_source", "Each extracted rule exists in the source"),
    ("meaning_preserved", "The legal meaning is preserved"),
    ("conditions_complete", "No important condition or exemption is missing"),
    ("jurisdiction_correct", "The jurisdiction is correct"),
    ("dates_correct", "Effective dates are correct"),
    ("citations_accurate", "Citations are accurate"),
    ("precedence_reasonable", "Precedence and priority relationships are reasonable"),
    ("no_hallucination", "Nothing was invented"),
    ("conflicts_considered", "Conflicts with existing rules are identified"),
    ("json_faithful", "The structured JSON represents the source faithfully"),
]

EMIT_JUDGMENT = {
    "name": "emit_judgment",
    "description": "Independent verdict on an extraction.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["pass", "review", "fail"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "checks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": [c[0] for c in JUDGE_CHECKS]},
                        "status": {"type": "string", "enum": ["pass", "warn", "fail"]},
                        "note": {"type": "string"},
                    },
                    "required": ["id", "status", "note"],
                },
            },
            "issues": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                        "rule_id": {"type": ["string", "null"]},
                        "message": {"type": "string"},
                        "source_section": {"type": ["string", "null"]},
                    },
                    "required": ["severity", "message"],
                },
            },
        },
        "required": ["verdict", "confidence", "checks", "issues"],
    },
}


def run_judge(
    llm: LLM,
    view: DocView,
    new_rules: list[Rule],
    validation: dict,
    hierarchy: dict,
    rerun: int = 0,
) -> dict:
    """Ask a model to inspect the extraction against the source, independently of the extractor.
    The answer is structured; code then forces the verdict to be consistent with the evidence."""
    system, version = load_prompt("judge")
    payload = {
        "rules": [
            r.model_dump(mode="json", exclude={"plain", "provenance", "audio", "votes"})
            for r in new_rules
        ],
        "deterministic_validation": [
            {"id": c["id"], "status": c["status"], "detail": c["detail"]}
            for c in validation["checks"]
        ],
        "precedence": [
            {"from": r["from"], "to": r["to"], "effect": r["effect"]}
            for r in hierarchy["relations"]
        ],
        "known_jurisdiction": view.jurisdiction.label,
    }
    source = view.model_text()[:70_000]
    user = (
        "SOURCE DOCUMENT (the only ground truth):\n"
        + view.wrapper(source)
        + "\n\nEXTRACTION TO JUDGE (JSON):\n"
        + json.dumps(payload, ensure_ascii=False)
        + (
            f"\n\nThis is independent second review number {rerun}; form your own view."
            if rerun
            else ""
        )
    )
    res = llm.call(stage="judge", model=config.MODEL_JUDGE, system=system, user=user, tool=EMIT_JUDGMENT,
                   prompt_version=version, ref=view.doc.doc_id, max_tokens=4000, effort="medium")  # fmt: skip
    out = res.output
    ids = {r.rule_id for r in new_rules}
    checks = {c["id"]: c for c in out.get("checks", []) if c.get("id") in dict(JUDGE_CHECKS)}
    full = [{"id": cid, "label": label, "status": checks.get(cid, {}).get("status", "warn"),
             "note": checks.get(cid, {}).get("note", "The judge did not report on this check.")} for cid, label in JUDGE_CHECKS]  # fmt: skip
    issues = [i for i in out.get("issues", []) if not i.get("rule_id") or i["rule_id"] in ids]
    conf = max(0.0, min(1.0, float(out.get("confidence", 0.0))))
    verdict = out.get("verdict", "review")
    # consistency enforced by code, never loosened: failures or errors cannot pass
    if any(c["status"] == "fail" for c in full) or any(i["severity"] == "error" for i in issues):
        verdict = "fail" if verdict == "fail" else "review"
    if verdict == "pass" and (
        any(c["status"] == "warn" for c in full) or any(i["severity"] == "warning" for i in issues)
    ):
        verdict = "pass" if conf >= MIN_CONFIDENCE_DEFAULT else "review"
    if not validation["passed"]:
        verdict = "review"
    return {"verdict": verdict, "confidence": round(conf, 3), "model": res.output and config.MODEL_JUDGE,
            "checks": full, "issues": issues, "cache_hit": res.cache_hit, "rerun": rerun}  # fmt: skip


def decide(
    validation: dict, judge: dict | None, impact_conflicts: int, auto_publish: bool, min_conf: float
) -> dict:
    """The conservative publication policy. Every reason that blocks auto-publish is listed."""
    reasons = []
    if not validation["passed"]:
        reasons.append("deterministic validation failed")
    if judge is None:
        reasons.append("the Judge has not run")
    else:
        if judge["verdict"] != "pass":
            reasons.append(f"the Judge verdict is {judge['verdict']}")
        if judge["confidence"] < min_conf:
            reasons.append(
                f"Judge confidence {judge['confidence']:.0%} is below the {min_conf:.0%} threshold"
            )
    if impact_conflicts:
        reasons.append(f"{impact_conflicts} unresolved conflict flag(s) need a human look")
    if reasons:
        decision = "review"
    else:
        decision = "auto_publish" if auto_publish else "prompt"
    return {
        "auto_publish_enabled": auto_publish,
        "min_confidence": min_conf,
        "decision": decision,
        "reasons": reasons,
    }


def effective_year(rules: list[Rule]) -> date | None:
    ds = [r.effective.lo for r in rules if r.effective.lo]
    return min(ds) if ds else None


__all__ = ["cal", "CATEGORIES"]
