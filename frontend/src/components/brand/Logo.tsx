import { cn } from "@/lib/utils";

interface LogoProps {
  className?: string;
  /** Swap in the final brand file later. */
  src?: string;
  showWordmark?: boolean;
}

export function LogoGlyph({ className }: { className?: string }) {
  const windows: { x: number; y: number; lit?: boolean }[] = [
    { x: 7, y: 9 },
    { x: 15, y: 9 },
    { x: 7, y: 16 },
    { x: 15, y: 16, lit: true },
    { x: 7, y: 23 },
    { x: 15, y: 23 },
  ];
  return (
    <svg viewBox="0 0 28 32" className={cn("h-7 w-auto", className)} aria-hidden="true">
      <path
        d="M3 31V9a6 6 0 0 1 6-6h10a6 6 0 0 1 6 6v22"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M1 31h26" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      {windows.map((w) => (
        <rect
          key={`${w.x}-${w.y}`}
          x={w.x - 0.5}
          y={w.y - 0.5}
          width="6"
          height="5"
          rx="0.6"
          className={w.lit ? "fill-highlighter" : "fill-none"}
          stroke="currentColor"
          strokeWidth="1.4"
        />
      ))}
    </svg>
  );
}

export function Logo({ className, src, showWordmark = true }: LogoProps) {
  if (src) return <img src={src} alt="Tenantly" className={cn("h-7 w-auto", className)} />;
  return (
    <span className={cn("inline-flex items-center gap-2 text-deed", className)}>
      <LogoGlyph />
      {showWordmark && <span className="text-[21px] font-bold tracking-[-0.02em]">Tenantly</span>}
    </span>
  );
}
