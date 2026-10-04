import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, ChevronDown, CircleCheck, CircleHelp, CircleX, Copy, FileSearch, BookOpen, Volume2 } from "lucide-react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { ResultPill, RESULT_META } from "./ResultPill";
import { TierTag } from "./TierTag";
import { useCopyCitation, useLawSheets } from "./LawSheets";
import type { Finding, ReasoningBoundary, RuleResult } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { fmtDate } from "@/lib/format";
import { cn } from "@/lib/utils";

export function NeedsReview() {
  const { tr } = useI18n();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="rounded-sm border border-hairline px-1.5 py-px text-xs text-graphite">
          {tr("Needs review", "Requiere revisión")}
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-sm">
        {tr("Our checks disagreed on a detail. Read the law before relying on this.", "Nuestras verificaciones no coincidieron en un detalle. Lea la ley antes de confiar en esto.")}
      </TooltipContent>
    </Tooltip>
  );
}

function CondIcon({ r }: { r: "true" | "false" | "unknown" }) {
  if (r === "true") return <CircleCheck className="mt-0.5 size-4 shrink-0 text-applies" aria-label="Met" />;
  if (r === "false") return <CircleX className="mt-0.5 size-4 shrink-0 text-graphite" aria-label="Not met" />;
  return <CircleHelp className="mt-0.5 size-4 shrink-0 text-unknown" aria-label="Unknown" />;
}

function basisWords(basis: string | null, tr: (a: string, b: string) => string) {
  if (!basis) return "";
  if (/MOD-IV/i.test(basis)) return ` (${tr("from", "de")} ${basis})`;
  return ` (${tr("public record", "registro público")})`;
}

interface Props {
  r: RuleResult;
  superseded?: RuleResult[];
  asOf: string;
  boundary?: ReasoningBoundary | null;
}

export function RuleRow({ r, superseded = [], asOf, boundary }: Props) {
  const { tr, tb, lang } = useI18n();
  const { openSource, openAudit } = useLawSheets();
  const copy = useCopyCitation();
  const tierC = r.citation.tier === "C";
  const audio = r.audio[lang];

  return (
    <article
      id={`rule-${r.rule_id}`}
      className={cn("ledger-rail border-b border-hairline bg-sheet py-6 pl-5 pr-4 md:pl-7 md:pr-6", RESULT_META[r.result].rail)}
    >
      <div className="flex flex-wrap items-center gap-2">
        <ResultPill result={r.result} />
        <TierTag tier={r.citation.tier} />
        {r.review_flag && <NeedsReview />}
      </div>
      <h3 className="mt-3 text-lg text-deed">{r.title}</h3>
      <p className="text-sm text-graphite">{r.jurisdiction.label}</p>
      <p className="mt-3 text-body text-deed prose-width">{tb(r.summary)}</p>

      {r.key_values.length > 0 && (
        <dl className="mt-4 grid max-w-[68ch] gap-x-6 gap-y-1 sm:grid-cols-[minmax(9rem,auto)_1fr]">
          {r.key_values.map((k, i) => (
            <div key={i} className="contents">
              <dt className="text-sm text-graphite">{k.name}</dt>
              <dd className="text-base text-deed tabular">
                {k.stale ? (
                  <span className="inline-flex items-start gap-1.5 text-unknown">
                    <CircleHelp className="mt-1 size-4 shrink-0" aria-hidden="true" />
                    {tb(k.stale_note)}
                  </span>
                ) : (
                  <>
                    {k.text}
                    {(k.valid_from || k.valid_to) && (
                      <span className="ml-2 text-sm text-graphite">
                        {k.valid_from ? fmtDate(k.valid_from, lang, "short") : "…"} – {k.valid_to ? fmtDate(k.valid_to, lang, "short") : "…"}
                      </span>
                    )}
                  </>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}

      <p className="mt-3 text-base text-graphite prose-width">{tb(r.reason)}</p>
      {r.effective_note && <p className="mt-1 text-sm text-graphite">{tb(r.effective_note)}</p>}

      {r.conflicts.map((c, i) => (
        <div key={i} className="mt-4 max-w-[68ch] rounded-md border border-unknown-border bg-unknown-bg px-4 py-3 text-unknown">
          <p className="flex items-start gap-2 text-base">
            <AlertTriangle className="mt-1 size-4 shrink-0" aria-hidden="true" />
            <span>
              {tb(c.explanation)}
              {c.active_from && ` ${tr("From", "Desde el")} ${fmtDate(c.active_from, lang)}.`}
            </span>
          </p>
          {c.with_rule_id && (
            <a href={`#rule-${c.with_rule_id}`} className="ml-6 mt-1 inline-block text-sm font-medium underline underline-offset-4">
              {tr("See the other rule", "Ver la otra regla")}
            </a>
          )}
        </div>
      ))}

      {r.open_question_ids.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {r.open_question_ids.map((id) => (
            <a key={id} href={`#oq-${id}`} className="rounded-sm border border-hairline px-2 py-0.5 text-sm text-permit hover:border-permit">
              {tr("Open question", "Pregunta abierta")}
            </a>
          ))}
        </div>
      )}

      {(r.conditions.length > 0 || r.caveats.length > 0) && (
        <Accordion type="single" collapsible className="mt-3 max-w-[68ch]">
          <AccordionItem value="why" className="border-b-0">
            <AccordionTrigger className="py-2 text-base font-medium text-permit hover:no-underline">
              {tr("Why this applies", "Por qué aplica")}
            </AccordionTrigger>
            <AccordionContent>
              <ul className="space-y-2">
                {r.conditions.map((c, i) => (
                  <li key={i} className="flex gap-2 text-base">
                    <CondIcon r={c.result} />
                    <span>
                      <span className="text-deed">{tb(c.label)}</span>
                      <span className="block text-sm text-graphite">
                        {c.actual
                          ? `${c.actual}${basisWords(c.basis, tr)}`
                          : c.fact === "year_built"
                            ? tr("Year built: not in public records", "Año de construcción: no está en registros públicos")
                            : tr("Not in public records", "No está en registros públicos")}
                        {`, ${tr("needs", "requiere")} ${c.expected}`}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
              {r.caveats.length > 0 && (
                <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-graphite">
                  {r.caveats.map((c, i) => <li key={i}>{tb(c)}</li>)}
                </ul>
              )}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      )}

      {superseded.map((s) => <SupersededLine key={s.rule_id} r={s} asOf={asOf} />)}

      <footer className="mt-5 border-t border-dashed border-hairline pt-4">
        <p className="text-sm text-deed">{r.citation.cite}</p>
        <p className="text-sm text-graphite">{tr("Retrieved", "Obtenido")} {fmtDate(r.citation.retrieved_at.slice(0, 10), lang, "short")}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => openSource({ citation: r.citation, ruleId: r.rule_id, extra: r.extra_citations })}>
            {tierC ? <FileSearch /> : <BookOpen />}
            {tierC ? tr("Why there's no quote", "Por qué no hay cita") : tr("Read the law", "Leer la ley")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => copy(r.citation)}>
            <Copy />
            {tr("Copy citation", "Copiar cita")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => openAudit({ ruleId: r.rule_id, title: r.title, citations: [r.citation, ...r.extra_citations], asOf, boundary })}
          >
            {tr("Audit", "Auditoría")}
          </Button>
          {audio && (
            <Button size="sm" variant="ghost" onClick={() => new Audio(audio).play()}>
              <Volume2 />
              {tr("Listen", "Escuchar")}
            </Button>
          )}
        </div>
      </footer>
    </article>
  );
}

function SupersededLine({ r }: { r: RuleResult; asOf: string }) {
  const { tr, tb } = useI18n();
  const { openSource } = useLawSheets();
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-4 max-w-[68ch] border-l-2 border-superseded-border pl-4">
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex w-full items-start gap-2 text-left text-base text-superseded">
        <ChevronDown className={cn("mt-1 size-4 shrink-0 transition-transform", open && "rotate-180")} aria-hidden="true" />
        <span>
          {tr("Also checked", "También revisada")}: <span className="font-medium">{r.title}</span>. {tr("Overridden here", "Reemplazada aquí")}: {tb(r.reason)}
        </span>
      </button>
      {open && (
        <div className="mt-2 pl-6">
          <p className="text-base text-graphite">{tb(r.summary)}</p>
          <button type="button" className="mt-1 text-sm text-permit underline-offset-4 hover:underline" onClick={() => openSource({ citation: r.citation, ruleId: r.rule_id })}>
            {tr("Read the law", "Leer la ley")}
          </button>
        </div>
      )}
    </div>
  );
}

export function FindingRow({ f }: { f: Finding }) {
  const { tr, tb } = useI18n();
  const { openSource } = useLawSheets();
  const ev = f.evidence[0];
  return (
    <div className="ledger-rail border-b border-dashed border-hairline border-l-superseded-border py-5 pl-5 pr-4 md:pl-7">
      <ResultPill result="none" />
      <p className="mt-2 text-body text-deed prose-width">{tb(f.explanation)}</p>
      <p className="text-sm text-graphite">{f.jurisdiction.label}{ev ? `, ${ev.cite}` : ""}</p>
      {ev && (
        <Button size="sm" variant="outline" className="mt-3" onClick={() => openSource({ citation: ev, ruleId: null, extra: f.evidence.slice(1) })}>
          <BookOpen />
          {tr("Read the law", "Leer la ley")}
        </Button>
      )}
    </div>
  );
}

export function RuleLink({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <Link to="/rules/$ruleId" params={{ ruleId: id }} className="text-permit underline-offset-4 hover:underline">
      {children}
    </Link>
  );
}
