import type { ReactNode } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { BookOpen, Copy } from "lucide-react";
import { Page } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { TierTag } from "@/components/tenantly/TierTag";
import { ResultPill } from "@/components/tenantly/ResultPill";
import { NeedsReview } from "@/components/tenantly/RuleRow";
import { useCopyCitation, useLawSheets } from "@/components/tenantly/LawSheets";
import { useAudit, useRule } from "@/lib/api/hooks";
import type { Result } from "@/lib/api/types";
import { CATEGORY_LABEL, STATUS_LABEL } from "@/lib/labels";
import { useI18n } from "@/lib/i18n";
import { fmtDate, pct } from "@/lib/format";

export const Route = createFileRoute("/rules/$ruleId")({
  head: ({ params }) => ({
    meta: [
      { title: `Rule ${params.ruleId} — Tenantly` },
      { name: "description", content: "What this housing rule requires, who it covers, when it takes effect, and the official text." },
      { property: "og:title", content: `Rule ${params.ruleId} — Tenantly` },
      { property: "og:description", content: "What this housing rule requires, who it covers, and the official text." },
    ],
  }),
  component: RuleDetailPage,
});

function Block({ title, children, id }: { title: string; children: ReactNode; id?: string }) {
  return (
    <section id={id} className="grid gap-3 border-t border-hairline py-8 md:grid-cols-12 md:gap-8">
      <h2 className="text-lg text-deed md:col-span-4">{title}</h2>
      <div className="md:col-span-8">{children}</div>
    </section>
  );
}

function RuleDetailPage() {
  const { ruleId } = Route.useParams();
  const { tr, tb, lang, t } = useI18n();
  const q = useRule(ruleId);
  const audit = useAudit(ruleId);
  const { openSource, openAudit } = useLawSheets();
  const copy = useCopyCitation();
  const L = (p: [string, string]) => (lang === "es" ? p[1] : p[0]);

  if (q.isLoading) return <Page><div className="pt-16"><Skeleton className="h-10 w-2/3" /><Skeleton className="mt-6 h-40" /></div></Page>;
  if (q.isError || !q.data) {
    return (
      <Page>
        <div className="pt-16">
          <h1 className="text-3xl text-deed">{tr("We couldn't find that rule.", "No pudimos encontrar esa regla.")}</h1>
          <Button asChild className="mt-6"><Link to="/rules">{tr("See all rules", "Ver todas las reglas")}</Link></Button>
        </div>
      </Page>
    );
  }
  const r = q.data;
  const cites = [r.citation, ...r.extra_citations];

  return (
    <Page>
      <nav className="pt-8 text-sm text-graphite" aria-label="Breadcrumb">
        <Link to="/rules" className="text-permit hover:underline">{tr("Rules", "Reglas")}</Link>
        <span className="mx-2" aria-hidden="true">›</span>
        {L(CATEGORY_LABEL[r.category])}
      </nav>
      <header className="grid gap-8 pb-10 pt-4 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-sm border border-deed px-2 py-0.5 text-sm text-deed">{L(STATUS_LABEL[r.rule_status])}</span>
            <TierTag tier={r.citation.tier} />
            {r.review_flag && <NeedsReview />}
          </div>
          <h1 className="mt-4 text-[30px] leading-tight text-deed md:text-4xl">{r.title}</h1>
          <p className="mt-2 text-base text-graphite">
            {r.jurisdiction.label}
            {r.effective_date && `, ${tr("effective", "vigente desde")} ${fmtDate(r.effective_date, lang)}`}
          </p>
          <p className="mt-5 max-w-[62ch] text-lg leading-[1.5] text-deed">{tb(r.summary)}</p>
        </div>
        <aside className="self-end rounded-lg border border-hairline bg-sheet p-5 lg:col-span-4">
          <h2 className="text-sm font-semibold text-graphite">{tr("Buildings in our data on Oct 1, 2026", "Edificios en nuestros datos al 1 de oct. de 2026")}</h2>
          <ul className="mt-3 space-y-2">
            {(Object.entries(r.counts_at_default_date) as [Result, number][]).filter(([, n]) => n > 0).map(([k, n]) => (
              <li key={k} className="flex items-center justify-between"><ResultPill result={k} /><span className="text-lg font-semibold text-deed tabular">{n}</span></li>
            ))}
            {Object.values(r.counts_at_default_date).every((n) => n === 0) && <li className="text-sm text-graphite">{tr("None of our sample buildings yet.", "Ninguno de nuestros edificios de muestra aún.")}</li>}
          </ul>
        </aside>
      </header>

      <div className="lg:max-w-[1000px]">
        <Block title={tr("What it requires", "Qué exige")}><p className="text-body text-deed prose-width">{r.requirement}</p></Block>
        <Block title={tr("Who it covers", "A quién cubre")}>
          <p className="text-body text-deed prose-width">{tb(r.who)}</p>
          <p className="mt-2 text-base text-graphite prose-width">{tb(r.coverage_text)}</p>
        </Block>
        {r.key_values.length > 0 && (
          <Block title={tr("Key values", "Valores clave")}>
            <dl className="divide-y divide-hairline border-y border-hairline">
              {r.key_values.map((k, i) => (
                <div key={i} className="grid gap-1 py-3 sm:grid-cols-[12rem_1fr]">
                  <dt className="text-sm text-graphite">{k.name}</dt>
                  <dd className="text-base text-deed tabular">
                    {k.text}
                    {(k.valid_from || k.valid_to) && <span className="block text-sm text-graphite">{k.valid_from ? fmtDate(k.valid_from, lang, "short") : "…"} – {k.valid_to ? fmtDate(k.valid_to, lang, "short") : "…"}</span>}
                    {k.stale && <span className="block text-sm text-unknown">{tb(k.stale_note)}</span>}
                  </dd>
                </div>
              ))}
            </dl>
          </Block>
        )}
        <Block title={tr("Exemptions", "Exenciones")}>
          {r.exemptions.length ? (
            <ul className="list-disc space-y-1 pl-5">{r.exemptions.map((e, i) => <li key={i}>{tb(e.description)}</li>)}</ul>
          ) : (
            <p className="text-base text-graphite">{tr("No exemptions were extracted from the text.", "No se extrajeron exenciones del texto.")}</p>
          )}
        </Block>
        <Block title={tr("How it interacts with other rules", "Cómo interactúa con otras reglas")}>
          {r.relations.length ? (
            <ul className="space-y-4">
              {r.relations.map((rel, i) => (
                <li key={i} className="border-l-2 border-hairline pl-4">
                  <p className="text-base text-deed">{tb(rel.explanation)}</p>
                  <p className="text-sm text-graphite">
                    {rel.other_rule_id && (
                      <Link to="/rules/$ruleId" params={{ ruleId: rel.other_rule_id }} className="text-permit hover:underline">{rel.other_rule_id}</Link>
                    )}
                    {rel.active_from && `, ${tr("from", "desde")} ${fmtDate(rel.active_from, lang)}`}
                    {`, ${rel.evidence.cite}`}
                  </p>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-base text-graphite">{tr("No interactions recorded.", "Sin interacciones registradas.")}</p>
          )}
        </Block>
        <Block title={tr("Citations", "Citas")}>
          {cites.map((c, i) => (
            <figure key={i} className="mb-6 last:mb-0">
              {c.tier === "C" ? (
                <p className="text-base text-graphite">{tr("The law's text was not supplied. Open the panel to see the materials that say it exists.", "El texto no fue proporcionado. Abra el panel para ver los materiales que indican que existe.")}</p>
              ) : (
                <blockquote className="law-quote ledger-rail border-l-deed pl-5 text-deed">"<mark className="mark-highlight">{c.quote}</mark>"</blockquote>
              )}
              <figcaption className="mt-2 text-sm text-graphite">{c.cite}, {tr("retrieved", "obtenido")} {fmtDate(c.retrieved_at.slice(0, 10), lang, "short")}</figcaption>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => openSource({ citation: c, ruleId: r.rule_id })}><BookOpen />{c.tier === "C" ? tr("Why there's no quote", "Por qué no hay cita") : tr("Read the law", "Leer la ley")}</Button>
                <Button size="sm" variant="ghost" onClick={() => copy(c)}><Copy />{tr("Copy citation", "Copiar cita")}</Button>
              </div>
            </figure>
          ))}
        </Block>
        <Block title={tr("How we extracted this", "Cómo lo extrajimos")}>
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[10rem_1fr]">
            <dt className="text-graphite">{tr("Readers", "Lectores")}</dt><dd>{r.provenance.models.join(", ")}</dd>
            <dt className="text-graphite">{tr("Votes", "Votos")}</dt><dd>{Object.entries(r.provenance.votes).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", ")}</dd>
            <dt className="text-graphite">{tr("Confidence", "Confianza")}</dt><dd className="tabular">{pct(r.confidence)}</dd>
            <dt className="text-graphite">{tr("Audit entries", "Registros")}</dt><dd className="tabular">{audit.data?.length ?? "…"}</dd>
          </dl>
          <Button size="sm" variant="outline" className="mt-4" onClick={() => openAudit({ ruleId: r.rule_id, title: r.title, citations: cites })}>{tr("Open the audit", "Abrir la auditoría")}</Button>
        </Block>
      </div>
      <p className="mt-10 border-t border-deed/70 pt-5 text-base font-medium text-deed">{t("disclaimer")}</p>
    </Page>
  );
}
