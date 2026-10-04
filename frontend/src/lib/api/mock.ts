// Illustrative mock data shaped like the real API. Not legal information.
// In-memory implementation of the /v1 endpoints, reached through client.request().
import { ApiError } from "./errors";
import { parseRuleQuery, ruleSearchText } from "./ruleQuery";
import { ADDRESS_INDEX, ADDRESSES, ALL_JURISDICTIONS, CATEGORIES, COMPILED_AT, DATA_VERSION, DISCLAIMER, RANGE } from "./mock/data";
import {
  CHANGES,
  OPEN_QUESTIONS,
  addressSummary,
  allFindings,
  buildLookup,
  buildTimeline,
  createJob,
  jobs,
  jurisdictionGeo,
  jurisdictionStack,
  listRuleDefs,
  proof,
  publishJob,
  ruleDetail,
  runJob,
  sourceDoc,
} from "./mock/engine";
import type { Meta, ResolveResponse } from "./types";

const latency = () => new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
const alertSubscriptions = new Map<string, Record<string, unknown>>();

function forcedError(fn: string) {
  if (typeof window === "undefined") return;
  const forced = new URLSearchParams(window.location.search).get("mockError");
  if (forced && forced === fn) {
    throw new ApiError(503, "service_unavailable", `Mock failure for ${fn}`, `mock_${Date.now()}`);
  }
}

const notFound = (what: string) => new ApiError(404, "not_found", `${what} not found`, `mock_${Date.now()}`);

function search(q: string, limit: number) {
  const n = q.trim().toLowerCase();
  if (!n) return [];
  return ADDRESS_INDEX.filter((a) => `${a.label} ${a.zip ?? ""} ${a.legal_city ?? ""}`.toLowerCase().includes(n)).slice(0, limit);
}

export async function mockRequest<T>(fn: string, path: string, init?: RequestInit): Promise<T> {
  await latency();
  forcedError(fn);
  const url = new URL(path, "http://mock.local");
  const p = url.pathname;
  const q = url.searchParams;
  const method = (init?.method ?? "GET").toUpperCase();
  const body: MockBody = init?.body ? (JSON.parse(String(init.body)) as MockBody) : {};
  let m: RegExpMatchArray | null;

  const out = ((): unknown => {
    if (p === "/meta") {
      const meta: Meta = {
        app: "Tenantly", api_version: "v1", data_version: DATA_VERSION, compiled_at: COMPILED_AT,
        default_as_of: "2026-10-01", sources_retrieved_at: "2026-10-01", as_of_range: RANGE,
        categories: CATEGORIES, jurisdictions: ALL_JURISDICTIONS,
        counts: { rules: listRuleDefs().length, findings: allFindings().length, addresses: 500, docs_text: 31, docs_link_only: 6 },
        persistence: "memory", demo_mode: "replay", disclaimer: DISCLAIMER,
      };
      return meta;
    }
    if (p === "/addresses") return ADDRESS_INDEX;
    if (p === "/addresses/search") return search(q.get("q") ?? "", Number(q.get("limit") ?? 8));
    if (p === "/resolve" && method === "POST") {
      const query = String(body.query ?? "");
      const hits = search(query, 5);
      const exact = hits.find((h) => h.label.toLowerCase() === query.trim().toLowerCase()) ?? (hits.length === 1 ? hits[0] : undefined);
      const seed = exact ? ADDRESSES.find((a) => a.id === exact.address_id) : undefined;
      const res: ResolveResponse = seed
        ? { match_type: "sample", address: addressSummary(seed), jurisdiction: jurisdictionStack(seed), candidates: hits, geocoder: "index" }
        : { match_type: hits.length ? "sample" : "not_found", address: null, jurisdiction: null, candidates: hits, geocoder: hits.length ? "index" : null };
      return res;
    }
    if ((m = p.match(/^\/lookup\/([^/]+)$/)) && m[1]! !== "custom") {
      const l = buildLookup(m[1]!, q.get("as_of") ?? "2026-10-01");
      if (!l) throw notFound("Address");
      return l;
    }
    if (p === "/lookup/custom" && method === "POST") {
      const facts: MockFacts = body.facts ?? {};
      const override: { year_built?: number; units?: number; subsidized?: boolean } = {};
      if (facts.year_built != null) override.year_built = Number(facts.year_built);
      if (facts.units != null) override.units = Number(facts.units);
      if (facts.subsidized_or_affordable != null) override.subsidized = Boolean(facts.subsidized_or_affordable);
      const l = buildLookup(String(body.address_id), String(body.as_of ?? "2026-10-01"), override);
      if (!l) throw notFound("Address");
      return l;
    }
    if ((m = p.match(/^\/timeline\/([^/]+)$/))) {
      const t = buildTimeline(m[1]!);
      if (!t) throw notFound("Address");
      return t;
    }
    if ((m = p.match(/^\/geo\/jurisdictions\/([^/]+)$/))) {
      const g = jurisdictionGeo(m[1]!);
      if (!g) throw notFound("Jurisdiction");
      return g;
    }
    if (p === "/rules") {
      const { states, terms } = parseRuleQuery(q.get("q") ?? "");
      return listRuleDefs()
        .filter((r) => !q.get("state") || r.jur.state === q.get("state"))
        .filter((r) => !states.size || states.has(r.jur.state))
        .filter((r) => !q.get("jurisdiction_id") || r.jur.id === q.get("jurisdiction_id"))
        .filter((r) => !q.get("category") || r.category === q.get("category"))
        .filter((r) => !q.get("status") || r.status === q.get("status"))
        .filter((r) => !q.get("tier") || r.citation.tier === q.get("tier"))
        .filter((r) => {
          if (!terms.length) return true;
          const hay = ruleSearchText({
            id: r.id, title: r.title, requirement: r.requirement, cite: r.citation.cite, jurName: r.jur.name,
            jurLabel: r.jur.label, state: r.jur.state, category: r.category, extra: [r.summary.en, r.summary.es],
          });
          return terms.every((t) => hay.includes(t));
        })
        .map(ruleDetail);
    }
    if ((m = p.match(/^\/rules\/([^/]+)$/))) {
      const d = listRuleDefs().find((r) => r.id === m![1]!);
      if (!d) throw notFound("Rule");
      return ruleDetail(d);
    }
    if (p === "/findings") return allFindings().filter((f) => !q.get("state") || f.jurisdiction.state === q.get("state"));
    if (p === "/open-questions") return OPEN_QUESTIONS;
    if ((m = p.match(/^\/sources\/([^/]+)$/))) {
      const s = sourceDoc(m[1]!, q.get("rule_id"));
      if (!s) throw notFound("Source");
      return s;
    }
    if (p === "/changes") return CHANGES;
    if ((m = p.match(/^\/changes\/([^/]+)$/))) {
      const c = CHANGES.find((x) => x.change_id === m![1]!);
      if (!c) throw notFound("Change");
      return c;
    }
    if (p === "/ingest" && method === "POST") {
      const job = createJob();
      return { job_id: job.job_id, status: job.status, events_url: `/v1/ingest/${job.job_id}/events` };
    }
    if ((m = p.match(/^\/ingest\/([^/]+)\/publish$/)) && method === "POST") {
      const r = publishJob(m[1]!);
      if (!r) throw notFound("Ingest job");
      return r;
    }
    if ((m = p.match(/^\/ingest\/([^/]+)$/))) {
      const j = jobs.get(m[1]!);
      if (!j) throw notFound("Ingest job");
      return j;
    }
    if (p === "/alerts/subscriptions" && method === "POST") {
      const id = `sub_${Date.now().toString(36)}`;
      const token = `tok_${id}`;
      const requestBody = JSON.parse(String(init?.body ?? "{}")) as { address_id?: string };
      const created = new Date().toISOString();
      const value = { subscription_id: id, unsubscribe_token: token, address_id: requestBody.address_id ?? "A0016", created_at: created, active: true, created: true, notifications_configured: false, last_notification: null, feeds: { atom: `/v1/alerts/feed/${requestBody.address_id}.atom`, ics: `/v1/alerts/calendar/${requestBody.address_id}.ics` } };
      alertSubscriptions.set(token, value);
      return value;
    }
    if ((m = p.match(/^\/alerts\/subscriptions\/([^/]+)$/)) && method === "GET") {
      const sub = alertSubscriptions.get(m[1]!);
      if (!sub) throw notFound("Watch");
      return sub;
    }
    if ((m = p.match(/^\/alerts\/subscriptions\/([^/]+)$/)) && method === "DELETE") {
      alertSubscriptions.delete(m[1]!);
      return { ok: true };
    }
    if (p === "/proof") return proof();
    if (p === "/audit") {
      const rid = q.get("rule_id");
      return listRuleDefs()
        .filter((r) => !rid || r.id === rid)
        .slice(0, Number(q.get("limit") ?? 20))
        .map((r, i) => ({ audit_id: `aud_${r.id}`, rule_id: r.id, at: "2026-10-01T22:4" + (i % 10) + ":00Z", action: "verified_quote", detail: `Quote for ${r.citation.cite} matched the source document` }));
    }
    throw notFound(`Endpoint ${method} ${p}`);
  })();
  return structuredClone(out) as T;
}

export function mockStreamIngest(jobId: string, onEvent: (e: { type: "stage" | "impact" | "done" | "error"; data: unknown }) => void): () => void {
  const job = jobs.get(jobId);
  if (!job) {
    setTimeout(() => onEvent({ type: "error", data: { code: "not_found", message: "Ingest job not found" } }), 50);
    return () => {};
  }
  return runJob(job, onEvent);
}

interface MockFacts {
  year_built?: number | string | null;
  units?: number | string | null;
  subsidized_or_affordable?: boolean | null;
}
interface MockBody {
  query?: string;
  address_id?: string;
  as_of?: string;
  facts?: MockFacts;
}
