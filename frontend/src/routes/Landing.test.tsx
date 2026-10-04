import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { AppRoutes } from "../App";
import { DEMO_CYPHER, DEMO_QUESTION, GUARD_CHECKS } from "../landing/demo";
import landingEn from "../landing/i18n/en.json";
import landingFil from "../landing/i18n/fil.json";
import { checkLandingPairs, checkLandingUseRules } from "../landing/palette";
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

async function landing() {
  renderApp(<AppRoutes />, { route: "/welcome" });
  await screen.findByRole("heading", { level: 1 });
  return document.querySelector<HTMLElement>(".lp")!;
}

beforeEach(() => {
  // jsdom has no canvas: the stage and the grain are simply not drawn in tests.
  HTMLCanvasElement.prototype.getContext = (() => null) as typeof HTMLCanvasElement.prototype.getContext;
  setReducedMotion(false);
});

describe("landing route", () => {
  it("opens at /welcome outside the app shell and leaves the other routes alone", async () => {
    await landing();
    expect(screen.queryByRole("navigation", { name: "Main menu" })).not.toBeInTheDocument();
    expect(screen.getAllByText("Thesis prototype, not an official government app").length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Start asking" })).toHaveAttribute("href", "/");
  });

  it("still shows the home screen inside the shell at /", async () => {
    renderApp(<AppRoutes />);
    expect(await screen.findByLabelText("What do you need to do?")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main menu" })).toBeInTheDocument();
    expect(document.querySelector(".lp")).toBeNull();
  });

  it("marks the sample card as sample data and shows only the mock API's facts", async () => {
    await landing();
    const card = document.querySelector<HTMLElement>(".lp-card")!;
    expect(within(card).getByText("Sample data")).toBeInTheDocument();
    expect(within(card).getByRole("heading", { name: "Business Permit" })).toBeInTheDocument();
    expect(card).toHaveTextContent("14 requirements · ₱235.50 · about 37 minutes");
  });

  it("labels the demo query as illustrative and keeps it read-only, labelled and limited", async () => {
    await landing();
    expect(screen.getByText("Illustrative query, read-only")).toBeInTheDocument();
    expect(DEMO_CYPHER).toMatch(/^MATCH /);
    expect(DEMO_CYPHER).toMatch(/LIMIT \d+$/);
    expect(DEMO_CYPHER).not.toMatch(/\b(CREATE|MERGE|SET|DELETE|REMOVE|DROP|CALL|LOAD)\b/i);
    // every node pattern has a label and every relationship a type
    expect(DEMO_CYPHER.match(/\((\w+)(?![\w:])/g)).toBeNull();
    expect(DEMO_CYPHER).not.toMatch(/\[\w*\]|--/);
  });

  it("says the alert is a draft for staff and never blames the outside-agency step", async () => {
    await landing();
    expect(screen.getByText("Drafting an alert for staff review")).toBeInTheDocument();
    const external = document.querySelector<HTMLElement>('.lp-step[data-state="external"]')!;
    expect(external).toHaveTextContent("not counted");
    expect(within(external).queryByText("Drafting an alert for staff review")).toBeNull();
    expect(document.querySelectorAll(".lp-alert")).toHaveLength(1);
    expect(document.querySelector('.lp-step[data-state="late"] .lp-alert')).not.toBeNull();
  });
});

describe("landing with reduced motion", () => {
  it("shows every beat in its end state and plays nothing", async () => {
    setReducedMotion(true);
    const root = await landing();
    expect(root).toHaveAttribute("data-motion", "static");
    expect(root).toHaveAttribute("data-playing", "false");
    expect(screen.getByTestId("lp-typed")).toHaveTextContent(`> ${DEMO_QUESTION}`);
    expect(screen.getByTestId("lp-code").textContent).toBe(DEMO_CYPHER);
    expect(root.querySelectorAll('.lp-guard li[data-on="true"]')).toHaveLength(GUARD_CHECKS.length);
    expect(root.querySelector(".lp-caret")).toBeNull();
    for (const el of root.querySelectorAll<HTMLElement>(".lp-step, .lp-alert, .lp-card, .lp-cta, .lp-arc")) {
      expect(el.style.opacity).toBe("1");
    }
  });
});

function landingSources(dir = "src/landing"): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return landingSources(path);
    return /\.test\.tsx?$/.test(name) ? [] : [path];
  });
}

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("landing strings", () => {
  it("has a Filipino string for every English key and no extras", () => {
    expect(keys(landingFil).sort()).toEqual(keys(landingEn).sort());
  });

  it("lists every Filipino landing string as not yet verified", () => {
    const md = readFileSync("NEEDS-NATIVE-REVIEW.md", "utf8").split(/\r?\n/);
    for (const key of keys(landingFil, "landing.")) {
      const row = md.find((line) => line.startsWith(`| \`${key}\` |`));
      expect(row, key).toBeDefined();
      expect(row!.trimEnd().endsWith("|  |"), `${key} must not be ticked`).toBe(true);
    }
  });

  it("marks the Taglish demo question for native review", () => {
    const demo = readFileSync("src/landing/demo.ts", "utf8");
    expect(demo).toMatch(/NEEDS-NATIVE-REVIEW.*\r?\nexport const DEMO_QUESTION/);
  });

  it("switches the page to Filipino", async () => {
    const user = userEvent.setup();
    await landing();
    await user.click(screen.getByRole("button", { name: "Filipino" }));
    expect(await screen.findByRole("link", { name: "Magsimulang magtanong" })).toBeInTheDocument();
  });
});

describe("landing assets", () => {
  it("loads nothing from another host: no external URLs, fonts or scripts", () => {
    const files = [...landingSources(), "src/routes/Landing.tsx"];
    expect(files.length).toBeGreaterThan(5);
    const external = /(?:https?:)?\/\/[\w-]+(?:\.[\w-]+)+|@import\s+url/i;
    const tags = /<(script|link|iframe)\b/; // lower case: HTML tags, not the router's <Link>
    const bad = files.filter((f) => {
      const text = readFileSync(f, "utf8");
      return external.test(text) || tags.test(text);
    });
    expect(bad).toEqual([]);
  });

  it("imports only bundled fonts", () => {
    const page = readFileSync("src/landing/LandingPage.tsx", "utf8");
    const fonts = page.match(/import "([^"]+\.css)"/g) ?? [];
    expect(fonts.filter((f) => !/"(@fontsource\/|\.\/)/.test(f))).toEqual([]);
  });

  it("passes WCAG AA for every landing colour pair and keeps blue decorative and red for the alert", () => {
    expect(checkLandingPairs().filter((r) => !r.pass)).toEqual([]);
    expect(checkLandingUseRules()).toEqual([]);
  });

  it("uses red only in the SLA alert styles", () => {
    const css = readFileSync("src/landing/landing.css", "utf8");
    const rules = css.split("}").filter((rule) => rule.includes("--lp-alert"));
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) expect(rule).toMatch(/lp-alert|lp-bloom|data-state="late"/);
  });
});
