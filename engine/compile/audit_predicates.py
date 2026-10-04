"""Second look at every exemption predicate (PLAN.md D6: the model never decides applicability).

A cheap model re-reads each exemption sentence and its predicate. If the predicate does not
faithfully encode a condition on the building, landlord or tenancy (for example an exemption that
is really about what a government agency does), the exemption becomes ``unknown``: it is shown as
a caveat and never silently removes the rule for a building.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from engine import config
from engine.compile.llm import LLM, NoToolCall
from engine.compile.tools import EMIT_FAITHFUL, load_prompt
from engine.ir import Exemption, Rule

log = logging.getLogger("tenantly.audit_predicates")


def _faithful(llm: LLM, rule: Rule, ex: Exemption) -> tuple[bool, str]:
    system, version = load_prompt("predicate_audit")
    user = json.dumps(
        {"rule": rule.title, "category": rule.category, "exemption": ex.description,
         "quote": ex.quote or rule.citation.quote[:600], "predicate": ex.predicate},
        ensure_ascii=False,
    )  # fmt: skip
    try:
        res = llm.call(stage="predicate_audit", model=config.MODEL_FAST, system=system, user=user,
                       tool=EMIT_FAITHFUL, prompt_version=version, ref=rule.rule_id, max_tokens=800)  # fmt: skip
    except NoToolCall:
        return False, "the audit returned no answer"
    return bool(res.output.get("faithful")), str(res.output.get("reason", ""))


def audit_rule(llm: LLM, rule: Rule) -> Rule:
    if not rule.exemptions or rule.citation.tier not in ("A", "B"):
        return rule
    out: list[Exemption] = []
    notes = list(rule.provenance.get("notes", []))
    for ex in rule.exemptions:
        if ex.predicate == {"const": "unknown"}:
            out.append(ex)
            continue
        ok, reason = _faithful(llm, rule, ex)
        if ok:
            out.append(ex)
        else:
            out.append(ex.model_copy(update={"predicate": {"const": "unknown"}}))
            notes.append(
                f"exemption downgraded to unknown (predicate not faithful): {ex.description[:80]}: {reason[:120]}"
            )
    prov = dict(rule.provenance)
    prov["notes"] = notes
    return rule.model_copy(update={"exemptions": out, "provenance": prov})


def audit_all(llm: LLM, rules: list[Rule], workers: int = 4) -> list[Rule]:
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda r: audit_rule(llm, r), rules))
