"""The Law Compiler DAG (PLAN.md 5.2): stages in order, content-addressed through the LLM cache,
so a rerun only pays for stages whose inputs changed. ``--explain`` lists what would run and
what it would cost, and spends nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from engine import config
from engine.compile import assemble, audit_predicates, discrepancy, gaps, link, tier_c
from engine.compile import explain as explain_stage
from engine.compile.context import DocView, load_views
from engine.compile.extract import Rejection, compile_document
from engine.compile.llm import LLM, canonical
from engine.corpus import sectionizer
from engine.io import atomic_write_json, atomic_write_jsonl
from engine.ir import Finding, OpenQuestion, Relation, Rule, RuleSet

log = logging.getLogger("tenantly.dag")

RULES_PATH = config.ARTIFACTS / "rules.compiled.json"
# downstream stages depend on earlier output, so a dry run can only estimate them
TYPICAL = {"link": (3, 0.25), "gap": (45, 0.12), "explain": (60, 0.30), "translate": (8, 0.02)}


def data_version(rules: list[Rule], relations: list[Relation], findings: list[Finding]) -> str:
    blob = canonical(
        [[r.model_dump(mode="json") for r in rules], [x.model_dump(mode="json") for x in relations],
         [f.model_dump(mode="json") for f in findings]]
    )  # fmt: skip
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def sections_for(view: DocView):
    from engine.corpus import versions

    return sectionizer.sectionize(view.doc, view.masked, versions.segment_versions(view.doc.text))


def compile_all(llm: LLM, only: list[str] | None = None, workers: int = 4):
    views, links = load_views()
    targets = [v for k, v in sorted(views.items()) if not only or k in only]
    rules_raw: list[Rule] = []
    rejected: list[Rejection] = []

    def one(v: DocView):
        try:
            return compile_document(llm, v, sections_for(v))
        except Exception:
            log.exception("compile failed doc=%s", v.doc.doc_id)
            raise

    with ThreadPoolExecutor(workers) as pool:
        for rules, rej in pool.map(one, targets):
            rules_raw += rules
            rejected += rej
    log.info("extraction done rules=%d rejected=%d", len(rules_raw), len(rejected))

    c_rules, c_audit = tier_c.build_tier_c(llm, links, rules_raw)
    all_raw = rules_raw + c_rules
    items = discrepancy.readme_items()
    final = assemble.finalize_rules(all_raw)
    final = audit_predicates.audit_all(llm, final)
    final, date_items = discrepancy.apply_alternative_dates(final, items)

    raw_rel = link.link_documents(llm, final, views)
    relations, rel_rejected = link.verify_relations(raw_rel, final, views)

    findings, gap_report = gaps.audit_gaps(llm, final, relations, views, links)

    with ThreadPoolExecutor(workers) as pool:
        final = list(pool.map(lambda r: explain_stage.explain_rule(llm, r), final))
    oqs = discrepancy.build_open_questions(llm, final, relations, views, links, date_items)
    final = _attach_oqs(final, oqs)
    return final, relations, findings, oqs, {"rejected": rejected, "tier_c_audit": c_audit,
                                              "gap_report": gap_report, "rel_rejected": rel_rejected,
                                              "n_docs": len(targets)}  # fmt: skip


def _attach_oqs(rules: list[Rule], oqs: list[OpenQuestion]) -> list[Rule]:
    by_rule: dict[str, list[str]] = {}
    for q in oqs:
        for rid in q.rule_ids:
            by_rule.setdefault(rid, []).append(q.oq_id)
    return [r.model_copy(update={"open_question_ids": by_rule.get(r.rule_id, [])}) for r in rules]


def write_artifacts(rules, relations, findings, oqs, extra: dict) -> RuleSet:
    rs = RuleSet(
        data_version=data_version(rules, relations, findings),
        compiled_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        rules=rules, relations=relations, findings=findings, open_questions=oqs,
    )  # fmt: skip
    atomic_write_json(RULES_PATH, rs.model_dump(mode="json"))
    rej = extra["rejected"]
    atomic_write_jsonl(
        config.ARTIFACTS / "audit" / "rejected.jsonl",
        [{"doc_id": r.doc_id, "pass": r.stage, "reason": r.reason, "title": r.title, "quote": r.quote} for r in rej],
    )  # fmt: skip
    tiers = Counter(r.citation.tier for r in rules)
    verified = sum(1 for r in rules if r.citation.quote_source == "corpus")
    adjudicated = sum(len(r.provenance.get("adjudicated_fields", [])) for r in rules)
    atomic_write_json(
        config.ARTIFACTS / "eval" / "verification.json",
        {
            "rules": len(rules), "tier_counts": {t: tiers.get(t, 0) for t in ("A", "B", "C", "C1")},
            "quotes_verified": verified, "rejected_candidates": len(rej),
            "rejected_by_reason": dict(sorted(Counter(r.reason for r in rej).items())),
            "adjudicated_fields": adjudicated,
            "mean_confidence": round(sum(r.confidence for r in rules) / max(1, len(rules)), 3),
            "relations": len(relations), "relations_rejected": len(extra["rel_rejected"]),
            "findings": len(findings), "open_questions": len(oqs),
            "review_flagged": sum(1 for r in rules if r.review_flag),
        },
    )  # fmt: skip
    atomic_write_json(config.ARTIFACTS / "eval" / "tier_c_audit.json", extra["tier_c_audit"])
    atomic_write_json(config.ARTIFACTS / "eval" / "gap_report.json", extra["gap_report"])
    atomic_write_json(config.ARTIFACTS / "eval" / "relations_rejected.json", extra["rel_rejected"])
    return rs


def explain_plan(llm: LLM, only: list[str] | None = None) -> dict:
    """Dry run: which model calls would be made (cache misses only) and what they would cost."""
    llm.dry = True
    llm.plan.clear()
    views, links = load_views()
    for k, v in sorted(views.items()):
        if only and k not in only:
            continue
        compile_document(llm, v, sections_for(v))
    tier_c.build_tier_c(llm, links, [])
    by_stage: dict[str, dict] = {}
    for p in llm.plan:
        s = by_stage.setdefault(p["stage"], {"calls": 0, "est_usd": 0.0, "model": p["model"]})
        s["calls"] += 1
        s["est_usd"] += p["est_usd"]
    for stage, (calls, usd) in TYPICAL.items():
        by_stage.setdefault(
            stage, {"calls": calls, "est_usd": usd, "model": "typical", "downstream": True}
        )
    total = sum(s["est_usd"] for s in by_stage.values())
    llm.dry = False
    return {"stages": by_stage, "estimated_total_usd": round(total, 2),
            "already_spent_usd": round(llm.ledger.total, 4), "cap_usd": llm.ledger.cap,
            "note": "Extraction output tokens are estimated at 4000 per call; downstream stages are typical values."}  # fmt: skip


def dump_plan(plan: dict) -> str:
    return json.dumps(plan, indent=2, sort_keys=True)
