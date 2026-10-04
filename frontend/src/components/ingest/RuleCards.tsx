import { useState } from "react";
import { ResultPill } from "@/components/tenantly/ResultPill";
import { TierTag } from "@/components/tenantly/TierTag";
import { JsonViewer } from "@/components/ingest/JsonViewer";
import { Button } from "@/components/ui/button";
import type { Hierarchy, IngestResultData } from "@/lib/api/types";
import { coverageLeaves } from "@/lib/ingest";
import { useI18n } from "@/lib/i18n";
import { fmtDate } from "@/lib/format";

const CATEGORY: Record<string, [string, string]> = {
  rent_increase_limits: ["Rent increase limit", "Límite de aumento de renta"],
  just_cause_eviction: ["Just-cause eviction", "Desalojo con causa justa"],
  security_deposits: ["Security deposit", "Depósito de seguridad"],
  application_screening_fees: ["Application and screening fee", "Cuota de solicitud y evaluación"],
  screening_restrictions: ["Screening restriction", "Restricción de evaluación"],
  algorithmic_rent_setting: ["Algorithmic rent setting", "Fijación algorítmica de rentas"],
};

export function RuleCards({ res, onViewSource }: { res: IngestResultData; onViewSource: (ruleId: string) => void }) {
  const { tr, tb, lang } = useI18n();
  const [openJson, setOpenJson] = useState<string | null>(null);
  const hier: Hierarchy | null | undefined = res.hierarchy;
  const priorityOf = (jid: string) => hier?.levels.find((l) => l.id === jid)?.priority;
  return (
    <div className="space-y-5">
      {res.rules.map((r, i) => {
        const raw = res.rules_json?.find((x) => (x as { rule_id?: string }).rule_id === r.rule_id) as { coverage?: unknown; exemptions?: { description: string }[] } | undefined;
        const leaves = coverageLeaves(raw?.coverage);
        const conflicts = (hier?.relations ?? []).filter((x) => x.from === r.rule_id || x.to === r.rule_id);
        const prio = priorityOf(r.jurisdiction.id);
        return (
          <article key={r.rule_id} className="rounded-lg border border-hairline bg-sheet">
            <header className="flex flex-wrap items-center gap-2 border-b border-hairline px-5 py-3">
              <span className="text-sm font-semibold tabular text-graphite">{tr("RULE", "REGLA")} #{i + 1}</span>
              <span className="rounded bg-survey px-2 py-0.5 text-sm font-medium tabular text-deed">{r.rule_id}</span>
              <TierTag tier={r.citation.tier} />
              <ResultPill result={r.rule_status === "in_force" ? "applies" : r.rule_status === "pending" ? "pending" : "not_yet_effective"} />
              <span className="ml-auto text-sm text-graphite">{tr("Confidence", "Confianza")} {(r.confidence * 100).toFixed(0)}%</span>
            </header>
            <div className="grid gap-6 px-5 py-5 md:grid-cols-12">
              <div className="md:col-span-7">
                <p className="text-sm text-graphite">{tr(...(CATEGORY[r.category] ?? [r.category, r.category]))}</p>
                <h3 className="mt-1 text-lg text-deed">{r.title}</h3>
                <p className="mt-2 text-body text-deed">{tb(r.summary)}</p>
                {r.key_values.length > 0 && (
                  <ul className="mt-3 space-y-1 text-base text-deed">
                    {r.key_values.map((k) => (
                      <li key={k.name + k.text}><span className="text-graphite">{k.name.replace(/_/g, " ")}: </span><strong>{k.text}</strong></li>
                    ))}
                  </ul>
                )}
                <p className="mt-4 text-sm font-semibold text-deed">{tr("Applies when", "Aplica cuando")}</p>
                <ul className="mt-1 list-disc pl-5 text-base text-deed">
                  <li>{tb(r.who)}</li>
                  {leaves.map((l) => <li key={l}>{l}</li>)}
                </ul>
                {r.exemptions.length > 0 && (
                  <>
                    <p className="mt-4 text-sm font-semibold text-deed">{tr("Exemptions", "Exenciones")}</p>
                    <ul className="mt-1 list-disc pl-5 text-base text-deed">
                      {r.exemptions.map((e) => <li key={tb(e.description)}>{tb(e.description)}</li>)}
                    </ul>
                  </>
                )}
              </div>
              <dl className="space-y-3 text-base md:col-span-5">
                <div><dt className="text-sm text-graphite">{tr("Jurisdiction", "Jurisdicción")}</dt><dd className="text-deed">{r.jurisdiction.label}{prio ? ` · ${tr("priority", "prioridad")} ${prio}` : ""}</dd></div>
                <div><dt className="text-sm text-graphite">{tr("Effective", "Vigencia")}</dt><dd className="text-deed">{r.effective_date ? fmtDate(r.effective_date, lang) : tr("not stated in the text", "no indicada en el texto")}</dd></div>
                <div><dt className="text-sm text-graphite">{tr("Status", "Estado")}</dt><dd className="text-deed">{r.rule_status.replace(/_/g, " ")}</dd></div>
                <div><dt className="text-sm text-graphite">{tr("Source section", "Sección de origen")}</dt><dd className="text-deed">{r.citation.cite}</dd></div>
                <div>
                  <dt className="text-sm text-graphite">{tr("Conflicts and precedence", "Conflictos y precedencia")}</dt>
                  <dd className="text-deed">
                    {conflicts.length === 0 ? tr("None found", "Ninguno") : conflicts.map((c) => <span key={c.from + c.to} className="mb-1 block">{tb(c.explanation)}</span>)}
                  </dd>
                </div>
              </dl>
            </div>
            <blockquote className="law-quote mx-5 mb-4 border-l-2 border-hairline pl-4 text-deed">“<mark className="mark-highlight">{r.citation.quote}</mark>”</blockquote>
            <footer className="flex flex-wrap gap-2 border-t border-hairline px-5 py-3">
              <Button type="button" variant="outline" size="sm" onClick={() => onViewSource(r.rule_id)}>{tr("View source", "Ver fuente")}</Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setOpenJson(openJson === r.rule_id ? null : r.rule_id)}>{tr("View JSON", "Ver JSON")}</Button>
            </footer>
            {openJson === r.rule_id && (
              <div className="border-t border-hairline p-4">
                <JsonViewer title={tr("Canonical rule (engine format)", "Regla canónica (formato del motor)")} value={res.rules_json?.find((x) => (x as { rule_id?: string }).rule_id === r.rule_id) ?? r} defaultOpen maxHeight={320} />
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
