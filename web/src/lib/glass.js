/* The glass look for every page (Wan, 11 Nov 2026: "add this for every segment ... add the controls also ... make sure the
   text font, color readable and visible", answered "1": the glass material on every page's cards, one control in the header).
   The settings are the pasted dashboard's own (blur, opacity, saturation, edge light), kept in this browser only.

   Readable by construction: a card is the theme's own surface colour at `opacity` over the theme's own background, never
   over a photograph, and opacity cannot go below MIN_OPACITY. So the colour behind the words stays within a small step of
   the surface the theme's text colours were checked against (web/themes.test.mjs). glass.test.mjs checks that floor against
   every theme. Plain functions, no imports, so Node can test them. */
export const GLASS_KEY = "semasa.glass";
export const MIN_OPACITY = 0.6;
export const DEFAULT_GLASS = { on: true, blur: 18, opacity: 0.74, saturation: 1.2, edge: 0.6 };
export const PRESETS = {
  clear: { blur: 10, opacity: MIN_OPACITY, saturation: 1.15, edge: 0.8 },
  frosted: { blur: 18, opacity: 0.74, saturation: 1.2, edge: 0.6 },
  solid: { blur: 0, opacity: 1, saturation: 1, edge: 0.3 },
};

const bounded = (v, min, max, fallback) => (Number.isFinite(Number(v)) ? Math.min(max, Math.max(min, Number(v))) : fallback);

export function normalizeGlass(raw) {
  const v = raw && typeof raw === "object" ? raw : {};
  return {
    on: v.on === undefined ? DEFAULT_GLASS.on : v.on === true,
    blur: bounded(v.blur, 0, 40, DEFAULT_GLASS.blur),
    opacity: bounded(v.opacity, MIN_OPACITY, 1, DEFAULT_GLASS.opacity),
    saturation: bounded(v.saturation, 0.5, 2, DEFAULT_GLASS.saturation),
    edge: bounded(v.edge, 0, 1, DEFAULT_GLASS.edge),
  };
}

export function readGlass(store) {
  try { return normalizeGlass(JSON.parse(store.getItem(GLASS_KEY) || "null")); } catch { return normalizeGlass(null); }
}
export function writeGlass(store, glass) {
  try { store.setItem(GLASS_KEY, JSON.stringify(normalizeGlass(glass))); } catch { /* private window: lasts until the tab closes */ }
}

/** Put the settings on the page: `data-glass` on <html> switches the look, the variables carry the numbers. */
export function applyGlass(el, glass) {
  const g = normalizeGlass(glass);
  el.setAttribute("data-glass", g.on ? "on" : "off");
  el.style.setProperty("--glass-blur", `${g.blur}px`);
  el.style.setProperty("--glass-opacity", String(g.opacity));
  el.style.setProperty("--glass-saturation", String(g.saturation));
  el.style.setProperty("--glass-edge", String(g.edge));
}

/** The colour actually behind a card's words: surface at `opacity` over the page background. For the contrast test. */
export const cardColour = (surface, bg, opacity) => surface.map((c, i) => Math.round(c * opacity + bg[i] * (1 - opacity)));
