/* Plain text out of Word (.docx), Excel (.xlsx) and CSV files, in the browser, with no new dependency: a .docx or .xlsx is
   a zip of XML, fflate (already used for exports) opens it, and the few tags that carry the words are read here.

   Wan, 1 Oct 2026: the FAQ AI bar must also take xlsx, csv and Word files. The result is TEXT for the reader (or, for a
   spreadsheet that already has a question column and an answer column, the pairs themselves, with no AI call).

   Deliberately NOT done: the old binary .doc and .xls (no honest way to read them without a large library: the page
   names them and asks for a re-save as .docx / .xlsx), formulas (the value Excel last calculated is read, as stored),
   macros, embedded pictures and comments. Hidden sheets are left out and said so.

   Everything here is pure (strings and bytes in, strings out) so Node can test it against files made by real Word and
   Excel (web/office.test.mjs). */
import { strFromU8, unzipSync } from "fflate";

export const OFFICE_LIMITS = { part: 40_000_000, rows: 5000, cell: 1500, pairs: 300, header: 5 };

export class OfficeError extends Error {}

const ENT = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
export const decodeXml = (s) => String(s || "").replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
  if (e[0] === "#") {
    const n = e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
    return Number.isFinite(n) && n > 0 && n < 0x110000 ? String.fromCodePoint(n) : "";
  }
  return ENT[e.toLowerCase()] ?? m;
});

/** The named parts of a zip, each no bigger than the cap. A part over the cap is simply not opened. */
function openZip(bytes, want) {
  let parts;
  try {
    parts = unzipSync(bytes, { filter: (f) => f.originalSize <= OFFICE_LIMITS.part && want(f.name) });
  } catch {
    throw new OfficeError("bukan fail Office yang sah, atau rosak / not a valid Office file, or it is damaged");
  }
  return parts;
}
const part = (parts, name) => (parts[name] ? strFromU8(parts[name]) : "");

// ---- Word -----------------------------------------------------------------------------------------------------

const DOC_TOKENS = /<w:(p|tbl|tr|tc)(?=[\s>])[^>]*>|<\/w:(p|tbl|tr|tc)>|<w:t(?=[\s>])[^>]*>([\s\S]*?)<\/w:t>|<w:(tab|br|cr|noBreakHyphen)\s*\/>/g;

/** The words of a .docx, in reading order: one line per paragraph, one line per table row with the cells joined by " | ".
    Tracked deletions are left out and tracked insertions kept, because that is what the document reads as. */
export function docxToText(bytes) {
  const parts = openZip(bytes, (n) => n === "word/document.xml");
  const xml = part(parts, "word/document.xml");
  if (!xml) throw new OfficeError("bukan fail Word .docx yang sah (tiada word/document.xml) / not a valid .docx (no word/document.xml)");
  const lines = [];
  let para = null;                     // text of the paragraph being read
  let cell = null, row = null;         // a table cell's paragraphs, and the cells of the current row
  let depth = 0;                       // table nesting: a table inside a cell is flattened into that cell
  const flushPara = () => {
    if (para === null) return;
    const text = para.replace(/[ \t]+/g, " ").trim();
    para = null;
    if (!text) return;
    if (cell) cell.push(text); else lines.push(text);
  };
  let m;
  DOC_TOKENS.lastIndex = 0;
  while ((m = DOC_TOKENS.exec(xml))) {
    const open = m[1], close = m[2];
    if (open === "p") { flushPara(); para = ""; }
    else if (close === "p") flushPara();
    else if (open === "tbl") depth++;
    else if (close === "tbl") { depth = Math.max(0, depth - 1); }
    else if (open === "tr") { if (depth <= 1) row = []; }
    else if (close === "tr") { if (depth <= 1 && row) { const line = row.join(" | ").trim(); if (line.replace(/[|\s]/g, "")) lines.push(line); row = null; } }
    else if (open === "tc") { if (depth <= 1) cell = []; }
    else if (close === "tc") { flushPara(); if (depth <= 1 && cell) { (row || (row = [])).push(cell.join(" ")); cell = null; } }
    else if (m[3] !== undefined) { if (para === null) para = ""; para += decodeXml(m[3]); }
    else if (m[4]) { if (para === null) para = ""; para += m[4] === "tab" ? "\t" : m[4] === "noBreakHyphen" ? "-" : " "; }
  }
  flushPara();
  return { text: lines.join("\n") };
}

// ---- Excel ----------------------------------------------------------------------------------------------------

const attr = (tag, name) => { const m = tag.match(new RegExp(`\\b${name}="([^"]*)"`)); return m ? decodeXml(m[1]) : ""; };
const colIndex = (ref) => { let n = 0; for (const ch of ref.replace(/[^A-Za-z]/g, "").toUpperCase()) n = n * 26 + ch.charCodeAt(0) - 64; return Math.max(0, n - 1); };

const BUILTIN_DATE = new Set([14, 15, 16, 17, 18, 19, 20, 21, 22, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 45, 46, 47, 50, 51, 52, 53, 54, 55, 56, 57, 58]);
const isDateFormat = (code) => /[ymdhs]/i.test(String(code).replace(/"[^"]*"|\[[^\]]*\]|\\.|_.|\*./g, ""));

function sharedStrings(xml) {
  const out = [];
  const re = /<si(?:\s[^>]*)?>([\s\S]*?)<\/si>|<si\s*\/>/g;
  let m;
  while ((m = re.exec(xml))) {
    const body = (m[1] || "").replace(/<rPh\b[\s\S]*?<\/rPh>/g, "");
    let s = "";
    body.replace(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g, (_, t) => { s += decodeXml(t); return ""; });
    out.push(s);
  }
  return out;
}

function dateStyles(xml) {
  const custom = {};
  for (const m of xml.matchAll(/<numFmt\b[^>]*>/g)) custom[attr(m[0], "numFmtId")] = attr(m[0], "formatCode");
  const block = (xml.match(/<cellXfs\b[\s\S]*?<\/cellXfs>/) || [""])[0];
  const flags = [];
  for (const m of block.matchAll(/<xf\b[^>]*?(?:\/>|>)/g)) {
    const id = parseInt(attr(m[0], "numFmtId") || "0", 10);
    flags.push(BUILTIN_DATE.has(id) || (custom[id] !== undefined && isDateFormat(custom[id])));
  }
  return flags;
}

const pad = (n) => String(n).padStart(2, "0");
export function serialToDate(serial, epoch1904 = false) {
  const days = Number(serial);
  if (!Number.isFinite(days)) return String(serial);
  const base = epoch1904 ? Date.UTC(1904, 0, 1) : Date.UTC(1899, 11, 30);
  const d = new Date(base + Math.round(days * 86400000));
  const date = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  const secs = Math.round((days % 1) * 86400);
  return days >= 1 && secs === 0 ? date : days < 1 ? `${pad(Math.floor(secs / 3600))}:${pad(Math.floor(secs / 60) % 60)}` : `${date} ${pad(Math.floor(secs / 3600))}:${pad(Math.floor(secs / 60) % 60)}`;
}
const cleanNumber = (v) => { const n = Number(v); return v !== "" && Number.isFinite(n) ? String(parseFloat(n.toPrecision(15))) : v; };

/** Every visible sheet of an .xlsx as { sheet, rows: string[][], nums: number[] } (nums = the sheet's own row numbers). */
export function xlsxToTables(bytes) {
  const parts = openZip(bytes, (n) => n === "xl/workbook.xml" || n === "xl/_rels/workbook.xml.rels" || n === "xl/sharedStrings.xml"
    || n === "xl/styles.xml" || /^xl\/worksheets\/[^/]+\.xml$/.test(n));
  const book = part(parts, "xl/workbook.xml");
  if (!book) throw new OfficeError("bukan fail Excel .xlsx yang sah (tiada xl/workbook.xml) / not a valid .xlsx (no xl/workbook.xml)");
  const epoch1904 = /<workbookPr\b[^>]*date1904="(1|true)"/i.test(book);
  const rels = {};
  for (const m of part(parts, "xl/_rels/workbook.xml.rels").matchAll(/<Relationship\b[^>]*>/g)) {
    rels[attr(m[0], "Id")] = attr(m[0], "Target").replace(/^\/?(xl\/)?/, "");
  }
  const shared = sharedStrings(part(parts, "xl/sharedStrings.xml"));
  const dates = dateStyles(part(parts, "xl/styles.xml"));
  const out = [];
  const hidden = [];
  for (const sm of book.matchAll(/<sheet\b[^>]*>/g)) {
    const name = attr(sm[0], "name") || `Sheet${out.length + 1}`;
    if (/^(hidden|veryHidden)$/i.test(attr(sm[0], "state"))) { hidden.push(name); continue; }
    const target = rels[attr(sm[0], "r:id") || attr(sm[0], "id")];
    const xml = target ? part(parts, `xl/${target}`) : "";
    if (!xml) continue;
    const rows = [], nums = [];
    let autoRow = 0;
    for (const rm of xml.matchAll(/<row\b([^>]*?)(?:\/>|>([\s\S]*?)<\/row>)/g)) {
      autoRow = parseInt(attr(rm[1], "r"), 10) || autoRow + 1;
      if (!rm[2]) continue;
      const cells = [];
      for (const cm of rm[2].matchAll(/<c\b([^>]*?)(?:\/>|>([\s\S]*?)<\/c>)/g)) {
        const ref = attr(cm[1], "r");
        const at = ref ? colIndex(ref) : cells.length;
        const t = attr(cm[1], "t");
        const v = (cm[2] || "").match(/<v>([\s\S]*?)<\/v>/);
        let text = "";
        if (t === "inlineStr") (cm[2] || "").replace(/<t(?:\s[^>]*)?>([\s\S]*?)<\/t>/g, (_, s) => { text += decodeXml(s); return ""; });
        else if (v) {
          const raw = decodeXml(v[1]);
          if (t === "s") text = shared[parseInt(raw, 10)] ?? "";
          else if (t === "b") text = raw === "1" ? "TRUE" : "FALSE";
          else if (t === "e") text = "";
          else if (t === "str" || t === "d") text = raw;
          else text = dates[parseInt(attr(cm[1], "s") || "0", 10)] ? serialToDate(raw, epoch1904) : cleanNumber(raw);
        }
        text = text.replace(/\s*\n\s*/g, " ").replace(/[ \t]+/g, " ").trim().slice(0, OFFICE_LIMITS.cell);
        if (text) { while (cells.length < at) cells.push(""); cells[at] = text; }
      }
      if (cells.length) { rows.push(cells); nums.push(autoRow); }
      if (rows.length >= OFFICE_LIMITS.rows) break;
    }
    out.push({ sheet: name, rows, nums, truncated: rows.length >= OFFICE_LIMITS.rows });
  }
  return { tables: out, hidden };
}

// ---- CSV ------------------------------------------------------------------------------------------------------

/** CSV/TSV text → rows. Handles quotes (with "" inside), newlines inside quotes, a BOM, and picks the delimiter
    (comma, semicolon, tab or pipe) that fits the first lines best. */
export function csvToRows(text) {
  const src = String(text || "").replace(/^﻿/, "");
  const head = src.split(/\r?\n/).slice(0, 5).join("\n").replace(/"[^"]*"/g, "");
  const delim = [",", ";", "\t", "|"].map((d) => [d, head.split(d).length - 1]).sort((a, b) => b[1] - a[1])[0];
  const d = delim[1] ? delim[0] : ",";
  const rows = [], nums = [];
  let row = [], cur = "", q = false, line = 1, start = 1;  // `start`: the file line a row began on
  const endCell = () => { row.push(cur.replace(/\s*\n\s*/g, " ").replace(/[ \t]+/g, " ").trim().slice(0, OFFICE_LIMITS.cell)); cur = ""; };
  const endRow = () => { endCell(); if (row.some(Boolean)) { while (row.length && !row[row.length - 1]) row.pop(); rows.push(row); nums.push(start); } row = []; };
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (q) {
      if (ch === '"') { if (src[i + 1] === '"') { cur += '"'; i++; } else q = false; }
      else { if (ch === "\n") line++; cur += ch; }
    } else if (ch === '"' && !cur.trim()) q = true;
    else if (ch === d) endCell();
    else if (ch === "\n" || (ch === "\r" && src[i + 1] !== "\n")) { endRow(); line++; start = line; if (rows.length >= OFFICE_LIMITS.rows) break; }
    else if (ch !== "\r") cur += ch;
  }
  if (cur || row.length) endRow();
  return { rows: rows.slice(0, OFFICE_LIMITS.rows), nums: nums.slice(0, OFFICE_LIMITS.rows), truncated: rows.length >= OFFICE_LIMITS.rows };
}

// ---- tables → what the reader or the page takes ----------------------------------------------------------------

/** One table as text for the reader: a title line, then one line per row with the cells joined by " | ". `header` is the
    first row, which the page repeats on every later piece so a long sheet keeps its column names. */
export function tableText(sheet, rows) {
  const lines = rows.map((r) => r.map((c) => c || "").join(" | ").replace(/(\s\|)+\s*$/, "").trim()).filter(Boolean);
  return { text: lines.length ? `Sheet: ${sheet}\n${lines.join("\n")}` : "", header: lines[0] ? lines[0].slice(0, 400) : "" };
}

const Q_HEAD = /^(soalan|pertanyaan|question|q)(?![a-z])/i;
const A_HEAD = /^(jawapan|jawab|answer|reply|respons|a)(?![a-z])/i;

/** A table that already has a question column and an answer column becomes pairs directly, with no AI call: the first
    "question" column and the first "answer" column after it (or before it, if none follows). `label` is what each pair says it came from
    (the page passes "Excel, helaian 2", never the sheet's or the file's own name, which can carry a client's: the hint is
    stored in source_name and mirrored to the sheet). null when the first rows
    show no such pair of headers, so an ordinary table goes to the reader instead. */
export function tablePairs(sheet, { rows, nums }, label = sheet) {
  for (let h = 0; h < Math.min(OFFICE_LIMITS.header, rows.length); h++) {
    const cells = rows[h].map((c) => String(c || "").trim());
    const qi = cells.findIndex((c) => Q_HEAD.test(c));
    if (qi < 0) continue;
    let ai = cells.findIndex((c, i) => i > qi && A_HEAD.test(c));
    if (ai < 0) ai = cells.findIndex((c, i) => i < qi && A_HEAD.test(c));
    if (ai < 0) continue;
    const pairs = [];
    let skipped = 0;
    for (let r = h + 1; r < rows.length; r++) {
      const question = String(rows[r][qi] || "").trim();
      if (!question) { if (rows[r].some(Boolean)) skipped++; continue; }
      if (pairs.length >= OFFICE_LIMITS.pairs) return { pairs, skipped, header: h + 1, cut: true };
      pairs.push({ question: question.slice(0, 600), answer: String(rows[r][ai] || "").trim().slice(0, 3000), instrument: "", unclear: false,
        source_hint: `${label} · baris ${nums[r] ?? r + 1}` });
    }
    return { pairs, skipped, header: h + 1, cut: false };
  }
  return null;
}
