import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { checkPairs, checkPalette, checkUseRules, contrast, type Tokens } from "./contrast.js";
import tokensJson from "./tokens.json";
import en from "../i18n/en.json";
import fil from "../i18n/fil.json";

const tokens = tokensJson as Tokens;

describe("design tokens", () => {
  it("uses the brand colours exactly", () => {
    expect(tokens.palette["blue-500"]!.hex).toBe("#0038A8");
    expect(tokens.palette["red-500"]!.hex).toBe("#CE1126");
    expect(tokens.palette["yellow-500"]!.hex).toBe("#FCD116");
    expect(tokens.palette["blue-900"]!.hex).toBe("#0B1F4B");
  });

  it("passes WCAG AA for every listed pair in light and dark", () => {
    const failed = checkPairs(tokens).filter((r) => !r.pass);
    expect(failed.map((r) => `${r.theme}: ${r.label} ${r.ratio.toFixed(2)}`)).toEqual([]);
  });

  it("keeps the palette to blue, red, yellow and neutrals, used as the brief says", () => {
    expect(checkPalette(tokens)).toEqual([]);
    expect(checkUseRules(tokens)).toEqual([]);
  });

  it("computes known contrast ratios", () => {
    expect(contrast("#000000", "#FFFFFF")).toBeCloseTo(21, 5);
    expect(contrast("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 5);
  });

  it("has the same roles in both themes", () => {
    expect(Object.keys(tokens.themes.dark!).sort()).toEqual(Object.keys(tokens.themes.light!).sort());
  });
});

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "test" ? [] : sourceFiles(path);
    return /\.(tsx?|css)$/.test(name) && !name.endsWith(".test.ts") && !name.endsWith(".test.tsx") ? [path] : [];
  });
}

describe("palette discipline", () => {
  it("has no raw colour values in components (colours come from tokens only)", () => {
    const offenders = sourceFiles("src")
      .filter((f) => !/(tokens|index)\.css$|\.d\.ts$/.test(f))
      .filter((f) => /#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(/.test(readFileSync(f, "utf8")));
    expect(offenders).toEqual([]);
  });
});

function keys(obj: object, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );
}

describe("translations", () => {
  it("has a Filipino string for every English key and no extras", () => {
    expect(keys(fil).sort()).toEqual(keys(en).sort());
  });

  it("lists every Filipino key in NEEDS-NATIVE-REVIEW.md", () => {
    const md = readFileSync("NEEDS-NATIVE-REVIEW.md", "utf8");
    const missing = keys(fil).filter((k) => !md.includes(`\`${k}\``));
    expect(missing).toEqual([]);
  });
});
