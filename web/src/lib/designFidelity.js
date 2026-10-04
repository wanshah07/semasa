/* "Make sure the design follows the reference" (Wan, 4 Oct 2026: "how to make sure the design follows the layout, background, colour,
   text (editable/replaceable)", with a conference poster as the example).

   The AI reads a reference as a LAYOUT (supabase/functions/semasa-chat/design.js): boxes, roles, fonts, sizes and colours it guessed by
   eye. A guess is good for where things are and poor for exactly which colour, so this file does the two things a guess cannot:

     snapLayout    replaces every colour the reader guessed with the colour MEASURED in the reference's own pixels: the background
                   (flat or a gradient along its own axis), each shape's fill and each text block's ink. A block on a photograph
                   (too uneven to name one colour) keeps the reader's colour and is listed, not silently changed.
     compareImages scores the rebuild against the reference, 0 to 100, on a grid of cells (colour and edge energy), and names the
                   worst cells, so "looks right" is a number the page can show and a refine pass can be held to: a pass that makes
                   the score WORSE is thrown away (the AI refine can regress; measured, never assumed).

   Pure: pixels in ({data: RGBA bytes, width, height}), numbers out. The browser reads them from a canvas (lib/designPatch.js
   readPixels); Node tests it on pictures it draws itself. Nothing here calls the AI or the network. */

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const hex2 = (n) => clamp(Math.round(n), 0, 255).toString(16).padStart(2, "0");
export const toHex = (rgb) => "#" + hex2(rgb[0]) + hex2(rgb[1]) + hex2(rgb[2]);
export const fromHex = (h) => (/^#[0-9a-f]{6}$/i.test(h || "") ? [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) : null);
const dist = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
const median = (xs) => { const v = xs.slice().sort((a, b) => a - b); return v[Math.floor(v.length / 2)]; };
export const medianRgb = (ss) => (ss.length ? [median(ss.map((s) => s[0])), median(ss.map((s) => s[1])), median(ss.map((s) => s[2]))] : null);

const at = (img, x, y) => { const i = (y * img.width + x) * 4; return [img.data[i], img.data[i + 1], img.data[i + 2], img.data[i + 3]]; };

/** Opaque pixel samples inside a box (fractions of the picture), on a grid of at most ~`max` points. */
export function sampleBox(img, b, max = 900) {
  const x0 = clamp(Math.floor(b.x * img.width), 0, img.width - 1), x1 = clamp(Math.ceil((b.x + b.w) * img.width) - 1, x0, img.width - 1);
  const y0 = clamp(Math.floor(b.y * img.height), 0, img.height - 1), y1 = clamp(Math.ceil((b.y + b.h) * img.height) - 1, y0, img.height - 1);
  const n = (x1 - x0 + 1) * (y1 - y0 + 1), step = Math.max(1, Math.round(Math.sqrt(n / max)));
  const out = [];
  for (let y = y0; y <= y1; y += step) for (let x = x0; x <= x1; x += step) { const p = at(img, x, y); if (p[3] >= 200) out.push([p[0], p[1], p[2]]); }
  return out;
}

/** How uneven a set of samples is: the median distance from their median colour (a few glyph pixels cannot move it). */
export function spread(samples) {
  if (samples.length < 6) return 0;
  const m = medianRgb(samples);
  return median(samples.map((s) => dist(s, m)));
}

const POTO = 14;                                   // above this spread a box sits on a photograph: no single colour names it

/** The picture's background, measured on its border ring (the part nothing is usually drawn on). Flat when the ring agrees; otherwise a
    gradient along `angle` (CSS angle: 180 is top to bottom) whose stops are the ring's median colour at each position along that axis. */
export function measureBackground(img, guess = {}) {
  const ring = 0.03, pts = [];
  for (let y = 0; y < img.height; y++) for (let x = 0; x < img.width; x++) {
    const fx = x / img.width, fy = y / img.height;
    if (fx < ring || fx > 1 - ring || fy < ring || fy > 1 - ring) { const p = at(img, x, y); if (p[3] >= 200) pts.push({ fx, fy, c: [p[0], p[1], p[2]] }); }
  }
  if (!pts.length) return null;
  const all = medianRgb(pts.map((p) => p.c));
  if (median(pts.map((p) => dist(p.c, all))) < 5) return { color: toHex(all), gradient: null, measured: true };
  const angle = Number(guess.gradient?.angle ?? 180), a = angle * Math.PI / 180, dx = Math.sin(a), dy = -Math.cos(a);
  const proj = (p) => clamp(0.5 + ((p.fx - 0.5) * dx + (p.fy - 0.5) * dy) / (Math.abs(dx) + Math.abs(dy)), 0, 1);
  const ats = guess.gradient?.stops?.length >= 2 ? guess.gradient.stops.map((s) => s.at) : [0, 1];
  const stops = ats.map((t) => {
    const near = pts.filter((p) => Math.abs(proj(p) - t) <= 0.08);
    const c = medianRgb((near.length >= 6 ? near : pts.slice().sort((p, q) => Math.abs(proj(p) - t) - Math.abs(proj(q) - t)).slice(0, 12)).map((p) => p.c));
    return { at: t, color: toHex(c) };
  });
  return { color: stops[0].color, gradient: { angle, stops }, measured: true };
}

/** A shape's fill: the median colour of the middle of its box; null when the middle is a photograph. */
export function measureFill(img, el) {
  const s = sampleBox(img, { x: el.x + el.w * 0.2, y: el.y + el.h * 0.2, w: el.w * 0.6, h: el.h * 0.6 });
  if (s.length < 6 || spread(s) > POTO) return null;
  return toHex(medianRgb(s));
}

/** A text block's ink colour and the paper behind it. Paper = the commonest colour in a ring just outside the box (or the box's own
    median when the ring is off the picture); ink = the median of the quarter of the box's pixels that differ MOST from the paper,
    taken only when enough pixels differ to be letters (at least 1.5% of the box). Returns { ink, paper, share } or null. */
export function measureInk(img, el) {
  const g = 0.006, ring = [
    ...sampleBox(img, { x: el.x, y: Math.max(0, el.y - 0.012), w: el.w, h: Math.min(0.01, el.y) }, 120),
    ...sampleBox(img, { x: el.x, y: Math.min(1, el.y + el.h + g), w: el.w, h: Math.min(0.01, 1 - el.y - el.h - g) }, 120)];
  const inside = sampleBox(img, el, 1400);
  if (inside.length < 12) return null;
  const paper = medianRgb(ring.length >= 8 ? ring : inside);
  if (spread(ring.length >= 8 ? ring : inside) > POTO) return null;
  const far = inside.map((s) => ({ s, d: dist(s, paper) })).filter((x) => x.d > 70);
  if (far.length < Math.max(6, inside.length * 0.015)) return null;
  far.sort((a, b) => b.d - a.d);
  const core = far.slice(0, Math.max(6, Math.ceil(far.length / 4))).map((x) => x.s);
  return { ink: toHex(medianRgb(core)), paper: toHex(paper), share: far.length / inside.length };
}

/**
 * The layout with its colours replaced by measured ones. `changes` names each one (what, was, now) for the page to show, and `kept`
 * names the blocks left on the reader's guess because they sit on a photograph or have too few letters to read.
 */
export function snapLayout(layout, img) {
  const changes = [], kept = [];
  const note = (what, was, now) => { if (was !== now) changes.push({ what, was: was || "", now }); };
  const out = JSON.parse(JSON.stringify(layout));
  const bg = measureBackground(img, out.background);
  if (bg) {
    note("background", out.background?.gradient ? "gradient" : out.background?.color, bg.gradient ? "gradient" : bg.color);
    out.background = { color: bg.color, gradient: bg.gradient };
  }
  out.elements = (out.elements || []).map((e, i) => {
    if (e.type === "rect" || e.type === "ellipse") {
      if (!e.fill && !e.gradient) return e;
      const c = measureFill(img, e);
      if (!c) { kept.push(`${e.type} ${i + 1}`); return e; }
      note(`${e.type} ${i + 1}`, e.fill || "gradient", c);
      return { ...e, fill: c, gradient: null };
    }
    if (e.type === "text") {
      const m = measureInk(img, e);
      if (!m) { kept.push(`${e.role} text ${i + 1}`); return e; }
      note(`${e.role} text ${i + 1}`, e.color, m.ink);
      return { ...e, color: m.ink, behind: m.paper };
    }
    return e;
  });
  out.palette = [...new Set([out.background.color, ...out.elements.flatMap((e) => [e.fill, e.color, e.stroke]).filter(Boolean)])].slice(0, 8);
  return { layout: out, changes, kept };
}

/* ---- the score -------------------------------------------------------------------------------------------------------------- */

const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
/** sRGB to CIE Lab (D65). */
export function lab(rgb) {
  const r = lin(rgb[0]), g = lin(rgb[1]), b = lin(rgb[2]);
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, y = 0.2126 * r + 0.7152 * g + 0.0722 * b, z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}
const deltaE = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** Cell means (Lab) and edge energy for an N×N grid, each cell the box-average of the pixels it covers. */
function grid(img, N) {
  const cells = Array.from({ length: N * N }, () => ({ n: 0, r: 0, g: 0, b: 0, e: 0 }));
  const lum = (x, y) => { const p = at(img, x, y); return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]; };
  for (let y = 0; y < img.height; y++) for (let x = 0; x < img.width; x++) {
    const c = cells[Math.min(N - 1, Math.floor(y / img.height * N)) * N + Math.min(N - 1, Math.floor(x / img.width * N))];
    const p = at(img, x, y);
    c.n++; c.r += p[0]; c.g += p[1]; c.b += p[2];
    if (x + 1 < img.width && y + 1 < img.height) c.e += Math.abs(lum(x, y) - lum(x + 1, y)) + Math.abs(lum(x, y) - lum(x, y + 1));
  }
  return cells.map((c) => ({ lab: lab([c.r / c.n, c.g / c.n, c.b / c.n]), edge: c.e / c.n }));
}

/**
 * How close `render` is to `ref`: { score 0..100, colour, structure, worst: [{x, y, w, h, delta}] } on an N×N grid (default 24). The
 * two pictures may differ in size (they are compared on the same grid). Colour: per cell ΔE (Lab) against 30, so a tint is cheap and a
 * wrong block is dear. Structure: the edge energy per cell (where lines and letters are), so a block of words in the wrong place or
 * missing costs even when the average colour is close. score = 70% colour + 30% structure. `worst` are the six cells that differ most,
 * as fractions of the picture, for the page to point at.
 */
export function compareImages(ref, render, N = 24) {
  const a = grid(ref, N), b = grid(render, N);
  let col = 0, str = 0;
  const per = a.map((c, i) => {
    const d = deltaE(c.lab, b[i].lab);
    const s = clamp(1 - d / 30, 0, 1);
    const hi = Math.max(c.edge, b[i].edge, 4);
    const st = clamp(1 - Math.abs(c.edge - b[i].edge) / hi, 0, 1);
    col += s; str += st;
    return { i, d, cost: (1 - s) * 0.7 + (1 - st) * 0.3 };
  });
  const colour = col / per.length * 100, structure = str / per.length * 100;
  const worst = per.slice().sort((p, q) => q.cost - p.cost).slice(0, 6).filter((p) => p.cost > 0.15)
    .map((p) => ({ x: (p.i % N) / N, y: Math.floor(p.i / N) / N, w: 1 / N, h: 1 / N, delta: Math.round(p.d * 10) / 10 }));
  return { score: Math.round((0.7 * colour + 0.3 * structure) * 10) / 10, colour: Math.round(colour * 10) / 10, structure: Math.round(structure * 10) / 10, worst };
}

/** The refine loop's decision: keep the new layout only if it scores better than the best so far (by at least `eps`); say when to stop
    (good enough, or no real gain). Pure so the rule is tested, not remembered. */
export function judgePass(best, next, { goal = 90, eps = 0.4, minGain = 1 } = {}) {
  const better = next.score > best.score + eps;
  const keep = better ? next : best;
  const gain = next.score - best.score;
  return { keep, accepted: better, stop: keep.score >= goal || !better || gain < minGain };
}
