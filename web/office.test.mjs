/* Word, Excel and CSV reading for the FAQ AI bar (src/lib/officeText.js), against files made by python-docx and openpyxl
   (web/test-fixtures) plus hand-built XML for the cases those tools do not write (cached formula values, inline strings,
   the 1904 date system, hostile input). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { strToU8, zipSync } from "fflate";
import { OFFICE_LIMITS, OfficeError, csvToRows, decodeXml, docxToText, serialToDate, tablePairs, tableText, xlsxToTables } from "./src/lib/officeText.js";

const fx = (n) => new Uint8Array(readFileSync(new URL(`./test-fixtures/${n}`, import.meta.url)));
const fxText = (n) => readFileSync(new URL(`./test-fixtures/${n}`, import.meta.url), "utf8");
let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

const xlsx = (files) => zipSync(Object.fromEntries(Object.entries(files).map(([k, v]) => [k, strToU8(v)])));
const WB = (sheets, extra = "") => `<?xml version="1.0"?><workbook xmlns="x" xmlns:r="r">${extra}<sheets>${sheets.map(([name, id, state]) => `<sheet name="${name}" sheetId="1" ${state ? `state="${state}"` : ""} r:id="${id}"/>`).join("")}</sheets></workbook>`;
const RELS = (m) => `<Relationships>${Object.entries(m).map(([id, tgt]) => `<Relationship Id="${id}" Type="t" Target="${tgt}"/>`).join("")}</Relationships>`;
const SHEET = (rows) => `<worksheet><sheetData>${rows}</sheetData></worksheet>`;

// ---- Word ------------------------------------------------------------------------------------------------------
t("docx: paragraphs in order, runs joined, entities decoded, break and tab become spaces, table rows use ' | '", () => {
  const { text } = docxToText(fx("faq.docx"));
  const lines = text.split("\n");
  assert.equal(lines[0], "Soalan Lazim Logo Halal");
  assert.equal(lines[1], "Soalan 1: Bolehkah syarikat guna logo halal lama? (rujukan: MPPHM & Klausa 40(2))");
  assert.ok(lines.includes("Baris satu Baris dua selepas tab"));
  assert.ok(lines.includes("Soalan | Jawapan"));
  assert.ok(lines.includes("Berapa lama sijil halal sah? | Dua tahun."));
  assert.equal(lines[lines.length - 1], "Penutup — café & kopi <ok>");
});

t("docx: two paragraphs in one table cell stay in that cell, one row stays one line", () => {
  const { text } = docxToText(fx("faq.docx"));
  assert.ok(text.includes("Adakah “logo” hijau wajib? (soalan kedua dalam sel yang sama) | Tidak; Klausa 40(2) membenarkan warna lain."));
});

t("docx: tracked deletions are left out, tracked insertions kept, nested table folded into its cell", () => {
  const body = `<w:body><w:p><w:r><w:t>Kept </w:t></w:r><w:del><w:r><w:delText>gone</w:delText></w:r></w:del><w:ins><w:r><w:t xml:space="preserve">added</w:t></w:r></w:ins></w:p>
    <w:tbl><w:tr><w:tc><w:p><w:r><w:t>Outer</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Inner</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:tc><w:tc><w:p><w:r><w:t>Right</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body>`;
  const { text } = docxToText(zipSync({ "word/document.xml": strToU8(`<w:document xmlns:w="w">${body}</w:document>`) }));
  assert.equal(text, "Kept added\nOuter Inner | Right");
});

t("docx: a zip that is not a Word file, and a file that is not a zip, are refused in words", () => {
  assert.throws(() => docxToText(zipSync({ "x.txt": strToU8("hi") })), (e) => e instanceof OfficeError && /\.docx/.test(e.message));
  assert.throws(() => docxToText(new Uint8Array([1, 2, 3, 4])), (e) => e instanceof OfficeError);
});

t("docx: a part over the size cap is not opened (a zip bomb costs nothing)", () => {
  const big = strToU8("<w:document>" + "a".repeat(10) + "</w:document>");
  const z = zipSync({ "word/document.xml": big });
  const keep = OFFICE_LIMITS.part; OFFICE_LIMITS.part = 5;
  try { assert.throws(() => docxToText(z), OfficeError); } finally { OFFICE_LIMITS.part = keep; }
});

// ---- Excel -----------------------------------------------------------------------------------------------------
t("xlsx: every visible sheet, in order; the hidden one is named and not read", () => {
  const { tables, hidden } = xlsxToTables(fx("qa_openpyxl.xlsx"));
  assert.deepEqual(tables.map((x) => x.sheet), ["FAQ", "Nota"]);
  assert.deepEqual(hidden, ["Rahsia"]);
});

t("xlsx: dates read as dates, numbers as numbers (0.1+0.2 is 0.3), booleans, ampersands, newlines folded, blank row skipped", () => {
  const f = xlsxToTables(fx("qa_openpyxl.xlsx")).tables[0];
  assert.deepEqual(f.rows[0], ["No", "Soalan", "Jawapan", "Kategori", "Tarikh", "Skor"]);
  assert.equal(f.rows[1][4], "2026-09-20");
  assert.equal(f.rows[2][4], "2026-09-21 14:30");
  assert.equal(f.rows[3][5], "0.3");
  assert.equal(f.rows[4][2], "Ya. Semua kosmetik wajib.");
  assert.equal(f.rows[4][5], "TRUE");
  assert.equal(f.rows[5][1], "Soalan dengan & ampersand <tag>?");
  assert.deepEqual(f.nums, [1, 2, 3, 4, 6, 7, 8], "sheet row numbers survive the skipped blank row 5");
});

t("xlsx: a question/answer sheet becomes pairs with no AI; a row with no question is counted, not read", () => {
  const f = xlsxToTables(fx("qa_openpyxl.xlsx")).tables[0];
  const r = tablePairs("FAQ", f);
  assert.equal(r.pairs.length, 5);
  assert.equal(r.skipped, 1);
  assert.equal(r.pairs[0].question, "Bolehkah logo halal dicetak hitam putih?");
  assert.equal(r.pairs[2].answer, "", "a question with no answer keeps an empty answer for the worker to write and flag");
  assert.equal(r.pairs[0].source_hint, "FAQ · baris 2");
  assert.equal(r.pairs[3].source_hint, "FAQ · baris 6");
  assert.equal(tablePairs("Syarikat ABC", f, "Excel, helaian 1").pairs[3].source_hint, "Excel, helaian 1 · baris 6", "the label, not the sheet's own name, is what is stored");
});

t("xlsx: a sheet with no question/answer headers goes to the reader as text with its header line", () => {
  const f = xlsxToTables(fx("qa_openpyxl.xlsx")).tables[1];
  assert.equal(tablePairs("Nota", f), null);
  const tx = tableText("Nota", f.rows);
  assert.equal(tx.text, "Sheet: Nota\nProduk | Bahan | Peratus\nSerum A | Niacinamide | 5\nKrim B | Retinol | 0.3");
  assert.equal(tx.header, "Produk | Bahan | Peratus");
});

t("xlsx: cached formula values, inline strings, errors, booleans, rich text and the 1904 date system", () => {
  const z = xlsx({
    "xl/workbook.xml": WB([["S", "rId1"]], '<workbookPr date1904="1"/>'),
    "xl/_rels/workbook.xml.rels": RELS({ rId1: "/xl/worksheets/sheet1.xml" }),
    "xl/sharedStrings.xml": '<sst><si><t>Soalan</t></si><si><r><t>Rich </t></r><r><rPr/><t>text</t></r><rPh sb="0"><t>IGNORED</t></rPh></si><si/></sst>',
    "xl/styles.xml": '<styleSheet><numFmts><numFmt numFmtId="164" formatCode="dd/mm/yyyy"/><numFmt numFmtId="165" formatCode="0.00&quot;m&quot;"/></numFmts><cellXfs><xf numFmtId="0"/><xf numFmtId="164"/><xf numFmtId="165"/></cellXfs></styleSheet>',
    "xl/worksheets/sheet1.xml": SHEET(
      '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>Inline &amp; one</t></is></c></row>'
      + '<row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2" t="str"><f>A2&amp;"!"</f><v>cached text</v></c><c r="C2" t="e"><v>#DIV/0!</v></c><c r="D2" t="b"><v>0</v></c></row>'
      + '<row r="3"><c r="A3" s="1"><v>1</v></c><c r="B3" s="2"><v>3.5</v></c><c r="D3" t="s"><v>2</v></c></row>'),
  });
  const { tables } = xlsxToTables(z);
  const rows = tables[0].rows;
  assert.deepEqual(rows[0], ["Soalan", "Inline & one"]);
  assert.deepEqual(rows[1], ["Rich text", "cached text", "", "FALSE"]);
  assert.equal(rows[2][0], "1904-01-02", "1904 system: serial 1 is 2 Jan 1904");
  assert.equal(rows[2][1], "3.5", "a number format with a quoted unit is not a date");
});

t("xlsx: not an Excel file is refused; a sheet over the row cap says it was cut", () => {
  assert.throws(() => xlsxToTables(zipSync({ "a.txt": strToU8("x") })), (e) => e instanceof OfficeError && /\.xlsx/.test(e.message));
  const rows = Array.from({ length: OFFICE_LIMITS.rows + 10 }, (_, i) => `<row r="${i + 1}"><c r="A${i + 1}" t="inlineStr"><is><t>r${i}</t></is></c></row>`).join("");
  const z = xlsx({ "xl/workbook.xml": WB([["S", "rId1"]]), "xl/_rels/workbook.xml.rels": RELS({ rId1: "worksheets/sheet1.xml" }), "xl/worksheets/sheet1.xml": SHEET(rows) });
  const s = xlsxToTables(z).tables[0];
  assert.equal(s.rows.length, OFFICE_LIMITS.rows);
  assert.equal(s.truncated, true);
});

t("dates: serial numbers and the time-only case", () => {
  assert.equal(serialToDate(46285), "2026-09-20");
  assert.equal(serialToDate(46285.5), "2026-09-20 12:00");
  assert.equal(serialToDate(0.75), "18:00");
});

// ---- CSV -------------------------------------------------------------------------------------------------------
t("csv: quotes, a comma and a newline inside quotes, row numbers follow the file's lines", () => {
  const c = csvToRows(fxText("semasa_export.csv"));
  assert.equal(c.rows.length, 3);
  assert.equal(c.rows[1][2], "Bolehkah, logo halal hitam putih?");
  assert.equal(c.rows[1][3], "Boleh. Selagi spesifikasi tidak berubah.");
  assert.deepEqual(c.nums, [1, 2, 4], "row 2 spans two file lines, so the next row began on line 4");
  const r = tablePairs("semasa_export", c);
  assert.equal(r.pairs.length, 2);
  assert.equal(r.pairs[1].source_hint, "semasa_export · baris 4");
});

t("csv: a semicolon file with a BOM and a doubled quote", () => {
  const c = csvToRows(fxText("semicolon.csv"));
  assert.deepEqual(c.rows[0], ["Question", "Answer", "Tag"]);
  assert.equal(c.rows[2][0], 'Is "halal" mandatory?');
  assert.equal(tablePairs("s", c).pairs.length, 2);
});

t("csv: a table with no Q/A headers is not turned into pairs", () => {
  assert.equal(tablePairs("n", csvToRows(fxText("noheader.csv"))), null);
});

t("csv: tab-separated, CRLF line ends, no final newline", () => {
  const c = csvToRows("Soalan\tJawapan\r\nA?\tB\r\nC?\tD");
  assert.deepEqual(c.rows, [["Soalan", "Jawapan"], ["A?", "B"], ["C?", "D"]]);
});

t("csv: empty and whitespace-only input give no rows", () => {
  assert.deepEqual(csvToRows("").rows, []);
  assert.deepEqual(csvToRows("\n\n  \n").rows, []);
});

t("pairs: headers are found within the first rows, a header like question_en counts, 'Quantity' and 'Amount' do not", () => {
  const rows = [["Laporan"], [""], ["No", "question_en", "answer_en"], ["1", "What?", "That."]];
  assert.equal(tablePairs("x", { rows: rows.filter((r) => r.some(Boolean)), nums: [1, 3, 4] }).pairs[0].answer, "That.");
  assert.equal(tablePairs("x", { rows: [["Quantity", "Amount"], ["1", "2"]], nums: [1, 2] }), null);
});

t("pairs: a table over the pair cap is cut and says so", () => {
  const rows = [["Soalan", "Jawapan"], ...Array.from({ length: OFFICE_LIMITS.pairs + 20 }, (_, i) => [`Soalan nombor ${i}?`, "x"])];
  const r = tablePairs("x", { rows, nums: rows.map((_, i) => i + 1) });
  assert.equal(r.pairs.length, OFFICE_LIMITS.pairs);
  assert.equal(r.cut, true);
});

t("xml entities: named, decimal and hex; an unknown name is left as it was; nothing absurd becomes a character", () => {
  assert.equal(decodeXml("a &amp; b &lt;c&gt; &quot;d&quot; &#233; &#x2019; &nbsp; &#0; &#99999999;"), 'a & b <c> "d" é ’ &nbsp;  ');
});

console.log(`${n} office tests passed`);
