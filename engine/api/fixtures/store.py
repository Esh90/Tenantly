"""Fixture-backed store for the Phase 0 skeleton.

Address ids, labels, use codes and building facts are real rows from the starter pack.
Everything about *law* here is an obvious placeholder (rule ids start with ``FIXTURE`` is avoided
for frontend ergonomics, so quotes and titles are tagged "[fixture]"). Coordinates are 0.0 until
geocoding exists (Phase 3). Real data replaces this store phase by phase.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import time
from datetime import UTC, datetime
from functools import lru_cache

from engine import config
from engine.api.errors import ApiError
from engine.geo.jurisdictions import CITIES, STATES
from engine.models import CATEGORIES, RESULTS

DATA_VERSION = "fixture0"
COMPILED_AT = "2026-10-01T00:00:00Z"
RANGE = {"start": config.AS_OF_RANGE[0], "end": config.AS_OF_RANGE[1]}

CATEGORY_LABELS = {
    "rent_increase_limits": ("Rent increase limits", "Límites a los aumentos de renta"),
    "just_cause_eviction": ("Just-cause eviction", "Desalojo con causa justa"),
    "security_deposits": ("Security deposits", "Depósitos de seguridad"),
    "application_screening_fees": (
        "Application and screening fees",
        "Cuotas de solicitud y evaluación",
    ),
    "screening_restrictions": ("Screening restrictions", "Restricciones de evaluación"),
    "algorithmic_rent_setting": ("Algorithmic rent setting", "Fijación algorítmica de rentas"),
}

# (id, level, name, label, state, geoid), derived from the single jurisdiction table
JURISDICTIONS = [(code, "state", name, code, code, None) for code, (_, name) in STATES.items()] + [
    (c.id, "city", c.name, c.label, c.state, c.place_geoid) for c in CITIES
]

_RANGE_RE = re.compile(r"^(\d+)(?:\.\d+)?\s*-\s*\d+(?:\.\d+)?\s")


def jur(jid: str) -> dict:
    for i, level, name, label, state, geoid in JURISDICTIONS:
        if i == jid:
            return {
                "id": i,
                "level": level,
                "name": name,
                "label": label,
                "state": state,
                "geoid": geoid,
                "in_scope": True,
            }
    raise KeyError(jid)


def bi(en: str, es: str | None = None) -> dict:
    return {"en": en, "es": es if es is not None else en}


def _title(s: str) -> str:
    return s.title() if s.isupper() else s


@lru_cache(maxsize=1)
def _rows() -> list[dict]:
    with open(config.ADDRESSES_CSV, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _city_id_for(row: dict) -> str | None:
    """Fixture-only guess of the legal city from the postal city (real resolution is Phase 3)."""
    postal = row["postal_city"]
    mapping = {
        "Los Angeles": "CA-0644000",
        "San Francisco": "CA-0667000",
        "San Diego": "CA-0666000",
        "San Ysidro": "CA-0666000",
        "Berkeley": "CA-0606000",
        "Jersey City": "NJ-3436000",
        "Hoboken": "NJ-3432250",
        "Newark": "NJ-3451000",
        "Cambridge": "MA-2511000",
    }
    if row["state"] == "MA" and postal != "Cambridge":
        return "MA-2507000"
    return mapping.get(postal)


def _label(row: dict) -> str:
    zip_part = f" {row['zip']}" if row["zip"] else ""
    return f"{_title(row['street_address'])}, {row['postal_city']}, {row['state']}{zip_part}"


def _summary(row: dict) -> dict:
    return {
        "address_id": row["address_id"],
        "label": _label(row),
        "street": _title(row["street_address"]),
        "postal_city": row["postal_city"],
        "zip": row["zip"] or None,
        "state": row["state"],
        "lat": 0.0,
        "lon": 0.0,
        "legal_city": None,
        "is_sample": True,
    }


def _index_item(row: dict) -> dict:
    return {
        "address_id": row["address_id"],
        "label": _label(row),
        "postal_city": row["postal_city"],
        "legal_city": None,
        "state": row["state"],
        "zip": row["zip"] or None,
        "lat": 0.0,
        "lon": 0.0,
    }


def _fact(value, source: str, label_en: str, label_es: str, basis=None) -> dict:
    interval = (
        [value, value] if isinstance(value, int | float) and not isinstance(value, bool) else None
    )
    return {
        "value": value,
        "interval": interval,
        "source": source if value is not None else "missing",
        "basis": basis,
        "record_conflict": False,
        "label": bi(label_en, label_es),
    }


def _facts(row: dict) -> dict:
    yb = int(row["year_built"]) if row["year_built"] else None
    units = int(row["units"]) if row["units"] else None
    return {
        "year_built": _fact(yb, "assessor", "Year built", "Año de construcción"),
        "units": _fact(units, "assessor", "Number of units", "Número de unidades"),
        "property_type": _fact(None, "missing", "Property type", "Tipo de propiedad"),
        "subsidized": _fact(None, "missing", "Subsidized or affordable", "Subsidiado o asequible"),
        "use_code": row["use_code"],
        "use_description": row["use_description"],
        "source_dataset": row["source_dataset"],
        "zip_suspect": False,
    }


def citation(tier: str = "A") -> dict:
    return {
        "doc_id": "D022",
        "cite": "[fixture] placeholder citation",
        "url": "https://example.invalid/fixture",
        "retrieved_at": "2026-10-01T22:00Z",
        "quote": "[fixture] This quote is a placeholder and is not taken from any law.",
        "char_start": None,
        "char_end": None,
        "doc_sha256": None,
        "tier": tier,
        "quote_source": "corpus",
        "supplementary_doc": None,
        "version_label": None,
        "low_signal": False,
    }


def _rule_result(rule_id: str, category: str, jid: str, result: str, status: str) -> dict:
    return {
        "rule_id": rule_id,
        "category": category,
        "title": "[fixture] placeholder rule",
        "jurisdiction": jur(jid),
        "result": result,
        "rule_status": status,
        "effective_date": "2026-01-01",
        "effective_note": None
        if result == "applies"
        else bi("Starts January 1, 2026.", "Comienza el 1 de enero de 2026."),
        "summary": bi("[fixture] Placeholder summary.", "[fixture] Resumen de ejemplo."),
        "who": bi("[fixture] Placeholder coverage.", "[fixture] Cobertura de ejemplo."),
        "reason": bi("[fixture] Placeholder reason.", "[fixture] Motivo de ejemplo."),
        "key_values": [],
        "conditions": [],
        "caveats": [],
        "missing_facts": [],
        "superseded_by": None,
        "governs_over": [],
        "conflicts": [],
        "conflict_flag": False,
        "citation": citation(),
        "extra_citations": [],
        "confidence": 0.5,
        "review_flag": True,
        "open_question_ids": [],
        "audio": {"en": None, "es": None},
    }


def _boundary() -> dict:
    return {
        "checked": [bi("[fixture] Placeholder checked item.")],
        "not_checked": [bi("[fixture] Placeholder unchecked item.")],
        "assumptions": [bi("[fixture] Placeholder assumption.")],
    }


def _check_as_of(as_of: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of) or not (
        RANGE["start"] <= as_of <= RANGE["end"]
    ):
        raise ApiError(
            "AS_OF_OUT_OF_RANGE",
            f"as_of must be within {RANGE['start']}..{RANGE['end']}.",
            {"as_of": as_of, "range": RANGE},
        )


class FixtureStore:
    """Same interface the real store will implement."""

    def __init__(self) -> None:
        self.started = time.monotonic()
        self.jobs: dict[str, dict] = {}
        self.published: dict[str, dict] = {}

    # ---- addresses ----
    def row(self, address_id: str) -> dict:
        for r in _rows():
            if r["address_id"] == address_id:
                return r
        raise ApiError(
            "ADDRESS_NOT_FOUND", "We couldn't match this address.", {"query": address_id}
        )

    def addresses(self) -> dict:
        return {"items": [_index_item(r) for r in _rows()], "data_version": DATA_VERSION}

    def search(self, q: str, limit: int) -> dict:
        needle = q.strip().lower()
        hits = [r for r in _rows() if needle and needle in _label(r).lower()]
        return {"items": [_index_item(r) for r in hits[:limit]]}

    def resolve(self, query: str) -> dict:
        needle = query.strip().lower()
        for r in _rows():
            if needle and (needle == r["address_id"].lower() or needle in _label(r).lower()):
                cands = [_index_item(r)]
                return {
                    "match_type": "sample",
                    "address": _summary(r),
                    "jurisdiction": self.stack(r),
                    "candidates": cands,
                    "geocoder": "index",
                }
        return {
            "match_type": "not_found",
            "address": None,
            "jurisdiction": None,
            "candidates": [],
            "geocoder": None,
        }

    def stack(self, row: dict) -> dict:
        city = _city_id_for(row)
        mailing = row["postal_city"]
        legal = jur(city)["name"] if city else None
        mismatch = bool(legal and legal != mailing)
        return {
            "state": jur(row["state"]),
            "county": None,
            "city": jur(city) if city else None,
            "mailing_city": mailing,
            "mailing_mismatch": mismatch,
            "note": bi(
                f"Mailed as {mailing}. Legally inside {legal}.",
                f"Enviado como {mailing}. Legalmente dentro de {legal}.",
            )
            if mismatch
            else None,
            "resolution": {"method": "state_only", "geocoder": "none", "census_agrees": None},
        }

    # ---- lookups ----
    def lookup(
        self, address_id: str, as_of: str, facts_source: str = "data", facts: dict | None = None
    ) -> dict:
        _check_as_of(as_of)
        row = self.row(address_id)
        blocks = []
        for cat in CATEGORIES:
            results = []
            if cat == "algorithmic_rent_setting" and row["state"] == "CA":
                live = as_of >= "2026-01-01"
                results.append(
                    _rule_result(
                        "CA-ALG-01",
                        cat,
                        "CA",
                        "applies" if live else "not_yet_effective",
                        "in_force" if live else "not_yet_effective",
                    )
                )
            en, es = CATEGORY_LABELS[cat]
            blocks.append(
                {
                    "category": cat,
                    "label": bi(en, es),
                    "headline": bi("[fixture] No headline yet.", "[fixture] Sin titular todavía."),
                    "results": results,
                    "findings": [],
                }
            )
        counts = dict.fromkeys(RESULTS, 0)
        for b in blocks:
            for r in b["results"]:
                counts[r["result"]] += 1
        return {
            "address": _summary(row),
            "jurisdiction": self.stack(row),
            "facts": _facts(row),
            "as_of": as_of,
            "categories": blocks,
            "pending": [],
            "failed": [],
            "upcoming": [],
            "counts": counts,
            "decisive_question": None,
            "open_questions": [],
            "reasoning_boundary": _boundary(),
            "facts_source": facts_source,
            "sources_retrieved_at": config.SOURCES_RETRIEVED_AT,
            "is_projection": as_of > config.SOURCES_RETRIEVED_AT,
            "data_version": DATA_VERSION,
            "disclaimer": config.DISCLAIMER,
            "fallback": False,
        }

    def custom(self, req) -> dict:
        _check_as_of(req.as_of)
        allowed = {
            "year_built",
            "units",
            "property_type",
            "subsidized_or_affordable",
            "owner_is_natural_person",
            "owner_occupied",
            "landlord_property_count",
            "landlord_unit_count",
            "unit_separately_alienable",
            "shares_kitchen_bath_with_owner",
        }
        bad = sorted(set(req.facts) - allowed)
        if bad:
            raise ApiError("INVALID_FACTS", "Unknown fact keys.", {"unknown": bad})
        if not req.address_id:
            raise ApiError("BAD_REQUEST", "Phase 0 supports address_id only.", {})
        return self.lookup(req.address_id, req.as_of, facts_source="user", facts=req.facts)

    def timeline(self, address_id: str) -> dict:
        row = self.row(address_id)
        starts = [RANGE["start"]]
        if row["state"] == "CA":
            starts.append("2026-01-01")
        segs = []
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else None
            segs.append({"start": start, "end": end, "lookup": self.lookup(address_id, start)})
        bps = (
            [
                {
                    "date": "2026-01-01",
                    "label": bi("[fixture] Placeholder breakpoint."),
                    "rule_ids": ["CA-ALG-01"],
                }
            ]
            if row["state"] == "CA"
            else []
        )
        return {
            "address_id": address_id,
            "range": RANGE,
            "breakpoints": bps,
            "segments": segs,
            "data_version": DATA_VERSION,
        }

    # ---- law ----
    def rule_detail(self, rule_id: str = "CA-ALG-01") -> dict:
        counts = dict.fromkeys(RESULTS, 0)
        return {
            "rule_id": rule_id,
            "category": "algorithmic_rent_setting",
            "title": "[fixture] placeholder rule",
            "jurisdiction": jur("CA"),
            "rule_status": "in_force",
            "effective_date": "2026-01-01",
            "effective_note": None,
            "requirement": "[fixture] Placeholder requirement.",
            "summary": bi("[fixture] Placeholder summary."),
            "who": bi("[fixture] Placeholder coverage."),
            "coverage_text": bi("[fixture] Placeholder coverage."),
            "exemptions": [],
            "key_values": [],
            "penalty": None,
            "citation": citation(),
            "extra_citations": [],
            "relations": [],
            "confidence": 0.5,
            "review_flag": True,
            "open_question_ids": [],
            "provenance": {
                "models": [],
                "prompt_versions": {},
                "votes": {},
                "adjudicated_fields": [],
                "audit_ids": [],
            },
            "counts_at_default_date": counts,
        }

    def rules(self, state, jurisdiction_id, category, status, tier, q) -> dict:
        r = self.rule_detail()
        ok = (
            (not state or r["jurisdiction"]["state"] == state)
            and (not jurisdiction_id or r["jurisdiction"]["id"] == jurisdiction_id)
            and (not category or r["category"] == category)
            and (not status or r["rule_status"] == status)
            and (not tier or r["citation"]["tier"] == tier)
            and (not q or q.lower() in r["title"].lower())
        )
        items = [r] if ok else []
        return {"items": items, "total": len(items)}

    def rule(self, rule_id: str) -> dict:
        if rule_id != "CA-ALG-01":
            raise ApiError("RULE_NOT_FOUND", "We couldn't find this rule.", {"rule_id": rule_id})
        return self.rule_detail(rule_id)

    def findings(self, state) -> dict:
        return {"items": []}

    def open_questions(self) -> dict:
        return {"items": []}

    def source(self, doc_id: str, rule_id: str | None, window: int) -> dict:
        with open(config.MANIFEST_CSV, newline="", encoding="utf-8") as fh:
            rows = {r["doc_id"]: r for r in csv.DictReader(fh)}
        m = rows.get(doc_id)
        if not m:
            raise ApiError("DOC_NOT_FOUND", "We couldn't find this document.", {"doc_id": doc_id})
        text, sha = "", None
        if m["status"] == "ok":
            raw = (config.DATASET / "corpus" / m["text_file"]).read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            text = raw.decode("utf-8")
        window = max(200, min(window, 20000))
        return {
            "doc_id": doc_id,
            "title": doc_id,
            "url": m["url"],
            "retrieved_at": m["retrieved_at"],
            "doc_sha256": sha,
            "sha_ok": None,
            "jurisdiction_label": m["jurisdictions"],
            "doc_type": "unclassified",
            "low_signal": False,
            "versions": [],
            "window": {
                "text": text[:window],
                "start": 0,
                "end": min(window, len(text)),
                "highlights": [],
            },
            "total_chars": len(text),
        }

    def geo(self, jurisdiction_id: str) -> dict:
        ids = {j[0] for j in JURISDICTIONS}
        if jurisdiction_id in ids:
            return {
                "type": "Feature",
                "id": jurisdiction_id,
                "geometry": None,
                "properties": {"jurisdiction": jur(jurisdiction_id), "fixture": True},
            }
        if jurisdiction_id in {"CA", "NJ", "MA"}:
            pass
        raise ApiError("ADDRESS_NOT_FOUND", "Unknown jurisdiction.", {"id": jurisdiction_id})

    def geo_state(self, state: str) -> dict:
        if state not in {"CA", "NJ", "MA"}:
            raise ApiError("UNSUPPORTED_STATE", "State not covered.", {"state": state})
        feats = [self.geo(j[0]) for j in JURISDICTIONS if j[4] == state]
        return {"type": "FeatureCollection", "features": feats}

    # ---- changes ----
    def _change(self, test: dict) -> dict:
        tid = test["test_id"]
        kind = test["type"]
        if kind == "as_of":
            compare = {"before": test["as_of_before"], "after": test["as_of_after"]}
        else:
            compare = {"on": test["as_of"]}
        states = test.get("states")
        count = (
            sum(1 for r in _rows() if states and r["state"] in states)
            if kind in ("as_of", "pending")
            else 0
        )
        return {
            "change_id": f"chg-{tid}",
            "kind": "test",
            "test_id": tid,
            "title": test["title"],
            "test_type": kind,
            "summary": bi("[fixture] Placeholder summary."),
            "created_at": COMPILED_AT,
            "rule_ids": test["rule_ids"],
            "compare": compare,
            "affected_count": count,
            "conflict_count": 0,
            "expected_check": {"passed": False, "detail": "fixture: not computed yet"},
        }

    def _tests(self) -> list[dict]:
        return json.loads(config.CHANGE_TESTS.read_text(encoding="utf-8"))

    def changes(self) -> dict:
        return {"items": [self._change(t) for t in self._tests()]}

    def change(self, change_id: str) -> dict:
        for t in self._tests():
            c = self._change(t)
            if c["change_id"] == change_id:
                c["affected"] = []
                return c
        raise ApiError(
            "CHANGE_NOT_FOUND", "We couldn't find this change.", {"change_id": change_id}
        )

    # ---- submission ----
    def submission(self, name: str):
        if name not in {"rules", "lookups", "changes"}:
            raise ApiError("BAD_REQUEST", "Unknown submission file.", {"name": name})
        built = config.OUT / f"{name}.json"
        path = built if built.exists() else config.DATASET / "submission_templates" / f"{name}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    # ---- ingest ----
    def ingest_start(self, req) -> dict:
        if len(req.text) > 200_000:
            raise ApiError(
                "DOCUMENT_TOO_LARGE",
                "Documents are limited to 200,000 characters.",
                {"chars": len(req.text)},
            )
        job_id = "job-" + hashlib.sha256((req.title + req.text).encode()).hexdigest()[:10]
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        stages = [
            "received",
            "sectionize",
            "triage",
            "extract",
            "verify",
            "crosscheck",
            "calendar",
            "link",
            "explain",
            "diff",
            "impact",
        ]
        self.jobs[job_id] = {
            "job_id": job_id,
            "status": "ready",
            "stage": "ready",
            "started_at": now,
            "finished_at": now,
            "stages": [
                {"stage": s, "status": "done", "detail": "[fixture] simulated", "ms": 0}
                for s in stages
            ],
            "result": {
                "rules": [],
                "findings": [],
                "relations": [],
                "impact": {
                    "affected_count": 0,
                    "sample": [],
                    "effective_date": None,
                    "conflicts": 0,
                },
                "verification": {"quotes_checked": 0, "quotes_verified": 0, "rejected": 0},
                "cost_usd": 0.0,
                "cache_hit": False,
            },
            "error": None,
        }
        return {"job_id": job_id, "status": "running", "events_url": f"/v1/ingest/{job_id}/events"}

    def ingest_get(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            raise ApiError("JOB_NOT_FOUND", "We couldn't find this job.", {"job_id": job_id})
        return job

    def ingest_publish(self, job_id: str) -> dict:
        job = self.ingest_get(job_id)
        if job["status"] == "published":
            raise ApiError(
                "ALREADY_PUBLISHED", "This job was already published.", {"job_id": job_id}
            )
        if job["status"] != "ready":
            raise ApiError("JOB_NOT_READY", "This job is not ready to publish.", {"job_id": job_id})
        job["status"] = "published"
        job["stage"] = "published"
        return {
            "change_id": f"chg-{job_id}",
            "published_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    # ---- alerts ----
    def subscribe(self, req) -> dict:
        self.row(req.address_id)
        digest = hashlib.sha256(f"{req.email}|{req.address_id}".encode()).hexdigest()
        sid = f"sub-{digest[:10]}"
        return {
            "subscription_id": sid,
            "unsubscribe_token": digest[:32],
            "feeds": {
                "atom": f"/v1/alerts/feed/{req.address_id}.atom",
                "ics": f"/v1/alerts/calendar/{req.address_id}.ics",
            },
        }

    def atom(self, address_id: str) -> str:
        row = self.row(address_id)
        return (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<feed xmlns="http://www.w3.org/2005/Atom">\n'
            f"  <title>Tenantly changes for {_label(row)}</title>\n"
            f"  <id>tenantly:{address_id}</id>\n  <updated>{COMPILED_AT}</updated>\n</feed>\n"
        )

    def ics(self, address_id: str) -> str:
        self.row(address_id)
        return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Tenantly//EN\r\nEND:VCALENDAR\r\n"

    # ---- meta / proof / audit ----
    def meta(self) -> dict:
        import csv as _csv

        with open(config.MANIFEST_CSV, newline="", encoding="utf-8") as fh:
            rows = list(_csv.DictReader(fh))
        return {
            "app": "Tenantly",
            "api_version": "v1",
            "data_version": DATA_VERSION,
            "compiled_at": COMPILED_AT,
            "default_as_of": config.DEFAULT_AS_OF,
            "sources_retrieved_at": config.SOURCES_RETRIEVED_AT,
            "as_of_range": RANGE,
            "categories": [{"key": c, "label": bi(*CATEGORY_LABELS[c])} for c in CATEGORIES],
            "jurisdictions": [jur(j[0]) for j in JURISDICTIONS],
            "counts": {
                "rules": 1,
                "findings": 0,
                "addresses": len(_rows()),
                "docs_text": sum(r["status"] == "ok" for r in rows),
                "docs_link_only": sum(r["status"] != "ok" for r in rows),
            },
            "persistence": "memory",
            "demo_mode": config.DEMO_MODE,
            "disclaimer": config.DISCLAIMER,
        }

    def proof(self) -> dict:
        return {
            "data_version": DATA_VERSION,
            "compiled_at": COMPILED_AT,
            "selfscore": None,
            "change_checks": [],
            "verification": {
                "rules": 0,
                "tier_counts": {"A": 0, "B": 0, "C": 0, "C1": 0},
                "quotes_verified": 0,
                "rejected_candidates": 0,
                "adjudicated_fields": 0,
                "mean_confidence": 0.0,
            },
            "facts": {
                "derived_units": 0,
                "record_conflicts": 0,
                "zip_suspect": 0,
                "missing_year_built": sum(not r["year_built"] for r in _rows()),
            },
            "geo": {
                "matched_batch": 0,
                "matched_oneline": 0,
                "matched_nominatim": 0,
                "unmatched": 0,
                "mailing_mismatches": 0,
                "census_disagreements": 0,
            },
            "plain_language": {"mean_grade_en": 0.0, "max_grade_en": 0.0, "es_coverage": 0.0},
            "latency": None,
            "cost": {"total_usd": 0.0, "by_stage": {}},
            "open_questions": [],
            "limitations": [bi("[fixture] Skeleton data; nothing is compiled yet.")],
        }

    def audit(self, rule_id: str | None, limit: int) -> dict:
        return {"items": []}

    def health(self) -> dict:
        return {
            "status": "ok",
            "data_version": DATA_VERSION,
            "uptime_s": round(time.monotonic() - self.started, 3),
        }
