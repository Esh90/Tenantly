import { useMemo, useState } from "react";
import type { GraphEdge, GraphNode, GraphNodeType, KnowledgeGraph } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const W = 178;
const H = 36;
const COL_X = [24, 250, 476, 702];
const TYPE_LABEL: Record<GraphNodeType, [string, string]> = {
  document: ["Document", "Documento"],
  jurisdiction: ["Jurisdiction", "Jurisdicción"],
  rule: ["Rule", "Regla"],
  condition: ["Property condition", "Condición del inmueble"],
  date: ["Effective date", "Fecha de vigencia"],
  exemption: ["Exemption", "Exención"],
};
const TYPE_FILL: Record<GraphNodeType, string> = {
  document: "fill-pending-bg stroke-pending",
  jurisdiction: "fill-sage-tint stroke-sage",
  rule: "fill-applies-bg stroke-applies",
  condition: "fill-survey stroke-graphite",
  date: "fill-notyet-bg stroke-notyet",
  exemption: "fill-unknown-bg stroke-unknown",
};
const EDGE_TONE: Record<string, string> = {
  OVERRIDES: "stroke-superseded", PREEMPTS: "stroke-destructive", SUPERSEDES: "stroke-destructive",
  EXEMPTS: "stroke-unknown", APPLIES_TO: "stroke-applies", EFFECTIVE_ON: "stroke-notyet",
  REQUIRES: "stroke-graphite", DERIVED_FROM: "stroke-pending", WITHIN: "stroke-sage",
};

function column(n: GraphNode): number {
  if (n.type === "document") return 0;
  if (n.type === "rule") return n.status === "new" ? 1 : 3;
  return 2;
}

/** Built only from the nodes and edges the pipeline returned. Click a node to inspect it. */
export function KnowledgeGraphView({ graph }: { graph: KnowledgeGraph }) {
  const { tr } = useI18n();
  const [sel, setSel] = useState<string | null>(null);
  const layout = useMemo(() => {
    const cols: GraphNode[][] = [[], [], [], []];
    graph.nodes.forEach((n) => cols[column(n)]!.push(n));
    const tallest = Math.max(...cols.map((c) => c.length), 1);
    const height = Math.max(tallest * 58 + 40, 260);
    const pos = new Map<string, { x: number; y: number }>();
    cols.forEach((c, ci) => c.forEach((n, i) => pos.set(n.id, { x: COL_X[ci]!, y: 20 + (i + 0.5) * ((height - 40) / c.length) - H / 2 })));
    return { pos, height };
  }, [graph]);
  const selected = graph.nodes.find((n) => n.id === sel) ?? null;
  const touching = (e: GraphEdge) => sel !== null && (e.source === sel || e.target === sel);
  const legend = (Object.keys(TYPE_LABEL) as GraphNodeType[]).filter((t) => graph.nodes.some((n) => n.type === t));
  return (
    <div className="grid gap-6 lg:grid-cols-12">
      <div className="overflow-x-auto rounded-lg border border-hairline bg-sheet lg:col-span-8">
        <svg viewBox={`0 0 ${COL_X[3]! + W + 24} ${layout.height}`} role="img" aria-label={tr("Knowledge graph of the new document", "Grafo de conocimiento del nuevo documento")} className="min-w-[760px]">
          <defs>
            <marker id="kg-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L8 4 L0 8 z" className="fill-graphite" />
            </marker>
          </defs>
          {graph.edges.map((e) => {
            const a = layout.pos.get(e.source);
            const b = layout.pos.get(e.target);
            if (!a || !b) return null;
            const forward = a.x <= b.x;
            const x1 = forward ? a.x + W : a.x;
            const x2 = forward ? b.x : b.x + W;
            const y1 = a.y + H / 2;
            const y2 = b.y + H / 2;
            const dx = Math.max(40, Math.abs(x2 - x1) / 2) * (forward ? 1 : -1);
            const active = touching(e);
            return (
              <g key={e.id} opacity={sel && !active ? 0.15 : 1}>
                <path d={`M${x1},${y1} C${x1 + dx},${y1} ${x2 - dx},${y2} ${x2},${y2}`} fill="none" strokeWidth={active ? 2.4 : 1.4} className={cn(EDGE_TONE[e.type] ?? "stroke-graphite")} markerEnd="url(#kg-arrow)" />
                <text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 4} textAnchor="middle" className="fill-graphite text-[10px] font-semibold">{e.type}</text>
              </g>
            );
          })}
          {graph.nodes.map((n) => {
            const p = layout.pos.get(n.id)!;
            const dim = sel !== null && n.id !== sel && !graph.edges.some((e) => touching(e) && (e.source === n.id || e.target === n.id));
            return (
              <g key={n.id} transform={`translate(${p.x},${p.y})`} opacity={dim ? 0.25 : 1} tabIndex={0} role="button" aria-label={`${n.type} ${n.label}`}
                 onClick={() => setSel(sel === n.id ? null : n.id)} onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && setSel(sel === n.id ? null : n.id)} className="cursor-pointer outline-none focus-visible:opacity-100">
                <rect width={W} height={H} rx={8} strokeWidth={n.id === sel ? 3 : 1.5} strokeDasharray={n.status === "existing" ? "5 3" : undefined} className={TYPE_FILL[n.type]} />
                <text x={10} y={H / 2 + 4} className="fill-deed text-[12px] font-medium">{n.label.length > 24 ? `${n.label.slice(0, 23)}…` : n.label}</text>
              </g>
            );
          })}
        </svg>
        <div className="flex flex-wrap gap-x-4 gap-y-1 border-t border-hairline px-4 py-2 text-xs text-graphite">
          {legend.map((t) => <span key={t} className="flex items-center gap-1.5"><span className={cn("inline-block size-3 rounded-sm border", TYPE_FILL[t].replace("fill-", "bg-").replace("stroke-", "border-"))} />{tr(...TYPE_LABEL[t])}</span>)}
          <span>{tr("Dashed outline: already in the live law set", "Contorno punteado: ya en la ley vigente")}</span>
        </div>
      </div>
      <aside className="lg:col-span-4">
        {selected ? (
          <div className="rounded-lg border border-hairline bg-sheet p-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-graphite">{tr(...TYPE_LABEL[selected.type])} · {selected.status === "new" ? tr("new", "nuevo") : tr("existing", "existente")}</p>
            <h3 className="mt-1 text-lg text-deed">{selected.label}</h3>
            <dl className="mt-3 space-y-2 text-sm">
              {Object.entries(selected.detail).filter(([, v]) => v !== null && v !== "").map(([k, v]) => (
                <div key={k}><dt className="text-graphite">{k.replace(/_/g, " ")}</dt><dd className="break-words text-deed">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></div>
              ))}
            </dl>
            <p className="mt-4 text-sm font-semibold text-deed">{tr("Relationships", "Relaciones")}</p>
            <ul className="mt-1 space-y-1 text-sm text-deed">
              {graph.edges.filter((e) => e.source === selected.id || e.target === selected.id).map((e) => {
                const other = graph.nodes.find((n) => n.id === (e.source === selected.id ? e.target : e.source));
                return <li key={e.id}>{e.source === selected.id ? `${e.type} →` : `← ${e.type}`} <button type="button" className="underline decoration-hairline underline-offset-2" onClick={() => setSel(other?.id ?? null)}>{other?.label}</button></li>;
              })}
            </ul>
          </div>
        ) : (
          <div className="rounded-lg border border-dashed border-hairline p-4 text-base text-graphite">
            <p>{tr("Select a node to see its details and relationships.", "Seleccione un nodo para ver sus detalles y relaciones.")}</p>
            <p className="mt-2 text-sm">{graph.nodes.filter((n) => n.status === "new").length} {tr("new nodes", "nodos nuevos")} · {graph.edges.length} {tr("relationships", "relaciones")}</p>
          </div>
        )}
      </aside>
    </div>
  );
}
