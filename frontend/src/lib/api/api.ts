// The only data-access surface for components.
import Fuse from "fuse.js";
import { z } from "zod";
import { API_BASE_URL, IS_MOCK } from "@/config";
import { request } from "./client";
import { withFallback } from "./fallback";
import { mockStreamIngest } from "./mock";
import type {
  AddressIndexItem,
  Category,
  ChangeEvent,
  EvidenceTier,
  Finding,
  ISODate,
  IngestJob,
  Lang,
  LookupResponse,
  Meta,
  OpenQuestion,
  ProofResponse,
  ResolveResponse,
  RuleDetail,
  RuleStatus,
  SourceDoc,
  StateCode,
  TimelineResponse,
} from "./types";

export type { AddressIndexItem };

export interface RuleFilters {
  state?: StateCode;
  jurisdiction_id?: string;
  category?: Category;
  status?: RuleStatus;
  tier?: EvidenceTier;
  q?: string;
}
export interface CustomLookupBody {
  address_id: string;
  as_of: ISODate;
  facts: Record<string, number | string | boolean | null>;
}
export interface IngestBody {
  title: string;
  text: string;
  jurisdiction_hint: string;
  source_url: string;
  retrieved_at: string;
  auto_publish?: boolean;
  format?: string;
}
export interface IngestStarted {
  job_id: string;
  status: IngestJob["status"];
  events_url: string;
}
export type IngestEvent = { type: "stage" | "state" | "impact" | "done" | "error"; data: unknown };
export interface SubscribeBody {
  email: string;
  address_id: string;
  lang: Lang;
}
export interface Subscription {
  subscription_id: string;
  unsubscribe_token: string;
  feeds: { atom: string; ics: string };
}
export interface AuditEntry {
  audit_id: string;
  rule_id: string;
  at: string;
  action: string;
  detail: string;
}
export interface JurisdictionFeature {
  type: "Feature";
  properties: { id: string; name: string; label: string };
  geometry: { type: "Polygon"; coordinates: [number, number][][] } | { type: "MultiPolygon"; coordinates: [number, number][][][] };
}

const qs = (params: Record<string, string | number | undefined | null>) => {
  const s = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v != null && v !== "" && s.set(k, String(v)));
  const out = s.toString();
  return out ? `?${out}` : "";
};
const post = (body: unknown, headers: Record<string, string> = {}): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
  headers: { "Content-Type": "application/json", ...headers },
});

/** The API wraps lists as { items }; the app works with plain arrays. */
async function unwrap<T>(p: Promise<T[] | { items: T[] }>): Promise<T[]> {
  const r = await p;
  return Array.isArray(r) ? r : r.items;
}

const metaSchema = z.object({ app: z.literal("Tenantly"), data_version: z.string(), default_as_of: z.string() }).passthrough();
const lookupSchema = z.object({ address: z.object({ address_id: z.string() }).passthrough(), as_of: z.string(), categories: z.array(z.unknown()) }).passthrough();

export const getMeta = () => withFallback(() => request<Meta>("/meta", { fn: "getMeta", schema: metaSchema }), "/meta.json");

export const getAddressIndex = () =>
  unwrap(
    withFallback(
      () => request<AddressIndexItem[] | { items: AddressIndexItem[] }>("/addresses", { fn: "getAddressIndex" }),
      "/addresses.json",
    ),
  );

export const searchAddresses = (q: string, limit = 8) =>
  unwrap(request<{ items: AddressIndexItem[] }>(`/addresses/search${qs({ q, limit })}`, { fn: "searchAddresses" }));

export const resolveAddress = (query: string) =>
  request<ResolveResponse>("/resolve", { fn: "resolveAddress", ...post({ query }) });

export const getLookup = (addressId: string, asOf: ISODate) =>
  request<LookupResponse>(`/lookup/${encodeURIComponent(addressId)}${qs({ as_of: asOf })}`, { fn: "getLookup", schema: lookupSchema });

export const postCustomLookup = (body: CustomLookupBody) =>
  request<LookupResponse>("/lookup/custom", { fn: "postCustomLookup", schema: lookupSchema, ...post(body) });

export const getTimeline = (addressId: string) =>
  withFallback(
    () => request<TimelineResponse>(`/timeline/${encodeURIComponent(addressId)}`, { fn: "getTimeline" }),
    `/timeline/${addressId}.json`,
  );

export const getJurisdictionGeo = (id: string) =>
  withFallback(() => request<JurisdictionFeature>(`/geo/jurisdictions/${encodeURIComponent(id)}`, { fn: "getJurisdictionGeo" }), `/geo/${id}.json`);

export const listRules = (filters: RuleFilters = {}) =>
  unwrap(
    withFallback(
      () => request<{ items: RuleDetail[] }>(`/rules${qs({ ...filters })}`, { fn: "listRules" }),
      "/rules.json",
    ),
  );

export const getRule = (ruleId: string) =>
  request<RuleDetail>(`/rules/${encodeURIComponent(ruleId)}`, { fn: "getRule" });

export const listFindings = (filters: { state?: StateCode | undefined } = {}) =>
  unwrap(
    withFallback(
      () => request<{ items: Finding[] }>(`/findings${qs({ ...filters })}`, { fn: "listFindings" }),
      "/findings.json",
    ),
  );

export const listOpenQuestions = () =>
  unwrap(
    withFallback(
      () => request<{ items: OpenQuestion[] }>("/open-questions", { fn: "listOpenQuestions" }),
      "/open_questions.json",
    ),
  );

export const getSource = (docId: string, ruleId?: string, window?: number) =>
  request<SourceDoc>(`/sources/${encodeURIComponent(docId)}${qs({ rule_id: ruleId, window })}`, { fn: "getSource" });

export const listChanges = () =>
  unwrap(
    withFallback(() => request<{ items: ChangeEvent[] }>("/changes", { fn: "listChanges" }), "/changes.json"),
  );

export const getChange = (changeId: string) =>
  withFallback(() => request<ChangeEvent>(`/changes/${encodeURIComponent(changeId)}`, { fn: "getChange" }), `/changes/${changeId}.json`);

export const startIngest = (body: IngestBody, adminToken: string) =>
  request<IngestStarted>("/ingest", { fn: "startIngest", ...post(body, { "X-Admin-Token": adminToken }) });

export const getIngest = (jobId: string) => request<IngestJob>(`/ingest/${encodeURIComponent(jobId)}`, { fn: "getIngest" });

export function streamIngest(jobId: string, onEvent: (e: IngestEvent) => void): () => void {
  if (IS_MOCK) return mockStreamIngest(jobId, onEvent);
  const es = new EventSource(`${API_BASE_URL}/v1/ingest/${encodeURIComponent(jobId)}/events`);
  const types: IngestEvent["type"][] = ["stage", "state", "impact", "done", "error"];
  types.forEach((type) =>
    es.addEventListener(type, (ev) => {
      const raw = (ev as MessageEvent).data;
      let data: unknown = raw;
      try {
        data = raw ? JSON.parse(raw) : null;
      } catch {
        /* keep raw */
      }
      onEvent({ type, data });
      if (type === "done" || type === "error") es.close();
    }),
  );
  return () => es.close();
}

export const publishIngest = (jobId: string, adminToken: string, approve = false) =>
  request<{ change_id: string; published_at: string }>(
    `/ingest/${encodeURIComponent(jobId)}/publish${qs({ approve: approve ? "true" : undefined })}`,
    { fn: "publishIngest", ...post({}, { "X-Admin-Token": adminToken }) },
  );

export const rejectIngest = (jobId: string, adminToken: string) =>
  request<{ job_id: string; state: string }>(`/ingest/${encodeURIComponent(jobId)}/reject`, {
    fn: "rejectIngest",
    ...post({}, { "X-Admin-Token": adminToken }),
  });

export const rejudgeIngest = (jobId: string, adminToken: string) =>
  request<{ job_id: string; state: string }>(`/ingest/${encodeURIComponent(jobId)}/rejudge`, {
    fn: "rejudgeIngest",
    ...post({}, { "X-Admin-Token": adminToken }),
  });

export const editIngest = (jobId: string, rules: Record<string, unknown>[], adminToken: string) =>
  request<{ job_id: string; state: string }>(`/ingest/${encodeURIComponent(jobId)}/edit`, {
    fn: "editIngest",
    ...post({ rules }, { "X-Admin-Token": adminToken }),
  });

/** Uploaded PDF and DOCX files are turned into text by the server; plain text is read in the browser. */
export const extractText = (file: File, adminToken: string) =>
  request<{ text: string; format: string; pages: number | null; chars: number }>(
    `/ingest/extract-text${qs({ filename: file.name })}`,
    {
      fn: "extractText",
      method: "POST",
      body: file,
      headers: { "Content-Type": "application/octet-stream", "X-Admin-Token": adminToken },
    },
  );

export const subscribeAlerts = (body: SubscribeBody) =>
  request<Subscription>("/alerts/subscriptions", { fn: "subscribeAlerts", ...post(body) });

export const unsubscribeAlerts = (token: string) =>
  request<{ ok: boolean }>(`/alerts/subscriptions/${encodeURIComponent(token)}`, { fn: "unsubscribeAlerts", method: "DELETE" });

export const getProof = () => withFallback(() => request<ProofResponse>("/proof", { fn: "getProof" }), "/proof.json");

type ApiAuditItem = {
  ts: string;
  stage: string;
  model: string | null;
  prompt_version: string | null;
  cache_hit: boolean;
  input_sha: string;
  output_sha: string;
  verifier: string | null;
  cost_usd: number;
};

/** Maps the API's audit rows (one per model call) to the app's AuditEntry. */
export const getAudit = async (ruleId?: string, limit = 20): Promise<AuditEntry[]> => {
  const rows = await unwrap(
    request<ApiAuditItem[] | { items: ApiAuditItem[] }>(`/audit${qs({ rule_id: ruleId, limit })}`, { fn: "getAudit" }),
  );
  return rows.map((r) => {
    const raw = r as ApiAuditItem & Partial<AuditEntry>;
    if (raw.audit_id) return raw as AuditEntry;
    return {
      audit_id: `${r.stage}-${r.output_sha.slice(0, 8)}`,
      rule_id: ruleId ?? "",
      at: r.ts,
      action: `${r.stage}${r.model ? ` (${r.model})` : ""}${r.cache_hit ? " [cached]" : ""}`,
      detail: `prompt v${r.prompt_version ?? "?"}; input ${r.input_sha.slice(0, 10)}; output ${r.output_sha.slice(0, 10)}; $${r.cost_usd.toFixed(4)}`,
    };
  });
};

export const submissionUrl = (name: "rules" | "lookups" | "changes") =>
  IS_MOCK ? `#submission-${name}` : `${API_BASE_URL}/v1/submission/${name}.json`;

/** Client-side fuzzy search over the address index (Fuse.js). */
export function createAddressSearcher(items: AddressIndexItem[]) {
  const fuse = new Fuse(items, {
    keys: [
      { name: "label", weight: 0.6 },
      { name: "postal_city", weight: 0.15 },
      { name: "legal_city", weight: 0.15 },
      { name: "zip", weight: 0.1 },
    ],
    threshold: 0.35,
    ignoreLocation: true,
  });
  return (q: string, limit = 8) => (q.trim() ? fuse.search(q, { limit }).map((r) => r.item) : []);
}
