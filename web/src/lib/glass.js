/* The glass look for every page (Wan, 11 Nov 2026: "add this for every segment ... add the controls also ... make sure the
   text font, color readable and visible", answered "1": the glass material on every page's cards, one control in the header).
   The settings are the pasted dashboard's own (blur, opacity, saturation, edge light), kept in this browser only.

   Readable by construction: a card is the theme's own surface colour at `opacity` over the theme's own background, never
   over a photograph, and opacity cannot go below MIN_OPACITY. So the colour behind the words stays within a small step of
   the surface the theme's text colours were checked against (web/themes.test.mjs). glass.test.mjs checks that floor against
   every theme. Plain functions, no imports, so Node can test them. */
export const GLASS_KEY = "semasa.glass";
export const MIN_OPACITY = 0.6;
export const DEFAULT_GLASS = { on: true, blur: 18, opacity: 0.74, saturation: 1.2, edge: 0.6, image: "", imgBlur: 0, imgOpacity: 0.6, imgSaturation: 1 };

/* A picture behind the glass (Wan, 11 Nov 2026: "glass look okay if got image background, allow me to add"). `image` is ""
   (the theme's own wash), "ground:<file>" (one of Semasa's own photographs in public/cards/grounds) or "custom" (a picture
   added from this device, kept in this browser under IMAGE_KEY, shrunk first). A photograph can be any colour, so two
   things keep the words readable whatever it is: the page lays the theme's background colour over the picture at
   IMAGE_SCRIM, and a card's opacity cannot go under IMAGE_MIN_OPACITY while a picture is on. glass.test.mjs checks every
   theme against a pure black and a pure white picture, the two worst cases. */
export const IMAGE_KEY = "semasa.glass.image";
export const IMAGE_SCRIM = 0.4;
export const IMAGE_MIN_OPACITY = 0.92;
/* The picture's own controls (Wan, 11 Nov 2026: "for image background make sure can control their blurry/opacity etc"): how
   blurred it is, how much of it shows through the theme's background (imgOpacity: 1 - the scrim; 0.6 is the old fixed 40%
   scrim) and how strong its colour is. The more of the picture shows, the more opaque a card must be to keep its words readable: imageFloor() is
   that floor (92% up to the old 60% picture, about 95.5% with the picture fully shown), and glass.test.mjs checks every
   theme's card against a black and a white picture at every step. */
export const IMAGE_MIN_SHOW = 0.1;
export const IMAGE_MAX_SHOW = 0.85;     // never the bare picture: page headings sit straight on it, outside any card
export const IMAGE_MAX_BLUR = 40;
export const GROUNDS = ["g_makmal01.jpg", "g_makmal02.jpg", "g_dokumen01.jpg", "g_kilang01.jpg", "g_gudang01.jpg", "g_rak01.jpg"];
const validImage = (v) => (v === "custom" || (typeof v === "string" && v.startsWith("ground:") && GROUNDS.includes(v.slice(7))) ? v : "");
export const imageFloor = (show) => Math.min(1, Math.max(IMAGE_MIN_OPACITY, Math.round((1 - 0.048 / Math.max(Number(show) || 0.6, 0.1)) * 1000) / 1000));
export const minOpacity = (glass) => (glass && glass.image ? imageFloor(glass.imgOpacity ?? 0.6) : MIN_OPACITY);
export const PRESETS = {
  clear: { blur: 10, opacity: MIN_OPACITY, saturation: 1.15, edge: 0.8 },
  frosted: { blur: 18, opacity: 0.74, saturation: 1.2, edge: 0.6 },
  solid: { blur: 0, opacity: 1, saturation: 1, edge: 0.3 },
};

const bounded = (v, min, max, fallback) => (Number.isFinite(Number(v)) ? Math.min(max, Math.max(min, Number(v))) : fallback);

export function normalizeGlass(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  const image = validImage(v.image);
  const imgOpacity = bounded(v.imgOpacity, IMAGE_MIN_SHOW, IMAGE_MAX_SHOW, DEFAULT_GLASS.imgOpacity);
  const floor = image ? imageFloor(imgOpacity) : MIN_OPACITY;
  return {
    on: v.on === undefined ? DEFAULT_GLASS.on : v.on === true,
    blur: bounded(v.blur, 0, 40, DEFAULT_GLASS.blur),
    opacity: bounded(v.opacity, floor, 1, Math.max(DEFAULT_GLASS.opacity, floor)),
    saturation: bounded(v.saturation, 0.5, 2, DEFAULT_GLASS.saturation),
    edge: bounded(v.edge, 0, 1, DEFAULT_GLASS.edge),
    image,
    imgBlur: bounded(v.imgBlur, 0, IMAGE_MAX_BLUR, DEFAULT_GLASS.imgBlur),
    imgOpacity,
    imgSaturation: bounded(v.imgSaturation, 0, 2, DEFAULT_GLASS.imgSaturation),
  };
}

export function readGlass(store) {
  try { return normalizeGlass(JSON.parse(store.getItem(GLASS_KEY) || "null")); } catch { return normalizeGlass(null); }
}
export function writeGlass(store, glass) {
  try { store.setItem(GLASS_KEY, JSON.stringify(normalizeGlass(glass))); } catch { /* private window: lasts until the tab closes */ }
}

/** The address of the picture behind the glass, or "" for none. `custom` is the stored data URL; `base` is the site's base path. */
export function imageUrl(glass, custom = "", base = "./") {
  const g = normalizeGlass(glass);
  if (!g.on || !g.image) return "";
  if (g.image === "custom") return /^data:image\/(jpeg|png|webp);base64,/.test(custom || "") ? custom : "";
  return `${base}cards/grounds/${g.image.slice(7)}`;
}

/** The picture's address made absolute against the page. A relative url() inside a CSS variable is resolved against the
    STYLESHEET that uses the variable (assets/index-*.css), not the page, so "./cards/grounds/x.jpg" was fetched from
    /assets/cards/... and no built-in picture ever appeared on the live site (Wan, 11 Nov 2026). A data: address is
    already absolute and comes back unchanged. */
export function absoluteUrl(url, pageUrl) {
  if (!url || url.startsWith("data:")) return url || "";
  try { return new URL(url, pageUrl).href; } catch { return url; }
}

/** Put the settings on the page: `data-glass` on <html> switches the look, the variables carry the numbers. `url` is the
    picture's address from imageUrl(), "" for none. */
export function applyGlass(el, glass, url = "") {
  const g = normalizeGlass(glass);
  el.setAttribute("data-glass", g.on ? "on" : "off");
  if (g.on && url) {
    el.setAttribute("data-glass-image", "on");
    el.style.setProperty("--glass-image", `url("${String(url).replace(/["\\\n]/g, "")}")`);
  } else {
    el.removeAttribute("data-glass-image");
    el.style.removeProperty("--glass-image");
  }
  el.style.setProperty("--glass-blur", `${g.blur}px`);
  el.style.setProperty("--glass-opacity", String(g.opacity));
  el.style.setProperty("--glass-saturation", String(g.saturation));
  el.style.setProperty("--glass-edge", String(g.edge));
  el.style.setProperty("--glass-img-blur", `${g.imgBlur}px`);
  el.style.setProperty("--glass-img-opacity", String(g.imgOpacity));
  el.style.setProperty("--glass-img-saturation", String(g.imgSaturation));
}

/** What a picture pixel becomes when the picture shows at `show` (its opacity) over the theme's background. */
export const scrimmed = (pixel, bg, show = 1 - IMAGE_SCRIM) => pixel.map((c, i) => Math.round(c * show + bg[i] * (1 - show)));

/** The colour actually behind a card's words: surface at `opacity` over the page background. For the contrast test. */
export const cardColour = (surface, bg, opacity) => surface.map((c, i) => Math.round(c * opacity + bg[i] * (1 - opacity)));
