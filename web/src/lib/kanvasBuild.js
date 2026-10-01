/* Kanvas's builders (moved out of pages/CanvasTab.jsx on 1 Oct 2026 so the Design tab can draw a PREVIEW of a rebuilt design and send it
   to the refine pass without opening the editor): the fonts, the seed → Fabric objects step, and a static render of a seed to a JPEG.
   Fabric.js 7 anchors every object at its CENTRE. */
import { Circle, Ellipse, FabricImage, Gradient, Group, Line, Rect, Shadow, StaticCanvas, Textbox } from "fabric";
import { FONTS } from "./fonts";
import { gradientCoords } from "./designCloneSeed";
import { uploadReference } from "./storage";

export const TEXT_SHADOW = () => new Shadow({ color: "rgba(0,0,0,0.35)", blur: 14, offsetX: 0, offsetY: 3 });
const fontsHref = (f) => `${import.meta.env.BASE_URL}cards/${f}`;

// document.fonts.load() asked before a stylesheet is parsed finds no @font-face and answers at once with nothing, so the
// first opening laid text out in the fallback font (measured: 0 faces). Wait for each stylesheet first, then the faces.
export function loadFonts() {
  const sheets = ["fonts.css", "fragrance-fonts.css"].map((f) => {
    let l = document.querySelector(`link[data-kanvas="${f}"]`);
    if (l?.dataset.loaded) return Promise.resolve();
    const done = new Promise((res) => {
      if (!l) {
        l = document.createElement("link");
        l.rel = "stylesheet"; l.href = fontsHref(f); l.dataset.kanvas = f;
        document.head.appendChild(l);
      }
      l.addEventListener("load", () => { l.dataset.loaded = "1"; res(); }, { once: true });
      l.addEventListener("error", () => res(), { once: true });
      setTimeout(res, 8000);                 // never hang the editor on a slow sheet
    });
    return done;
  });
  const wanted = Object.entries(FONTS).flatMap(([fam, ws]) => ws.map((w) => `${w} 40px "${fam}"`));
  return Promise.all(sheets).then(() => Promise.all(wanted.map((f) => document.fonts.load(f).catch(() => null))));
}

export const nearestWeight = (family, want) => {
  const ws = FONTS[family] || [400];
  return ws.reduce((a, b) => (Math.abs(b - want) < Math.abs(a - want) ? b : a), ws[0]);
};

export function coverImage(img, w, h) {
  const k = Math.max(w / img.width, h / img.height);
  img.set({ left: w / 2, top: h / 2, scaleX: k, scaleY: k, angle: 0 });
  img.setCoords();
}

/** A gradient from a layout's {angle, stops}, in the object's own pixels. */
function gradientOf(g, w, h) {
  return new Gradient({ type: "linear", gradientUnits: "pixels", coords: gradientCoords(g.angle, w, h),
    colorStops: g.stops.map((s) => ({ offset: s.at, color: s.color })) });
}

/** A rectangle or ellipse from a design-clone layer: a top-left box in pixels, solid or gradient fill, opacity, rounded corners. */
function shapeLayer(L) {
  const common = { left: L.x + L.w / 2, top: L.y + L.h / 2, opacity: L.opacity ?? 1,
    fill: L.gradient ? gradientOf(L.gradient, L.w, L.h) : L.fill || "rgba(0,0,0,0)",
    stroke: L.stroke || undefined, strokeWidth: L.stroke ? Math.max(1, L.strokeW || 1) : 0 };
  if (L.ellipse) return new Ellipse({ ...common, rx: L.w / 2, ry: L.h / 2 });
  return new Rect({ ...common, width: L.w, height: L.h, rx: L.radius || 0, ry: L.radius || 0 });
}

/** A picture area from a design-clone layer: the picture covers the box and is clipped to its shape; with no picture, a dashed empty box. */
async function photoLayer(L, user, own) {
  const cx = L.x + L.w / 2, cy = L.y + L.h / 2;
  const clip = () => (L.shape === "ellipse" ? new Ellipse({ left: cx, top: cy, rx: L.w / 2, ry: L.h / 2, absolutePositioned: true })
    : new Rect({ left: cx, top: cy, width: L.w, height: L.h, rx: L.shape === "rounded" ? Math.min(L.w, L.h) * 0.08 : 0, ry: L.shape === "rounded" ? Math.min(L.w, L.h) * 0.08 : 0, absolutePositioned: true }));
  if (!L.url) {
    const box = L.shape === "ellipse" ? new Ellipse({ left: cx, top: cy, rx: L.w / 2, ry: L.h / 2 }) : new Rect({ left: cx, top: cy, width: L.w, height: L.h, rx: L.shape === "rounded" ? Math.min(L.w, L.h) * 0.08 : 0 });
    box.set({ fill: "rgba(128,128,128,0.28)", stroke: "rgba(255,255,255,0.7)", strokeWidth: 3, strokeDashArray: [14, 10] });
    return box;
  }
  void user; void own;
  const img = await FabricImage.fromURL(L.url, { crossOrigin: "anonymous" });
  const k = Math.max(L.w / img.width, L.h / img.height);
  img.set({ left: cx, top: cy, scaleX: k, scaleY: k });
  img.clipPath = clip();
  return img;
}

export function makeBadge(text, x, y, d) {
  const disc = new Circle({ left: x, top: y, radius: d / 2,
    fill: new Gradient({ type: "radial", gradientUnits: "percentage",
      coords: { x1: 0.35, y1: 0.3, r1: 0, x2: 0.35, y2: 0.3, r2: 0.8 },
      colorStops: [{ offset: 0, color: "#fbf1d0" }, { offset: 0.45, color: "#e3c888" }, { offset: 1, color: "#b8914a" }] }),
    shadow: new Shadow({ color: "rgba(0,0,0,0.28)", blur: d * 0.12, offsetY: d * 0.04 }) });
  const words = new Textbox(text, { left: x, top: y, width: d * 0.76, fontFamily: "Poppins", fontWeight: 800, fontSize: d * 0.14,
    lineHeight: 1.1, fill: "#2b2113", textAlign: "center" });
  return new Group([disc, words], { left: x, top: y });
}

export function tainted(err, t) {
  return /taint|SecurityError|insecure/i.test(String(err?.name || err?.message || err))
    ? t("Satu gambar datang dari laman lain yang tidak membenarkan eksport; buang gambar itu dan muat naik salinannya sendiri.",
      "A picture comes from a site that does not allow export; remove it and upload your own copy.")
    : (err?.message || String(err));
}

// A Wangian design (lib/canvasSeed.js) as Fabric objects. Its pictures are copied into the uploads bucket first:
// the worker's own files are deleted with the design job (7 days unsaved, or the version not kept), and a Kanvas
// design must not lose its background the week after.
export async function buildSeed(fc, seed, user, own, { copy = true } = {}) {
  fc.backgroundColor = seed.bgColor || "#111111";
  const byName = {};
  const missed = [];
  for (const L of seed.layers) {
    let obj = null;
    // one picture that will not open (a logo replaced since the design was made) is left out and named; it used to
    // throw out of the loop, so the bottle, the headline and the badges never appeared either
    try {
    if (L.kind === "image") {
      let url = L.url;
      if (copy) try {
        const res = await fetch(url, { mode: "cors" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);   // a 404 page is not a picture: never copy it
        const blob = await res.blob();
        const ext = blob.type === "image/png" ? "png" : "jpg";
        const up = await uploadReference(user, new File([blob], `kanvas-${L.role || "gambar"}.${ext}`, { type: blob.type || "image/jpeg" }));
        own(up.path);
        url = up.url;
      } catch { /* keep the worker's address: it still opens, and saving warns nothing extra */ }
      obj = await FabricImage.fromURL(url, { crossOrigin: "anonymous" });
      if (L.cover) coverImage(obj, seed.width, seed.height);
      else {
        const k = L.height / obj.height;
        const wd = obj.width * k;
        const x = L.side === "left" ? L.xLeft + wd / 2 : L.side === "right" ? L.xRight - wd / 2 : L.x;
        const y = L.bottomY != null ? L.bottomY - L.height / 2 : L.top + L.height / 2;
        obj.set({ left: x, top: y, scaleX: k, scaleY: k });
        if (L.shadow) obj.shadow = new Shadow({ color: "rgba(0,0,0,0.3)", blur: 24, offsetY: 18 });
      }
      obj.role = L.role;
    } else if (L.kind === "text") {
      obj = new Textbox(L.text, { left: L.x, top: 0, width: L.width, fontFamily: L.font, fontWeight: L.weight,
        fontStyle: L.italic ? "italic" : "normal", fontSize: L.size, lineHeight: L.lineHeight || 1.16, charSpacing: L.spacing || 0,
        fill: L.fill, textAlign: L.align || "center" });
      if (L.shadow) obj.shadow = TEXT_SHADOW();
      if (L.fit) {                       // like the CSS: the big line shrinks until it fits its box, never cut
        // a Textbox widens itself to its longest word (dynamicMinWidth): shrink until that word fits the box
        while (obj.width > L.width + 1 && obj.fontSize > 12) { obj.set({ fontSize: obj.fontSize * 0.94, width: L.width }); obj.initDimensions(); }
      }
      // a block of new words may be longer than the reference's: shrink until it fits the box it had, never cut a word
      if (L.maxHeight) while (obj.height > L.maxHeight && obj.fontSize > 12) { obj.set({ fontSize: obj.fontSize * 0.94 }); obj.initDimensions(); }
      const prev = L.below ? byName[L.below] : null;
      const topEdge = prev ? prev.top + prev.height / 2 + (L.gap || 0) : L.top;
      obj.set({ top: topEdge + obj.height / 2 });
    } else if (L.kind === "badge") {
      obj = makeBadge(L.text, L.x, L.y, L.d);
    } else if (L.kind === "rect") {
      obj = shapeLayer(L);
    } else if (L.kind === "line") {
      obj = new Line([L.x1, L.y1, L.x2, L.y2], { stroke: L.stroke, strokeWidth: L.strokeW, opacity: L.opacity ?? 1, strokeLineCap: "round" });
    } else if (L.kind === "photo") {
      obj = await photoLayer(L, user, own);
    }
    } catch {
      missed.push(L.name || L.role || "?");
      continue;
    }
    if (!obj) continue;
    obj.name = L.name;
    byName[L.name] = obj;
    fc.add(obj);
    if (L.under && byName[L.under]) fc.moveObjectTo(obj, fc.getObjects().indexOf(byName[L.under]));
  }
  fc.requestRenderAll();
  return missed;
}


/** A seed drawn off screen, as a JPEG data URL no wider than `maxSide` (the Design tab's preview and the refine pass's second picture).
    Pictures are used from their own addresses, never copied into the uploads bucket, and the canvas is thrown away afterwards. */
export async function renderSeedPreview(seed, { maxSide = 1000, quality = 0.85 } = {}) {
  await loadFonts();
  const fc = new StaticCanvas(undefined, { width: seed.width, height: seed.height, backgroundColor: seed.bgColor || "#ffffff" });
  try {
    const missed = await buildSeed(fc, seed, null, () => {}, { copy: false });
    fc.renderAll();
    const k = Math.min(1, maxSide / Math.max(seed.width, seed.height));
    return { dataUrl: fc.toDataURL({ format: "jpeg", quality, multiplier: k }), missed };
  } finally {
    fc.dispose();
  }
}
