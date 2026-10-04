"""Exports (PLAN.md 12, 13): submission files, change events and the static snapshot.

Everything here derives from artifacts through the same engine and renderer the API uses, so the
submission files, the snapshot and the live API can never disagree.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from engine import config
from engine.compile.repair import same_state_scope
from engine.export.submission import validate_rules
from engine.io import atomic_write_json
from engine.ir import Rule, RuleSet
from engine.rules import templates as T
from engine.rules.changes import ChangeOutput, run_all
from engine.rules.engine import evaluate_address
from engine.rules.explain import explain
from engine.rules.facts_env import AddressEnv
from engine.rules.render import rule_status

DEFAULT = date.fromisoformat(config.DEFAULT_AS_OF)


def load_ruleset() -> RuleSet:
    raw = json.loads((config.ARTIFACTS / "rules.compiled.json").read_text(encoding="utf-8"))
    rs = RuleSet.model_validate(raw)
    from engine.compile.context import load_views
    from engine.compile.repair import repair_ruleset

    views, links = load_views()
    fixed = repair_ruleset(rs, views, links)
    if fixed.model_dump(mode="json") != rs.model_dump(mode="json"):
        atomic_write_json(config.ARTIFACTS / "rules.compiled.json", fixed.model_dump(mode="json"))
    return fixed


def load_records() -> dict[str, dict]:
    return json.loads((config.ARTIFACTS / "addresses.resolved.json").read_text(encoding="utf-8"))


# ---- rules.json ----


def key_value_text(r: Rule) -> str | None:
    """The first value valid on the default date, else the latest with its period."""
    valid = [
        k
        for k in r.key_values
        if (k.valid_from is None or k.valid_from <= DEFAULT)
        and (k.valid_to is None or DEFAULT <= k.valid_to)
    ]
    if valid:
        return valid[0].text
    dated = sorted((k for k in r.key_values if k.valid_to), key=lambda k: k.valid_to)  # type: ignore[arg-type,return-value]
    if dated:
        k = dated[-1]
        return f"{k.text} (published for {k.valid_from or 'earlier'} to {k.valid_to})"
    return r.key_values[0].text if r.key_values else None


def rule_record(r: Rule, rs: RuleSet) -> dict:
    overrides: list[str] = []
    notes: list[str] = []
    by_id = {x.rule_id: x for x in rs.rules}
    for rel in rs.relations:
        if rel.effect == "supersede":
            source = by_id.get(rel.source_rule_id)
            targets = (
                [rel.target_rule_id] if rel.target_rule_id
                else [
                    x.rule_id
                    for x in rs.rules
                    if x.rule_id != rel.source_rule_id
                    and same_state_scope(rel.target_scope, x, source)
                ]
            )  # fmt: skip
            if rel.source_rule_id == r.rule_id and targets:
                overrides += targets
                notes.append(
                    f"Yields to {', '.join(targets)} where they apply ({r.citation.cite})."
                )
            elif r.rule_id in targets:
                overrides.append(rel.source_rule_id)
                notes.append(
                    f"Governs over {rel.source_rule_id} where it applies (local law over state law)."
                )
        elif rel.effect == "bar" and rel.source_rule_id == r.rule_id:
            notes.append("Bars matching local rules (state law over local law).")
    conflict = False
    cnote: list[str] = []
    if r.citation.tier in ("C", "C1"):
        cnote.append(r.provenance.get("notes", [""])[0])
    for rel in rs.relations:
        if rel.effect == "conflict_flag" and r.rule_id in (rel.source_rule_id, rel.target_rule_id):
            when = rel.active_from.isoformat() if rel.active_from else "its start"
            active = rel.active_from is not None and rel.active_from <= DEFAULT
            conflict |= active
            cnote.append(
                f"Possible preemption between {rel.source_rule_id} and {rel.target_rule_id} from {when}; flagged for human review."
            )
    for q in rs.open_questions:
        if r.rule_id in q.rule_ids:
            cnote.append(f"Open question: {q.title['en']}")
            if (
                q.changes_answer_between
                and q.changes_answer_between[0] <= DEFAULT <= q.changes_answer_between[1]
            ):
                conflict = True
    rec = {
        "team_rule_id": r.rule_id, "jurisdiction": r.jurisdiction.label,
        "level": "state" if r.jurisdiction.level == "state" else "city", "category": r.category,
        "status": rule_status(r, DEFAULT), "title": r.title, "requirement": r.requirement,
        "key_value": key_value_text(r), "coverage_conditions": r.coverage_text,
        "exemptions": r.exemptions_text, "overrides": sorted(set(overrides)),
        "interaction": " ".join(notes) or None, "effective_date": r.effective.output(),
        "citation": r.citation.cite, "source_doc_id": r.citation.doc_id, "source_url": r.citation.url,
        "quoted_span": r.citation.quote, "confidence": r.confidence, "conflict_flag": conflict,
        "conflict_note": " ".join(n for n in cnote if n) or None,
    }  # fmt: skip
    return rec


def build_rules_json(rs: RuleSet) -> dict:
    return {
        "rules": sorted((rule_record(r, rs) for r in rs.rules), key=lambda x: x["team_rule_id"])
    }


# ---- lookups.json ----


def build_lookups(rs: RuleSet, records: dict[str, dict]) -> dict:
    titles = {r.rule_id: r.title for r in rs.rules}
    out: dict[str, list[dict]] = {}
    for aid in sorted(records):
        rec = records[aid]
        res = evaluate_address(rs, rec, AddressEnv(rec), DEFAULT)
        out[aid] = [
            {
                "team_rule_id": o.rule_id,
                "result": o.result,
                "explanation": explain(o, DEFAULT, titles)["en"],
                "conflict_flag": o.conflict_flag,
            }  # fmt: skip
            for o in sorted(res.outcomes, key=lambda o: o.rule_id)
        ]
    return {"as_of": config.DEFAULT_AS_OF, "lookups": out}


# ---- changes ----


def change_events(
    outputs: dict[str, ChangeOutput], records: dict[str, dict], created_at: str
) -> dict[str, dict]:
    from engine.rules.render import address_label

    events: dict[str, dict] = {}
    for tid, o in outputs.items():
        aff = []
        for a in o.affected:
            rec = records[a.address_id]
            aff.append({
                "address_id": a.address_id, "label": address_label(rec), "lat": rec["lat"], "lon": rec["lon"],
                "legal_city": rec["legal_city"],
                "before": [{"rule_id": r, "result": v} for r, v in a.before],
                "after": [{"rule_id": r, "result": v} for r, v in a.after],
                "conflict_flag": a.conflict_flag,
            })  # fmt: skip
        compare = (
            o.compare if o.test_type != "with_without" else {"mode": "with_without", **o.compare}
        )
        events[f"chg-{tid}"] = {
            "change_id": f"chg-{tid}", "kind": "test", "test_id": tid, "title": o.title,
            "test_type": o.test_type, "summary": T.bi(o.notes, o.notes), "created_at": created_at,
            "rule_ids": o.rule_ids, "compare": compare, "affected_count": len(o.affected),
            "conflict_count": len(o.conflict_ids), "expected_check": None, "affected": aff,
        }  # fmt: skip
    return events


def build_changes(rs: RuleSet, records: dict[str, dict]) -> tuple[dict, dict]:
    tests = json.loads(config.CHANGE_TESTS.read_text(encoding="utf-8"))
    outputs = run_all(tests, rs, records)
    submission = {
        tid: {"affected_address_ids": o.affected_ids, "conflict_flag_address_ids": o.conflict_ids, "notes": o.notes}
        for tid, o in outputs.items()
    }  # fmt: skip
    events = change_events(outputs, records, rs.compiled_at)
    return submission, events


def write_changes(rs: RuleSet, records: dict[str, dict]) -> dict:
    submission, events = build_changes(rs, records)
    for ev in events.values():
        atomic_write_json(config.ARTIFACTS / "changes" / f"{ev['test_id']}.json", ev)
    atomic_write_json(config.OUT / "changes.json", submission)
    return submission


def export_all(rs: RuleSet, records: dict[str, dict]) -> dict:
    rules_doc = build_rules_json(rs)
    errors = validate_rules(rules_doc)
    if errors:
        raise SystemExit("rules.json fails the official schema:\n" + "\n".join(errors[:20]))
    lookups = build_lookups(rs, records)
    assert len(lookups["lookups"]) == 500 and all(
        set(e) == {"team_rule_id", "result", "explanation", "conflict_flag"}
        for v in lookups["lookups"].values()
        for e in v
    )
    atomic_write_json(config.OUT / "rules.json", rules_doc)
    atomic_write_json(config.OUT / "lookups.json", lookups)
    submission = write_changes(rs, records)
    return {
        "rules": len(rules_doc["rules"]),
        "addresses": len(lookups["lookups"]),
        "changes": sorted(submission),
    }


# ---- snapshot ----


def build_snapshot(out_dir: Path | None = None) -> dict:
    from engine.api.store import Store

    out = out_dir or config.ARTIFACTS / "web"
    store = Store()
    atomic_write_json(out / "meta.json", store.meta())
    atomic_write_json(out / "addresses.json", store.addresses())
    atomic_write_json(out / "rules.json", store.rules(None, None, None, None, None, None))
    atomic_write_json(out / "findings.json", store.findings(None))
    atomic_write_json(out / "open_questions.json", store.open_questions())
    atomic_write_json(out / "changes.json", store.changes())
    for cid in store._change_files():
        atomic_write_json(out / "changes" / f"{cid.removeprefix('chg-')}.json", store.change(cid))
    for aid in store.records:
        atomic_write_json(out / "timeline" / f"{aid}.json", store.timeline(aid))
    feats = store._features()
    for fid, f in feats.items():
        atomic_write_json(out / "geo" / f"{fid}.json", f)
    atomic_write_json(out / "proof.json", store.proof())
    return {"timelines": len(store.records), "geo": len(feats), "data_version": store.data_version}
