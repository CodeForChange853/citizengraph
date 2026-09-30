import { createFixtureAdapter } from "./fixtureAdapter";
import { ApiUnreachableError, createRealAdapter } from "./realAdapter";
import type { ChatRequest, ChatResponse, ServiceListItem } from "./types";

export interface ApiClient {
  /** Which adapter answered last: "real" (FastAPI) or "fixtures" (local sample data). */
  mode: "real" | "fixtures";
  services(): Promise<ServiceListItem[]>;
  chat(req: ChatRequest): Promise<ChatResponse>;
}

interface Options {
  useFixtures?: boolean;
  real?: ApiClient;
  fixtures?: ApiClient;
  /** How long to stay on fixtures after the API failed, before trying it again. */
  retryAfterMs?: number;
  now?: () => number;
}

/**
 * Tries the real API and falls back to local fixtures when it cannot be reached, so
 * `npm run dev` works without Python. VITE_USE_FIXTURES=1 skips the real API entirely.
 */
export function createApiClient(options: Options = {}): ApiClient {
  const useFixtures = options.useFixtures ?? import.meta.env.VITE_USE_FIXTURES === "1";
  const fixtures = options.fixtures ?? createFixtureAdapter();
  if (useFixtures) return fixtures;

  const real = options.real ?? createRealAdapter();
  const retryAfterMs = options.retryAfterMs ?? 30_000;
  const now = options.now ?? Date.now;
  let downUntil = 0;

  async function call<T>(fn: (a: ApiClient) => Promise<T>): Promise<T> {
    if (now() >= downUntil) {
      try {
        const out = await fn(real);
        client.mode = "real";
        return out;
      } catch (err) {
        if (!(err instanceof ApiUnreachableError)) throw err;
        downUntil = now() + retryAfterMs;
      }
    }
    client.mode = "fixtures";
    return fn(fixtures);
  }

  const client: ApiClient = {
    mode: "real",
    services: () => call((a) => a.services()),
    chat: (req: ChatRequest): Promise<ChatResponse> => call((a) => a.chat(req)),
  };
  return client;
}

