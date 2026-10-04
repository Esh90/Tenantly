"""METHOD_NOTE.md and the README results tables, generated from artifacts/eval (measured values
only; a value that has not been measured stays a visible placeholder)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from engine import config
from engine.compile.verify import span_text_is_exact
from engine.export.build import load_ruleset

EVAL = config.ARTIFACTS / "eval"
PLACEHOLDER = "‹measured›"


def _read(name: str, default=None):
    p = EVAL / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def measured() -> dict:
    rs = load_ruleset()
    ver = _read("verification.json", {})
    facts = _read("facts_report.json", {})
    geo = _read("geo_report.json", {})
    score = _read("selfscore.json", {"components": []})
    checks = {c["test_id"]: c for c in _read("changes_check.json", [])}
    ledger = json.loads((config.ARTIFACTS / "ledger.json").read_text(encoding="utf-8"))
    plain = _read("reading_level.json", {})
    lat = _read("latency.json")
    ab = [r for r in rs.rules if r.citation.tier in ("A", "B")]
    exact = 0
    cache: dict[str, str] = {}
    for r in ab:
        c = r.citation
        if c.doc_id not in cache:
            cache[c.doc_id] = (config.TEXT_DIR / f"{c.doc_id}.txt").read_text(encoding="utf-8")
        exact += bool(
            c.char_start is not None
            and span_text_is_exact(cache[c.doc_id], c.char_start, c.char_end, c.quote)
        )
    return {"rs": rs, "ver": ver, "facts": facts, "geo": geo, "score": score, "checks": checks,
            "ledger": ledger, "plain": plain, "lat": lat, "ab": len(ab), "exact": exact}  # fmt: skip


def comp(m: dict, name: str) -> str:
    c = next((x for x in m["score"]["components"] if x["name"] == name), None)
    return f"{c['score']:.1f} / {c['max']}" if c else PLACEHOLDER


def change_cells(m: dict, tid: str) -> tuple[str, str]:
    c = m["checks"].get(tid)
    if not c:
        return PLACEHOLDER, "-"
    ours = f"{c['affected']} affected" + (
        f", {c['conflicts']} conflict flags" if c["expected_conflicts"] or c["conflicts"] else ""
    )
    return ours, "✓" if c["passed"] else "✗"


def integrity_rows(m: dict) -> dict[str, str]:
    t = m["ver"].get("tier_counts", {})
    g, f, p, led = m["geo"], m["facts"], m["plain"], m["ledger"]
    rows = {
        "Rules extracted (Tier A / B / C / C1)": " / ".join(
            str(t.get(k, 0)) for k in ("A", "B", "C", "C1")
        ),
        "Tier A/B quotes verified byte-for-byte against the corpus": f"{m['exact']} of {m['ab']} ({m['exact'] / max(1, m['ab']):.0%}) (target 100%)",
        "Candidate rules rejected because their quote wasn't in the source": str(
            m["ver"].get("rejected_candidates", PLACEHOLDER)
        ),
        "Fields resolved by the adjudicator model": str(
            m["ver"].get("adjudicated_fields", PLACEHOLDER)
        ),
        "Buildings resolved by geometry / mailing-city mismatches caught": f"{g.get('addresses', 0) - g.get('unmatched', 0)} / {g.get('mailing_mismatches', 0)}",
        "Suspect ZIP codes dropped before geocoding": str(f.get("zip_suspect", PLACEHOLDER)),
        "Unit counts recovered from public-record descriptions": str(
            f.get("derived_units", PLACEHOLDER)
        ),
        "Public records that contradict each other (flagged, never guessed)": str(
            f.get("record_conflicts", PLACEHOLDER)
        ),
        "Mean reading grade of renter summaries (EN)": f"{p['mean_grade_en']} (max {p['max_grade_en']}; gate ≤ 8.5)"
        if p
        else PLACEHOLDER,
        "Total model spend to compile the corpus": f"${led['total_usd']:.2f} of a ${led['cap_usd']:.2f} cap",
    }
    if m["lat"]:
        rows["Lookup latency p50 / p95 (server)"] = (
            f"{m['lat']['lookup_p50_ms']:.1f} ms / {m['lat']['lookup_p95_ms']:.1f} ms"
        )
        if m["lat"].get("llm_baseline_ms"):
            rows["Same question via retrieval + LLM (baseline)"] = (
                f"{m['lat']['llm_baseline_ms'] / 1000:.1f} s"
            )
    return rows


def fill_readme(path: Path | None = None) -> int:
    """Replace placeholders in the README results tables. Returns how many cells were filled."""
    m = measured()
    path = path or config.ROOT / "README.md"
    lines = path.read_text(encoding="utf-8").split("\n")
    rows = integrity_rows(m)
    comp_map = {
        "Extraction accuracy": "Extraction",
        "Address coverage": "Address coverage",
        "Citations": "Citations",
        "Change tracking": "Change tracking",
    }
    filled = 0
    for i, ln in enumerate(lines):
        if PLACEHOLDER not in ln and "‹✓/✗›" not in ln:
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if cells[0] in comp_map and len(cells) == 3:
            lines[i] = f"| {cells[0]} | {cells[1]} | {comp(m, comp_map[cells[0]])} |"
            filled += 1
        elif re.fullmatch(r"T[1-5]", cells[0]) and len(cells) == 5:
            ours, ok = change_cells(m, cells[0])
            lines[i] = f"| {cells[0]} | {cells[1]} | {cells[2]} | {ours} | {ok} |"
            filled += 1
        elif cells[0] in rows and len(cells) == 2:
            lines[i] = f"| {cells[0]} | {rows[cells[0]]} |"
            filled += 1
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return filled


def build_note(m: dict) -> str:
    rows = integrity_rows(m)
    rs = m["rs"]
    comps = "\n".join(
        f"| {c['name']} | {c['score']:.1f} / {c['max']} | {c['note']} |"
        for c in m["score"]["components"]
    )
    ch = "\n".join(
        f"| {t} | {c['affected']} (expected {c['expected']}) | {c['conflicts']} (expected {c['expected_conflicts']}) | {'pass' if c['passed'] else 'differs'} |"
        for t, c in sorted(m["checks"].items())
    )
    integ = "\n".join(f"| {k} | {v} |" for k, v in rows.items())
    return f"""# Tenantly: method note

*Information, not legal advice.*

## Problem
Which housing rules apply to one apartment on a given date? Rules come from state statutes, city
ordinances and pending bills; each has coverage tests (building age, unit count, owner type),
effective dates and exemptions, and the answer depends on the building's legal city and the date.

## Pipeline
1. **Compile the law, offline.** Each of the 54 supplied documents is read in two
   passes (Claude Sonnet by section, Claude Haiku over the whole in-force text). Every quote must be an
   exact span of the source file at stored offsets, or the rule is discarded. Disagreements between the
   passes go to an adjudicator that must cite the deciding span. No model is called when an address is looked up.
2. **Dates are computed, not guessed.** The model reports date expressions; a deterministic legal calendar
   computes dates ("first day of the twelfth month next following enactment" gives 2027-07-01 for the FAIR Act).
3. **Facts with provenance.** Units and year built come from assessor records, with intervals (a 5-unit use code
   is [5, infinity)); when two records contradict, the fact is unknown and flagged.
4. **Jurisdiction by geometry.** Census TIGER boundaries and point-in-polygon decide the legal city; the
   mailing city never does.
5. **Three-valued logic.** Coverage and exemptions are predicates over a fixed fact registry, evaluated with
   TRUE / FALSE / UNKNOWN over intervals. Unknown is an answer, with the missing fact named.
6. **Precedence and change tracking.** State bars, local-over-state precedence and preemption conflicts are
   explicit relations with quoted evidence; timelines are precomputed per address, and change tests diff them.

## Evidence tiers
A: official law text in the corpus. B: official agency or bill page. C: a law whose text was not supplied but
that two independent supplied signals assert (the quote is supplementary text, labeled, never the ordinance).
C1: one signal; always unknown.

## Measured results
Self-score against our own silver key (the official scorer was not in the pack):

| Component | Score | Note |
|---|---|---|
{comps}

Change tests (computed from resolved legal cities):

| Test | Affected | Conflict flags | Result |
|---|---|---|---|
{ch}

| Metric | Value |
|---|---|
{integ}

## Limitations
- {len(rs.rules)} rules were extracted; some guidance pages yield several near-duplicate records.
- Facts such as owner type are not public; the app asks one question and shows caveats instead of guessing.
- Answers after 2026-10-01 are projections from sources retrieved that day.
- One sample address (a parcel lot with no house number) could not be geocoded; its city rules are unknown.

## Not legal advice
Tenantly describes public law for information. Check the official source or a qualified professional before acting.
"""


def write() -> tuple[str, int]:
    m = measured()
    note = config.ROOT / "METHOD_NOTE.md"
    note.write_text(build_note(m), encoding="utf-8", newline="\n")
    return str(note), fill_readme()
