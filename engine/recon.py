"""Recon: verify the claims in CORPUS_ATLAS.md section 1 and 9 against the actual files."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import Counter

from engine import config
from engine.geo.zipsanity import zip_is_suspect

BOSTON_NEIGHBORHOODS = {
    "allston",
    "brighton",
    "dorchester",
    "east boston",
    "hyde park",
    "jamaica plain",
    "mattapan",
    "roxbury",
    "south boston",
    "boston",
}


def _read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def run() -> list[dict]:
    """Return a list of checks: {claim, expected, actual, ok}."""
    checks: list[dict] = []

    def check(claim: str, expected, actual) -> None:
        checks.append(
            {"claim": claim, "expected": expected, "actual": actual, "ok": expected == actual}
        )

    manifest = _read_csv(config.MANIFEST_CSV)
    links = _read_csv(config.LINKS_ONLY_CSV)
    ok_rows = [r for r in manifest if r["status"] == "ok"]
    check("manifest rows", 87, len(manifest))
    check("manifest rows with text (status ok)", 54, len(ok_rows))
    check("manifest rows without text (link-only + manual)", 33, len(manifest) - len(ok_rows))
    check(
        "manifest link-only rows (D056 is status manual: 403)",
        32,
        sum(r["status"] == "link-only" for r in manifest),
    )
    check("links_only.csv rows", 33, len(links))
    check("text files on disk", 54, len(list(config.TEXT_DIR.glob("D*.txt"))))

    bad_hash, bad_header = [], []
    for r in ok_rows:
        path = config.DATASET / "corpus" / r["text_file"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != r["sha256"]:
            bad_hash.append(r["doc_id"])
        head = raw.decode("utf-8", "replace").splitlines()[:2]
        if not (head[0].startswith("SOURCE: ") and head[1].startswith("RETRIEVED: ")):
            bad_header.append(r["doc_id"])
    check("text files whose sha256 equals the manifest sha256", 54, len(ok_rows) - len(bad_hash))
    check("files without SOURCE/RETRIEVED header", [], bad_header)

    rows = _read_csv(config.ADDRESSES_CSV)
    check("address rows", 500, len(rows))
    check(
        "address ids A0001..A0500 unique",
        True,
        sorted(r["address_id"] for r in rows) == [f"A{i:04d}" for i in range(1, 501)],
    )
    states = Counter(r["state"] for r in rows)
    check("state totals", {"CA": 250, "NJ": 140, "MA": 110}, dict(states))
    check("missing year_built", 212, sum(not r["year_built"].strip() for r in rows))
    miss_units = Counter(r["postal_city"] for r in rows if not r["units"].strip())
    check("missing units (postal city: count)", None, dict(sorted(miss_units.items())))
    empty_zip = Counter(r["postal_city"] for r in rows if not r["zip"].strip())
    check(
        "empty ZIP: SF 80, Cambridge 50",
        {"San Francisco": 80, "Cambridge": 50},
        {k: v for k, v in empty_zip.items() if k in ("San Francisco", "Cambridge")},
    )
    suspect = [r for r in rows if zip_is_suspect(r["state"], r["postal_city"], r["zip"])]
    check("suspect ZIPs", 83, len(suspect))
    check("suspect ZIPs all NJ", True, all(r["state"] == "NJ" for r in suspect))
    ma = Counter(r["postal_city"] for r in rows if r["state"] == "MA")
    boston = {k: v for k, v in ma.items() if k.lower() in BOSTON_NEIGHBORHOODS}
    check(
        "MA postal names that are Boston",
        {
            "Allston": 3,
            "Boston": 23,
            "Brighton": 4,
            "Dorchester": 13,
            "East Boston": 6,
            "Hyde Park": 1,
            "Jamaica Plain": 1,
            "Mattapan": 1,
            "Roxbury": 7,
            "South Boston": 1,
        },
        boston,
    )
    check("MA Cambridge rows", 50, ma.get("Cambridge", 0))
    check(
        "postal city totals (postal, not legal)",
        None,
        {
            f"{k[0]}/{k[1]}": v
            for k, v in sorted(Counter((r["state"], r["postal_city"]) for r in rows).items())
        },
    )
    check(
        "use_code by source (distinct sources)",
        None,
        dict(Counter(r["source_dataset"] for r in rows)),
    )
    check(
        "use codes",
        None,
        {
            " | ".join(k): v
            for k, v in sorted(
                Counter(
                    (r["source_dataset"], r["use_code"], r["use_description"]) for r in rows
                ).items()
            )
        },
    )
    m = [r for r in rows if re.match(r"^\d+(\.\d+)?\s*-\s*\d+", r["street_address"])]
    check("street addresses with ranges", None, len(m))
    return checks
