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
from engine.compile.context import cite_key, jurisdiction_for
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


def _in_source(sig: dict, mats: Materials) -> bool:
    t = mats.text.get(sig["source"])
    if t is None:
        return False
    norm = lambda s: re.sub(r"\s+", " ", s).strip()  # noqa: E731
    return len(norm(sig["text"])) >= 8 and norm(sig["text"]) in norm(t)


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
        sigs = [s for s in law.get("signals", []) if _in_source(s, mats)]
        sources = sorted(
            {
                s["source"].split(":")[0] if s["source"].startswith("link") else s["source"]
                for s in sigs
            }
        )
        entry = {"jurisdiction": law.get("jurisdiction"), "category": law.get("category"),
                 "citation": law.get("citation"), "status": law.get("status_claim"),
                 "signals": len(sigs), "sources": sources}  # fmt: skip
        try:
            jur = jurisdiction_for(law["jurisdiction"])
        except KeyError:
            audit.append({**entry, "skipped": "jurisdiction not in scope"})
            continue
        if law.get("category") not in CATEGORIES or not sigs:
            audit.append({**entry, "skipped": "no verified signal"})
            continue
        lifecycle = law["status_claim"]
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
        sigs.sort(key=lambda s: (s["source"] != BRIEF_NAME, s["source"]))
        best = sigs[0]
        span = _exact_span(best, mats)
        link_sig = next((s for s in sigs if s["source"].startswith("link:")), None)
        link_doc = link_sig["source"].split(":", 1)[1] if link_sig else None
        link = next((link for link in links if link.doc_id == link_doc), None)
        parsed = _brief_date(law.get("date_claim"))
        eff = (
            DateValue(lo=parsed[0], hi=parsed[1], precision=parsed[2], derivation="brief_reference")  # type: ignore[arg-type]
            if parsed and lifecycle == "enacted" else DateValue()
        )  # fmt: skip
        note = (
            f"Source text not supplied (link-only). Quoted span is from {best['source']}, not the "
            f"ordinance. Signals: {', '.join(sources)}."
        )
        rules.append(
            Rule(
                rule_id=f"tmp-C-{jur.id}-{law['category']}-{cite_key(law['citation'])}",
                category=law["category"], jurisdiction=jur, title=str(law["citation"])[:120],
                requirement=f"{law['citation']} is reported by the supplied materials; its text was not supplied.",
                coverage={"const": True},
                coverage_text="Reported to cover rentals in the jurisdiction; the ordinance text was not supplied.",
                lifecycle=lifecycle, effective=eff,
                citation=Citation(
                    doc_id=link_doc or "SUPP", cite=str(law["citation"]), url=link.url if link else BRIEF_NAME,
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
