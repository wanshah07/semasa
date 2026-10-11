/* Documents drafted from the FAQ and the Otak AI brain (supabase/037_brain_docs.sql, backend/semasa/brain_docs.py). This is the
   browser's half: the document types and what they hold (rules/documents.json, shared with the worker), the material put
   together from the entries, FAQs, words and files picked, the request row, and a plain-text copy of a finished draft. The Word
   file itself is src/lib/docxWrite.js. Pure, so it runs under node. */
import RULES from "../../../rules/documents.json";

export const MARKER = RULES.marker;
export const STATUS = RULES.status;
/** `read` is what the worker drafts from (backend/semasa/brain_docs.py MAX_SOURCE); `row` is the column's own limit. */
export const LIMITS = { read: 40_000, row: 120_000, note: 500, structure: 2_000, minimum: 20 };
export const DOC_TYPES = RULES.types.map((t) => ({
  id: t.id,
  label: [t.label.ms, t.label.en],
  description: [t.description.ms, t.description.en],
  sections: t.sections.map((s) => ({ key: s.key, kind: s.kind, heading: [s.heading.ms, s.heading.en] })),
}));
export const TYPE_IDS = DOC_TYPES.map((t) => t.id);
/** The types offered as they are; "template" is chosen through the user's own templates instead. */
export const BUILTIN_TYPES = DOC_TYPES.filter((t) => t.id !== "template");
export const LANG_CHOICES = [["ms", "Bahasa Malaysia", "Bahasa Malaysia"], ["en", "English", "English"], ["both", "BM + English", "BM + English"]];
export const KIND_WORDS = { paragraphs: ["Teks", "Text"], bullets: ["Senarai", "List"], table: ["Jadual", "Table"] };
export const STATUS_WORDS = { pending: ["Menunggu AI", "Waiting for the AI"], working: ["Sedang ditulis", "Being drafted"], done: ["Siap", "Ready"], error: ["Gagal", "Failed"] };

const kindWord = { note: "Nota", faq: "FAQ", skill: "Skill", prompt: "Prompt", reference: "Rujukan", checklist: "Senarai semak" };
const clean = (s) => String(s ?? "").replace(/\r\n?/g, "\n").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();

/** The words of one Otak entry as material: the kind's own fields first, then the body, the source address last. */
export function entryText(e) {
  const d = e?.data || {};
  const bits = [`${kindWord[e?.kind] || e?.kind || "Entri"}: ${e?.title || ""}`];
  if (e?.category) bits.push(`Kategori: ${e.category}`);
  if (e?.kind === "faq") bits.push(`Soalan: ${e.question || ""}`, `Jawapan: ${e.answer || e.body || ""}`);
  else if (e?.kind === "skill") bits.push(d.when ? `Bila guna: ${d.when}` : "", ...(d.steps || []).map((s, i) => `Langkah ${i + 1}: ${s}`), !(d.steps || []).length ? e.body || "" : "");
  else if (e?.kind === "checklist") bits.push(...(d.items || []).map((s) => `- ${s}`), !(d.items || []).length ? e.body || "" : "");
  else if (e?.kind === "prompt") bits.push(d.use ? `Untuk: ${d.use}` : "", e.body || "");
  else bits.push(e?.summary && e.summary !== e?.body ? e.summary : "", e?.body || "");
  if (e?.source_url) bits.push(`Sumber: ${e.source_url}`);
  return clean(bits.filter(Boolean).join("\n"));
}

/** One FAQ as material, from the question and answer already chosen in the language being shown. */
export const faqText = (question, answer, category = "") => clean([category ? `Kategori: ${category}` : "", `Soalan: ${question}`, `Jawapan: ${answer}`].filter(Boolean).join("\n"));

/**
 * The material for a request. `items` are { kind, id, title, text } (entries, FAQs, files read here); `text` is words pasted.
 * Each part is numbered ("Bahan 2") so the draft can say where a statement came from and a reviewer can find it.
 * Returns { text, refs, chars, over, cut }: `over` when more than the worker reads, `cut` when more than the column holds.
 */
export function assembleSource({ items = [], text = "" } = {}) {
  const parts = [];
  const refs = [];
  const add = (kind, id, title, body) => {
    const b = clean(body);
    if (!b) return;
    parts.push(`[Bahan ${parts.length + 1}: ${title || kind}]\n${b}`);
    refs.push({ kind, id: id || "", title: String(title || kind).slice(0, 120) });
  };
  for (const it of items) add(it.kind, it.id, it.title, it.text);
  add("text", "", "Fakta ditampal", text);
  let joined = parts.join("\n\n-----\n\n");
  const chars = joined.length;
  const cut = chars > LIMITS.row;
  if (cut) joined = joined.slice(0, LIMITS.row);
  return { text: joined, refs, chars, over: chars > LIMITS.read, cut };
}

/** Why a request cannot be sent yet, in words (an empty list means it can). `template` is the chosen one when type is "template". */
export function validateRequest({ type, lang, source, structure, template } = {}) {
  const bad = [];
  if (!TYPE_IDS.includes(type)) bad.push(["jenis dokumen", "document type"]);
  if (!["ms", "en", "both"].includes(lang)) bad.push(["bahasa", "language"]);
  if (String(source?.text || "").trim().length < LIMITS.minimum) bad.push(["bahan: pilih entri atau FAQ, atau tampal fakta", "material: pick entries or FAQs, or paste the facts"]);
  if (type === "custom" && !String(structure || "").trim()) bad.push(["struktur: satu bahagian setiap baris", "structure: one section per line"]);
  if (type === "template" && !(template && template.status === "done" && Array.isArray(template.structure) && template.structure.length)) bad.push(["templat: pilih templat yang sudah siap", "template: choose a template that is ready"]);
  return bad;
}

/** The row to insert in semasa_brain_docs. A chosen template travels as a copy of its structure, so the document can be drafted
    again after the template is edited or deleted. */
export function requestRow({ type, lang, title = "", note = "", structure = "", source, userId = null, template = null }) {
  return {
    status: "pending", doc_type: type, lang, title: clean(title).slice(0, 120), note: clean(note).slice(0, LIMITS.note),
    custom_structure: type === "custom" ? String(structure || "").slice(0, LIMITS.structure) : "",
    template_id: type === "template" ? template?.id || null : null,
    template_snapshot: type === "template" ? { name: template?.name || "", source_lang: template?.source_lang || "ms", structure: template?.structure || [] } : {},
    source_text: source.text, source_refs: source.refs, result: {}, error: "", attempts: 0, created_by: userId,
  };
}

// ---- templates (supabase/038_doc_templates.sql) ---------------------------------------------------------------------------

/** The row to insert in semasa_doc_templates for one reference read by `readReference`. */
export function templateRow({ reference, name = "", note = "", userId = null }) {
  return {
    status: "pending", name: clean(name || reference.name).slice(0, 120), description: "", source_file: reference.file || "", source_lang: "",
    note: clean(note).slice(0, LIMITS.note), source_text: reference.text, structure: [], warnings: [], error: "", attempts: 0, created_by: userId,
  };
}

/** The templates that can be chosen: read, with at least one section. */
export const usableTemplates = (list) => (list || []).filter((t) => t.status === "done" && Array.isArray(t.structure) && t.structure.length);

const pipe = (v) => String(v ?? "").split("|").map((c) => clean(c)).filter(Boolean);
/** A template's sections as the editor's rows: titles in both languages, the kind, columns as "a | b | c", the hint, optional. */
export function editRows(template) {
  return (template?.structure || []).map((s) => ({
    headingMs: s.heading?.ms || "", headingEn: s.heading?.en || "", kind: s.kind || "paragraphs",
    columnsMs: (s.columns || []).map((c) => c.ms).join(" | "), columnsEn: (s.columns || []).map((c) => c.en).join(" | "),
    hint: s.hint?.ms || s.hint?.en || "", optional: !!s.optional,
  }));
}

/** Why the editor's rows cannot be saved, in words (an empty list means they can). */
export function editProblems(rows) {
  const bad = [];
  const real = (rows || []).filter((r) => clean(r.headingMs) || clean(r.headingEn));
  if (!real.length) bad.push(["sekurang-kurangnya satu bahagian", "at least one section"]);
  real.forEach((r, i) => { if (r.kind === "table" && pipe(r.columnsMs || r.columnsEn).length < 2) bad.push([`bahagian ${i + 1}: jadual perlu dua lajur atau lebih (asingkan dengan |)`, `section ${i + 1}: a table needs two or more columns (separate with |)`]); });
  return bad;
}

/** The editor's rows back into stored sections. The worker re-checks them when a document is made: it numbers the first column
    called No. or Bil., and keeps a column that names an owner, date, version or signature only when the material has it. */
export function structureFromEdit(rows) {
  const out = [];
  for (const r of rows || []) {
    const ms = clean(r.headingMs).slice(0, 120), en = clean(r.headingEn).slice(0, 120);
    if (!ms && !en) continue;
    const kind = ["paragraphs", "bullets", "table"].includes(r.kind) ? r.kind : "paragraphs";
    const hint = clean(r.hint).slice(0, 300);
    const sec = { key: `s${out.length + 1}`, kind, heading: { ms: ms || en, en: en || ms }, hint: { ms: hint, en: hint } };
    if (kind === "table") {
      const cm = pipe(r.columnsMs), ce = pipe(r.columnsEn);
      const names = cm.length ? cm : ce;
      sec.columns = names.slice(0, 8).map((c, i) => ({ ms: cm[i] || ce[i] || c, en: ce[i] || cm[i] || c }));
    } else if (r.optional) sec.optional = true;
    out.push(sec);
  }
  return out;
}

/** The languages a request asked for, in the order they are shown. */
export const docLangs = (row) => (row?.lang === "both" ? ["ms", "en"] : [row?.lang === "en" ? "en" : "ms"]);
export const typeOf = (id) => DOC_TYPES.find((t) => t.id === id);

/** What a reviewer should look at first in a finished draft. */
export function docWarnings(doc) {
  return { check: doc?.source_check?.length || 0, wording: doc?.flags?.length || 0, confirm: doc?.to_confirm?.length || 0, conflicts: doc?.conflicts?.length || 0, truncated: !!doc?.truncated };
}

/** A finished draft as plain text, for copying. */
export function docToText(doc) {
  const g = doc.generic || {};
  const out = [doc.title, doc.status, "", ...(doc.meta || []).map(([k, v]) => `${k}: ${v}`)];
  for (const s of doc.sections || []) {
    out.push("", s.heading.toUpperCase());
    if (s.kind === "table") { out.push(s.columns.join(" | ")); s.rows.forEach((r) => out.push(r.join(" | "))); }
    else out.push(...(s.bullets || s.paragraphs || []).map((x) => (s.kind === "bullets" ? `- ${x}` : x)));
  }
  const list = (h, items) => { if (items?.length) out.push("", String(h || "").toUpperCase(), ...items.map((x) => `- ${x}`)); };
  list(g.to_confirm, doc.to_confirm); list(g.conflicts, doc.conflicts); list(g.source_check, doc.source_check?.length ? [doc.source_check.join(", ")] : []); list(g.flags, doc.flags);
  out.push("", doc.disclaimer);
  return out.join("\n");
}
