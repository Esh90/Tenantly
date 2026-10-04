"""Cross-document merge, confidence and team rule ids (PLAN.md 11.8, 12.2)."""

from __future__ import annotations

import re
from collections import defaultdict

from engine.compile.context import cite_key, jurisdiction_for
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


LOCAL_MARKERS = re.compile(
    r"\bBMC\b|\bSDMC\b|\bLAMC\b|S\.?F\.? Admin|Admin\.? Code|Municipal Code|\bMC\b|\bordinance\b|\bch\.\s*\d|\bBerkeley\b|"
    r"\bRent Ordinance\b|\bRSO\b|\bSan (Francisco|Diego)\b|\bLos Angeles\b|\bJersey City\b|\bHoboken\b|\bBoston\b|\bCambridge\b|\bSanta Ana\b",
    re.I,
)
STATE_CITES = {
    "CA": re.compile(
        r"\bCal(ifornia|\.)?\s+(Civ|Gov|Bus|Health|Penal|Code)|\bCiv(il)?\.?\s+Code\b|\bGov(ernment)?\.?\s+Code\b|Bus(iness)?\.?\s*&\s*Prof",
        re.I,
    ),
    "NJ": re.compile(r"N\.?J\.?S\.?A|\bP\.?L\.?\s*\d{4}|New Jersey", re.I),
    "MA": re.compile(r"\bM\.?G\.?L\b|\bG\.?L\.?\s*c\.|Mass(achusetts)?\.?\s+Gen", re.I),
}


def rehome(rule: Rule) -> Rule:
    """A city guidance page that cites a state statute describes the state rule: file it there."""
    if rule.jurisdiction.level != "city" or rule.citation.tier not in ("A", "B"):
        return rule
    cite = re.sub(r"\([^)]*\)", "", rule.citation.cite)  # drop "(as applied in Berkeley)" asides
    if LOCAL_MARKERS.search(cite):
        return rule
    pat = STATE_CITES.get(rule.jurisdiction.state)
    if pat and pat.search(cite):
        prov = dict(rule.provenance)
        prov["rehomed_from"] = rule.jurisdiction.label
        return rule.model_copy(
            update={"jurisdiction": jurisdiction_for(rule.jurisdiction.state), "provenance": prov}
        )
    return rule


def _group_key(r: Rule) -> tuple:
    toks = cite_key(r.citation.cite).split("|")
    first = toks[0] if toks and any(c.isdigit() for c in toks[0]) else f"{r.citation.doc_id}:title"
    return (r.jurisdiction.id, r.category, first, r.lifecycle)


def merge_across_docs(rules: list[Rule]) -> list[Rule]:
    """Rules with the same (jurisdiction, category, cite) from different documents become one:
    the best-tier, longest-quote record is primary and the others become extra citations."""
    groups: dict[tuple, list[Rule]] = defaultdict(list)
    for r in rules:
        groups[_group_key(r)].append(r)
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
    merged = assign_ids(merge_across_docs([rehome(r) for r in rules]))
    out = []
    for r in merged:
        c = confidence(r)
        out.append(r.model_copy(update={"confidence": c, "review_flag": r.review_flag or c < 0.5}))
    return out
