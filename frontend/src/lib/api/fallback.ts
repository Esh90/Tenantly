import { SNAPSHOT_BASE_URL } from "@/config";
import { ApiError } from "./errors";

type Listener = (on: boolean) => void;
let fallbackActive = false;
const listeners = new Set<Listener>();

export function isFallbackActive() {
  return fallbackActive;
}
export function onFallbackChange(fn: Listener) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}
function setFallback() {
  if (fallbackActive) return;
  fallbackActive = true;
  listeners.forEach((l) => l(true));
}

function shouldFallback(e: unknown) {
  if (!(e instanceof ApiError)) return true;
  return e.status === 0 || e.status >= 500;
}

/**
 * Runs the live request; on network failure, timeout, or 5xx, and only when a
 * snapshot base URL is configured, reads the static snapshot file instead.
 */
export async function withFallback<T>(
  live: () => Promise<T>,
  snapshotPath: string,
  fromSnapshot?: (data: T) => T,
): Promise<T> {
  try {
    return await live();
  } catch (e) {
    if (!SNAPSHOT_BASE_URL || !shouldFallback(e)) throw e;
    const res = await fetch(`${SNAPSHOT_BASE_URL}${snapshotPath}`);
    if (!res.ok) throw e;
    let data = (await res.json()) as T;
    if (fromSnapshot) data = fromSnapshot(data);
    setFallback();
    if (data && typeof data === "object" && !Array.isArray(data) && "fallback" in (data as object)) {
      (data as unknown as { fallback: boolean }).fallback = true;
    }
    return data;
  }
}
