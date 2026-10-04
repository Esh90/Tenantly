"""Ingest (PLAN.md 5.4, D17): one document through the same compile DAG into a STAGED overlay,
then deterministic validation and an independent Judge, then VERIFIED or REVIEW REQUIRED, and only
then PUBLISHED into the live rule engine.

States: staged (rules extracted, kept apart from the live set) -> verified (validation and Judge
passed) or review_required (a human decides) -> published. Rejected jobs never reach renters.
Spend is capped separately (INGEST_BUDGET_USD); identical documents replay from the cache for free.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from engine import config
from engine.api import ingest_parts as parts
from engine.api.errors import ApiError
from engine.compile import assemble, extract, link
from engine.compile import explain as explain_stage
from engine.compile.context import DocView, cite_key, resolve_jurisdiction
from engine.compile.llm import LLM, BudgetExceeded, Ledger
from engine.corpus import boilerplate, doctype, sectionizer, versions
from engine.corpus.loader import Doc
from engine.export.build import rule_record
from engine.io import atomic_write_json
from engine.ir import Relation, Rule, RuleSet
from engine.rules.engine import evaluate_address
from engine.rules.facts_env import AddressEnv

log = logging.getLogger("tenantly.ingest")

MAX_CHARS = 200_000
STAGES = ["received", "parse", "sectionize", "triage", "extract", "verify", "crosscheck", "jurisdiction",
          "calendar", "link", "explain", "priority", "graph", "validate", "judge", "impact", "staged"]  # fmt: skip
DEFAULT_DATE = date.fromisoformat(config.DEFAULT_AS_OF)
INGEST_CAP = float(os.environ.get("INGEST_BUDGET_USD", "0.5"))
MIN_CONFIDENCE = float(
    os.environ.get("INGEST_AUTO_PUBLISH_MIN_CONFIDENCE", parts.MIN_CONFIDENCE_DEFAULT)
)
JOB_DIR = config.ARTIFACTS / "audit" / "ingest_jobs"


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_view(
    title: str, text: str, jurisdiction, url: str | None, retrieved: str | None
) -> DocView:
    digest = hashlib.sha256((title + "\n" + text).encode("utf-8")).hexdigest()
    doc_id = f"I-{digest[:8]}"
    src = url or f"pasted://{doc_id}"
    ret = retrieved or _now()
    raw = f"SOURCE: {src}\nRETRIEVED: {ret}\n\n{text}"
    doc = Doc(
        doc_id=doc_id, url=src, retrieved_at=ret, jurisdictions=jurisdiction.label, source_type="official (pasted)",
        manifest_sha256="", sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(), sha_ok=False, text=raw,
        header_url=src, header_retrieved=ret, header_mismatch=False, body_start=raw.index("\n\n") + 2,
    )  # fmt: skip
    masked = boilerplate.mask_corpus([doc])[doc_id]
    segs = versions.segment_versions(raw)
    return DocView(
        doc=doc, doc_type=doctype.classify(doc).doc_type, jurisdiction=jurisdiction, segments=segs,
        spans=versions.in_force_spans(raw, segs, DEFAULT_DATE), version_label=versions.in_force_label(segs, DEFAULT_DATE),
        low_signal=False, masked=masked,
    )  # fmt: skip


def new_job(job_id: str) -> dict:
    return {
        "job_id": job_id, "status": "running", "state": None, "stage": "received", "started_at": _now(),
        "finished_at": None,
        "stages": [{"stage": s, "status": "pending", "detail": "", "ms": None} for s in STAGES],
        "result": {"audit": []}, "error": None,
    }  # fmt: skip


@dataclass
class Ctx:
    """Everything needed to re-validate, re-judge, edit and publish a staged job."""

    view: DocView
    title: str
    fmt: str
    auto_publish: bool
    new_rules: list[Rule] = field(default_factory=list)
    new_rels: list[Relation] = field(default_factory=list)
    base: RuleSet | None = None
    overlay: RuleSet | None = None
    superseded: list[str] = field(default_factory=list)
    impact_full: dict | None = None
    judge_runs: int = 0
    n_raw: int = 0
    verified_quotes: int = 0
    rejected: int = 0
    spent0: float = 0.0


class IngestManager:
    def __init__(self, store) -> None:
        self.store = store
        self.jobs: dict[str, dict] = {}
        self.ctx: dict[str, Ctx] = {}
        self.lock = threading.Lock()
        self.ledger = Ledger(config.ARTIFACTS / "ingest_ledger.json", cap=INGEST_CAP)
        self.llm = LLM(
            ledger=self.ledger, audit_path=config.ARTIFACTS / "audit" / "ingest_audit.jsonl"
        )

    # ---------------------------------------------------------------- API surface
    def start(self, req) -> dict:
        if len(req.text) > MAX_CHARS:
            raise ApiError(
                "DOCUMENT_TOO_LARGE",
                "Documents are limited to 200,000 characters.",
                {"chars": len(req.text)},
            )
        if len(req.text.strip()) < 40:
            raise ApiError("BAD_REQUEST", "Paste or upload the full text of the law.", {})
        hint = (req.jurisdiction_hint or "").strip()
        method = "provided"
        note = f"{hint} was provided"
        if hint:
            try:
                jur = (
                    resolve_jurisdiction(hint)
                    if not hint.startswith(("CA-", "NJ-", "MA-"))
                    else _by_id(hint)
                )
            except KeyError as exc:
                raise ApiError(
                    "UNSUPPORTED_STATE",
                    f"{hint!r} is not one of the jurisdictions Tenantly covers.",
                    {"hint": hint},
                ) from exc
        else:
            label, note = parts.infer_jurisdiction(req.text)
            if label is None:
                raise ApiError(
                    "BAD_REQUEST",
                    f"We could not tell which jurisdiction this is: {note}. Please choose one.",
                    {},
                )
            jur, method = resolve_jurisdiction(label), "inferred"
        view = make_view(req.title, req.text, jur, req.source_url, req.retrieved_at)
        job_id = "job-" + view.doc.doc_id[2:]
        with self.lock:
            existing = self.jobs.get(job_id)
            if existing and existing["status"] in ("running", "ready", "review_required"):
                return {
                    "job_id": job_id,
                    "status": existing["status"],
                    "events_url": f"/v1/ingest/{job_id}/events",
                }
            if self.ledger.total >= self.ledger.cap:
                raise ApiError(
                    "BUDGET_EXCEEDED", "The ingest budget for this deployment is used up.", {}
                )
            job = new_job(job_id)
            self.jobs[job_id] = job
            self.ctx[job_id] = Ctx(
                view=view,
                title=req.title,
                fmt=getattr(req, "format", None) or "text",
                auto_publish=bool(req.auto_publish),
            )
        job["result"]["source"] = {
            "title": req.title, "doc_id": view.doc.doc_id, "chars": view.doc.chars, "doc_type": view.doc_type,
            "format": self.ctx[job_id].fmt, "jurisdiction": _jur_json(jur), "url": view.doc.url, "text": req.text,
        }  # fmt: skip
        job["result"]["inferred"] = {
            "jurisdiction_method": method,
            "jurisdiction_note": note,
            "effective_date": None,
        }
        self._audit(
            job,
            "received",
            f"{view.doc.chars} characters for {jur.label}; auto-publish {'on' if req.auto_publish else 'off'}",
        )
        threading.Thread(target=self._run, args=(job_id,), daemon=True).start()
        return {"job_id": job_id, "status": "running", "events_url": f"/v1/ingest/{job_id}/events"}

    def get(self, job_id: str) -> dict:
        job = self.jobs.get(job_id)
        if not job:
            raise ApiError("JOB_NOT_FOUND", "We couldn't find this job.", {"job_id": job_id})
        return job

    def events(self, job_id: str):
        job = self.get(job_id)
        sent: dict[str, str] = {}
        last_state = None
        while True:
            for s in job["stages"]:
                key = f"{s['status']}|{s['detail']}"
                if s["status"] != "pending" and sent.get(s["stage"]) != key:
                    sent[s["stage"]] = key
                    yield f"event: stage\ndata: {json.dumps(s)}\n\n"
            if job["state"] != last_state and job["state"]:
                last_state = job["state"]
                yield f"event: state\ndata: {json.dumps({'state': job['state'], 'status': job['status']})}\n\n"
            if job["status"] in ("ready", "review_required", "published", "rejected", "failed"):
                break
            time.sleep(0.4)
        if job["status"] == "failed":
            yield f"event: error\ndata: {json.dumps(job['error'])}\n\n"
        else:
            impact = job["result"].get("impact") or {}
            yield f"event: impact\ndata: {json.dumps(impact)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': job['status'], 'state': job['state']})}\n\n"

    # ---------------------------------------------------------------- review actions
    def publish(self, job_id: str, approve: bool = False) -> dict:
        job = self.get(job_id)
        ctx = self.ctx.get(job_id)
        if job["status"] == "published":
            raise ApiError(
                "ALREADY_PUBLISHED", "This job was already published.", {"job_id": job_id}
            )
        if job["status"] not in ("ready", "review_required") or ctx is None:
            raise ApiError("JOB_NOT_READY", "This job is not ready to publish.", {"job_id": job_id})
        validation = job["result"].get("validation")
        if not validation or not validation["passed"]:
            raise ApiError(
                "JOB_NOT_READY",
                "Validation failed. Edit the extraction to fix the failing checks before publishing.",
                {"job_id": job_id},
            )
        if job["status"] == "review_required" and not approve:
            raise ApiError(
                "JOB_NOT_READY",
                "The Judge asked for human review. Approve it explicitly to publish.",
                {"job_id": job_id},
            )
        who = (
            "reviewer approval"
            if job["status"] == "review_required"
            else ("auto-publish policy" if ctx.auto_publish else "admin publish")
        )
        return self._publish(job, ctx, who)

    def reject(self, job_id: str) -> dict:
        job = self.get(job_id)
        if job["status"] in ("published", "running"):
            raise ApiError("JOB_NOT_READY", "Only staged jobs can be rejected.", {"job_id": job_id})
        job["status"], job["state"], job["stage"] = "rejected", "rejected", "failed"
        self._audit(job, "rejected", "rejected by reviewer; nothing was published")
        self._persist(job)
        return {"job_id": job_id, "state": "rejected"}

    def rejudge(self, job_id: str) -> dict:
        job = self.get(job_id)
        ctx = self.ctx.get(job_id)
        if job["status"] not in ("ready", "review_required") or ctx is None:
            raise ApiError(
                "JOB_NOT_READY", "Only staged jobs can be judged again.", {"job_id": job_id}
            )
        ctx.judge_runs += 1
        self._judge_and_decide(job, ctx)
        return {"job_id": job_id, "state": job["state"]}

    def edit(self, job_id: str, rules: list[dict]) -> dict:
        job = self.get(job_id)
        ctx = self.ctx.get(job_id)
        if job["status"] not in ("ready", "review_required") or ctx is None:
            raise ApiError("JOB_NOT_READY", "Only staged jobs can be edited.", {"job_id": job_id})
        try:
            edited = [Rule.model_validate(r) for r in rules]
        except Exception as exc:  # noqa: BLE001
            raise ApiError(
                "BAD_REQUEST",
                "The edited JSON is not a valid rule list.",
                {"reason": str(exc)[:300]},
            ) from exc
        ids = [r.rule_id for r in edited]
        if len(set(ids)) != len(ids) or not edited:
            raise ApiError("BAD_REQUEST", "Rule ids must be present and unique.", {})
        ctx.new_rules = edited
        self._audit(
            job,
            "edited",
            f"reviewer edited the extraction ({len(edited)} rules); validation and the Judge must run again",
        )
        self._rebuild(job, ctx, rerun_judge=False)
        return {"job_id": job_id, "state": job["state"]}

    # ---------------------------------------------------------------- the pipeline
    def _set(
        self, job: dict, stage: str, status: str, detail: str = "", ms: int | None = None
    ) -> None:
        for s in job["stages"]:
            if s["stage"] == stage:
                s.update(status=status, detail=detail, ms=ms)
        if status == "running":
            job["stage"] = stage

    def _audit(self, job: dict, event: str, detail: str) -> None:
        job["result"].setdefault("audit", []).append(
            {"ts": _now(), "event": event, "detail": detail}
        )

    def _timed(self, job, stage, fn, detail_fn=lambda r: ""):
        self._set(job, stage, "running")
        t = time.monotonic()
        out = fn()
        self._set(job, stage, "done", detail_fn(out), int((time.monotonic() - t) * 1000))
        return out

    def _run(self, job_id: str) -> None:
        job, ctx = self.jobs[job_id], self.ctx[job_id]
        ctx.spent0 = self.ledger.total
        try:
            self._pipeline(job, ctx)
        except BudgetExceeded as exc:
            self._fail(job, "BUDGET_EXCEEDED", f"The ingest budget would be exceeded: {exc}")
        except ApiError as exc:
            self._fail(job, exc.code, exc.message)
        except Exception as exc:  # noqa: BLE001
            log.exception("ingest failed job=%s", job_id)
            self._fail(job, "INTERNAL", f"Ingest failed: {type(exc).__name__}")
        job["finished_at"] = _now()

    def _fail(self, job: dict, code: str, message: str) -> None:
        job["status"], job["stage"] = "failed", "failed"
        job["error"] = {"code": code, "message": message}
        for s in job["stages"]:
            if s["status"] == "running":
                s["status"] = "failed"
        self._audit(job, "failed", f"{code}: {message}")

    def _pipeline(self, job: dict, ctx: Ctx) -> None:
        view, res = ctx.view, job["result"]
        src = res["source"]
        self._timed(
            job,
            "received",
            lambda: None,
            lambda _: f"{view.doc.chars:,} characters, classified as {view.doc_type}",
        )
        self._timed(
            job,
            "parse",
            lambda: None,
            lambda _: (
                f"{ {'pdf': 'PDF', 'docx': 'Word document'}.get(src['format'], 'pasted or plain text') }, {len(view.model_text().splitlines())} lines after removing page chrome"
            ),
        )
        secs = self._timed(
            job,
            "sectionize",
            lambda: sectionizer.sectionize(view.doc, view.masked, view.segments),
            lambda s: f"{len(s)} sections identified",
        )
        keep = self._timed(
            job,
            "triage",
            lambda: extract.triage_sections(self.llm, view, secs),
            lambda k: (
                "all sections kept" if k is None else f"{len(k)} sections kept for extraction"
            ),
        )

        def do_extract():
            raw_a = extract.run_pass(self.llm, view, extract.text_for_pass_a(view, secs, keep), "A")
            raw_b = extract.run_pass(self.llm, view, view.model_text(), "B")
            ok_a, rej_a = extract.finalize_all(view, raw_a, "A")
            ok_b, rej_b = extract.finalize_all(view, raw_b, "B")
            return ok_a, ok_b, rej_a + rej_b, len(raw_a) + len(raw_b)

        ok_a, ok_b, rejected, ctx.n_raw = self._timed(
            job,
            "extract",
            do_extract,
            lambda r: f"{r[3]} candidate rules from two independent passes",
        )
        ctx.verified_quotes, ctx.rejected = len(ok_a) + len(ok_b), len(rejected)
        res["verification"] = {
            "quotes_checked": ctx.n_raw,
            "quotes_verified": ctx.verified_quotes,
            "rejected": ctx.rejected,
        }
        self._timed(
            job,
            "verify",
            lambda: None,
            lambda _: (
                f"{ctx.verified_quotes} of {ctx.n_raw} quotes found byte for byte in the document; {ctx.rejected} rejected"
            ),
        )
        rules = self._timed(
            job,
            "crosscheck",
            lambda: extract.merge_passes(self.llm, view, ok_a, ok_b),
            lambda r: f"{len(r)} rules after cross-check and voting",
        )
        if not rules:
            raise ApiError(
                "BAD_REQUEST", "No rule with a verifiable quote was found in this document.", {}
            )
        self._timed(
            job,
            "jurisdiction",
            lambda: None,
            lambda _: (
                f"{view.jurisdiction.label} ({res['inferred']['jurisdiction_method']}): {res['inferred']['jurisdiction_note']}"
            ),
        )
        eff = parts.effective_year(rules)
        res["inferred"]["effective_date"] = eff.isoformat() if eff else None
        self._timed(
            job,
            "calendar",
            lambda: None,
            lambda _: ", ".join(
                sorted({r.effective.output() or "no date in the text" for r in rules})
            ),
        )

        base = self.store.rs
        ctx.base = base
        taken = {}
        for r in rules:
            cell = (r.jurisdiction.id, r.category)
            taken[cell] = sum(
                1
                for x in base.rules
                if (x.jurisdiction.id, x.category) == cell and x.lifecycle == "enacted"
            )
        final = assemble.finalize_rules(rules)
        counts: dict[tuple, int] = {}
        renamed = []
        for r in final:
            cell = (r.jurisdiction.id, r.category)
            counts[cell] = counts.get(cell, 0) + 1
            prefix, tail = r.rule_id.rsplit("-", 1)
            tail = f"{taken.get(cell, 0) + counts[cell]:02d}" if r.lifecycle == "enacted" else tail
            renamed.append(r.model_copy(update={"rule_id": f"{prefix}-{tail}"}))
        ctx.new_rules = renamed

        def do_link():
            tmp = RuleSet(data_version="tmp", compiled_at=_now(), rules=base.rules + ctx.new_rules)
            views = {view.doc.doc_id: view}
            raw = link.link_documents(self.llm, ctx.new_rules, views)
            rels, _ = link.verify_relations(raw, tmp.rules, views)
            offset = len(base.relations)
            return [
                r.model_copy(update={"relation_id": f"REL-{offset + i + 1:03d}"})
                for i, r in enumerate(rels)
            ]

        ctx.new_rels = self._timed(
            job,
            "link",
            do_link,
            lambda r: f"{len(r)} precedence or conflict relations found in the text",
        )
        ctx.new_rules = self._timed(
            job,
            "explain",
            lambda: [explain_stage.explain_rule(self.llm, r) for r in ctx.new_rules],
            lambda r: f"{len(r)} rules written up in English and Spanish",
        )
        self._rebuild(job, ctx, rerun_judge=True, timed=True)

    # ---------------------------------------------------------------- assembling the staged view
    def _overlay(self, ctx: Ctx) -> RuleSet:
        """Live rules plus the staged ones. A rule with the same provision but new text replaces its
        earlier version in the overlay (and is recorded as superseded)."""
        base = ctx.base
        new_keys = {
            (r.jurisdiction.id, r.category, cite_key(r.citation.cite)) for r in ctx.new_rules
        }
        ctx.superseded = []
        kept = []
        for old in base.rules:
            key = (old.jurisdiction.id, old.category, cite_key(old.citation.cite))
            same = next(
                (
                    n
                    for n in ctx.new_rules
                    if (n.jurisdiction.id, n.category, cite_key(n.citation.cite)) == key
                ),
                None,
            )
            if (
                key in new_keys
                and same is not None
                and same.citation.quote != old.citation.quote
                and old.lifecycle == "enacted"
            ):
                ctx.superseded.append(old.rule_id)
                continue
            kept.append(old)
        rules = sorted(kept + ctx.new_rules, key=lambda r: r.rule_id)
        return base.model_copy(update={"rules": rules, "relations": base.relations + ctx.new_rels})

    def _rebuild(self, job: dict, ctx: Ctx, rerun_judge: bool, timed: bool = False) -> None:
        """(Re)compute everything derived from the staged rules, in pipeline order."""
        res = job["result"]
        step = (
            (lambda stage, fn, d=lambda r: "": self._timed(job, stage, fn, d))
            if timed
            else (lambda stage, fn, d=lambda r: "": fn())
        )
        ctx.overlay = self._overlay(ctx)
        res["rules_json"] = [r.model_dump(mode="json") for r in ctx.new_rules]
        res["submission_json"] = [rule_record(r, ctx.overlay) for r in ctx.new_rules]
        preview = self.store.preview(ctx.overlay)
        res["rules"] = [preview._detail(r) for r in ctx.new_rules]
        res["relations"] = [rel for r in ctx.new_rules for rel in preview._detail(r)["relations"]]
        res["findings"] = []
        hierarchy = step(
            "priority",
            lambda: parts.build_hierarchy(ctx.view, ctx.new_rules, ctx.overlay, ctx.base),
            lambda h: (
                f"{len(h['levels'])} levels, {len(h['relations'])} precedence relation(s) evaluated"
            ),
        )
        res["hierarchy"] = hierarchy
        graph = step(
            "graph",
            lambda: parts.build_graph(ctx.view, ctx.new_rules, ctx.overlay, ctx.base),
            lambda g: (
                f"{len(g['nodes'])} nodes and {len(g['edges'])} relationships built from the extracted data"
            ),
        )
        res["graph"] = graph
        validation = step(
            "validate",
            lambda: parts.validate_staged(
                ctx.view, ctx.new_rules, ctx.overlay, ctx.base, ctx.new_rels
            ),
            lambda v: (
                f"{sum(c['status'] == 'pass' for c in v['checks'])} of {len(v['checks'])} checks passed"
                + ("" if v["passed"] else "; validation failed")
            ),
        )
        res["validation"] = validation
        if timed:
            self._set(job, "judge", "running")
        job["state"] = "staged"
        self._audit(
            job,
            "staged",
            f"{len(ctx.new_rules)} rules held in staging, apart from the live law set",
        )
        self._audit(
            job,
            "validation",
            "passed"
            if validation["passed"]
            else "failed: "
            + "; ".join(c["detail"] for c in validation["checks"] if c["status"] == "fail"),
        )
        if rerun_judge:
            t = time.monotonic()
            self._judge(job, ctx)
            if timed:
                j = res["judge"]
                self._set(
                    job,
                    "judge",
                    "done",
                    f"verdict {j['verdict']}, confidence {j['confidence']:.0%}",
                    int((time.monotonic() - t) * 1000),
                )
        else:
            res["judge"] = None
            job["status"], job["state"] = "review_required", "review_required"
            res["policy"] = parts.decide(validation, None, 0, ctx.auto_publish, MIN_CONFIDENCE)
        impact_full = step(
            "impact",
            lambda: self._impact(ctx),
            lambda i: f"{i['affected_count']} buildings reached",
        )
        ctx.impact_full = impact_full
        res["impact"] = {k: v for k, v in impact_full.items() if not k.startswith("_")}
        res["cost_usd"] = round(self.ledger.total - ctx.spent0, 4)
        res["cache_hit"] = self.ledger.total == ctx.spent0
        self._decide(job, ctx, validation)
        if timed:
            self._set(job, "staged", "done", f"state: {job['state'].replace('_', ' ')}", 0)

    def _judge(self, job: dict, ctx: Ctx) -> None:
        res = job["result"]
        try:
            res["judge"] = parts.run_judge(
                self.llm,
                ctx.view,
                ctx.new_rules,
                res["validation"],
                res["hierarchy"],
                ctx.judge_runs,
            )
        except BudgetExceeded:
            res["judge"] = {"verdict": "review", "confidence": 0.0, "model": None, "checks": [], "cache_hit": False, "rerun": ctx.judge_runs,
                            "issues": [{"severity": "warning", "rule_id": None, "message": "The Judge could not run because the model budget is used up; a human must review.", "source_section": None}]}  # fmt: skip
        j = res["judge"]
        self._audit(
            job,
            "judge",
            f"verdict {j['verdict']}, confidence {j['confidence']:.0%}, {len(j['issues'])} issue(s)",
        )

    def _judge_and_decide(self, job: dict, ctx: Ctx) -> None:
        self._judge(job, ctx)
        self._decide(job, ctx, job["result"]["validation"])

    def _decide(self, job: dict, ctx: Ctx, validation: dict) -> None:
        res = job["result"]
        conflicts = (res.get("impact") or {}).get("conflicts", 0)
        policy = parts.decide(
            validation, res.get("judge"), conflicts, ctx.auto_publish, MIN_CONFIDENCE
        )
        res["policy"] = policy
        if policy["decision"] == "review":
            job["status"], job["state"] = "review_required", "review_required"
            self._audit(job, "review_required", "; ".join(policy["reasons"]))
            return
        job["status"], job["state"] = "ready", "verified"
        self._audit(job, "verified", "deterministic validation and the Judge passed")
        if policy["decision"] == "auto_publish":
            self._publish(job, ctx, "auto-publish policy")

    # ---------------------------------------------------------------- impact and publishing
    def _impact(self, ctx: Ctx) -> dict:
        from engine.rules.render import address_label

        base, overlay = ctx.base, ctx.overlay
        ids = [r.rule_id for r in ctx.new_rules]
        effs = [r.effective.lo for r in ctx.new_rules if r.effective.lo]
        on = max([DEFAULT_DATE] + effs)
        affected, conflicts, changed_existing = [], 0, set()
        for aid, rec in self.store.records.items():
            env = AddressEnv(rec)
            before = {o.rule_id: o for o in evaluate_address(base, rec, env, on).outcomes}
            after = {o.rule_id: o for o in evaluate_address(overlay, rec, env, on).outcomes}
            existing_changed = {
                rid for rid in set(before) | set(after)
                if rid not in ids and (before[rid].result if rid in before else "none") != (after[rid].result if rid in after else "none")
            }  # fmt: skip
            changed_existing |= existing_changed
            if any(i in after for i in ids) or existing_changed:
                flag = any(after[i].conflict_flag for i in ids if i in after)
                conflicts += flag
                watch = ids + sorted(existing_changed)
                affected.append({
                    "address_id": aid, "label": address_label(rec), "lat": rec["lat"], "lon": rec["lon"],
                    "legal_city": rec["legal_city"],
                    "before": [{"rule_id": i, "result": before[i].result if i in before else "none"} for i in watch],
                    "after": [{"rule_id": i, "result": after[i].result if i in after else "none"} for i in watch],
                    "conflict_flag": flag,
                })  # fmt: skip
        eff = min(effs).isoformat() if effs else None
        return {"affected_count": len(affected), "sample": affected[:12], "effective_date": eff, "conflicts": conflicts,
                "_all": affected, "_on": on.isoformat(), "_changed_existing": sorted(changed_existing)}  # fmt: skip

    def _publish(self, job: dict, ctx: Ctx, who: str) -> dict:
        res = job["result"]
        impact = ctx.impact_full
        new_ids = {r.rule_id for r in ctx.new_rules}
        cid = self.store.apply_overlay(ctx.overlay, new_ids, job, impact["_all"], impact["_on"])
        touching = parts.related_relations(ctx.overlay, new_ids)
        existing_touched = sum(
            1
            for rel, src, tg in touching
            if rel.relation_id not in {r.relation_id for r in ctx.new_rels}
        )
        places = sorted(
            {a["legal_city"] or "(address not located; state rules only)" for a in impact["_all"]}
        )
        res["changes"] = {
            "document": ctx.title, "rules_added": len(ctx.new_rules), "relationships_added": len(ctx.new_rels),
            "existing_relationships_touched": existing_touched, "rules_superseded": list(ctx.superseded),
            "existing_rules_changed": list(impact["_changed_existing"]), "affected_jurisdictions": places,
            "affected_properties": impact["affected_count"],
            "graph_nodes_added": res["graph"]["delta"]["nodes"], "graph_edges_added": res["graph"]["delta"]["edges"], "change_id": cid,
        }  # fmt: skip
        job["status"], job["state"], job["stage"] = "published", "published", "published"
        self._audit(
            job,
            "published",
            f"published by {who}; change event {cid}; {impact['affected_count']} buildings reached",
        )
        self._persist(job)
        return {"change_id": cid, "published_at": _now()}

    def _persist(self, job: dict) -> None:
        try:
            JOB_DIR.mkdir(parents=True, exist_ok=True)
            atomic_write_json(JOB_DIR / f"{job['job_id']}.json", job)
        except OSError:
            log.warning("could not persist the audit trail for %s", job["job_id"])


def _by_id(jid: str):
    from engine.api.store import jurisdiction_ref

    return jurisdiction_ref(jid)


def _jur_json(j) -> dict:
    return {
        "id": j.id,
        "level": j.level,
        "name": j.name,
        "label": j.label,
        "state": j.state,
        "geoid": j.geoid,
        "in_scope": True,
    }
