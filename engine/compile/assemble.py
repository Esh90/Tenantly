"""Cross-document merge, confidence and team rule ids (PLAN.md 11.8, 12.2)."""

from __future__ import annotations

from collections import defaultdict

from engine.compile.context import cite_key
from engine.ir import Rule

JUR_CODES = {
    "CA": "CA", "NJ": "NJ", "MA": "MA",
    "CA-0644000": "LA", "CA-0667000": "SF", "CA-0666000": "SD", "CA-0606000": "BRK",
    "CA-0669000": "SNA", "NJ-3436000": "JC", "NJ-3432250": "HOB", "NJ-3451000": "NWK",
    "MA-2507000": "BOS", "MA-2511000": "CAM",
}  # fmt: skip
CAT_CODES = {
    "rent_increase_limits": "RENT", "just_cause_eviction": "JCE", "security_deposits": "DEP",
    "application_screening_fees": "FEE", "screening_restrictions": "SCR",
    "algorithmic_rent_setting": "ALG",
}  # fmt: skip
TIER_BASE = {"A": 0.9, "B": 0.8, "C": 0.55, "C1": 0.3}
TIER_CAP = {"A": 1.0, "B": 0.9, "C": 0.6, "C1": 0.3}
DERIVED_PENALTY = {"readme_reference", "brief_reference"}
LONG_QUOTE_FIRST = lambda r: (-len(r.citation.quote), r.citation.doc_id)  # noqa: E731


def merge_across_docs(rules: list[Rule]) -> list[Rule]:
    """Rules with the same (jurisdiction, category, cite) from different documents become one:
    the best-tier, longest-quote record is primary and the others become extra citations."""
    groups: dict[tuple, list[Rule]] = defaultdict(list)
    for r in rules:
        groups[(r.jurisdiction.id, r.category, cite_key(r.citation.cite), r.lifecycle)].append(r)
    out: list[Rule] = []
    for _, group in sorted(groups.items()):
        group.sort(key=lambda r: (r.citation.tier, *LONG_QUOTE_FIRST(r)))
        primary = group[0]
        extras = list(primary.extra_citations)
        kvs = list(primary.key_values)
        seen_kv = {(k.name, k.text) for k in kvs}
        exes = list(primary.exemptions)
        for other in group[1:]:
            if other.citation.quote != primary.citation.quote:
                extras.append(other.citation)
            for k in other.key_values:
                if (k.name, k.text) not in seen_kv:
                    kvs.append(k)
                    seen_kv.add((k.name, k.text))
            have = {e.description for e in exes}
            exes += [e for e in other.exemptions if e.description not in have]
        out.append(
            primary.model_copy(
                update={"extra_citations": extras, "key_values": kvs, "exemptions": exes}
            )
        )
    return out


def confidence(rule: Rule) -> float:
    tier = rule.citation.tier
    c = TIER_BASE[tier] + float(rule.provenance.get("conf_delta", 0.0))
    if rule.citation.low_signal:
        c -= 0.1
    if rule.effective.derivation in DERIVED_PENALTY:
        c -= 0.1
    return round(max(0.05, min(c, TIER_CAP[tier])), 2)


def assign_ids(rules: list[Rule]) -> list[Rule]:
    """{JUR}-{CAT}-{NN}: enacted rules by normalized cite, pending and failed rules as P#."""
    by_cell: dict[tuple, list[Rule]] = defaultdict(list)
    for r in rules:
        by_cell[(r.jurisdiction.id, r.category)].append(r)
    out: list[Rule] = []
    for (jid, cat), group in sorted(by_cell.items()):
        enacted = sorted(
            (r for r in group if r.lifecycle == "enacted"), key=lambda r: cite_key(r.citation.cite)
        )
        other = sorted(
            (r for r in group if r.lifecycle != "enacted"), key=lambda r: cite_key(r.citation.cite)
        )
        prefix = f"{JUR_CODES[jid]}-{CAT_CODES[cat]}"
        for n, r in enumerate(enacted, start=1):
            out.append(r.model_copy(update={"rule_id": f"{prefix}-{n:02d}"}))
        for n, r in enumerate(other, start=1):
            out.append(r.model_copy(update={"rule_id": f"{prefix}-P{n}"}))
    return sorted(out, key=lambda r: r.rule_id)


def finalize_rules(rules: list[Rule]) -> list[Rule]:
    merged = assign_ids(merge_across_docs(rules))
    out = []
    for r in merged:
        c = confidence(r)
        out.append(r.model_copy(update={"confidence": c, "review_flag": r.review_flag or c < 0.5}))
    return out
