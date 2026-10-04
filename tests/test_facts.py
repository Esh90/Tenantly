"""Phase 0 slice: ZIP sanity. Use-code derivation and record conflicts arrive in Phase 1."""

import csv

from engine import config
from engine.geo.zipsanity import zip_is_suspect


def _rows():
    with open(config.ADDRESSES_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_83_suspect_zips_all_nj():
    suspect = [r for r in _rows() if zip_is_suspect(r["state"], r["postal_city"], r["zip"])]
    assert len(suspect) == 83
    assert {r["state"] for r in suspect} == {"NJ"}


def test_empty_zip_is_not_suspect():
    assert not zip_is_suspect("CA", "San Francisco", "")
    assert not zip_is_suspect("MA", "Cambridge", None)


def test_known_bad_zip_examples():
    assert zip_is_suspect("NJ", "Newark", "11219")  # A0003: Brooklyn ZIP
    assert not zip_is_suspect("NJ", "Hoboken", "07030")
    assert not zip_is_suspect("NJ", "Jersey City", "07304")
