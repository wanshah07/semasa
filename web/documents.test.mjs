/* Documents from the FAQ and the brain: the shared rules, the material and the request (src/lib/documents.js) and the Word file
   (src/lib/docxWrite.js), read back with the Word reader the FAQ bar already uses. `npm test`. */
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { unzipSync, strFromU8 } from "fflate";
import { DOCX_MIME, buildDocx, docFileName } from "./src/lib/docxWrite.js";
import { docxToText } from "./src/lib/officeText.js";

const here = new URL("./", import.meta.url);
// Node needs an import attribute for JSON that Vite does not; inline the rules into a temporary copy of the module instead.
const rules = readFileSync(new URL("../rules/documents.json", here), "utf8");
const dir = mkdtempSync(join(tmpdir(), "documents-"));
writeFileSync(join(dir, "documents.mjs"), readFileSync(new URL("./src/lib/documents.js", here), "utf8").replace(/import RULES from [^\n]+\n/, `const RULES = ${rules};\n`));
const { DOC_TYPES, LIMITS, TYPE_IDS, assembleSource, docToText, docWarnings, entryText, faqText, requestRow, validateRequest } = await import(pathToFileURL(join(dir, "documents.mjs")).href);

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const py = readFileSync(new URL("../backend/semasa/brain_docs.py", here), "utf8");
const sql = readFileSync(new URL("../supabase/037_brain_docs.sql", here), "utf8");

const doc = (over = {}) => ({
  lang: "ms", type: "sop_draft", title: "SOP Penerimaan Bahan & Label <1>", status: "DRAF UNTUK SEMAKAN",
  disclaimer: "Draf ini dijana oleh AI (Semasa).", meta: [["Jenis dokumen", "Draf SOP"], ["Status", "DRAF UNTUK SEMAKAN"], ["Versi", "[Perlu pengesahan]"]],
  generic: { to_confirm: "Perkara yang perlu disahkan", conflicts: "Percanggahan", source_check: "Semakan sumber", flags: "Semak: frasa", page: "Halaman", truncated: "Bahan terlalu panjang." },
  sections: [
    { key: "purpose", heading: "Tujuan", kind: "paragraphs", paragraphs: ["Mengawal penerimaan bahan.", "Baris dua\nbaris tiga [Perlu pengesahan] tamat."] },
    { key: "refs", heading: "Rujukan", kind: "bullets", bullets: ["Klausa 17(6)(j)", "[Perlu pengesahan]"] },
    { key: "procedure", heading: "Prosedur", kind: "table", columns: ["Bil.", "Langkah", "Tanggungjawab"], rows: [["1", "Periksa label & nombor lot", "Pekerja"], ["2", "Rujuk kepada supervisor", "[Perlu pengesahan]"]] },
  ],
  to_confirm: ["Kaedah pengasingan"], conflicts: ["A kata X, B kata Y"], source_check: ["JAKIM-9999"], flags: ["Bahan ini adalah halal."], truncated: false, ...over,
});

t("the types are the worker's types and the database's: one list in three places", () => {
  assert.equal(TYPE_IDS.length, 14);
  for (const id of TYPE_IDS) { assert.ok(py.includes("RULES_PATH") && sql.includes(`'${id}'`), id); }
  const listed = [...sql.match(/doc_type in \(([^)]*)\)/s)[1].matchAll(/'([a-z_]+)'/g)].map((m) => m[1]);
  assert.deepEqual([...listed].sort(), [...TYPE_IDS].sort());
  assert.ok(DOC_TYPES.every((x) => x.label[0] && x.label[1] && x.description[0] && x.description[1]));
  assert.equal(DOC_TYPES.find((x) => x.id === "custom").sections.length, 0);
});

t("the limit the page warns at is the one the worker reads", () => {
  assert.equal(Number(py.match(/MAX_SOURCE = ([\d_]+)/)[1].replaceAll("_", "")), LIMITS.read);
  assert.equal(Number(sql.match(/char_length\(source_text\) <= (\d+)/)[1]), LIMITS.row);
});

t("an Otak entry becomes material by its kind, and an FAQ by its question and answer", () => {
  assert.equal(entryText({ kind: "faq", title: "Logo", category: "halal", question: "Boleh tukar warna?", answer: "Boleh, Klausa 40(2)", source_url: "https://x.my/a" }),
    "FAQ: Logo\nKategori: halal\nSoalan: Boleh tukar warna?\nJawapan: Boleh, Klausa 40(2)\nSumber: https://x.my/a");
  assert.equal(entryText({ kind: "skill", title: "Semak", data: { when: "Sebelum beli", steps: ["Buka Quest3+", "Cari nombor"] } }), "Skill: Semak\nBila guna: Sebelum beli\nLangkah 1: Buka Quest3+\nLangkah 2: Cari nombor");
  assert.equal(entryText({ kind: "checklist", title: "Lancar", data: { items: ["Label", "PIF"] } }), "Senarai semak: Lancar\n- Label\n- PIF");
  assert.equal(entryText({ kind: "note", title: "N", summary: "ringkas", body: "isi" }), "Nota: N\nringkas\nisi");
  assert.equal(entryText({ kind: "note", title: "N", summary: "sama", body: "sama" }), "Nota: N\nsama");
  assert.equal(faqText("S?", "J.", "halal"), "Kategori: halal\nSoalan: S?\nJawapan: J.");
});

t("the material numbers each part so the draft can cite it, skips the empty and says when it is more than is read", () => {
  const s = assembleSource({ items: [{ kind: "faq", id: "1", title: "FAQ A", text: "isi A" }, { kind: "note", id: "2", title: "Kosong", text: "  " }, { kind: "note", id: "3", title: "Nota C", text: "isi C" }], text: "fakta saya" });
  assert.equal(s.text, "[Bahan 1: FAQ A]\nisi A\n\n-----\n\n[Bahan 2: Nota C]\nisi C\n\n-----\n\n[Bahan 3: Fakta ditampal]\nfakta saya");
  assert.deepEqual(s.refs.map((r) => r.title), ["FAQ A", "Nota C", "Fakta ditampal"]);
  assert.equal(s.over, false);
  const big = assembleSource({ items: [{ kind: "note", title: "B", text: "x".repeat(LIMITS.read + 5) }] });
  assert.ok(big.over && !big.cut);
  const huge = assembleSource({ text: "y".repeat(LIMITS.row + 100) });
  assert.ok(huge.cut && huge.text.length === LIMITS.row);
});

t("a request is checked in words and becomes a pending row, with an own structure only for 'custom'", () => {
  const source = assembleSource({ text: "Pekerja receiving memeriksa label bahan." });
  assert.deepEqual(validateRequest({ type: "sop_draft", lang: "both", source }), []);
  assert.equal(validateRequest({ type: "x", lang: "fr", source: { text: "" } }).length, 3);
  assert.equal(validateRequest({ type: "custom", lang: "ms", source, structure: " " }).length, 1);
  const row = requestRow({ type: "faq_pack", lang: "en", title: "  FAQ  halal ", note: "n".repeat(900), structure: "ignored", source, userId: "u1" });
  assert.equal(row.status, "pending"); assert.equal(row.title, "FAQ halal"); assert.equal(row.note.length, LIMITS.note); assert.equal(row.custom_structure, "");
  assert.deepEqual(row.result, {}); assert.equal(row.created_by, "u1"); assert.equal(requestRow({ type: "custom", lang: "ms", structure: "A | b", source }).custom_structure, "A | b");
});

t("the Word file is a valid package that the Word reader reads back, with the marker, the table and the lists in it", () => {
  const bytes = buildDocx(doc());
  const parts = unzipSync(bytes);
  assert.deepEqual(Object.keys(parts).sort(), ["[Content_Types].xml", "_rels/.rels", "docProps/core.xml", "word/_rels/document.xml.rels", "word/document.xml", "word/footer1.xml", "word/header1.xml", "word/styles.xml"]);
  assert.equal(Object.keys(parts)[0], "[Content_Types].xml");                       // the content types come first in the package
  for (const [name, data] of Object.entries(parts)) assertWellFormed(strFromU8(data), name);
  const text = docxToText(bytes).text.split("\n");
  assert.equal(text[0], "SOP Penerimaan Bahan & Label <1>");                          // & and < survive the escaping
  assert.ok(text.includes("DRAF UNTUK SEMAKAN") && text.includes("Versi | [Perlu pengesahan]"));
  assert.ok(text.includes("Tujuan") && text.includes("• Klausa 17(6)(j)") && text.includes("Bil. | Langkah | Tanggungjawab"));
  assert.ok(text.includes("2 | Rujuk kepada supervisor | [Perlu pengesahan]"));
  assert.ok(text.includes("Perkara yang perlu disahkan") && text.includes("• Kaedah pengasingan") && text.includes("• A kata X, B kata Y"));
  assert.ok(text.includes("Semakan sumber") && text.includes("JAKIM-9999") && text.includes("• Bahan ini adalah halal."));
  assert.ok(text.includes("Baris dua baris tiga [Perlu pengesahan] tamat."));          // a line break inside a paragraph stays inside it
});

t("the marker is highlighted wherever it stands, the header says draft on every page, the footer carries the disclaimer", () => {
  const parts = unzipSync(buildDocx(doc()));
  const body = strFromU8(parts["word/document.xml"]);
  assert.equal((body.match(/<w:highlight w:val="yellow"\/>/g) || []).length, 4);       // one in the paragraph, the bullet, two table cells (meta, procedure)
  assert.ok(strFromU8(parts["word/header1.xml"]).includes("DRAF UNTUK SEMAKAN") && strFromU8(parts["word/footer1.xml"]).includes("Draf ini dijana oleh AI"));
  assert.ok(strFromU8(parts["word/footer1.xml"]).includes('w:instr=" PAGE "'));
  assert.ok(body.includes("<w:tblHeader/>") && body.includes('w:orient') === false);
});

t("a table of five or more columns turns the page to landscape and the column widths add up to the page", () => {
  const wide = doc({ sections: [{ key: "m", heading: "Peta", kind: "table", columns: ["A", "B", "C", "D", "E", "F"], rows: [["a".repeat(60), "b", "c", "d", "e", "f"]] }] });
  const body = strFromU8(unzipSync(buildDocx(wide))["word/document.xml"]);
  assert.ok(body.includes('w:w="16838" w:h="11906" w:orient="landscape"'));
  const grid = [...body.matchAll(/<w:gridCol w:w="(\d+)"\/>/g)].map((m) => Number(m[1]));
  const total = Number(body.match(/<w:tblW w:w="(\d+)" w:type="dxa"\/>/g).at(-1).match(/\d+/)[0]);
  const wideGrid = grid.slice(-6);
  assert.equal(wideGrid.reduce((a, b) => a + b, 0), total); assert.equal(total, 16838 - 2160);
  assert.ok(wideGrid[0] > wideGrid[1]);
});

t("hostile text cannot break the package: control characters go, markup is escaped, nothing is executed", () => {
  const evil = doc({ title: "T\u0000\u0008<script>alert(1)</script>\"&", sections: [{ key: "p", heading: "H<>", kind: "paragraphs", paragraphs: ["a\u000Bb ]]> <w:p/>"] }] });
  const parts = unzipSync(buildDocx(evil));
  for (const [name, data] of Object.entries(parts)) assertWellFormed(strFromU8(data), name);
  const body = strFromU8(parts["word/document.xml"]);
  assert.ok(!body.includes("<script>") && !body.includes("\u0000") && body.includes("&lt;script&gt;"));
  assert.throws(() => buildDocx({}), /not a drafted document/);
});

t("the file name is the title, the language and the date in Malaysia", () => {
  assert.equal(docFileName(doc(), new Date("2026-10-11T17:00:00Z")), "sop-penerimaan-bahan-label-1-ms-draf-2026-10-12.docx");         // 01:00 MYT the next day
  assert.equal(docFileName({ lang: "en", title: "Ünïcode FAQ" }, new Date("2026-10-11T05:00:00Z")), "unicode-faq-en-draft-2026-10-11.docx");
  assert.equal(docFileName({}, new Date("2026-10-11T05:00:00Z")), "dokumen-ms-draf-2026-10-11.docx");
  assert.ok(DOCX_MIME.endsWith("wordprocessingml.document"));
});

t("what a reviewer looks at first, and a plain-text copy that keeps the lists and the disclaimer", () => {
  assert.deepEqual(docWarnings(doc()), { check: 1, wording: 1, confirm: 1, conflicts: 1, truncated: false });
  assert.deepEqual(docWarnings(null), { check: 0, wording: 0, confirm: 0, conflicts: 0, truncated: false });
  const txt = docToText(doc());
  assert.ok(txt.startsWith("SOP Penerimaan Bahan & Label <1>\nDRAF UNTUK SEMAKAN\n\nJenis dokumen: Draf SOP"));
  assert.ok(txt.includes("PROSEDUR\nBil. | Langkah | Tanggungjawab\n1 | Periksa label & nombor lot | Pekerja") && txt.includes("PERKARA YANG PERLU DISAHKAN\n- Kaedah pengasingan"));
  assert.ok(txt.endsWith("Draf ini dijana oleh AI (Semasa)."));
});

/** A small well-formedness check: tags balance and every attribute value is quoted (node has no DOMParser). */
function assertWellFormed(xml, name) {
  assert.ok(!/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/.test(xml), `${name}: control character`);
  const stack = [];
  for (const m of xml.matchAll(/<(\/?)([A-Za-z][\w:.-]*)((?:\s+[\w:.-]+="[^"]*")*)\s*(\/?)>/g)) {
    if (m[4]) continue;
    if (m[1]) assert.equal(stack.pop(), m[2], `${name}: </${m[2]}> closes the wrong tag`);
    else stack.push(m[2]);
  }
  assert.equal(stack.length, 0, `${name}: unclosed ${stack.join(",")}`);
  assert.ok(!/<[^>]*[^"\w\s/?=-][^>]*"[^"]*$/.test(""), name);
  const stripped = xml.replace(/<\?xml[^>]*\?>/, "").replace(/<[^>]+>/g, "");
  assert.ok(!/[<>]/.test(stripped) && !/&(?!amp;|lt;|gt;|quot;|apos;|#\d+;)/.test(stripped), `${name}: bare markup characters in text`);
}

console.log(`documents.test.mjs: ${n} groups OK`);
