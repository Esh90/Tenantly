import { useEffect, useRef, useState } from "react";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { CircleCheck, CircleDashed, CircleX, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Page, PageHeader, SectionTitle } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { MapPanel } from "@/components/map/MapPanel";
import { ResultPill } from "@/components/tenantly/ResultPill";
import { TierTag } from "@/components/tenantly/TierTag";
import { useMeta, usePublishIngest, useStartIngest } from "@/lib/api/hooks";
import { streamIngest } from "@/lib/api/api";
import { ApiError } from "@/lib/api/errors";
import type { IngestJob, IngestStage } from "@/lib/api/types";
import { useI18n } from "@/lib/i18n";
import { fmtDate, toISO } from "@/lib/format";

export const Route = createFileRoute("/ingest")({
  head: () => ({
    meta: [
      { title: "Read a new law — Tenantly" },
      { name: "description", content: "Paste a law's full text to extract its rules, verify every quote and see which buildings it reaches before publishing." },
      { property: "og:title", content: "Read a new law — Tenantly" },
      { property: "og:description", content: "Extract rules from a new law and see which buildings it reaches before publishing." },
    ],
  }),
  component: IngestPage,
});

const LIMIT = 200_000;
const STAGE_NAMES: Record<string, [string, string]> = {
  received: ["Received", "Recibido"], sectionize: ["Split into sections", "Dividido en secciones"], triage: ["Find sections with rules", "Encontrar secciones con reglas"],
  extract: ["Extract rules", "Extraer reglas"], verify: ["Check every quote", "Verificar cada cita"], crosscheck: ["Cross-check other rules", "Comparar con otras reglas"],
  calendar: ["Compute effective date", "Calcular fecha de vigencia"], link: ["Link to a jurisdiction", "Vincular a jurisdicción"], explain: ["Write plain language", "Redactar en lenguaje claro"],
  diff: ["Compare with current rules", "Comparar con reglas actuales"], impact: ["Find affected buildings", "Encontrar edificios afectados"], ready: ["Ready to publish", "Listo para publicar"],
};

type StageRow = IngestJob["stages"][number];

function IngestPage() {
  const { tr, tb, lang } = useI18n();
  const meta = useMeta();
  const start = useStartIngest();
  const publish = usePublishIngest();
  const navigate = useNavigate();
  const [token, setToken] = useState("");
  const [title, setTitle] = useState("Cambridge Fair Screening Ordinance");
  const [jur, setJur] = useState("ma_cambridge");
  const [url, setUrl] = useState("");
  const [retrieved, setRetrieved] = useState("");
  const [text, setText] = useState("");
  const [stages, setStages] = useState<StageRow[]>([]);
  const [job, setJob] = useState<IngestJob | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [confirm, setConfirm] = useState(false);
  const unsub = useRef<null | (() => void)>(null);

  useEffect(() => {
    setToken(window.sessionStorage.getItem("tenantly.admin") ?? "");
    setRetrieved(toISO(new Date()));
    return () => unsub.current?.();
  }, []);

  const run = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (!token) return setError(tr("Enter the admin token.", "Escriba el token de administrador."));
    if (text.length > LIMIT) return setError(tr("This text is longer than 200,000 characters.", "Este texto supera los 200,000 caracteres."));
    if (text.trim().length < 40) return setError(tr("Paste the full text of the law.", "Pegue el texto completo de la ley."));
    window.sessionStorage.setItem("tenantly.admin", token);
    setJob(null);
    setStages(Object.keys(STAGE_NAMES).map((s) => ({ stage: s as IngestStage, status: "pending", detail: "", ms: null })));
    try {
      const r = await start.mutateAsync({ body: { title, text, jurisdiction_hint: jur, source_url: url, retrieved_at: retrieved }, token });
      setJobId(r.job_id);
      unsub.current = streamIngest(r.job_id, (ev) => {
        if (ev.type === "stage" || ev.type === "impact") {
          const s = ev.data as StageRow;
          setStages((prev) => {
            const idx = prev.findIndex((p) => p.stage === s.stage);
            return prev.map((p, i) => (i === idx ? { ...s, status: "done" } : i === idx + 1 ? { ...p, status: "running" } : p));
          });
        } else if (ev.type === "done") setJob(ev.data as IngestJob);
        else if (ev.type === "error") setError((ev.data as { message?: string })?.message ?? tr("Reading failed.", "La lectura falló."));
      });
    } catch (err) {
      setStages([]);
      if (err instanceof ApiError) {
        if (err.status === 401) setError(tr("That admin token isn't valid.", "Ese token de administrador no es válido."));
        else if (err.status === 413) setError(tr("This text is longer than 200,000 characters.", "Este texto supera los 200,000 caracteres."));
        else if (err.status === 503 && err.code.toUpperCase() === "BUDGET_EXCEEDED") setError(tr("The extraction budget is used up. Showing saved results only.", "Se agotó el presupuesto de extracción. Solo se muestran resultados guardados."));
        else setError(err.message);
      } else setError(tr("Reading failed.", "La lectura falló."));
    }
  };

  const doPublish = async () => {
    if (!jobId) return;
    try {
      const r = await publish.mutateAsync({ jobId, token });
      setConfirm(false);
      const sample = job?.result?.impact.sample[0]?.address_id;
      toast.success(tr("Published to renters", "Publicado para inquilinos"), {
        action: { label: tr("See the change", "Ver el cambio"), onClick: () => navigate({ to: "/changes/$id", params: { id: r.change_id } }) },
        cancel: sample ? { label: tr("Sample address", "Dirección de muestra"), onClick: () => navigate({ to: "/a/$addressId", params: { addressId: sample }, search: { asOf: "2027-01-01" } }) } : undefined,
      });
      setJob((j) => (j ? { ...j, status: "published" } : j));
    } catch (err) {
      toast.error(err instanceof ApiError && err.status === 401 ? tr("That admin token isn't valid.", "Ese token de administrador no es válido.") : tr("Publishing didn't work.", "No se pudo publicar."));
    }
  };

  const res = job?.result;
  const running = stages.length > 0 && !job && !error;

  return (
    <Page>
      <PageHeader
        title={tr("Read a new law", "Leer una nueva ley")}
        lede={tr(
          "Paste the full text. Tenantly extracts rules, checks every quote against the text, computes the effective date, and shows which buildings it would reach before you publish.",
          "Pegue el texto completo. Tenantly extrae reglas, verifica cada cita, calcula la fecha de vigencia y muestra qué edificios alcanzaría antes de publicar.",
        )}
      />

      <div className="mt-10 grid gap-12 lg:grid-cols-12">
        <form onSubmit={run} className="space-y-5 lg:col-span-7">
          <div>
            <Label htmlFor="tok">{tr("Admin token", "Token de administrador")}</Label>
            <Input id="tok" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} className="mt-1.5 h-11 max-w-sm bg-sheet" />
            <p className="mt-1 text-xs text-graphite">{tr("Kept in this browser tab only.", "Se guarda solo en esta pestaña.")}</p>
          </div>
          <div className="grid gap-5 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="ttl">{tr("Title", "Título")}</Label>
              <Input id="ttl" required value={title} onChange={(e) => setTitle(e.target.value)} className="mt-1.5 h-11 bg-sheet" />
            </div>
            <div>
              <Label>{tr("Jurisdiction", "Jurisdicción")}</Label>
              <Select value={jur} onValueChange={setJur}>
                <SelectTrigger className="mt-1.5 h-11 bg-sheet"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {(meta.data?.jurisdictions ?? []).filter((j) => j.level !== "county").map((j) => <SelectItem key={j.id} value={j.id}>{j.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="ret">{tr("Retrieved", "Obtenido")}</Label>
              <Input id="ret" type="date" value={retrieved} onChange={(e) => setRetrieved(e.target.value)} className="mt-1.5 h-11 bg-sheet tabular" />
            </div>
            <div className="sm:col-span-2">
              <Label htmlFor="url">{tr("Source URL (optional)", "URL de la fuente (opcional)")}</Label>
              <Input id="url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} className="mt-1.5 h-11 bg-sheet" placeholder="https://" />
            </div>
          </div>
          <div>
            <div className="flex items-baseline justify-between">
              <Label htmlFor="txt">{tr("Full text", "Texto completo")}</Label>
              <span className={`text-xs tabular ${text.length > LIMIT ? "text-destructive" : "text-graphite"}`}>{text.length.toLocaleString()} / 200,000</span>
            </div>
            <Textarea id="txt" value={text} onChange={(e) => setText(e.target.value)} className="mt-1.5 min-h-[280px] bg-sheet font-sans text-base" placeholder={tr("Section 1. No housing provider shall deny tenancy…", "Sección 1. Ningún proveedor de vivienda…")} />
          </div>
          {error && <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-base text-destructive">{error}</p>}
          <Button type="submit" size="lg" disabled={running || start.isPending}>{running ? tr("Reading", "Leyendo") : tr("Read this law", "Leer esta ley")}</Button>
        </form>

        <aside className="lg:col-span-5">
          <h2 className="text-base font-semibold text-deed">{tr("Progress", "Progreso")}</h2>
          {stages.length === 0 ? (
            <p className="mt-3 border-t border-hairline pt-3 text-base text-graphite">{tr("Steps appear here while the law is read.", "Los pasos aparecen aquí mientras se lee la ley.")}</p>
          ) : (
            <ol aria-live="polite" className="mt-3 border-t border-hairline">
              {stages.map((s, i) => (
                <li key={s.stage} className="grid grid-cols-[1.75rem_1.5rem_1fr_auto] items-start gap-2 border-b border-hairline py-2.5">
                  <span className="text-sm text-graphite tabular">{i + 1}</span>
                  {s.status === "done" ? <CircleCheck className="size-5 text-applies" /> : s.status === "running" ? <Loader2 className="size-5 animate-spin text-permit" /> : s.status === "failed" ? <CircleX className="size-5 text-destructive" /> : <CircleDashed className="size-5 text-hairline" />}
                  <span>
                    <span className="block text-base text-deed">{tr(...(STAGE_NAMES[s.stage] ?? [s.stage, s.stage]))}</span>
                    {s.detail && <span className="block text-sm text-graphite">{s.detail}</span>}
                  </span>
                  <span className="text-xs text-graphite tabular">{s.ms ? `${s.ms} ms` : ""}</span>
                </li>
              ))}
            </ol>
          )}
        </aside>
      </div>

      {res && (
        <section className="mt-16">
          <SectionTitle
            title={tr(`We found ${res.rules.length} ${res.rules.length === 1 ? "rule" : "rules"}`, `Encontramos ${res.rules.length} regla(s)`)}
            sub={tr(`${res.verification.quotes_verified} of ${res.verification.quotes_checked} quotes found in the text.`, `${res.verification.quotes_verified} de ${res.verification.quotes_checked} citas encontradas en el texto.`)}
          />
          <div className="grid gap-10 pt-6 lg:grid-cols-12">
            <div className="lg:col-span-7">
              {res.rules.map((r) => (
                <article key={r.rule_id} className="ledger-rail border-b border-hairline border-l-notyet bg-sheet py-6 pl-6 pr-5">
                  <div className="flex flex-wrap gap-2"><ResultPill result="not_yet_effective" /><TierTag tier={r.citation.tier} /></div>
                  <h3 className="mt-3 text-lg text-deed">{r.title}</h3>
                  <p className="text-sm text-graphite">{r.jurisdiction.label}{r.effective_date && `, ${tr("effective", "vigente desde")} ${fmtDate(r.effective_date, lang)}`}</p>
                  <p className="mt-3 text-body text-deed">{tb(r.summary)}</p>
                  <blockquote className="law-quote mt-4 border-l-2 border-hairline pl-4 text-deed">"<mark className="mark-highlight">{r.citation.quote}</mark>"</blockquote>
                  <p className="mt-2 text-sm text-graphite">{r.citation.cite}</p>
                </article>
              ))}
            </div>
            <aside className="space-y-6 lg:col-span-5">
              <dl className="grid grid-cols-3 divide-x divide-hairline rounded-lg border border-hairline bg-sheet">
                {[
                  [tr("Buildings", "Edificios"), String(res.impact.affected_count)],
                  [tr("Effective", "Vigencia"), res.impact.effective_date ? fmtDate(res.impact.effective_date, lang, "short") : "—"],
                  [tr("Conflicts", "Conflictos"), String(res.impact.conflicts)],
                ].map(([k, v]) => (
                  <div key={k} className="px-4 py-3"><dt className="text-xs text-graphite">{k}</dt><dd className="text-lg font-semibold text-deed tabular">{v}</dd></div>
                ))}
              </dl>
              <figure className="overflow-hidden rounded-lg border border-hairline bg-sheet">
                <MapPanel points={res.impact.sample.map((a) => ({ id: a.address_id, lat: a.lat, lon: a.lon, kind: "changed" as const, label: a.label }))} fit="points" height={240} ariaLabel={tr("Map of buildings this law would reach", "Mapa de edificios que alcanzaría esta ley")} />
                <figcaption className="border-t border-hairline px-4 py-2.5 text-sm text-graphite">
                  {res.impact.sample.map((a) => a.label.split(",")[0]).join(", ")}
                </figcaption>
              </figure>
              {job?.status === "published" ? (
                <p className="text-base text-applies">{tr("Published to renters.", "Publicado para inquilinos.")} <Link to="/changes/$id" params={{ id: "chg_ing_demo" }} className="text-permit underline">{tr("See the change", "Ver el cambio")}</Link></p>
              ) : (
                <Button size="lg" className="w-full" onClick={() => setConfirm(true)}>{tr("Publish to renters", "Publicar para inquilinos")}</Button>
              )}
            </aside>
          </div>
        </section>
      )}

      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent className="bg-sheet sm:max-w-md">
          <DialogHeader>
            <DialogTitle className="text-xl">{tr(`Publish ${res?.rules.length ?? 0} rules?`, `¿Publicar ${res?.rules.length ?? 0} reglas?`)}</DialogTitle>
            <DialogDescription className="text-base">{tr(`${res?.impact.affected_count ?? 0} buildings will see this change.`, `${res?.impact.affected_count ?? 0} edificios verán este cambio.`)}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setConfirm(false)}>{tr("Cancel", "Cancelar")}</Button>
            <Button onClick={doPublish} disabled={publish.isPending}>{tr("Publish to renters", "Publicar para inquilinos")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Page>
  );
}
