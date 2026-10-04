import { useEffect, useState } from "react";
import { CloudOff } from "lucide-react";
import { isFallbackActive, onFallbackChange } from "@/lib/api/fallback";
import { useI18n } from "@/lib/i18n";
import { useMeta } from "@/lib/api/hooks";
import { fmtDate } from "@/lib/format";

export function FallbackBanner() {
  const { tr, lang } = useI18n();
  const meta = useMeta();
  const [on, setOn] = useState(false);
  useEffect(() => {
    setOn(isFallbackActive());
    return onFallbackChange(setOn);
  }, []);
  if (!on) return null;
  return (
    <div role="status" className="border-b border-unknown-border bg-unknown-bg text-deed">
      <div className="mx-auto flex max-w-[1280px] items-center gap-2 px-5 py-2 text-sm md:px-8">
        <CloudOff className="size-4" aria-hidden="true" />
        {(() => {
          const when = meta.data ? fmtDate(meta.data.compiled_at.slice(0, 10), lang) : "";
          return tr(`Showing saved data from ${when}. Live updates are unavailable right now.`, `Mostrando datos guardados del ${when}. Las actualizaciones en vivo no están disponibles ahora.`);
        })()}
      </div>
    </div>
  );
}
