import { useEffect, useMemo, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { CalendarDays, ChevronDown, Info, MapPin } from "lucide-react";
import { DEFAULT_AS_OF } from "@/config";
import { useCustomLookup, useJurisdictionGeo, useTimeline } from "@/lib/api/hooks";
import type { CategoryBlock, LookupResponse, Result, RuleResult } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { fmtDate, fromISO, toISO } from "@/lib/format";
import { useMedia } from "@/hooks/use-media";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { MapPanel } from "@/components/map/MapPanel";
import { TimelineTrack } from "@/components/tenantly/TimelineTrack";
import { FindingRow, RuleRow } from "@/components/tenantly/RuleRow";
import { ResultPill } from "@/components/tenantly/ResultPill";
import { BoundaryBlock, BuildingFactsBlock, DecisivePanel, SummaryLine, WatchBlock } from "@/components/tenantly/ResultParts";
import { useLawSheets } from "@/components/tenantly/LawSheets";
import { cn } from "@/lib/utils";

const search = z.object({ asOf: z.string().optional() });

export const Route = createFileRoute("/a/$addressId")({
  validateSearch: search,
  head: ({ params }) => ({
    meta: [
      { title: `Housing laws for address ${params.addressId} — Tenantly` },
      { name: "description", content: "Every housing rule that reaches this apartment address on the chosen date, with the official law text quoted." },
      { property: "og:title", content: `Housing laws for address ${params.addressId} — Tenantly` },
      { property: "og:description", content: "Every housing rule that reaches this apartment address, quoted from the law." },
    ],
  }),
  component: ResultPage,
});

function ResultPage() {
  const { addressId } = Route.useParams();
  const { asOf: rawAsOf } = Route.useSearch();
  const navigate = useNavigate({ from: "/a/$addressId" });
  const { tr, t } = useI18n();
  const tl = useTimeline(addressId);
  const custom = useCustomLookup();
  const [userFacts, setUserFacts] = useState<Record<string, number | boolean | string> | null>(null);

  const range = tl.data?.range ?? { start: "2025-01-01", end: "2028-12-31" };
  const validRaw = !!rawAsOf && /^\d{4}-\d{2}-\d{2}$/.test(rawAsOf);
  const clamped = validRaw && (rawAsOf! < range.start || rawAsOf! > range.end);
  const asOf = !validRaw ? DEFAULT_AS_OF : rawAsOf! < range.start ? range.start : rawAsOf! > range.end ? range.end : rawAsOf!;

  const segLookup = useMemo(() => {
    if (!tl.data) return null;
    const seg = [...tl.data.segments].reverse().find((s) => s.start <= asOf) ?? tl.data.segments[0];
    return seg?.lookup ?? null;
  }, [tl.data, asOf]);

  // Re-run the custom lookup when the date changes while user facts are active.
  const { mutate } = custom;
  useEffect(() => {
    if (userFacts) mutate({ address_id: addressId, as_of: asOf, facts: userFacts });
  }, [userFacts, asOf, addressId, mutate]);

  const lookup: LookupResponse | null = userFacts && custom.data ? custom.data : segLookup;
  const setAsOf = (iso: string) => navigate({ search: { asOf: iso }, replace: true, resetScroll: false });

  if (tl.isLoading) return <ResultSkeleton label={t("lookup_loading")} />;
  if (tl.isError || !lookup || !tl.data) {
    return (
      <div className="mx-auto max-w-[1280px] px-5 pt-16 md:px-8">
        <h1 className="text-3xl text-deed">{tr("Results didn't load", "Los resultados no cargaron")}</h1>
        <p role="alert" className="mt-3 text-body text-graphite">{tr("We couldn't load results for this address. Check your connection and try again.", "No pudimos cargar los resultados para esta dirección. Revise su conexión e intente de nuevo.")}</p>
        <div className="mt-6 flex gap-3">
          <Button onClick={() => tl.refetch()}>{tr("Retry", "Reintentar")}</Button>
          <Button variant="outline" asChild><Link to="/">{t("go_home")}</Link></Button>
        </div>
      </div>
    );
  }

  return (
    <ResultView
      lookup={lookup}
      asOf={asOf}
      setAsOf={setAsOf}
      timeline={tl.data}
      clamped={clamped}
      busy={custom.isPending}
      usingUser={!!userFacts}
      onAnswer={(fact, value) => setUserFacts((prev) => ({ ...(prev ?? {}), [fact]: value }))}
      onReset={() => {
        setUserFacts(null);
        custom.reset();
      }}
    />
  );
}

function ResultSkeleton({ label }: { label: string }) {
  return (
    <div className="mx-auto max-w-[1280px] px-5 pt-10 md:px-8 md:pt-14" aria-label={label} aria-busy="true" role="status">
      <span className="sr-only">{label}</span>
      <div className="border-b border-hairline pb-8">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="mt-3 h-9 w-3/4 max-w-2xl" />
        <div className="mt-6 flex gap-6"><Skeleton className="h-9 w-24" /><Skeleton className="h-9 w-40" /><Skeleton className="h-9 w-32" /></div>
        <Skeleton className="mt-8 h-32 w-full rounded-lg" />
      </div>
      <div className="mt-10 grid gap-10 lg:grid-cols-12 lg:gap-12">
        <div className="lg:col-span-7">
          <Skeleton className="h-6 w-64" />
          {[0, 1, 2].map((i) => (
            <div key={i} className="mt-10 border-t-2 border-hairline pt-5">
              <Skeleton className="h-5 w-24" /><Skeleton className="mt-3 h-6 w-2/3" /><Skeleton className="mt-3 h-4 w-full" /><Skeleton className="mt-2 h-4 w-5/6" />
            </div>
          ))}
        </div>
        <div className="lg:col-span-5"><Skeleton className="h-80 w-full rounded-lg" /></div>
      </div>
    </div>
  );
}

interface ViewProps {
  lookup: LookupResponse;
  asOf: string;
  setAsOf: (s: string) => void;
  timeline: NonNullable<ReturnType<typeof useTimeline>["data"]>;
  clamped: boolean;
  busy: boolean;
  usingUser: boolean;
  onAnswer: (fact: string, v: number | boolean | string) => void;
  onReset: () => void;
}

function ResultView({ lookup, asOf, setAsOf, timeline, clamped, busy, usingUser, onAnswer, onReset }: ViewProps) {
  const { tr, tb, lang, t } = useI18n();
  const isDesktop = useMedia("(min-width: 1024px)", true);
  const j = lookup.jurisdiction;
  const [calOpen, setCalOpen] = useState(false);

  const scrollToDecisive = () => document.getElementById("decisive")?.scrollIntoView({ behavior: "smooth", block: "center" });

  const aside = <Aside lookup={lookup} onAdd={scrollToDecisive} compact={!isDesktop} />;

  return (
    <div className="mx-auto max-w-[1280px] px-5 md:px-8">
      {/* Header block: property, jurisdiction, date */}
      <header className="border-b border-hairline pb-8 pt-10 md:pt-14">
        <p className="flex items-center gap-1.5 text-sm text-graphite">
          <MapPin className="size-4" aria-hidden="true" />
          {lookup.address.is_sample ? tr("Sample building", "Edificio de muestra") : tr("Address", "Dirección")}
        </p>
        <h1 className="mt-2 text-[28px] leading-tight text-deed md:text-3xl">{lookup.address.label}</h1>

        <ol className="mt-6 flex flex-wrap items-end gap-x-3 gap-y-3" aria-label={tr("Jurisdictions", "Jurisdicciones")}>
          {[
            { level: tr("State", "Estado"), item: j.state },
            { level: tr("County", "Condado"), item: j.county },
            { level: tr("City", "Ciudad"), item: j.city },
          ].map((x, i) => (
            <li key={x.level} className="flex items-end gap-3">
              {i > 0 && <span className="hidden pb-0.5 text-graphite sm:inline" aria-hidden="true">›</span>}
              <span>
                <span className="block text-xs text-graphite">{x.level}</span>
                <span className={cn("text-base text-deed", i === 2 && x.item && "border-b-[3px] border-highlighter font-semibold")}>
                  {x.item ? (i === 0 ? x.item.name : x.item.label) : tr("Not in our sources", "No está en nuestras fuentes")}
                </span>
              </span>
            </li>
          ))}
        </ol>

        {!j.city && (
          <p role="status" className="mt-4 flex max-w-[68ch] items-start gap-2 text-base text-deed">
            <Info className="mt-1 size-4 shrink-0 text-permit" aria-hidden="true" />
            {tr("This address is outside the cities we cover. State law still applies; local laws for this place aren't in our sources yet.", "Esta dirección está fuera de las ciudades que cubrimos. La ley estatal sigue aplicando; las leyes locales de este lugar aún no están en nuestras fuentes.")}
          </p>
        )}
        {j.mailing_mismatch && j.note && (
          <p className="mt-4 flex max-w-[68ch] items-start gap-2 text-base text-deed">
            <Info className="mt-1 size-4 shrink-0 text-permit" aria-hidden="true" />
            {tb(j.note)}
          </p>
        )}

        <div className="mt-8 rounded-lg border border-hairline bg-sheet px-5 py-4 md:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-base text-deed">
              {tr("Showing the law as of", "Mostrando la ley al")} <span className="font-semibold tabular">{fmtDate(asOf, lang)}</span>
            </p>
            <Popover open={calOpen} onOpenChange={setCalOpen}>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm">
                  <CalendarDays />
                  {tr("Change date", "Cambiar fecha")}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-auto bg-popover p-0">
                <Calendar
                  mode="single"
                  selected={fromISO(asOf)}
                  defaultMonth={fromISO(asOf)}
                  startMonth={fromISO(timeline.range.start)}
                  endMonth={fromISO(timeline.range.end)}
                  disabled={[{ before: fromISO(timeline.range.start) }, { after: fromISO(timeline.range.end) }]}
                  onSelect={(d) => {
                    if (d) {
                      setAsOf(toISO(new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))));
                      setCalOpen(false);
                    }
                  }}
                  className="pointer-events-auto p-3"
                />
              </PopoverContent>
            </Popover>
          </div>
          <TimelineTrack timeline={timeline} asOf={asOf} onChange={setAsOf} appliesCount={lookup.counts.applies} />
          {clamped && (
            <p role="status" className="mt-2 text-sm text-deed">
              {tr("Tenantly covers January 1, 2025 to December 31, 2028.", "Tenantly cubre del 1 de enero de 2025 al 31 de diciembre de 2028.")}
            </p>
          )}
          {lookup.is_projection && (
            <p className="mt-2 text-sm text-graphite">
              {tr(
                "This date is after our sources were retrieved (October 1, 2026). This is a projection from those sources; laws may have changed since.",
                "Esta fecha es posterior a la obtención de nuestras fuentes (1 de octubre de 2026). Es una proyección; las leyes pueden haber cambiado.",
              )}
            </p>
          )}
        </div>
      </header>

      <div className="mt-8 grid gap-10 lg:mt-10 lg:grid-cols-12 lg:gap-12">
        {!isDesktop && <div>{aside}</div>}

        <div className="min-w-0 lg:col-span-7">
          <div aria-live="polite"><SummaryLine counts={lookup.counts} /></div>
          <div className="mt-6">
            <DecisivePanel q={lookup.decisive_question} onSubmit={onAnswer} busy={busy} usingUser={usingUser} onReset={onReset} />
          </div>

          {lookup.categories.map((c) => (
            <CategorySection key={c.category} block={c} asOf={asOf} lookup={lookup} />
          ))}

          {lookup.upcoming.length > 0 && (
            <section className="mt-14">
              <h2 className="text-xl text-deed">{tr("Coming up", "Próximamente")}</h2>
              <ul className="mt-4 divide-y divide-hairline border-y border-hairline">
                {lookup.upcoming.map((u) => (
                  <li key={u.rule_id + u.date} className="grid gap-1 py-4 sm:grid-cols-[9rem_1fr]">
                    <button type="button" onClick={() => setAsOf(u.date)} className="text-left text-base font-semibold text-permit tabular hover:underline">
                      {fmtDate(u.date, lang, "short")}
                    </button>
                    <div>
                      <p className="text-base text-deed">{u.title}</p>
                      <p className="text-sm text-graphite">
                        <ResultWord r={u.from} /> {tr("becomes", "pasa a")} <ResultWord r={u.to} />
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {lookup.pending.length > 0 && (
            <section className="mt-14">
              <h2 className="text-xl text-deed">{tr("Proposed, not law", "Propuestas, no son ley")}</h2>
              <p className="mt-1 text-base text-graphite">{tr("These bills are not law. They would cover this building if passed.", "Estos proyectos no son ley. Cubrirían este edificio si se aprueban.")}</p>
              <div className="mt-4 border-t border-hairline">
                {lookup.pending.map((r) => <RuleRow key={r.rule_id} r={r} asOf={asOf} boundary={lookup.reasoning_boundary} />)}
              </div>
            </section>
          )}

          {lookup.failed.length > 0 && <FailedSection lookup={lookup} />}

          {lookup.open_questions.length > 0 && (
            <section className="mt-14">
              <h2 className="text-xl text-deed">{tr("Open questions", "Preguntas abiertas")}</h2>
              <ul className="mt-4 space-y-3">
                {lookup.open_questions.map((q) => (
                  <li key={q.oq_id} id={`oq-${q.oq_id}`} className="scroll-mt-24 rounded-lg border border-hairline bg-sheet p-5">
                    <h3 className="text-lg text-deed">{tb(q.title)}</h3>
                    <p className="mt-1 text-base text-graphite prose-width">{tb(q.detail)}</p>
                    {q.sources.length > 0 && <p className="mt-2 text-sm text-graphite">{q.sources.map((s) => s.cite).join(", ")}</p>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <p className="mt-14 border-t border-deed/70 pt-5 text-base font-medium text-deed prose-width">{t("disclaimer")}</p>
        </div>

        {isDesktop && (
          <div className="lg:col-span-5">
            <div className="sticky top-[88px]">{aside}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function ResultWord({ r }: { r: Result | "none" }) {
  const { tr } = useI18n();
  const words: Record<Result | "none", [string, string]> = {
    none: ["no rule", "sin regla"], applies: ["applies", "aplica"], unknown: ["can't tell yet", "aún no se sabe"],
    superseded: ["overridden", "reemplazada"], not_yet_effective: ["not in effect yet", "aún no vigente"], pending: ["proposed", "propuesta"],
  };
  const [en, es] = words[r];
  return <span className="font-medium text-deed">{tr(en, es)}</span>;
}

function CategorySection({ block, asOf, lookup }: { block: CategoryBlock; asOf: string; lookup: LookupResponse }) {
  const { tb, tr } = useI18n();
  const primary = block.results.filter((r) => r.result !== "superseded" || !block.results.some((g) => g.rule_id === r.superseded_by));
  const childrenOf = (id: string): RuleResult[] => block.results.filter((r) => r.result === "superseded" && r.superseded_by === id);
  return (
    <section className="mt-14" aria-labelledby={`cat-${block.category}`}>
      <div className="border-b-2 border-deed pb-3">
        <h2 id={`cat-${block.category}`} className="text-xl text-deed">{tb(block.label)}</h2>
        <p className="mt-1 text-body text-graphite">{tb(block.headline)}</p>
      </div>
      <div>
        {primary.map((r) => (
          <RuleRow key={r.rule_id} r={r} superseded={childrenOf(r.rule_id)} asOf={asOf} boundary={lookup.reasoning_boundary} />
        ))}
        {block.findings.map((f) => <FindingRow key={f.finding_id} f={f} />)}
        {primary.length === 0 && block.findings.length === 0 && (
          <p className="py-5 text-base text-graphite">{tr("Nothing to show for this category on this date.", "No hay nada que mostrar en esta categoría para esta fecha.")}</p>
        )}
      </div>
    </section>
  );
}

function FailedSection({ lookup }: { lookup: LookupResponse }) {
  const { tr, tb } = useI18n();
  const { openSource } = useLawSheets();
  return (
    <section className="mt-14">
      <h2 className="text-xl text-deed">{tr("Not law", "No es ley")}</h2>
      <ul className="mt-4 border-t border-hairline">
        {lookup.failed.map((f) => (
          <li key={f.rule_id} className="ledger-rail border-b border-dashed border-hairline border-l-superseded-border py-5 pl-5 md:pl-7">
            <ResultPill result="none" />
            <p className="mt-2 text-lg font-semibold text-deed">{f.title}</p>
            <p className="text-base text-graphite">{tb(f.note)}</p>
            <button type="button" className="mt-2 text-sm text-permit hover:underline" onClick={() => openSource({ citation: f.citation, ruleId: null })}>
              {tr("Read the law", "Leer la ley")}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Aside({ lookup, onAdd, compact }: { lookup: LookupResponse; onAdd: () => void; compact: boolean }) {
  const { tr } = useI18n();
  const geo = useJurisdictionGeo(lookup.jurisdiction.city?.id);
  const [mapOpen, setMapOpen] = useState(!compact);
  const [open, setOpen] = useState(false);
  const cityName = lookup.jurisdiction.city?.label ?? lookup.jurisdiction.state.name;

  const mapBlock = (
    <figure className="overflow-hidden rounded-lg border border-hairline bg-sheet">
      <MapPanel
        city={geo.data ?? null}
        points={[{ id: lookup.address.address_id, lat: lookup.address.lat, lon: lookup.address.lon, kind: "building", label: lookup.address.label }]}
        height={compact ? 220 : 320}
        ariaLabel={`Map showing ${lookup.address.label} inside ${cityName}`}
      />
      <figcaption className="flex items-center gap-2 border-t border-hairline px-4 py-2.5 text-sm text-graphite">
        <span className="inline-block size-3 border border-deed bg-highlighter/60" aria-hidden="true" />
        {tr(`Legal boundary: ${cityName}`, `Límite legal: ${cityName}`)}
      </figcaption>
    </figure>
  );

  const rest = (
    <div className="space-y-8">
      <BuildingFactsBlock facts={lookup.facts} onAdd={onAdd} />
      <WatchBlock lookup={lookup} />
      <BoundaryBlock b={lookup.reasoning_boundary} />
    </div>
  );

  if (!compact) {
    return (
      <aside className="space-y-8" aria-label={tr("Property and map", "Propiedad y mapa")}>
        {mapBlock}
        {rest}
      </aside>
    );
  }

  const yb = lookup.facts.year_built.value;
  const units = lookup.facts.units.value;
  return (
    <aside className="rounded-lg border border-hairline bg-sheet" aria-label={tr("Property and map", "Propiedad y mapa")}>
      <Collapsible open={mapOpen} onOpenChange={setMapOpen}>
        <CollapsibleTrigger className="flex min-h-12 w-full items-center justify-between px-4 text-left text-base font-medium text-deed">
          {tr("Map", "Mapa")}
          <ChevronDown className={cn("size-4 transition-transform", mapOpen && "rotate-180")} />
        </CollapsibleTrigger>
        <CollapsibleContent className="px-3 pb-3">{mapBlock}</CollapsibleContent>
      </Collapsible>
      <Collapsible open={open} onOpenChange={setOpen} className="border-t border-hairline">
        <CollapsibleTrigger className="flex min-h-12 w-full items-center justify-between gap-3 px-4 text-left">
          <span>
            <span className="block text-base font-medium text-deed">{tr("Building record", "Registro del edificio")}</span>
            <span className="block text-sm text-graphite tabular">
              {yb == null ? tr("Year built unknown", "Año desconocido") : tr(`Built ${yb}`, `Construido en ${yb}`)}
              {units != null ? `, ${units} ${tr("units", "unidades")}` : ""}
            </span>
          </span>
          <ChevronDown className={cn("size-4 shrink-0 transition-transform", open && "rotate-180")} />
        </CollapsibleTrigger>
        <CollapsibleContent className="px-4 pb-5">{rest}</CollapsibleContent>
      </Collapsible>
    </aside>
  );
}
