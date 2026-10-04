"""Submission exporter: schema validation (PLAN.md 12). Real export lands in Phase 2."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from engine import config


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


def atomic_write_json(path: Path, obj) -> None:
    """Sorted keys, ensure_ascii=False, write to a temp file then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
