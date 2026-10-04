import { useRef } from "react";
import type { TimelineResponse } from "@/lib/api/types";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useI18n } from "@/lib/i18n";
import { addMonths, clampISO, daysBetween, fmtDate, fromISO, toISO } from "@/lib/format";

interface Props {
  timeline: TimelineResponse;
  asOf: string;
  onChange: (iso: string) => void;
  appliesCount: number;
}

export function TimelineTrack({ timeline, asOf, onChange, appliesCount }: Props) {
  const { tr, tb, lang } = useI18n();
  const { start, end } = timeline.range;
  const total = daysBetween(start, end);
  const trackRef = useRef<HTMLDivElement>(null);
  const pos = (iso: string) => (daysBetween(start, iso) / total) * 100;
  const segIndex = Math.max(0, timeline.segments.reduce((acc, s, i) => (s.start <= asOf ? i : acc), -1));
  const seg = timeline.segments[segIndex];
  const segEnd = seg?.end ?? end;
  const points = timeline.breakpoints.map((b) => b.date);

  const fromPointer = (clientX: number) => {
    const el = trackRef.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width));
    const d = fromISO(start);
    d.setUTCDate(d.getUTCDate() + Math.round(ratio * total));
    const iso = toISO(d);
    // snap to the start of the segment the pointer is in
    const s = [...timeline.segments].reverse().find((x) => x.start <= iso);
    onChange(s ? s.start : start);
  };

  const onKey = (e: React.KeyboardEvent) => {
    let next: string | null = null;
    if (e.key === "ArrowRight") next = points.find((p) => p > asOf) ?? end;
    else if (e.key === "ArrowLeft") next = [...points].reverse().find((p) => p < asOf) ?? start;
    else if (e.key === "PageUp") next = addMonths(asOf, 1);
    else if (e.key === "PageDown") next = addMonths(asOf, -1);
    else if (e.key === "Home") next = start;
    else if (e.key === "End") next = end;
    if (next) {
      e.preventDefault();
      onChange(clampISO(next, start, end));
    }
  };

  const years: string[] = [];
  for (let y = Number(start.slice(0, 4)); y <= Number(end.slice(0, 4)); y++) years.push(`${y}-01-01`);

  return (
    <div className="mt-5">
      <div
        ref={trackRef}
        className="relative h-10 cursor-pointer touch-none select-none"
        onPointerDown={(e) => {
          (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
          fromPointer(e.clientX);
        }}
        onPointerMove={(e) => e.buttons === 1 && fromPointer(e.clientX)}
      >
        <div className="absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 rounded-sm border border-hairline bg-sheet" />
        {seg && (
          <div
            className="absolute top-1/2 h-2 -translate-y-1/2 bg-highlighter transition-all duration-200"
            style={{ left: `${pos(seg.start)}%`, width: `${Math.max(0.8, pos(segEnd) - pos(seg.start))}%` }}
            aria-hidden="true"
          />
        )}
        {timeline.breakpoints.map((b) => (
          <Tooltip key={b.date}>
            <TooltipTrigger asChild>
              <span
                className="absolute top-1/2 h-5 w-px -translate-y-1/2 bg-deed"
                style={{ left: `${pos(b.date)}%` }}
                tabIndex={-1}
              />
            </TooltipTrigger>
            <TooltipContent className="text-sm">
              {fmtDate(b.date, lang)}: {tb(b.label)}
            </TooltipContent>
          </Tooltip>
        ))}
        <div
          role="slider"
          tabIndex={0}
          aria-label={tr("Date to show the law for", "Fecha para mostrar la ley")}
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={daysBetween(start, asOf)}
          aria-valuetext={fmtDate(asOf, lang)}
          onKeyDown={onKey}
          className="absolute top-1/2 size-5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-deed bg-sheet transition-[left] duration-200 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-permit"
          style={{ left: `${pos(asOf)}%` }}
        />
      </div>
      <div className="relative h-5 text-xs text-graphite tabular" aria-hidden="true">
        {years.map((y) => (
          <span key={y} className="absolute -translate-x-1/2 first:translate-x-0" style={{ left: `${pos(y)}%` }}>
            {y.slice(0, 4)}
          </span>
        ))}
      </div>
      <p className="sr-only" aria-live="polite">
        {tr(`Showing the law as of ${fmtDate(asOf, "en")}. ${appliesCount} rules apply.`, `Mostrando la ley al ${fmtDate(asOf, "es")}. Aplican ${appliesCount} reglas.`)}
      </p>
    </div>
  );
}
