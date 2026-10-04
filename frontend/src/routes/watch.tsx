import { useEffect } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, CalendarPlus, Check, X } from "lucide-react";
import { Page, PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useAlertStatus, useChangeDetails, useUnsubscribeAlerts } from "@/lib/api/hooks";
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
  const changes = useChangeDetails(list.length > 0);
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
            const hits = changes.filter(
              (c) =>
                (!w.since || c.created_at >= w.since) &&
                (c.affected ?? []).some((a) => a.address_id === w.address_id),
            );
            return (
              <li key={w.address_id} className="border-b border-hairline py-8">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <Link to="/a/$addressId" params={{ addressId: w.address_id }} className="text-xl font-semibold text-deed underline-offset-4 hover:text-permit hover:underline">{w.label}</Link>
                    {w.since && <p className="mt-1 text-sm text-graphite">{tr("Watching since", "Siguiendo desde")} {fmtDate(w.since.slice(0, 10), lang)}</p>}
                    <WatchDeliveryStatus token={w.token} />
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
                {w.ics && (
                  <a href={feed(w.ics)} download={`${w.address_id}.ics`} className="mt-4 inline-flex items-center gap-1.5 text-sm text-permit hover:underline">
                    <CalendarPlus className="size-4" />{tr("Add effective dates to your calendar", "Agregar fechas a su calendario")}
                  </a>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Page>
  );
}

function WatchDeliveryStatus({ token }: { token?: string | undefined }) {
  const { tr, lang } = useI18n();
  const status = useAlertStatus(token);
  if (!token || status.isLoading) return null;
  if (status.isError) return <p className="mt-2 text-sm text-destructive">{tr("Notification status unavailable.", "Estado de notificación no disponible.")}</p>;
  const data = status.data;
  if (!data) return null;
  return (
    <div className="mt-3 text-sm">
      <p className="font-semibold text-deed">{tr("Notification status", "Estado de notificación")}</p>
      {!data.notifications_configured && <p className="mt-1 text-unknown">{tr("Email notifications are not configured.", "Las notificaciones por correo no están configuradas.")}</p>}
      {!data.last_notification && <p className="mt-1 text-graphite">{tr("No notifications yet.", "Aún no hay notificaciones.")}</p>}
      {data.last_notification?.status === "sent" && (
        <p className="mt-1 flex items-center gap-1.5 text-applies"><Check className="size-4" />{tr("Last notification", "Última notificación")}: {fmtDate(data.last_notification.attempted_at.slice(0, 10), lang)}</p>
      )}
      {data.last_notification?.status === "failed" && (
        <p className="mt-1 flex items-center gap-1.5 text-destructive"><AlertTriangle className="size-4" />{tr("Notification could not be sent", "No se pudo enviar la notificación")}</p>
      )}
    </div>
  );
}
