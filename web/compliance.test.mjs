// Runs rules/cases.json against web/src/lib/compliance.js (the same cases pytest runs
// against backend/semasa/compliance.py) and, with --dump, prints every case's flags so
// the two scanners can be compared line by line. `npm test`.
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const here = new URL(".", import.meta.url);
const rules = readFileSync(new URL("../rules/compliance.json", here), "utf8");
const cases = JSON.parse(readFileSync(new URL("../rules/cases.json", here), "utf8"));
// Node needs an import attribute for JSON that Vite does not; inline the rules instead.
const src = readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/^import RULES from .*$/m, `const RULES = ${rules};`);
const tmp = join(mkdtempSync(join(tmpdir(), "cmp-")), "compliance.mjs");
writeFileSync(tmp, src);
const { scan, normaliseSlides } = await import(pathToFileURL(tmp).href);

if (process.argv.includes("--dump")) {
  console.log(JSON.stringify(cases.map((c) => scan(c.post, null, c.schedule || null, c.indo_extra || null))));
  process.exit(0);
}
let failed = 0;
for (const c of cases) {
  const flags = scan(c.post, null, c.schedule || null, c.indo_extra || null);
  const hard = flags.filter((f) => f.hard).map((f) => `${f.where}: ${f.msg}`);
  const soft = flags.filter((f) => !f.hard).map((f) => `${f.where}: ${f.msg}`);
  const e = c.expect, errs = [];
  if ("hard" in e && hard.length !== e.hard) errs.push(`hard ${hard.length} != ${e.hard}`);
  if ("hard_min" in e && hard.length < e.hard_min) errs.push(`hard ${hard.length} < ${e.hard_min}`);
  for (const s of e.contains || []) if (!hard.some((h) => h.includes(s))) errs.push(`missing hard "${s}"`);
  for (const s of e.not_contains || []) if (hard.some((h) => h.includes(s))) errs.push(`unexpected hard "${s}"`);
  for (const s of e.soft_contains || []) if (!soft.some((h) => h.includes(s))) errs.push(`missing soft "${s}"`);
  for (const s of e.soft_not_contains || []) if (soft.some((h) => h.includes(s))) errs.push(`unexpected soft "${s}"`);
  if (errs.length) { failed++; console.log(`FAIL ${c.name}: ${errs.join("; ")}\n  ${hard.concat(soft).join("\n  ")}`); }
}
// text size, font and the mascot's place and size (Wan, 3 Oct 2026): kept only when valid and not the default; the same
// as backend/tests/test_compliance.py::test_a_slides_text_size_font_and_mascot_choices_...
{
  const kept = normaliseSlides([{ title: "A", points: ["x"], type_size: "80", font: "sans", mascot_pos: "bl", mascot_size: "130" }]);
  const wantKept = [{ title: "A", points: ["x"], type_size: "80", font: "sans", mascot_pos: "bl", mascot_size: "130" }];
  if (JSON.stringify(kept) !== JSON.stringify(wantKept)) { failed++; console.log("FAIL slide typography kept", JSON.stringify(kept)); }
  const none = normaliseSlides([{ title: "A", points: ["x"], type_size: "100", font: "comic", mascot_pos: "top", mascot_size: "999" }]);
  if (JSON.stringify(none) !== JSON.stringify([{ title: "A", points: ["x"] }])) { failed++; console.log("FAIL slide typography dropped", JSON.stringify(none)); }
}
console.log(`${cases.length - failed}/${cases.length} compliance cases pass`);
process.exit(failed ? 1 : 0);
