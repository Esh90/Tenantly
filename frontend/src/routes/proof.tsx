import type { ReactNode } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { CircleCheck, CircleX, FlaskConical } from "lucide-react";
import { Page, PageHeader } from "@/components/layout/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { useProof } from "@/lib/api/hooks";
import { IS_MOCK } from "@/config";
import { useI18n } from "@/lib/i18n";
import { fmtDate, pct } from "@/lib/format";

export const Route = createFileRoute("/proof")({
  head: () => ({
    meta: [
      { title: "How we know it's right — Tenantly" },
      { name: "description", content: "How Tenantly checks every quote, effective date, boundary and building record behind its answers." },
      { property: "og:title", content: "How we know it's right — Tenantly" },
      { property: "og:description", content: "How Tenantly checks every quote, date and boundary behind its answers." },
    ],
  }),
  component: ProofPage,
});

function Sec({ id, title, sentence, children }: { id: string; title: string; sentence: string; children: ReactNode }) {
  return (
    <section id={id} className="grid scroll-mt-24 gap-4 border-t border-hairline py-10 lg:grid-cols-12 lg:gap-10">
      <div className="lg:col-span-4">
        <h2 className="text-xl text-deed">{title}</h2>
        <p className="mt-2 text-base text-graphite">{sentence}</p>
      </div>
      <div className="min-w-0 lg:col-span-8">{children}</div>
    </section>
  );
}

function Stats({ items }: { items: [string, string | number][] }) {
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-hairline bg-hairline sm:grid-cols-3">
      {items.map(([k, v]) => (
        <div key={k} className="bg-sheet px-4 py-3">
          <dt className="text-sm text-graphite">{k}</dt>
          <dd className="mt-0.5 text-xl font-semibold text-deed tabular">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Architecture() {
  const { tr } = useI18n();
  const boxes = [tr("Law text", "Texto legal"), tr("Verified rules", "Reglas verificadas"), tr("Your building + date", "Su edificio + fecha"), tr("Answer", "Respuesta")];
  return (
    <svg viewBox="0 0 760 170" className="h-auto w-full text-deed" role="img" aria-label={tr("Law text becomes verified rules, which are checked against your building and date to give an answer. Law Watch feeds new law text back in.", "El texto legal se convierte en reglas verificadas, que se comparan con su edificio y fecha para dar una respuesta. Law Watch alimenta texto nuevo.")}>
      {boxes.map((b, i) => (
        <g key={b} transform={`translate(${i * 190},40)`}>
          <rect width="160" height="56" rx="4" fill="var(--sheet)" stroke="currentColor" strokeWidth={i === 3 ? 2 : 1} />
          <text x="80" y="33" textAnchor="middle" fontSize="15" fill="currentColor" fontFamily="var(--font-sans)">{b}</text>
          {i < 3 && <path d="M163 28h24m-6-5 6 5-6 5" fill="none" stroke="currentColor" strokeWidth="1.4" />}
        </g>
      ))}
      <path d="M570 96v40H80v-36" fill="none" stroke="var(--graphite)" strokeDasharray="4 4" strokeWidth="1.2" />
      <path d="M75 106l5-6 5 6" fill="none" stroke="var(--graphite)" strokeWidth="1.2" />
      <text x="325" y="156" textAnchor="middle" fontSize="13" fill="var(--graphite)" fontFamily="var(--font-sans)">Law Watch</text>
    </svg>
  );
}

function ProofPage() {
  const { tr, tb, lang } = useI18n();
  const q = useProof();
  const p = q.data;

  return (
    <Page>
      <PageHeader
        title={tr("How we know it's right", "Cómo sabemos que es correcto")}
        lede={tr("Every answer rests on checks you can inspect: quotes matched to the law, dates computed from the text, and buildings placed by map boundaries.", "Cada respuesta se basa en verificaciones que puede revisar: citas comparadas con la ley, fechas calculadas del texto y edificios ubicados por límites del mapa.")}
      />
      {IS_MOCK && (
        <p className="mt-6 flex items-center gap-2 rounded-md border border-unknown-border bg-unknown-bg px-4 py-2.5 text-base text-unknown">
          <FlaskConical className="size-4" />
          {tr("Sample numbers. Connect the API to see measured results.", "Números de muestra. Conecte la API para ver resultados medidos.")}
        </p>
      )}

      <div className="mt-8"><Architecture /></div>

      {q.isLoading || !p ? (
        <div className="mt-10 space-y-4"><Skeleton className="h-32" /><Skeleton className="h-32" /></div>
      ) : (
        <div className="mt-6">
          {p.selfscore && (
            <Sec id="score" title={tr("Scores on our practice key", "Puntajes en nuestra clave de práctica")} sentence={tr("The starter pack has no official scorer; this mirrors the published rubric using our own reading of the corpus.", "El paquete inicial no tiene evaluador oficial; esto replica la rúbrica publicada con nuestra propia lectura.")}>
              <table className="w-full text-left">
                <thead><tr className="border-b-2 border-deed text-sm text-graphite"><th className="py-2 font-medium">{tr("Component", "Componente")}</th><th className="py-2 text-right font-medium">{tr("Score", "Puntaje")}</th><th className="hidden py-2 pl-6 font-medium sm:table-cell">{tr("Note", "Nota")}</th></tr></thead>
                <tbody>
                  {p.selfscore.components.map((c) => (
                    <tr key={c.name} className="border-b border-hairline"><td className="py-2.5 text-base">{c.name}</td><td className="py-2.5 text-right tabular">{c.score} / {c.max}</td><td className="hidden py-2.5 pl-6 text-sm text-graphite sm:table-cell">{c.note}</td></tr>
                  ))}
                </tbody>
              </table>
              <Accordion type="single" collapsible className="mt-2">
                <AccordionItem value="raw" className="border-b-0">
                  <AccordionTrigger className="text-base text-permit hover:no-underline">{tr("Raw report", "Informe completo")}</AccordionTrigger>
                  <AccordionContent><pre className="whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">{p.selfscore.raw_report}</pre></AccordionContent>
                </AccordionItem>
              </Accordion>
            </Sec>
          )}

          <Sec id="tests" title={tr("Change tests", "Pruebas de cambios")} sentence={tr("Five defined changes, each with the number of buildings it should touch.", "Cinco cambios definidos, cada uno con el número de edificios que debería afectar.")}>
            <table className="w-full text-left">
              <thead><tr className="border-b-2 border-deed text-sm text-graphite"><th className="py-2 font-medium">{tr("Test", "Prueba")}</th><th className="py-2 text-right font-medium">{tr("Expected", "Esperado")}</th><th className="py-2 text-right font-medium">{tr("Ours", "Nuestro")}</th><th className="py-2 text-right font-medium">{tr("Conflicts", "Conflictos")}</th><th className="py-2 pl-4 font-medium">{tr("Result", "Resultado")}</th></tr></thead>
              <tbody>
                {p.change_checks.map((c) => (
                  <tr key={c.test_id} className="border-b border-hairline tabular">
                    <td className="py-2.5">{c.test_id}</td><td className="py-2.5 text-right">{c.expected}</td><td className="py-2.5 text-right">{c.affected}</td><td className="py-2.5 text-right">{c.conflicts} / {c.expected_conflicts}</td>
                    <td className="py-2.5 pl-4">{c.passed ? <span className="inline-flex items-center gap-1 text-applies"><CircleCheck className="size-4" />{tr("Pass", "Aprobada")}</span> : <span className="inline-flex items-center gap-1 text-destructive"><CircleX className="size-4" />{tr("Fail", "Fallida")}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Sec>

          <Sec id="quotes" title={tr("Every quote is checked", "Cada cita se verifica")} sentence={tr("A rule survives only if its quote appears character for character in the saved law.", "Una regla solo sobrevive si su cita aparece carácter por carácter en la ley guardada.")}>
            <Stats items={[
              [tr("Rules", "Reglas"), p.verification.rules],
              [tr("Official text", "Texto oficial"), p.verification.tier_counts.A],
              [tr("Official guidance", "Guía oficial"), p.verification.tier_counts.B],
              [tr("Text not supplied", "Texto no proporcionado"), p.verification.tier_counts.C],
              [tr("Quotes verified", "Citas verificadas"), p.verification.quotes_verified],
              [tr("Settled by review", "Resueltos en revisión"), p.verification.adjudicated_fields],
            ]} />
            <p className="mt-4 text-base text-deed"><span className="font-semibold tabular">{p.verification.rejected_candidates}</span> {tr("rules we threw away because their quote wasn't in the law.", "reglas descartadas porque su cita no estaba en la ley.")}</p>
          </Sec>

          <Sec id="records" title={tr("Messy public records", "Registros públicos desordenados")} sentence={tr("Assessor data has gaps and errors; we count them instead of hiding them.", "Los datos del tasador tienen vacíos y errores; los contamos en vez de ocultarlos.")}>
            <Stats items={[
              [tr("Unit counts derived", "Unidades derivadas"), p.facts.derived_units],
              [tr("Records that disagree", "Registros en desacuerdo"), p.facts.record_conflicts],
              [tr("Suspect ZIPs", "Códigos postales dudosos"), p.facts.zip_suspect],
              [tr("Missing year built", "Sin año de construcción"), p.facts.missing_year_built],
              [tr("Mailing-city mismatches", "Ciudad postal distinta"), p.geo.mailing_mismatches],
              [tr("Unmatched addresses", "Direcciones sin ubicar"), p.geo.unmatched],
            ]} />
          </Sec>

          <Sec id="plain" title={tr("Plain language", "Lenguaje claro")} sentence={tr("Summaries are written to be read at a middle-school level, in English and Spanish.", "Los resúmenes se escriben para leerse a nivel de secundaria, en inglés y español.")}>
            <Stats items={[[tr("Mean grade level", "Nivel promedio"), p.plain_language.mean_grade_en], [tr("Highest grade level", "Nivel máximo"), p.plain_language.max_grade_en], [tr("Spanish coverage", "Cobertura en español"), pct(p.plain_language.es_coverage)]]} />
          </Sec>

          {p.latency && (
            <Sec id="speed" title={tr("Speed", "Velocidad")} sentence={tr(`Measured ${fmtDate(p.latency.measured_at.slice(0, 10), lang)} against the live API.`, `Medido el ${fmtDate(p.latency.measured_at.slice(0, 10), lang)} contra la API en vivo.`)}>
              {(() => {
                const base = p.latency.llm_baseline_ms ?? 4200;
                const max = Math.max(base, p.latency.lookup_p95_ms);
                const bars: [string, number, string][] = [
                  [tr("Tenantly lookup, typical (p50)", "Consulta Tenantly, típica (p50)"), p.latency.lookup_p50_ms, "bg-deed"],
                  [tr("Tenantly lookup, slow (p95)", "Consulta Tenantly, lenta (p95)"), p.latency.lookup_p95_ms, "bg-deed/70"],
                  [p.latency.llm_baseline_ms ? tr("Asking a chatbot per question", "Preguntar a un chatbot") : tr("Asking a chatbot per question (estimate)", "Preguntar a un chatbot (estimado)"), base, "bg-graphite/40"],
                ];
                return (
                  <ul className="space-y-4">
                    {bars.map(([l, v, c]) => (
                      <li key={l}>
                        <div className="flex justify-between text-sm"><span className="text-deed">{l}</span><span className="text-graphite tabular">{v.toLocaleString()} ms</span></div>
                        <div className="mt-1.5 h-3 rounded-sm bg-muted"><div className={`h-3 rounded-sm ${c}`} style={{ width: `${Math.max(1.5, (v / max) * 100)}%` }} /></div>
                      </li>
                    ))}
                  </ul>
                );
              })()}
            </Sec>
          )}

          <Sec id="cost" title={tr("Cost", "Costo")} sentence={tr("What it cost to read every law once.", "Lo que costó leer cada ley una vez.")}>
            <p className="text-3xl font-semibold text-deed tabular">${p.cost.total_usd.toFixed(2)}</p>
            <ul className="mt-3 divide-y divide-hairline border-y border-hairline text-sm">
              {Object.entries(p.cost.by_stage).map(([k, v]) => <li key={k} className="flex justify-between py-2"><span>{k}</span><span className="tabular">${v.toFixed(2)}</span></li>)}
            </ul>
          </Sec>

          <Sec id="oq" title={tr("Open questions we found", "Preguntas abiertas que encontramos")} sentence={tr("Places where the sources leave the answer unsettled.", "Lugares donde las fuentes dejan la respuesta sin resolver.")}>
            <ul className="space-y-4">{p.open_questions.map((o) => <li key={o.oq_id} className="border-l-2 border-hairline pl-4"><p className="text-base font-semibold text-deed">{tb(o.title)}</p><p className="text-base text-graphite">{tb(o.detail)}</p></li>)}</ul>
          </Sec>

          <Sec id="scope" title={tr("What we cover, and what we don't", "Qué cubrimos y qué no")} sentence={tr("Three states, ten cities, six topics. The limits matter as much.", "Tres estados, diez ciudades, seis temas. Los límites importan igual.")}>
            <div className="grid gap-8 sm:grid-cols-2">
              <div>
                <h3 className="text-base font-semibold text-deed">{tr("What we cover", "Qué cubrimos")}</h3>
                <ul className="mt-2 space-y-1.5 text-base text-deed">
                  <li>California, New Jersey, Massachusetts</li>
                  <li>{tr("Ten cities and their counties", "Diez ciudades y sus condados")}</li>
                  <li>{tr("Six rental topics, any date from 2025 to 2028", "Seis temas, cualquier fecha de 2025 a 2028")}</li>
                </ul>
              </div>
              <div>
                <h3 className="text-base font-semibold text-deed">{tr("What we don't", "Qué no")}</h3>
                <ul className="mt-2 space-y-1.5 text-base text-deed">{p.limitations.map((l, i) => <li key={i}>{tb(l)}</li>)}</ul>
              </div>
            </div>
          </Sec>
        </div>
      )}
    </Page>
  );
}
