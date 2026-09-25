/* FAQ exports, all made in the browser: Excel (.xlsx), PDF (the browser's own "Save as PDF", from a
   print-ready page) and posters (PNG, drawn on a canvas). Nothing leaves the page to make them.

   Posters follow the slide renderer's rules (backend/semasa/slides.py): every word is kept (a card
   that cannot fit says so instead of cutting), a token too wide for the column is split by
   character, and the website is on the footer only. */
import DEFAULTS from "../../../rules/faq_categories.json";
import { tr } from "./i18n";

export const DEFAULT_CATEGORIES = DEFAULTS.categories;

/** The live category list (semasa_settings.faq) or the defaults; "lain" is always there. */
export function faqCategories(settings) {
  const raw = settings?.faq?.categories;
  const list = (Array.isArray(raw) && raw.length ? raw : DEFAULT_CATEGORIES)
    .filter((c) => c && String(c.key || "").trim())
    .map((c) => {
      const subs = (c.subs || []).map(String).filter((s) => s.trim());
      const out = { key: String(c.key).trim(), bm: String(c.bm || c.key), en: String(c.en || c.key), subs };
      if (c.auto) Object.assign(out, { auto: true, auto_at: c.auto_at || null });   // made by the bot (faq_sort.py)
      const autoSubs = (c.auto_subs || []).map(String).filter((s) => subs.includes(s));
      if (autoSubs.length) out.auto_subs = autoSubs;
      return out;
    });
  if (!list.some((c) => c.key === "lain")) list.push({ key: "lain", bm: "Lain-lain", en: "Other", subs: [] });
  return list;
}

export const qOf = (r, lang) => (lang === "en" ? r.question_en : r.question_bm) || r.question_bm || r.raw_question || "";
export const aOf = (r, lang) => (lang === "en" ? r.answer_en : r.answer_bm) || r.answer_bm || r.raw_answer || "";

const slug = (s) => String(s || "faq").toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "faq";
const today = () => new Date().toISOString().slice(0, 10);
export const fileName = (label, ext, extra = "") => `faq-${slug(label)}${extra ? `-${extra}` : ""}-${today()}.${ext}`;

export function download(blob, name) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.rel = "noopener";
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30_000);
}

// --- Excel -------------------------------------------------------------------------------

export function excelSheets(rows, cats, label) {
  const catLabel = Object.fromEntries(cats.map((c) => [c.key, c.bm]));
  const head = ["Kategori", "Subkategori", "Soalan (BM)", "Jawapan (BM)", "Question (EN)", "Answer (EN)", "Tag",
    "Instrumen / sumber rasmi", "Perlu semakan", "Dikemas kini"];
  const widths = [18, 22, 50, 70, 50, 70, 20, 30, 14, 18];
  const data = [head.map((h) => ({ value: h, fontWeight: "bold", wrap: true })),
    ...rows.map((r) => [catLabel[r.category] || r.category, r.subcategory, r.question_bm, r.answer_bm, r.question_en,
      r.answer_en, (r.tags || []).join(", "), r.instrument, r.needs_check ? "YA" : "", String(r.updated_at || "").slice(0, 10)]
      .map((v) => ({ type: String, value: String(v ?? ""), wrap: true })))];
  const sheet = String(label || "FAQ").replace(/[[\]*?/\\:]/g, " ").slice(0, 31) || "FAQ";
  return [{ data, sheet, columns: widths.map((width) => ({ width })) }];
}

export async function exportExcel(rows, cats, label) {
  const { default: writeExcelFile } = await import("write-excel-file/browser");
  const blob = await writeExcelFile(excelSheets(rows, cats, label)).toBlob();
  download(blob, fileName(label, "xlsx"));
}

// --- PDF (print) ------------------------------------------------------------------------------

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/** A print-ready HTML document. `lang` is "bm", "en" or "both". Internal notes never appear. */
export function pdfHtml(rows, { label, lang = "bm", website = "", cats = [] }) {
  const catLabel = Object.fromEntries(cats.map((c) => [c.key, lang === "en" ? c.en : c.bm]));
  const groups = [];
  for (const r of rows) {
    const g = `${catLabel[r.category] || r.category}${r.subcategory ? ` · ${r.subcategory}` : ""}`;
    const last = groups[groups.length - 1];
    if (last && last.name === g) last.rows.push(r); else groups.push({ name: g, rows: [r] });
  }
  const one = (r, lg) => `<div class="qa"><p class="q">${esc(qOf(r, lg))}</p><p class="a">${esc(aOf(r, lg))}</p></div>`;
  const body = groups.map((g) => `<h2>${esc(g.name)}</h2>${g.rows.map((r) => `<section>
      ${lang === "both" ? `${one(r, "bm")}<div class="en">${one(r, "en")}</div>` : one(r, lang)}
      ${r.instrument ? `<p class="src">${lang === "en" ? "Source" : "Sumber"}: ${esc(r.instrument)}</p>` : ""}
    </section>`).join("")}`).join("");
  const title = `FAQ · ${label}`;
  return `<!doctype html><html lang="${lang === "en" ? "en" : "ms"}"><head><meta charset="utf-8"><title>${esc(title)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<style>
@page { size: A4; margin: 18mm 16mm 20mm; }
body { font: 10.5pt/1.5 Inter, system-ui, sans-serif; color: #1c1917; margin: 0; }
header { border-bottom: 2px solid #b0792a; padding-bottom: 8pt; margin-bottom: 14pt; }
.eyebrow { color: #b0792a; font: 600 8pt Inter; letter-spacing: .18em; text-transform: uppercase; margin: 0; }
h1 { font: 600 22pt/1.15 Fraunces, Georgia, serif; margin: 4pt 0 0; }
.meta { color: #78716c; font-size: 8.5pt; margin: 4pt 0 0; }
h2 { font: 600 13pt Fraunces, Georgia, serif; color: #b0792a; margin: 16pt 0 6pt; break-after: avoid; }
section { break-inside: avoid; border-bottom: 1px solid #e6ddce; padding: 7pt 0; }
.q { font-weight: 600; margin: 0 0 3pt; }
.a { margin: 0; white-space: pre-line; }
.en { margin-top: 5pt; padding-left: 8pt; border-left: 2px solid #e6ddce; color: #44403c; }
.src { color: #78716c; font-size: 8.5pt; margin: 4pt 0 0; }
footer { position: fixed; bottom: -12mm; left: 0; right: 0; color: #78716c; font-size: 8pt; }
</style></head><body>
<header><p class="eyebrow">FAQ</p><h1>${esc(label)}</h1><p class="meta">${rows.length} ${lang === "en" ? "questions" : "soalan"} · ${today()}</p></header>
${body}
${website ? `<footer>${esc(website)}</footer>` : ""}
</body></html>`;
}

/** Opens the browser's print dialog on the document; "Save as PDF" makes the file. */
export function exportPdf(rows, opts) {
  const frame = document.createElement("iframe");
  frame.setAttribute("aria-hidden", "true");
  frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0";
  document.body.appendChild(frame);
  const doc = frame.contentWindow.document;
  doc.open(); doc.write(pdfHtml(rows, opts)); doc.close();
  const go = async () => {
    try { await frame.contentWindow.document.fonts?.ready; } catch { /* print anyway */ }
    frame.contentWindow.focus();
    frame.contentWindow.print();
    setTimeout(() => frame.remove(), 60_000);
  };
  if (doc.readyState === "complete") setTimeout(go, 300); else frame.onload = () => setTimeout(go, 300);
  return frame;
}

// --- posters -------------------------------------------------------------------------------

const W = 1080, H = 1350, M = 88;
const PAPER = "#FAF7F2", INK = "#1C1917", MUTED = "#78716C", ACCENT = "#B0792A", LINE = "#E6DDCE";
const DISPLAY = "Fraunces, Georgia, serif", BODY = "Inter, system-ui, sans-serif";

export class PosterError extends Error {}

async function fontsReady() {
  if (!document.fonts?.load) return;
  await Promise.all(["600 60px Fraunces", "400 36px Inter", "600 24px Inter"].map((f) => document.fonts.load(f).catch(() => null)));
}

/** Split a token wider than the column by character; a token that fits comes back whole. */
export function hardSplit(ctx, word, width) {
  if (ctx.measureText(word).width <= width) return [word];
  const parts = [];
  let cur = "";
  for (const ch of word) {
    if (cur && ctx.measureText(cur + ch).width > width) { parts.push(cur); cur = ch; } else cur += ch;
  }
  if (cur) parts.push(cur);
  return parts;
}

/** Lines of `text` in the context's current font, never wider than `width`. Newlines are kept. */
export function wrap(ctx, text, width) {
  const lines = [];
  for (const para of String(text || "").split(/\n+/)) {
    let cur = "";
    for (const word of para.split(/\s+/).filter(Boolean)) {
      for (const piece of hardSplit(ctx, word, width)) {
        const next = cur ? `${cur} ${piece}` : piece;
        if (cur && ctx.measureText(next).width > width) { lines.push(cur); cur = piece; } else cur = next;
      }
    }
    if (cur) lines.push(cur);
  }
  return lines;
}

function canvas() {
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const ctx = c.getContext("2d");
  ctx.fillStyle = PAPER; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = ACCENT; ctx.fillRect(M, M - 28, 120, 6);
  ctx.textBaseline = "top";
  return [c, ctx];
}

function eyebrow(ctx, text, right) {
  ctx.font = `600 24px ${BODY}`;
  ctx.fillStyle = MUTED;
  if (right) ctx.fillText(right, W - M - ctx.measureText(right).width, M);
  ctx.fillStyle = ACCENT;
  let t = String(text).toUpperCase();
  const room = W - 2 * M - (right ? ctx.measureText(right).width + 40 : 0);
  while (t.length > 3 && ctx.measureText(t).width > room) t = `${t.slice(0, -2).trimEnd()}…`;
  ctx.fillText(t, M, M);
}

function footer(ctx, website, source, lang) {
  let bottom = H - M;
  if (website) {
    ctx.font = `600 26px ${BODY}`; ctx.fillStyle = MUTED;
    ctx.fillText(website, M, bottom - 26);
    bottom -= 26 + 30;
  }
  if (source) {
    ctx.font = `400 22px ${BODY}`; ctx.fillStyle = MUTED;
    const lines = wrap(ctx, `${lang === "en" ? "Source" : "Sumber"}: ${source}`, W - 2 * M).slice(0, 3);
    lines.forEach((ln, i) => ctx.fillText(ln, M, bottom - (lines.length - i) * 30));
    bottom -= lines.length * 30 + 20;
    ctx.fillStyle = LINE; ctx.fillRect(M, bottom, 80, 2);
    bottom -= 16;
  }
  return bottom;
}

const blobOf = (c) => new Promise((ok, no) => c.toBlob((b) => (b ? ok(b) : no(new PosterError(tr("pelayar tidak dapat membuat gambar", "the browser could not make the picture")))), "image/png"));

/** One card per question: 1080×1350, question on top, answer below. */
export async function posterCard(row, { lang = "bm", catLabel = "", website = "" } = {}) {
  await fontsReady();
  const [c, ctx] = canvas();
  eyebrow(ctx, `FAQ · ${catLabel}${row.subcategory ? ` · ${row.subcategory}` : ""}`, "");
  const bottom = footer(ctx, website, row.instrument, lang);
  const top = M + 70;
  const col = W - 2 * M;
  const q = qOf(row, lang), a = aOf(row, lang);
  for (let s = 1; s >= 0.5 - 1e-9; s = Math.round((s - 0.05) * 100) / 100) {
    const qs = Math.round(64 * s), as = Math.round(36 * s);
    ctx.font = `600 ${qs}px ${DISPLAY}`; const ql = wrap(ctx, q, col);
    ctx.font = `400 ${as}px ${BODY}`; const al = wrap(ctx, a, col);
    const qlh = Math.round(qs * 1.15), alh = Math.round(as * 1.45), gap = Math.round(56 * s);
    const h = ql.length * qlh + gap + al.length * alh;
    if (h > bottom - top) continue;
    let y = top + Math.max(0, Math.floor((bottom - top - h) / 2));
    ctx.fillStyle = INK; ctx.font = `600 ${qs}px ${DISPLAY}`;
    ql.forEach((ln) => { ctx.fillText(ln, M, y); y += qlh; });
    ctx.fillStyle = ACCENT; ctx.fillRect(M, y + gap / 2 - 2, 60, 4);
    y += gap;
    ctx.fillStyle = INK; ctx.font = `400 ${as}px ${BODY}`;
    al.forEach((ln) => { ctx.fillText(ln, M, y); y += alh; });
    return blobOf(c);
  }
  throw new PosterError(tr("soalan dan jawapan ini terlalu panjang untuk satu kad; pendekkan jawapan atau guna poster kategori",
    "this question and answer are too long for one card; shorten the answer or use the category poster"));
}

/** A category poster, as many 1080×1350 pages as it takes. Returns PNG blobs in order. */
export async function posterPages(rows, { lang = "bm", label = "", website = "" } = {}) {
  await fontsReady();
  const col = W - 2 * M;
  const measure = document.createElement("canvas").getContext("2d");
  const blockOf = (r, s) => {
    const qs = Math.round(40 * s), as = Math.round(28 * s);
    measure.font = `600 ${qs}px ${DISPLAY}`; const ql = wrap(measure, qOf(r, lang), col);
    measure.font = `400 ${as}px ${BODY}`; const al = wrap(measure, aOf(r, lang), col);
    const qlh = Math.round(qs * 1.18), alh = Math.round(as * 1.45);
    return { ql, al, qs, as, qlh, alh, h: ql.length * qlh + 12 + al.length * alh };
  };
  const GAP = 40;
  const pageTop = (first) => M + 70 + (first ? 160 : 0);
  const pageBottom = H - M - (website ? 56 : 0);
  // lay the blocks out first, so the page count is known before drawing "1/3"
  const pages = [[]];
  let y = pageTop(true);
  for (const r of rows) {
    let b = blockOf(r, 1);
    const room = pageBottom - pageTop(false);
    for (let s = 0.95; b.h > room && s >= 0.6 - 1e-9; s = Math.round((s - 0.05) * 100) / 100) b = blockOf(r, s);
    if (b.h > room) throw new PosterError(tr('"{q}…" terlalu panjang untuk satu halaman poster; pendekkan jawapannya',
      '"{q}…" is too long for a poster page; shorten its answer', { q: qOf(r, lang).slice(0, 60) }));
    // page 1 has 160px less room (the title): a block that does not fit under it starts page 2
    if (y + b.h > pageBottom && (pages[pages.length - 1].length || pages.length === 1)) { pages.push([]); y = pageTop(false); }
    pages[pages.length - 1].push({ b, y });
    y += b.h + GAP;
  }
  const out = [];
  for (let i = 0; i < pages.length; i++) {
    const [c, ctx] = canvas();
    eyebrow(ctx, "FAQ", pages.length > 1 ? `${i + 1}/${pages.length}` : "");
    if (i === 0) {
      ctx.fillStyle = INK; ctx.font = `600 72px ${DISPLAY}`;
      let t = label;
      while (t.length > 3 && ctx.measureText(t).width > col) t = `${t.slice(0, -2).trimEnd()}…`;
      ctx.fillText(t, M, M + 60);
      ctx.fillStyle = MUTED; ctx.font = `400 26px ${BODY}`;
      ctx.fillText(`${rows.length} ${lang === "en" ? "questions" : "soalan"}`, M, M + 150);
    }
    for (const { b, y: by } of pages[i]) {
      let yy = by;
      ctx.fillStyle = INK; ctx.font = `600 ${b.qs}px ${DISPLAY}`;
      b.ql.forEach((ln) => { ctx.fillText(ln, M, yy); yy += b.qlh; });
      yy += 12;
      ctx.fillStyle = "#44403C"; ctx.font = `400 ${b.as}px ${BODY}`;
      b.al.forEach((ln) => { ctx.fillText(ln, M, yy); yy += b.alh; });
      ctx.fillStyle = LINE; ctx.fillRect(M, yy + GAP / 2 - 1, W - 2 * M, 2);
    }
    if (website) { ctx.font = `600 26px ${BODY}`; ctx.fillStyle = MUTED; ctx.fillText(website, M, H - M - 26); }
    out.push(await blobOf(c));
  }
  return out;
}

/** Category poster → one PNG, or a ZIP of pages. */
export async function exportPoster(rows, { lang, label, website }) {
  const pages = await posterPages(rows, { lang, label, website });
  if (pages.length === 1) return download(pages[0], fileName(label, "png", lang));
  const { zipSync } = await import("fflate");
  const files = {};
  for (let i = 0; i < pages.length; i++) {
    files[`${slug(label)}-${lang}-${String(i + 1).padStart(2, "0")}.png`] = new Uint8Array(await pages[i].arrayBuffer());
  }
  download(new Blob([zipSync(files, { level: 0 })], { type: "application/zip" }), fileName(label, "zip", `poster-${lang}`));
}
