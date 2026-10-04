"""Shared helpers for the Law Compiler: jurisdictions, in-force document text, cite keys."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from engine import config
from engine.corpus import boilerplate, doctype, versions
from engine.corpus.loader import Doc, LinkOnlyDoc, load_corpus
from engine.geo.jurisdictions import CITIES, STATES
from engine.ir import JurisdictionRef

DEFAULT_DATE = date.fromisoformat(config.DEFAULT_AS_OF)

CITY_BY_LABEL = {c.label: c for c in CITIES}


def jurisdiction_for(label: str) -> JurisdictionRef:
    """Manifest jurisdiction label ("CA", "Berkeley, CA") to a JurisdictionRef."""
    if label in STATES:
        return JurisdictionRef(
            id=label,
            level="state",
            name=STATES[label][1],
            label=label,
            state=label,  # type: ignore[arg-type]
        )
    c = CITY_BY_LABEL[label]
    return JurisdictionRef(
        id=c.id, level="city", name=c.name, label=c.label, state=c.state,  # type: ignore[arg-type]
        geoid=c.place_geoid,
    )  # fmt: skip


def resolve_jurisdiction(text: str) -> JurisdictionRef:
    """Accept a label ("Berkeley, CA"), a state code or name, or a bare city name."""
    t = text.strip()
    if t in STATES or t in CITY_BY_LABEL:
        return jurisdiction_for(t)
    for code, (_, name) in STATES.items():
        if t.lower() in (name.lower(), f"state of {name.lower()}"):
            return jurisdiction_for(code)
    for c in CITIES:
        if t.lower() in (c.name.lower(), c.label.lower(), f"city of {c.name.lower()}"):
            return jurisdiction_for(c.label)
    raise KeyError(text)


@dataclass
class DocView:
    doc: Doc
    doc_type: str
    jurisdiction: JurisdictionRef
    segments: list[versions.VersionSegment]
    spans: list[tuple[int, int]]  # in-force raw spans
    version_label: str | None
    low_signal: bool
    masked: boilerplate.MaskedDoc

    def model_text(self) -> str:
        """The in-force, boilerplate-free text sent to the model (offsets stay in the raw file)."""
        parts: list[str] = []
        for ln in self.masked.kept_lines():
            if any(a <= ln.start < b for a, b in self.spans) and not versions.MARKER_RE.search(
                ln.text
            ):
                parts.append(ln.text)
        return "\n".join(parts)

    def wrapper(self, text: str) -> str:
        return (
            f'<document doc_id="{self.doc.doc_id}" doc_type="{self.doc_type}" '
            f'jurisdiction="{self.jurisdiction.label}" retrieved_at="{self.doc.retrieved_at}" '
            f'version="{self.version_label or "single"}">\n{text}\n</document>'
        )


def load_views(on: date = DEFAULT_DATE) -> tuple[dict[str, DocView], list[LinkOnlyDoc]]:
    docs, links = load_corpus()
    masked = boilerplate.mask_corpus(docs)
    from engine.corpus import signal

    out: dict[str, DocView] = {}
    for d in docs:
        segs = versions.segment_versions(d.text)
        out[d.doc_id] = DocView(
            doc=d,
            doc_type=doctype.classify(d).doc_type,
            jurisdiction=jurisdiction_for(d.jurisdictions),
            segments=segs,
            spans=versions.in_force_spans(d.text, segs, on),
            version_label=versions.in_force_label(segs, on),
            low_signal=signal.is_low_signal(signal.signal_score(masked[d.doc_id])),
            masked=masked[d.doc_id],
        )
    return out, links


_SECTION_TOKEN = re.compile(r"\d+[a-z]?(?:[.:\-]\d+[a-z]?)*")


def cite_key(cite: str) -> str:
    """Normalized key for a citation: its section numbers, or its alphanumerics if it has none."""
    tokens = _SECTION_TOKEN.findall(cite.lower())
    if tokens:
        return "|".join(tokens)
    return re.sub(r"[^a-z0-9]", "", cite.lower())
