/* The FAQ AI bar's browser half: turn pasted / dropped / chosen files into what the reader can take, send them, and
   hand back the question-and-answer pairs found. Pure parts (cutting, batching, matching) are in faqAiLogic.js.

   Nothing is written here. The pairs come back to the page, Wan keeps the ones he wants, and the page inserts each as a
   `new` FAQ row: the worker (backend/semasa/faq.py) then rewrites, anonymises and categorises it like any other.

   PDF: read in the browser with pdf.js, loaded only when a PDF is chosen. A page with text sends its text; a page with
   none (a scan, a photographed page) is drawn and sent as a picture, so a scanned PDF works too. */
import { supabase } from "./SupabaseClient";
import { explain } from "./chat";
import { AI_LIMITS, batchInputs, fitSize, mergeItems, tilePlan } from "./faqAiLogic";

const IMG = /^image\/(png|jpe?g|webp|gif)$/;
const TEXT_EXT = /\.(txt|md|csv|tsv|json|log)$/i;

export function acceptKind(file) {
  if (IMG.test(file.type)) return "image";
  if (file.type === "application/pdf" || /\.pdf$/i.test(file.name || "")) return "pdf";
  if (file.type.startsWith("text/") || TEXT_EXT.test(file.name || "")) return "text";
  return "";
}

const readAs = (file, how) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(r.result);
  r.onerror = () => reject(r.error);
  r[how](file);
});

const toJpeg = (canvas) => canvas.toDataURL("image/jpeg", 0.85);

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("gambar tidak boleh dibuka / the picture could not be opened")); };
    img.src = url;
  });
}

/** One picture → one or more JPEGs (a tall screenshot is cut into overlapping tiles, each shrunk to a readable size). */
async function imageItems(file, name) {
  const img = await loadImage(file);
  const tiles = tilePlan(img.naturalWidth, img.naturalHeight);
  return tiles.map((t, i) => {
    const { w, h } = fitSize(img.naturalWidth, t.h, 1800);
    const scale = w / img.naturalWidth;
    const c = document.createElement("canvas");
    c.width = w; c.height = Math.max(1, Math.round(t.h * scale));
    const ctx = c.getContext("2d");
    ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height); // a transparent PNG would turn black in a JPEG
    ctx.drawImage(img, 0, t.y, img.naturalWidth, t.h, 0, 0, c.width, c.height);
    void h;
    return { name: tiles.length > 1 ? `${name} (bahagian ${i + 1}/${tiles.length})` : name, dataUrl: toJpeg(c) };
  });
}

let pdfLib = null;
async function pdfjs() {
  if (pdfLib) return pdfLib;
  // the LEGACY build: pdf.js 5's modern one calls Map.getOrInsertComputed, which most browsers do not have yet
  // ("getOrInsertComputed is not a function" in Chromium 141); the legacy build carries its own fallbacks
  const lib = await import("pdfjs-dist/legacy/build/pdf.mjs");
  const worker = (await import("pdfjs-dist/legacy/build/pdf.worker.min.mjs?url")).default;
  lib.GlobalWorkerOptions.workerSrc = worker;
  pdfLib = lib;
  return lib;
}

async function pdfItems(file, name) {
  const lib = await pdfjs();
  const doc = await lib.getDocument({ data: new Uint8Array(await readAs(file, "readAsArrayBuffer")) }).promise;
  const pages = Math.min(doc.numPages, AI_LIMITS.pdfPages);
  const items = [];
  let text = "", pictures = 0, scanned = 0;
  for (let n = 1; n <= pages; n++) {
    const page = await doc.getPage(n);
    const content = await page.getTextContent();
    let line = "", lastY = null;
    const lines = [];
    for (const it of content.items) {
      if (typeof it.str !== "string") continue;
      const y = it.transform?.[5];
      if (lastY !== null && y !== undefined && Math.abs(y - lastY) > 3) { lines.push(line); line = ""; }
      line += it.str + (it.hasEOL ? "\n" : "");
      lastY = y ?? lastY;
    }
    lines.push(line);
    const pageText = lines.join("\n").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
    if (pageText.length >= 40) {
      text += `\n\n--- ${name} · halaman ${n} ---\n${pageText}`;
    } else if (pictures < AI_LIMITS.pdfImagePages) {
      const vp0 = page.getViewport({ scale: 1 });
      const vp = page.getViewport({ scale: Math.min(2.5, 1500 / vp0.width) });
      const c = document.createElement("canvas");
      c.width = Math.round(vp.width); c.height = Math.round(vp.height);
      const ctx = c.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height);
      await page.render({ canvasContext: ctx, viewport: vp }).promise;
      items.push({ name: `${name} · halaman ${n}`, dataUrl: toJpeg(c) });
      pictures++; scanned++;
    }
    page.cleanup();
  }
  if (text.trim()) items.unshift({ name, text: text.trim() });
  const notes = [];
  if (doc.numPages > pages) notes.push({ name, skipped: `hanya ${pages} halaman pertama dibaca daripada ${doc.numPages} / only the first ${pages} of ${doc.numPages} pages were read` });
  if (!items.length) notes.push({ name, skipped: "PDF ini tiada teks dan halaman tidak dapat dilukis / this PDF has no text and its pages could not be drawn" });
  if (scanned >= AI_LIMITS.pdfImagePages) notes.push({ name, skipped: `halaman imbasan melebihi ${AI_LIMITS.pdfImagePages}; selebihnya tidak dibaca / more than ${AI_LIMITS.pdfImagePages} scanned pages; the rest were not read` });
  return [...items, ...notes];
}

/** Everything the person gave → items for batchInputs. A file that cannot be read is named, never dropped silently. */
export async function prepareInputs(files, onProgress = () => {}) {
  const out = [];
  const list = Array.from(files || []).slice(0, AI_LIMITS.files);
  const extra = Array.from(files || []).length - list.length;
  for (let i = 0; i < list.length; i++) {
    const f = list[i];
    const name = f.name || (IMG.test(f.type) ? `tampalan-${i + 1}.png` : "fail");
    onProgress(`${i + 1}/${list.length} ${name}`);
    try {
      const kind = acceptKind(f);
      if (kind === "image") {
        out.push(...(f.size > AI_LIMITS.imageBytes ? [{ name, skipped: "gambar lebih 12 MB / picture over 12 MB" }] : await imageItems(f, name)));
      } else if (kind === "pdf") {
        out.push(...(f.size > AI_LIMITS.pdfBytes ? [{ name, skipped: "PDF lebih 25 MB / PDF over 25 MB" }] : await pdfItems(f, name)));
      } else if (kind === "text") {
        out.push({ name, text: String(await readAs(f, "readAsText")) });
      } else {
        out.push({ name, skipped: "jenis fail ini belum boleh dibaca (gambar, PDF dan teks sahaja) / this file type is not read yet (pictures, PDF and text only)" });
      }
    } catch (e) {
      out.push({ name, skipped: `gagal dibaca / could not be read: ${String(e?.message || e).slice(0, 100)}` });
    }
  }
  if (extra > 0) out.push({ name: "…", skipped: `${extra} fail lagi tidak dibaca; had ${AI_LIMITS.files} fail sekali / ${extra} more files not read; ${AI_LIMITS.files} files at a time` });
  return out;
}

/** Send the prepared items (several calls when there is a lot) and fold the answers into one list. Never throws:
    `errors` says which call failed and why, `items` keeps what the others found. */
export async function extractFaqs({ note = "", inputs = [], onProgress = () => {} }) {
  if (!supabase) return { items: [], notRead: [], errors: ["Supabase belum disambung / Supabase is not configured"], missing: false };
  const { batches, skipped } = batchInputs(inputs);
  const calls = batches.length || (note.trim() ? 1 : 0);
  const lists = [], errors = [], notRead = skipped.map((s) => `${s.name}: ${s.why}`);
  let missing = false;
  for (let i = 0; i < calls; i++) {
    onProgress(calls > 1 ? `AI membaca bahagian ${i + 1}/${calls}… / AI is reading part ${i + 1}/${calls}…` : "AI sedang membaca… / the AI is reading…");
    const { data, error } = await supabase.functions.invoke("semasa-chat", { body: { action: "faq_extract", note: i === 0 ? note : "", files: batches[i] || [] } });
    if (error) {
      const why = await explain(error);
      if (why.missing) { missing = true; errors.push("fungsi belum dipasang / the function is not deployed"); break; }
      errors.push(calls > 1 ? `bahagian ${i + 1}: ${why.message}` : why.message);
      continue;
    }
    if (data?.error) { errors.push(String(data.error)); continue; }
    lists.push(data?.items || []);
    for (const n of data?.not_read || []) notRead.push(n);
  }
  return { items: mergeItems(lists), notRead, errors, missing };
}
