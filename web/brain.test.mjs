/* Otak AI: what a drop becomes, filtering and search, an edit, and the exports (lib/brain.js). `npm test`. */
import assert from "node:assert/strict";
import { brainSummary, categoriesOf, copyText, entryRow, exportFiles, filterEntries, inboxLabel, isWalled, rowsFromPaste, tagCloud, tagsFrom, toMarkdown, toSkillMd, urlsIn, validateEntry, variablesIn } from "./src/lib/brain.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

t("addresses: found once each, trailing punctuation off, query strings kept", () => {
  assert.deepEqual(urlsIn("Lihat https://a.my/x?id=1&b=2, dan (https://b.com/y). Ulang https://a.my/x?id=1&b=2!"), ["https://a.my/x?id=1&b=2", "https://b.com/y"]);
  assert.deepEqual(urlsIn(""), []);
});

t("a paste: bare-address lines become links, the rest one text row, the options ride on every row", () => {
  const { rows, cut } = rowsFromPaste("https://npra.gov.my/a\nCatatan saya tentang notis ini.\nhttps://www.threads.net/@x/post/1\nSambungan catatan https://c.com di tengah", { hint: "faq", note: " untuk klien " });
  assert.deepEqual(rows.map((r) => r.source_kind), ["link", "link", "text"]);
  assert.equal(rows[2].body, "Catatan saya tentang notis ini.\nSambungan catatan https://c.com di tengah");
  assert.ok(rows.every((r) => r.hint === "faq" && r.note === "untuk klien")); assert.equal(cut, false);
  assert.deepEqual(rowsFromPaste("https://a.my/x", { scrape: true }).rows.map((r) => r.source_kind), ["scrape"]);
  assert.equal(rowsFromPaste("x", { hint: "bogus" }).rows[0].hint, "");
  assert.deepEqual(rowsFromPaste("  \n ").rows, []);
});

t("a long paste is cut and says so; too many links are capped and counted", () => {
  const long = rowsFromPaste("a".repeat(70_000));
  assert.equal(long.cut, true); assert.equal(long.rows[0].body.length, 60_000);
  const many = rowsFromPaste(Array.from({ length: 45 }, (_, i) => `https://x.my/${i}`).join("\n"));
  assert.equal(many.rows.length, 40); assert.equal(many.extra, 5);
});

t("social hosts that need a login are named, a news site is not", () => {
  assert.ok(isWalled("https://www.instagram.com/p/x") && isWalled("https://m.facebook.com/a") && isWalled("https://x.com/u/status/1") && isWalled("https://www.threads.net/@u"));
  assert.ok(!isWalled("https://npra.gov.my") && !isWalled("https://notinstagram.com") && !isWalled("not a url"));
});

const E = [
  { id: "1", kind: "faq", category: "halal", title: "Logo halal boleh ditukar warna?", summary: "Boleh", body: "Boleh, Klausa 40(2)", question: "Boleh tukar warna logo?", answer: "Boleh, Klausa 40(2)", tags: ["logo", "halal"], pinned: false, confidence: 0.9, created_at: "2026-10-09T01:00:00Z" },
  { id: "2", kind: "skill", category: "kosmetik", title: "Semak notifikasi di Quest3+", summary: "Langkah semak", body: "1. Buka Quest3+", tags: ["quest3", "npra"], pinned: true, confidence: 0.5, created_at: "2026-10-01T01:00:00Z", data: { when: "Sebelum beli stok", steps: ["Buka Quest3+", "Cari nombor"] } },
  { id: "3", kind: "prompt", category: "pemasaran", title: "Ringkas notis NPRA", summary: "Prompt", body: "Ringkaskan {{notis}} untuk {{audiens}}", tags: ["npra"], confidence: 0.8, created_at: "2026-10-10T01:00:00Z", data: { use: "ringkas" } },
  { id: "4", kind: "note", category: "kosmetik", title: "Régulasi baharu", summary: "x", body: "Notis tentang kosmetik", tags: [], edited: true, confidence: 0.2, created_at: "2026-10-05T01:00:00Z" },
];

t("filter: kind, category, tag, pinned; pinned first then newest", () => {
  assert.deepEqual(filterEntries(E).map((e) => e.id), ["2", "3", "1", "4"]);
  assert.deepEqual(filterEntries(E, { kind: "faq" }).map((e) => e.id), ["1"]);
  assert.deepEqual(filterEntries(E, { category: "kosmetik" }).map((e) => e.id), ["2", "4"]);
  assert.deepEqual(filterEntries(E, { tag: "npra" }).map((e) => e.id), ["2", "3"]);
  assert.deepEqual(filterEntries(E, { pinned: true }).map((e) => e.id), ["2"]);
});

t("search: every word must appear, accents and case ignored, tags and answers count", () => {
  assert.deepEqual(filterEntries(E, { q: "regulasi" }).map((e) => e.id), ["4"]);
  assert.deepEqual(filterEntries(E, { q: "KLAUSA 40" }).map((e) => e.id), ["1"]);
  assert.deepEqual(filterEntries(E, { q: "quest3 buka" }).map((e) => e.id), ["2"]);
  assert.deepEqual(filterEntries(E, { q: "npra tiada" }).map((e) => e.id), []);
  assert.deepEqual(filterEntries(E, { q: "  " }).length, 4);
});

t("summary: counts by kind and category, what waits, what needs the text, what is unsure", () => {
  const s = brainSummary(E, [{ status: "pending" }, { status: "working" }, { status: "needs_text" }, { status: "error" }, { status: "done" }]);
  assert.equal(s.total, 4); assert.deepEqual(s.byKind, { note: 1, faq: 1, skill: 1, prompt: 1, reference: 0, checklist: 0 });
  assert.deepEqual(s.byCategory, { halal: 1, kosmetik: 2, pemasaran: 1 });
  assert.equal(s.waiting, 2); assert.equal(s.needsText, 1); assert.equal(s.failed, 1); assert.equal(s.pinned, 1);
  assert.equal(s.lowConfidence, 1);                                                   // id 2 (0.5); id 4 is 0.2 but Wan edited it
});

t("categories: the configured list, then any a filed entry still carries", () => {
  assert.deepEqual(categoriesOf([{ category: "lama" }, { category: "halal" }], ["Halal", "lain"]), ["halal", "lain", "lama"]);
  assert.ok(categoriesOf([], []).includes("regulatori"));
  assert.deepEqual(tagCloud(E).slice(0, 2), [{ tag: "npra", count: 2 }, { tag: "halal", count: 1 }]);
});

t("tags and variables", () => {
  assert.deepEqual(tagsFrom("A, b; #C\nb"), ["a", "b", "c"]); assert.deepEqual(tagsFrom(["X", " "]), ["x"]);
  assert.deepEqual(variablesIn("{{a}} {{ b }} {{a}} {{}}"), ["a", "b"]);
});

t("validate: each kind needs its own words", () => {
  assert.deepEqual(validateEntry({ kind: "note", title: "T", body: "b" }), []);
  assert.deepEqual(validateEntry({ kind: "faq", title: "T", question: "Q", answer: "" }), ["question/answer"]);
  assert.deepEqual(validateEntry({ kind: "note", title: " ", body: "" }), ["title", "body"]);
  assert.deepEqual(validateEntry({ kind: "zzz", title: "T", body: "b" }), ["kind"]);
});

t("an edit: the kind's own fields are rebuilt from what was typed and `edited` is set", () => {
  const sk = entryRow({ kind: "skill", title: " Semak ", category: "Kosmetik", when: "Sebelum beli", steps: "1. Buka\n- Cari\n\nCatat", tags: "A, b", body: "lama" });
  assert.deepEqual(sk.data, { when: "Sebelum beli", steps: ["Buka", "Cari", "Catat"] });
  assert.equal(sk.body, "1. Buka\n2. Cari\n3. Catat"); assert.equal(sk.edited, true); assert.equal(sk.category, "kosmetik"); assert.deepEqual(sk.tags, ["a", "b"]);
  const pr = entryRow({ kind: "prompt", title: "P", body: "Tulis {{topik}}", use: "tulis" });
  assert.deepEqual(pr.data, { use: "tulis", variables: ["topik"] });
  const ck = entryRow({ kind: "checklist", title: "C", items: "[ ] Label\n- PIF" });
  assert.equal(ck.body, "- [ ] Label\n- [ ] PIF"); assert.deepEqual(ck.data.items, ["Label", "PIF"]);
  const fq = entryRow({ kind: "faq", title: "F", question: " Q? ", answer: " A " });
  assert.equal(fq.body, "A"); assert.equal(fq.question, "Q?");
  assert.equal(entryRow({ kind: "bogus", title: "x", body: "y" }).kind, "note");
});

t("copy: a prompt is its words, an FAQ is the question and the answer", () => {
  assert.equal(copyText(E[2]), "Ringkaskan {{notis}} untuk {{audiens}}"); assert.equal(copyText(E[0]), "Boleh tukar warna logo?\n\nBoleh, Klausa 40(2)");
});

t("markdown: front matter, the question as the heading of an FAQ, a prompt fenced", () => {
  const md = toMarkdown(E[0]); assert.ok(md.startsWith("---\ntitle: \"Logo halal boleh ditukar warna?\"\nkind: faq\ncategory: halal\ntags: [\"logo\", \"halal\"]\n---")); assert.ok(md.includes("## Boleh tukar warna logo?"));
  const pm = toMarkdown(E[2]); assert.ok(pm.includes("```\nRingkaskan {{notis}} untuk {{audiens}}\n```") && pm.includes("**Untuk / For:** ringkas"));
});

t("a SKILL.md: a slug name, a one-line description with when to use it, the steps as the body", () => {
  const s = toSkillMd(E[1]);
  assert.ok(s.startsWith("---\nname: semak-notifikasi-di-quest3\ndescription: \"Langkah semak Use when: Sebelum beli stok\"\n---\n\n# Semak notifikasi di Quest3+"));
  assert.ok(s.endsWith("1. Buka Quest3+\n"));
});

t("export: skills as <slug>/SKILL.md, the rest by kind, a repeated title gets a number", () => {
  const files = exportFiles([...E, { ...E[0], id: "5" }]);
  assert.deepEqual(files.map((f) => f.name), ["faq/logo-halal-boleh-ditukar-warna.md", "skills/semak-notifikasi-di-quest3/SKILL.md", "prompt/ringkas-notis-npra.md", "note/regulasi-baharu.md", "faq/logo-halal-boleh-ditukar-warna-2.md"]);
});

t("the inbox line: a host for a link, a file name for a file, the first words of a text", () => {
  assert.equal(inboxLabel({ source_kind: "link", url: "https://www.npra.gov.my/a" }), "npra.gov.my");
  assert.equal(inboxLabel({ source_kind: "file", file_name: "SOP.pdf" }), "SOP.pdf");
  assert.equal(inboxLabel({ source_kind: "text", body: "  satu\n dua " }), "satu dua");
});

console.log(`brain.test.mjs: ${n} groups OK`);
