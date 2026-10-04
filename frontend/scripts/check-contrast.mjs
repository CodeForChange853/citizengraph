// `npm run contrast`: fails if any text/background pair we use is below WCAG AA, in either app theme or
// in either landing palette, or if a palette breaks its colour-use rules. Reads src/design/tokens.json and
// src/landing/palette.{neon,gov}.json.
import tokens from "../src/design/tokens.json" with { type: "json" };
import { checkPairs, checkPalette, checkUseRules } from "../src/design/contrast.js";
import gov from "../src/landing/palette.gov.json" with { type: "json" };
import neon from "../src/landing/palette.neon.json" with { type: "json" };
import { checkPalettePairs, checkPaletteRules } from "../src/landing/paletteRules.js";

const results = checkPairs(tokens);
const paletteProblems = [...checkPalette(tokens), ...checkUseRules(tokens)];

const line = (r) =>
  `  ${r.pass ? "ok  " : "FAIL"} ${r.ratio.toFixed(2).padStart(5)}:1 (min ${r.min})  ${r.label}  [${r.fg} on ${r.bg}]`;

for (const theme of Object.keys(tokens.themes)) {
  console.log(`\n${theme} theme`);
  for (const r of results.filter((x) => x.theme === theme)) console.log(line(r));
}

// The landing page (/welcome) has its own stage palettes. VITE_LANDING_THEME picks one at build time
// (neon by default); both are checked here so the flag can be flipped at any time.
for (const palette of [neon, gov]) {
  console.log(`\nlanding stage: ${palette.name}${palette.name === "neon" ? " (default)" : ""}`);
  const pairs = checkPalettePairs(palette);
  for (const r of pairs) console.log(line(r));
  results.push(...pairs);
  paletteProblems.push(...checkPaletteRules(palette));
}

const failed = results.filter((r) => !r.pass);
for (const p of paletteProblems) console.log(`PALETTE ${p}`);

if (failed.length || paletteProblems.length) {
  console.error(`\n${failed.length} contrast failure(s), ${paletteProblems.length} palette/colour-use problem(s).`);
  process.exit(1);
}
console.log(`\nAll ${results.length} pairs pass WCAG AA. Palette is inside the four allowed families.`);
