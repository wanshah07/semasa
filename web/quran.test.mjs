// Ayat al-Quran: the page fetches a verse to the same words as the worker (rules/quran_cases.json, answers recorded from
// the two sources), never cuts or alters it, and the renderer's credit lines are the rules' own.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { glossarySource } from "./glossaryInline.mjs";

const here = new URL(".", import.meta.url);
const rulesText = readFileSync(new URL("../rules/compliance.json", here), "utf8");
const rules = JSON.parse(rulesText);
const doc = JSON.parse(readFileSync(new URL("../rules/quran_cases.json", here), "utf8"));
// Node needs an import attribute for JSON that Vite does not: inline the rules, as the other suites do
const dir = mkdtempSync(join(tmpdir(), "qrn-"));
writeFileSync(join(dir, "compliance.js"), readFileSync(new URL("src/lib/compliance.js", here), "utf8").replace(/^import RULES from .*$/m, `const RULES = ${rulesText};`));
writeFileSync(join(dir, "glossary.js"), glossarySource());
writeFileSync(join(dir, "quran.js"), readFileSync(new URL("src/lib/quran.js", here), "utf8").replace('from "./compliance"', 'from "./compliance.js"'));
const { fetchAyat, skeleton, cleanArabic, QuranError } = await import(pathToFileURL(join(dir, "quran.js")).href);
const { ayatRef, ayatLabel, normaliseSlides } = await import(pathToFileURL(join(dir, "compliance.js")).href);

let n = 0;
const fake = (down) => async (url) => (down.some((d) => url.includes(d)) || !(url in doc.responses)
  ? { status: 503, json: async () => null } : { status: 200, json: async () => doc.responses[url] });
for (const c of doc.cases) {
  let got;
  try { got = { out: await fetchAyat(c.ref, c.stream, fake(c.down)) }; } catch (e) { assert.ok(e instanceof QuranError, String(e)); got = { error: e.message }; }
  assert.deepEqual(got, "out" in c ? { out: c.out } : { error: c.error }, `${c.ref} ${c.stream} down=${c.down}`);
  n++;
}
// the 114 surahs and their 6,236 ayat
assert.equal(rules.quran.surahs.length, 114);
assert.equal(rules.quran.surahs.reduce((a, s) => a + s[1], 0), 6236);
assert.deepEqual(ayatRef("2:286"), [2, 286, 286]);
assert.equal(ayatRef("2:287"), null, "Al-Baqarah has 286 ayat");
assert.equal(ayatRef("115:1"), null);
assert.equal(ayatRef("9:1-4"), null, "at most three ayat on a slide");
assert.equal(ayatRef("2:169-168"), null, "a range runs forwards");
assert.equal(ayatLabel("103:1-3"), "Al-'Asr 103:1-3");
// the Bismillah before a surah is not part of its first ayat; in Al-Fatihah it is the first ayat
const B = rules.quran.bismillah;
assert.equal(cleanArabic(`${B} قُلْ هُوَ ٱللَّهُ أَحَدٌ`, 112, 1), "قُلْ هُوَ ٱللَّهُ أَحَدٌ");
assert.equal(cleanArabic("﻿" + B, 1, 1), B);
assert.equal(cleanArabic(`${B} قُلْ هُوَ ٱللَّهُ أَحَدٌ`, 112, 2), `${B} قُلْ هُوَ ٱللَّهُ أَحَدٌ`, "only before ayat 1");
assert.equal(skeleton("ٱلسَّمَٰوَٰتِ"), skeleton("ٱلسَّمَـٰوَٰتِ"), "a tatweel carrier is not a letter");
assert.notEqual(skeleton("قُلْ هُوَ ٱللَّهُ أَحَدٌ"), skeleton("قُلْ أَعُوذُ بِرَبِّ ٱلنَّاسِ"));
// a slide keeps a verse only with a reference, and the label is worked out, never taken from what was stored
const [kept] = normaliseSlides([{ ayat: "2:168", ayat_ar: "x", ayat_tr: "y", ayat_ed: "ms.basmeih@alquran.cloud", ayat_ok: "1", ayat_label: "An-Nas 114:1" }]);
assert.deepEqual(kept, { title: "", points: [], ayat: "2:168", ayat_ar: "x", ayat_tr: "y", ayat_ed: "ms.basmeih@alquran.cloud", ayat_ok: "1", ayat_label: "Al-Baqarah 2:168" });
assert.deepEqual(normaliseSlides([{ title: "A", ayat_ar: "x", ayat_tr: "y", ayat_ok: "1" }]), [{ title: "A", points: [] }], "verse words with no reference are dropped");
assert.deepEqual(normaliseSlides([{ title: "A", ayat: "2:999", ayat_ed: "made.up" }]), [{ title: "A", points: [], ayat: "2:999" }], "a reference that does not exist gets no label");
// the renderer: its credit lines are the rules' own, the verse card ignores the look, and it never cuts an Arabic word
const studio = readFileSync(new URL("src/lib/cards/studio.js", here), "utf8");
const { specsFor, AYAT_CREDIT } = await import("./src/lib/cards/studio.js");
for (const ed of Object.values(rules.quran.editions)) assert.equal(AYAT_CREDIT[ed.id], ed.credit, ed.id);
const verse = { title: "Peringatan", points: [], ayat: "2:168", ayat_label: "Al-Baqarah 2:168", ayat_ar: "ar", ayat_tr: "tr", ayat_ed: "ms.basmeih@alquran.cloud" };
for (const look of ["grid", "era", "photo", "image", "hand"]) {
  const specs = specsFor([{ title: "Kulit", points: [] }, { ...verse, template: "g_stat" }, { title: "Tutup", points: ["a"] }], { look, bg: "https://x/p.jpg", citation: "NPRA" });
  assert.equal(specs[1].template, "q_ayat", look);
  assert.deepEqual(specs[1].ayat, { ref: "2:168", label: "Al-Baqarah 2:168", ar: "ar", tr: "tr", ed: "ms.basmeih@alquran.cloud" });
  assert.ok(!specs[1].bg && !specs[1].mascot, "no ground and no mascot on a verse card");
}
assert.equal(specsFor([{ title: "", points: [], ayat: "112:1" }], { look: "grid" }).length, 1, "a slide with only a verse is drawn");
const painter = studio.slice(studio.indexOf("async function renderAyatCard"), studio.indexOf("/* A design's two colours"));
assert.ok(painter.length > 500 && !/hardSplit|toUpperCase\(\)\s*\+|slice\(0,/.test(painter.replace(/heading = [^\n]+/, "")), "the verse is never cut, sliced or re-cased");
assert.ok(!/gWrap\(ctx, arabic/.test(painter) && /ayatWrap\(ctx, arabic/.test(painter), "the Arabic has its own whole-word wrapper");
assert.ok(/AmiriQuran-arabic\.woff2/.test(readFileSync(new URL("public/cards/fonts.css", here), "utf8")), "the Quran face is in the card fonts");
console.log(`quran: ${n} fetch cases and the verse rules pass`);
