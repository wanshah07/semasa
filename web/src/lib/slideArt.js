/* A post's OWN illustrations in the design picker (Wan, 23 Nov 2026: "I want illustration based on content like this, not fix conical
   flask"). The worker draws one picture per slide from its words (backend/semasa/illustrated.py) and keeps every one on the slide job:
   `meta.art[key] = {url, ...}`, where key = sha1("<STYLE_VERSION>|[cut|]<the slide's words>")[:16]. The picker asks for the same keys, so
   a slide whose words are unchanged shows ITS drawing in every look: the whole drawn page for Diari, a transparent cut-out for the
   others. A slide with no drawing yet shows a plain picture-frame stand-in, never a drawing of something it is not about. */

export const STYLE_VERSION = 2;                      // illustrated.STYLE_VERSION: bump both together (web/slideArt.test.mjs reads the file)

/** The words a drawing depends on, joined as illustrated.key_of joins them. */
export const wordsOf = (s) => [s?.title, s?.lead, ...(Array.isArray(s?.points) ? s.points : []), s?.note].map((x) => String(x || "")).join("\n");

/** illustrated.key_of(item, cut): the first 16 hex of sha1("2|cut|<words>"). */
export async function artKey(slide, cut = false) {
  const data = new TextEncoder().encode(`${STYLE_VERSION}|${cut ? "cut|" : ""}${wordsOf(slide)}`);
  const hex = [...new Uint8Array(await globalThis.crypto.subtle.digest("SHA-1", data))].map((b) => b.toString(16).padStart(2, "0")).join("");
  return hex.slice(0, 16);
}

/** key → address, over every slide job of the post (a later job wins). Jobs come newest first, so they are read oldest first. */
export function artIndex(jobs) {
  const idx = new Map();
  for (const j of [...(jobs || [])].reverse()) {
    const art = j?.meta?.art;
    if (!art || typeof art !== "object") continue;
    for (const [k, v] of Object.entries(art)) if (v && typeof v.url === "string" && v.url) idx.set(k, v.url);
  }
  return idx;
}

/** {cut, page} addresses for each slide ("" when the worker has not drawn that one). */
export async function artFor(slides, jobs) {
  const idx = artIndex(jobs);
  if (!idx.size) return slides.map(() => ({ cut: "", page: "" }));
  return Promise.all(slides.map(async (s) => ({ cut: idx.get(await artKey(s, true)) || "", page: idx.get(await artKey(s, false)) || "" })));
}

// ---- the brand cover's own title and illustration ---------------------------------------------------------------------------------

export const COVER_TITLE_WORDS = 12;                  // carousel.COVER_TITLE_WORDS: the cover's title is ONE COMPLETE SENTENCE of at most this many words
export const LEAD_SENTENCE_MAX = 22;
/** carousel._lead_sentence: the first WHOLE sentence of `text`, no trailing punctuation; longer than `most` words it is cut at its
    last comma, semicolon or colon inside the limit, else kept whole. Never a few words cut off a longer line. */
export function leadSentence(text, most = LEAD_SENTENCE_MAX) {
  const t = String(text || "").replace(/\*/g, "").replace(/\s+/g, " ").trim();
  const first = t.split(/(?<=[.!?])\s+/)[0].trim().replace(/[.!?,;:]+$/, "");
  const w = first.split(" ").filter(Boolean);
  if (w.length <= most) return first;
  const head = w.slice(0, most).join(" ");
  const cut = Math.max(head.lastIndexOf(","), head.lastIndexOf(";"), head.lastIndexOf(":"));
  return cut > 0 && head.slice(0, cut).trim().split(" ").length >= 4 ? head.slice(0, cut).trim() : first;
}
// kept for older callers: the first clause when short enough, else its first n words
export function leadWords(text, n) {
  const t = String(text || "").replace(/\*/g, "").replace(/\s+/g, " ").trim();
  const first = t.split(/(?<=[.:;!?])\s+/)[0].trim().replace(/[.:;!?,]+$/, "");
  const c = first.split(" ").filter(Boolean).length;
  if (c >= 2 && c <= n) return first;
  return t.split(" ").slice(0, n).join(" ").replace(/[.:;!?,]+$/, "");
}
/** What the preview's cover says: the title the worker chose when a finished job drew this very hook, else the same fallback the
    worker uses when no writer answers (the hook itself when it is already short). */
export function coverTitleFor(first, jobs) {
  const hook = String(first?.title || "").trim();
  if (!hook) return "";
  for (const j of jobs || []) {
    const ct = String(j?.meta?.cover_title || "").trim();
    if (ct && j.status === "done" && (j.meta.slides || []).some((s) => String(s?.title || "").trim() === hook)) return ct;
  }
  return hook.replace(/\*/g, "").split(/\s+/).length <= COVER_TITLE_WORDS ? hook : leadSentence(hook);
}
/** The address of the hook's cover illustration the worker kept for this slide ("cover|" + the slide's key), or "". */
export async function coverArtUrl(first, jobs) {
  if (!first) return "";
  return artIndex(jobs).get("cover|" + await artKey(first)) || "";
}

// ---- turning a drawing on a white page into a cut-out (the browser twin of illustrated.cutout) ----------------------------------

const PAGE_WHITE = 232;                               // illustrated.CUT_WHITE: a pixel this light on every channel is page, not ink
const PAGE_TOL = 26;                                  // a cream or tinted page: within this of the colour the edges are made of
/** The colour of the page round a drawing: the median of the LIGHT pixels on its four edges ([r,g,b]), or null when the edges are
    mostly ink (a picture that fills its whole frame). */
export function pageColour(px, w, h) {
  const at = [];
  for (let x = 0; x < w; x += 2) { at.push(x, (h - 1) * w + x); }
  for (let y = 0; y < h; y += 2) { at.push(y * w, y * w + w - 1); }
  const light = at.filter((i) => px[i * 4 + 3] > 0 && Math.min(px[i * 4], px[i * 4 + 1], px[i * 4 + 2]) >= 170);
  if (light.length < at.length * 0.4) return null;
  const med = (c) => { const v = light.map((i) => px[i * 4 + c]).sort((p, q) => p - q); return v[v.length >> 1]; };
  return [med(0), med(1), med(2)];
}
/** In place: the page round the drawing (the page colour reached from the edges) becomes transparent, then a white sticker border of
    `r` px is grown round what is left. White is the worker's rule (CUT_WHITE); a cream page, like the Diari drawings, is taken away
    by its own colour so a stored drawing is transparent in the picker too. `px` is RGBA, row by row. Returns false when no page
    was found (the picture fills its card). */
export function cutPixels(px, w, h, r = Math.max(6, Math.round(w * 0.012))) {
  const pc = pageColour(px, w, h);
  if (!pc) return false;
  const whitePage = Math.min(...pc) >= PAGE_WHITE;
  const page = new Uint8Array(w * h), stack = [];
  const white = (i) => px[i * 4 + 3] > 0 && (whitePage
    ? px[i * 4] >= PAGE_WHITE && px[i * 4 + 1] >= PAGE_WHITE && px[i * 4 + 2] >= PAGE_WHITE
    : Math.abs(px[i * 4] - pc[0]) <= PAGE_TOL && Math.abs(px[i * 4 + 1] - pc[1]) <= PAGE_TOL && Math.abs(px[i * 4 + 2] - pc[2]) <= PAGE_TOL);
  const seed = (i) => { if (!page[i] && white(i)) { page[i] = 1; stack.push(i); } };
  for (let x = 0; x < w; x++) { seed(x); seed((h - 1) * w + x); }
  for (let y = 0; y < h; y++) { seed(y * w); seed(y * w + w - 1); }
  if (!stack.length) return false;
  while (stack.length) {
    const i = stack.pop(), x = i % w, y = (i - x) / w;
    if (x > 0) seed(i - 1);
    if (x < w - 1) seed(i + 1);
    if (y > 0) seed(i - w);
    if (y < h - 1) seed(i + w);
  }
  // the drawing = everything that is not page; its border = the drawing grown by r (a box, two passes)
  const solid = new Uint8Array(w * h);
  for (let i = 0; i < w * h; i++) solid[i] = page[i] ? 0 : 1;
  const grow = (src, along, across, len, n) => {
    const out = new Uint8Array(w * h);
    for (let a = 0; a < across; a++) {
      let count = 0;
      const at = (t) => (along === "x" ? a * w + t : t * w + a);
      for (let t = 0; t < Math.min(r, len); t++) count += src[at(t)];
      for (let t = 0; t < len; t++) {
        if (t + r < len) count += src[at(t + r)];
        if (t - r - 1 >= 0) count -= src[at(t - r - 1)];
        out[at(t)] = count > 0 ? 1 : 0;
      }
    }
    return out;
  };
  const border = grow(grow(solid, "x", h, w), "y", w, h);
  for (let i = 0; i < w * h; i++) {
    if (solid[i]) continue;
    if (border[i]) { px[i * 4] = px[i * 4 + 1] = px[i * 4 + 2] = 255; px[i * 4 + 3] = 255; } else px[i * 4 + 3] = 0;
  }
  return true;
}

const loadImage = (src) => new Promise((res) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => res(null); i.src = src; });
/** An address as a blob address of this page (the card canvas must not be tainted by a picture from another origin, and a short
    string keeps the picker's render keys small), or "" when it cannot be read. */
export async function dataUrlOf(url) {
  try {
    const r = await fetch(url, { mode: "cors" });
    return r.ok ? URL.createObjectURL(await r.blob()) : "";
  } catch (e) { return ""; }
}
const toBlobUrl = (canvas, type, q) => new Promise((res) => canvas.toBlob((b) => res(b ? URL.createObjectURL(b) : ""), type, q));
/** A drawing on a white page → a PNG blob address with the page transparent and a white sticker border; the input when no page is found. */
export async function cutOutUrl(src) {
  const im = await loadImage(src);
  if (!im) return "";
  const c = document.createElement("canvas"); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const ctx = c.getContext("2d"); ctx.drawImage(im, 0, 0);
  const d = ctx.getImageData(0, 0, c.width, c.height);
  if (!cutPixels(d.data, c.width, c.height)) return src;
  ctx.putImageData(d, 0, 0);
  return toBlobUrl(c, "image/png");
}
/** A cut-out laid on a white page (Diari draws its picture as a whole page): a JPEG blob address. */
export async function onPageUrl(src) {
  const im = await loadImage(src);
  if (!im) return "";
  const c = document.createElement("canvas"); c.width = im.naturalWidth; c.height = im.naturalHeight;
  const ctx = c.getContext("2d"); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height); ctx.drawImage(im, 0, 0);
  return toBlobUrl(c, "image/jpeg", 0.92);
}
