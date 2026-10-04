"""Submission exporter: schema validation (PLAN.md 12). Real export lands in Phase 2."""

from __future__ import annotations

import json

from jsonschema import Draft202012Validator

from engine import config
from engine.io import atomic_write_json  # noqa: F401  (re-exported for callers)


def load_schema() -> dict:
    return json.loads(config.RULE_SCHEMA.read_text(encoding="utf-8"))


def validate_rules(doc: dict) -> list[str]:
    """Return schema errors for a rules.json document (empty list means valid)."""
    validator = Draft202012Validator(load_schema())
    errors: list[str] = []
    rules = doc.get("rules")
    if not isinstance(rules, list):
        return ["top level must be {'rules': [...]}"]
    for i, rule in enumerate(rules):
        for err in sorted(validator.iter_errors(rule), key=lambda e: list(e.path)):
            loc = "/".join(str(p) for p in err.path) or "<rule>"
            errors.append(f"rules[{i}].{loc}: {err.message}")
    return errors
