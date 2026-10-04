import { useEffect, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Download, Search } from "lucide-react";
import { Page, PageHeader } from "@/components/layout/PageHeader";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useMeta, useRules } from "@/lib/api/hooks";
import { submissionUrl, type RuleFilters } from "@/lib/api/api";
import type { Category, EvidenceTier, RuleStatus, StateCode } from "@/lib/api/types";
import { CATEGORY_LABEL, STATUS_LABEL, TIER_LABEL } from "@/lib/labels";
import { useI18n } from "@/lib/i18n";
import { fmtDate, pct } from "@/lib/format";

export const Route = createFileRoute("/rules/")({
  head: () => ({
    meta: [
      { title: "Rules — Tenantly" },
      { name: "description", content: "Every housing rule Tenantly tracks in California, New Jersey and Massachusetts, with status, effective date and evidence." },
      { property: "og:title", content: "Rules — Tenantly" },
      { property: "og:description", content: "Every housing rule Tenantly tracks, with status, effective date and evidence." },
    ],
  }),
  component: RulesPage,
});

const ALL = "all";

function FilterSelect({ label, value, onChange, options }: { label: string; value: string; onChange: (v: string) => void; options: [string, string][] }) {
  const { tr } = useI18n();
  return (
    <label className="block">
      <span className="mb-1.5 block text-sm text-graphite">{label}</span>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-11 bg-sheet text-base"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>{tr("All", "Todos")}</SelectItem>
          {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
        </SelectContent>
      </Select>
    </label>
  );
}

function RulesPage() {
  const { tr, tb, lang } = useI18n();
  const meta = useMeta();
  const [state, setState] = useState(ALL);
  const [city, setCity] = useState(ALL);
  const [category, setCategory] = useState(ALL);
  const [status, setStatus] = useState(ALL);
  const [tier, setTier] = useState(ALL);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 250);
    return () => clearTimeout(t);
  }, [q]);

  const filters: RuleFilters = useMemo(() => {
    const f: RuleFilters = {};
    if (state !== ALL) f.state = state as StateCode;
    if (city !== ALL) f.jurisdiction_id = city;
    if (category !== ALL) f.category = category as Category;
    if (status !== ALL) f.status = status as RuleStatus;
    if (tier !== ALL) f.tier = tier as EvidenceTier;
    if (debouncedQ.trim()) f.q = debouncedQ.trim();
    return f;
  }, [state, city, category, status, tier, debouncedQ]);
  const rules = useRules(filters);
  const L = (p: [string, string]) => (lang === "es" ? p[1] : p[0]);

  const cities = (meta.data?.jurisdictions ?? []).filter((j) => j.level === "city" && (state === ALL || j.state === state));

  return (
    <Page>
      <PageHeader
        title={tr("Rules", "Reglas")}
        lede={tr("Every rule Tenantly can quote word for word, by place, topic and status. Open one to read what it requires and the text behind it.", "Cada regla que Tenantly puede citar palabra por palabra, por lugar, tema y estado.")}
      />

      <div className="grid gap-4 border-b border-hairline py-6 sm:grid-cols-2 lg:grid-cols-6">
        <label className="block sm:col-span-2 lg:col-span-6 xl:col-span-6">
          <span className="sr-only">{tr("Search rules", "Buscar reglas")}</span>
          <span className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-graphite" aria-hidden="true" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("Search by name, citation, state or city", "Buscar por nombre, cita, estado o ciudad")} className="h-11 w-full rounded-md border border-hairline bg-sheet pl-9 pr-3 text-base focus:border-permit focus:outline-none" />
          </span>
        </label>
        <FilterSelect label={tr("State", "Estado")} value={state} onChange={(v) => { setState(v); setCity(ALL); }} options={[["CA", "California"], ["NJ", "New Jersey"], ["MA", "Massachusetts"]]} />
        <FilterSelect label={tr("City", "Ciudad")} value={city} onChange={setCity} options={cities.map((c) => [c.id, c.name])} />
        <FilterSelect label={tr("Topic", "Tema")} value={category} onChange={setCategory} options={Object.entries(CATEGORY_LABEL).map(([k, v]) => [k, L(v)])} />
        <FilterSelect label={tr("Status", "Estado legal")} value={status} onChange={setStatus} options={Object.entries(STATUS_LABEL).map(([k, v]) => [k, L(v)])} />
        <FilterSelect label={tr("Evidence", "Evidencia")} value={tier} onChange={setTier} options={Object.entries(TIER_LABEL).map(([k, v]) => [k, L(v)])} />
        <div className="flex items-end text-sm text-graphite tabular">
          {rules.data ? tr(`${rules.data.length} rules`, `${rules.data.length} reglas`) : ""}
        </div>
      </div>

      <div className="-mx-5 overflow-x-auto md:mx-0">
        <table className="w-full min-w-[860px] text-left">
          <thead>
            <tr className="border-b-2 border-deed text-sm text-graphite">
              {[tr("Rule", "Regla"), tr("Jurisdiction", "Jurisdicción"), tr("Topic", "Tema"), tr("Status", "Estado"), tr("Effective", "Vigencia"), tr("Evidence", "Evidencia"), tr("Confidence", "Confianza")].map((h, i) => (
                <th key={h} className={`py-3 font-medium ${i === 0 ? "pl-5 md:pl-0" : ""} ${i === 6 ? "pr-5 text-right md:pr-0" : "pr-4"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rules.isLoading &&
              Array.from({ length: 6 }).map((_, i) => (
                <tr key={i} className="border-b border-hairline"><td colSpan={7} className="py-3"><Skeleton className="h-6" /></td></tr>
              ))}
            {rules.data?.map((r) => (
              <tr key={r.rule_id} className="border-b border-hairline align-top hover:bg-sheet">
                <td className="py-3 pl-5 pr-4 md:pl-0">
                  <Link to="/rules/$ruleId" params={{ ruleId: r.rule_id }} className="text-base font-medium text-deed underline-offset-4 hover:text-permit hover:underline">{r.title}</Link>
                  <span className="mt-0.5 block max-w-[48ch] text-sm text-graphite">{tb(r.summary)}</span>
                </td>
                <td className="py-3 pr-4 text-sm text-deed">{r.jurisdiction.label}</td>
                <td className="py-3 pr-4 text-sm text-deed">{L(CATEGORY_LABEL[r.category])}</td>
                <td className="py-3 pr-4 text-sm text-deed">{L(STATUS_LABEL[r.rule_status])}</td>
                <td className="whitespace-nowrap py-3 pr-4 text-sm text-deed tabular">{r.effective_date ? fmtDate(r.effective_date, lang, "short") : "—"}</td>
                <td className="py-3 pr-4 text-sm text-deed">{L(TIER_LABEL[r.citation.tier])}</td>
                <td className="py-3 pr-5 text-right text-sm text-deed tabular md:pr-0">{pct(r.confidence)}</td>
              </tr>
            ))}
            {rules.isError && (
              <tr>
                <td colSpan={7} className="py-10 text-center text-base text-graphite" role="alert">
                  {tr("We couldn't load the rules.", "No pudimos cargar las reglas.")}{" "}
                  <button type="button" onClick={() => rules.refetch()} className="text-permit underline-offset-4 hover:underline">{tr("Try again", "Intentar de nuevo")}</button>
                </td>
              </tr>
            )}
            {!rules.isError && rules.data?.length === 0 && (
              <tr><td colSpan={7} className="py-10 text-center text-base text-graphite">{tr("No rules match these filters.", "Ninguna regla coincide con estos filtros.")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <section className="mt-16 grid gap-6 border-t border-hairline pt-8 md:grid-cols-12">
        <div className="md:col-span-5">
          <h2 className="text-xl text-deed">{tr("Download submission files", "Descargar archivos de envío")}</h2>
          <p className="mt-1 text-base text-graphite">{tr("The same data as machine-readable files.", "Los mismos datos en archivos legibles por máquina.")}</p>
        </div>
        <ul className="flex flex-wrap gap-3 md:col-span-7 md:justify-end">
          {(["rules", "lookups", "changes"] as const).map((n) => (
            <li key={n}>
              <a href={submissionUrl(n)} className="inline-flex h-11 items-center gap-2 rounded-md border border-hairline bg-sheet px-4 text-base text-deed hover:border-deed">
                <Download className="size-4" />{n}.json
              </a>
            </li>
          ))}
        </ul>
      </section>
    </Page>
  );
}
