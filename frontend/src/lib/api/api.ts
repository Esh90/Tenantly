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
}
export interface IngestStarted {
  job_id: string;
  status: IngestJob["status"];
  events_url: string;
}
export type IngestEvent = { type: "stage" | "impact" | "done" | "error"; data: unknown };
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
  geometry: { type: "Polygon"; coordinates: [number, number][][] };
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

const metaSchema = z.object({ app: z.literal("Tenantly"), data_version: z.string(), default_as_of: z.string() }).passthrough();
const lookupSchema = z.object({ address: z.object({ address_id: z.string() }).passthrough(), as_of: z.string(), categories: z.array(z.unknown()) }).passthrough();

export const getMeta = () => withFallback(() => request<Meta>("/meta", { fn: "getMeta", schema: metaSchema }), "/meta.json");

export const getAddressIndex = () =>
  withFallback(() => request<AddressIndexItem[]>("/addresses", { fn: "getAddressIndex" }), "/addresses.json");

export const searchAddresses = (q: string, limit = 8) =>
  request<AddressIndexItem[]>(`/addresses/search${qs({ q, limit })}`, { fn: "searchAddresses" });

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
  withFallback(() => request<RuleDetail[]>(`/rules${qs({ ...filters })}`, { fn: "listRules" }), "/rules.json");

export const getRule = (ruleId: string) =>
  request<RuleDetail>(`/rules/${encodeURIComponent(ruleId)}`, { fn: "getRule" });

export const listFindings = (filters: { state?: StateCode | undefined } = {}) =>
  withFallback(() => request<Finding[]>(`/findings${qs({ ...filters })}`, { fn: "listFindings" }), "/findings.json");

export const listOpenQuestions = () =>
  withFallback(() => request<OpenQuestion[]>("/open-questions", { fn: "listOpenQuestions" }), "/open_questions.json");

export const getSource = (docId: string, ruleId?: string, window?: number) =>
  request<SourceDoc>(`/sources/${encodeURIComponent(docId)}${qs({ rule_id: ruleId, window })}`, { fn: "getSource" });

export const listChanges = () =>
  withFallback(() => request<ChangeEvent[]>("/changes", { fn: "listChanges" }), "/changes.json");

export const getChange = (changeId: string) =>
  withFallback(() => request<ChangeEvent>(`/changes/${encodeURIComponent(changeId)}`, { fn: "getChange" }), `/changes/${changeId}.json`);

export const startIngest = (body: IngestBody, adminToken: string) =>
  request<IngestStarted>("/ingest", { fn: "startIngest", ...post(body, { "X-Admin-Token": adminToken }) });

export const getIngest = (jobId: string) => request<IngestJob>(`/ingest/${encodeURIComponent(jobId)}`, { fn: "getIngest" });

export function streamIngest(jobId: string, onEvent: (e: IngestEvent) => void): () => void {
  if (IS_MOCK) return mockStreamIngest(jobId, onEvent);
  const es = new EventSource(`${API_BASE_URL}/v1/ingest/${encodeURIComponent(jobId)}/events`);
  const types: IngestEvent["type"][] = ["stage", "impact", "done", "error"];
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

export const publishIngest = (jobId: string, adminToken: string) =>
  request<{ change_id: string; published_at: string }>(`/ingest/${encodeURIComponent(jobId)}/publish`, {
    fn: "publishIngest",
    ...post({}, { "X-Admin-Token": adminToken }),
  });

export const subscribeAlerts = (body: SubscribeBody) =>
  request<Subscription>("/alerts/subscriptions", { fn: "subscribeAlerts", ...post(body) });

export const unsubscribeAlerts = (token: string) =>
  request<{ ok: boolean }>(`/alerts/subscriptions/${encodeURIComponent(token)}`, { fn: "unsubscribeAlerts", method: "DELETE" });

export const getProof = () => withFallback(() => request<ProofResponse>("/proof", { fn: "getProof" }), "/proof.json");

export const getAudit = (ruleId?: string, limit = 20) =>
  request<AuditEntry[]>(`/audit${qs({ rule_id: ruleId, limit })}`, { fn: "getAudit" });

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
