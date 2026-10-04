import { useMemo } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, Download } from "lucide-react";
import { Page, PageHeader, SectionTitle } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { MapPanel, type MapPoint } from "@/components/map/MapPanel";
import { ResultPill } from "@/components/tenantly/ResultPill";
import { useAddressIndex, useChange } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n";
import { downloadCsv } from "@/lib/format";
import { compareText, kindText, typeText } from "@/lib/changes";

export const Route = createFileRoute("/changes/$id")({
  head: ({ params }) => ({
    meta: [
      { title: `Change ${params.id} — Tenantly` },
      { name: "description", content: "Which sample buildings one change in the law reaches, before and after." },
      { property: "og:title", content: `Change ${params.id} — Tenantly` },
      { property: "og:description", content: "Which sample buildings one change in the law reaches, before and after." },
    ],
  }),
  component: ChangeDetail,
});

function ChangeDetail() {
  const { id } = Route.useParams();
  const { tr, tb, lang } = useI18n();
  const q = useChange(id);
  const index = useAddressIndex();
  const c = q.data;

  const points = useMemo<MapPoint[]>(() => {
    if (!c) return [];
    const changed = new Set(c.affected.map((a) => a.address_id));
    const cities = new Set(c.affected.map((a) => a.legal_city));
    const others = (index.data ?? [])
      .filter((a) => cities.has(a.legal_city) && !changed.has(a.address_id))
      .map((a) => ({ id: a.address_id, lat: a.lat, lon: a.lon, kind: "other" as const, label: a.label }));
    return [...others, ...c.affected.map((a) => ({ id: a.address_id, lat: a.lat, lon: a.lon, kind: "changed" as const, label: a.label }))];
  }, [c, index.data]);

  if (q.isLoading) return <Page><div className="pt-16"><Skeleton className="h-10 w-1/2" /><Skeleton className="mt-6 h-64" /></div></Page>;
  if (!c) return <Page><div className="pt-16"><h1 className="text-3xl text-deed">{tr("We couldn't find that change.", "No pudimos encontrar ese cambio.")}</h1><Button asChild className="mt-6"><Link to="/changes">{tr("See all changes", "Ver todos los cambios")}</Link></Button></div></Page>;

  const csv = () =>
    downloadCsv(`${c.change_id}.csv`, [
      ["address_id", "address", "legal_city", "before", "after", "conflict"],
      ...c.affected.map((a) => [a.address_id, a.label, a.legal_city ?? "", a.before.map((b) => `${b.rule_id}:${b.result}`).join(" "), a.after.map((b) => `${b.rule_id}:${b.result}`).join(" "), a.conflict_flag ? "yes" : "no"]),
    ]);

  return (
    <Page>
      <nav className="pt-8 text-sm text-graphite" aria-label="Breadcrumb">
        <Link to="/changes" className="text-permit hover:underline">{tr("Changes", "Cambios")}</Link>
      </nav>
      <PageHeader
        title={c.title}
        lede={tb(c.summary)}
        aside={
          <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div><dt className="text-graphite">{tr("Kind", "Tipo")}</dt><dd className="text-deed">{kindText(c.kind, tr)}{c.test_id ? `, ${c.test_id}` : ""}</dd></div>
            <div><dt className="text-graphite">{tr("Type", "Clase")}</dt><dd className="text-deed">{typeText(c.test_type, tr)}</dd></div>
            <div><dt className="text-graphite">{tr("Compared", "Comparado")}</dt><dd className="text-deed tabular">{compareText(c, lang, tr)}</dd></div>
            <div><dt className="text-graphite">{tr("Buildings affected", "Edificios afectados")}</dt><dd className="text-lg font-semibold text-deed tabular">{c.affected_count}</dd></div>
          </dl>
        }
      />

      {c.conflict_count > 0 && (
        <p className="mt-8 flex max-w-[72ch] items-start gap-2 rounded-md border border-unknown-border bg-unknown-bg px-4 py-3 text-base text-unknown">
          <AlertTriangle className="mt-1 size-4 shrink-0" />
          {tr(`${c.conflict_count} buildings are flagged for a possible conflict between rules after this change.`, `${c.conflict_count} edificios quedan marcados por un posible conflicto entre reglas tras este cambio.`)}
        </p>
      )}

      {c.affected.length === 0 ? (
        <p className="mt-10 rounded-lg border border-dashed border-superseded-border px-6 py-10 text-lg text-deed">
          {tr("No buildings are affected. This measure is not law.", "Ningún edificio está afectado. Esta medida no es ley.")}
        </p>
      ) : (
        <div className="mt-10 grid gap-10 lg:grid-cols-12">
          <figure className="overflow-hidden rounded-lg border border-hairline bg-sheet lg:col-span-5 lg:self-start lg:sticky lg:top-[88px]">
            <MapPanel points={points} fit="points" height={360} ariaLabel={tr(`Map of ${c.affected.length} affected buildings`, `Mapa de ${c.affected.length} edificios afectados`)} />
            <figcaption className="flex flex-wrap gap-4 border-t border-hairline px-4 py-2.5 text-sm text-graphite">
              <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full border border-deed bg-highlighter" />{tr("Changed", "Cambió")}</span>
              <span className="inline-flex items-center gap-1.5"><span className="size-1.5 rounded-full bg-graphite" />{tr("Other addresses in the city", "Otras direcciones en la ciudad")}</span>
            </figcaption>
          </figure>
          <div className="min-w-0 lg:col-span-7">
            <div className="flex items-end justify-between gap-4">
              <div className="flex-1"><SectionTitle title={tr("Before and after", "Antes y después")} sub={tr(`A sample of ${c.affected.length} of ${c.affected_count} buildings.`, `Una muestra de ${c.affected.length} de ${c.affected_count} edificios.`)} /></div>
            </div>
            <div className="-mx-5 overflow-x-auto md:mx-0">
              <table className="w-full min-w-[560px] text-left">
                <thead>
                  <tr className="border-b border-hairline text-sm text-graphite">
                    <th className="py-2.5 pl-5 pr-3 font-medium md:pl-0">{tr("Address", "Dirección")}</th>
                    <th className="py-2.5 pr-3 font-medium">{tr("Before", "Antes")}</th>
                    <th className="py-2.5 pr-3 font-medium">{tr("After", "Después")}</th>
                    <th className="py-2.5 pr-5 font-medium md:pr-0">{tr("Conflict", "Conflicto")}</th>
                  </tr>
                </thead>
                <tbody>
                  {c.affected.map((a) => (
                    <tr key={a.address_id} className="border-b border-hairline align-top">
                      <td className="py-3 pl-5 pr-3 md:pl-0">
                        <Link to="/a/$addressId" params={{ addressId: a.address_id }} className="text-base text-deed underline-offset-4 hover:text-permit hover:underline">{a.label}</Link>
                      </td>
                      <td className="py-3 pr-3">{a.before.map((b) => <ResultPill key={b.rule_id} result={b.result} />)}</td>
                      <td className="py-3 pr-3">{a.after.map((b) => <ResultPill key={b.rule_id} result={b.result} />)}</td>
                      <td className="py-3 pr-5 text-sm md:pr-0">{a.conflict_flag ? <span className="inline-flex items-center gap-1 text-unknown"><AlertTriangle className="size-4" />{tr("Possible", "Posible")}</span> : <span className="text-graphite">{tr("None", "Ninguno")}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Button variant="outline" className="mt-6" onClick={csv}><Download />{tr("Download this table", "Descargar esta tabla")}</Button>
          </div>
        </div>
      )}
    </Page>
  );
}
