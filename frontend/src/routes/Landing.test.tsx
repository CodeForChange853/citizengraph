import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fireEvent, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { DEMO_CYPHER, DEMO_QUESTION, GUARD_CHECKS } from "../landing/demo";
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

/** Counts audio contexts: none may exist before the visitor asks for sound with a gesture. */
function stubAudio() {
  const created = vi.fn();
  class FakeAudioContext {
    state = "running";
    currentTime = 0;
    destination = {};
    constructor() {
      created();
    }
    resume = vi.fn(async () => {});
    suspend = vi.fn(async () => {});
    close = vi.fn(async () => {});
    createOscillator = vi.fn(() => ({
      type: "sine",
      frequency: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
      start: vi.fn(),
      stop: vi.fn(),
    }));
    createGain = vi.fn(() => ({
      gain: { setValueAtTime: vi.fn(), exponentialRampToValueAtTime: vi.fn() },
      connect: vi.fn(),
    }));
  }
  vi.stubGlobal("AudioContext", FakeAudioContext);
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
