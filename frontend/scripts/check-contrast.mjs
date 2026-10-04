// `npm run contrast`: fails if any text/background pair we use is below WCAG AA, in either theme,
// or if the palette leaves the four allowed hue families. Reads src/design/tokens.json.
import tokens from "../src/design/tokens.json" with { type: "json" };
import { checkPairs, checkPalette, checkUseRules, contrast, MIN_RATIO } from "../src/design/contrast.js";
import landing from "../src/landing/palette.json" with { type: "json" };

const results = checkPairs(tokens);
const failed = results.filter((r) => !r.pass);
const paletteProblems = [...checkPalette(tokens), ...checkUseRules(tokens)];

for (const theme of Object.keys(tokens.themes)) {
  console.log(`\n${theme} theme`);
  for (const r of results.filter((x) => x.theme === theme)) {
    const mark = r.pass ? "ok  " : "FAIL";
    console.log(`  ${mark} ${r.ratio.toFixed(2).padStart(5)}:1 (min ${r.min})  ${r.label}  [${r.fg} on ${r.bg}]`);
  }
}

// The landing page (/welcome) has its own dark stage palette: src/landing/palette.json.
console.log("\nlanding stage");
for (const pair of landing.pairs) {
  const [fg, bg] = [landing.colors[pair.fg], landing.colors[pair.bg]];
  if (!fg || !bg) throw new Error(`Landing pair "${pair.label}" uses unknown colour ${pair.fg}/${pair.bg}`);
  const ratio = contrast(fg, bg);
  const min = MIN_RATIO[pair.kind];
  const result = { theme: "landing", ...pair, ratio, min, pass: ratio >= min };
  results.push(result);
  if (!result.pass) failed.push(result);
  if (landing.decorative.includes(pair.fg)) paletteProblems.push(`landing: ${pair.label}: "${pair.fg}" is decorative only`);
  console.log(`  ${result.pass ? "ok  " : "FAIL"} ${ratio.toFixed(2).padStart(5)}:1 (min ${min})  ${pair.label}  [${pair.fg} on ${pair.bg}]`);
}
for (const p of paletteProblems) console.log(`PALETTE ${p}`);

if (failed.length || paletteProblems.length) {
  console.error(`\n${failed.length} contrast failure(s), ${paletteProblems.length} palette/colour-use problem(s).`);
  process.exit(1);
}
console.log(`\nAll ${results.length} pairs pass WCAG AA. Palette is inside the four allowed families.`);
