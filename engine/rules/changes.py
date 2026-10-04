"""Typed change tests (PLAN.md 8.7): as_of, boundary, pending, negative.

The affected set is the set of addresses whose results for the mapped rules differ between two
dates (or that a rule reaches on one date). Test rule ids from the challenge map to our rules
deterministically; an ambiguous mapping raises an error and never guesses.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from engine.ir import Rule, RuleSet
from engine.rules.engine import AddressResult, Policy, evaluate_address
from engine.rules.facts_env import AddressEnv

PREFIX_JURISDICTION = {
    "CA": "CA", "NJ": "NJ", "MA": "MA", "JC": "NJ-3436000", "HOB": "NJ-3432250",
}  # fmt: skip
TOKEN_CATEGORY = {"ALG": "algorithmic_rent_setting", "RENT": "rent_increase_limits"}
BILL_ID = re.compile(r"\b([SH])\.\s?(\d+)\b")


class AmbiguousMapping(ValueError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def map_test_rule(test_rule_id: str, test: dict, ruleset: RuleSet) -> str:
    """Map a challenge test rule id (CA-ALG-01, JC-ALG-01, MA-ALG-P1, ...) to one of our rules."""
    for r in ruleset.rules:
        if r.rule_id == test_rule_id:
            return r.rule_id
    parts = test_rule_id.split("-")
    if len(parts) != 3 or parts[0] not in PREFIX_JURISDICTION or parts[1] not in TOKEN_CATEGORY:
        raise AmbiguousMapping(f"cannot map {test_rule_id!r}")
    jur, cat, suffix = PREFIX_JURISDICTION[parts[0]], TOKEN_CATEGORY[parts[1]], parts[2]
    cands = [r for r in ruleset.rules if r.jurisdiction.id == jur and r.category == cat]
    if suffix.startswith("P"):
        index = int(suffix[1:]) - 1
        cands = [r for r in cands if r.lifecycle in ("pending", "failed")]
        bills = [f"{m.group(1)}.{m.group(2)}" for m in BILL_ID.finditer(test["title"])]
        if bills and index < len(bills):
            want = _norm(bills[index])
            cands = [
                r for r in cands if want in _norm(r.citation.cite + r.title + r.citation.quote)
            ]
    else:
        cands = [r for r in cands if r.lifecycle == "enacted"]
    if len(cands) != 1:
        raise AmbiguousMapping(
            f"{test_rule_id!r} maps to {len(cands)} rules: {[r.rule_id for r in cands]}"
        )
    return cands[0].rule_id


@dataclass
class Affected:
    address_id: str
    before: list[tuple[str, str]]  # (rule_id, result or "none")
    after: list[tuple[str, str]]
    conflict_flag: bool


@dataclass
class ChangeOutput:
    test_id: str
    test_type: str
    title: str
    rule_ids: list[str]
    compare: dict
    affected: list[Affected] = field(default_factory=list)
    conflict_ids: list[str] = field(default_factory=list)
    notes: str = ""

    @property
    def affected_ids(self) -> list[str]:
        return sorted(a.address_id for a in self.affected)


def _snapshot(res: AddressResult, rule_ids: list[str]) -> list[tuple[str, str]]:
    by = res.by_rule()
    return [(rid, by[rid].result if rid in by else "none") for rid in rule_ids]


def _evaluate(ruleset, record, d, policy, user=None):
    return evaluate_address(ruleset, record, AddressEnv(record, user), d, policy)


def run_test(
    test: dict, ruleset: RuleSet, records: dict[str, dict], policy: Policy | None = None
) -> ChangeOutput:
    ids = [map_test_rule(r, test, ruleset) for r in test["rule_ids"]]
    kind = test["type"]
    states = set(test.get("states") or [])
    pool = [records[a] for a in sorted(records) if not states or records[a]["state"] in states]
    out = ChangeOutput(test["test_id"], kind, test["title"], ids, {})

    if kind == "as_of":
        before, after = (
            date.fromisoformat(test["as_of_before"]),
            date.fromisoformat(test["as_of_after"]),
        )
        out.compare = {"before": before.isoformat(), "after": after.isoformat()}
        conflict_ids = ids + [
            map_test_rule(r, test, ruleset) for r in test.get("conflict_with", [])
        ]
        moves: Counter = Counter()
        for rec in pool:
            rb, ra = _evaluate(ruleset, rec, before, policy), _evaluate(ruleset, rec, after, policy)
            sb, sa = _snapshot(rb, ids), _snapshot(ra, ids)
            flagged = bool(test.get("conflict_with")) and any(
                o.conflict_flag for o in ra.outcomes if o.rule_id in conflict_ids
            )
            if sb != sa:
                out.affected.append(Affected(rec["address_id"], sb, sa, flagged))
                moves[(tuple(r for _, r in sb), tuple(r for _, r in sa))] += 1
            if flagged:
                out.conflict_ids.append(rec["address_id"])
        out.notes = _as_of_notes(test, ids, before, after, out, len(pool), moves, conflict_ids)
    elif kind == "boundary":
        on = date.fromisoformat(test["as_of"])
        out.compare = {"on": on.isoformat()}
        split: Counter = Counter()
        for rec in pool:
            res = _evaluate(ruleset, rec, on, policy)
            snap = _snapshot(res, ids)
            hit = [rid for rid, r in snap if r in ("applies", "unknown")]
            if hit:
                out.affected.append(Affected(rec["address_id"], snap, snap, False))
                for rid in hit:
                    split[rid] += 1
        parts = ", ".join(f"{rid} reaches {split[rid]}" for rid in ids)
        out.notes = (
            f"On {on.isoformat()}, {len(out.affected)} of {len(pool)} addresses are reached by "
            f"{' or '.join(ids)}: {parts}."
        )
    elif kind == "pending":
        on = date.fromisoformat(test["as_of"])
        out.compare = {"on": on.isoformat()}
        for rec in pool:
            res = _evaluate(ruleset, rec, on, policy)
            by = res.by_rule()
            reach = [
                rid
                for rid in ids
                if rid in by and by[rid].result == "pending" and by[rid].would_reach
            ]
            if reach:
                snap = _snapshot(res, ids)
                out.affected.append(Affected(rec["address_id"], snap, snap, False))
        out.notes = (
            f"On {on.isoformat()}, {' and '.join(ids)} are pending, not law. "
            f"{len(out.affected)} of {len(pool)} addresses would be reached if enacted."
        )
    elif kind == "negative":
        on = date.fromisoformat(test["as_of"])
        out.compare = {"on": on.isoformat()}
        failed = [r.rule_id for r in ruleset.rules if r.rule_id in ids and r.lifecycle == "failed"]
        for rec in pool:
            res = _evaluate(ruleset, rec, on, policy)
            snap = _snapshot(res, ids)
            if any(r != "none" for _, r in snap):
                out.affected.append(Affected(rec["address_id"], snap, snap, False))
        out.notes = (
            f"On {on.isoformat()}, {' and '.join(failed) or 'no mapped rule'} recorded as failed; "
            f"{len(out.affected)} addresses receive a result from it."
        )
    else:
        raise ValueError(f"unsupported test type {kind!r}")
    out.affected.sort(key=lambda a: a.address_id)
    out.conflict_ids = sorted(set(out.conflict_ids))
    return out


def _as_of_notes(test, ids, before, after, out, pool_size, moves, conflict_ids) -> str:
    states = ", ".join(test.get("states") or ["all states"])
    split = "; ".join(
        f"{n} addresses: {'/'.join(a)} -> {'/'.join(b)}" for (a, b), n in sorted(moves.items())
    )
    text = (
        f"Compared {before.isoformat()} with {after.isoformat()} for {', '.join(ids)} "
        f"({states}). {len(out.affected)} of {pool_size} addresses change"
        + (f" ({split})." if split else ".")
    )
    if test.get("conflict_with"):
        text += (
            f" {len(out.conflict_ids)} carry a conflict flag on {after.isoformat()} "
            f"(possible preemption between {' and '.join(conflict_ids)}), for human review."
        )
    return text


def run_all(
    tests: list[dict], ruleset: RuleSet, records: dict[str, dict], policy: Policy | None = None
) -> dict[str, ChangeOutput]:
    return {t["test_id"]: run_test(t, ruleset, records, policy) for t in tests}


def rules_by_id(ruleset: RuleSet) -> dict[str, Rule]:
    return {r.rule_id: r for r in ruleset.rules}
