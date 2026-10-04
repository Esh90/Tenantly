import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { IngestJob } from "@/lib/api/types";
import { locateQuote } from "@/lib/ingest";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type Props = {
  job: IngestJob;
  focusRule: string | null;
  busy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onRejudge: () => void;
  onSaveEdit: (rules: Record<string, unknown>[]) => void;
};

/** Original text on the left with every extracted quote highlighted; the extraction on the right. */
export function ReviewScreen({ job, focusRule, busy, onApprove, onReject, onRejudge, onSaveEdit }: Props) {
  const { tr } = useI18n();
  const res = job.result!;
  const text = res.source?.text ?? "";
  const rules = res.rules_json ?? [];
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [err, setErr] = useState("");
  const markRef = useRef<HTMLElement | null>(null);

  useEffect(() => setDraft(JSON.stringify(rules, null, 2)), [res.rules_json]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }), [focusRule]);

  const segments = useMemo(() => {
    const spans = rules
      .map((r) => {
        const q = (r as { citation?: { quote?: string } }).citation?.quote ?? "";
        const at = locateQuote(text, q);
        return at ? { start: at[0], end: at[1], id: (r as { rule_id: string }).rule_id } : null;
      })
      .filter((x): x is { start: number; end: number; id: string } => x !== null)
      .sort((a, b) => a.start - b.start);
    const out: { text: string; id?: string }[] = [];
    let pos = 0;
    for (const s of spans) {
      if (s.start < pos) continue;
      if (s.start > pos) out.push({ text: text.slice(pos, s.start) });
      out.push({ text: text.slice(s.start, s.end), id: s.id });
      pos = s.end;
    }
    out.push({ text: text.slice(pos) });
    return out;
  }, [text, rules]);

  const save = () => {
    try {
      const parsed = JSON.parse(draft) as unknown;
      if (!Array.isArray(parsed)) throw new Error("not a list");
      setErr("");
      onSaveEdit(parsed as Record<string, unknown>[]);
      setEditing(false);
    } catch {
      setErr(tr("That is not valid JSON for a list of rules.", "Eso no es un JSON válido para una lista de reglas."));
    }
  };

  const review = job.status === "review_required";
  return (
    <section aria-label={tr("Human review", "Revisión humana")} className={cn("rounded-lg border bg-sheet", review ? "border-unknown-border" : "border-hairline")}>
      <header className="border-b border-hairline px-5 py-4">
        <h3 className="text-lg font-semibold text-deed">{review ? tr("REVIEW REQUIRED", "REVISIÓN REQUERIDA") : tr("Review the extraction", "Revise la extracción")}</h3>
        <p className="mt-1 text-base text-graphite">
          {res.source?.title} · {tr("Judge confidence", "Confianza del Juez")} {res.judge ? `${(res.judge.confidence * 100).toFixed(0)}%` : tr("not run yet", "aún sin ejecutar")}
        </p>
        {res.judge && res.judge.issues.length > 0 && (
          <ul className="mt-3 space-y-1">{res.judge.issues.slice(0, 4).map((i, k) => <li key={k} className="text-base text-unknown">⚠ {i.message}</li>)}</ul>
        )}
      </header>
      <div className="grid gap-0 lg:grid-cols-2 lg:divide-x lg:divide-hairline">
        <div className="p-5">
          <p className="text-sm font-semibold text-graphite">{tr("ORIGINAL LEGAL TEXT", "TEXTO LEGAL ORIGINAL")}</p>
          <div tabIndex={0} className="mt-2 max-h-[460px] overflow-auto whitespace-pre-wrap rounded-md border border-hairline bg-survey p-4 text-[15px] leading-relaxed text-deed">
            {segments.map((s, i) =>
              s.id ? (
                <mark key={i} ref={s.id === focusRule ? markRef : undefined} className={cn("mark-highlight rounded-sm", s.id === focusRule && "ring-2 ring-permit")} title={s.id}>{s.text}</mark>
              ) : (
                <span key={i}>{s.text}</span>
              ),
            )}
          </div>
        </div>
        <div className="p-5">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-graphite">{tr("EXTRACTED RULES (JSON)", "REGLAS EXTRAÍDAS (JSON)")}</p>
            <button type="button" className="text-sm text-permit underline underline-offset-2" onClick={() => setEditing(!editing)}>{editing ? tr("Stop editing", "Dejar de editar") : tr("Edit extraction", "Editar extracción")}</button>
          </div>
          {editing ? (
            <>
              <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} className="mt-2 h-[460px] font-mono text-[13px]" spellCheck={false} aria-label="Extracted rules JSON" />
              {err && <p role="alert" className="mt-2 text-sm text-destructive">{err}</p>}
              <Button type="button" className="mt-3" onClick={save} disabled={busy}>{tr("Save and re-validate", "Guardar y revalidar")}</Button>
            </>
          ) : (
            <pre tabIndex={0} className="mt-2 max-h-[460px] overflow-auto rounded-md border border-hairline bg-survey p-4 text-[13px] leading-relaxed text-deed">{JSON.stringify(rules, null, 2)}</pre>
          )}
        </div>
      </div>
      <footer className="flex flex-wrap gap-2 border-t border-hairline px-5 py-4">
        <Button type="button" size="lg" onClick={onApprove} disabled={busy || job.status === "published" || !res.validation?.passed}>{tr("Approve & Publish", "Aprobar y publicar")}</Button>
        <Button type="button" size="lg" variant="outline" onClick={onReject} disabled={busy || job.status === "published"}>{tr("Reject", "Rechazar")}</Button>
        <Button type="button" size="lg" variant="outline" onClick={onRejudge} disabled={busy || job.status === "published"}>{tr("Run Judge Again", "Ejecutar el Juez otra vez")}</Button>
        {!res.validation?.passed && <p className="self-center text-sm text-destructive">{tr("Publishing is blocked until validation passes. Edit the extraction to fix it.", "La publicación está bloqueada hasta que la validación pase. Edite la extracción para corregirla.")}</p>}
      </footer>
    </section>
  );
}
