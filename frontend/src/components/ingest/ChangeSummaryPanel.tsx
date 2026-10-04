import { Link } from "@tanstack/react-router";
import { PartyPopper } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { AuditEvent, ChangesSummary, IngestResultData } from "@/lib/api/types";
import { fmtTime } from "@/lib/ingest";
import { useI18n } from "@/lib/i18n";

export function ChangeSummaryPanel({ c, res, onSection }: { c: ChangesSummary; res: IngestResultData; onSection: (id: string) => void }) {
  const { tr } = useI18n();
  const sample = res.impact?.sample[0]?.address_id;
  const rows: [string, string][] = [
    [tr("Rules added", "Reglas agregadas"), String(c.rules_added)],
    [tr("Relationships added", "Relaciones agregadas"), String(c.relationships_added)],
    [tr("Existing relationships touched", "Relaciones existentes afectadas"), String(c.existing_relationships_touched)],
    [tr("Earlier rules superseded", "Reglas anteriores reemplazadas"), c.rules_superseded.length ? c.rules_superseded.join(", ") : "0"],
    [tr("Existing rules whose result changes", "Reglas existentes cuyo resultado cambia"), c.existing_rules_changed.length ? c.existing_rules_changed.join(", ") : "0"],
    [tr("Affected jurisdictions", "Jurisdicciones afectadas"), `${c.affected_jurisdictions.length} (${c.affected_jurisdictions.join(", ")})`],
    [tr("Potentially affected properties", "Propiedades potencialmente afectadas"), String(c.affected_properties)],
    [tr("Knowledge graph", "Grafo de conocimiento"), `+${c.graph_nodes_added} ${tr("nodes", "nodos")}, +${c.graph_edges_added} ${tr("relationships", "relaciones")}`],
  ];
  return (
    <section className="rounded-lg border border-applies-border bg-applies-bg">
      <header className="flex items-center gap-3 border-b border-applies-border px-5 py-4">
        <PartyPopper className="size-6 text-applies" aria-hidden="true" />
        <div>
          <h3 className="text-lg font-semibold text-applies">{tr("LAW PUBLISHED", "LEY PUBLICADA")}</h3>
          <p className="text-base text-deed">{c.document}</p>
        </div>
      </header>
      <dl className="grid gap-x-8 gap-y-3 px-5 py-5 sm:grid-cols-2">
        {rows.map(([k, v]) => <div key={k}><dt className="text-sm text-graphite">{k}</dt><dd className="text-base font-medium text-deed">{v}</dd></div>)}
      </dl>
      <footer className="flex flex-wrap gap-2 border-t border-applies-border bg-sheet px-5 py-4">
        <Button type="button" variant="outline" onClick={() => onSection("ing-rules")}>{tr("View rules", "Ver reglas")}</Button>
        <Button type="button" variant="outline" onClick={() => onSection("ing-json")}>{tr("View JSON", "Ver JSON")}</Button>
        <Button type="button" variant="outline" onClick={() => onSection("ing-graph")}>{tr("View knowledge graph", "Ver grafo de conocimiento")}</Button>
        {c.change_id && <Button asChild variant="outline"><Link to="/changes/$id" params={{ id: c.change_id }}>{tr("View affected properties", "Ver propiedades afectadas")}</Link></Button>}
        {sample && <Button asChild><Link to="/a/$addressId" params={{ addressId: sample }} search={{ asOf: res.impact?.effective_date ?? undefined }}>{tr("Open an affected address", "Abrir una dirección afectada")}</Link></Button>}
      </footer>
    </section>
  );
}

export function AuditTrail({ events }: { events: AuditEvent[] }) {
  const { tr } = useI18n();
  if (events.length === 0) return null;
  return (
    <ol className="rounded-lg border border-hairline bg-sheet">
      <li className="border-b border-hairline px-5 py-3 text-base font-semibold text-deed">{tr("Audit trail", "Registro de auditoría")}</li>
      {events.map((e, i) => (
        <li key={i} className="grid grid-cols-[5.5rem_9rem_1fr] gap-3 border-b border-hairline px-5 py-2 text-sm last:border-b-0">
          <span className="tabular text-graphite">{fmtTime(e.ts)}</span>
          <span className="font-medium text-deed">{e.event.replace(/_/g, " ")}</span>
          <span className="text-graphite">{e.detail}</span>
        </li>
      ))}
    </ol>
  );
}
