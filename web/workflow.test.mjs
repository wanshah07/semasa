/* The post workflow's pure parts: stripping the ask out of a caption, and the decision/version records. */
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

// compliance.js imports JSON the way Vite does; inline it for Node (as compliance.test.mjs does)
const here = new URL(".", import.meta.url);
const rules = readFileSync(new URL("../rules/compliance.json", here), "utf8");
const src = readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/import RULES from "[^"]+";/, `const RULES = ${rules};`);
const dir = mkdtempSync(join(tmpdir(), "wf-"));
writeFileSync(join(dir, "compliance.js"), src);
const { stripPromo } = await import(pathToFileURL(join(dir, "compliance.js")).href);
const { withDecision, withVersion, restoreVersion } = await import(new URL("src/lib/workflow.js", here).href);

let n = 0;
const t = (name, fn) => { fn(); n++; };
t("strip removes only the ask", () => {
  const cap = "Notifikasi bukan kelulusan.\n\nNPRA menyemak selepas pasaran. Hubungi kami untuk semakan.\nLayari www.kkmhalalconsultant.com hari ini.\n\n#NPRA";
  const r = stripPromo(cap);
  assert.equal(r.text, "Notifikasi bukan kelulusan.\n\nNPRA menyemak selepas pasaran.\n\n#NPRA");
  assert.deepEqual(r.removed, ["Hubungi kami untuk semakan.", "Layari www.kkmhalalconsultant.com hari ini."]);
  assert.equal(stripPromo("Sumber: https://www.npra.gov.my").text, "Sumber: https://www.npra.gov.my");
});
t("decisions append, capped", () => {
  const d = withDecision({ decisions: [] }, "approved", "", Date.parse("2026-09-24T02:00:00Z"));
  assert.deepEqual(d, [{ at: "2026-09-24T02:00:00.000Z", by: "page", action: "approved" }]);
  const many = { decisions: Array.from({ length: 60 }, (_, i) => ({ action: String(i) })) };
  const out = withDecision(many, "rejected", "salah fakta");
  assert.equal(out.length, 50);
  assert.equal(out.at(-1).note, "salah fakta");
});
t("versions keep the words, restore swaps them", () => {
  const post = { hook: "A", text: { bm: { instagram: "a" } }, citation: "c1", versions: [] };
  const v = withVersion(post, "edited by hand", Date.parse("2026-09-24T02:00:00Z"));
  assert.deepEqual(v[0], { hook: "A", text: { bm: { instagram: "a" } }, citation: "c1", at: "2026-09-24T02:00:00.000Z", why: "edited by hand" });
  const now = { hook: "B", text: { bm: { instagram: "b" } }, citation: "c2", versions: v, decisions: [] };
  const patch = restoreVersion(now, 0, Date.parse("2026-09-25T02:00:00Z"));
  assert.equal(patch.hook, "A");
  assert.equal(patch.versions.length, 2);
  assert.equal(patch.versions[1].hook, "B");                  // what it replaced is kept: nothing is lost
  assert.equal(patch.decisions.at(-1).action, "restored version");
});
console.log(`${n}/3 workflow tests pass`);
