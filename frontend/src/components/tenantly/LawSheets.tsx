import type React from "react";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Copy, ExternalLink, ShieldAlert, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { TierTag } from "./TierTag";
import { useAudit, useRule, useSource } from "@/lib/api/hooks";
import type { Citation, ReasoningBoundary } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { copyText, fmtDate } from "@/lib/format";
import { DEFAULT_AS_OF } from "@/config";

export interface SourceTarget {
  citation: Citation;
  ruleId: string | null;
  extra?: Citation[];
}
export interface AuditTarget {
  ruleId: string;
  title: string;
  citations: Citation[];
  asOf?: string | undefined;
  boundary?: ReasoningBoundary | null | undefined;
}

interface Ctx {
  openSource: (t: SourceTarget) => void;
  openAudit: (t: AuditTarget) => void;
}
// Keep one context object across hot reloads so the provider and consumers always match.
const g = globalThis as { __tenantlyLawCtx?: React.Context<Ctx | null> };
const LawCtx = (g.__tenantlyLawCtx ??= createContext<Ctx | null>(null));

export function useLawSheets() {
  const v = useContext(LawCtx);
  if (!v) throw new Error("useLawSheets must be inside LawSheetsProvider");
  return v;
}

export function citationText(c: Citation, lang: "en" | "es" = "en") {
  return `${c.cite}, ${lang === "es" ? "obtenido" : "retrieved"} ${fmtDate(c.retrieved_at.slice(0, 10), lang)}, ${c.url}`;
}

export function useCopyCitation() {
  const { lang, tr } = useI18n();
  return async (c: Citation) => {
    const ok = await copyText(citationText(c, lang));
    if (ok) toast.success(tr("Citation copied", "Cita copiada"));
    else toast.error(tr("Copy didn't work in this browser", "No se pudo copiar en este navegador"));
  };
}

const sheetCls = "w-full max-w-none overflow-y-auto bg-sheet p-0 sm:max-w-[640px]";

export function LawSheetsProvider({ children }: { children: ReactNode }) {
  const [source, setSource] = useState<SourceTarget | null>(null);
  const [audit, setAudit] = useState<AuditTarget | null>(null);
  return (
    <LawCtx.Provider value={{ openSource: setSource, openAudit: setAudit }}>
      {children}
      <Sheet open={!!source} onOpenChange={(o) => !o && setSource(null)}>
        <SheetContent side="right" className={sheetCls}>
          {source && <SourceBody target={source} />}
        </SheetContent>
      </Sheet>
      <Sheet open={!!audit} onOpenChange={(o) => !o && setAudit(null)}>
        <SheetContent side="right" className={sheetCls}>
          {audit && <AuditBody target={audit} />}
        </SheetContent>
      </Sheet>
    </LawCtx.Provider>
  );
}

function Meta({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-graphite">{k}</dt>
      <dd className="text-deed">{children}</dd>
    </div>
  );
}

function SourceBody({ target }: { target: SourceTarget }) {
  const { tr, lang } = useI18n();
  const copy = useCopyCitation();
  const c = target.citation;
  const supplementary = c.tier === "C" || c.quote_source === "supplementary";
  const q = useSource(supplementary ? "" : c.doc_id, target.ruleId ?? undefined);
  const firstMark = useRef<HTMLElement>(null);
  const [copiedSha, setCopiedSha] = useState(false);

  useEffect(() => {
    firstMark.current?.scrollIntoView({ block: "center" });
  }, [q.data]);

  const doc = q.data;
  const shortSha = (doc?.doc_sha256 ?? c.doc_sha256 ?? "").slice(0, 12);

  return (
    <div className="flex min-h-full flex-col">
      <SheetHeader className="space-y-1 border-b border-hairline px-6 py-5 text-left">
        <SheetDescription className="text-sm text-graphite">
          {supplementary ? tr("Why there's no quote", "Por qué no hay cita") : tr("Official source", "Fuente oficial")}
        </SheetDescription>
        <SheetTitle className="pr-8 text-xl text-deed">{doc?.title ?? c.cite}</SheetTitle>
      </SheetHeader>

      <dl className="border-b border-hairline px-6 py-4">
        <Meta k={tr("Citation", "Cita")}>{c.cite}</Meta>
        {doc && <Meta k={tr("Jurisdiction", "Jurisdicción")}>{doc.jurisdiction_label}</Meta>}
        <Meta k={tr("Retrieved", "Obtenido")}>{fmtDate(c.retrieved_at.slice(0, 10), lang)}</Meta>
        {doc && <Meta k={tr("Document type", "Tipo")}>{doc.doc_type}</Meta>}
        <Meta k={tr("Evidence", "Evidencia")}><TierTag tier={c.tier} /></Meta>
        {shortSha && (
          <Meta k={tr("Fingerprint", "Huella")}>
            <span className="inline-flex flex-wrap items-center gap-2">
              <code className="text-sm tabular">{shortSha}</code>
              <button
                type="button"
                className="inline-flex items-center gap-1 text-sm text-permit hover:underline"
                onClick={async () => {
                  await copyText(doc?.doc_sha256 ?? c.doc_sha256 ?? "");
                  setCopiedSha(true);
                }}
              >
                {copiedSha ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                {copiedSha ? tr("Copied", "Copiado") : tr("Copy", "Copiar")}
              </button>
              {doc?.sha_ok === true ? (
                <span className="inline-flex items-center gap-1 text-applies"><ShieldCheck className="size-4" />{tr("Hash verified", "Huella verificada")}</span>
              ) : (
                <span className="inline-flex items-center gap-1 text-graphite"><ShieldAlert className="size-4" />{tr("Hash not verified", "Huella no verificada")}</span>
              )}
            </span>
          </Meta>
        )}
      </dl>

      {doc?.low_signal && (
        <p className="mx-6 mt-4 rounded-md border border-unknown-border bg-unknown-bg px-3 py-2 text-sm text-unknown">
          {tr("Partial capture: the saved page is mostly site navigation.", "Captura parcial: la página guardada es mayormente navegación del sitio.")}
        </p>
      )}

      {doc && doc.versions.length > 1 && (
        <div className="mx-6 mt-4">
          <h3 className="text-sm font-semibold text-graphite">{tr("Versions", "Versiones")}</h3>
          <ul className="mt-2 divide-y divide-hairline border-y border-hairline text-sm">
            {doc.versions.map((v) => (
              <li key={v.label} className="flex justify-between py-2">
                <span>{v.label}</span>
                <span className="text-graphite tabular">
                  {v.in_force_on_default ? tr("In force on Oct 1, 2026", "Vigente el 1 de oct. de 2026") : `${v.valid_from ?? "…"} – ${v.valid_to ?? "…"}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex-1 px-6 py-6">
        {supplementary ? (
          <div>
            <p className="text-body text-deed">
              {tr("The law's text was not supplied. These materials say it exists:", "El texto de la ley no fue proporcionado. Estos materiales indican que existe:")}
            </p>
            <ul className="mt-4 space-y-4">
              {[c, ...(target.extra ?? [])].map((s, i) => (
                <li key={`${s.doc_id}-${i}`} className="border-l-2 border-hairline pl-4">
                  <p className="text-sm font-medium text-deed">{s.supplementary_doc ?? s.cite}</p>
                  <p className="mt-1 text-base text-graphite">"{s.quote}"</p>
                </li>
              ))}
            </ul>
          </div>
        ) : q.isLoading ? (
          <div className="space-y-3"><Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-11/12" /><Skeleton className="h-4 w-4/5" /></div>
        ) : q.isError || !doc ? (
          <div>
            <p className="text-sm text-graphite">{tr("The full document didn't load. The quoted passage:", "El documento completo no cargó. El pasaje citado:")}</p>
            <blockquote className="law-quote mt-3 text-deed"><mark className="mark-highlight">{c.quote}</mark></blockquote>
          </div>
        ) : (
          <article className="law-quote text-deed">
            {doc.window.start > 0 && <p className="mb-3 font-sans text-sm text-graphite">{tr("Earlier text omitted", "Texto anterior omitido")}</p>}
            <p className="whitespace-pre-wrap">
              {renderHighlights(doc.window.text, doc.window.highlights.map((h) => ({ start: h.start - doc.window.start, end: h.end - doc.window.start })), firstMark)}
            </p>
            {doc.window.end < doc.total_chars && <p className="mt-3 font-sans text-sm text-graphite">{tr("Later text omitted", "Texto posterior omitido")}</p>}
          </article>
        )}
      </div>

      <div className="sticky bottom-0 flex flex-wrap gap-2 border-t border-hairline bg-sheet px-6 py-4">
        <Button asChild>
          <a href={c.url} target="_blank" rel="noreferrer">
            <ExternalLink />
            {tr("Open official source", "Abrir fuente oficial")}
          </a>
        </Button>
        <Button variant="outline" onClick={() => copy(c)}>
          <Copy />
          {tr("Copy citation", "Copiar cita")}
        </Button>
      </div>
    </div>
  );
}

function renderHighlights(text: string, hs: { start: number; end: number }[], firstRef: React.RefObject<HTMLElement | null>) {
  const sorted = [...hs].sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let pos = 0;
  sorted.forEach((h, i) => {
    if (h.start > pos) out.push(text.slice(pos, h.start));
    out.push(
      <mark key={i} ref={i === 0 ? (firstRef as React.RefObject<HTMLElement>) : undefined} className="mark-highlight">
        {text.slice(h.start, h.end)}
      </mark>,
    );
    pos = h.end;
  });
  out.push(text.slice(pos));
  return out;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border-b border-hairline px-6 py-5">
      <h3 className="text-base font-semibold text-deed">{title}</h3>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function AuditBody({ target }: { target: AuditTarget }) {
  const { tr, tb, lang } = useI18n();
  const rule = useRule(target.ruleId);
  const audit = useAudit(target.ruleId);
  const p = rule.data?.provenance;

  return (
    <div>
      <SheetHeader className="space-y-1 border-b border-hairline px-6 py-5 text-left">
        <SheetDescription className="text-sm text-graphite">{tr("Audit", "Auditoría")}</SheetDescription>
        <SheetTitle className="pr-8 text-xl text-deed">{target.title}</SheetTitle>
      </SheetHeader>

      <Section title={tr("Sources", "Fuentes")}>
        <ul className="space-y-2">
          {target.citations.map((c, i) => (
            <li key={`${c.doc_id}-${i}`} className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-deed">{c.cite}</span>
              <TierTag tier={c.tier} />
            </li>
          ))}
        </ul>
      </Section>

      <Section title={tr("Dates", "Fechas")}>
        <dl>
          <Meta k={tr("As of", "A la fecha")}>{fmtDate(target.asOf ?? DEFAULT_AS_OF, lang)}</Meta>
          <Meta k={tr("Sources retrieved", "Fuentes obtenidas")}>{fmtDate("2026-10-01", lang)}</Meta>
        </dl>
      </Section>

      <Section title={tr("How it was extracted", "Cómo se extrajo")}>
        {rule.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : !p ? (
          <p className="text-sm text-graphite">{tr("Extraction details are not available for this item.", "No hay detalles de extracción para este elemento.")}</p>
        ) : (
          <dl>
            <Meta k={tr("Readers", "Lectores")}>{p.models.join(", ")}</Meta>
            <Meta k={tr("Instructions", "Instrucciones")}>{Object.entries(p.prompt_versions).map(([k, v]) => `${k} ${v}`).join(", ")}</Meta>
            <Meta k={tr("Votes", "Votos")}>{Object.entries(p.votes).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", ")}</Meta>
            <Meta k={tr("Settled by review", "Resuelto en revisión")}>{p.adjudicated_fields.length ? p.adjudicated_fields.join(", ") : tr("None", "Ninguno")}</Meta>
          </dl>
        )}
      </Section>

      <Section title={tr("Checks passed", "Verificaciones aprobadas")}>
        <ul className="space-y-1.5 text-sm text-deed">
          <li className="flex gap-2"><Check className="mt-0.5 size-4 text-applies" />{tr("Quote found word for word in the source", "Cita encontrada palabra por palabra en la fuente")}</li>
          <li className="flex gap-2"><Check className="mt-0.5 size-4 text-applies" />{tr("Rule matches the expected structure", "La regla cumple la estructura esperada")}</li>
          <li className="flex gap-2"><Check className="mt-0.5 size-4 text-applies" />{tr("Effective date computed from the text's enactment clause", "Fecha de vigencia calculada a partir de la cláusula de promulgación")}</li>
        </ul>
      </Section>

      {target.boundary && (
        <Section title={tr("What we checked", "Lo que revisamos")}>
          <ul className="list-disc space-y-1 pl-5 text-sm text-deed">
            {target.boundary.checked.map((b, i) => <li key={i}>{tb(b)}</li>)}
          </ul>
        </Section>
      )}

      <Section title={tr("Audit log", "Registro")}>
        {audit.data?.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{tr("When", "Cuándo")}</TableHead>
                <TableHead>{tr("Action", "Acción")}</TableHead>
                <TableHead>{tr("Detail", "Detalle")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {audit.data.map((a) => (
                <TableRow key={a.audit_id}>
                  <TableCell className="whitespace-nowrap text-sm tabular">{a.at.slice(0, 16).replace("T", " ")}</TableCell>
                  <TableCell className="text-sm">{a.action.replace(/_/g, " ")}</TableCell>
                  <TableCell className="text-sm text-graphite">{a.detail}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-sm text-graphite">{audit.isLoading ? "…" : tr("No entries.", "Sin registros.")}</p>
        )}
      </Section>
    </div>
  );
}
