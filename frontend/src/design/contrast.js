// WCAG 2.x contrast maths and token checks. Plain ESM so `npm run contrast` (node) and the app share it.

/** Minimum ratios: normal text 4.5, large text 3, UI components and graphics 3. */
export const MIN_RATIO = { text: 4.5, large: 3, ui: 3 };

/** Hue ranges (degrees) each palette family may use. Neutrals must also be low saturation. */
export const FAMILY_HUES = {
  blue: [212, 232],
  neutral: [212, 232],
  red: [345, 360],
  yellow: [44, 56],
};

export function hexToRgb(hex) {
  const m = /^#([0-9a-f]{6})$/i.exec(hex);
  if (!m) throw new Error(`Not a 6-digit hex colour: ${hex}`);
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function luminance(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a, b) {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

export function hsl(hex) {
  const [r, g, b] = hexToRgb(hex).map((v) => v / 255);
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0, l };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  return { h: (h * 60 + 360) % 360, s, l };
}

/** role -> hex for one theme. */
export function resolveTheme(tokens, theme) {
  const out = {};
  for (const [role, key] of Object.entries(tokens.themes[theme])) {
    const entry = tokens.palette[key];
    if (!entry) throw new Error(`Role "${role}" (${theme}) uses unknown palette colour "${key}"`);
    out[role] = entry.hex;
  }
  return out;
}

/** Every pair listed in tokens.pairs, in every theme. */
export function checkPairs(tokens) {
  const results = [];
  for (const theme of Object.keys(tokens.themes)) {
    const roles = resolveTheme(tokens, theme);
    for (const pair of tokens.pairs) {
      const fg = roles[pair.fg];
      const bg = roles[pair.bg];
      if (!fg || !bg) throw new Error(`Pair "${pair.label}" uses unknown role ${pair.fg}/${pair.bg}`);
      const ratio = contrast(fg, bg);
      const min = MIN_RATIO[pair.kind];
      results.push({ theme, ...pair, fgHex: fg, bgHex: bg, ratio, min, pass: ratio >= min });
    }
  }
  return results;
}

/** Palette rule: only our four families, and each colour must sit in its family's hue range. */
export function checkPalette(tokens) {
  const problems = [];
  for (const [name, { hex, family }] of Object.entries(tokens.palette)) {
    const range = FAMILY_HUES[family];
    if (!range) {
      problems.push(`${name}: unknown family "${family}"`);
      continue;
    }
    const { h, s } = hsl(hex);
    const rgb = hexToRgb(hex);
    const chroma = (Math.max(...rgb) - Math.min(...rgb)) / 255;
    if (family === "neutral" && chroma > 0.2) problems.push(`${name} ${hex}: too colourful for a neutral`);
    if (s === 0 && family === "neutral") continue;
    if (h < range[0] || h > range[1]) problems.push(`${name} ${hex}: hue ${Math.round(h)} is outside ${family}`);
  }
  return problems;
}

/**
 * Colour-use rules from the brief, checked on every listed pair:
 * yellow only on blue (or navy), never red on blue, and a yellow background only takes navy text.
 */
export function checkUseRules(tokens) {
  const problems = [];
  for (const theme of Object.keys(tokens.themes)) {
    const t = tokens.themes[theme];
    for (const pair of tokens.pairs) {
      const fg = tokens.palette[t[pair.fg]];
      const bg = tokens.palette[t[pair.bg]];
      const where = `${theme}: ${pair.label} [${pair.fg} on ${pair.bg}]`;
      if (fg.family === "yellow" && bg.family !== "blue") problems.push(`${where}: yellow must sit on blue or navy`);
      if (fg.family === "red" && bg.family === "blue") problems.push(`${where}: red on blue`);
      if (bg.family === "yellow" && t[pair.fg] !== "blue-900") problems.push(`${where}: yellow background needs navy text`);
    }
    for (const role of ["alert", "alert-bg"]) {
      if (!["red", "neutral"].includes(tokens.palette[t[role]].family)) problems.push(`${theme}: ${role} must be red`);
    }
  }
  return problems;
}
