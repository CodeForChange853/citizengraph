// The words rule of the landing page, as a test: no technical term reaches a visitor, in any text a
// person can see or a screen reader can read (docs/landing_motion_spec.md, section 6).
import { readdirSync, readFileSync } from "node:fs";
import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import en from "./i18n/en.json";
import { SCENES } from "./scenes";
import { landing, setReducedMotion } from "./testHelpers";

/** Whole words or phrases, any letter case. "agency" is not "agent"; "deadline" is not "line". */
export const BANNED = [
  "model",
  "models",
  "LLM",
  "SLM",
  "neural",
  "Cypher",
  "query",
  "queries",
  "graph",
  "graphs",
  "node",
  "nodes",
  "Neo4j",
  "database",
  "schema",
  "guardrail",
  "guardrails",
  "LIMIT",
  "read-only",
  "read only",
  "agent",
  "agents",
  "SLA",
  "pipeline",
  "QLoRA",
  "GGUF",
  "CPU",
  "RAM",
  "GB",
  "hardware",
  "design target",
  "network",
  "offline-first",
  "local-first",
  "offline",
  "cloud",
  "server",
  "API",
  "latency",
  "token",
  "tokens",
  "benchmark",
  "benchmarks",
  "accuracy",
  "terminal",
  "prompt",
];
/** File locations and code: paths, file names, storage keys. */
const LOCATION = /(\bsrc\/|[\w-]+\.(json|tsx?|py|md|yaml|cypher)\b|localStorage|\bfolder\b|\bdirectory\b)/i;
const LABEL = "Thesis prototype, not an official government app";
const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const WORDS = new RegExp(`(?<![\\w-])(${BANNED.map(escape).join("|")})(?![\\w-])`, "i");

/** What is wrong with a piece of text, or nothing. The product name is the one allowed use of "graph". */
export function problems(text: string): string[] {
  const found: string[] = [];
  const plain = text.replaceAll("Citizen Graph", "").replaceAll(LABEL, "");
  const word = WORDS.exec(plain);
  if (word) found.push(`banned term "${word[0]}"`);
  const place = LOCATION.exec(plain);
  if (place) found.push(`file location "${place[0]}"`);
  if (/official/i.test(plain)) found.push('"official" outside the prototype label');
  return found;
}

function strings(value: unknown, path = ""): [string, string][] {
  if (typeof value === "string") return [[path, value]];
  if (Array.isArray(value)) return value.flatMap((v, i) => strings(v, `${path}.${i}`));
  return Object.entries(value as object).flatMap(([k, v]) => strings(v, path ? `${path}.${k}` : k));
}

/** Everything a person can see or a screen reader can read under an element. */
function exposed(root: HTMLElement): [string, string][] {
  const out: [string, string][] = [["text", root.textContent ?? ""]];
  root.querySelectorAll<HTMLElement>("*").forEach((el) => {
    for (const name of ["aria-label", "alt", "title", "placeholder", "aria-description"]) {
      const value = el.getAttribute(name);
      if (value) out.push([`${el.tagName.toLowerCase()}[${name}]`, value]);
    }
  });
  return out;
}

const words = (s: string) => s.trim().split(/\s+/).length;

afterEach(() => setReducedMotion(false));

describe("the checker itself", () => {
  it("catches the banned terms and lets the allowed ones through", () => {
    expect(problems("The model writes a query")).not.toEqual([]);
    expect(problems("It is read-only")).not.toEqual([]);
    expect(problems("an agent watches")).not.toEqual([]);
    expect(problems("see src/landing/copy.ts")).not.toEqual([]);
    expect(problems("an official app")).not.toEqual([]);
    expect(problems("Waiting on another agency isn't blamed on the office")).toEqual([]);
    expect(problems("Citizen Graph. AI, Core 1, Core 2, Guide, Watch, charter, deadline, alert.")).toEqual([]);
    expect(problems(LABEL)).toEqual([]);
  });
});

describe("landing words", () => {
  it("has no banned term, file location or stray 'official' in the copy file", () => {
    const bad = strings(en).flatMap(([key, text]) => problems(text).map((p) => `${key}: ${p}`));
    expect(bad).toEqual([]);
  });

  it("has none in the page as rendered, in text or in accessible names", async () => {
    const root = await landing();
    const bad = exposed(root).flatMap(([where, text]) => problems(text).map((p) => `${where}: ${p}`));
    expect(bad).toEqual([]);
    expect(root.textContent).toContain(LABEL);
  });

  it("has none in the still version for reduced motion", async () => {
    setReducedMotion(true);
    const root = await landing();
    expect(root.dataset.motion).toBe("static");
    const bad = exposed(root).flatMap(([where, text]) => problems(text).map((p) => `${where}: ${p}`));
    expect(bad).toEqual([]);
  });

  it("keeps every headline to 12 words and every support text to 25", () => {
    const scenes = en.scenes as Record<string, { headline?: string; support?: string; shots?: { headline: string; support: string }[] }>;
    for (const scene of SCENES) {
      const lines = scenes[scene.id]!.shots ?? [scenes[scene.id] as { headline: string; support: string }];
      for (const line of lines) {
        expect(words(line.headline), line.headline).toBeLessThanOrEqual(12);
        expect(words(line.support), line.support).toBeLessThanOrEqual(25);
      }
    }
  });

  it("makes no claim of proof: no numbers except 4 offices and 40 services, and none about speed, cost or users", async () => {
    const root = await landing();
    // drop the scene counter and "Core 1" / "Core 2"
    root.querySelectorAll(".lp-counter, .lp-dots").forEach((el) => el.remove());
    const text = (root.textContent ?? "").replace(/Core [12]/g, "");
    expect(text.match(/\d+/g)?.sort()).toEqual(["4", "4", "40", "40"]);
    expect(text).not.toMatch(/₱|PHP|peso|\d\s*(ms|seconds?|minutes?|hours?|days?)\b|percent|%|faster|saves|proven|approved|endorsed/i);
  });

  it("has no terminal: no input, no code, no typed text, no caret", async () => {
    const root = await landing();
    expect(root.querySelectorAll("input, textarea, code, pre, kbd, [contenteditable]")).toHaveLength(0);
    expect(screen.queryByRole("textbox")).toBeNull();
    const sources = readdirSync("src/landing").filter((f) => /\.(tsx?|css)$/.test(f) && !/test/i.test(f));
    for (const file of sources) expect(readFileSync(`src/landing/${file}`, "utf8"), file).not.toMatch(/caret|typewriter|MATCH \(|RETURN /);
  });

  it("shows no seal, emblem or image file", async () => {
    const root = await landing();
    expect(root.querySelectorAll("img, picture, video, audio, iframe")).toHaveLength(0);
  });
});
