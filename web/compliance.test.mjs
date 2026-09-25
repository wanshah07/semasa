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
const { scan } = await import(pathToFileURL(tmp).href);

if (process.argv.includes("--dump")) {
  console.log(JSON.stringify(cases.map((c) => scan(c.post, null, c.schedule || null))));
  process.exit(0);
}
let failed = 0;
for (const c of cases) {
  const flags = scan(c.post, null, c.schedule || null);
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
console.log(`${cases.length - failed}/${cases.length} compliance cases pass`);
process.exit(failed ? 1 : 0);
