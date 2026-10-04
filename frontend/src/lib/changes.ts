import type { ChangeEvent } from "@/lib/api/types";
import { fmtDate } from "@/lib/format";

export function compareText(c: ChangeEvent, lang: "en" | "es", tr: (a: string, b: string) => string) {
  const cmp = c.compare;
  if ("mode" in cmp) return `${tr("With and without, on", "Con y sin, el")} ${fmtDate(cmp.on, lang, "short")}`;
  if ("before" in cmp) return `${fmtDate(cmp.before, lang, "short")} → ${fmtDate(cmp.after, lang, "short")}`;
  return `${tr("On", "El")} ${fmtDate(cmp.on, lang, "short")}`;
}
export function kindText(k: ChangeEvent["kind"], tr: (a: string, b: string) => string) {
  return k === "test" ? tr("Test", "Prueba") : k === "ingest" ? tr("New law", "Nueva ley") : tr("Watch", "Seguimiento");
}
export function typeText(t: ChangeEvent["test_type"], tr: (a: string, b: string) => string) {
  const m: Record<ChangeEvent["test_type"], [string, string]> = {
    as_of: ["Date change", "Cambio de fecha"], boundary: ["Boundary", "Límite"], pending: ["Pending bill", "Proyecto pendiente"],
    negative: ["Nothing should change", "Nada debe cambiar"], with_without: ["With and without", "Con y sin"],
  };
  return tr(...m[t]);
}

