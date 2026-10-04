"""Corpus loader (PLAN.md 9.1). The manifest is ground truth for metadata.

Offsets used everywhere (quotes, versions, sections) are indices into ``Doc.text``, which is the
raw file decoded as UTF-8 with no newline translation.
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from engine import config


@dataclass(frozen=True)
class Doc:
    doc_id: str
    url: str  # from the manifest (authoritative)
    retrieved_at: str  # from the manifest (authoritative)
    jurisdictions: str
    source_type: str
    manifest_sha256: str
    sha256: str  # of the text file we actually read; used for byte-offset verification
    sha_ok: bool  # does the file hash equal the manifest hash (see DATASET_NOTES.md)
    text: str
    header_url: str | None
    header_retrieved: str | None
    header_mismatch: bool
    body_start: int  # offset of the first character after the SOURCE/RETRIEVED header

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class LinkOnlyDoc:
    doc_id: str
    url: str
    jurisdictions: str
    source_type: str
    status: str  # "link-only" or the manifest's manual status (e.g. D056, 403)
    slug_tokens: tuple[str, ...] = field(default=())


_HEADER_SOURCE = re.compile(r"^SOURCE:\s*(.+?)\s*$", re.M)
_HEADER_RETRIEVED = re.compile(r"^RETRIEVED:\s*(.+?)\s*$", re.M)


def _slug_tokens(url: str) -> tuple[str, ...]:
    path = urlparse(url).path.lower()
    return tuple(t for t in re.split(r"[^a-z0-9]+", path) if len(t) > 1)


def _norm_ts(ts: str) -> str:
    """'2026-10-01 22:44 UTC' and '2026-10-01T22:44Z' are the same moment."""
    return re.sub(r"[^0-9]", "", ts)[:12]


def _read_manifest() -> list[dict]:
    with open(config.MANIFEST_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_corpus() -> tuple[list[Doc], list[LinkOnlyDoc]]:
    docs: list[Doc] = []
    links: list[LinkOnlyDoc] = []
    for row in _read_manifest():
        if row["status"] != "ok":
            links.append(
                LinkOnlyDoc(
                    doc_id=row["doc_id"],
                    url=row["url"],
                    jurisdictions=row["jurisdictions"],
                    source_type=row["source_type"],
                    status=row["status"],
                    slug_tokens=_slug_tokens(row["url"]),
                )
            )
            continue
        raw = (config.DATASET / "corpus" / row["text_file"]).read_bytes()
        text = raw.decode("utf-8")
        sha = hashlib.sha256(raw).hexdigest()
        src = _HEADER_SOURCE.search(text[:600])
        ret = _HEADER_RETRIEVED.search(text[:600])
        body_start = text.find("\n\n") + 2 if "\n\n" in text[:600] else 0
        header_mismatch = bool(
            (src and src.group(1) != row["url"])
            or (ret and _norm_ts(ret.group(1)) != _norm_ts(row["retrieved_at"]))
        )
        docs.append(
            Doc(
                doc_id=row["doc_id"],
                url=row["url"],
                retrieved_at=row["retrieved_at"],
                jurisdictions=row["jurisdictions"],
                source_type=row["source_type"],
                manifest_sha256=row["sha256"],
                sha256=sha,
                sha_ok=sha == row["sha256"],
                text=text,
                header_url=src.group(1) if src else None,
                header_retrieved=ret.group(1) if ret else None,
                header_mismatch=header_mismatch,
                body_start=body_start,
            )
        )
    return docs, links
