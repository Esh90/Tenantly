"""Plain-language EN/ES summaries (PLAN.md 11.11): written by Haiku, accepted only through gates.

Gates: every number must appear in the rule record, reading grade <= 8.5, no banned phrases.
One retry with the failure named; then a deterministic template.
"""

from __future__ import annotations

import json
import logging
import re

import textstat

from engine import config
from engine.compile.llm import LLM
from engine.compile.tools import EMIT_PLAIN, load_prompt
from engine.ir import Rule

log = logging.getLogger("tenantly.explain")

BANNED = ("avoid", "get around", "loophole", "workaround", "circumvent", "you should", "we recommend",
          "legal advice", "debes", "le recomendamos", "evitar")  # fmt: skip
MAX_GRADE = 8.5
NUM = re.compile(r"\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in NUM.findall(text)}


def allowed_numbers(rule: Rule) -> set[str]:
    blob = " ".join(
        [rule.title, rule.requirement, rule.coverage_text, rule.citation.quote, rule.citation.cite,
         rule.exemptions_text or "", rule.penalty or ""]
        + [k.text for k in rule.key_values] + [str(k.value) for k in rule.key_values]
        + [e.description for e in rule.exemptions]
    )  # fmt: skip
    blob += " " + json.dumps(rule.coverage) + " " + (rule.effective.output() or "")
    return _numbers(blob)


def check(rule: Rule, out: dict) -> list[str]:
    problems = []
    en = f"{out.get('summary_en', '')} {out.get('who_en', '')}"
    es = f"{out.get('summary_es', '')} {out.get('who_es', '')}"
    if not all(out.get(k, "").strip() for k in ("summary_en", "who_en", "summary_es", "who_es")):
        problems.append("a field is empty")
    allowed = allowed_numbers(rule)
    extra = (_numbers(en) | _numbers(es)) - allowed
    if extra:
        problems.append(f"numbers not in the rule record: {sorted(extra)}")
    for phrase in BANNED:
        if phrase in en.lower() or phrase in es.lower():
            problems.append(f"banned phrase: {phrase}")
    if len(out.get("summary_en", "").split()) > 45:
        problems.append("summary_en is longer than 40 words")
    if textstat.flesch_kincaid_grade(out.get("summary_en", "") or "x") > MAX_GRADE:
        problems.append("reading grade above 8.5")
    return problems


def template(rule: Rule) -> dict[str, str]:
    kv = rule.key_values[0].text if rule.key_values else ""
    tail = f": {kv}." if kv else "."
    return {
        "summary_en": f"{rule.title}{tail}", "who_en": f"{rule.coverage_text}",
        "summary_es": f"{rule.title}{tail}", "who_es": f"{rule.coverage_text}",
    }  # fmt: skip


def explain_rule(llm: LLM, rule: Rule) -> Rule:
    system, version = load_prompt("explain")
    record = {
        "title": rule.title, "category": rule.category, "jurisdiction": rule.jurisdiction.label,
        "requirement": rule.requirement, "coverage_text": rule.coverage_text,
        "key_values": [k.text for k in rule.key_values], "exemptions": [e.description for e in rule.exemptions],
        "lifecycle": rule.lifecycle, "effective_date": rule.effective.output(), "penalty": rule.penalty,
        "note": "The text of this law was not supplied." if rule.citation.tier in ("C", "C1") else None,
    }  # fmt: skip
    user = json.dumps(record, ensure_ascii=False)
    out: dict = {}
    problems: list[str] = []
    for attempt in (1, 2):
        extra = (
            ""
            if attempt == 1
            else f"\nYour previous answer failed: {'; '.join(problems)}. Fix this."
        )
        res = llm.call(stage="explain", model=config.MODEL_FAST, system=system, user=user + extra,
                       tool=EMIT_PLAIN, prompt_version=version, ref=rule.rule_id, max_tokens=1500)  # fmt: skip
        out = res.output
        problems = check(rule, out)
        if not problems:
            break
    used_template = bool(problems)
    if used_template:
        out = template(rule)
    grade = round(textstat.flesch_kincaid_grade(out["summary_en"]), 2)
    prov = dict(rule.provenance)
    prov["plain_template"] = used_template
    return rule.model_copy(update={"plain": {k: out[k] for k in ("summary_en", "who_en", "summary_es", "who_es")},
                                   "grade_level_en": grade, "provenance": prov})  # fmt: skip
