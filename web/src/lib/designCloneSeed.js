/* A reference design, read as a LAYOUT by the AI (supabase/functions/semasa-chat/design.js), laid out as Kanvas layers with new words
   (Wan, 1 Oct 2026: "allow upload design, then ai render similarly, only context is different").

   Pure: layout + words in, a seed out (the same `{ width, height, name, layers }` shape lib/canvasSeed.js makes for a Wangian design),
   so Node tests it and CanvasTab.buildSeed draws it. Nothing here calls the AI.

   Positions in the layout are fractions of the canvas, x and y the top-left of the box; the seed's own positions are pixels. Text
   layers keep the existing meaning (x is the CENTRE of the box, `top` its top edge); shapes and photo boxes are given as top-left
   boxes and placed by CanvasTab, which anchors Fabric objects at their centre. */

import { FONTS } from "./fonts.js";

export const FONT_OF = { serif: "Playfair Display", display: "Anton", condensed: "Anton", mono: "JetBrains Mono", script: "Caveat" };

/** The font family for a class and weight. "sans" is Poppins when bold (it has 600 to 800 only) and Instrument Sans otherwise. */
export function fontFor(cls, weight) {
  if (cls === "sans") return weight >= 650 ? "Poppins" : "Instrument Sans";
  return FONT_OF[cls] || "Poppins";
}
export const nearestWeight = (family, want) => {
  const ws = FONTS[family] || [400];
  return ws.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a), ws[0]);
};

/** `*word*` marks the key word of a headline (the post writer's convention); the editor cannot style part of a line, so the marks go. */
export const stripEmph = (s) => String(s || "").replace(/\*([^*\n]+)\*/g, "$1");

/** Linear-gradient end points in pixels, in the object's own box (0,0 top-left), for a CSS-style angle: 0 runs bottom to top,
    90 left to right, 180 top to bottom. The line is as long as it takes for the corners to reach the end colours. */
export function gradientCoords(angle, w, h) {
  const a = (Number(angle) || 0) * Math.PI / 180;
  const dx = Math.sin(a), dy = -Math.cos(a);
  const len = Math.abs(w * dx) + Math.abs(h * dy);
  const cx = w / 2, cy = h / 2;
  return { x1: cx - dx * len / 2, y1: cy - dy * len / 2, x2: cx + dx * len / 2, y2: cy + dy * len / 2 };
}

const byPosition = (a, b) => a.y - b.y || a.x - b.x;
const area = (e) => e.w * e.h;

/** The text blocks of a layout sorted into the slots the new words fill. */
export function slotsOf(layout) {
  const text = (layout?.elements || []).filter((e) => e.type === "text");
  const headlines = text.filter((e) => e.role === "headline").sort((a, b) => b.size * area(b) - a.size * area(a));
  return {
    headline: headlines[0] || null,
    extraHeadlines: headlines.slice(1),
    eyebrow: text.filter((e) => e.role === "eyebrow").sort(byPosition)[0] || null,
    points: text.filter((e) => e.role === "point").sort(byPosition),
    source: text.filter((e) => e.role === "source").sort(byPosition)[0] || null,
    deco: text.filter((e) => e.role === "deco"),
  };
}

/** The words the AI wrote into the layout (when the request carried a brief), as { eyebrow, headline, points, source }. */
export function wordsFromLayout(layout) {
  const s = slotsOf(layout);
  return {
    eyebrow: s.eyebrow?.text || "", headline: s.headline?.text || "", points: s.points.map((p) => p.text).filter(Boolean),
    source: s.source?.text || "",
  };
}

const slotName = (role, i, t) => (role === "headline" ? t("Tajuk", "Headline") : role === "eyebrow" ? t("Label", "Label")
  : role === "source" ? t("Sumber", "Source") : t("Poin {n}", "Point {n}", { n: i + 1 }));

/** One text element as a seed layer with `text` in place of its reference text. */
function textLayer(el, text, name, W, H, u) {
  const font = fontFor(el.font, el.weight);
  const shown = stripEmph(text);
  return {
    kind: "text", name, text: el.uppercase ? shown.toUpperCase() : shown, font, weight: nearestWeight(font, el.weight), italic: !!el.italic,
    size: Math.max(10, Math.round(el.size * u)), fill: el.color, x: (el.x + el.w / 2) * W, top: el.y * H, width: Math.max(40, el.w * W),
    align: el.align, lineHeight: el.line_height, spacing: Math.round(el.letter_spacing * 1000), shadow: !!el.shadow,
    maxHeight: Math.max(20, el.h * H), fit: true,
  };
}

/** More points than the reference has blocks for: they are spread evenly through the room the points had, from the first point block down to
    the next text block below it (the source line, say) or the foot of the canvas, in the first block's style, the type shrunk if a slot is
    tighter than the block was. Returns the elements to draw and how many points fit. Nothing is ever stacked onto another block. */
function spreadPoints(points, others, count) {
  const first = points[0];
  const below = others.filter((e) => e.y > first.y + 0.001).map((e) => e.y - 0.01);
  const floor = Math.min(0.98, ...below);
  const minSlot = Math.max(0.035, first.h * 0.6);
  const fits = Math.max(points.length, Math.min(count, Math.floor((floor - first.y) / minSlot + 1e-9)));
  const n = Math.min(count, fits);
  const slot = (floor - first.y) / n;
  const shrink = slot < first.h ? Math.max(0.6, slot / first.h) : 1;
  const out = Array.from({ length: n }, (_, i) => ({ ...first, y: first.y + i * slot, h: Math.min(first.h, slot * 0.92), size: first.size * shrink }));
  return { out, fit: n };
}

/**
 * layout + words → seed.
 *   layout   the cleaned layout from the function (design.js cleanLayout)
 *   words    { eyebrow, headline, points: [], source }  (empty ones leave their slot out: no placeholder words are ever drawn)
 *   opts     { width, height, name, pictureUrl, t }  pictureUrl is the picture for the biggest photo area (or the whole background);
 *            t is the page's translator, used for layer names
 * Returns { seed, notes } where notes name what was left out or moved, for the page to show.
 */
export function layoutToSeed(layout, words, { width, height, name, pictureUrl = "", t = (bm, en) => en } = {}) {
  const W = Math.round(width), H = Math.round(height), u = Math.min(W, H);
  const notes = [];
  const layers = [];
  const bg = layout.background || { color: "#ffffff", gradient: null };
  layers.push({ kind: "rect", name: t("Latar", "Background"), role: "bg", x: 0, y: 0, w: W, h: H, fill: bg.color, gradient: bg.gradient, opacity: 1 });

  const photos = (layout.elements || []).filter((e) => e.type === "photo");
  const main = photos.slice().sort((a, b) => area(b) - area(a))[0] || null;
  const fullBleed = (e) => e.w >= 0.9 && e.h >= 0.9;
  if (pictureUrl && (!main || fullBleed(main))) layers.push({ kind: "image", name: t("Gambar", "Picture"), role: "bg", url: pictureUrl, cover: true });

  const slots = slotsOf(layout);
  if (slots.extraHeadlines.length) notes.push(t("{n} blok tajuk tambahan digabungkan ke dalam satu.", "{n} extra headline block(s) were merged into one.", { n: slots.extraHeadlines.length }));
  if (slots.deco.length) notes.push(t("{n} teks kecil hiasan ditinggalkan (tarikh, nombor, label tepi).", "{n} small decorative text(s) were left out (dates, numbers, side labels).", { n: slots.deco.length }));

  const pts = (words.points || []).map((p) => String(p || "").trim()).filter(Boolean);
  const use = new Map();                                    // the element -> the text it now carries
  const made = [];                                          // blocks the reference lacked: drawn after it, never part of its stacking
  if (slots.headline && words.headline?.trim()) use.set(slots.headline, { text: words.headline.trim(), name: slotName("headline", 0, t) });
  else if (!slots.headline && words.headline?.trim()) {       // the reference had no title block: one is made at the top, large and centred
    const el = { type: "text", role: "headline", x: 0.08, y: 0.1, w: 0.84, h: 0.28, size: 0.085, font: "sans", weight: 800, color: "#ffffff", align: "center", italic: false, uppercase: false, letter_spacing: 0, line_height: 1.08, shadow: false };
    slots.headline = el; made.push({ el, text: words.headline.trim(), name: slotName("headline", 0, t) });
    notes.push(t("Rujukan tiada blok tajuk: satu dibuat di atas.", "The reference has no headline block: one was made at the top."));
  }
  if (slots.eyebrow && words.eyebrow?.trim()) use.set(slots.eyebrow, { text: words.eyebrow.trim(), name: slotName("eyebrow", 0, t) });
  else if (slots.eyebrow) notes.push(t("Label kecil ditinggalkan kerana tiada perkataan.", "The small label was left out: no words for it."));
  if (slots.source && words.source?.trim()) use.set(slots.source, { text: words.source.trim(), name: slotName("source", 0, t) });
  else if (slots.source) notes.push(t("Baris sumber ditinggalkan kerana tiada perkataan.", "The source line was left out: no words for it."));
  const extra = [];
  if (pts.length > slots.points.length && slots.points.length) {
    const textBlocks = (layout.elements || []).filter((e) => e.type === "text" && e.role !== "point");
    const { out, fit } = spreadPoints(slots.points, textBlocks, pts.length);
    out.forEach((el, i) => extra.push({ el, text: pts[i], name: slotName("point", i, t) }));
    for (let i = fit; i < pts.length; i++) notes.push(t("Poin {n} tiada ruang dan ditinggalkan.", "Point {n} had no room and was left out.", { n: i + 1 }));
    if (fit > slots.points.length) notes.push(t("Poin disebar sama rata kerana rujukan hanya ada {n} blok.", "The points were spread evenly because the reference has only {n} block(s).", { n: slots.points.length }));
  } else {
    pts.forEach((text, i) => {
      if (slots.points[i]) use.set(slots.points[i], { text, name: slotName("point", i, t) });
      else notes.push(t("Rujukan tiada blok poin: poin {n} ditinggalkan.", "The reference has no point block: point {n} was left out.", { n: i + 1 }));
    });
  }
  if (slots.points.length > pts.length) notes.push(t("{n} blok poin dalam rujukan tiada perkataan dan ditinggalkan.", "{n} point block(s) in the reference had no words and were left out.", { n: slots.points.length - pts.length }));

  // z-order is the layout's own: shapes and text interleave as the reference stacked them
  for (const el of layout.elements || []) {
    if (el.type === "rect" || el.type === "ellipse") {
      if (!el.fill && !el.gradient && !el.stroke) continue;
      layers.push({ kind: "rect", name: el.type === "ellipse" ? t("Bulatan", "Ellipse") : t("Bentuk", "Shape"), ellipse: el.type === "ellipse", x: el.x * W, y: el.y * H,
        w: el.w * W, h: el.h * H, fill: el.fill, gradient: el.gradient, opacity: el.opacity, radius: el.radius * Math.min(el.w * W, el.h * H),
        stroke: el.stroke, strokeW: el.stroke_w * u });
    } else if (el.type === "line") {
      layers.push({ kind: "line", name: t("Garis", "Line"), x1: el.x * W, y1: el.y * H, x2: (el.x + el.w) * W, y2: (el.y + el.h) * H, stroke: el.stroke, strokeW: Math.max(1, el.stroke_w * u), opacity: el.opacity });
    } else if (el.type === "photo") {
      if (pictureUrl && el === main && !fullBleed(el)) layers.push({ kind: "photo", name: t("Gambar", "Picture"), url: pictureUrl, shape: el.shape, x: el.x * W, y: el.y * H, w: el.w * W, h: el.h * H });
      else if (!fullBleed(el)) layers.push({ kind: "photo", name: `${t("Gambar (ganti)", "Picture (replace)")}${el.description ? `: ${el.description}` : ""}`, url: "", shape: el.shape, x: el.x * W, y: el.y * H, w: el.w * W, h: el.h * H });
    } else if (el.type === "text") {
      const u2 = use.get(el);
      if (u2) layers.push(textLayer(el, u2.text, u2.name, W, H, u));
    }
  }
  for (const x of [...made, ...extra]) layers.push(textLayer(x.el, x.text, x.name, W, H, u));
  if (main && !pictureUrl && fullBleed(main)) notes.push(t("Gambar latar rujukan diganti dengan warna dan kecerunan yang serupa: tambah gambar anda sendiri di Kanvas.", "The reference's background photo is replaced by a similar colour and gradient: add your own picture in Kanvas."));
  else if (photos.some((p) => !fullBleed(p)) && !pictureUrl) notes.push(t("Kawasan gambar dibiarkan sebagai ruang kosong untuk anda ganti.", "Picture areas are left as empty boxes for you to replace."));
  return { seed: { width: W, height: H, name: name || t("Reka bentuk daripada rujukan", "Design from a reference"), layers, bgColor: bg.color, source: "design-clone" }, notes };
}
