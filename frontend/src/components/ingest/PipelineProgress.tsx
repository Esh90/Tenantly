import { CircleCheck, CircleDashed, CircleX, Loader2 } from "lucide-react";
import type { IngestJob } from "@/lib/api/types";
import { STAGE_GROUPS, STAGE_LABEL } from "@/lib/ingest";
import { useI18n } from "@/lib/i18n";

/** Live pipeline. A row turns green only when the backend reports that stage as done. */
export function PipelineProgress({ stages }: { stages: IngestJob["stages"] }) {
  const { tr } = useI18n();
  const byId = new Map(stages.map((s) => [s.stage, s]));
  let n = 0;
  return (
    <ol aria-live="polite" className="space-y-6">
      {STAGE_GROUPS.map((g) => (
        <li key={g.title[0]}>
          <p className="text-xs font-semibold uppercase tracking-wider text-graphite">{tr(...g.title)}</p>
          <ul className="mt-2 border-t border-hairline">
            {g.stages.map((id) => {
              const s = byId.get(id);
              n += 1;
              const status = s?.status ?? "pending";
              return (
                <li key={id} className="grid grid-cols-[1.5rem_1.5rem_1fr_auto] items-start gap-2 border-b border-hairline py-2.5">
                  <span className="text-sm tabular text-graphite">{n}</span>
                  {status === "done" ? (
                    <CircleCheck className="size-5 text-applies" aria-label="done" />
                  ) : status === "running" ? (
                    <Loader2 className="size-5 animate-spin text-permit" aria-label="running" />
                  ) : status === "failed" ? (
                    <CircleX className="size-5 text-destructive" aria-label="failed" />
                  ) : (
                    <CircleDashed className="size-5 text-hairline" aria-label="waiting" />
                  )}
                  <span>
                    <span className={`block text-base ${status === "pending" ? "text-graphite" : "text-deed"}`}>{tr(...(STAGE_LABEL[id] ?? [id, id]))}</span>
                    {s?.detail && status !== "pending" && <span className="block text-sm text-graphite">{s.detail}</span>}
                  </span>
                  <span className="text-xs tabular text-graphite">{s?.ms ? `${s.ms} ms` : ""}</span>
                </li>
              );
            })}
          </ul>
        </li>
      ))}
    </ol>
  );
}
