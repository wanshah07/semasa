/* A reference document, read in the browser into the words the worker turns into a template (supabase/038_doc_templates.sql,
   backend/semasa/brain_docs.py `process_templates`). A Word file keeps its shape: a paragraph in a heading style, or short and
   all bold, or short and all capitals, is written as "# Heading"; a table is "TABLE:" and its rows as "| a | b |" with the first row
   the header; every other paragraph is its own line, so a form's own instruction text ("Nyatakan tujuan...") reaches the AI. An
   Excel sheet is a heading and a table; CSV a table; text and Markdown as they are. The marks are a hint to the AI, never a rule.
   A PDF, a picture and an old .doc are refused by name with what to do. Pure: no DOM, so it runs under node. */
import { strFromU8, unzipSync } from "fflate";
import { OfficeError, csvToRows, decodeXml, xlsxToTables } from "./officeText.js";

export const REFERENCE_LIMIT = 60_000;
export const REFERENCE_MIN = 40;
const MAX_FILE = 15_000_000;
const HEADING_STYLE = /^(?:heading|title|subtitle|tajuk|judul|h[1-6]$)/i;
const BOLD_ON = /<w:b(?:\s+w:val="(?:1|true|on)")?\s*\/>/;
const cell = (s) => String(s ?? "").replace(/\|/g, "/").replace(/\s+/g, " ").trim();
const row = (cells) => `| ${cells.map(cell).join(" | ")} |`;

/** The top-level paragraphs and tables of a document.xml, in order, as slices of the xml. */
function blocks(xml) {
  const out = [];
  let depth = 0, start = -1, kind = "";
  for (const m of xml.matchAll(/<w:(tbl|p)(?=[\s>])|<\/w:tbl>|<\/w:p>/g)) {
    if (m[0] === "</w:tbl>") { depth = Math.max(0, depth - 1); if (depth === 0 && kind === "tbl") { out.push({ kind, xml: xml.slice(start, m.index + m[0].length) }); kind = ""; } }
    else if (m[0] === "</w:p>") { if (kind === "p" && depth === 0) { out.push({ kind, xml: xml.slice(start, m.index + m[0].length) }); kind = ""; } }
    else if (m[1] === "tbl") { if (depth === 0) { start = m.index; kind = "tbl"; } depth++; }
    else if (m[1] === "p" && depth === 0 && !kind) { start = m.index; kind = "p"; }
  }
  return out;
}

const textOf = (xml) => decodeXml([...xml.matchAll(/<w:t(?=[\s>])[^>]*>([\s\S]*?)<\/w:t>|<w:tab\s*\/>/g)].map((m) => (m[1] === undefined ? "\t" : m[1])).join(""))
  .replace(/\s+/g, " ").trim();

/** A paragraph: its text, its style, and whether every word of it is bold. */
function paragraph(xml) {
  const style = (xml.match(/<w:pStyle\s+w:val="([^"]*)"/) || [])[1] || "";
  const runs = [...xml.matchAll(/<w:r(?=[\s>])[\s\S]*?<\/w:r>/g)].map((m) => m[0]).filter((r) => textOf(r));
  return { text: textOf(xml), style, allBold: runs.length > 0 && runs.every((r) => BOLD_ON.test(r)) };
}

export const isHeading = ({ text, style, allBold }) => {
  if (!text) return false;
  if (HEADING_STYLE.test(style)) return true;
  if (text.length > 100 || /[.;,]$/.test(text)) return false;
  return allBold || (text.length <= 70 && text === text.toUpperCase() && /[A-ZÀ-Ý]{3}/.test(text));
};

function tableRows(xml) {
  return xml.split(/<w:tr(?=[\s>])/).slice(1).map((r) => r.split(/<w:tc(?=[\s>])/).slice(1).map((c) => textOf(c)));
}

function tableLines(rows, max = 8) {
  const shown = rows.filter((r) => r.length).slice(0, max);
  const out = ["TABLE:", ...shown.map(row)];
  if (rows.length > max) out.push(`(${rows.length - max} more rows)`);
  return out;
}

/** The marked words of a .docx. */
export function docxMarked(bytes) {
  let parts;
  try { parts = unzipSync(bytes, { filter: (f) => f.name === "word/document.xml" && f.originalSize <= 40_000_000 }); }
  catch { throw new OfficeError("bukan fail Word yang sah, atau rosak / not a valid Word file, or it is damaged"); }
  if (!parts["word/document.xml"]) throw new OfficeError("bukan fail Word .docx yang sah (tiada word/document.xml) / not a valid .docx (no word/document.xml)");
  const lines = [];
  for (const b of blocks(strFromU8(parts["word/document.xml"]))) {
    if (b.kind === "tbl") { lines.push(...tableLines(tableRows(b.xml))); continue; }
    const p = paragraph(b.xml);
    if (!p.text) continue;
    lines.push(isHeading(p) ? `# ${p.text}` : p.text.slice(0, 300));
  }
  return lines.join("\n");
}

export const baseName = (name) => String(name || "").replace(/\.[A-Za-z0-9]{1,5}$/, "").replace(/[_]+/g, " ").trim().slice(0, 120);
const kindOf = (name, mime) => {
  const n = String(name || "").toLowerCase();
  if (n.endsWith(".docx") || /wordprocessingml/.test(mime)) return "docx";
  if (n.endsWith(".xlsx") || /spreadsheetml/.test(mime)) return "xlsx";
  if (/\.(csv|tsv)$/.test(n)) return "csv";
  if (/\.(txt|md|markdown)$/.test(n) || /^text\//.test(mime)) return "text";
  if (n.endsWith(".pdf") || mime === "application/pdf") return "pdf";
  if (/\.(doc|xls|ppt|pptx|odt|rtf)$/.test(n)) return "legacy";
  if (/^image\//.test(mime)) return "image";
  return "other";
};

/** The words of one reference file for the worker: { name, text } or an Error that names the file and says what to do. */
export async function readReference(file) {
  const name = file?.name || "fail";
  if (file.size > MAX_FILE) throw new Error(`${name}: ${Math.round(file.size / 1_000_000)} MB, melebihi ${MAX_FILE / 1_000_000} MB / over ${MAX_FILE / 1_000_000} MB`);
  const kind = kindOf(name, file.type);
  const fail = (bm, en) => { throw new Error(`${name}: ${bm} / ${en}`); };
  let text = "";
  try {
    if (kind === "docx") text = docxMarked(new Uint8Array(await file.arrayBuffer()));
    else if (kind === "xlsx") {
      const { tables } = xlsxToTables(new Uint8Array(await file.arrayBuffer()));
      text = tables.filter((t) => t.rows.length).map((t) => [`# ${t.sheet}`, ...tableLines(t.rows)].join("\n")).join("\n");
    } else if (kind === "csv") text = tableLines(csvToRows(await file.text()).rows).join("\n");
    else if (kind === "text") text = (await file.text()).trim();
  } catch (e) { throw new Error(`${name}: ${e instanceof OfficeError || e instanceof Error ? e.message : String(e)}`); }
  if (kind === "pdf") fail("PDF belum dibaca untuk templat: simpan sebagai Word (.docx) atau tampal teksnya dalam fail teks", "a PDF is not read for a template yet: save it as Word (.docx) or paste its text into a text file");
  if (kind === "image") fail("gambar tidak dibaca untuk templat: taip semula bahagiannya dalam fail teks atau Word", "a picture is not read for a template: retype its sections in a text or Word file");
  if (kind === "legacy") fail("format lama (.doc, .xls, .ppt, .rtf): buka dan simpan sebagai .docx atau .xlsx", "an old format (.doc, .xls, .ppt, .rtf): open it and save as .docx or .xlsx");
  if (kind === "other") fail("jenis fail ini tidak dibaca (guna .docx, .xlsx, .csv, .txt atau .md)", "this file type is not read (use .docx, .xlsx, .csv, .txt or .md)");
  text = text.trim();
  if (text.length < REFERENCE_MIN) fail("hampir tiada teks untuk dibaca", "there is hardly any text to read");
  return { name: baseName(name), file: name.slice(0, 160), text: text.slice(0, REFERENCE_LIMIT), cut: text.length > REFERENCE_LIMIT };
}
