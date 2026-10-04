import { ArrowDown, Landmark } from "lucide-react";
import type { Hierarchy } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const LEVEL_NAME = {
  state: ["STATE LAW", "LEY ESTATAL"],
  county: ["COUNTY LAW", "LEY DEL CONDADO"],
  city: ["CITY ORDINANCE", "ORDENANZA MUNICIPAL"],
} as const;

const EFFECT_TONE: Record<string, string> = {
  bar: "border-destructive/40 bg-destructive/5",
  supersede: "border-superseded-border bg-superseded-bg",
  conflict_flag: "border-unknown-border bg-unknown-bg",
};

/** State, county, city with priority numbers, and the precedence relations the engine evaluated. */
export function HierarchyView({ h }: { h: Hierarchy }) {
  const { tr, tb } = useI18n();
  return (
    <div className="grid gap-8 lg:grid-cols-12">
      <ol className="lg:col-span-6">
        {h.levels.map((lvl, i) => (
          <li key={lvl.id}>
            <div className={cn("rounded-lg border bg-sheet p-4", lvl.rules.some((r) => r.new) ? "border-permit" : "border-hairline")}>
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs font-semibold tracking-wider text-graphite">{tr(LEVEL_NAME[lvl.level][0], LEVEL_NAME[lvl.level][1])}</p>
                <span className="rounded-full bg-deed px-2.5 py-0.5 text-xs font-semibold text-primary-foreground">{tr("Priority", "Prioridad")} {lvl.priority}</span>
              </div>
              <p className="mt-1 flex items-center gap-2 text-lg text-deed"><Landmark className="size-5 text-graphite" aria-hidden="true" />{lvl.label}</p>
              {lvl.rules.length === 0 ? (
                <p className="mt-2 text-sm text-graphite">{tr("No rules in the affected categories at this level.", "Sin reglas en las categorías afectadas en este nivel.")}</p>
              ) : (
                <ul className="mt-3 space-y-1.5">
                  {lvl.rules.map((r) => (
                    <li key={r.rule_id} className="flex flex-wrap items-baseline gap-2 text-base text-deed">
                      <span className={cn("rounded px-1.5 text-sm tabular", r.new ? "bg-highlighter text-highlighter-ink" : "bg-survey")}>{r.rule_id}</span>
                      <span>{r.title}</span>
                      {r.new && <span className="text-xs font-semibold text-permit">{tr("NEW", "NUEVA")}</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
            {i < h.levels.length - 1 && (
              <div className="flex justify-center py-1.5 text-graphite" aria-hidden="true"><ArrowDown className="size-5" /></div>
            )}
          </li>
        ))}
      </ol>
      <div className="space-y-3 lg:col-span-6">
        <h3 className="text-base font-semibold text-deed">{tr("How precedence is resolved", "Cómo se resuelve la precedencia")}</h3>
        {h.relations.map((r) => (
          <div key={r.from + r.to + r.effect} className={cn("rounded-lg border p-4", EFFECT_TONE[r.effect] ?? "border-hairline")}>
            <p className="text-sm font-semibold tabular text-graphite">{r.from} → {r.to} · {r.effect.replace("_", " ")}</p>
            <p className="mt-1 text-base text-deed">{tb(r.explanation)}</p>
          </div>
        ))}
        {h.notes.map((n, i) => (
          <p key={i} className="rounded-lg border border-hairline bg-sheet p-4 text-base text-graphite">{tb(n)}</p>
        ))}
      </div>
    </div>
  );
}
