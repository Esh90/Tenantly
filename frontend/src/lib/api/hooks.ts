import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./api";
import type { ISODate } from "./types";

const STALE = 5 * 60 * 1000;

export const keys = {
  meta: ["meta"] as const,
  addresses: ["addresses"] as const,
  lookup: (id: string, asOf: string) => ["lookup", id, asOf] as const,
  timeline: (id: string) => ["timeline", id] as const,
  geo: (id: string) => ["geo", id] as const,
  rules: (f: api.RuleFilters) => ["rules", f] as const,
  rule: (id: string) => ["rule", id] as const,
  findings: (state?: string) => ["findings", state ?? "all"] as const,
  openQuestions: ["open-questions"] as const,
  source: (doc: string, rule?: string) => ["source", doc, rule ?? ""] as const,
  changes: ["changes"] as const,
  change: (id: string) => ["change", id] as const,
  ingest: (id: string) => ["ingest", id] as const,
  proof: ["proof"] as const,
  audit: (id?: string) => ["audit", id ?? "all"] as const,
};

export const useMeta = () => useQuery({ queryKey: keys.meta, queryFn: api.getMeta, staleTime: STALE });
export const useAddressIndex = () =>
  useQuery({ queryKey: keys.addresses, queryFn: api.getAddressIndex, staleTime: STALE });
export const useLookup = (id: string, asOf: ISODate) =>
  useQuery({ queryKey: keys.lookup(id, asOf), queryFn: () => api.getLookup(id, asOf), staleTime: STALE, enabled: !!id });
export const useTimeline = (id: string) =>
  useQuery({ queryKey: keys.timeline(id), queryFn: () => api.getTimeline(id), staleTime: STALE, gcTime: 30 * 60 * 1000, enabled: !!id });
export const useJurisdictionGeo = (id: string | null | undefined) =>
  useQuery({ queryKey: keys.geo(id ?? ""), queryFn: () => api.getJurisdictionGeo(id as string), staleTime: STALE, enabled: !!id });
export const useRules = (f: api.RuleFilters = {}) =>
  useQuery({ queryKey: keys.rules(f), queryFn: () => api.listRules(f), staleTime: STALE });
export const useRule = (id: string) => useQuery({ queryKey: keys.rule(id), queryFn: () => api.getRule(id), staleTime: STALE });
export const useFindings = (state?: api.RuleFilters["state"]) =>
  useQuery({ queryKey: keys.findings(state), queryFn: () => api.listFindings({ state }), staleTime: STALE });
export const useOpenQuestions = () =>
  useQuery({ queryKey: keys.openQuestions, queryFn: api.listOpenQuestions, staleTime: STALE });
export const useSource = (docId: string, ruleId?: string) =>
  useQuery({ queryKey: keys.source(docId, ruleId), queryFn: () => api.getSource(docId, ruleId), staleTime: STALE, enabled: !!docId });
export const useChanges = () => useQuery({ queryKey: keys.changes, queryFn: api.listChanges, staleTime: STALE });
export const useChange = (id: string) => useQuery({ queryKey: keys.change(id), queryFn: () => api.getChange(id), staleTime: STALE });
export const useIngest = (id: string) => useQuery({ queryKey: keys.ingest(id), queryFn: () => api.getIngest(id), enabled: !!id });
export const useProof = () => useQuery({ queryKey: keys.proof, queryFn: api.getProof, staleTime: STALE });
export const useAudit = (ruleId?: string) =>
  useQuery({ queryKey: keys.audit(ruleId), queryFn: () => api.getAudit(ruleId), staleTime: STALE });

export const useCustomLookup = () => useMutation({ mutationFn: api.postCustomLookup });
export const useResolveAddress = () => useMutation({ mutationFn: api.resolveAddress });
export const useSubscribeAlerts = () => useMutation({ mutationFn: api.subscribeAlerts });
export const useUnsubscribeAlerts = () => useMutation({ mutationFn: api.unsubscribeAlerts });
export const useStartIngest = () =>
  useMutation({ mutationFn: (v: { body: api.IngestBody; token: string }) => api.startIngest(v.body, v.token) });
const invalidateLive = (qc: ReturnType<typeof useQueryClient>) => {
  for (const k of ["changes", "change", "timeline", "lookup", "rules", "rule", "meta", "findings", "open-questions", "proof", "addresses", "source", "audit"]) qc.invalidateQueries({ queryKey: [k] });
};
export function usePublishIngest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { jobId: string; token: string; approve?: boolean }) => api.publishIngest(v.jobId, v.token, v.approve),
    onSuccess: () => invalidateLive(qc),
  });
}
export const useRejectIngest = () => useMutation({ mutationFn: (v: { jobId: string; token: string }) => api.rejectIngest(v.jobId, v.token) });
export const useRejudgeIngest = () => useMutation({ mutationFn: (v: { jobId: string; token: string }) => api.rejudgeIngest(v.jobId, v.token) });
export const useEditIngest = () =>
  useMutation({ mutationFn: (v: { jobId: string; rules: Record<string, unknown>[]; token: string }) => api.editIngest(v.jobId, v.rules, v.token) });
export const useExtractText = () => useMutation({ mutationFn: (v: { file: File; token: string }) => api.extractText(v.file, v.token) });
export const useInvalidateLive = () => {
  const qc = useQueryClient();
  return () => invalidateLive(qc);
};
