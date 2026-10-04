"""The real data store: compiled rules + resolved addresses + the engine, all in memory.

Same interface as the fixture store. Lookups are deterministic engine code over in-memory data;
no model is called on any path in this module.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path

from engine import config
from engine.api.errors import ApiError
from engine.api.fixtures.store import FixtureStore
from engine.corpus import versions
from engine.geo import geocode
from engine.geo.jurisdictions import CITIES, COUNTIES
from engine.geo.pip import default_locator
from engine.io import atomic_write_json
from engine.ir import Rule, RuleSet
from engine.models import CATEGORIES, RESULTS
from engine.rules import templates as T
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv, InvalidFacts
from engine.rules.render import (
    address_label,
    citation_json,
    city_jurisdiction,
    county_jurisdiction,
    finding_json,
    index_item,
    jurisdiction_json,
    render_lookup,
    state_jurisdiction,
)
from engine.rules.timeline import build_timeline, segment_at, transitions

RANGE = {"start": config.AS_OF_RANGE[0], "end": config.AS_OF_RANGE[1]}
RULES_PATH = config.ARTIFACTS / "rules.compiled.json"
RESOLVED_PATH = config.ARTIFACTS / "addresses.resolved.json"
EVAL = config.ARTIFACTS / "eval"


def available() -> bool:
    return RULES_PATH.exists() and RESOLVED_PATH.exists()


def _read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _check_as_of(as_of: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", as_of or ""):
        raise ApiError(
            "AS_OF_OUT_OF_RANGE", "as_of must be a date like 2026-10-01.", {"as_of": as_of}
        )
    if not (RANGE["start"] <= as_of <= RANGE["end"]):
        raise ApiError("AS_OF_OUT_OF_RANGE", f"as_of must be within {RANGE['start']}..{RANGE['end']}.",
                       {"as_of": as_of, "range": RANGE})  # fmt: skip
    return date.fromisoformat(as_of)


class Store(FixtureStore):
    """Serves real data. Inherits only the pieces that have no real data yet (ingest, alerts)."""

    def __init__(self, ruleset: RuleSet | None = None, resolved: dict | None = None) -> None:
        super().__init__()
        self.rs = ruleset or RuleSet.model_validate(_read(RULES_PATH))
        self.records: dict[str, dict] = resolved or _read(RESOLVED_PATH)
        self.rules_by_id = {r.rule_id: r for r in self.rs.rules}
        self.data_version = self.rs.data_version
        self.geo_records: dict[str, dict] = {}  # geocoded arbitrary addresses, id geo-<sha10>
        self._timelines: dict[tuple, list] = {}
        self._docs = self._load_docs()
        self.default_date = date.fromisoformat(config.DEFAULT_AS_OF)
        self._counts = self._counts_at_default()
        self.n_text, self.n_link = self._manifest_counts()
        self.extra_changes: dict[str, dict] = {}
        self._ingest = None

    # ---- startup ----
    def _manifest_counts(self) -> tuple[int, int]:
        import csv

        with open(config.MANIFEST_CSV, newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        return sum(r["status"] == "ok" for r in rows), sum(r["status"] != "ok" for r in rows)

    def _load_docs(self) -> dict[str, dict]:
        path = config.ARTIFACTS / "corpus" / "docs.jsonl"
        out: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    d = json.loads(line)
                    out[d["doc_id"]] = d
        return out

    def _counts_at_default(self) -> dict[str, dict[str, int]]:
        counts: dict[str, dict[str, int]] = {
            r.rule_id: dict.fromkeys(RESULTS, 0) for r in self.rs.rules
        }
        for rec in self.records.values():
            res = evaluate_address(self.rs, rec, AddressEnv(rec), self.default_date)
            for o in res.outcomes:
                counts[o.rule_id][o.result] += 1
        return counts

    # ---- records ----
    def record(self, address_id: str) -> dict:
        rec = self.records.get(address_id) or self.geo_records.get(address_id)
        if rec is None:
            raise ApiError(
                "ADDRESS_NOT_FOUND", "We couldn't match this address.", {"query": address_id}
            )
        return rec

    def row(self, address_id: str) -> dict:  # used by inherited alert helpers
        rec = self.record(address_id)
        return {"address_id": address_id, "postal_city": rec["postal_city"], "state": rec["state"],
                "street_address": rec["street"], "zip": rec["zip"] or ""}  # fmt: skip

    def _segments(self, rec: dict, user: dict | None = None):
        key = (rec["address_id"], json.dumps(user, sort_keys=True) if user else "")
        if key not in self._timelines:
            if len(self._timelines) > 4000:
                self._timelines.clear()
            self._timelines[key] = build_timeline(self.rs, rec, user)
        return self._timelines[key]

    def _lookup(self, rec: dict, d: date, user: dict | None = None) -> dict:
        env = AddressEnv(rec, user)
        res = evaluate_address(self.rs, rec, env, d)
        return render_lookup(self.rs, rec, res, env, self._segments(rec, user),
                             facts_source="user" if user else "data", n_docs=self.n_text)  # fmt: skip

    # ---- addresses ----
    def addresses(self) -> dict:
        return {
            "items": [index_item(r) for r in self.records.values()],
            "data_version": self.data_version,
        }

    def search(self, q: str, limit: int) -> dict:
        needle = q.strip().lower()
        hits = [r for r in self.records.values() if needle and needle in address_label(r).lower()]
        return {"items": [index_item(r) for r in hits[:limit]]}

    def resolve(self, query: str) -> dict:
        from engine.rules.render import address_summary, jurisdiction_stack

        q = query.strip()
        needle = q.lower()
        hits = [r for r in self.records.values()
                if needle and (needle == r["address_id"].lower() or needle in address_label(r).lower())]  # fmt: skip
        if hits:
            r = hits[0]
            return {"match_type": "sample", "address": address_summary(r), "jurisdiction": jurisdiction_stack(r),
                    "candidates": [index_item(x) for x in hits[:8]], "geocoder": "index"}  # fmt: skip
        rec = self._geocode_free_text(q)
        if rec is None:
            return {"match_type": "not_found", "address": None, "jurisdiction": None, "candidates": [],
                    "geocoder": None}  # fmt: skip
        self.geo_records[rec["address_id"]] = rec
        return {"match_type": "geocoded", "address": address_summary(rec), "jurisdiction": jurisdiction_stack(rec),
                "candidates": [index_item(rec)], "geocoder": "census" if rec["geocoder"].startswith("census") else "nominatim"}  # fmt: skip

    def _geocode_free_text(self, q: str) -> dict | None:
        try:
            hit = geocode.census_oneline(q) or geocode.nominatim(q)
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                "GEOCODER_UNAVAILABLE",
                "The address service is not responding.",
                {"reason": str(exc)},
            ) from exc
        if hit is None:
            return None
        return self._record_for_point(
            hit.lat, hit.lon, label=q, geocoder=hit.tier, matched=hit.matched_address
        )

    def _record_for_point(self, lat: float, lon: float, label: str = "Selected point",
                          geocoder: str = "none", matched: str | None = None) -> dict:  # fmt: skip
        located = default_locator().locate(lat, lon)
        state = None
        for cid in (located.city_id, located.county_id):
            if cid:
                state = cid.split("-", 1)[0]
                break
        if state is None:
            raise ApiError(
                "UNSUPPORTED_STATE",
                "Tenantly covers California, New Jersey and Massachusetts.",
                {"lat": lat, "lon": lon},
            )
        city = next((c for c in CITIES if c.id == located.city_id), None)
        aid = "geo-" + hashlib.sha256(f"{label}|{lat:.5f}|{lon:.5f}".encode()).hexdigest()[:10]
        empty = {"lo": None, "hi": None, "record_conflict": False, "basis": None, "sources": []}
        stack = (
            [state]
            + ([located.county_id] if located.county_id else [])
            + ([located.city_id] if located.city_id else [])
        )
        return {
            "address_id": aid, "state": state, "street": label, "postal_city": city.name if city else "",
            "zip": None, "zip_used": None, "zip_suspect": False, "lat": lat, "lon": lon,
            "geocoder": geocoder, "geocode_variant": None, "matched_address": matched,
            "city_id": located.city_id, "county_id": located.county_id,
            "legal_city": city.name if city else None, "mailing_mismatch": False, "mailing_note": None,
            "census_county_fips": None, "census_agrees": None, "geo_conflict": False,
            "resolution_method": "point_in_polygon", "stack_ids": stack,
            "facts": {"units": dict(empty), "year_built": dict(empty), "property_type": None,
                      "property_type_basis": None, "subsidized": None, "subsidized_basis": None,
                      "review_flags": [], "use_code": "", "use_description": "", "source_dataset": "none"},
        }  # fmt: skip

    # ---- lookups ----
    def lookup(
        self, address_id: str, as_of: str, facts_source: str = "data", facts: dict | None = None
    ) -> dict:
        d = _check_as_of(as_of)
        return self._lookup(self.record(address_id), d, facts)

    def custom(self, req) -> dict:
        d = _check_as_of(req.as_of)
        try:
            if req.address_id:
                rec = self.record(req.address_id)
            elif req.lat is not None and req.lon is not None:
                rec = self._record_for_point(req.lat, req.lon)
                self.geo_records[rec["address_id"]] = rec
            else:
                raise ApiError("BAD_REQUEST", "Provide address_id or lat and lon.", {})
            return self._lookup(rec, d, dict(req.facts))
        except InvalidFacts as exc:
            raise ApiError(
                "INVALID_FACTS", "Some facts were not understood.", {"problems": exc.problems}
            ) from exc

    def timeline(self, address_id: str) -> dict:
        rec = self.record(address_id)
        segs = self._segments(rec)
        out_segs = []
        for s in segs:
            env = AddressEnv(rec)
            res = s.result
            out_segs.append({"start": s.start.isoformat(), "end": s.end.isoformat() if s.end else None,
                             "lookup": render_lookup(self.rs, rec, res, env, segs, n_docs=self.n_text)})  # fmt: skip
        bps = []
        for s in segs[1:]:
            changed = [t["rule_id"] for t in transitions(segs, s.start - date.resolution)
                       if t["date"] == s.start]  # fmt: skip
            label = (
                T.not_yet_headline(s.start)
                if changed
                else T.bi("Status details change.", "Cambian los detalles del estado.")
            )
            bps.append(
                {"date": s.start.isoformat(), "label": label, "rule_ids": sorted(set(changed))}
            )
        return {"address_id": address_id, "range": RANGE, "breakpoints": bps, "segments": out_segs,
                "data_version": self.data_version}  # fmt: skip

    # ---- law ----
    def _detail(self, r: Rule) -> dict:
        from engine.rules.render import _plain, effective_note, key_values_json, rule_status

        rels = []
        for rel in self.rs.relations:
            if rel.source_rule_id == r.rule_id or rel.target_rule_id == r.rule_id:
                other = (
                    rel.target_rule_id if rel.source_rule_id == r.rule_id else rel.source_rule_id
                )
                verb = {
                    "supersede": "Yields to",
                    "bar": "Barred by" if rel.target_rule_id == r.rule_id else "Bars",
                    "conflict_flag": "May conflict with",
                }[rel.effect]
                who = other or "local rules"
                rels.append({"type": rel.type, "other_rule_id": other,
                             "explanation": T.bi(f"{verb} {who}.", f"{verb} {who}."), "evidence": citation_json(rel.evidence),
                             "active_from": rel.active_from.isoformat() if rel.active_from else None})  # fmt: skip
        audit = [
            row["key"]
            for row in self._audit_rows()
            if row.get("ref") in (r.citation.doc_id, r.rule_id)
        ][:12]
        return {
            "rule_id": r.rule_id, "category": r.category, "title": r.title,
            "jurisdiction": jurisdiction_json(r.jurisdiction), "rule_status": rule_status(r, self.default_date),
            "effective_date": r.effective.output(), "effective_note": effective_note(r, self.default_date),
            "requirement": r.requirement, "summary": _plain(r, "summary") or T.bi(r.requirement, r.requirement),
            "who": _plain(r, "who") or T.bi(r.coverage_text, r.coverage_text),
            "coverage_text": T.bi(r.coverage_text, r.coverage_text),
            "exemptions": [
                {"description": T.bi(e.description, e.description),
                 "citation": citation_json(r.citation.model_copy(update={"quote": e.quote, "char_start": None, "char_end": None})) if e.quote else None}
                for e in r.exemptions
            ],
            "key_values": key_values_json(r, self.default_date), "penalty": r.penalty,
            "citation": citation_json(r.citation), "extra_citations": [citation_json(c) for c in r.extra_citations],
            "relations": rels, "confidence": r.confidence, "review_flag": r.review_flag,
            "open_question_ids": list(r.open_question_ids),
            "provenance": {
                "models": sorted({m for m in (config.MODEL_STRONG, config.MODEL_FAST) if r.provenance.get("passes")}),
                "prompt_versions": {"extract": "1"}, "votes": {k: str(v) for k, v in r.votes.items()},
                "adjudicated_fields": list(r.provenance.get("adjudicated_fields", [])), "audit_ids": audit,
            },
            "counts_at_default_date": self._counts.get(r.rule_id, dict.fromkeys(RESULTS, 0)),
        }  # fmt: skip

    def rules(self, state, jurisdiction_id, category, status, tier, q) -> dict:
        items = []
        for r in self.rs.rules:
            d = self._detail(r)
            if state and r.jurisdiction.state != state:
                continue
            if jurisdiction_id and r.jurisdiction.id != jurisdiction_id:
                continue
            if category and r.category != category:
                continue
            if status and d["rule_status"] != status:
                continue
            if tier and r.citation.tier != tier:
                continue
            if (
                q
                and q.lower() not in (r.title + " " + r.citation.cite + " " + r.requirement).lower()
            ):
                continue
            items.append(d)
        return {"items": items, "total": len(items)}

    def rule(self, rule_id: str) -> dict:
        r = self.rules_by_id.get(rule_id)
        if r is None:
            raise ApiError("RULE_NOT_FOUND", "We couldn't find this rule.", {"rule_id": rule_id})
        return self._detail(r)

    def findings(self, state) -> dict:
        return {
            "items": [
                finding_json(f)
                for f in self.rs.findings
                if not state or f.jurisdiction.state == state
            ]
        }

    def open_questions(self) -> dict:
        return {"items": [self._oq(q) for q in self.rs.open_questions]}

    @staticmethod
    def _oq(q) -> dict:
        return {"oq_id": q.oq_id, "title": T.bi(q.title["en"], q.title["es"]), "detail": T.bi(q.detail["en"], q.detail["es"]),
                "rule_ids": list(q.rule_ids), "sources": [citation_json(c) for c in q.sources],
                "changes_answer_between": [x.isoformat() for x in q.changes_answer_between] if q.changes_answer_between else None}  # fmt: skip

    def source(self, doc_id: str, rule_id: str | None, window: int) -> dict:
        import csv

        with open(config.MANIFEST_CSV, newline="", encoding="utf-8") as fh:
            rows = {r["doc_id"]: r for r in csv.DictReader(fh)}
        m = rows.get(doc_id)
        if not m:
            raise ApiError("DOC_NOT_FOUND", "We couldn't find this document.", {"doc_id": doc_id})
        info = self._docs.get(doc_id, {})
        text, sha = "", None
        if m["status"] == "ok":
            raw = (config.DATASET / "corpus" / m["text_file"]).read_bytes()
            sha, text = hashlib.sha256(raw).hexdigest(), raw.decode("utf-8")
        window = max(200, min(window, 20000))
        start = 0
        rule = self.rules_by_id.get(rule_id or "")
        cites = [
            r
            for r in self.rs.rules
            if r.citation.doc_id == doc_id and r.citation.char_start is not None
        ]
        if rule and rule.citation.doc_id == doc_id and rule.citation.char_start is not None:
            start = max(0, rule.citation.char_start - window // 3)
        end = min(len(text), start + window)
        highlights = [{"start": r.citation.char_start - start, "end": r.citation.char_end - start, "rule_id": r.rule_id}
                      for r in cites if start <= r.citation.char_start and r.citation.char_end <= end]  # fmt: skip
        first = text[text.find("\n\n") + 2 :].strip().split("\n", 1)[0][:140] if text else doc_id
        vers = [{"label": v["label"], "valid_from": v["valid_from"], "valid_to": v["valid_to"],
                 "in_force_on_default": v["in_force_on_default"]} for v in info.get("versions", [])]  # fmt: skip
        return {"doc_id": doc_id, "title": first or doc_id, "url": m["url"], "retrieved_at": m["retrieved_at"],
                "doc_sha256": sha, "sha_ok": None if sha is None else (sha == m["sha256"]),
                "jurisdiction_label": m["jurisdictions"], "doc_type": info.get("doc_type", "link_only"),
                "low_signal": bool(info.get("low_signal", False)), "versions": vers,
                "window": {"text": text[start:end], "start": start, "end": end, "highlights": highlights},
                "total_chars": len(text)}  # fmt: skip

    # ---- geography ----
    def _features(self) -> dict[str, dict]:
        gj = _read(config.ARTIFACTS / "geo" / "jurisdictions.geojson", {"features": []})
        return {f["id"]: f for f in gj["features"]}

    def geo(self, jurisdiction_id: str) -> dict:
        f = self._features().get(jurisdiction_id)
        if f is None:
            raise ApiError("ADDRESS_NOT_FOUND", "Unknown jurisdiction.", {"id": jurisdiction_id})
        return f

    def geo_state(self, state: str) -> dict:
        if state not in ("CA", "NJ", "MA"):
            raise ApiError("UNSUPPORTED_STATE", "State not covered.", {"state": state})
        feats = [f for f in self._features().values() if f["properties"]["state"] == state]
        order = {"state": 0, "county": 1, "city": 2}
        feats.sort(key=lambda f: (order[f["properties"]["level"]], f["id"]))
        return {"type": "FeatureCollection", "features": feats}

    @classmethod
    def preview(cls, overlay: RuleSet):
        """A light read-only view over a staged rule set, for rendering rule details. It skips the
        per-address counts, which only the live set needs."""
        live = load_store()
        o = cls.__new__(cls)
        o.rs, o.rules_by_id = overlay, {r.rule_id: r for r in overlay.rules}
        o.default_date, o._counts, o._docs = live.default_date, {}, live._docs
        o._audit_cache = live._audit_rows()
        o.data_version = "preview"
        return o

    # ---- ingest (real) ----
    @property
    def ingest(self):
        if self._ingest is None:
            from engine.api.ingest import IngestManager

            self._ingest = IngestManager(self)
        return self._ingest

    def ingest_start(self, req) -> dict:
        return self.ingest.start(req)

    def ingest_get(self, job_id: str) -> dict:
        return self.ingest.get(job_id)

    def ingest_events(self, job_id: str):
        return self.ingest.events(job_id)

    def ingest_publish(self, job_id: str, approve: bool = False) -> dict:
        return self.ingest.publish(job_id, approve)

    def ingest_reject(self, job_id: str) -> dict:
        return self.ingest.reject(job_id)

    def ingest_rejudge(self, job_id: str) -> dict:
        return self.ingest.rejudge(job_id)

    def ingest_edit(self, job_id: str, rules: list[dict]) -> dict:
        return self.ingest.edit(job_id, rules)

    def apply_overlay(
        self, overlay: RuleSet, new_ids: set[str], job: dict, affected: list, on: str
    ) -> str:
        """Publish: swap in the overlay, recompute counts and record a change event."""
        from engine.compile.dag import data_version

        dv = data_version(overlay.rules, overlay.relations, overlay.findings)
        self.rs = overlay.model_copy(update={"data_version": dv})
        self.rules_by_id = {r.rule_id: r for r in self.rs.rules}
        self.data_version = dv
        self._timelines.clear()
        self._counts = self._counts_at_default()
        cid = f"chg-{job['job_id']}"
        titles = ", ".join(sorted(new_ids))
        self.extra_changes[cid] = {
            "change_id": cid, "kind": "ingest", "test_id": None, "title": f"New document published: {titles}",
            "test_type": "with_without",
            "summary": T.bi(f"{len(new_ids)} new rule(s) published; {len(affected)} addresses are reached.",
                            f"Se publicaron {len(new_ids)} regla(s) nueva(s); alcanzan a {len(affected)} direcciones."),
            "created_at": now_iso(), "rule_ids": sorted(new_ids),
            "compare": {"mode": "with_without", "on": on}, "affected_count": len(affected),
            "conflict_count": sum(1 for a in affected if a["conflict_flag"]), "expected_check": None,
            "affected": affected,
        }  # fmt: skip
        return cid

    # ---- changes ----
    def _change_files(self) -> dict[str, dict]:
        out = {}
        for p in sorted((config.ARTIFACTS / "changes").glob("T*.json")):
            out[f"chg-{p.stem}"] = json.loads(p.read_text(encoding="utf-8"))
        return out

    def changes(self) -> dict:
        items = []
        for ev in list(self._change_files().values()) + list(self.extra_changes.values()):
            items.append({k: v for k, v in ev.items() if k != "affected"})
        return {"items": items}

    def change(self, change_id: str) -> dict:
        ev = self._change_files().get(change_id) or self.extra_changes.get(change_id)
        if ev is None:
            raise ApiError(
                "CHANGE_NOT_FOUND", "We couldn't find this change.", {"change_id": change_id}
            )
        return ev

    # ---- submission files ----
    def submission(self, name: str):
        if name not in {"rules", "lookups", "changes"}:
            raise ApiError("BAD_REQUEST", "Unknown submission file.", {"name": name})
        built = config.OUT / f"{name}.json"
        if not built.exists():
            raise ApiError(
                "NOT_READY", "Submission files have not been exported yet.", {"name": name}
            )
        return json.loads(built.read_text(encoding="utf-8"))

    # ---- meta / proof / audit ----
    def meta(self) -> dict:
        compiled = self.rs.compiled_at
        return {
            "app": "Tenantly", "api_version": "v1", "data_version": self.data_version, "compiled_at": compiled,
            "default_as_of": config.DEFAULT_AS_OF, "sources_retrieved_at": config.SOURCES_RETRIEVED_AT,
            "as_of_range": RANGE,
            "categories": [{"key": c, "label": T.bi(*T.CATEGORY_LABELS[c])} for c in CATEGORIES],
            "jurisdictions": self._jurisdictions(),
            "counts": {"rules": len(self.rs.rules), "findings": len(self.rs.findings), "addresses": len(self.records),
                       "docs_text": self.n_text, "docs_link_only": self.n_link},
            "persistence": "memory", "demo_mode": config.DEMO_MODE, "disclaimer": config.DISCLAIMER,
        }  # fmt: skip

    def _jurisdictions(self) -> list[dict]:
        out = [state_jurisdiction(s) for s in ("CA", "NJ", "MA")]
        out += [city_jurisdiction(c.id) for c in CITIES]
        out += [county_jurisdiction(f"{s}-{fips}") for fips, _n, s in COUNTIES]
        return out

    def _audit_rows(self) -> list[dict]:
        path = config.ARTIFACTS / "audit" / "compile_audit.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def audit(self, rule_id: str | None, limit: int) -> dict:
        rows = self._audit_rows()
        if rule_id:
            r = self.rules_by_id.get(rule_id)
            refs = {rule_id} | ({r.citation.doc_id} if r else set())
            rows = [x for x in rows if x.get("ref") in refs]
        rows = rows[-limit:]
        return {"items": [{"ts": x["ts"], "stage": x["stage"], "model": x.get("model"),
                           "prompt_version": str(x.get("prompt_version")), "cache_hit": x["cache_hit"],
                           "input_sha": x["input_sha"], "output_sha": x["output_sha"],
                           "verifier": x.get("verifier"), "cost_usd": x["cost_usd"]} for x in rows]}  # fmt: skip

    def proof(self) -> dict:
        ver = _read(EVAL / "verification.json", {})
        facts = _read(EVAL / "facts_report.json", {})
        geo = _read(EVAL / "geo_report.json", {})
        ledger = _read(config.ARTIFACTS / "ledger.json", {})
        score = _read(EVAL / "selfscore.json")
        if score:
            score = {k: score[k] for k in ("components", "key", "raw_report")}
        checks = _read(EVAL / "changes_check.json", [])
        lat = _read(EVAL / "latency.json")
        if lat:
            lat = {
                k: lat.get(k)
                for k in (
                    "measured_at",
                    "lookup_p50_ms",
                    "lookup_p95_ms",
                    "custom_p50_ms",
                    "llm_baseline_ms",
                )
            }
        plain = _read(EVAL / "reading_level.json", {})
        return {
            "data_version": self.data_version, "compiled_at": self.rs.compiled_at,
            "selfscore": score,
            "change_checks": checks,
            "verification": {"rules": ver.get("rules", len(self.rs.rules)),
                             "tier_counts": ver.get("tier_counts", {"A": 0, "B": 0, "C": 0, "C1": 0}),
                             "quotes_verified": ver.get("quotes_verified", 0),
                             "rejected_candidates": ver.get("rejected_candidates", 0),
                             "adjudicated_fields": ver.get("adjudicated_fields", 0),
                             "mean_confidence": ver.get("mean_confidence", 0.0)},  # fmt: skip
            "facts": {"derived_units": facts.get("derived_units", 0), "record_conflicts": facts.get("record_conflicts", 0),
                      "zip_suspect": facts.get("zip_suspect", 0), "missing_year_built": facts.get("missing_year_built", 0)},
            "geo": {"matched_batch": geo.get("matched_batch", 0), "matched_oneline": geo.get("matched_oneline", 0),
                    "matched_nominatim": geo.get("matched_nominatim", 0), "unmatched": geo.get("unmatched", 0),
                    "mailing_mismatches": geo.get("mailing_mismatches", 0), "census_disagreements": geo.get("census_disagreements", 0)},
            "plain_language": {"mean_grade_en": plain.get("mean_grade_en", 0.0), "max_grade_en": plain.get("max_grade_en", 0.0),
                               "es_coverage": plain.get("es_coverage", 0.0)},
            "latency": lat,
            "cost": {"total_usd": ledger.get("total_usd", 0.0), "by_stage": ledger.get("by_stage", {})},
            "open_questions": [self._oq(q) for q in self.rs.open_questions],
            "limitations": [
                T.bi("Answers use public records; facts like who owns the building are not public.", "Las respuestas usan registros públicos; datos como quién es el dueño no son públicos."),
                T.bi("Laws whose text was not supplied are labeled and never quoted from the ordinance.", "Las leyes sin texto disponible se etiquetan y nunca se citan de la ordenanza."),
                T.bi("Dates after October 1, 2026 are projections from the sources we retrieved.", "Las fechas posteriores al 1 de octubre de 2026 son proyecciones."),
            ],
        }  # fmt: skip

    def health(self) -> dict:
        return {
            "status": "ok",
            "data_version": self.data_version,
            "uptime_s": round(time.monotonic() - self.started, 3),
        }

    def atom(self, address_id: str) -> str:
        rec = self.record(address_id)
        ups = transitions(self._segments(rec), self.default_date)
        entries = "".join(
            f"<entry><title>{t['title']}: {t['from']} to {t['to']}</title><id>tenantly:{address_id}:{t['rule_id']}:{t['date']}</id>"
            f"<updated>{t['date']}T00:00:00Z</updated></entry>"
            for t in ups
        )
        return ('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
                f"<title>Tenantly changes for {address_label(rec)}</title><id>tenantly:{address_id}</id>"
                f"<updated>{self.rs.compiled_at}</updated>{entries}</feed>\n")  # fmt: skip

    def ics(self, address_id: str) -> str:
        rec = self.record(address_id)
        ups = transitions(self._segments(rec), self.default_date)
        ev = "".join(
            f"BEGIN:VEVENT\r\nUID:{address_id}-{t['rule_id']}-{t['date']}@tenantly\r\nDTSTART;VALUE=DATE:{t['date'].strftime('%Y%m%d')}\r\n"
            f"SUMMARY:{t['title']} changes to {t['to']}\r\nEND:VEVENT\r\n"
            for t in ups
        )
        return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Tenantly//EN\r\n{ev}END:VCALENDAR\r\n"


def jurisdiction_ref(jid: str):
    """A JurisdictionRef for a state code or a city id such as CA-0667000."""
    from engine.compile.context import jurisdiction_for

    if jid in ("CA", "NJ", "MA"):
        return jurisdiction_for(jid)
    for c in CITIES:
        if c.id == jid:
            return jurisdiction_for(c.label)
    raise KeyError(jid)


@lru_cache(maxsize=1)
def load_store() -> Store:
    return Store()


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["Store", "available", "load_store", "atomic_write_json", "segment_at", "versions"]
