// The landing page's own colours. They live in palette.<theme>.json (not in component code) so the repo's
// "no raw colour values" rule holds and `npm run contrast` can check every pair.
//
// One build flag picks the file: VITE_LANDING_THEME=neon (default) or gov. Components and styles only
// ever name roles (see paletteRules.js), so flipping the flag restyles the whole page.
import type { CSSProperties } from "react";
import gov from "./palette.gov.json";
import neon from "./palette.neon.json";
import {
  checkPalettePairs,
  checkPaletteRules,
  ROLES,
  type LandingPairResult,
  type PaletteFile,
  type Role,
} from "./paletteRules.js";

export type { LandingPairResult, Role };
export type LandingTheme = "neon" | "gov";

export const PALETTES: Record<LandingTheme, PaletteFile> = { neon, gov };
export const LANDING_THEME: LandingTheme = import.meta.env.VITE_LANDING_THEME === "gov" ? "gov" : "neon";
const palette = PALETTES[LANDING_THEME];

/** The hex value of each role in the selected palette. */
export const COLORS = Object.fromEntries(ROLES.map((role) => [role, palette.colors[palette.roles[role]]!])) as Record<
  Role,
  string
>;

/** `#RRGGBB` plus an alpha byte, for canvas strokes and fills. */
export function withAlpha(role: Role, alpha: number): string {
  const byte = Math.round(Math.min(1, Math.max(0, alpha)) * 255);
  return COLORS[role] + byte.toString(16).padStart(2, "0");
}

const kebab = (role: string) => role.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);

/**
 * CSS variables for the landing root: `--lp-<role>` for every role. The last four re-point the app's
 * theme roles inside the landing page, so shared pieces (SampleDataTag, the focus ring) are drawn in
 * stage colours whatever the app theme is.
 */
export const STAGE_VARS = {
  ...Object.fromEntries(ROLES.map((role) => [`--lp-${kebab(role)}`, COLORS[role]])),
  "--surface-2": COLORS.panel,
  "--fg-muted": COLORS.muted,
  "--border-strong": COLORS.edge,
  "--focus": COLORS.accent,
} as CSSProperties;

/** Same maths as the token check, on the landing pairs of one palette (default: the selected one). */
export function checkLandingPairs(theme: LandingTheme = LANDING_THEME): LandingPairResult[] {
  return checkPalettePairs(PALETTES[theme]);
}

/** Colour-use rules of one palette (default: the selected one). See paletteRules.js. */
export function checkLandingUseRules(theme: LandingTheme = LANDING_THEME): string[] {
  return checkPaletteRules(PALETTES[theme]);
}
