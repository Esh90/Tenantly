"""Ingest (PLAN.md 5.4, D17): one pasted document through the same compile DAG into a staged
overlay, with a computed blast radius. It reaches renters only after an explicit admin publish.

Spend is capped separately (INGEST_BUDGET_USD); identical documents replay from the content
addressed cache for free.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from datetime import UTC, date, datetime
from pathlib import Path

from engine import config
from engine.api.errors import ApiError
from engine.compile import assemble, extract, link
from engine.compile import explain as explain_stage
from engine.compile.context import DocView, resolve_jurisdiction
from engine.compile.llm import LLM, BudgetExceeded, Ledger
from engine.corpus import boilerplate, doctype, sectionizer, versions
from engine.corpus.loader import Doc
from engine.ir import RuleSet
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv

log = logging.getLogger("tenantly.ingest")

MAX_CHARS = 200_000
STAGES = ["received", "sectionize", "triage", "extract", "verify", "crosscheck", "calendar",
          "link", "explain", "diff", "impact"]  # fmt: skip
DEFAULT_DATE = date.fromisoformat(config.DEFAULT_AS_OF)
INGEST_CAP = float(os.environ.get("INGEST_BUDGET_USD", "0.5"))


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_view(
    title: str, text: str, hint: str | None, url: str | None, retrieved: str | None
) -> DocView:
    if not hint:
        raise ApiError(
            "BAD_REQUEST", "jurisdiction_hint is required, for example 'Cambridge, MA'.", {}
        )
    try:
        jur = resolve_jurisdiction(hint)
    except KeyError as exc:
        raise ApiError(
            "UNSUPPORTED_STATE",
            f"{hint!r} is not one of the jurisdictions Tenantly covers.",
            {"hint": hint},
        ) from exc
    digest = hashlib.sha256((title + "\n" + text).encode("utf-8")).hexdigest()
    doc_id = f"I-{digest[:8]}"
    src = url or f"pasted://{doc_id}"
    ret = retrieved or _now()
    raw = f"SOURCE: {src}\nRETRIEVED: {ret}\n\n{text}"
    doc = Doc(
        doc_id=doc_id, url=src, retrieved_at=ret, jurisdictions=jur.label, source_type="official (pasted)",
        manifest_sha256="", sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(), sha_ok=False, text=raw,
        header_url=src, header_retrieved=ret, header_mismatch=False, body_start=raw.index("\n\n") + 2,
    )  # fmt: skip
    masked = boilerplate.mask_corpus([doc])[doc_id]
    segs = versions.segment_versions(raw)
    return DocView(
        doc=doc, doc_type=doctype.classify(doc).doc_type, jurisdiction=jur, segments=segs,
        spans=versions.in_force_spans(raw, segs, DEFAULT_DATE), version_label=versions.in_force_label(segs, DEFAULT_DATE),
        low_signal=False, masked=masked,
    )  # fmt: skip


def new_job(job_id: str) -> dict:
    return {
        "job_id": job_id, "status": "running", "stage": "received", "started_at": _now(), "finished_at": None,
        "stages": [{"stage": s, "status": "pending", "detail": "", "ms": None} for s in STAGES],
        "result": None, "error": None,
    }  # fmt: skip


class IngestManager:
    def __init__(self, store) -> None:
        self.store = store
        self.jobs: dict[str, dict] = {}
        self.overlays: dict[str, tuple[RuleSet, set[str], list, str]] = {}
        self.lock = threading.Lock()
        self.ledger = Ledger(config.ARTIFACTS / "ingest_ledger.json", cap=INGEST_CAP)
        self.llm = LLM(
            ledger=self.ledger, audit_path=config.ARTIFACTS / "audit" / "ingest_audit.jsonl"
        )

    # ---- API surface ----
    def start(self, req) -> dict:
        if len(req.text) > MAX_CHARS:
            raise ApiError(
                "DOCUMENT_TOO_LARGE",
                "Documents are limited to 200,000 characters.",
                {"chars": len(req.text)},
            )
        view = make_view(
            req.title, req.text, req.jurisdiction_hint, req.source_url, req.retrieved_at
        )
        job_id = "job-" + view.doc.doc_id[2:]
        with self.lock:
            existing = self.jobs.get(job_id)
            if existing and existing["status"] in ("running", "ready"):
                return {
                    "job_id": job_id,
                    "status": existing["status"],
                    "events_url": f"/v1/ingest/{job_id}/events",
                }
            if self.ledger.total >= self.ledger.cap:
                raise ApiError(
                    "BUDGET_EXCEEDED", "The ingest budget for this deployment is used up.", {}
                )
            self.jobs[job_id] = new_job(job_id)
        threading.Thread(target=self._run, args=(job_id, view), daemon=True).start()
        return {"job_id": job_id, "status": "running", "events_url": f"/v1/ingest/{job_id}/events"}

    def get(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            raise ApiError("JOB_NOT_FOUND", "We couldn't find this job.", {"job_id": job_id})
        return job

    def events(self, job_id: str):
        job = self.get(job_id)
        sent: dict[str, str] = {}
        while True:
            for s in job["stages"]:
                key = f"{s['status']}|{s['detail']}"
                if s["status"] != "pending" and sent.get(s["stage"]) != key:
                    sent[s["stage"]] = key
                    yield f"event: stage\ndata: {json.dumps(s)}\n\n"
            if job["status"] in ("ready", "published", "failed"):
                break
            time.sleep(0.4)
        if job["status"] == "failed":
            yield f"event: error\ndata: {json.dumps(job['error'])}\n\n"
        else:
            yield f"event: impact\ndata: {json.dumps(job['result']['impact'])}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': job['status']})}\n\n"

    def publish(self, job_id: str) -> dict:
        job = self.get(job_id)
        if job["status"] == "published":
            raise ApiError(
                "ALREADY_PUBLISHED", "This job was already published.", {"job_id": job_id}
            )
        if job["status"] != "ready":
            raise ApiError("JOB_NOT_READY", "This job is not ready to publish.", {"job_id": job_id})
        overlay, new_ids, affected_all, on = self.overlays[job_id]
        change_id = self.store.apply_overlay(overlay, new_ids, job, affected_all, on)
        job["status"], job["stage"] = "published", "published"
        return {"change_id": change_id, "published_at": _now()}

    # ---- the pipeline ----
    def _set(
        self, job: dict, stage: str, status: str, detail: str = "", ms: int | None = None
    ) -> None:
        for s in job["stages"]:
            if s["stage"] == stage:
                s.update(status=status, detail=detail, ms=ms)
        if status == "running":
            job["stage"] = stage

    def _run(self, job_id: str, view: DocView) -> None:
        job = self.jobs[job_id]
        spent0 = self.ledger.total
        t0 = time.monotonic()
        try:
            self._pipeline(job, view, spent0)
        except BudgetExceeded as exc:
            self._fail(job, "BUDGET_EXCEEDED", f"The ingest budget would be exceeded: {exc}")
        except ApiError as exc:
            self._fail(job, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001
            log.exception("ingest failed job=%s", job_id)
            self._fail(job, "INTERNAL", f"Ingest failed: {type(exc).__name__}")
        job["finished_at"] = _now()
        log.info(
            "ingest job=%s status=%s ms=%.0f", job_id, job["status"], (time.monotonic() - t0) * 1000
        )

    def _fail(self, job: dict, code: str, message: str) -> None:
        job["status"], job["stage"] = "failed", "failed"
        job["error"] = {"code": code, "message": message}
        for s in job["stages"]:
            if s["status"] == "running":
                s["status"] = "failed"

    def _timed(self, job, stage, fn, detail_fn=lambda r: ""):
        self._set(job, stage, "running")
        t = time.monotonic()
        out = fn()
        self._set(job, stage, "done", detail_fn(out), int((time.monotonic() - t) * 1000))
        return out

    def _pipeline(self, job: dict, view: DocView, spent0: float) -> None:
        self._timed(
            job,
            "received",
            lambda: None,
            lambda _: f"{view.doc.chars} characters, {view.doc_type}, {view.jurisdiction.label}",
        )
        secs = self._timed(
            job,
            "sectionize",
            lambda: sectionizer.sectionize(view.doc, view.masked, view.segments),
            lambda s: f"{len(s)} sections",
        )
        keep = self._timed(
            job,
            "triage",
            lambda: extract.triage_sections(self.llm, view, secs),
            lambda k: "all sections kept" if k is None else f"{len(k)} sections kept",
        )
        rejected: list = []

        def do_extract():
            text_a = extract.text_for_pass_a(view, secs, keep)
            raw_a = extract.run_pass(self.llm, view, text_a, "A")
            raw_b = extract.run_pass(self.llm, view, view.model_text(), "B")
            ok_a, rej_a = extract.finalize_all(view, raw_a, "A")
            ok_b, rej_b = extract.finalize_all(view, raw_b, "B")
            return ok_a, ok_b, rej_a + rej_b, len(raw_a) + len(raw_b)

        ok_a, ok_b, rejected, n_raw = self._timed(
            job, "extract", do_extract, lambda r: f"{r[3]} candidate rules from two passes"
        )
        verified = len(ok_a) + len(ok_b)
        self._timed(
            job,
            "verify",
            lambda: None,
            lambda _: (
                f"{verified} of {n_raw} quotes found in the document; {len(rejected)} rejected"
            ),
        )
        rules = self._timed(
            job,
            "crosscheck",
            lambda: extract.merge_passes(self.llm, view, ok_a, ok_b),
            lambda r: f"{len(r)} rules after voting",
        )
        self._timed(
            job,
            "calendar",
            lambda: None,
            lambda _: (
                ", ".join(sorted({r.effective.output() or "date unknown" for r in rules}))
                or "no rules"
            ),
        )
        if not rules:
            raise ApiError(
                "BAD_REQUEST", "No rule with a verifiable quote was found in this document.", {}
            )

        base = self.store.rs
        taken = {
            (r.jurisdiction.id, r.category): sum(
                1
                for x in base.rules
                if (x.jurisdiction.id, x.category) == (r.jurisdiction.id, r.category)
                and x.lifecycle == "enacted"
            )
            for r in rules
        }
        new_rules = assemble.finalize_rules(rules)
        renamed = []
        n_by_cell: dict[tuple, int] = {}
        for r in new_rules:
            cell = (r.jurisdiction.id, r.category)
            n_by_cell[cell] = n_by_cell.get(cell, 0) + 1
            prefix = r.rule_id.rsplit("-", 1)[0]
            suffix = (
                f"{taken.get(cell, 0) + n_by_cell[cell]:02d}"
                if r.lifecycle == "enacted"
                else r.rule_id.rsplit("-", 1)[1]
            )
            renamed.append(r.model_copy(update={"rule_id": f"{prefix}-{suffix}"}))
        new_rules = renamed

        def do_link():
            tmp = RuleSet(data_version="tmp", compiled_at=_now(), rules=base.rules + new_rules)
            views = {view.doc.doc_id: view}
            raw = link.link_documents(self.llm, new_rules, views)
            rels, _ = link.verify_relations(raw, tmp.rules, views)
            return rels

        rels = self._timed(job, "link", do_link, lambda r: f"{len(r)} relations")
        explained = self._timed(job, "explain", lambda: [explain_stage.explain_rule(self.llm, r) for r in new_rules],
                                lambda r: f"{len(r)} rules explained in English and Spanish")  # fmt: skip
        offset = len(base.relations)
        rels = [
            r.model_copy(update={"relation_id": f"REL-{offset + i + 1:03d}"})
            for i, r in enumerate(rels)
        ]
        overlay = base.model_copy(
            update={
                "rules": sorted(base.rules + explained, key=lambda r: r.rule_id),
                "relations": base.relations + rels,
            }
        )
        self._timed(
            job,
            "diff",
            lambda: None,
            lambda _: f"{len(explained)} new rules, {len(rels)} new relations",
        )
        impact_full = self._timed(
            job,
            "impact",
            lambda: self._impact(base, overlay, explained),
            lambda i: f"{i['affected_count']} addresses affected",
        )
        impact = {k: v for k, v in impact_full.items() if not k.startswith("_")}
        from engine.api.store import Store

        ids = [r.rule_id for r in explained]
        preview = Store(ruleset=overlay, resolved=self.store.records)
        job["result"] = {
            "rules": [preview._detail(r) for r in explained],
            "findings": [], "relations": [rel for r in explained for rel in preview._detail(r)["relations"]],
            "impact": impact,
            "verification": {"quotes_checked": n_raw, "quotes_verified": verified, "rejected": len(rejected)},
            "cost_usd": round(self.ledger.total - spent0, 4), "cache_hit": self.ledger.total == spent0,
        }  # fmt: skip
        self.overlays[job["job_id"]] = (overlay, set(ids), impact_full["_all"], impact_full["_on"])
        job["status"], job["stage"] = "ready", "ready"

    def _impact(self, base: RuleSet, overlay: RuleSet, new_rules) -> dict:
        from engine.rules.render import address_label

        ids = [r.rule_id for r in new_rules]
        effs = [r.effective.lo for r in new_rules if r.effective.lo]
        on = max([DEFAULT_DATE] + effs)
        affected, conflicts = [], 0
        for aid, rec in self.store.records.items():
            env = AddressEnv(rec)
            before = {o.rule_id: o for o in evaluate_address(base, rec, env, on).outcomes}
            after = {o.rule_id: o for o in evaluate_address(overlay, rec, env, on).outcomes}
            if any(i in after for i in ids):
                flag = any(after[i].conflict_flag for i in ids if i in after)
                conflicts += flag
                affected.append({
                    "address_id": aid, "label": address_label(rec), "lat": rec["lat"], "lon": rec["lon"],
                    "legal_city": rec["legal_city"],
                    "before": [{"rule_id": i, "result": before[i].result if i in before else "none"} for i in ids],
                    "after": [{"rule_id": i, "result": after[i].result if i in after else "none"} for i in ids],
                    "conflict_flag": flag,
                })  # fmt: skip
        eff = min(effs).isoformat() if effs else None
        return {"affected_count": len(affected), "sample": affected[:12], "effective_date": eff, "conflicts": conflicts,
                "_all": affected, "_on": on.isoformat()}  # fmt: skip


def is_ready(path: Path) -> bool:
    return path.exists()
