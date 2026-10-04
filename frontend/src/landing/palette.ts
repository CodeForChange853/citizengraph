// The landing page's own colours. They live in palette.json (not in component code) so the repo's
// "no raw colour values" rule holds and `npm run contrast` can check every pair.
import type { CSSProperties } from "react";
import { contrast, MIN_RATIO, type PairKind } from "../design/contrast.js";
import palette from "./palette.json";

export type ColorName = keyof typeof palette.colors;
export const COLORS: Record<ColorName, string> = palette.colors;

/** `#RRGGBB` plus an alpha byte, for canvas strokes and fills. */
export function withAlpha(name: ColorName, alpha: number): string {
  const byte = Math.round(Math.min(1, Math.max(0, alpha)) * 255);
  return COLORS[name] + byte.toString(16).padStart(2, "0");
}

/**
 * CSS variables for the landing root. The last four re-point the app's theme roles inside the landing
 * page, so shared pieces (SampleDataTag, the focus ring) are drawn in stage colours in either theme.
 */
export const STAGE_VARS = {
  "--lp-stage": COLORS.stage,
  "--lp-panel": COLORS.panel,
  "--lp-text": COLORS.text,
  "--lp-accent": COLORS.accent,
  "--lp-line": COLORS.line,
  "--lp-edge": COLORS.edge,
  "--lp-alert": COLORS.alert,
  "--surface-2": COLORS.panel,
  "--fg-muted": COLORS.text,
  "--border-strong": COLORS.edge,
  "--focus": COLORS.accent,
} as CSSProperties;

export interface LandingPairResult {
  label: string;
  fg: string;
  bg: string;
  ratio: number;
  min: number;
  pass: boolean;
}

/** Same maths as the token check, on the landing pairs. */
export function checkLandingPairs(): LandingPairResult[] {
  return palette.pairs.map((p) => {
    const ratio = contrast(COLORS[p.fg as ColorName], COLORS[p.bg as ColorName]);
    const min = MIN_RATIO[p.kind as PairKind];
    return { label: p.label, fg: p.fg, bg: p.bg, ratio, min, pass: ratio >= min };
  });
}

/** Use rules: decorative colours are never a foreground of a checked pair; red only in alert pairs. */
export function checkLandingUseRules(): string[] {
  const problems: string[] = [];
  for (const p of palette.pairs) {
    if (palette.decorative.includes(p.fg)) problems.push(`${p.label}: "${p.fg}" is decorative only`);
    const usesAlert = palette.alertOnly.includes(p.fg) || palette.alertOnly.includes(p.bg);
    if (usesAlert && !/alert/i.test(p.label)) problems.push(`${p.label}: red is for the SLA alert only`);
    if (palette.alertOnly.includes(p.fg) && p.kind === "text") problems.push(`${p.label}: red is never text`);
  }
  return problems;
}
