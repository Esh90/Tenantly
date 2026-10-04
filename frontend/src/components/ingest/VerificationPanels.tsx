import { CircleAlert, CircleCheck, CircleX, ShieldCheck, TriangleAlert } from "lucide-react";
import type { IngestCheck, IngestJudge, IngestPolicy, IngestValidation } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

function StatusIcon({ status }: { status: IngestCheck["status"] }) {
  if (status === "pass") return <CircleCheck className="mt-0.5 size-5 shrink-0 text-applies" aria-label="pass" />;
  if (status === "warn") return <TriangleAlert className="mt-0.5 size-5 shrink-0 text-unknown" aria-label="warning" />;
  return <CircleX className="mt-0.5 size-5 shrink-0 text-destructive" aria-label="fail" />;
}

export function ValidationPanel({ v }: { v: IngestValidation }) {
  const { tr } = useI18n();
  return (
    <div className="rounded-lg border border-hairline bg-sheet">
      <div className="flex items-center justify-between border-b border-hairline px-5 py-3">
        <h3 className="flex items-center gap-2 text-base font-semibold text-deed"><ShieldCheck className="size-5" aria-hidden="true" />{tr("VALIDATION", "VALIDACIÓN")}</h3>
        <span className={cn("rounded-full border px-2.5 py-0.5 text-sm font-medium", v.passed ? "border-applies-border bg-applies-bg text-applies" : "border-destructive/40 bg-destructive/5 text-destructive")}>
          {v.passed ? tr("All gates passed", "Todas las pruebas superadas") : tr("Validation failed", "La validación falló")}
        </span>
      </div>
      <ul className="divide-y divide-hairline">
        {v.checks.map((c) => (
          <li key={c.id} className="flex gap-3 px-5 py-3">
            <StatusIcon status={c.status} />
            <div>
              <p className="text-base text-deed">{c.label}</p>
              <p className={cn("text-sm", c.status === "pass" ? "text-graphite" : c.status === "warn" ? "text-unknown" : "text-destructive")}>{c.detail}</p>
              {c.status !== "pass" && (c.items?.length ?? 0) > 1 && (
                <ul className="mt-1 list-disc pl-5 text-sm text-graphite">{c.items!.slice(1, 6).map((it) => <li key={it}>{it}</li>)}</ul>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

const VERDICT = {
  pass: { en: "PASS", es: "APROBADO", icon: CircleCheck, tone: "border-applies-border bg-applies-bg text-applies" },
  review: { en: "REVIEW REQUIRED", es: "REVISIÓN REQUERIDA", icon: CircleAlert, tone: "border-unknown-border bg-unknown-bg text-unknown" },
  fail: { en: "FAIL", es: "RECHAZADO", icon: CircleX, tone: "border-destructive/40 bg-destructive/5 text-destructive" },
} as const;

export function JudgePanel({ j, policy }: { j: IngestJudge; policy?: IngestPolicy | null | undefined }) {
  const { tr } = useI18n();
  const m = VERDICT[j.verdict];
  const Icon = m.icon;
  return (
    <div className="rounded-lg border border-hairline bg-sheet">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline px-5 py-3">
        <h3 className="text-base font-semibold text-deed">{tr("AUTONOMOUS JUDGE", "JUEZ AUTÓNOMO")}</h3>
        <span className="text-sm text-graphite">{tr("Independent review against the source text", "Revisión independiente contra el texto de origen")}{j.model ? ` · ${j.model}` : ""}{j.rerun ? ` · ${tr("review", "revisión")} #${j.rerun + 1}` : ""}</span>
      </div>
      <div className="grid gap-6 px-5 py-5 md:grid-cols-12">
        <div className="md:col-span-4">
          <p className={cn("inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-lg font-semibold", m.tone)}><Icon className="size-6" aria-hidden="true" />{tr(m.en, m.es)}</p>
          <p className="mt-4 text-sm text-graphite">{tr("Confidence reported by the Judge", "Confianza informada por el Juez")}</p>
          <p className="text-3xl font-semibold tabular text-deed">{(j.confidence * 100).toFixed(0)}%</p>
          {policy && (
            <div className="mt-4 rounded-md border border-hairline bg-survey p-3 text-sm text-deed">
              <p className="font-semibold">{tr("Publication policy", "Política de publicación")}</p>
              <p className="mt-1">{tr("Auto-publish needs a pass, validation, no conflicts and confidence of at least", "La publicación automática requiere aprobación, validación, sin conflictos y una confianza de al menos")} {(policy.min_confidence * 100).toFixed(0)}%.</p>
              {policy.reasons.length > 0 && <ul className="mt-2 list-disc pl-4 text-unknown">{policy.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            </div>
          )}
        </div>
        <div className="md:col-span-8">
          <ul className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
            {j.checks.map((c) => (
              <li key={c.id} className="flex gap-2">
                <StatusIcon status={c.status} />
                <span>
                  <span className="block text-base text-deed">{c.label}</span>
                  {c.note && <span className="block text-sm text-graphite">{c.note}</span>}
                </span>
              </li>
            ))}
          </ul>
          {j.issues.length > 0 && (
            <>
              <p className="mt-5 text-sm font-semibold text-deed">{tr("Issues", "Problemas")}</p>
              <ul className="mt-1 space-y-1.5">
                {j.issues.map((i, idx) => (
                  <li key={idx} className="flex gap-2 text-base text-deed">
                    <span className={cn("mt-1 inline-block size-2 shrink-0 rounded-full", i.severity === "error" ? "bg-destructive" : i.severity === "warning" ? "bg-unknown" : "bg-graphite")} aria-label={i.severity} />
                    <span>{i.rule_id && <strong className="tabular">{i.rule_id}: </strong>}{i.message}{i.source_section ? <span className="text-graphite"> ({tr("section", "sección")} {i.source_section})</span> : null}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
