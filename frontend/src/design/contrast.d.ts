export type PairKind = "text" | "large" | "ui";
export interface Tokens {
  palette: Record<string, { hex: string; family: string }>;
  themes: Record<string, Record<string, string>>;
  pairs: { fg: string; bg: string; kind: PairKind; label: string }[];
  decorative: string[];
}
export interface PairResult {
  theme: string;
  fg: string;
  bg: string;
  kind: PairKind;
  label: string;
  fgHex: string;
  bgHex: string;
  ratio: number;
  min: number;
  pass: boolean;
}
export const MIN_RATIO: Record<PairKind, number>;
export const FAMILY_HUES: Record<string, [number, number]>;
export function hexToRgb(hex: string): [number, number, number];
export function luminance(hex: string): number;
export function contrast(a: string, b: string): number;
export function hsl(hex: string): { h: number; s: number; l: number };
export function resolveTheme(tokens: Tokens, theme: string): Record<string, string>;
export function checkPairs(tokens: Tokens): PairResult[];
export function checkPalette(tokens: Tokens): string[];
export function checkUseRules(tokens: Tokens): string[];
