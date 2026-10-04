import { useState } from "react";
import { Check, ChevronDown, ChevronRight, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

/** Collapsible, copyable JSON. The value shown is exactly what the pipeline produced. */
export function JsonViewer({ title, value, defaultOpen = false, maxHeight = 420 }: { title: string; value: unknown; defaultOpen?: boolean; maxHeight?: number }) {
  const { tr } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  const [copied, setCopied] = useState(false);
  const text = JSON.stringify(value, null, 2);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: the text is selectable */
    }
  };
  return (
    <div className="rounded-lg border border-hairline bg-sheet">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5">
        <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-2 text-left text-base font-medium text-deed">
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          {title}
          <span className="text-sm font-normal text-graphite">{text.length.toLocaleString()} {tr("characters", "caracteres")}</span>
        </button>
        <Button type="button" variant="outline" size="sm" onClick={copy} className="gap-1.5">
          {copied ? <Check className="size-4" /> : <Copy className="size-4" />}
          {copied ? tr("Copied", "Copiado") : tr("Copy", "Copiar")}
        </Button>
      </div>
      {open && (
        <pre tabIndex={0} style={{ maxHeight }} className="overflow-auto border-t border-hairline bg-survey px-4 py-3 text-[13px] leading-relaxed text-deed">
          {text}
        </pre>
      )}
    </div>
  );
}
