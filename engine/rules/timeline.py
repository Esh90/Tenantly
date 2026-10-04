"""Bitemporal timelines (PLAN.md 8.7): every date where any status can change becomes a
breakpoint; each segment is evaluated once and adjacent identical segments are merged.

Semantics: ``sunset`` is the first day the rule is no longer in force ("repealed as of
January 1, 2030" is 2030-01-01), so it is a breakpoint itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from engine import config
from engine.ir import RuleSet
from engine.rules import dsl
from engine.rules.engine import AddressResult, Policy, evaluate_address
from engine.rules.facts_env import AddressEnv

RANGE_START = date.fromisoformat(config.AS_OF_RANGE[0])
RANGE_END = date.fromisoformat(config.AS_OF_RANGE[1])


@dataclass(frozen=True)
class Breakpoint:
    date: date
    rule_ids: tuple[str, ...]
    kinds: tuple[str, ...]  # effective | sunset | relation | key_value | age


@dataclass
class Segment:
    start: date
    end: date | None  # None for the last segment
    result: AddressResult


def collect_breakpoints(
    ruleset: RuleSet,
    record: dict,
    env: dsl.FactEnv,
    start: date = RANGE_START,
    end: date = RANGE_END,
) -> list[Breakpoint]:
    stack = set(record["stack_ids"])
    hits: dict[date, tuple[set[str], set[str]]] = {}

    def add(d: date | None, rule_id: str, kind: str) -> None:
        if d is not None and start < d <= end:
            ids, kinds = hits.setdefault(d, (set(), set()))
            ids.add(rule_id)
            kinds.add(kind)

    for rule in ruleset.rules:
        if rule.jurisdiction.id not in stack and not (
            record["resolution_method"] != "point_in_polygon"
            and rule.jurisdiction.level == "city"
            and rule.jurisdiction.state == record["state"]
        ):
            continue
        rid = rule.rule_id
        add(rule.effective.lo, rid, "effective")
        add(rule.effective.hi, rid, "effective")
        if rule.sunset is not None:
            add(rule.sunset.lo, rid, "sunset")
            add(rule.sunset.hi, rid, "sunset")
        for kv in rule.key_values:
            add(kv.valid_from, rid, "key_value")
            if kv.valid_to is not None:
                add(kv.valid_to + timedelta(days=1), rid, "key_value")
        predicates = [rule.coverage] + [ex.predicate for ex in rule.exemptions]
        for p in predicates:
            for d in dsl.change_dates(dsl.parse(p), env, start, end):
                add(d, rid, "age")
    for rel in ruleset.relations:
        add(rel.active_from, rel.source_rule_id, "relation")
        if rel.condition is not None:
            for d in dsl.change_dates(dsl.parse(rel.condition), env, start, end):
                add(d, rel.source_rule_id, "age")
    return [
        Breakpoint(d, tuple(sorted(ids)), tuple(sorted(kinds)))
        for d, (ids, kinds) in sorted(hits.items())
    ]


def signature(res: AddressResult) -> tuple:
    """What a renter can see; two segments with the same signature are merged."""
    outs = []
    for o in sorted(res.outcomes, key=lambda x: x.rule_id):
        kvs = tuple(
            (kv.name, (kv.valid_from is None or kv.valid_from <= res.as_of)
             and (kv.valid_to is None or res.as_of <= kv.valid_to))
            for kv in o.rule.key_values
        )  # fmt: skip
        outs.append(
            (o.rule_id, o.result, o.would_be, o.would_reach, o.superseded_by, tuple(o.governs_over),
             tuple((c.with_rule_id, c.kind) for c in o.conflicts), tuple(o.caveats),
             tuple(o.missing_facts), tuple(o.notes), kvs)
        )  # fmt: skip
    return (
        tuple(outs),
        tuple(sorted(f.finding_id for f in res.findings)),
        tuple(sorted(r.rule_id for r in res.failed)),
    )


def build_timeline(
    ruleset: RuleSet,
    record: dict,
    user_facts: dict | None = None,
    policy: Policy | None = None,
    ingested: frozenset[str] = frozenset(),
    start: date = RANGE_START,
    end: date = RANGE_END,
) -> list[Segment]:
    env = AddressEnv(record, user_facts)
    bps = collect_breakpoints(ruleset, record, env, start, end)
    starts = [start] + [b.date for b in bps]
    segments: list[Segment] = []
    last_sig = None
    for s in starts:
        res = evaluate_address(ruleset, record, env, s, policy, ingested)
        sig = signature(res)
        if sig == last_sig:
            continue
        if segments:
            segments[-1].end = s
        segments.append(Segment(s, None, res))
        last_sig = sig
    return segments


def segment_at(segments: list[Segment], d: date) -> Segment:
    chosen = segments[0]
    for seg in segments:
        if seg.start <= d:
            chosen = seg
        else:
            break
    return chosen


def transitions(segments: list[Segment], after: date) -> list[dict]:
    """Result changes strictly after a date, per rule: for the 'upcoming' list."""
    out: list[dict] = []
    cur = segment_at(segments, after)
    prev = {o.rule_id: o for o in cur.result.outcomes}
    for seg in segments:
        if seg.start <= after:
            continue
        now = {o.rule_id: o for o in seg.result.outcomes}
        for rid in sorted(set(prev) | set(now)):
            a, b = prev.get(rid), now.get(rid)
            ra = a.result if a else "none"
            rb = b.result if b else "none"
            if ra != rb:
                rule = (b or a).rule
                out.append(
                    {"date": seg.start, "rule_id": rid, "title": rule.title, "from": ra, "to": rb}
                )
        prev = now
    return out
