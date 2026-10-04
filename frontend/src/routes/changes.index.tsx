import { Button } from "@/components/ui/button";
import { createFileRoute, Link } from "@tanstack/react-router";
import { CircleCheck, CircleX } from "lucide-react";
import { Page, PageHeader } from "@/components/layout/PageHeader";
import { Skeleton } from "@/components/ui/skeleton";
import { useChanges } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n";
import { compareText, kindText, typeText } from "@/lib/changes";

export const Route = createFileRoute("/changes/")({
  head: () => ({
    meta: [
      { title: "Changes — Tenantly" },
      { name: "description", content: "How the law changes for sample buildings as new rules take effect, with the buildings affected and conflicts found." },
      { property: "og:title", content: "Changes — Tenantly" },
      { property: "og:description", content: "How the law changes for sample buildings as new rules take effect." },
    ],
  }),
  component: ChangesPage,
});

function ChangesPage() {
  const { tr, lang } = useI18n();
  const q = useChanges();
  return (
    <Page>
      <PageHeader
        title={tr("Changes", "Cambios")}
        lede={tr("Each change compares the law for every sample building at two moments, or with and without a measure, and counts who is affected.", "Cada cambio compara la ley para cada edificio de muestra en dos momentos, o con y sin una medida, y cuenta a quién afecta.")}
      />
      <div className="-mx-5 overflow-x-auto md:mx-0">
        <table className="w-full min-w-[900px] text-left">
          <thead>
            <tr className="border-b-2 border-deed text-sm text-graphite">
              {[tr("Title", "Título"), tr("Kind", "Tipo"), tr("Type", "Clase"), tr("Compared", "Comparado"), tr("Buildings affected", "Edificios afectados"), tr("Conflicts", "Conflictos"), tr("Check", "Verificación")].map((h, i) => (
                <th key={h} className={`py-3 pr-4 font-medium ${i === 0 ? "pl-5 md:pl-0" : ""} ${i === 4 || i === 5 ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {q.isLoading && Array.from({ length: 5 }).map((_, i) => <tr key={i}><td colSpan={7} className="py-3"><Skeleton className="h-6" /></td></tr>)}
            {q.data && q.data.length === 0 && <tr><td colSpan={7} className="py-8 pl-5 text-base text-graphite md:pl-0">{tr("No law changes yet.", "Aún no hay cambios en la ley.")}</td></tr>}
            {q.isError && <tr><td colSpan={7} className="py-8 pl-5 md:pl-0"><p role="alert" className="text-base text-deed">{tr("We couldn't load the list of changes. Check your connection and try again.", "No pudimos cargar la lista de cambios. Revise su conexión e intente de nuevo.")}</p><Button className="mt-3" variant="outline" onClick={() => q.refetch()}>{tr("Retry", "Reintentar")}</Button></td></tr>}
            {q.data?.map((c) => (
              <tr key={c.change_id} className="border-b border-hairline align-top hover:bg-sheet">
                <td className="py-3.5 pl-5 pr-4 md:pl-0">
                  <Link to="/changes/$id" params={{ id: c.change_id }} className="text-base font-medium text-deed underline-offset-4 hover:text-permit hover:underline">{c.title}</Link>
                  {c.test_id && <span className="block text-sm text-graphite">{c.test_id}</span>}
                </td>
                <td className="py-3.5 pr-4 text-sm">{kindText(c.kind, tr)}</td>
                <td className="py-3.5 pr-4 text-sm">{typeText(c.test_type, tr)}</td>
                <td className="whitespace-nowrap py-3.5 pr-4 text-sm tabular">{compareText(c, lang, tr)}</td>
                <td className="py-3.5 pr-4 text-right text-base font-semibold tabular">{c.affected_count}</td>
                <td className="py-3.5 pr-4 text-right text-base tabular">{c.conflict_count}</td>
                <td className="py-3.5 pr-4 text-sm">
                  {c.expected_check ? (
                    c.expected_check.passed ? (
                      <span className="inline-flex items-center gap-1.5 text-applies"><CircleCheck className="size-4" />{tr("Passed", "Aprobada")}</span>
                    ) : (
                      <span className="inline-flex items-start gap-1.5 text-destructive"><CircleX className="mt-0.5 size-4" />{tr("Failed", "Fallida")}: {c.expected_check.detail}</span>
                    )
                  ) : (
                    <span className="text-graphite">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Page>
  );
}
