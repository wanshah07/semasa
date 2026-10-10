/* Otak AI: turn a dropped file into an inbox row (the browser half; the pure half is lib/brain.js).
   A picture is shrunk to 1600px and uploaded; a PDF is uploaded as it is and the worker reads its text layer (the bucket takes
   only pictures, text and PDF); a Word, Excel or CSV file has its words read here, because the bucket does not take those
   types, and the words travel in the row. Text and Markdown files travel as text. A file this cannot read is refused by name
   with what to do instead; nothing is dropped silently. */
import { OfficeError, csvToRows, docxToText, tableText, xlsxToTables } from "./officeText";
import { kindOf, legacyWhy } from "./faqAiLogic";
import { LIMITS } from "./brain";

const MAX_FILE = 25_000_000;

async function bytesOf(file) { return new Uint8Array(await file.arrayBuffer()); }

/** { row, upload } for one file: `row` is the inbox row's fields, `upload` the File to put in the bucket first (or null). Throws a
    plain Error whose message names the file and says what to do. */
export async function prepareFile(file, { shrink } = {}) {
  const name = file.name || "fail";
  if (file.size > MAX_FILE) throw new Error(`${name}: ${Math.round(file.size / 1_000_000)} MB, melebihi ${MAX_FILE / 1_000_000} MB / over ${MAX_FILE / 1_000_000} MB`);
  const kind = kindOf(name, file.type);
  const base = { file_name: name.slice(0, 160), file_mime: file.type || "" };
  try {
    if (kind === "image") return { row: { ...base, source_kind: "image", file_mime: "image/jpeg" }, upload: shrink ? await shrink(file) : file };
    if (kind === "pdf") return { row: { ...base, source_kind: "file", file_mime: "application/pdf" }, upload: file };
    if (kind === "docx") {
      const { text } = docxToText(await bytesOf(file));
      if (!text.trim()) throw new Error("tiada teks / no text in it");
      return { row: { ...base, source_kind: "file", body: text.trim().slice(0, LIMITS.text) }, upload: null };
    }
    if (kind === "xlsx") {
      const { tables } = xlsxToTables(await bytesOf(file));
      const text = tables.map((t) => tableText(t.sheet, t.rows).text).filter(Boolean).join("\n\n");
      if (!text) throw new Error("tiada data / no data in it");
      return { row: { ...base, source_kind: "file", body: text.slice(0, LIMITS.text) }, upload: null };
    }
    if (kind === "csv") {
      const text = tableText(name.replace(/\.[^.]+$/, "") || "CSV", csvToRows(await file.text()).rows).text;
      if (!text) throw new Error("tiada data / no data in it");
      return { row: { ...base, source_kind: "file", body: text.slice(0, LIMITS.text) }, upload: null };
    }
    if (kind === "text") {
      const text = (await file.text()).trim();
      if (!text) throw new Error("kosong / empty");
      return { row: { ...base, source_kind: "file", body: text.slice(0, LIMITS.text) }, upload: null };
    }
  } catch (e) {
    throw new Error(`${name}: ${e instanceof OfficeError || e instanceof Error ? e.message : String(e)}`);
  }
  throw new Error(`${name}: ${kind === "legacy" ? legacyWhy(name) : "jenis fail ini tidak boleh dibaca / this file type is not read"}`);
}
