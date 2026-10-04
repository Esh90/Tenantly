import { CalendarClock, CircleCheck, CircleHelp, CircleSlash, CornerDownRight, FilePen } from "lucide-react";
import type { Result } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Kind = Result | "none";

export const RESULT_META: Record<Kind, { icon: typeof CircleCheck; en: string; es: string; pill: string; rail: string }> = {
  applies: { icon: CircleCheck, en: "Applies", es: "Aplica", pill: "text-applies bg-applies-bg border-applies-border", rail: "border-l-applies" },
  unknown: { icon: CircleHelp, en: "Can't tell yet", es: "Aún no se sabe", pill: "text-unknown bg-unknown-bg border-unknown-border", rail: "border-l-unknown" },
  superseded: { icon: CornerDownRight, en: "Overridden here", es: "Reemplazada aquí", pill: "text-superseded bg-superseded-bg border-superseded-border", rail: "border-l-superseded" },
  not_yet_effective: { icon: CalendarClock, en: "Not in effect yet", es: "Aún no entra en vigor", pill: "text-notyet bg-notyet-bg border-notyet-border", rail: "border-l-notyet" },
  pending: { icon: FilePen, en: "Proposed, not law", es: "Propuesta, no es ley", pill: "text-pending bg-pending-bg border-pending-border", rail: "border-l-pending" },
  none: { icon: CircleSlash, en: "No rule here", es: "No hay regla aquí", pill: "text-superseded bg-transparent border-dashed border-superseded-border", rail: "border-l-superseded" },
};

export function ResultPill({ result, className }: { result: Kind; className?: string }) {
  const { lang } = useI18n();
  const m = RESULT_META[result];
  const Icon = m.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-sm font-medium whitespace-nowrap",
        m.pill,
        className,
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
      {lang === "es" ? m.es : m.en}
    </span>
  );
}
