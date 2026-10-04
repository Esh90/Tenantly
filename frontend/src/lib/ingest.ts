import type { IngestStage, IngestState } from "@/lib/api/types";

export const STAGE_GROUPS: { title: [string, string]; stages: IngestStage[] }[] = [
  { title: ["Understand the document", "Entender el documento"], stages: ["received", "parse", "sectionize", "triage"] },
  { title: ["Extract the law with AI", "Extraer la ley con IA"], stages: ["extract", "verify", "crosscheck"] },
  { title: ["Place it in the legal system", "Ubicarla en el sistema legal"], stages: ["jurisdiction", "calendar", "link", "explain", "priority", "graph"] },
  { title: ["Verify before it goes live", "Verificar antes de publicar"], stages: ["validate", "judge", "impact", "staged"] },
];

export const STAGE_LABEL: Record<string, [string, string]> = {
  received: ["Document received", "Documento recibido"],
  parse: ["Document parsed", "Documento analizado"],
  sectionize: ["Sections identified", "Secciones identificadas"],
  triage: ["Relevant provisions found", "Disposiciones relevantes halladas"],
  extract: ["Legal provisions extracted (two independent passes)", "Disposiciones extraídas (dos pasadas independientes)"],
  verify: ["Every quote checked against the text", "Cada cita verificada contra el texto"],
  crosscheck: ["Rules cross-checked and normalized", "Reglas comparadas y normalizadas"],
  jurisdiction: ["Jurisdiction identified", "Jurisdicción identificada"],
  calendar: ["Effective dates computed", "Fechas de vigencia calculadas"],
  link: ["Relationships to other laws found", "Relaciones con otras leyes halladas"],
  explain: ["Plain-language summaries written", "Resúmenes en lenguaje claro redactados"],
  priority: ["Priority relationships evaluated", "Relaciones de prioridad evaluadas"],
  graph: ["Knowledge graph built", "Grafo de conocimiento construido"],
  validate: ["Deterministic validation", "Validación determinista"],
  judge: ["Autonomous Judge", "Juez autónomo"],
  impact: ["Affected buildings found", "Edificios afectados hallados"],
  staged: ["Held in staging, apart from live law", "En preparación, separado de la ley vigente"],
};

export const STATE_META: Record<IngestState, { en: string; es: string; tone: string }> = {
  staged: { en: "STAGED", es: "EN PREPARACIÓN", tone: "text-pending bg-pending-bg border-pending-border" },
  verified: { en: "VERIFIED", es: "VERIFICADA", tone: "text-applies bg-applies-bg border-applies-border" },
  review_required: { en: "REVIEW REQUIRED", es: "REVISIÓN REQUERIDA", tone: "text-unknown bg-unknown-bg border-unknown-border" },
  published: { en: "PUBLISHED", es: "PUBLICADA", tone: "text-applies bg-applies-bg border-applies-border" },
  rejected: { en: "REJECTED", es: "RECHAZADA", tone: "text-superseded bg-superseded-bg border-superseded-border" },
};

/** Find a quoted span in the pasted text even if the extractor's quote differs in whitespace. */
export function locateQuote(text: string, quote: string): [number, number] | null {
  if (!quote) return null;
  const direct = text.indexOf(quote);
  if (direct >= 0) return [direct, direct + quote.length];
  const pattern = quote
    .trim()
    .split(/\s+/)
    .map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("\\s+");
  const m = new RegExp(pattern).exec(text);
  return m ? [m.index, m.index + m[0].length] : null;
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString();
}

type Pred = { fact?: string; op?: string; value?: unknown; all?: unknown[]; any?: unknown[]; not?: unknown };

/** The condition leaves of a coverage predicate, in plain words. */
export function coverageLeaves(pred: unknown): string[] {
  const out: string[] = [];
  const walk = (p: unknown) => {
    if (!p || typeof p !== "object") return;
    const o = p as Pred;
    if (typeof o.fact === "string") {
      const v = o.value && typeof o.value === "object" ? `${(o.value as { as_of_minus_years?: number }).as_of_minus_years} years before the date` : String(o.value);
      out.push(`${o.fact.replace(/_/g, " ")} ${o.op ?? ""} ${v}`);
    }
    o.all?.forEach(walk);
    o.any?.forEach(walk);
    if (o.not) walk(o.not);
  };
  walk(pred);
  return out;
}
