// The single swap point between mock data and the live Tenantly API.
// Leave VITE_API_BASE_URL unset (or "") to run entirely on mock data.
export const API_BASE_URL: string = import.meta.env['VITE_API_BASE_URL'] ?? ""; // "" = mock mode
export const SNAPSHOT_BASE_URL: string = import.meta.env['VITE_SNAPSHOT_BASE_URL'] ?? "";
export const REQUEST_TIMEOUT_MS = 6000;
export const DEFAULT_AS_OF = "2026-10-01";
export const SOURCES_RETRIEVED_AT = "2026-10-01";

export const IS_MOCK = API_BASE_URL === "";
