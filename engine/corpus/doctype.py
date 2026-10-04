"""Deterministic document-type classifier (PLAN.md 11.4).

A motion yields no rule; a bill status page can never produce an in-force rule; a draft
ordinance (blank adoption certificate) is draft material. Haiku is consulted only for documents
this classifier cannot place, which never happens on the supplied corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.corpus.loader import Doc

DOC_TYPES = (
    "statute", "ordinance", "draft_materials", "bill_status", "guidance", "news", "motion",
    "policy",
)  # fmt: skip

_STATUTE_URL = re.compile(
    r"(leginfo\.legislature\.ca\.gov/faces/(codes_displaySection|billNavClient)"
    r"|malegislature\.gov/Laws/|pub\.njleg)",
    re.I,
)
_BLANK_ORDINANCE_NUMBER = re.compile(r"ORDINANCE\s+NUMBER\s+O-_{3,}", re.I)


@dataclass(frozen=True)
class DocClass:
    doc_type: str
    reason: str


def classify(doc: Doc) -> DocClass:
    body = doc.text[doc.body_start :]
    head = body[:800]
    first_lines = [ln.strip() for ln in head.split("\n") if ln.strip()][:6]

    if re.search(r"\bI\s+THEREFORE\s+MOVE\b", body) and any(
        ln.upper() == "MOTION" for ln in first_lines
    ):
        return DocClass("motion", "title MOTION and 'I THEREFORE MOVE'")
    if "malegislature.gov/Bills/" in doc.url:
        return DocClass("bill_status", "malegislature.gov bill page")
    if _STATUTE_URL.search(doc.url):
        return DocClass("statute", "official legislature or statute URL")
    if re.search(r"be it ordained", body, re.I) and _BLANK_ORDINANCE_NUMBER.search(body):
        return DocClass("draft_materials", "ordinance text with a blank adoption number")
    if re.search(r"\bORDINANCE\s+NO\.", head) or re.search(r"be it ordained", body, re.I):
        return DocClass("ordinance", "ordinance heading or enacting clause")
    if "municode" in doc.url.lower():
        return DocClass("ordinance", "municipal code publication")
    if any(
        re.search(r"\bpolicy\b", ln, re.I) for ln in first_lines[:5]
    ) and doc.source_type.startswith("official"):
        return DocClass("policy", "official document titled as a policy")
    if doc.source_type.startswith("official"):
        return DocClass("guidance", "official agency page")
    return DocClass("news", "not an official source")
