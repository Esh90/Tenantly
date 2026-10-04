import json

from engine import config
from engine.export.submission import atomic_write_json, validate_rules


def test_template_rules_validate_against_official_schema():
    doc = json.loads((config.DATASET / "submission_templates" / "rules.json").read_text("utf-8"))
    assert validate_rules(doc) == []


def test_sample_rule_record_validates():
    sample = json.loads((config.DATASET / "schema" / "sample_rule_record.json").read_text("utf-8"))
    assert validate_rules({"rules": [sample]}) == []


def test_invalid_rule_is_reported():
    errs = validate_rules({"rules": [{"team_rule_id": "x"}]})
    assert errs and any("required" in e for e in errs)


def test_short_quote_rejected():
    sample = json.loads((config.DATASET / "schema" / "sample_rule_record.json").read_text("utf-8"))
    sample["quoted_span"] = "too short"
    assert any("quoted_span" in e for e in validate_rules({"rules": [sample]}))


def test_atomic_write_is_sorted_and_utf8(tmp_path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"b": "é", "a": 1})
    assert p.read_text("utf-8").index('"a"') < p.read_text("utf-8").index('"b"')
    assert "é" in p.read_text("utf-8")
    assert not (tmp_path / "x.json.tmp").exists()
