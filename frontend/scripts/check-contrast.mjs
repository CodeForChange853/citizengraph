// `npm run contrast`: fails if any text/background pair we use is below WCAG AA, in either theme,
// or if the palette leaves the four allowed hue families. Reads src/design/tokens.json.
import tokens from "../src/design/tokens.json" with { type: "json" };
import { checkPairs, checkPalette, checkUseRules } from "../src/design/contrast.js";

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
for (const p of paletteProblems) console.log(`PALETTE ${p}`);

if (failed.length || paletteProblems.length) {
  console.error(`\n${failed.length} contrast failure(s), ${paletteProblems.length} palette/colour-use problem(s).`);
  process.exit(1);
}
console.log(`\nAll ${results.length} pairs pass WCAG AA. Palette is inside the four allowed families.`);
