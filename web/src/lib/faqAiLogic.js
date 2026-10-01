/* The pure half of the FAQ AI bar (pages/FaqTab.jsx → lib/faqAi.js), so Node can test it (web/faq_ai.test.mjs).

   Wan, 1 Oct 2026: "for faq add AI bar that allow us to paste screenshot, image, upload pdf then AI will analyze and
   auto to categorize them to proper Q&A FAQ". The limits below mirror supabase/functions/semasa-chat/faq.js: a call
   the function would refuse is split here instead of failing there. */

export const AI_LIMITS = { images: 6, text: 40_000, files: 12, pdfPages: 40, pdfImagePages: 12, imageBytes: 12_000_000, pdfBytes: 25_000_000,
  officeBytes: 20_000_000, calls: 10, note: 500 };

const EXT = (name) => (String(name || "").toLowerCase().match(/\.([a-z0-9]+)$/) || [])[1] || "";
/** What the bar does with a file: image | pdf | docx | xlsx | csv | text, or `legacy` (an old Office or other format it
    names and refuses), or "" (not a thing it reads). Decided by the extension first: browsers often send no type for
    .csv or .docx, and Windows sends odd ones. */
export function kindOf(name, type = "") {
  const ext = EXT(name), ty = String(type || "").toLowerCase();
  if (/^image\/(png|jpe?g|webp|gif)$/.test(ty) || ["png", "jpg", "jpeg", "webp", "gif"].includes(ext)) return "image";
  if (ty === "application/pdf" || ext === "pdf") return "pdf";
  if (ext === "docx" || ext === "docm" || ty === "application/vnd.openxmlformats-officedocument.wordprocessingml.document") return "docx";
  if (ext === "xlsx" || ext === "xlsm" || ty === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") return "xlsx";
  if (ext === "csv" || ext === "tsv" || ty === "text/csv" || ty === "text/tab-separated-values") return "csv";
  if (["doc", "xls", "xlsb", "rtf", "odt", "ods", "ppt", "pptx", "pages", "numbers", "heic", "heif", "tif", "tiff", "bmp", "svg"].includes(ext)) return "legacy";
  if (["txt", "md", "json", "log"].includes(ext) || ty.startsWith("text/")) return "text";
  return "";
}

/** Why a `legacy` file is refused, in one line the person can act on. */
export function legacyWhy(name) {
  const ext = EXT(name);
  if (["doc", "rtf", "odt", "pages"].includes(ext)) return "fail Word lama; buka dan simpan sebagai .docx atau PDF / an old Word format: open it and save as .docx or PDF";
  if (["xls", "xlsb", "ods", "numbers"].includes(ext)) return "fail Excel lama; buka dan simpan sebagai .xlsx atau .csv / an old Excel format: open it and save as .xlsx or .csv";
  if (["ppt", "pptx"].includes(ext)) return "PowerPoint belum boleh dibaca; simpan sebagai PDF / PowerPoint is not read yet: save it as a PDF";
  return "format gambar ini belum boleh dibaca; simpan sebagai PNG atau JPG / this picture format is not read yet: save it as PNG or JPG";
}

/** A typed or pasted text longer than the note limit is MATERIAL, not a note: the function keeps only 500 characters of a
    note, so a pasted Q&A of 2,000 characters would have been cut without a word. It goes as a text file instead. */
export function splitNote(note) {
  const text = String(note || "").trim();
  if (!text) return { note: "", material: "" };
  return text.length > AI_LIMITS.note ? { note: "", material: text } : { note: text, material: "" };
}

/** What each kept pair is filed as. Never the file's own name: a screenshot called "Syarikat ABC - Puan Siti.png" would
    otherwise go into source_name, which the worker mirrors to the Semasa sheet. */
export function sourceLabel(kinds) {
  const names = { image: "gambar", pdf: "PDF", docx: "Word", xlsx: "Excel", csv: "CSV", text: "teks", typed: "teks ditaip" };
  const seen = [...new Set((kinds || []).map((k) => names[k]).filter(Boolean))];
  return seen.length ? seen.join(" + ") : "teks ditaip";
}

/** Where a long screenshot is cut. A phone screenshot of a chat can be 1080 x 5000: sent whole, the reader shrinks it
    until the words are unreadable. Tiles are at most `maxRatio` times as tall as wide and overlap a little, so a
    message cut by one tile is whole in the next (the duplicate question that results is folded by mergeItems). */
export function tilePlan(width, height, { maxRatio = 1.8, overlap = 0.08 } = {}) {
  const w = Math.max(1, Math.round(width)), h = Math.max(1, Math.round(height));
  const tileH = Math.round(w * maxRatio);
  if (h <= Math.round(tileH * 1.15)) return [{ y: 0, h }];
  const step = Math.round(tileH * (1 - overlap));
  const tiles = [];
  for (let y = 0; y < h; y += step) {
    const th = Math.min(tileH, h - y);
    if (tiles.length && th < tileH * 0.25) { tiles[tiles.length - 1].h = h - tiles[tiles.length - 1].y; break; } // a sliver joins the last tile
    tiles.push({ y, h: th });
    if (y + th >= h) break;
  }
  return tiles;
}

/** The size a picture is sent at: the longest side no more than `max`, never enlarged. */
export function fitSize(width, height, max = 1600) {
  const s = Math.min(1, max / Math.max(width, height, 1));
  return { w: Math.max(1, Math.round(width * s)), h: Math.max(1, Math.round(height * s)) };
}

/** Text cut into pieces of at most `limit` characters, at a blank line or a line end when there is one. `header` (the
    first row of a spreadsheet) is put in front of every piece after the first, inside the limit, so a long sheet keeps
    its column names in each call. */
export function chunkText(text, limit = AI_LIMITS.text, header = "") {
  const out = [];
  let rest = String(text || "").trim();
  const pre = header ? `${header}\n` : "";
  let room = limit;
  while (rest.length > room) {
    let cut = rest.lastIndexOf("\n\n", room);
    if (cut < room * 0.5) cut = rest.lastIndexOf("\n", room);
    if (cut < room * 0.5) cut = room;
    out.push((out.length ? pre : "") + rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
    room = Math.max(1000, limit - pre.length);
  }
  if (rest) out.push((out.length ? pre : "") + rest);
  return out;
}

/** Prepared items → calls the function takes: at most `images` pictures and `text` characters each. Items marked
    `skipped` never go; they are reported back by name. Order is kept so a PDF's pages stay in order. `pairs` items (a
    spreadsheet that already has question and answer columns) need no reading at all and come back as `direct`. No more
    than `calls` calls are made; the rest are counted in `dropped` so the page can say so. */
export function batchInputs(items) {
  const batches = [];
  const skipped = [];
  const direct = [];
  let cur = { files: [], images: 0, chars: 0 };
  const flush = () => { if (cur.files.length) batches.push(cur.files); cur = { files: [], images: 0, chars: 0 }; };
  for (const it of items || []) {
    if (it.skipped) { skipped.push({ name: it.name, why: it.skipped }); continue; }
    if (it.pairs) { direct.push(...it.pairs); continue; }
    if (it.dataUrl) {
      if (cur.images >= AI_LIMITS.images) flush();
      cur.files.push({ name: it.name, dataUrl: it.dataUrl }); cur.images++;
    } else if (it.text) {
      for (const piece of chunkText(it.text, AI_LIMITS.text, it.header || "")) {
        if (cur.chars + piece.length > AI_LIMITS.text) flush();
        cur.files.push({ name: it.name, text: piece }); cur.chars += piece.length;
      }
    }
  }
  flush();
  const dropped = Math.max(0, batches.length - AI_LIMITS.calls);
  return { batches: batches.slice(0, AI_LIMITS.calls), skipped, direct, dropped };
}

const fold = (s) => String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
const STOP = new Set(["the", "a", "an", "is", "are", "of", "to", "for", "in", "on", "and", "or", "can", "do", "does", "apa", "yang", "dan", "atau", "ke", "di", "ini", "itu", "boleh", "kah", "bolehkah", "adakah", "what", "how"]);
const words = (s) => new Set(fold(s).split(" ").filter((w) => w.length > 1 && !STOP.has(w)));

/** 0..1: how much two questions share. Word overlap against the SMALLER set, so a short question inside a longer
    one still counts as the same question. Two questions of fewer than three real words are never "similar". */
export function similarity(a, b) {
  const A = words(a), B = words(b);
  if (A.size < 3 || B.size < 3) return fold(a) && fold(a) === fold(b) ? 1 : 0;
  let hit = 0;
  for (const w of A) if (B.has(w)) hit++;
  return hit / Math.min(A.size, B.size);
}

export const SIMILAR_AT = 0.8;

/** Fold the results of several calls into one list: a question seen twice (tile overlap, two pages) keeps the longer
    answer and the `unclear` flag only when both were unclear. */
export function mergeItems(lists) {
  const out = [];
  for (const list of lists || []) {
    for (const it of list || []) {
      const at = out.findIndex((o) => similarity(o.question, it.question) >= 0.9);
      if (at < 0) { out.push({ ...it }); continue; }
      const o = out[at];
      if ((it.answer || "").length > (o.answer || "").length) o.answer = it.answer;
      o.unclear = !!(o.unclear && it.unclear);
      o.instrument = o.instrument || it.instrument || "";
    }
  }
  return out;
}

/** Mark each extracted pair that already exists in the FAQ (ready, waiting or candidate), by any of the question
    texts the row holds. Returns the same items with `exists` = { id, question } or null. Rows the worker has
    dismissed or that failed do not count: re-adding one of those is a reasonable thing to do. */
export function markExisting(items, rows) {
  const live = (rows || []).filter((r) => ["ready", "new", "working", "candidate"].includes(r.status));
  return (items || []).map((it) => {
    let best = null, top = 0;
    for (const r of live) {
      for (const q of [r.raw_question, r.question_bm, r.question_en]) {
        if (!q) continue;
        const s = similarity(it.question, q);
        if (s > top) { top = s; best = r; }
      }
    }
    return { ...it, exists: top >= SIMILAR_AT && best ? { id: best.id, question: best.question_en || best.question_bm || best.raw_question, status: best.status } : null };
  });
}

/** The row the FAQ table takes for one kept pair. The worker rewrites it, anonymises it again and picks the category. */
export function faqRow(it, { userId, sourceLabel }) {
  const hint = String(it.source_hint || "").trim();
  return {
    status: "new", source_kind: "paste",
    raw_question: String(it.question || "").trim().slice(0, 6000),
    raw_answer: String(it.answer || "").trim().slice(0, 6000),
    source_name: `AI bar · ${sourceLabel}${hint ? ` · ${hint}` : ""}`.slice(0, 200),
    category: "lain", category_by: "bot",          // the worker chooses: nothing here pre-empts it
    created_by: userId || null,
  };
}
