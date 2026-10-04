// Landing palette checks. Plain ESM so `npm run contrast` (node) and the tests share them.
//
// The landing code never names a colour: it names a ROLE. Each palette file (palette.neon.json,
// palette.gov.json) maps every role to one of its own colours. The pairs below are every text and UI
// pairing the landing styles and the canvas use, written once by role, so both palettes are checked for
// exactly the same uses.
import { contrast, MIN_RATIO } from "../design/contrast.js";

export const ROLES = [
  "stage",
  "panel",
  "text",
  "heading",
  "muted",
  "edge",
  "line",
  "accent",
  "onAccent",
  "glow",
  "hot",
  "alert",
  "onAlert",
];

export const ROLE_PAIRS = [
  { fg: "text", bg: "stage", kind: "text", label: "body text on the stage" },
  { fg: "text", bg: "panel", kind: "text", label: "body text on a panel (terminal, answer card, read-out)" },
  { fg: "heading", bg: "stage", kind: "text", label: "headlines on the stage" },
  { fg: "heading", bg: "panel", kind: "text", label: "headings on a panel (answer card)" },
  { fg: "muted", bg: "stage", kind: "text", label: "small labels and HUD text on the stage" },
  { fg: "muted", bg: "panel", kind: "text", label: "small labels on a panel (terminal labels, sample tag)" },
  { fg: "accent", bg: "stage", kind: "text", label: "system text on the stage (links, scroll hint, HUD values)" },
  { fg: "accent", bg: "panel", kind: "text", label: "system text on a panel (prompt, guardrail ticks)" },
  { fg: "hot", bg: "stage", kind: "text", label: "newest headline word and arc text on the stage" },
  { fg: "hot", bg: "panel", kind: "text", label: "highlighted word on a panel" },
  { fg: "onAccent", bg: "accent", kind: "text", label: "text on an accent fill (call to action, pressed toggle)" },
  { fg: "onAlert", bg: "alert", kind: "text", label: "SLA alert text on the alert fill" },
  { fg: "alert", bg: "stage", kind: "ui", label: "SLA alert edge on the stage" },
  { fg: "alert", bg: "panel", kind: "ui", label: "SLA alert edge on a panel" },
  { fg: "accent", bg: "stage", kind: "ui", label: "focus ring and caret on the stage" },
  { fg: "accent", bg: "panel", kind: "ui", label: "focus ring and caret on a panel" },
  { fg: "heading", bg: "stage", kind: "ui", label: "focus ring round the call to action" },
  { fg: "glow", bg: "stage", kind: "ui", label: "glow trail, orb ring and sparks on the stage" },
  { fg: "text", bg: "stage", kind: "ui", label: "service nodes, crop marks and leader lines on the stage" },
  { fg: "edge", bg: "stage", kind: "ui", label: "control and step outline on the stage" },
  { fg: "edge", bg: "panel", kind: "ui", label: "panel and sample tag outline" },
];

/** WCAG ratio of every role pair in one palette. */
export function checkPalettePairs(palette) {
  return ROLE_PAIRS.map((pair) => {
    const fg = palette.roles[pair.fg];
    const bg = palette.roles[pair.bg];
    const fgHex = palette.colors[fg];
    const bgHex = palette.colors[bg];
    if (!fgHex || !bgHex) throw new Error(`${palette.name}: "${pair.label}" uses an unknown colour (${fg} on ${bg})`);
    const ratio = contrast(fgHex, bgHex);
    const min = MIN_RATIO[pair.kind];
    return {
      theme: `landing ${palette.name}`,
      label: `Landing: ${pair.label}`,
      kind: pair.kind,
      fgRole: pair.fg,
      bgRole: pair.bg,
      fg,
      bg,
      fgHex,
      bgHex,
      ratio,
      min,
      pass: ratio >= min,
    };
  });
}

/**
 * Colour-use rules. Every palette: all roles defined; decorative colours are never a checked foreground.
 * Each file then states its own rules:
 *   alertOnly  colours that may only be the alert role, and never text (gov: red is for the SLA alert);
 *   fillText   the one text colour allowed on a fill (neon: #050505 on orange and cyan, never white);
 *   textOn     the only backgrounds a colour may be text on (neon: orange text on stage and panel only).
 */
export function checkPaletteRules(palette) {
  const problems = [];
  const say = (text) => problems.push(`landing ${palette.name}: ${text}`);
  for (const role of ROLES) {
    const colour = palette.roles[role];
    if (!colour || !palette.colors[colour]) say(`role "${role}" has no colour`);
  }
  for (const role of Object.keys(palette.roles)) if (!ROLES.includes(role)) say(`unknown role "${role}"`);
  const { alertOnly, fillText, textOn } = palette.rules;
  for (const [role, colour] of Object.entries(palette.roles)) {
    if (alertOnly.includes(colour) && role !== "alert") say(`"${colour}" is for the SLA alert only, not for "${role}"`);
  }
  for (const pair of ROLE_PAIRS) {
    const fg = palette.roles[pair.fg];
    const bg = palette.roles[pair.bg];
    if (palette.decorative.includes(fg)) say(`${pair.label}: "${fg}" is decorative only`);
    if (pair.kind !== "text") continue;
    if (alertOnly.includes(fg)) say(`${pair.label}: "${fg}" is never text`);
    if (fillText[bg] && fillText[bg] !== fg) say(`${pair.label}: text on "${bg}" must be "${fillText[bg]}", not "${fg}"`);
    if (textOn[fg] && !textOn[fg].includes(bg)) say(`${pair.label}: "${fg}" text is not allowed on "${bg}"`);
  }
  return problems;
}
