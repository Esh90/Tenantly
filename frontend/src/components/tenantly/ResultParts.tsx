import { useState } from "react";
import { AlertTriangle, BellRing, Check } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { RESULT_META } from "./ResultPill";
import { useAlertStatus, useSubscribeAlerts } from "@/lib/api/hooks";
import type { BuildingFacts as Facts, DecisiveQuestion, FactValue, LookupResponse, ReasoningBoundary, Result } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { useWatched } from "@/lib/watch";
import { cn } from "@/lib/utils";
import { fmtDate } from "@/lib/format";

/* ---------- summary line ---------- */
export function SummaryLine({ counts }: { counts: Record<Result, number> }) {
  const { tr } = useI18n();
  const parts: { r: Result; text: string }[] = [];
  const n = (k: Result) => counts[k] ?? 0;
  parts.push({ r: "applies", text: n("applies") === 1 ? tr("1 rule applies.", "Aplica 1 regla.") : tr(`${n("applies")} rules apply.`, `Aplican ${n("applies")} reglas.`) });
  if (n("superseded")) parts.push({ r: "superseded", text: tr(`${n("superseded")} ${n("superseded") === 1 ? "is" : "are"} overridden by stricter local rules.`, `${n("superseded")} reemplazada(s) por reglas locales más estrictas.`) });
  if (n("not_yet_effective")) parts.push({ r: "not_yet_effective", text: tr(`${n("not_yet_effective")} ${n("not_yet_effective") === 1 ? "starts" : "start"} later.`, `${n("not_yet_effective")} entra(n) en vigor más adelante.`) });
  if (n("unknown")) parts.push({ r: "unknown", text: tr(`${n("unknown")} can't be settled yet.`, `${n("unknown")} aún no se puede(n) resolver.`) });
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 text-lg text-deed">
      {parts.map((p) => {
        const M = RESULT_META[p.r];
        const Icon = M.icon;
        return (
          <span key={p.r} className="inline-flex items-center gap-1.5">
            <Icon className={cn("size-[18px]", M.pill.split(" ")[0])} aria-hidden="true" />
            {p.text}
          </span>
        );
      })}
    </p>
  );
}

/* ---------- decisive question ---------- */
export function DecisivePanel({
  q,
  onSubmit,
  busy,
  usingUser,
  onReset,
}: {
  q: DecisiveQuestion | null;
  onSubmit: (fact: string, value: number | boolean | string) => void;
  busy: boolean;
  usingUser: boolean;
  onReset: () => void;
}) {
  const { tr, tb } = useI18n();
  const [val, setVal] = useState("");
  const [err, setErr] = useState("");
  if (!q && !usingUser) return null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!q) return;
    if (q.input === "year") {
      const y = Number(val);
      if (!Number.isInteger(y) || y < 1800 || y > 2026) return setErr(tr("Enter a year between 1800 and 2026.", "Escriba un año entre 1800 y 2026."));
      onSubmit(q.fact, y);
    } else if (q.input === "integer") {
      const n = Number(val);
      if (!Number.isInteger(n) || n < 1) return setErr(tr("Enter a whole number.", "Escriba un número entero."));
      onSubmit(q.fact, n);
    } else if (q.input === "boolean") {
      if (!val) return setErr(tr("Choose Yes or No.", "Elija Sí o No."));
      onSubmit(q.fact, val === "yes");
    } else onSubmit(q.fact, val);
    setErr("");
  };

  return (
    <section id="decisive" className="rounded-lg border border-deed bg-sheet p-5 md:p-6">
      {q && (
        <form onSubmit={submit}>
          <h2 className="text-lg text-deed">
            {tr(`One answer would settle ${q.resolves_rule_ids.length} ${q.resolves_rule_ids.length === 1 ? "rule" : "rules"}:`, `Una respuesta resolvería ${q.resolves_rule_ids.length} regla(s):`)}{" "}
            <span className="font-normal">{tb(q.prompt)}</span>
          </h2>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            {q.input === "boolean" ? (
              <ToggleGroup type="single" value={val} onValueChange={setVal} className="gap-2">
                {[["yes", tr("Yes", "Sí")], ["no", "No"]].map(([v, l]) => (
                  <ToggleGroupItem key={v} value={v!} className="h-11 rounded-md border border-hairline px-5 data-[state=on]:border-deed data-[state=on]:bg-deed data-[state=on]:text-primary-foreground">
                    {l}
                  </ToggleGroupItem>
                ))}
              </ToggleGroup>
            ) : q.input === "select" && q.options ? (
              <select
                aria-label={tb(q.prompt)}
                value={val}
                onChange={(e) => setVal(e.target.value)}
                className="h-11 rounded-md border border-hairline bg-sheet px-3"
              >
                <option value="">{tr("Choose one", "Elija una")}</option>
                {q.options.map((o) => <option key={o.value} value={o.value}>{tb(o.label)}</option>)}
              </select>
            ) : (
              <div>
                <Label htmlFor="dq" className="sr-only">{tb(q.prompt)}</Label>
                <Input id="dq" inputMode="numeric" value={val} onChange={(e) => setVal(e.target.value)} placeholder={q.input === "year" ? "1985" : "12"} className="h-11 w-36 text-base tabular" />
              </div>
            )}
            <Button type="submit" disabled={busy}>{busy ? tr("Updating", "Actualizando") : tr("Update results", "Actualizar resultados")}</Button>
          </div>
          {err && <p className="mt-2 text-sm text-destructive" role="alert">{err}</p>}
        </form>
      )}
      {usingUser && (
        <div className={cn("flex flex-wrap items-center justify-between gap-3", q && "mt-4 border-t border-hairline pt-4")}>
          <p className="text-base text-deed">{tr("Based on what you told us.", "Según lo que nos dijo.")}</p>
          <Button variant="outline" size="sm" onClick={onReset}>{tr("Use public records only", "Usar solo registros públicos")}</Button>
        </div>
      )}
    </section>
  );
}

/* ---------- building facts ---------- */
function sourceWords(f: FactValue, tr: (a: string, b: string) => string) {
  switch (f.source) {
    case "assessor": return tr("Public record", "Registro público");
    case "assessor_derived": return `${tr("Derived from public record", "Derivado del registro público")}: ${f.basis ?? ""}`;
    case "user": return tr("You told us", "Usted nos dijo");
    case "derived": return tr("Derived from public record", "Derivado del registro público");
    default: return tr("Not in public records", "No está en registros públicos");
  }
}

export function BuildingFactsBlock({ facts, onAdd }: { facts: Facts; onAdd: () => void }) {
  const { tr, tb } = useI18n();
  const rows: [string, FactValue][] = [
    [tr("Year built", "Año de construcción"), facts.year_built],
    [tr("Units", "Unidades"), facts.units],
    [tr("Building type", "Tipo de edificio"), facts.property_type],
    [tr("Subsidized", "Subsidiado"), facts.subsidized],
  ];
  return (
    <section>
      <h2 className="text-base font-semibold text-deed">{tr("Building record", "Registro del edificio")}</h2>
      <dl className="mt-3 divide-y divide-hairline border-y border-hairline">
        {rows.map(([k, f]) => (
          <div key={k} className="grid grid-cols-[7.5rem_1fr] gap-3 py-2.5">
            <dt className="text-sm text-graphite">{k}</dt>
            <dd>
              <span className={cn("block text-base tabular", f.value == null ? "text-graphite" : "text-deed")}>
                {f.value == null ? "—" : tb(f.label)}
              </span>
              <span className="block text-xs text-graphite">{sourceWords(f, tr)}</span>
              {f.record_conflict && (
                <span className="mt-1 flex items-start gap-1 text-xs text-unknown">
                  <AlertTriangle className="size-3.5" />
                  {tr("Public records disagree; treated as unknown", "Los registros públicos no coinciden; se trata como desconocido")}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
      {facts.zip_suspect && (
        <p className="mt-3 rounded-md border border-unknown-border bg-unknown-bg px-3 py-2 text-sm text-unknown">
          {tr("The ZIP in public records is outside this city; we ignored it for location.", "El código postal del registro está fuera de esta ciudad; lo ignoramos para la ubicación.")}
        </p>
      )}
      <p className="mt-2 text-xs text-graphite">{facts.source_dataset}</p>
      <Button variant="link" className="h-auto px-0 py-2 text-base text-permit" onClick={onAdd}>
        {tr("Add what you know", "Agregar lo que sabe")}
      </Button>
    </section>
  );
}

/* ---------- reasoning boundary ---------- */
export function BoundaryBlock({ b }: { b: ReasoningBoundary }) {
  const { tr, tb } = useI18n();
  const lists: [string, typeof b.checked][] = [
    [tr("Checked", "Revisado"), b.checked],
    [tr("Not checked", "No revisado"), b.not_checked],
    [tr("Assumptions", "Supuestos"), b.assumptions],
  ];
  return (
    <section>
      <h2 className="text-base font-semibold text-deed">{tr("What we checked", "Lo que revisamos")}</h2>
      {lists.map(([k, items]) => (
        <div key={k} className="mt-3">
          <h3 className="text-sm text-graphite">{k}</h3>
          <ul className="mt-1 space-y-1">
            {items.map((x, i) => (
              <li key={i} className="flex gap-2 text-sm text-deed">
                <span className="mt-2 h-px w-2.5 shrink-0 bg-graphite" aria-hidden="true" />
                {tb(x)}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}

/* ---------- watch ---------- */
export function WatchBlock({ lookup }: { lookup: LookupResponse }) {
  const { tr, lang } = useI18n();
  const { list, isWatched, add } = useWatched();
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const sub = useSubscribeAlerts();
  const watched = isWatched(lookup.address.address_id);
  const entry = list.find((item) => item.address_id === lookup.address.address_id);
  const status = useAlertStatus(entry?.token);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const r = await sub.mutateAsync({ email, address_id: lookup.address.address_id, lang });
      add({ address_id: r.address_id, label: lookup.address.label, since: r.created_at, token: r.unsubscribe_token, atom: r.feeds.atom, ics: r.feeds.ics });
      toast.success(tr("Watching this address", "Siguiendo esta dirección"));
    } catch {
      toast.error(tr("We couldn't save that. Try again.", "No pudimos guardarlo. Intente de nuevo."));
    }
  };

  return (
    <section>
      <h2 className="text-base font-semibold text-deed">{tr("Watch this address", "Seguir esta dirección")}</h2>
      <p className="mt-1 text-sm text-graphite">{tr("We'll notify you when a published housing-law change affects this address.", "Le avisaremos cuando un cambio publicado en la ley de vivienda afecte esta dirección.")}</p>
      <Button variant={watched ? "outline" : "default"} className="mt-3 w-full" onClick={() => setOpen(true)}>
        {watched ? <Check /> : <BellRing />}
        {watched ? tr("✓ You're watching this property", "✓ Está siguiendo esta propiedad") : tr("Watch this address", "Seguir esta dirección")}
      </Button>
      {watched && (
        <div className="mt-3 rounded-md border border-hairline bg-sheet px-3 py-3 text-sm">
          <p className="font-semibold text-deed">{tr("Notification status", "Estado de notificación")}</p>
          <p className="mt-1 text-applies">{tr("✓ Watching this address", "✓ Siguiendo esta dirección")}</p>
          {status.data && !status.data.notifications_configured && (
            <p className="mt-1 text-unknown">{tr("Email notifications are not configured.", "Las notificaciones por correo no están configuradas.")}</p>
          )}
          {status.data?.last_notification?.status === "sent" && (
            <p className="mt-1 text-graphite">{tr("Last notification", "Última notificación")}: {fmtDate(status.data.last_notification.attempted_at.slice(0, 10), lang)}</p>
          )}
          {status.data?.last_notification?.status === "failed" && (
            <p className="mt-1 text-destructive">⚠ {tr("Notification could not be sent", "No se pudo enviar la notificación")}</p>
          )}
          {status.data && !status.data.last_notification && (
            <p className="mt-1 text-graphite">{tr("No notifications yet.", "Aún no hay notificaciones.")}</p>
          )}
        </div>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-sheet sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-xl">{tr("Watch this address", "Seguir esta dirección")}</DialogTitle>
            <DialogDescription>{lookup.address.label}</DialogDescription>
          </DialogHeader>
          {sub.data || watched ? (
            <div className="space-y-3">
              <p className="text-base font-semibold text-deed">{tr("✓ You're watching this property", "✓ Está siguiendo esta propiedad")}</p>
              <p className="text-sm text-graphite">{tr("We'll notify you when a published housing-law change affects this address.", "Le avisaremos cuando un cambio publicado en la ley de vivienda afecte esta dirección.")}</p>
              {sub.data && !sub.data.notifications_configured && <p className="text-sm text-unknown">{tr("Email notifications are not configured.", "Las notificaciones por correo no están configuradas.")}</p>}
              <DialogFooter>
                <Button type="button" onClick={() => setOpen(false)}>{tr("Done", "Listo")}</Button>
              </DialogFooter>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <Label htmlFor="w-email">{tr("Email", "Correo")}</Label>
                <Input id="w-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1.5 h-11" />
              </div>
              <DialogFooter>
                <Button type="submit" disabled={sub.isPending}>{tr("Start Watching", "Empezar a seguir")}</Button>
              </DialogFooter>
            </form>
          )}
        </DialogContent>
      </Dialog>
    </section>
  );
}
