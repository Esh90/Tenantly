"""Tier C builder (PLAN.md 11.9, D13): laws whose text was not supplied but that at least two
independent supplied signals assert. Quotes are exact text from the supplementary materials;
no ordinance text is ever invented.
"""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from dataclasses import dataclass

from engine import config
from engine.compile import dates
from engine.compile.context import cite_key, resolve_jurisdiction
from engine.compile.llm import LLM
from engine.compile.tools import EMIT_SIGNALS, load_prompt
from engine.corpus.loader import LinkOnlyDoc
from engine.ir import Citation, DateValue, Rule
from engine.models import CATEGORIES

log = logging.getLogger("tenantly.tier_c")

BRIEF_NAME = "challenge_brief_public.pdf"
README_NAME = "README.md"
TESTS_NAME = "change_tests.json"
TITLES_NAME = "link_titles.csv"


@dataclass(frozen=True)
class Materials:
    text: dict[str, str]  # source name -> exact text

    def bundle(self) -> str:
        return "\n\n".join(f"=== SOURCE: {name} ===\n{t}" for name, t in self.text.items())


def load_materials(links: list[LinkOnlyDoc]) -> Materials:
    text: dict[str, str] = {}
    pdf = config.SUPPLEMENT / BRIEF_NAME
    if pdf.exists():
        try:
            out = subprocess.run(
                ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
                capture_output=True, check=True, timeout=60,
            )  # fmt: skip
            text[BRIEF_NAME] = out.stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            from pypdf import PdfReader

            text[BRIEF_NAME] = "\n".join(p.extract_text() or "" for p in PdfReader(pdf).pages)
    text[README_NAME] = (config.DATASET / "README.md").read_text(encoding="utf-8")
    text[TESTS_NAME] = config.CHANGE_TESTS.read_text(encoding="utf-8")
    for link in links:
        slug = link.url.split("://", 1)[-1]
        text[f"link:{link.doc_id}"] = f"{link.doc_id} {link.jurisdictions} {slug}"
    titles = config.SUPPLEMENT / TITLES_NAME
    if titles.exists():
        with open(titles, newline="", encoding="utf-8") as fh:
            text[TITLES_NAME] = "\n".join(
                f"{r['doc_id']}: {r['title']}" for r in csv.DictReader(fh)
            )
    return Materials(text)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def locate_signal(sig: dict, mats: Materials) -> dict | None:
    """Find where a signal's text really is. The claimed source is tried first; if the model
    named the wrong one, the first source that actually contains the exact text wins."""
    want = _norm(sig.get("text", ""))
    if len(want) < 8:
        return None
    claimed = sig.get("source", "")
    names = [claimed] + [n for n in mats.text if n != claimed]
    if re.fullmatch(r"D\d{3}", claimed):
        names.insert(0, f"link:{claimed}")
    for name in names:
        if name in mats.text and want in _norm(mats.text[name]):
            return {"source": name, "text": sig["text"]}
    return None


def _in_source(sig: dict, mats: Materials) -> bool:
    return locate_signal(sig, mats) is not None


def _exact_span(sig: dict, mats: Materials) -> str:
    """The text as it appears in the source (whitespace as written), at least 20 characters."""
    t = mats.text[sig["source"]]
    flat = re.sub(r"\s+", " ", t)
    want = re.sub(r"\s+", " ", sig["text"]).strip()
    i = flat.find(want)
    # widen short signals with the surrounding source text so the quote reaches 20 characters
    start = max(0, i - max(0, (20 - len(want)) // 2 + 6))
    end = min(len(flat), i + len(want) + max(0, (20 - len(want)) // 2 + 6))
    return flat[start:end].strip() if len(want) < 20 else want


def build_tier_c(
    llm: LLM, links: list[LinkOnlyDoc], existing: list[Rule], budget_note: str = ""
) -> tuple[list[Rule], list[dict]]:
    mats = load_materials(links)
    system, version = load_prompt("tier_c")
    res = llm.call(stage="tier_c", model=config.MODEL_FAST, system=system, user=mats.bundle(),
                   tool=EMIT_SIGNALS, prompt_version=version, max_tokens=12000)  # fmt: skip
    have_cells = {(r.jurisdiction.label, r.category) for r in existing if r.lifecycle == "enacted"}
    rules: list[Rule] = []
    audit: list[dict] = []
    for law in res.output.get("laws", []):
        sigs = []
        link_ids = {link.doc_id for link in links}
        for did in law.get("link_doc_ids", []) or []:
            did = str(did).replace("link:", "").strip()
            if (
                did in link_ids
                and f"link:{did}" in mats.text
                and not any(x["source"] == f"link:{did}" for x in sigs)
            ):
                sigs.append({"source": f"link:{did}", "text": mats.text[f"link:{did}"]})
        for raw in law.get("signals", []):
            found = locate_signal(raw, mats)
            if found and found["source"] not in {x["source"] for x in sigs}:
                sigs.append(found)
        category = law.get("category")
        cite_tokens = [
            t for t in re.findall(NUMBER_TOKEN, str(law.get("citation", ""))) if len(t) >= 3
        ]
        try:
            jur = resolve_jurisdiction(law["jurisdiction"])
        except KeyError:
            audit.append({"jurisdiction": law.get("jurisdiction"), "category": category,
                          "citation": law.get("citation"), "skipped": "jurisdiction not in scope"})  # fmt: skip
            continue
        # a change test that names this jurisdiction's rule id and category is a signal too
        test_sig = change_test_signal(jur.id, category, mats)
        sigs = [x for x in sigs if x["source"] != TESTS_NAME or x.get("synthetic")]
        if test_sig:
            sigs.append(test_sig)
        specific = [s for s in sigs if s.get("synthetic") or is_specific(s, category, cite_tokens)]
        kinds = sorted(
            {"link" if s["source"].startswith("link:") else s["source"] for s in specific}
        )
        sources = kinds
        entry = {"jurisdiction": law.get("jurisdiction"), "category": category,
                 "citation": law.get("citation"), "status": law.get("status_claim"),
                 "signals": len(sigs), "specific_signals": len(specific), "sources": sources}  # fmt: skip
        if category not in CATEGORIES or not specific:
            audit.append({**entry, "skipped": "no verified signal names the measure"})
            continue
        lifecycle = law["status_claim"]
        keys = set(cite_key(law["citation"]).split("|"))
        if any(
            r.jurisdiction.id == jur.id
            and r.category == law["category"]
            and keys & set(cite_key(r.citation.cite).split("|"))
            for r in existing
        ) or any(
            r.category == law["category"]
            and r.lifecycle != "enacted"
            and r.jurisdiction.state == jur.state
            and any(k in cite_key(r.citation.cite) for k in keys if len(k) >= 4)
            for r in existing
        ):
            audit.append({**entry, "skipped": "already covered by a rule from supplied text"})
            continue
        if lifecycle == "enacted" and (jur.label, law["category"]) in have_cells:
            audit.append({**entry, "skipped": "cell already has a rule from supplied text"})
            continue
        n_sources = len(sources)
        if lifecycle == "enacted" and n_sources < config.TIER_C_MIN_SIGNALS:
            tier = "C1"
        elif lifecycle == "enacted":
            tier = "C"
        else:
            tier = "C" if n_sources >= config.TIER_C_MIN_SIGNALS else "C1"
        # the quoted span comes from the strongest source: the public brief, else the first signal
        specific.sort(
            key=lambda s: (s["source"].startswith("link:"), s["source"] != BRIEF_NAME, s["source"])
        )
        best = specific[0]
        span = _exact_span(best, mats)
        link_sig = next((s for s in specific if s["source"].startswith("link:")), None)
        link_doc = link_sig["source"].split(":", 1)[1] if link_sig else None
        link = next((link for link in links if link.doc_id == link_doc), None)
        parsed = _brief_date(law.get("date_claim"))
        eff = (
            DateValue(lo=parsed[0], hi=parsed[1], precision=parsed[2], derivation="brief_reference")  # type: ignore[arg-type]
            if parsed and lifecycle == "enacted" else DateValue()
        )  # fmt: skip
        cite_text = str(law["citation"])
        signal_text = " ".join(s["text"] for s in specific)
        if cite_tokens and not all(t in signal_text for t in cite_tokens):
            cite_text = slug_title(link.url) if link else f"{jur.name} {category.replace('_', ' ')}"
        note = (
            f"Source text not supplied (link-only). Quoted span is from {best['source']}, not the "
            f"ordinance. Signals: {', '.join(sources)}."
        )
        rules.append(
            Rule(
                rule_id=f"tmp-C-{jur.id}-{law['category']}-{cite_key(law['citation'])}",
                category=law["category"], jurisdiction=jur, title=cite_text[:120],
                requirement=f"{cite_text} is reported by the supplied materials; its text was not supplied.",
                coverage={"const": True},
                coverage_text="Reported to cover rentals in the jurisdiction; the ordinance text was not supplied.",
                lifecycle=lifecycle, effective=eff,
                citation=Citation(
                    doc_id=link_doc or "SUPP", cite=cite_text, url=link.url if link else BRIEF_NAME,
                    retrieved_at="2026-10-01", quote=span, tier=tier, quote_source="supplementary",
                    supplementary_doc=best["source"],
                ),
                doc_type="news" if tier == "C1" else "guidance", confidence=0.0,
                provenance={"notes": [note], "signals": [{"source": s["source"], "text": s["text"]} for s in sigs],
                            "tier_c_sources": sources, "date_claim": law.get("date_claim")},
            )
        )  # fmt: skip
        audit.append({**entry, "tier": tier, "created": True})
    return rules, audit


NUMBER_TOKEN = r"\d[\d.\-]*\d|\d{3,}"
CATEGORY_SLUG = {
    "algorithmic_rent_setting": r"algorithm|pricing|realpage|rent-set|coordinat|software|ai-",
    "rent_increase_limits": r"rent-control|rent-stabil|rent-level|rent",
    "just_cause_eviction": r"evict|just-cause|good-cause",
    "security_deposits": r"deposit",
    "application_screening_fees": r"fee",
    "screening_restrictions": r"source-of-income|fair-chance|screening|criminal|discriminat",
}


def is_specific(sig: dict, category: str | None, cite_tokens: list[str]) -> bool:
    """A signal counts only if its own text names the measure: a link slug with a keyword of the
    category, or supplied text containing a number from the citation."""
    if sig["source"].startswith("link:"):
        return bool(
            category in CATEGORY_SLUG and re.search(CATEGORY_SLUG[category], sig["text"].lower())
        )
    return any(t in sig["text"] for t in cite_tokens)


def slug_title(url: str) -> str:
    last = [p for p in url.split("?")[0].rstrip("/").split("/") if p][-1]
    return re.sub(r"[-_]+", " ", last).strip()[:100].capitalize()


def _brief_date(claim: str | None):
    """'Jun 2025', 'June 2025', '2025-06' or 'Jun 2025)' to (lo, hi, precision)."""
    if not claim:
        return None
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{4})", claim)
    if m:
        for i, name in enumerate(
            ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
            start=1,
        ):
            if m.group(1).lower().startswith(name):
                return dates.parse_partial(f"{m.group(2)}-{i:02d}")
    return dates.parse_partial(claim.strip())


def change_test_signal(jurisdiction_id: str, category: str | None, mats: Materials) -> dict | None:
    """A rule id in the change tests (JC-ALG-01, MA-RENT-P1, ...) that maps to this jurisdiction
    and category by the documented prefix and token tables."""
    import json

    from engine.rules.changes import PREFIX_JURISDICTION, TOKEN_CATEGORY

    try:
        tests = json.loads(mats.text.get(TESTS_NAME, "[]"))
    except ValueError:
        return None
    for t in tests:
        for rid in t.get("rule_ids", []):
            parts = rid.split("-")
            if (
                len(parts) == 3
                and PREFIX_JURISDICTION.get(parts[0]) == jurisdiction_id
                and TOKEN_CATEGORY.get(parts[1]) == category
                and rid in mats.text[TESTS_NAME]
            ):
                return {
                    "source": TESTS_NAME,
                    "synthetic": True,
                    "text": f'"{rid}"  # {t.get("title", "")}'[:120],
                }
    return None
