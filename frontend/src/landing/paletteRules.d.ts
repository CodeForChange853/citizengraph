import type { PairKind } from "../design/contrast.js";

export type Role =
  | "stage"
  | "panel"
  | "text"
  | "heading"
  | "muted"
  | "edge"
  | "line"
  | "accent"
  | "onAccent"
  | "glow"
  | "hot"
  | "alert"
  | "onAlert";

export interface PaletteFile {
  name: string;
  colors: Record<string, string>;
  roles: Record<Role, string>;
  decorative: string[];
  rules: {
    alertOnly: string[];
    fillText: Record<string, string>;
    textOn: Record<string, string[]>;
  };
}

export interface RolePair {
  fg: Role;
  bg: Role;
  kind: PairKind;
  label: string;
}

export interface LandingPairResult {
  theme: string;
  label: string;
  kind: PairKind;
  fgRole: Role;
  bgRole: Role;
  fg: string;
  bg: string;
  fgHex: string;
  bgHex: string;
  ratio: number;
  min: number;
  pass: boolean;
}

export const ROLES: Role[];
export const ROLE_PAIRS: RolePair[];
export function checkPalettePairs(palette: PaletteFile): LandingPairResult[];
export function checkPaletteRules(palette: PaletteFile): string[];
