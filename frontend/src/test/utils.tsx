import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router";
import { ApiProvider } from "../api/ApiProvider";
import type { ApiClient } from "../api/client";
import { createFixtureAdapter } from "../api/fixtureAdapter";

export function renderApp(ui: ReactElement, opts: { route?: string; state?: unknown; client?: ApiClient } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ApiProvider client={opts.client ?? createFixtureAdapter()}>
        <MemoryRouter initialEntries={[{ pathname: opts.route ?? "/", state: opts.state }]}>{ui}</MemoryRouter>
      </ApiProvider>
    </QueryClientProvider>,
  );
}
