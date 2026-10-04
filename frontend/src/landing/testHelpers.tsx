// Test helpers only (never imported by the page).
import { screen } from "@testing-library/react";
import { AppRoutes } from "../App";
import { renderApp } from "../test/utils";

/** jsdom has no matchMedia: this stands in for the device's "reduce motion" setting. */
export function setReducedMotion(on: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: on && query.includes("prefers-reduced-motion"),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  })) as typeof window.matchMedia;
}

export async function landing() {
  renderApp(<AppRoutes />, { route: "/welcome" });
  await screen.findByRole("heading", { level: 1 }, { timeout: 5000 }); // the first test also loads the lazy chunk
  return document.querySelector<HTMLElement>(".lp")!;
}
