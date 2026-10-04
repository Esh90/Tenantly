import { z } from "zod";
import { API_BASE_URL, IS_MOCK, REQUEST_TIMEOUT_MS } from "@/config";
import { ApiError } from "./errors";
import { mockRequest } from "./mock";

export { ApiError };

const envelope = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.unknown().optional(),
    request_id: z.string().nullable().optional(),
  }),
});

/** Loose structural check: live responses must be JSON objects or arrays. */
const anyJson = z.union([z.record(z.unknown()), z.array(z.unknown())]);

export interface RequestOptions extends RequestInit {
  /** api.ts function name; used by ?mockError= in mock mode. */
  fn: string;
  schema?: z.ZodTypeAny;
}

export async function request<T>(path: string, opts: RequestOptions): Promise<T> {
  const { fn, schema, ...init } = opts;
  if (IS_MOCK) return mockRequest<T>(fn, path, init);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/v1${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
      signal: controller.signal,
    });
  } catch (e) {
    const aborted = e instanceof DOMException && e.name === "AbortError";
    throw new ApiError(0, aborted ? "timeout" : "network_error", aborted ? "The request timed out" : "Could not reach the server");
  } finally {
    clearTimeout(timer);
  }

  const text = await res.text();
  let json: unknown = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    throw new ApiError(res.status, "bad_json", "The server sent an unreadable response");
  }

  if (!res.ok) {
    const parsed = envelope.safeParse(json);
    if (parsed.success) {
      const err = parsed.data.error;
      throw new ApiError(res.status, err.code, err.message, err.request_id ?? null, err.details ?? null);
    }
    throw new ApiError(res.status, "http_error", `Request failed with status ${res.status}`);
  }

  const check = (schema ?? anyJson).safeParse(json);
  if (!check.success) {
    throw new ApiError(res.status, "invalid_response", "The server response did not match the expected shape");
  }
  return json as T;
}
