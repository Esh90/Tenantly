import { useCallback, useEffect, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { toast } from "sonner";
import { Page, PageHeader, SectionTitle } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { PipelineProgress } from "@/components/ingest/PipelineProgress";
import { RuleCards } from "@/components/ingest/RuleCards";
import { JsonViewer } from "@/components/ingest/JsonViewer";
import { HierarchyView } from "@/components/ingest/HierarchyView";
import { KnowledgeGraphView } from "@/components/ingest/KnowledgeGraphView";
import { JudgePanel, ValidationPanel } from "@/components/ingest/VerificationPanels";
import { ReviewScreen } from "@/components/ingest/ReviewScreen";
import { AuditTrail, ChangeSummaryPanel } from "@/components/ingest/ChangeSummaryPanel";
import { AUTO, LIMIT, UploadPanel, type UploadValues } from "@/components/ingest/UploadPanel";
import { getIngest, streamIngest } from "@/lib/api/api";
import { useEditIngest, useExtractText, useMeta, usePublishIngest, useRejectIngest, useRejudgeIngest, useStartIngest } from "@/lib/api/hooks";
import { ApiError } from "@/lib/api/errors";
import type { IngestJob } from "@/lib/api/types";
import { STATE_META } from "@/lib/ingest";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/ingest")({
  head: () => ({
    meta: [
      { title: "Law Ingestion — Tenantly" },
      { name: "description", content: "Add a new law and watch it be extracted, verified by an independent judge, staged, and published into the live law engine." },
      { property: "og:title", content: "Law Ingestion — Tenantly" },
      { property: "og:description", content: "A transparent AI legal-data pipeline: upload, extract, validate, judge, review, publish." },
    ],
  }),
  component: IngestPage,
});

const TERMINAL = new Set(["ready", "review_required", "published", "rejected", "failed"]);

function errText(err: unknown, tr: (en: string, es: string) => string): string {
  if (err instanceof ApiError) {
    if (err.status === 401) return tr("That admin token isn't valid.", "Ese token de administrador no es válido.");
    if (err.status === 413) return tr("This text is too long (limit 200,000 characters).", "Este texto es demasiado largo (límite 200,000 caracteres).");
    if (err.status === 503 && err.code.toUpperCase() === "BUDGET_EXCEEDED") return tr("The extraction budget is used up.", "Se agotó el presupuesto de extracción.");
    return err.message;
  }
  return tr("Something went wrong.", "Algo salió mal.");
}

function IngestPage() {
  const { tr } = useI18n();
  const meta = useMeta();
  const start = useStartIngest();
  const publish = usePublishIngest();
  const reject = useRejectIngest();
  const rejudge = useRejudgeIngest();
  const edit = useEditIngest();
  const extractText = useExtractText();
  const [values, setValues] = useState<UploadValues>({ token: "", title: "", jurisdiction: AUTO, url: "", text: "", format: "text", autoPublish: false });
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<IngestJob | null>(null);
  const [error, setError] = useState("");
  const [reading, setReading] = useState(false);
  const [focusRule, setFocusRule] = useState<string | null>(null);
  const unsub = useRef<null | (() => void)>(null);
  const poll = useRef<null | ReturnType<typeof setInterval>>(null);
  const reviewRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setValues((v) => ({ ...v, token: window.sessionStorage.getItem("tenantly.admin") ?? "" }));
    return () => {
      unsub.current?.();
      if (poll.current) clearInterval(poll.current);
    };
  }, []);

  const refresh = useCallback(async (id: string) => {
    try {
      const j = await getIngest(id);
      setJob(j);
      if (TERMINAL.has(j.status) && poll.current) {
        clearInterval(poll.current);
        poll.current = null;
      }
      return j;
    } catch {
      return null;
    }
  }, []);

  const running = job?.status === "running" || (start.isPending && !job);

  const run = async () => {
    setError("");
    const t = values.text.trim();
    if (!values.token) return setError(tr("Enter the admin token.", "Escriba el token de administrador."));
    if (t.length < 40) return setError(tr("Upload a file or paste the full text of the law.", "Suba un archivo o pegue el texto completo de la ley."));
    if (t.length > LIMIT) return setError(tr("This text is longer than 200,000 characters.", "Este texto supera los 200,000 caracteres."));
    window.sessionStorage.setItem("tenantly.admin", values.token);
    unsub.current?.();
    setJob(null);
    try {
      const r = await start.mutateAsync({
        body: {
          title: values.title.trim() || t.split("\n")[0]!.slice(0, 80),
          text: t,
          jurisdiction_hint: values.jurisdiction === AUTO ? "" : values.jurisdiction,
          source_url: values.url,
          retrieved_at: new Date().toISOString(),
          auto_publish: values.autoPublish,
          format: values.format,
        },
        token: values.token,
      });
      setJobId(r.job_id);
      await refresh(r.job_id);
      // the backend reports each stage as it truly finishes; every event refetches the job
      unsub.current = streamIngest(r.job_id, (ev) => {
        void refresh(r.job_id);
        if (ev.type === "error") setError((ev.data as { message?: string })?.message ?? tr("Analysis failed.", "El análisis falló."));
      });
      // plain polling covers proxies that buffer event streams
      if (poll.current) clearInterval(poll.current);
      poll.current = setInterval(() => void refresh(r.job_id), 1500);
    } catch (err) {
      setError(errText(err, tr));
    }
  };

  const readFile = async (file: File) => {
    setError("");
    setReading(true);
    try {
      const lower = file.name.toLowerCase();
      if (lower.endsWith(".txt") || lower.endsWith(".md") || file.type === "text/plain") {
        const text = await file.text();
        setValues((v) => ({ ...v, text, format: "text", title: v.title || file.name.replace(/\.[^.]+$/, "") }));
      } else {
        if (!values.token) throw new Error(tr("Enter the admin token to read PDF and DOCX files.", "Escriba el token para leer archivos PDF y DOCX."));
        const r = await extractText.mutateAsync({ file, token: values.token });
        setValues((v) => ({ ...v, text: r.text, format: r.format, title: v.title || file.name.replace(/\.[^.]+$/, "") }));
        toast.success(tr(`Read ${r.chars.toLocaleString()} characters${r.pages ? ` from ${r.pages} pages` : ""}`, `Se leyeron ${r.chars.toLocaleString()} caracteres`));
      }
    } catch (err) {
      setError(err instanceof Error && !(err instanceof ApiError) ? err.message : errText(err, tr));
    } finally {
      setReading(false);
    }
  };

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    if (!jobId) return;
    try {
      await fn();
      await refresh(jobId);
      toast.success(ok);
    } catch (err) {
      toast.error(errText(err, tr));
    }
  };

  const res = job?.result ?? null;
  const state = job?.state ?? null;
  const goto = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  const viewSource = (ruleId: string) => {
    setFocusRule(ruleId);
    reviewRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const canPublish = job?.status === "ready" && !!jobId;

  return (
    <Page>
      <PageHeader
        title={tr("Law Ingestion", "Ingesta de leyes")}
        lede={tr(
          "Add a new law and watch it become part of the live system: extracted by AI, checked against the source, verified by an independent judge, staged, and only then published.",
          "Agregue una nueva ley y vea cómo pasa a formar parte del sistema: extraída con IA, verificada contra la fuente, revisada por un juez independiente, preparada y solo entonces publicada.",
        )}
      />

      <div className="mt-8">
        {!job ? (
          <UploadPanel values={values} onChange={setValues} jurisdictions={meta.data?.jurisdictions ?? []} error={error} running={!!running} reading={reading} onReadFile={readFile} onSubmit={() => void run()} />
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-hairline bg-sheet px-5 py-4">
            <div className="min-w-0 flex-1">
              <p className="truncate text-lg text-deed">{res?.source?.title ?? job.job_id}</p>
              <p className="text-sm text-graphite">
                {res?.source ? `${res.source.chars.toLocaleString()} ${tr("characters", "caracteres")} · ${res.source.jurisdiction.label}` : ""}
                {res?.inferred ? ` · ${res.inferred.jurisdiction_method === "inferred" ? tr("jurisdiction detected from the text", "jurisdicción detectada del texto") : tr("jurisdiction chosen by you", "jurisdicción elegida por usted")}` : ""}
              </p>
            </div>
            {state && <span className={cn("rounded-full border px-3 py-1 text-sm font-semibold tracking-wide", STATE_META[state].tone)}>{tr(STATE_META[state].en, STATE_META[state].es)}</span>}
            <Button type="button" variant="outline" onClick={() => { unsub.current?.(); setJob(null); setJobId(null); setError(""); }}>{tr("Analyze another law", "Analizar otra ley")}</Button>
          </div>
        )}
      </div>

      {job && (
        <div className="mt-10 grid gap-10 lg:grid-cols-12">
          <aside className="lg:col-span-4">
            <div className="lg:sticky lg:top-24">
              <h2 className="mb-4 text-lg font-semibold text-deed">{tr("LAW INGESTION PIPELINE", "PIPELINE DE INGESTA")}</h2>
              <PipelineProgress stages={job.stages} />
              {job.error && <p role="alert" className="mt-4 rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-base text-destructive">{job.error.message}</p>}
              {res && <p className="mt-4 text-xs text-graphite">{tr("Model spend for this document", "Gasto de modelo en este documento")}: ${res.cost_usd.toFixed(3)}{res.cache_hit ? ` (${tr("replayed from cache", "repetido desde caché")})` : ""}</p>}
            </div>
          </aside>

          <div className="space-y-14 lg:col-span-8">
            {res?.changes && <ChangeSummaryPanel c={res.changes} res={res} onSection={goto} />}

            {canPublish && (
              <div className="flex flex-wrap items-center gap-4 rounded-lg border border-applies-border bg-applies-bg px-5 py-4">
                <p className="flex-1 text-base text-deed"><strong>{tr("VERIFIED.", "VERIFICADA.")}</strong> {tr("Validation and the Judge passed. The rules are staged and not yet live.", "La validación y el Juez aprobaron. Las reglas están preparadas pero aún no vigentes.")}</p>
                <Button size="lg" disabled={publish.isPending} onClick={() => void act(() => publish.mutateAsync({ jobId: jobId!, token: values.token }), tr("Published to the live law engine", "Publicada en el motor de leyes"))}>{tr("Publish to live law", "Publicar en la ley vigente")}</Button>
              </div>
            )}

            {res && res.rules.length > 0 && (
              <section id="ing-rules">
                <SectionTitle title={tr(`Extracted ${res.rules.length} ${res.rules.length === 1 ? "rule" : "rules"}`, `Se extrajeron ${res.rules.length} regla(s)`)} sub={res.verification ? tr(`${res.verification.quotes_verified} of ${res.verification.quotes_checked} candidate quotes were found byte for byte in the document.`, `${res.verification.quotes_verified} de ${res.verification.quotes_checked} citas candidatas se hallaron literalmente en el documento.`) : undefined} />
                <div className="pt-6"><RuleCards res={res} onViewSource={viewSource} /></div>
              </section>
            )}

            {res?.rules_json && (
              <section id="ing-json">
                <SectionTitle title={tr("Extracted JSON", "JSON extraído")} sub={tr("Generated by the pipeline, in the canonical format the law engine uses. Nothing here is hand-written.", "Generado por el pipeline, en el formato canónico del motor. Nada está escrito a mano.")} />
                <div className="space-y-3 pt-6">
                  <JsonViewer title={tr("Canonical rules (engine format)", "Reglas canónicas (formato del motor)")} value={res.rules_json} />
                  {res.submission_json && <JsonViewer title={tr("Official rule records (submission schema)", "Registros oficiales de reglas (esquema de entrega)")} value={res.submission_json} />}
                </div>
              </section>
            )}

            {res?.hierarchy && (
              <section id="ing-hierarchy">
                <SectionTitle title={tr("Jurisdiction and priority", "Jurisdicción y prioridad")} sub={tr("Where the new law sits in State → County → City, and how conflicts are resolved.", "Dónde queda la nueva ley en Estado → Condado → Ciudad y cómo se resuelven los conflictos.")} />
                <div className="pt-6"><HierarchyView h={res.hierarchy} /></div>
              </section>
            )}

            {res?.graph && (
              <section id="ing-graph">
                <SectionTitle title={tr("Knowledge graph", "Grafo de conocimiento")} sub={tr(`+${res.graph.delta.nodes} nodes and ${res.graph.edges.length} relationships, built from the extracted and validated data.`, `+${res.graph.delta.nodes} nodos y ${res.graph.edges.length} relaciones, construidos con los datos extraídos y validados.`)} />
                <div className="pt-6"><KnowledgeGraphView graph={res.graph} /></div>
              </section>
            )}

            {res?.validation && (
              <section id="ing-validation">
                <SectionTitle title={tr("Deterministic validation", "Validación determinista")} sub={tr("Plain code, no AI: required fields, schema, citations, dates, references and duplicates.", "Código simple, sin IA: campos, esquema, citas, fechas, referencias y duplicados.")} />
                <div className="pt-6"><ValidationPanel v={res.validation} /></div>
              </section>
            )}

            {res?.judge && (
              <section id="ing-judge">
                <SectionTitle title={tr("Autonomous Judge", "Juez autónomo")} sub={tr("A second, independent model inspects the extraction against the original text. Its answer is structured and auditable.", "Un segundo modelo independiente inspecciona la extracción frente al texto original. Su respuesta es estructurada y auditable.")} />
                <div className="pt-6"><JudgePanel j={res.judge} policy={res.policy} /></div>
              </section>
            )}

            {res?.impact && (
              <section id="ing-impact">
                <SectionTitle title={tr("What this law would reach", "A quién alcanzaría esta ley")} />
                <dl className="mt-6 grid grid-cols-3 divide-x divide-hairline rounded-lg border border-hairline bg-sheet">
                  {[
                    [tr("Buildings", "Edificios"), String(res.impact.affected_count)],
                    [tr("Effective", "Vigencia"), res.impact.effective_date ?? "—"],
                    [tr("Conflict flags", "Alertas de conflicto"), String(res.impact.conflicts)],
                  ].map(([k, v]) => <div key={k} className="px-4 py-3"><dt className="text-sm text-graphite">{k}</dt><dd className="text-xl font-semibold tabular text-deed">{v}</dd></div>)}
                </dl>
                {job.status === "published" && res.impact.sample[0] && (
                  <p className="mt-4 text-base text-deed">
                    {tr("Now live in Address Lookup: ", "Ahora vigente en la búsqueda de direcciones: ")}
                    {res.impact.sample.slice(0, 4).map((a) => <Link key={a.address_id} to="/a/$addressId" params={{ addressId: a.address_id }} search={{ asOf: res.impact?.effective_date ?? undefined }} className="mr-3 text-permit underline underline-offset-2">{a.label.split(",")[0]}</Link>)}
                  </p>
                )}
              </section>
            )}

            {res?.source && res.rules_json && (job.status === "review_required" || job.status === "ready" || job.status === "published") && (
              <div id="ing-review" ref={reviewRef}>
                <ReviewScreen
                  job={job}
                  focusRule={focusRule}
                  busy={publish.isPending || reject.isPending || rejudge.isPending || edit.isPending}
                  onApprove={() => void act(() => publish.mutateAsync({ jobId: jobId!, token: values.token, approve: true }), tr("Approved and published", "Aprobada y publicada"))}
                  onReject={() => void act(() => reject.mutateAsync({ jobId: jobId!, token: values.token }), tr("Rejected. Nothing was published.", "Rechazada. No se publicó nada."))}
                  onRejudge={() => void act(() => rejudge.mutateAsync({ jobId: jobId!, token: values.token }), tr("The Judge reviewed it again", "El Juez la revisó otra vez"))}
                  onSaveEdit={(rules) => void act(() => edit.mutateAsync({ jobId: jobId!, rules, token: values.token }), tr("Saved. Validation ran again; run the Judge to re-verify.", "Guardado. La validación se ejecutó otra vez; ejecute el Juez para verificar de nuevo."))}
                />
              </div>
            )}

            {res?.audit && res.audit.length > 0 && <AuditTrail events={res.audit} />}
          </div>
        </div>
      )}
    </Page>
  );
}
