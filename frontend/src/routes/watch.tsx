import { useEffect } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { CalendarPlus, Rss, X } from "lucide-react";
import { Page, PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useChanges, useUnsubscribeAlerts } from "@/lib/api/hooks";
import { useWatched } from "@/lib/watch";
import { useI18n } from "@/lib/i18n";
import { fmtDate } from "@/lib/format";
import { API_BASE_URL } from "@/config";

export const Route = createFileRoute("/watch")({
  head: () => ({
    meta: [
      { title: "Watched addresses — Tenantly" },
      { name: "description", content: "Addresses you follow, and the changes in housing law that reach them." },
      { property: "og:title", content: "Watched addresses — Tenantly" },
      { property: "og:description", content: "Addresses you follow, and the changes in housing law that reach them." },
    ],
  }),
  component: WatchPage,
});

function WatchPage() {
  const { tr, tb, lang } = useI18n();
  const { list, remove, markSeen, unseen } = useWatched();
  const changes = useChanges();
  const unsub = useUnsubscribeAlerts();
  const feed = (p?: string) => (p ? (API_BASE_URL ? `${API_BASE_URL}${p}` : p) : undefined);

  useEffect(() => {
    if (unseen && list.length) markSeen();
  }, [unseen, list.length, markSeen]);

  return (
    <Page narrow>
      <PageHeader title={tr("Watched addresses", "Direcciones seguidas")} lede={tr("Addresses you follow on this device, and the changes in the law that reach them.", "Direcciones que sigue en este dispositivo y los cambios en la ley que les afectan.")} />
      {list.length === 0 ? (
        <div className="mt-10 rounded-lg border border-dashed border-hairline px-6 py-12">
          <p className="text-lg text-deed">{tr("You're not watching any addresses yet. Open an address and choose Watch this address.", "Aún no sigue ninguna dirección. Abra una dirección y elija Seguir esta dirección.")}</p>
          <Button asChild className="mt-6"><Link to="/">{tr("Look up address", "Buscar dirección")}</Link></Button>
        </div>
      ) : (
        <ul className="mt-6">
          {list.map((w) => {
            const hits = (changes.data ?? []).filter((c) => c.affected.some((a) => a.address_id === w.address_id));
            return (
              <li key={w.address_id} className="border-b border-hairline py-8">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <Link to="/a/$addressId" params={{ addressId: w.address_id }} className="text-xl font-semibold text-deed underline-offset-4 hover:text-permit hover:underline">{w.label}</Link>
                    <p className="mt-1 text-sm text-graphite">{tr("Watching since", "Siguiendo desde")} {fmtDate(w.since.slice(0, 10), lang)}</p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => { if (w.token) unsub.mutate(w.token); remove(w.address_id); }}>
                    <X />{tr("Stop watching", "Dejar de seguir")}
                  </Button>
                </div>
                <h3 className="mt-5 text-sm font-semibold text-graphite">{tr("Changes since you started watching", "Cambios desde que empezó a seguir")}</h3>
                {hits.length ? (
                  <ul className="mt-2 divide-y divide-hairline border-y border-hairline">
                    {hits.map((c) => (
                      <li key={c.change_id} className="py-3">
                        <Link to="/changes/$id" params={{ id: c.change_id }} className="text-base text-deed underline-offset-4 hover:text-permit hover:underline">{c.title}</Link>
                        <p className="text-sm text-graphite">{tb(c.summary)}</p>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-base text-graphite">{tr("No changes for this address yet.", "Aún no hay cambios para esta dirección.")}</p>
                )}
                {(w.ics || w.atom) && (
                  <div className="mt-4 flex flex-wrap gap-5 text-sm">
                    {w.ics && <a href={feed(w.ics)} className="inline-flex items-center gap-1.5 text-permit hover:underline"><CalendarPlus className="size-4" />{tr("Add effective dates to your calendar", "Agregar fechas a su calendario")}</a>}
                    {w.atom && <a href={feed(w.atom)} className="inline-flex items-center gap-1.5 text-permit hover:underline"><Rss className="size-4" />{tr("Follow changes in a feed reader", "Seguir en un lector de noticias")}</a>}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Page>
  );
}
