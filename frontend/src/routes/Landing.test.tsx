import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { act, fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { DEMO_CYPHER, DEMO_QUESTION, GUARD_CHECKS } from "../landing/demo";
import { FakeAudioContext } from "../landing/fakeAudio";
import landingEn from "../landing/i18n/en.json";
import landingFil from "../landing/i18n/fil.json";
import { checkLandingPairs, checkLandingUseRules, COLORS, LANDING_THEME, PALETTES } from "../landing/palette";
import { checkPalettePairs, checkPaletteRules, ROLES } from "../landing/paletteRules.js";
import { SOUND_KEY } from "../landing/sound";
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
  await screen.findByRole("heading", { level: 1 }, { timeout: 5000 }); // the first test also loads the lazy chunk
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

  it("marks the answer card as sample data and shows neutral placeholders only: no amount, time or count", async () => {
    await landing();
    const card = document.querySelector<HTMLElement>(".lp-card")!;
    expect(within(card).getByText("Sample data")).toBeInTheDocument();
    expect(within(card).getByRole("heading", { name: "Business Permit" })).toBeInTheDocument();
    expect(within(card).getAllByText("Read from the charter")).toHaveLength(3);
    // nothing from the mock API's numbers, and no number at all
    expect(card.textContent).not.toMatch(/[0-9₱]/);
    expect(card.textContent).not.toMatch(/minute|peso|requirements?\b/i);
    expect(card.querySelectorAll("li")).toHaveLength(0); // no invented checklist
  });

  it("claims no numbers anywhere except the charter's office and service counts and the design target", async () => {
    const root = await landing();
    const text = root.querySelector("main")!.textContent ?? "";
    expect(text).not.toMatch(/₱|%|accura|benchmark|faster|percent/i);
    const numbers = [...new Set(text.replace(/LIMIT 25|0[5-8] \/ 08|Step [1-4]/g, "").match(/\d+/g))].sort();
    expect(numbers).toEqual(["16", "4", "40"]); // 4 offices, 40 services, "16 GB" design target
  });

  it("uses the word 'official' only in the not-official label, and claims no endorsement", async () => {
    const root = await landing();
    const label = "Thesis prototype, not an official government app";
    expect((root.textContent ?? "").replaceAll(label, "")).not.toMatch(/official/i);
    expect(JSON.stringify(landingEn)).not.toMatch(/official|endors|approved by|partner/i);
    expect(JSON.stringify(landingFil)).not.toMatch(/opisyal|official/i);
    expect(root.querySelectorAll("img, svg image")).toHaveLength(0); // no seals, emblems or marks
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
    expect(screen.getByTestId("lp-typed")).toHaveAttribute("data-count", String(DEMO_QUESTION.length));
    expect(screen.getByTestId("lp-code")).toHaveAttribute("data-count", String(DEMO_CYPHER.length));
    expect(screen.queryByRole("button", { name: "Replay intro" })).toBeNull();
    expect(root.querySelectorAll('.lp-guard li[data-on="true"]')).toHaveLength(GUARD_CHECKS.length);
    expect(root.querySelector(".lp-caret")).toBeNull();
    for (const el of root.querySelectorAll<HTMLElement>(".lp-step, .lp-alert, .lp-card, .lp-cta, .lp-arc")) {
      expect(el.style.opacity).toBe("1");
    }
  });
});

describe("landing intro", () => {
  it("plays by itself, with 'Skip intro' first in the tab order", async () => {
    const user = userEvent.setup();
    const root = await landing();
    expect(root).toHaveAttribute("data-motion", "full");
    expect(root).toHaveAttribute("data-playing", "true");
    expect(Number(screen.getByTestId("lp-typed").dataset.count)).toBeLessThan(DEMO_QUESTION.length);
    await user.tab();
    expect(screen.getByRole("link", { name: "Skip intro" })).toHaveFocus();
    expect(root.querySelector("a, button, [tabindex]")).toBe(screen.getByRole("link", { name: "Skip intro" }));
  });

  it("skips to the end of the intro: everything typed and ticked, nothing playing", async () => {
    const user = userEvent.setup();
    const root = await landing();
    await user.click(screen.getByRole("link", { name: "Skip intro" }));
    expect(root).toHaveAttribute("data-playing", "false");
    expect(screen.getByTestId("lp-typed")).toHaveAttribute("data-count", String(DEMO_QUESTION.length));
    expect(screen.getByTestId("lp-code")).toHaveAttribute("data-count", String(DEMO_CYPHER.length));
    expect(root.querySelectorAll('.lp-guard li[data-on="true"]')).toHaveLength(GUARD_CHECKS.length);
    expect(screen.getByRole("main")).toHaveFocus();
    expect(screen.getByRole("link", { name: "Skip intro" })).toHaveAttribute("data-idle", "true");
  });

  it("can be replayed from the start", async () => {
    const user = userEvent.setup();
    const root = await landing();
    await user.click(screen.getByRole("link", { name: "Skip intro" }));
    await user.click(screen.getByRole("button", { name: "Replay intro" }));
    expect(root).toHaveAttribute("data-playing", "true");
    expect(Number(screen.getByTestId("lp-typed").dataset.count)).toBeLessThan(DEMO_QUESTION.length);
  });
});

function setViewport(width: number, height: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
  fireEvent(window, new Event("resize"));
}

describe("landing on a short phone (390x700)", () => {
  afterEach(() => setViewport(1024, 768));

  it("uses the compact stage under 760 px of height and keeps the query and all four checks in it", async () => {
    setViewport(390, 700);
    const root = await landing();
    expect(root).toHaveAttribute("data-compact", "true");
    const stage = root.querySelector<HTMLElement>(".lp-stage")!;
    expect(within(stage).getByText("Illustrative query, read-only")).toBeInTheDocument();
    expect(stage.querySelectorAll(".lp-guard li")).toHaveLength(GUARD_CHECKS.length);
    expect(within(stage).getByText("Thesis prototype, not an official government app")).toBeInTheDocument();
  });

  it("uses the full stage at 760 px and above, and follows a resize", async () => {
    setViewport(1366, 768);
    const root = await landing();
    expect(root).toHaveAttribute("data-compact", "false");
    act(() => setViewport(390, 759));
    expect(root).toHaveAttribute("data-compact", "true");
    act(() => setViewport(390, 760));
    expect(root).toHaveAttribute("data-compact", "false");
  });

  it("has compact rules for the stage in the stylesheet", () => {
    const css = readFileSync("src/landing/landing.css", "utf8");
    for (const part of [".lp-term", ".lp-guard", ".lp-graphzone", ".lp-skip", ".lp-h1"]) {
      expect(css).toContain(`.lp[data-compact="true"] ${part}`);
    }
  });
});

/** Counts audio contexts: none may exist before the visitor asks for sound with a gesture. */
function stubAudio() {
  const created = vi.fn();
  vi.stubGlobal(
    "AudioContext",
    class extends FakeAudioContext {
      constructor() {
        super();
        created();
      }
    },
  );
  return created;
}

describe("landing sound", () => {
  it("is off by default: no audio context, nothing stored, and none after gestures elsewhere", async () => {
    const created = stubAudio();
    const user = userEvent.setup();
    await landing();
    const toggle = screen.getByRole("button", { name: "Sound: off" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    await user.click(screen.getByRole("link", { name: "Skip intro" }));
    fireEvent.keyDown(window, { key: "a" });
    expect(created).not.toHaveBeenCalled();
    expect(localStorage.getItem(SOUND_KEY)).toBeNull();
  });

  it("starts only when the visitor turns it on, and remembers the choice", async () => {
    const created = stubAudio();
    const user = userEvent.setup();
    await landing();
    await user.click(screen.getByRole("button", { name: "Sound: off" }));
    expect(screen.getByRole("button", { name: "Sound: on" })).toHaveAttribute("aria-pressed", "true");
    expect(created).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(SOUND_KEY)).toBe("true");
    await user.click(screen.getByRole("button", { name: "Sound: on" }));
    expect(localStorage.getItem(SOUND_KEY)).toBe("false");
    expect(screen.getByRole("button", { name: "Sound: off" })).toBeInTheDocument();
  });

  it("waits for a gesture on the next visit even when sound was left on", async () => {
    const created = stubAudio();
    localStorage.setItem(SOUND_KEY, "true");
    await landing();
    expect(screen.getByRole("button", { name: "Sound: on" })).toBeInTheDocument();
    expect(created).not.toHaveBeenCalled();
    fireEvent.pointerDown(window);
    expect(created).toHaveBeenCalledTimes(1);
  });

  it("has no sound at all with reduced motion", async () => {
    const created = stubAudio();
    localStorage.setItem(SOUND_KEY, "true");
    setReducedMotion(true);
    await landing();
    expect(screen.queryByRole("button", { name: /Sound/ })).toBeNull();
    fireEvent.pointerDown(window);
    expect(created).not.toHaveBeenCalled();
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

  it("uses the neon palette unless the build flag says gov, and both files define every role", () => {
    expect(LANDING_THEME).toBe("neon");
    expect(COLORS.stage).toBe(PALETTES.neon.colors.stage);
    for (const theme of ["neon", "gov"] as const) {
      expect(Object.keys(PALETTES[theme].roles).sort(), theme).toEqual([...ROLES].sort());
    }
  });

  it("switches to the government palette with VITE_LANDING_THEME=gov", async () => {
    vi.stubEnv("VITE_LANDING_THEME", "gov");
    vi.resetModules();
    try {
      const flipped = await import("../landing/palette");
      expect(flipped.LANDING_THEME).toBe("gov");
      expect(flipped.COLORS.stage).toBe(PALETTES.gov.colors.stage);
      expect((flipped.STAGE_VARS as Record<string, string>)["--lp-on-alert"]).toBe(PALETTES.gov.colors.text);
    } finally {
      vi.unstubAllEnvs();
      vi.resetModules();
    }
  });

  it("passes WCAG AA for every landing colour pair in both palettes, and each palette keeps its use rules", () => {
    for (const theme of ["neon", "gov"] as const) {
      expect(checkLandingPairs(theme).filter((r) => !r.pass), theme).toEqual([]);
      expect(checkLandingUseRules(theme), theme).toEqual([]);
    }
  });

  it("neon: text on an orange or cyan fill is the stage colour, never white, and orange text sits on stage or panel", () => {
    const neon = PALETTES.neon;
    expect(neon.colors[neon.roles.onAccent]).toBe(neon.colors.stage);
    expect(neon.colors[neon.roles.onAlert]).toBe(neon.colors.stage);
    const broken = structuredClone(neon);
    broken.roles.onAlert = "heading"; // white on orange is 3.4:1
    const pairs = checkPalettePairs(broken);
    expect(pairs.filter((r) => !r.pass).map((r) => r.fgRole)).toEqual(["onAlert"]);
    expect(checkPaletteRules(broken).join("\n")).toMatch(/text on "neon" must be "stage"/);
  });

  it("gov: red is only the SLA alert and never text; blue stays decorative", () => {
    const gov = PALETTES.gov;
    expect(gov.rules.alertOnly).toEqual(["alert"]);
    expect(gov.decorative).toEqual(["line"]);
    const broken = structuredClone(gov);
    broken.roles.hot = "alert";
    expect(checkPaletteRules(broken).join("\n")).toMatch(/is for the SLA alert only/);
  });

  it("uses red only in the SLA alert styles", () => {
    const css = readFileSync("src/landing/landing.css", "utf8");
    const rules = css.split("}").filter((rule) => rule.includes("--lp-alert"));
    expect(rules.length).toBeGreaterThan(0);
    for (const rule of rules) expect(rule).toMatch(/lp-alert|lp-bloom|data-state="late"/);
  });
});
