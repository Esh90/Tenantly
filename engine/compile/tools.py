"""Tool schemas (the forced-output contracts) and prompt loading for the Law Compiler."""

from __future__ import annotations

from pathlib import Path

from engine.models import CATEGORIES

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def load_prompt(name: str) -> tuple[str, int]:
    """Return (prompt text, version). Line 1 of every prompt is ``version: N``."""
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    assert first.startswith("version:"), f"{name}.md must start with 'version: N'"
    return body.strip(), int(first.split(":", 1)[1])


CAT = {"type": "string", "enum": list(CATEGORIES)}
STR = {"type": "string"}
NULL_STR = {"type": ["string", "null"]}

KEY_VALUE = {
    "type": "object",
    "properties": {
        "name": STR,
        "text": STR,
        "value": {"type": ["number", "string", "null"]},
        "unit": NULL_STR,
        "valid_from": NULL_STR,
        "valid_to": NULL_STR,
    },
    "required": ["name", "text"],
}

RULE_RECORD = {
    "type": "object",
    "properties": {
        "category": CAT,
        "quote": STR,
        "cite": STR,
        "title": STR,
        "requirement": STR,
        "key_values": {"type": "array", "items": KEY_VALUE},
        "coverage": {"type": "object"},
        "coverage_text": STR,
        "exemptions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": STR,
                    "predicate": {"type": "object"},
                    "quote": NULL_STR,
                },
                "required": ["description", "predicate"],
            },
        },
        "tenancy_conditions": {"type": "array", "items": STR},
        "effective_date": NULL_STR,
        "effective_expression": NULL_STR,
        "anchor_quote": NULL_STR,
        "sunset_date": NULL_STR,
        "approval_date": NULL_STR,
        "lifecycle": {"type": "string", "enum": ["enacted", "pending", "failed"]},
        "relations_hint": {"type": "array", "items": STR},
        "penalty": NULL_STR,
        "uncertain_fields": {"type": "array", "items": STR},
    },
    "required": [
        "category",
        "quote",
        "cite",
        "title",
        "requirement",
        "coverage",
        "coverage_text",
        "lifecycle",
    ],
}

EMIT_TRIAGE = {
    "name": "emit_triage",
    "description": "Label every section of the document.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_id": STR,
                        "categories": {"type": "array", "items": CAT},
                        "role": {
                            "type": "string",
                            "enum": [
                                "operative",
                                "definition",
                                "exemption",
                                "penalty",
                                "effective_date",
                                "preemption",
                                "procedural",
                                "findings",
                                "other",
                            ],
                        },
                        "keep": {"type": "boolean"},
                        "refs": {"type": "array", "items": STR},
                    },
                    "required": ["section_id", "categories", "role", "keep"],
                },
            }
        },
        "required": ["sections"],
    },
}

EMIT_RULES = {
    "name": "emit_rules",
    "description": "Report every rule found in the document.",
    "input_schema": {
        "type": "object",
        "properties": {"rules": {"type": "array", "items": RULE_RECORD}},
        "required": ["rules"],
    },
}

EMIT_DECISION = {
    "name": "emit_decision",
    "description": "Decide a disputed field.",
    "input_schema": {
        "type": "object",
        "properties": {
            "choice": {"type": "string", "description": "The chosen option label, e.g. A or B"},
            "undetermined": {"type": "boolean"},
            "evidence_quote": STR,
        },
        "required": ["choice", "undetermined", "evidence_quote"],
    },
}

EMIT_SIGNALS = {
    "name": "emit_signals",
    "description": "List laws asserted by the supplementary materials.",
    "input_schema": {
        "type": "object",
        "properties": {
            "laws": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "jurisdiction": STR,
                        "category": CAT,
                        "citation": STR,
                        "status_claim": {
                            "type": "string",
                            "enum": ["enacted", "pending", "failed"],
                        },
                        "date_claim": NULL_STR,
                        "link_doc_ids": {"type": "array", "items": STR},
                        "signals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"source": STR, "text": STR},
                                "required": ["source", "text"],
                            },
                        },
                    },
                    "required": ["jurisdiction", "category", "citation", "status_claim", "signals"],
                },
            }
        },
        "required": ["laws"],
    },
}

EMIT_GAP = {
    "name": "emit_gap_result",
    "description": "Classify one empty jurisdiction/category cell.",
    "input_schema": {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "enum": [
                    "found",
                    "barred_by_state",
                    "motion_only",
                    "only_pending",
                    "failed_measure",
                    "text_not_supplied",
                    "none_in_sources",
                ],
            },
            "section_id": NULL_STR,
            "quote": NULL_STR,
            "explanation": STR,
        },
        "required": ["result", "explanation"],
    },
}

EMIT_RELATIONS = {
    "name": "emit_relations",
    "description": "Report relations between rules that the text states.",
    "input_schema": {
        "type": "object",
        "properties": {
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "yields_to",
                                "preempts",
                                "bars",
                                "conflicts_with",
                                "supplements",
                                "amends",
                            ],
                        },
                        "source_rule_id": STR,
                        "target_rule_id": NULL_STR,
                        "target_scope": {"type": ["object", "null"]},
                        "condition": {"type": ["object", "null"]},
                        "effect": {"type": "string", "enum": ["supersede", "conflict_flag", "bar"]},
                        "doc_id": STR,
                        "quote": STR,
                        "active_from": NULL_STR,
                    },
                    "required": ["type", "source_rule_id", "effect", "doc_id", "quote"],
                },
            }
        },
        "required": ["relations"],
    },
}

EMIT_PLAIN = {
    "name": "emit_plain",
    "description": "Plain-language text for one rule.",
    "input_schema": {
        "type": "object",
        "properties": {"summary_en": STR, "who_en": STR, "summary_es": STR, "who_es": STR},
        "required": ["summary_en", "who_en", "summary_es", "who_es"],
    },
}

EMIT_TRANSLATION = {
    "name": "emit_translation",
    "description": "Spanish versions of an English title and detail.",
    "input_schema": {
        "type": "object",
        "properties": {"title_es": STR, "detail_es": STR},
        "required": ["title_es", "detail_es"],
    },
}


EMIT_FAITHFUL = {
    "name": "emit_faithful",
    "description": "Is the predicate a faithful encoding of the legal condition?",
    "input_schema": {
        "type": "object",
        "properties": {"faithful": {"type": "boolean"}, "reason": STR},
        "required": ["faithful", "reason"],
    },
}
