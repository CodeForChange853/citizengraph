import { QueryClient } from "@tanstack/react-query";

/**
 * networkMode "always": TanStack Query would otherwise pause every request while the phone thinks it
 * is offline, so the home screen would say "Loading" forever. The API client already handles a
 * missing connection (service worker cache, then local fixtures), and the ask box is disabled offline.
 */
export function createQueryClient(retry: number | false = 1): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry, networkMode: "always" },
      mutations: { networkMode: "always" },
    },
  });
}
