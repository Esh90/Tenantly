// The single swap point between mock data and the live Tenantly API.
// Leave VITE_API_BASE_URL unset (or "") to run entirely on mock data.
export const API_BASE_URL: string = import.meta.env['VITE_API_BASE_URL'] ?? ""; // "" = mock mode
export const SNAPSHOT_BASE_URL: string = import.meta.env['VITE_SNAPSHOT_BASE_URL'] ?? "";
// Covers free-host cold starts and one-time ingest-manager initialization. The long extraction
// itself streams over SSE after POST /ingest has returned.
export const REQUEST_TIMEOUT_MS = 30000;
export const DEFAULT_AS_OF = "2026-10-01";
export const SOURCES_RETRIEVED_AT = "2026-10-01";

export const IS_MOCK = API_BASE_URL === "";
/** Optional. Unused on the public hackathon demo. Only needed if PUBLIC_INGEST_ENABLED=false. */
export const ADMIN_TOKEN: string = import.meta.env["VITE_ADMIN_TOKEN"] ?? "tenantly-demo";
