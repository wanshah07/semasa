/* The reference picture's own pixels, read in the browser for "rebuild on the reference" (Wan, 1 Oct 2026: "make sure almost 100%
   serupa"). When the reference stays as the background, the old words have to go under a patch the colour of whatever was behind
   them. The reader guesses that colour (`behind`); the picture itself knows it. For each box this samples a thin ring just above and
   just below the box, takes the median of each (lib/designCloneSeed.patchFromRings), and says when the ring is so uneven that the
   box most likely sits on a photograph, where a flat patch will show and Wan should be told. Nothing leaves the browser. */
import { medianRgb, patchFromRings } from "./designCloneSeed.js";

export function loadImageFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("gambar rujukan tidak boleh dibuka / the reference picture could not be opened")); };
    img.src = url;
  });
}

/** The reference's own shape as a canvas size: the shorter side 1080, the longer side to match (capped at 4096, the function's limit;
    a strip taller than that is still rebuilt, slightly squashed, which the preview shows). */
export function sizeLike(naturalWidth, naturalHeight) {
  const w = Math.max(1, Number(naturalWidth) || 1), h = Math.max(1, Number(naturalHeight) || 1);
  return w >= h ? [Math.min(4096, Math.round(1080 * w / h)), 1080] : [1080, Math.min(4096, Math.round(1080 * h / w))];
}

/** How uneven a ring is: the MEDIAN distance of its samples from their median colour. A few pixels of an old glyph or a border caught in
    the ring cannot move it (a standard deviation flagged a flat teal gradient as a photograph for exactly that reason, measured). */
const spread = (samples) => {
  if (samples.length < 4) return 0;
  const m = medianRgb(samples);
  const d = samples.map((s) => Math.hypot(s[0] - m[0], s[1] - m[1], s[2] - m[2])).sort((x, y) => x - y);
  return d[Math.floor(d.length / 2)];
};

/** Pixel samples from a horizontal band of the picture: `y0..y1` rows, inset a tenth of the box from each side, at most ~400 points. */
function band(data, W, H, x0, x1, y0, y1) {
  const out = [];
  const ya = Math.max(0, Math.floor(y0)), yb = Math.min(H - 1, Math.ceil(y1));
  const xa = Math.max(0, Math.floor(x0)), xb = Math.min(W - 1, Math.ceil(x1));
  if (yb < ya || xb < xa) return out;
  const stepX = Math.max(1, Math.floor((xb - xa + 1) / 40)), stepY = Math.max(1, Math.floor((yb - ya + 1) / 5));
  for (let y = ya; y <= yb; y += stepY) for (let x = xa; x <= xb; x += stepX) {
    const i = (y * W + x) * 4;
    if (data[i + 3] < 200) continue;              // transparent: nothing behind to copy
    out.push([data[i], data[i + 1], data[i + 2]]);
  }
  return out;
}

/** Patches for `boxes` (fractions, from lib/designCloneSeed.patchBoxes) read off `file`. Each patch keeps its box and gains
    { fill } or { gradient } and `onPhoto`. A box that cannot be read keeps the reader's `behind` colour, or is left out. */
export async function samplePatches(file, boxes) {
  const img = await loadImageFile(file);
  const k = Math.min(1, 1200 / Math.max(img.naturalWidth, img.naturalHeight));
  const W = Math.max(1, Math.round(img.naturalWidth * k)), H = Math.max(1, Math.round(img.naturalHeight * k));
  const c = document.createElement("canvas");
  c.width = W; c.height = H;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, W, H);
  let data;
  try { data = ctx.getImageData(0, 0, W, H).data; } catch { data = null; }   // a tainted canvas: fall back to the reader's colours
  return boxes.map((b) => {
    const x0 = b.x * W, x1 = (b.x + b.w) * W, y0 = b.y * H, y1 = (b.y + b.h) * H;
    const inset = (x1 - x0) * 0.1, ring = Math.max(2, (y1 - y0) * 0.08);
    const top = data ? band(data, W, H, x0 + inset, x1 - inset, y0 - ring, y0 - 1) : [];
    const bottom = data ? band(data, W, H, x0 + inset, x1 - inset, y1 + 1, y1 + ring) : [];
    const patch = patchFromRings(top, bottom, b.behind);
    if (!patch) return null;
    return { ...b, ...patch, onPhoto: spread([...top, ...bottom]) > 14 };
  });
}

/** A picture (a File/Blob, or a data/object URL) as RGBA pixels no wider than `maxSide`: { data, width, height }, or null when the
    browser will not let it be read (a tainted canvas). Used to MEASURE the reference and the rebuild (lib/designFidelity.js). */
export async function readPixels(source, maxSide = 360) {
  let img;
  if (typeof source === "string") {
    img = await new Promise((resolve, reject) => {
      const el = new Image();
      el.onload = () => resolve(el);
      el.onerror = () => reject(new Error("gambar tidak boleh dibuka / the picture could not be opened"));
      el.src = source;
    });
  } else img = await loadImageFile(source);
  const k = Math.min(1, maxSide / Math.max(img.naturalWidth, img.naturalHeight));
  const width = Math.max(1, Math.round(img.naturalWidth * k)), height = Math.max(1, Math.round(img.naturalHeight * k));
  const c = document.createElement("canvas");
  c.width = width; c.height = height;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(img, 0, 0, width, height);
  try { return { data: ctx.getImageData(0, 0, width, height).data, width, height }; } catch { return null; }
}
