"""Discrepancy and open-question engine (PLAN.md D16, 11.10).

Open questions come from the README's section 9 items, from sources that disagree, from captures
that are partial, and from official pages we could not read. Dates are never invented: where two
sources give two dates, the rule's effective date becomes the interval between them.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from engine import config
from engine.compile import calendar as cal
from engine.compile.context import DocView
from engine.compile.llm import LLM
from engine.compile.tools import EMIT_TRANSLATION, load_prompt
from engine.corpus.loader import LinkOnlyDoc
from engine.ir import Citation, DateValue, OpenQuestion, Relation, Rule

log = logging.getLogger("tenantly.discrepancy")

MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b"
)
BULLET = re.compile(r"^- \*\*(?P<title>.+?)\*\*\s*(?P<detail>.*)$")
ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def readme_items() -> list[dict]:
    text = (config.DATASET / "README.md").read_text(encoding="utf-8")
    section = text.split("## 9.", 1)[1].split("\n## ", 1)[0] if "## 9." in text else ""
    items = []
    for line in section.splitlines():
        m = BULLET.match(line.strip())
        if m:
            detail = f"{m['title']} {m['detail']}".strip()
            items.append({"title": m["title"].strip(), "detail": detail})
    return items


def item_dates(detail: str) -> list[date]:
    out = [date(int(a), int(b), int(c)) for a, b, c in ISO.findall(detail)]
    out += cal.parse_all_dates(detail)
    seen = set(out)
    for m in MONTH_YEAR.finditer(detail):  # "January 2026" has no day: use the first of the month
        d = date(int(m.group(2)), cal.MONTHS[m.group(1).lower()], 1)
        if not any(x.year == d.year and x.month == d.month for x in seen):
            out.append(d)
            seen.add(d)
    return sorted(set(out))


def _match_rules(item: dict, rules: list[Rule]) -> list[Rule]:
    d = item["detail"].lower()
    out: list[Rule] = []
    for r in rules:
        name = r.jurisdiction.name.lower()
        hit = name in d or (
            r.jurisdiction.level == "state"
            and (r.jurisdiction.state.lower() + " " in d + " " and r.jurisdiction.name.lower() in d)
        )
        if (
            not hit
            and "fair act" in d
            and r.jurisdiction.id.startswith("NJ")
            and r.category == "algorithmic_rent_setting"
        ):
            hit = True
        if not hit:
            continue
        if "algorithmic" in d or "13.63" in d or "fair act" in d:
            ok = r.category == "algorithmic_rent_setting"
        elif "rso" in d or "rent" in d:
            ok = r.category == "rent_increase_limits"
        elif "screening" in d:
            ok = r.category == "application_screening_fees"
        else:
            ok = False
        if ok and r.lifecycle == "enacted":
            out.append(r)
    return out


def apply_alternative_dates(
    rules: list[Rule], items: list[dict]
) -> tuple[list[Rule], dict[str, list[date]]]:
    """Where an item gives two dates for a rule whose own text gave none, use the interval."""
    by_id = {r.rule_id: r for r in rules}
    used: dict[str, list[date]] = {}
    for it in items:
        ds = item_dates(it["detail"])
        if len(ds) < 2 or "effective" not in it["detail"].lower():
            continue
        for r in _match_rules(it, rules):
            cur = by_id[r.rule_id]
            if cur.category != "algorithmic_rent_setting" or cur.effective.lo is not None:
                continue
            alts = tuple((d.isoformat(), "dataset README section 9") for d in ds)
            by_id[r.rule_id] = cur.model_copy(update={"effective": DateValue(
                lo=min(ds), hi=max(ds), precision="day", derivation="readme_reference", alternatives=alts)})  # fmt: skip
            used[r.rule_id] = ds
    return [by_id[r.rule_id] for r in rules], used


def _readme_citation(it: dict) -> Citation:
    return Citation(
        doc_id="README", cite="Participant guide, section 9", url="dataset/README.md",
        retrieved_at="2026-10-01", quote=it["detail"][:300] if len(it["detail"]) >= 20 else it["detail"].ljust(20, "."),
        tier="B", quote_source="supplementary", supplementary_doc="README.md",
    )  # fmt: skip


def build_open_questions(
    llm: LLM,
    rules: list[Rule],
    relations: list[Relation],
    views: dict[str, DocView],
    links: list[LinkOnlyDoc],
    date_items: dict[str, list[date]],
) -> list[OpenQuestion]:
    system, version = load_prompt("translate")
    qs: list[OpenQuestion] = []

    def translate(title: str, detail: str) -> dict:
        res = llm.call(stage="translate", model=config.MODEL_FAST, system=system,
                       user=f"title: {title}\ndetail: {detail}", tool=EMIT_TRANSLATION, prompt_version=version,
                       max_tokens=1200)  # fmt: skip
        return {
            "title_es": res.output.get("title_es", title),
            "detail_es": res.output.get("detail_es", detail),
        }

    def add(
        oid: str, title: str, detail: str, ids: list[str], sources: list[Citation], between=None
    ):
        tr = translate(title, detail)
        qs.append(OpenQuestion(oq_id=oid, title={"en": title, "es": tr["title_es"]},
                               detail={"en": detail, "es": tr["detail_es"]}, rule_ids=sorted(ids),
                               sources=sources, changes_answer_between=between))  # fmt: skip

    for n, it in enumerate(readme_items(), start=1):
        matched = _match_rules(it, rules)
        ids = [r.rule_id for r in matched]
        ds = item_dates(it["detail"])
        between = (min(ds), max(ds)) if len(ds) >= 2 else None
        if not between and "preempt" in it["detail"].lower():
            act = next(
                (
                    rel.active_from
                    for rel in relations
                    if rel.effect == "conflict_flag" and rel.active_from
                ),
                None,
            )
            if act:
                between = (act, act)
        extra = ""
        for r in matched:
            if r.rule_id in date_items:
                extra = " The ordinance text we hold has no effective date, so we show the range between the two published dates."
        add(
            f"OQ-{n:02d}",
            it["title"],
            it["detail"].rstrip(".") + "." + extra,
            ids,
            [_readme_citation(it)],
            between,
        )
    n = len(qs)
    for link in links:
        if link.status.startswith("manual"):
            n += 1
            add(f"OQ-{n:02d}", f"Official text could not be read ({link.doc_id})",
                f"The official page for {link.jurisdictions} ({link.url}) could not be captured, so rules from it are not in our sources.",
                [], [])  # fmt: skip
    seen: set[str] = set()
    for r in rules:
        if r.citation.low_signal and r.citation.doc_id not in seen:
            seen.add(r.citation.doc_id)
            n += 1
            add(f"OQ-{n:02d}", f"Partial capture of source {r.citation.doc_id}",
                f"The saved copy of {r.citation.doc_id} is mostly site navigation, so coverage details for {r.title} may be incomplete.",
                [x.rule_id for x in rules if x.citation.doc_id == r.citation.doc_id], [r.citation])  # fmt: skip
    return qs
