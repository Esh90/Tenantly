"""Self-score that mirrors the published rubric, against our silver key (eval/silver_key.yaml).

This lives outside engine/ on purpose: the pipeline never reads the key or this file
(tests/test_integrity.py enforces it). Run: ``uv run python -m eval.selfscore`` (make score).

Components (max): extraction 25, address coverage 20, citations 15, change tracking 15.
The judged components (plain language 10, responsible design 10, scalability 5) are not scored here.
"""

from __future__ import annotations

import json
import statistics
from datetime import date
from pathlib import Path

import yaml

from engine import config
from engine.compile.assemble import JUR_CODES
from engine.compile.context import cite_key
from engine.compile.verify import span_text_is_exact
from engine.export import build
from engine.io import atomic_write_json
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv
from engine.rules.render import rule_status

KEY = Path(__file__).with_name("silver_key.yaml")
EVAL = config.ARTIFACTS / "eval"
JID = {code: jid for jid, code in JUR_CODES.items()}
DEFAULT = date.fromisoformat(config.DEFAULT_AS_OF)
KIND_OK = {
    "R": lambda r: r.lifecycle == "enacted" and r.citation.tier in ("A", "B"),
    "C": lambda r: r.citation.tier in ("C", "C1"),
    "P": lambda r: r.lifecycle == "pending",
    "X": lambda r: r.lifecycle == "failed",
}


def load_key() -> dict:
    return yaml.safe_load(KEY.read_text(encoding="utf-8"))


def _cites_match(rule, cites: list[str]) -> bool:
    text = (rule.citation.cite + " " + rule.title).lower()
    keyed = cite_key(rule.citation.cite)
    return all(c.lower() in text or c.lower() in keyed for c in cites)


def _date_ok(rule, expected: str | None) -> bool | None:
    if not expected:
        return None
    out = rule.effective.output()
    if out and out.startswith(expected):
        return True
    lo, hi = rule.effective.lo, rule.effective.hi
    if lo and hi and len(expected) == 10:  # an interval that contains the expected day
        return lo <= date.fromisoformat(expected) <= hi
    return False


def score_extraction(rs, key) -> tuple[float, str, list[dict]]:
    items = [c for c in key["cells"] if c["kind"] in KIND_OK]
    detail, total = [], 0.0
    for it in items:
        jid = JID[it["j"]]
        cands = [
            r
            for r in rs.rules
            if r.jurisdiction.id == jid and r.category == it["cat"] and KIND_OK[it["kind"]](r)
        ]
        if it.get("cites"):
            cands = [r for r in cands if _cites_match(r, it["cites"])]
        best, best_s = None, 0.0
        for r in cands:
            fields = [1.0]  # jurisdiction + category + cite matched
            if it.get("status"):
                fields.append(1.0 if rule_status(r, DEFAULT) == it["status"] else 0.0)
            d = _date_ok(r, it.get("effective"))
            if d is not None:
                fields.append(1.0 if d else 0.0)
            s = sum(fields) / len(fields)
            if s > best_s:
                best, best_s = r, s
        total += best_s
        detail.append({"cell": f"{it['j']}/{it['cat']}/{it['kind']}", "cites": it.get("cites"),
                       "matched": best.rule_id if best else None, "score": round(best_s, 2)})  # fmt: skip
    score = 25 * total / len(items)
    found = sum(1 for d in detail if d["matched"])
    return (
        score,
        f"{found} of {len(items)} expected rules matched by jurisdiction, category and cite; mean field accuracy {total / len(items):.2f}",
        detail,
    )


def score_findings(rs, key) -> dict:
    cells = [c for c in key["cells"] if c["kind"] == "F"]
    have = {(f.jurisdiction.id, f.category): f.reason_code for f in rs.findings}
    got = sum(1 for c in cells if (JID[c["j"]], c["cat"]) in have)
    reason_ok = sum(
        1 for c in cells if c.get("reason") and have.get((JID[c["j"]], c["cat"])) == c["reason"]
    )
    reasons = sum(1 for c in cells if c.get("reason"))
    return {
        "expected_cells": len(cells),
        "cells_with_finding": got,
        "reason_codes_expected": reasons,
        "reason_codes_matched": reason_ok,
    }


def score_coverage(rs, records, key) -> tuple[float, str, list[dict]]:
    total, n, detail = 0.0, 0, []
    for aid, spec in key["addresses"].items():
        rec = records[aid]
        res = evaluate_address(rs, rec, AddressEnv(rec), DEFAULT)
        for code, cat, expected in spec["expect"]:
            got = {
                o.result
                for o in res.outcomes
                if o.rule.jurisdiction.id == JID[code] and o.rule.category == cat
            }
            if expected == "omitted":
                pts = 1.0 if not got else -1.0
            elif expected in got:
                pts = 1.0
            elif "unknown" in got and expected != "unknown":
                pts = 0.5
            elif expected == "applies":
                pts = -2.0
            else:
                pts = -1.0
            total += pts
            n += 1
            detail.append(
                {
                    "address": aid,
                    "cell": f"{code}/{cat}",
                    "expected": expected,
                    "got": sorted(got),
                    "points": pts,
                }
            )
    score = 20 * max(0.0, total / n)
    return (
        score,
        f"{sum(1 for d in detail if d['points'] == 1.0)} of {n} address expectations exactly right; a missed 'applies' costs 2, unknown earns half",
        detail,
    )


def score_citations(rs, records) -> tuple[float, str]:
    raw = {}
    by_id = {r.rule_id: r for r in rs.rules}
    applied, backed = 0, 0
    for aid in sorted(records):
        rec = records[aid]
        for o in evaluate_address(rs, rec, AddressEnv(rec), DEFAULT).outcomes:
            if o.result != "applies":
                continue
            applied += 1
            c = by_id[o.rule_id].citation
            if c.tier in ("A", "B") and c.quote_source == "corpus" and c.char_start is not None:
                if c.doc_id not in raw:
                    raw[c.doc_id] = (config.TEXT_DIR / f"{c.doc_id}.txt").read_text(
                        encoding="utf-8"
                    )
                if span_text_is_exact(raw[c.doc_id], c.char_start, c.char_end, c.quote):
                    backed += 1
    share = backed / applied if applied else 0.0
    return (
        15 * share,
        f"{backed} of {applied} 'applies' answers cite a quote found at its stored offsets in the corpus ({share:.1%})",
    )


def jaccard(a: set, b: set) -> float:
    return 1.0 if not a and not b else len(a & b) / len(a | b)


def expected_changes(records) -> dict:
    ids = lambda f: sorted(a for a, r in records.items() if f(r))  # noqa: E731
    return {
        "T1": (ids(lambda r: r["state"] == "CA"), []),
        "T2": (ids(lambda r: r["city_id"] in ("NJ-3432250", "NJ-3436000")), []),
        "T3": (ids(lambda r: r["state"] == "NJ"), ids(lambda r: r["city_id"] in ("NJ-3432250", "NJ-3436000"))),
        "T4": (ids(lambda r: r["state"] == "MA"), []),
        "T5": ([], []),
    }  # fmt: skip


def score_changes(records) -> tuple[float, str, list[dict]]:
    sub = json.loads((config.OUT / "changes.json").read_text(encoding="utf-8"))
    exp = expected_changes(records)
    parts, checks = [], []
    for tid, (ea, ec) in exp.items():
        got = sub.get(tid, {"affected_address_ids": [], "conflict_flag_address_ids": []})
        ja = jaccard(set(got["affected_address_ids"]), set(ea))
        jc = jaccard(set(got["conflict_flag_address_ids"]), set(ec))
        parts.append(ja)
        if tid == "T3":
            parts.append(jc)
        checks.append({"test_id": tid, "passed": ja == 1.0 and jc == 1.0, "affected": len(got["affected_address_ids"]),
                       "expected": len(ea), "conflicts": len(got["conflict_flag_address_ids"]), "expected_conflicts": len(ec)})  # fmt: skip
    score = 15 * sum(parts) / len(parts)
    return (
        score,
        f"{sum(c['passed'] for c in checks)} of {len(checks)} tests match the expected sets exactly (Jaccard mean {sum(parts) / len(parts):.2f})",
        checks,
    )


def patch_change_events(checks: list[dict]) -> None:
    for c in checks:
        p = config.ARTIFACTS / "changes" / f"{c['test_id']}.json"
        if p.exists():
            ev = json.loads(p.read_text(encoding="utf-8"))
            ev["expected_check"] = {
                "passed": c["passed"],
                "detail": f"affected {c['affected']} of expected {c['expected']}; conflict flags {c['conflicts']} of expected {c['expected_conflicts']}",
            }
            atomic_write_json(p, ev)


def reading_level(rs) -> dict:
    grades = [r.grade_level_en for r in rs.rules if r.grade_level_en is not None]
    es = sum(1 for r in rs.rules if r.plain.get("summary_es") and r.plain.get("who_es"))
    return {"mean_grade_en": round(statistics.mean(grades), 2) if grades else 0.0,
            "max_grade_en": round(max(grades), 2) if grades else 0.0,
            "es_coverage": round(es / max(1, len(rs.rules)), 3),
            "templated": sum(1 for r in rs.rules if r.provenance.get("plain_template"))}  # fmt: skip


def main() -> str:
    rs, records, key = build.load_ruleset(), build.load_records(), load_key()
    e, en, ed = score_extraction(rs, key)
    c, cn, cd = score_coverage(rs, records, key)
    q, qn = score_citations(rs, records)
    ch, chn, checks = score_changes(records)
    comps = [
        {"name": "Extraction", "score": round(e, 2), "max": 25, "note": en},
        {"name": "Address coverage", "score": round(c, 2), "max": 20, "note": cn},
        {"name": "Citations", "score": round(q, 2), "max": 15, "note": qn},
        {"name": "Change tracking", "score": round(ch, 2), "max": 15, "note": chn},
    ]  # fmt: skip
    total = sum(x["score"] for x in comps)
    lines = ["Tenantly self-score against the silver key (not the official scorer)", ""]
    lines += [f"{x['name']:<18} {x['score']:>6.2f} / {x['max']:<3} {x['note']}" for x in comps]
    lines += [
        "",
        f"Automatic components total {total:.2f} / 75",
        "Judged components (plain language, responsible design, scalability) are not scored here.",
    ]
    report = "\n".join(lines)
    atomic_write_json(EVAL / "selfscore.json", {"components": comps, "key": "silver", "raw_report": report,
                                                "extraction_detail": ed, "coverage_detail": cd,
                                                "findings": score_findings(rs, key)})  # fmt: skip
    atomic_write_json(EVAL / "changes_check.json", checks)
    atomic_write_json(EVAL / "reading_level.json", reading_level(rs))
    patch_change_events(checks)
    return report


if __name__ == "__main__":
    print(main())
