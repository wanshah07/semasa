/* The Malay words for the compliance flags (src/lib/complianceBm.js): every label in rules/compliance.json and every fixed
   message in compliance.js has one, the messages built with numbers translate, and a message nobody translated yet is
   shown in English rather than hidden. The scan itself is not touched by any of this (compliance.test.mjs). */
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { MSG_BM, flagWords, msgBm, whereBm } from "./src/lib/complianceBm.js";

const rulesText = readFileSync(new URL("../rules/compliance.json", import.meta.url), "utf8");
const RULES = JSON.parse(rulesText);
// Node needs an import attribute for JSON that Vite does not; inline the rules, as compliance.test.mjs does
const tmp = join(mkdtempSync(join(tmpdir(), "cmpbm-")), "compliance.mjs");
writeFileSync(tmp, readFileSync(new URL("./src/lib/compliance.js", import.meta.url), "utf8").replace(/^import RULES from .*$/m, `const RULES = ${rulesText};`));
const { scan } = await import(pathToFileURL(tmp).href);
let n = 0;
const t = (name, fn) => { fn(); n++; };

t("every label in rules/compliance.json has Malay", () => {
  const labels = [...RULES.hard, ...RULES.cta, ...RULES.soft].map((r) => r.label)
    .concat(["social_src", "aggregator", "not_english", "any_url"].map((k) => RULES[k].label), RULES.indo_soft.map(([, why]) => why));
  const missing = labels.filter((l) => !(l in MSG_BM));
  assert.deepEqual(missing, [], `no Malay for: ${missing.join(" | ")}`);
});

t("every fixed message compliance.js writes has Malay", () => {
  const src = readFileSync(new URL("./src/lib/compliance.js", import.meta.url), "utf8");
  const fixed = [...src.matchAll(/add\((?:true|false), [^,]+, "((?:[^"\\]|\\.)*)"\)/g)].map((m) => JSON.parse(`"${m[1]}"`));
  assert.ok(fixed.length >= 15, "the pattern still finds the messages");
  const missing = fixed.filter((m) => !(m in MSG_BM));
  assert.deepEqual(missing, [], `no Malay for: ${missing.join(" | ")}`);
});

t("messages with numbers and words in them", () => {
  assert.equal(msgBm("2301 chars, over the 2200 limit"), "2301 aksara, melebihi had 2200");
  assert.equal(msgBm("9 hashtags, over the 8 limit"), "9 hashtag, melebihi had 8");
  assert.equal(msgBm('Bahasa Indonesia word "kualitas"'), 'perkataan Bahasa Indonesia "kualitas"');
  assert.equal(msgBm('Bahasa Indonesia word "sekarang ini" (tabung: write "kini")'), 'perkataan Bahasa Indonesia "sekarang ini" (tabung: tulis "kini")');
  assert.match(msgBm('cites "ChemLinked", a blog or news aggregator. Cite the instrument.'), /^memetik "ChemLinked"/);
  assert.equal(msgBm("1 slide of substance between the cover and the closing. At least 3."), "1 slaid berisi antara kulit dan penutup. Sekurang-kurangnya 3.");
  assert.equal(msgBm("Monday carries kosmetik and kajian_kes, and this is makanan. A note, not a block."),
    "Isnin membawa kosmetik dan kajian_kes, dan ini makanan. Nota, bukan sekatan.");
  assert.equal(whereBm("Caption (instagram)"), "Kapsyen (instagram)");
  assert.equal(whereBm("EN variant (facebook)"), "Varian EN (facebook)");
  assert.equal(whereBm("Design 2, slide 3"), "Reka bentuk 2, slaid 3");
  assert.equal(whereBm("Kedudukan"), "Kedudukan", "a name that is already Malay is kept");
});

t("an unknown message stays English, and English pages see the flag as it is", () => {
  assert.equal(msgBm("a rule added tomorrow"), "a rule added tomorrow");
  const f = { hard: true, where: "Caption (threads)", msg: "empty" };
  assert.deepEqual(flagWords(f, "en"), { where: "Caption (threads)", msg: "empty" });
  assert.deepEqual(flagWords(f, "bm"), { where: "Kapsyen (threads)", msg: "kosong" });
  assert.deepEqual(f, { hard: true, where: "Caption (threads)", msg: "empty" }, "the flag is not changed");
});

t("every flag a real scan raises has Malay", () => {
  const post = { stream: "regulab", domain: "kosmetik", lang: "bm", channels: ["instagram", "facebook", "threads"],
    text: { bm: { instagram: "Dijamin lulus! Hubungi kami di www.kkmhalalconsultant.com. Kualitas terbaik di Malaysia — link in bio #a #b #c #d #e #f #g #h #i",
      facebook: "", threads: "Tahukah anda? reddit kata begitu." } }, slides: [{ title: "Cover" }, { title: "x" }, { title: "" }] };
  const flags = scan(post, null, { 1: ["kosmetik"] }, [["sekarang ini", "kini"]]);
  assert.ok(flags.length > 5);
  const english = flags.filter((f) => msgBm(f.msg) === f.msg && !/^CTA: '/.test(f.msg));
  assert.deepEqual(english.map((f) => f.msg), []);
});

console.log(`complianceBm: ${n} ok`);
