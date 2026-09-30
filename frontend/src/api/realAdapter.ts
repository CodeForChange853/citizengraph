import type { ApiClient } from "./client";
import type { ChatRequest, ChatResponse, Health, ServiceListItem } from "./types";

/** Raised when the API cannot be reached (network error, timeout, proxy 5xx). */
export class ApiUnreachableError extends Error {}

const TIMEOUT_MS = 4000;

async function request<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...init, signal: AbortSignal.timeout(TIMEOUT_MS) });
  } catch (err) {
    throw new ApiUnreachableError(err instanceof Error ? err.message : "network error");
  }
  // The Vite dev proxy answers 5xx when the Python API is not running.
  if (res.status >= 500) throw new ApiUnreachableError(`HTTP ${res.status}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as T;
}

/** Talks to the FastAPI service. In dev, `base` is "/api" (proxied by Vite). */
export function createRealAdapter(base = "/api"): ApiClient {
  return {
    mode: "real",
    services: () => request<ServiceListItem[]>(base, "/services"),
    health: () => request<Health>(base, "/health"),
    chat: (req: ChatRequest) =>
      request<ChatResponse>(base, "/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }),
  };
}
