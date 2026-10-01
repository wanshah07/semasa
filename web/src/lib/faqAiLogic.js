/* The pure half of the FAQ AI bar (pages/FaqTab.jsx → lib/faqAi.js), so Node can test it (web/faq_ai.test.mjs).

   Wan, 1 Oct 2026: "for faq add AI bar that allow us to paste screenshot, image, upload pdf then AI will analyze and
   auto to categorize them to proper Q&A FAQ". The limits below mirror supabase/functions/semasa-chat/faq.js: a call
   the function would refuse is split here instead of failing there. */

export const AI_LIMITS = { images: 6, text: 40_000, files: 12, pdfPages: 40, pdfImagePages: 12, imageBytes: 12_000_000, pdfBytes: 25_000_000 };

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

/** Text cut into pieces of at most `limit` characters, at a blank line or a page marker when there is one. */
export function chunkText(text, limit = AI_LIMITS.text) {
  const out = [];
  let rest = String(text || "").trim();
  while (rest.length > limit) {
    let cut = rest.lastIndexOf("\n\n", limit);
    if (cut < limit * 0.5) cut = rest.lastIndexOf("\n", limit);
    if (cut < limit * 0.5) cut = limit;
    out.push(rest.slice(0, cut).trim());
    rest = rest.slice(cut).trim();
  }
  if (rest) out.push(rest);
  return out;
}

/** Prepared items → calls the function takes: at most `images` pictures and `text` characters each. Items marked
    `skipped` never go; they are reported back by name. Order is kept so a PDF's pages stay in order. */
export function batchInputs(items) {
  const batches = [];
  const skipped = [];
  let cur = { files: [], images: 0, chars: 0 };
  const flush = () => { if (cur.files.length) batches.push(cur.files); cur = { files: [], images: 0, chars: 0 }; };
  for (const it of items || []) {
    if (it.skipped) { skipped.push({ name: it.name, why: it.skipped }); continue; }
    if (it.dataUrl) {
      if (cur.images >= AI_LIMITS.images) flush();
      cur.files.push({ name: it.name, dataUrl: it.dataUrl }); cur.images++;
    } else if (it.text) {
      for (const piece of chunkText(it.text)) {
        if (cur.chars + piece.length > AI_LIMITS.text) flush();
        cur.files.push({ name: it.name, text: piece }); cur.chars += piece.length;
      }
    }
  }
  flush();
  return { batches, skipped };
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
