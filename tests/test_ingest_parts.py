"""Offline checks for the ingest helpers that need no model calls."""

import pytest

from engine.api.errors import ApiError
from engine.api.ingest_parts import extract_text, infer_jurisdiction


def test_extract_text_plain():
    out = extract_text("law.txt", b"Section 1. Rent.\n\nSection 2. Fees.")
    assert "Section 2" in out["text"]


def test_extract_text_rejects_oversize():
    with pytest.raises(ApiError):
        extract_text("big.txt", b"x" * 10_000_001)


def test_infer_jurisdiction_names_the_city_most_mentioned():
    label, why = infer_jurisdiction(
        "The City of Cambridge, Massachusetts adopts this ordinance. Cambridge shall enforce it."
    )
    assert label is not None and "Cambridge" in label
    assert why


def test_infer_jurisdiction_unknown_text_is_none():
    label, _ = infer_jurisdiction("Lorem ipsum dolor sit amet.")
    assert label is None
