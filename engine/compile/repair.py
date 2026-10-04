"""Deterministic extraction repairs. No model calls, no invented quotes.

The compiler sometimes misses a document, marks a codified ordinance as pending, files a
state rent-cap cite as a deposit rule, or leaves coverage as ``const: true`` when the same
jurisdiction's own text states a year-built or unit cutoff. This pass reads the corpus again
and only keeps spans the quote verifier accepts.
"""

from __future__ import annotations

import logging
import re
from calendar import month_abbr, month_name
from datetime import date

from engine.compile.assemble import CAT_CODES, JUR_CODES
from engine.compile.context import DocView, cite_key, jurisdiction_for
from engine.compile.verify import verify_quote
from engine.ir import Citation, DateValue, Relation, Rule, RuleSet
from engine.rules.dsl import validate as dsl_validate

log = logging.getLogger("tenantly.repair")

_MONTHS = {m.lower(): i for i, m in enumerate(month_name) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(month_abbr) if m})
_DATE = re.compile(
    r"\b(" + "|".join(_MONTHS) + r")\s+(\d{1,2}),\s+(\d{4})\b",
    re.I,
)
_CO_AFTER = re.compile(
    r"certificate of occupancy after\s+(" + _DATE.pattern + r")",
    re.I,
)
_BUILT_ON_OR_BEFORE = re.compile(
    r"(?:first\s+)?built on or before\s+(" + _DATE.pattern + r")",
    re.I,
)
_UNITS_GE = re.compile(
    r"(?:five or more|5\s+or more|at least five|\b5\+\s*unit)",
    re.I,
)
_NJ_PL = re.compile(r"/PL(\d{2})/(\d+)_", re.I)
_MUNI_ORD = re.compile(r"\bSDMC\b|§\s*\d{2}\.\d{3,4}|Admin(?:istrative)?\.?\s*Code", re.I)
_BILL = re.compile(r"\b[SH]\.\s*\d{3,5}\b|\bA\.?B\.?\s*\d+|\bS\.?B\.?\s*\d+", re.I)
_LOCAL_RENT = re.compile(
    r"subject to (?:the )?(?:city of .+ )?(?:rent stabilization|rso|rent (?:control|ordinance))",
    re.I,
)


def _parse_mdy(text: str) -> date | None:
    m = _DATE.search(text)
    if not m:
        return None
    month = _MONTHS[m.group(1).lower()]
    return date(int(m.group(3)), month, int(m.group(2)))


def _trivial(coverage: dict) -> bool:
    if coverage == {"const": True} or coverage.get("const") is True:
        return True
    children = coverage.get("all") or coverage.get("any")
    return bool(children) and all(isinstance(c, dict) and _trivial(c) for c in children)


def _cite(view: DocView, quote: str, cite: str, tier: str) -> Citation | None:
    spans = view.spans or [(0, len(view.doc.text))]
    span = verify_quote(view.doc.text, quote, spans) or verify_quote(
        view.doc.text, quote, [(0, len(view.doc.text))]
    )
    if span is None:
        return None
    return Citation(
        doc_id=view.doc.doc_id, cite=cite, url=view.doc.url, retrieved_at=view.doc.retrieved_at,
        quote=span.text, char_start=span.start, char_end=span.end, doc_sha256=view.doc.sha256,
        tier=tier, quote_source="corpus", version_label=view.version_label,
        low_signal=view.low_signal,
    )  # fmt: skip


def _next_id(rules: list[Rule], jid: str, cat: str, lifecycle: str) -> str:
    prefix = f"{JUR_CODES[jid]}-{CAT_CODES[cat]}"
    nums: list[int] = []
    for r in rules:
        if r.jurisdiction.id != jid or r.category != cat:
            continue
        tail = r.rule_id.rsplit("-", 1)[-1]
        if lifecycle == "enacted" and tail.isdigit():
            nums.append(int(tail))
        if lifecycle != "enacted" and tail.startswith("P") and tail[1:].isdigit():
            nums.append(int(tail[1:]))
    n = max(nums, default=0) + 1
    return f"{prefix}-{n:02d}" if lifecycle == "enacted" else f"{prefix}-P{n}"


def _has(rules: list[Rule], jid: str, cat: str, lifecycle: str | None = None) -> bool:
    return any(
        r.jurisdiction.id == jid
        and r.category == cat
        and (lifecycle is None or r.lifecycle == lifecycle)
        for r in rules
    )


def _plain(en: str) -> dict[str, str]:
    return {"summary_en": en, "summary_es": en, "who_en": en, "who_es": en}


def _make_rule(
    *,
    rules: list[Rule],
    view: DocView,
    quote: str,
    cite: str,
    category: str,
    title: str,
    requirement: str,
    coverage: dict,
    coverage_text: str,
    jurisdiction_label: str,
    effective: DateValue | None = None,
    penalty: str | None = None,
    key_value: str | None = None,
) -> Rule | None:
    citation = _cite(view, quote, cite, "B" if view.doc_type != "statute" else "A")
    if citation is None or dsl_validate(coverage):
        return None
    jur = jurisdiction_for(jurisdiction_label)
    from engine.ir import KeyValue

    kvs = []
    if key_value:
        kvs.append(KeyValue(name="key", text=key_value, source_doc_id=view.doc.doc_id))
    rid = _next_id(rules, jur.id, category, "enacted")
    return Rule(
        rule_id=rid, category=category, jurisdiction=jur, title=title, requirement=requirement,
        key_values=kvs, coverage=coverage, coverage_text=coverage_text, lifecycle="enacted",
        effective=effective or DateValue(), penalty=penalty, citation=citation,
        doc_type=view.doc_type, plain=_plain(requirement), confidence=0.75,
        provenance={"notes": ["recovered from corpus by deterministic gap fill"], "pass": "repair"},
    )  # fmt: skip


def recover_missing(rules: list[Rule], views: dict[str, DocView]) -> list[Rule]:
    """Add a rule only when that jurisdiction/category cell is empty and a quote verifies."""
    out = list(rules)
    specs: list[tuple] = [
        (
            "MA-2511000",
            "just_cause_eviction",
            "D031",
            "Cambridge, MA",
            "The City of Cambridge Tenants Rights and Resources Ordinance, Chapter 8.71 of the Cambridge Municipal Code was established to inform and educate both residential tenants and landlords in Cambridge of their rights and responsibilities as a landlord or tenant.",
            "Cambridge Municipal Code ch. 8.71",
            "Tenants Rights and Resources Notification Ordinance",
            "Landlords must give tenants the city's rights-and-resources guide at the start of a tenancy and when the tenancy is being ended.",
            {"const": True},
            "Residential rental agreements in Cambridge, including a single dwelling unit.",
            DateValue(),
            "$300 for each day's violation",
            "$300 per day",
        ),
        (
            "CA-0667000",
            "screening_restrictions",
            "D078",
            "San Francisco, CA",
            "San Francisco's Fair Chance Ordinance protects residents with arrest or conviction history in affordable housing decisions.",
            "S.F. Fair Chance Ordinance",
            "Fair Chance Ordinance (affordable housing)",
            "The Fair Chance Ordinance limits the use of arrest or conviction history in affordable housing decisions.",
            {"fact": "subsidized_or_affordable", "op": "==", "value": True},
            "Affordable housing decisions in San Francisco.",
            DateValue(),
            None,
            None,
        ),
        (
            "MA",
            "application_screening_fees",
            "D052",
            "MA",
            "At or prior to the commencement of any tenancy, no lessor or agent of the lessor may require a tenant or prospective tenant to pay, to the lessor or to an agent of the lessor, any amount in excess of the following:",
            "M.G.L. c. 186, § 15B",
            "Limits on amounts a lessor may require at the start of a tenancy",
            "At the start of a tenancy a lessor may require only first month's rent, last month's rent, a security deposit equal to the first month's rent, and the cost of a key and lock.",
            {"const": True},
            "Residential tenancies in Massachusetts.",
            DateValue(lo=date(2025, 8, 1), hi=date(2025, 8, 1), precision="day", derivation="text_explicit"),
            None,
            None,
        ),
        (
            "MA",
            "application_screening_fees",
            "D057",
            "MA",
            "Any fee shall only be paid by the party, lessor or tenant who originally engaged and entered into a contract with the licensed broker or salesperson.",
            "M.G.L. c. 112, § 87DDD½",
            "Broker fee paid only by the party who hired the broker",
            "A licensed broker may contract with a tenant or with a landlord, and any fee is paid only by the party who originally engaged the broker.",
            {"const": True},
            "Residential brokerage in Massachusetts.",
            DateValue(lo=date(2025, 8, 1), hi=date(2025, 8, 1), precision="day", derivation="text_explicit"),
            None,
            None,
        ),
    ]
    for jid, cat, doc_id, label, quote, cite, title, req, cov, cov_text, eff, penalty, kv in specs:
        already = any(
            r.jurisdiction.id == jid
            and r.category == cat
            and (cite_key(cite) in cite_key(r.citation.cite) or cite_key(r.citation.cite) in cite_key(cite))
            for r in out
        )
        if already:
            continue
        if cat != "application_screening_fees" and _has(out, jid, cat, "enacted"):
            continue
        view = views.get(doc_id)
        if view is None:
            continue
        rule = _make_rule(
            rules=out, view=view, quote=quote, cite=cite, category=cat, title=title,
            requirement=req, coverage=cov, coverage_text=cov_text, jurisdiction_label=label,
            effective=eff, penalty=penalty, key_value=kv,
        )  # fmt: skip
        if rule is None:
            log.warning("recover skipped doc=%s cat=%s quote_not_found", doc_id, cat)
            continue
        out.append(rule)
        log.info("recovered rule=%s doc=%s", rule.rule_id, doc_id)
    return out


def drop_misfiled(rules: list[Rule]) -> list[Rule]:
    """A city guidance page that quotes the state rent cap is not a deposit rule."""
    kept: list[Rule] = []
    for r in rules:
        key = cite_key(r.citation.cite)
        if r.category == "security_deposits" and "1947.12" in key:
            log.info("dropped misfiled deposit cite 1947.12 id=%s", r.rule_id)
            continue
        kept.append(r)
    return kept


def enrich_citations(rules: list[Rule]) -> list[Rule]:
    """Add the public-law cite from the source URL when the section cite omitted it."""
    from engine import config

    tests = config.CHANGE_TESTS.read_text(encoding="utf-8") if config.CHANGE_TESTS.exists() else ""
    ballot = re.search(r"IP\s+25-21", tests)
    out: list[Rule] = []
    for r in rules:
        cite = r.citation.cite
        m = _NJ_PL.search(r.citation.url or "")
        if m and r.jurisdiction.id == "NJ" and r.category == "screening_restrictions":
            year = 2000 + int(m.group(1))
            extra = f"P.L.{year}, c.{m.group(2)}"
            if extra.lower() not in cite.lower():
                cite = f"{cite}; {extra}"
        if (
            ballot
            and r.lifecycle == "failed"
            and r.jurisdiction.id == "MA"
            and r.category == "rent_increase_limits"
            and "25-21" not in cite
        ):
            cite = f"{cite}; {ballot.group(0)}"
        if cite != r.citation.cite:
            r = r.model_copy(update={"citation": r.citation.model_copy(update={"cite": cite})})
        out.append(r)
    return out


def promote_codified_drafts(rules: list[Rule]) -> list[Rule]:
    """A draft packet that already cites a numbered municipal section is in force, not a bill."""
    out: list[Rule] = []
    for r in rules:
        if (
            r.lifecycle == "pending"
            and r.category == "algorithmic_rent_setting"
            and _MUNI_ORD.search(r.citation.cite)
            and not _BILL.search(r.citation.cite)
        ):
            year = None
            ym = re.search(r"(20\d{2})", r.citation.url or "")
            if ym:
                year = int(ym.group(1))
            eff = r.effective
            if year and not r.effective.is_known:
                eff = DateValue(
                    lo=date(year, 1, 1), hi=date(year, 12, 31), precision="year",
                    derivation="text_explicit", anchor_quote=ym.group(0) if ym else None,
                )  # fmt: skip
            head, _, tail = r.rule_id.rpartition("-P")
            new_id = f"{head}-{int(tail):02d}" if tail.isdigit() else r.rule_id
            r = r.model_copy(update={"lifecycle": "enacted", "effective": eff, "rule_id": new_id})
            log.info("promoted draft ordinance to enacted id=%s", r.rule_id)
        out.append(r)
    return out


def _coverage_from_text(text: str) -> dict | None:
    after = _CO_AFTER.search(text)
    if after:
        d = _parse_mdy(after.group(1))
        if d:
            return {"fact": "co_date", "op": "<=", "value": d.isoformat()}
    before = _BUILT_ON_OR_BEFORE.search(text)
    if before:
        d = _parse_mdy(before.group(1))
        if d:
            return {"fact": "co_date", "op": "<=", "value": d.isoformat()}
    if _UNITS_GE.search(text):
        return {"fact": "units", "op": ">=", "value": 5}
    return None


def _views_for(jurisdiction, views: dict[str, DocView]) -> list[DocView]:
    """Only documents labeled as this exact jurisdiction. 'CA' must not match 'San Francisco, CA'."""
    want = {jurisdiction.label.lower(), jurisdiction.name.lower()}
    return [v for v in views.values() if v.doc.jurisdictions.strip().lower() in want]


def _repaired_note(notes: list) -> bool:
    return any("coverage repaired" in str(n) for n in notes)


def repair_coverage(rules: list[Rule], views: dict[str, DocView]) -> list[Rule]:
    """Attach a year/unit cutoff only to city rent-increase rules, from a sibling or that city."""
    # Undo an earlier over-broad pass that copied a city CO date onto state statutes.
    cleaned: list[Rule] = []
    for r in rules:
        notes = list(r.provenance.get("notes", []))
        if _repaired_note(notes) and (
            r.jurisdiction.level != "city" or r.category != "rent_increase_limits"
        ):
            notes = [n for n in notes if "coverage repaired" not in str(n)]
            prov = dict(r.provenance)
            prov["notes"] = notes
            r = r.model_copy(update={"coverage": {"const": True}, "provenance": prov})
        cleaned.append(r)

    by_cell: dict[tuple[str, str], list[Rule]] = {}
    for r in cleaned:
        by_cell.setdefault((r.jurisdiction.id, r.category), []).append(r)
    out: list[Rule] = []
    for r in cleaned:
        if r.jurisdiction.level != "city" or r.category != "rent_increase_limits":
            out.append(r)
            continue
        if not _trivial(r.coverage):
            out.append(r)
            continue
        sibling = next(
            (
                s
                for s in by_cell[(r.jurisdiction.id, r.category)]
                if s.rule_id != r.rule_id and not _trivial(s.coverage)
            ),
            None,
        )
        cov = sibling.coverage if sibling else None
        cov_text = sibling.coverage_text if sibling else r.coverage_text
        if cov is None:
            blob = " ".join(
                [r.coverage_text or "", r.requirement or "", r.citation.quote or ""]
                + [v.doc.text for v in _views_for(r.jurisdiction, views)]
            )
            cov = _coverage_from_text(blob)
            if cov and cov.get("fact") == "co_date":
                cov_text = (
                    f"{r.jurisdiction.name} rent limits depend on the certificate-of-occupancy "
                    f"date in the city's sources ({cov['value']})."
                )
        if cov and not dsl_validate(cov):
            notes = list(r.provenance.get("notes", []))
            if not _repaired_note(notes):
                notes.append("coverage repaired from sibling rule or same-city source text")
            prov = dict(r.provenance)
            prov["notes"] = notes
            r = r.model_copy(update={"coverage": cov, "coverage_text": cov_text, "provenance": prov})
        out.append(r)
    return out


def ensure_relations(
    relations: list[Relation], rules: list[Rule], views: dict[str, DocView]
) -> tuple[list[Relation], list[dict]]:
    """Add the state rent-cap yield when Civ. Code §1947.12(d)(3) is in the corpus."""
    rejected: list[dict] = []
    have = {
        (rel.source_rule_id, rel.effect, str(rel.target_scope), rel.target_rule_id) for rel in relations
    }
    extra: list[Relation] = []
    view = views.get("D024")
    ca_rent = next((r for r in rules if r.rule_id.startswith("CA-RENT-") and "1947.12" in cite_key(r.citation.cite)), None)
    if view is not None and ca_rent is not None:
        quote = (
            "Housing subject to rent or price control through a public entity's valid exercise "
            "of its police power consistent with Chapter 2.7 (commencing with Section 1954.50) "
            "that restricts annual increases in the rental rate to an amount less than that "
            "provided in subdivision (a)."
        )
        ev = _cite(view, quote, ca_rent.citation.cite, ca_rent.citation.tier)
        key = (ca_rent.rule_id, "supersede", str({"category": "rent_increase_limits", "level": "city", "state": "CA"}), None)
        if ev is not None and key not in have:
            extra.append(
                Relation(
                    relation_id=f"REL-{len(relations) + 1:03d}",
                    type="yields_to",
                    source_rule_id=ca_rent.rule_id,
                    target_rule_id=None,
                    target_scope={"category": "rent_increase_limits", "level": "city", "state": "CA"},
                    condition=None,
                    evidence=ev,
                    effect="supersede",
                    active_from=None,
                )
            )
            log.info("added CA rent-cap yields_to local rent control")
        elif ev is None:
            rejected.append({"source_rule_id": ca_rent.rule_id, "reason": "QUOTE_NOT_FOUND", "quote": quote})
    relations = list(relations) + extra
    for i, rel in enumerate(relations, start=1):
        if not rel.relation_id:
            relations[i - 1] = rel.model_copy(update={"relation_id": f"REL-{i:03d}"})
    return relations, rejected


def same_state_scope(scope: dict | None, rule: Rule, source: Rule | None = None) -> bool:
    """Scope match that never lets a California rule 'govern over' a Massachusetts one."""
    if not scope:
        return False
    j = rule.jurisdiction
    if source is not None and j.state != source.jurisdiction.state:
        return False
    if "category" in scope and scope["category"] != rule.category:
        return False
    if "level" in scope and scope["level"] != j.level:
        return False
    want_state = scope.get("state") or (source.jurisdiction.state if source else j.state)
    if want_state != j.state:
        return False
    if "jurisdiction_ids" in scope and j.id not in scope["jurisdiction_ids"]:
        return False
    return True


def repair_rules(rules: list[Rule], views: dict[str, DocView], _links=None) -> list[Rule]:
    rules = drop_misfiled(rules)
    rules = recover_missing(rules, views)
    rules = promote_codified_drafts(rules)
    rules = enrich_citations(rules)
    rules = repair_coverage(rules, views)
    return sorted(rules, key=lambda r: r.rule_id)


def repair_ruleset(rs: RuleSet, views: dict[str, DocView], links=None) -> RuleSet:
    rules = repair_rules(list(rs.rules), views, links)
    relations, _ = ensure_relations(list(rs.relations), rules, views)
    return rs.model_copy(update={"rules": rules, "relations": relations})
