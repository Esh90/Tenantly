import { Link } from "@tanstack/react-router";
import { LogoGlyph } from "@/components/brand/Logo";
import { useMeta } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n";
import { IS_MOCK } from "@/config";

function formatDate(iso: string, lang: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString(lang === "es" ? "es-US" : "en-US", { year: "numeric", month: "long", day: "numeric", timeZone: "UTC" });
}

export function Footer() {
  const { t, lang } = useI18n();
  const { data: meta } = useMeta();
  const linkCls = "text-[15px] text-deed underline-offset-4 hover:underline";

  return (
    <footer className="mt-24 border-t border-deed/80 bg-sheet">
      <div className="mx-auto max-w-[1280px] px-5 py-14 md:px-8">
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-6">
            <div className="flex items-center gap-3 text-deed">
              <LogoGlyph className="h-9" />
              <span className="text-2xl font-bold tracking-[-0.02em]">Tenantly</span>
            </div>
            <p className="mt-5 max-w-[46ch] text-body text-graphite">{t("footer_about")}</p>
          </div>

          <nav aria-label="Footer" className="grid grid-cols-2 gap-8 md:col-span-6 md:grid-cols-2">
            <div>
              <h2 className="text-sm font-semibold text-graphite">{t("footer_explore")}</h2>
              <ul className="mt-3 space-y-2">
                <li><Link to="/" className={linkCls}>{t("nav_home")}</Link></li>
                <li><Link to="/rules" className={linkCls}>{t("nav_rules")}</Link></li>
                <li><Link to="/changes" className={linkCls}>{t("nav_changes")}</Link></li>
                <li><Link to="/watch" className={linkCls}>{t("nav_watched")}</Link></li>
              </ul>
            </div>
            <div>
              <h2 className="text-sm font-semibold text-graphite">{t("footer_trust")}</h2>
              <ul className="mt-3 space-y-2">
                <li><Link to="/about" className={linkCls}>{t("nav_about")}</Link></li>
                <li><Link to="/proof" className={linkCls}>{t("nav_proof")}</Link></li>
              </ul>
            </div>
          </nav>
        </div>

        <div className="mt-14 grid gap-6 border-t border-hairline pt-6 md:grid-cols-12">
          <p className="text-base font-medium text-deed md:col-span-7 prose-width">{t("disclaimer")}</p>
          <dl className="text-sm text-graphite md:col-span-5 md:text-right tabular">
            <div>
              <dt className="inline">{t("footer_data")}: </dt>
              <dd className="inline">{meta?.data_version ?? "…"}</dd>
            </div>
            <div>
              <dt className="inline">{t("footer_compiled")}: </dt>
              <dd className="inline">{meta ? formatDate(meta.compiled_at, lang) : "…"}</dd>
            </div>
            <div>{t("footer_retrieved")}</div>
            {IS_MOCK && <div>{t("footer_sample")}</div>}
          </dl>
        </div>
      </div>
    </footer>
  );
}
