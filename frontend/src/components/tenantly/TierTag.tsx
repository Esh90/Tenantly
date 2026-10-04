import type { EvidenceTier } from "@/lib/api/types";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const TIERS: Record<EvidenceTier, { label: string; tip: string }> = {
  A: { label: "Official text", tip: "Quoted from the official law text in our sources." },
  B: { label: "Official guidance", tip: "Quoted from official guidance published by the government, not the law itself." },
  C: {
    label: "Text not supplied",
    tip: "The law's text was not in our sources. We know it exists from other supplied materials, so we show it but do not quote the law itself.",
  },
  C1: { label: "Single source, unconfirmed", tip: "Only one supplied source mentions this rule, and we could not confirm it elsewhere." },
};

export function TierTag({ tier }: { tier: EvidenceTier }) {
  const t = TIERS[tier];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className="inline-flex items-center rounded-sm border border-hairline px-1.5 py-px text-xs text-graphite hover:border-graphite"
        >
          {t.label}
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-sm">{t.tip}</TooltipContent>
    </Tooltip>
  );
}
