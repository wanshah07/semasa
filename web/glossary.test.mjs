// The glossary (rules/glossary.json) as the page reads it (src/lib/glossary.js): the same answers as backend/semasa/glossary.py on the
// shared cases in rules/glossary_cases.json, plus the page's soft check and the foot's place in the slide shape. `npm test`.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { glossarySource } from "./glossaryInline.mjs";

const here = new URL(".", import.meta.url);
const dir = mkdtempSync(join(tmpdir(), "gl-"));
writeFileSync(join(dir, "glossary.js"), glossarySource());
writeFileSync(join(dir, "compliance.js"), readFileSync(new URL("src/lib/compliance.js", here), "utf8")
  .replace(/^import RULES from .*$/m, `const RULES = ${readFileSync(new URL("../rules/compliance.json", here), "utf8")};`));
const G = await import(pathToFileURL(join(dir, "glossary.js")).href);
const C = await import(pathToFileURL(join(dir, "compliance.js")).href);
const doc = JSON.parse(readFileSync(new URL("../rules/glossary_cases.json", here), "utf8"));
const raw = JSON.parse(readFileSync(new URL("../rules/glossary.json", here), "utf8"));
let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

t("the file is well formed and every wording fits a footnote", () => {
  assert.ok(raw.terms.length >= 40);
  const seen = new Set();
  for (const e of raw.terms) {
    assert.ok(!seen.has(e.id) && e.term.length && e.bm && e.en && e.source && e.label.bm && e.label.en, e.id);
    seen.add(e.id);
    for (const lang of ["bm", "en"]) assert.ok(e[lang].split(/\s+/).length <= 14, `${e.id} ${lang}`);
  }
});

t("the page finds, reads and cleans exactly what the worker does (rules/glossary_cases.json)", () => {
  for (const c of doc.used) {
    assert.deepEqual(G.used(c.text).map(([e, w]) => [e.id, w]), c.used, c.text);
    assert.deepEqual(G.used(c.text, false).map(([e]) => e.id), c.all, c.text);
  }
  for (const c of doc.feet) {
    assert.deepEqual(G.pairsOf(c.foot), c.pairs, c.foot);
    assert.deepEqual([...G.definedIn(c.foot)].sort(), c.defined, c.foot);
    assert.equal(G.cleanFoot(c.foot, "bm"), c.clean_bm, c.foot);
    assert.equal(G.cleanFoot(c.foot, "en"), c.clean_en, c.foot);
  }
  for (const c of doc.captions) {
    assert.deepEqual([...G.definedInCaption(c.caption)].sort(), c.defined);
    assert.equal(G.stripDefinisi(c.caption), c.stripped);
  }
});

const post = (caption, slides) => ({ stream: "regulab", lang: "bm", text: { bm: { instagram: caption, facebook: caption, threads: caption } }, media: [{ id: "m", alt: "x" }], ...(slides ? { slides } : {}) });
const explain = (flags) => flags.filter((f) => f.msg.startsWith("explain ")).map((f) => `${f.where}: ${f.msg}`);

t("an unexplained term is a soft warning, never a block", () => {
  const flags = C.scan(post("Setiap kosmetik perlu PIF yang lengkap."));
  assert.ok(explain(flags).includes('Caption (instagram): explain "PIF": add a footnote (Nota kaki)'));
  assert.ok(!flags.some((f) => f.hard && f.msg.startsWith("explain ")));
  assert.deepEqual(explain(C.scan(post("Setiap kosmetik perlu PIF.\n\nDefinisi: PIF = fail maklumat produk."))), []);
  assert.deepEqual(explain(C.scan(post("KKM dan NPRA umum tarik balik."))), [], "familiar names never ask");
});

t("a slide term is explained by its own foot or by the caption's Definisi line, and the foot is not the slide's own words", () => {
  const word = { title: "Apa itu PIF", points: ["NPRA boleh minta PIF."] };
  assert.ok(explain(C.scan(post("Isi.", [word]))).includes('Slide 1: explain "PIF": add a footnote (Nota kaki)'));
  assert.deepEqual(explain(C.scan(post("Isi.", [{ ...word, foot: "Definisi: PIF = fail" }]))), []);
  assert.deepEqual(explain(C.scan(post("Isi.\n\nDefinisi: PIF = fail.", [word]))), []);
  assert.deepEqual(explain(C.scan(post("Isi.", [{ title: "Satu", points: [], foot: "Definisi: PIF = fail" }]))), []);
});

t("the foot is kept by normaliseSlides, compared by slidesKey and judged like any slide word", () => {
  const s = C.normaliseSlides([{ title: "A", points: ["b"], foot: "  Definisi: PIF = fail  ", footnote: "NPRA" }]);
  assert.deepEqual(s, [{ title: "A", points: ["b"], footnote: "NPRA", foot: "Definisi: PIF = fail" }]);
  assert.notEqual(C.slidesKey([{ title: "A", foot: "x" }]), C.slidesKey([{ title: "A" }]));
  assert.ok(C.slideText(s[0]).includes("Definisi: PIF") && !C.slideBody(s[0]).includes("Definisi"));
  assert.deepEqual(C.normaliseSlides([{ foot: "Definisi: PIF = fail" }]), [{ title: "", points: [], foot: "Definisi: PIF = fail" }]);
  assert.ok(C.scan(post("Isi.", [{ title: "A", points: ["x"], foot: "Hubungi kami" }])).some((f) => f.hard && f.where === "Slide 1"));
});

console.log(`ok - ${n} glossary checks`);
