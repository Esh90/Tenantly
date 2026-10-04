import type { Lang } from "@/lib/api/types";

export function fmtDate(iso: string | null | undefined, lang: Lang = "en", style: "long" | "short" = "long"): string {
  if (!iso) return "";
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(lang === "es" ? "es-US" : "en-US", {
    year: "numeric",
    month: style === "long" ? "long" : "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function toISO(d: Date): string {
  return d.toISOString().slice(0, 10);
}
export function fromISO(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}
export function addMonths(iso: string, n: number): string {
  const d = fromISO(iso);
  d.setUTCMonth(d.getUTCMonth() + n);
  return toISO(d);
}
export function clampISO(iso: string, min: string, max: string) {
  return iso < min ? min : iso > max ? max : iso;
}
export function daysBetween(a: string, b: string) {
  return Math.round((fromISO(b).getTime() - fromISO(a).getTime()) / 86400000);
}
export function pct(n: number) {
  return `${Math.round(n * 100)}%`;
}

export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function downloadCsv(filename: string, rows: (string | number)[][]) {
  const csv = rows
    .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
    .join("\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
