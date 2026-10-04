// The landing page's look in ONE file: colours and type. Swap this file to restyle the page (for example
// for a government look); nothing else names a colour. The landing is not part of the app's contrast gate,
// but body text stays light grey on near-black. The values live in tokens.json.
import tokens from "./tokens.json";

/**
 * stage: almost black. panel: cards and chips. neon: Core 2 (the Watch), sparks, alerts, the orb.
 * accent: Core 1 (the Guide), system glow, focus rings. line: hairlines and wireframe.
 * idle: the stretch of a request spent at another agency.
 */
export const TOKENS = tokens.colors;

export type TokenName = keyof typeof TOKENS;

export const FONTS = {
  display: '"Archivo", "Atkinson Hyperlegible", system-ui, sans-serif',
  body: '"Atkinson Hyperlegible", system-ui, sans-serif',
  mono: '"Atkinson Hyperlegible Mono", ui-monospace, monospace',
} as const;

/** A token as red, green, blue in 0 to 1 (for shaders). */
export function tone(name: TokenName): [number, number, number] {
  const n = parseInt(TOKENS[name].slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

/** The tokens as CSS custom properties, set once on the page root. */
export const STAGE_VARS = {
  ...Object.fromEntries(Object.entries(TOKENS).map(([name, hex]) => [`--lp-${name}`, hex])),
  "--lp-font-display": FONTS.display,
  "--lp-font-body": FONTS.body,
  "--lp-font-mono": FONTS.mono,
} as Record<string, string>;
