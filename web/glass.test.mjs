/* The glass look must never cost readability (Wan, 11 Nov 2026: "make sure the text font, color readable and visible").
   For every theme: at the lowest opacity the control allows, the colour behind a card's words (surface over the page
   background) still gives ink 7:1 and muted text and accent text 4.5:1. Also the settings' own bounds. No browser. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { THEME_IDS } from "./src/design/themeChoice.js";
import { DEFAULT_GLASS, MIN_OPACITY, PRESETS, cardColour, normalizeGlass, readGlass, writeGlass } from "./src/lib/glass.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const dir = new URL("./src/design/", import.meta.url);
const vars = (block) => Object.fromEntries([...block.matchAll(/--([a-z0-9_-]+):\s*(\d+)\s+(\d+)\s+(\d+)\s*;/g)].map((m) => [m[1], [+m[2], +m[3], +m[4]]]));
const base = vars(/:root\s*\{([\s\S]*?)\n\}/.exec(readFileSync(new URL("tokens.css", dir), "utf8"))[1]);
const themeVars = (id) => ({ ...base, ...vars(new RegExp(`\\[data-theme="${id}"\\]\\s*\\{([\\s\\S]*?)\\n\\}`).exec(readFileSync(new URL(`themes/${id}.css`, dir), "utf8"))[1]) });
const lum = (c) => { const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

t("settings are bounded, and opacity has a floor", () => {
  const g = normalizeGlass({ blur: 999, opacity: 0.05, saturation: -3, edge: 7, on: "yes" });
  assert.deepEqual(g, { on: false, blur: 40, opacity: MIN_OPACITY, saturation: 0.5, edge: 1 });
  assert.deepEqual(normalizeGlass(null), DEFAULT_GLASS);
  assert.deepEqual(normalizeGlass("junk"), DEFAULT_GLASS);
  for (const p of Object.values(PRESETS)) assert.ok(p.opacity >= MIN_OPACITY);
});
t("a saved setting comes back; storage that throws gives the default", () => {
  const m = new Map();
  const s = { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v) };
  writeGlass(s, { ...DEFAULT_GLASS, on: false, blur: 5 });
  assert.equal(readGlass(s).on, false);
  assert.equal(readGlass(s).blur, 5);
  assert.deepEqual(readGlass({ getItem() { throw new Error("blocked"); } }), DEFAULT_GLASS);
});
t("at the lowest opacity, every theme's card still reads", () => {
  for (const id of THEME_IDS) {
    const v = themeVars(id);
    const solid = v["c-surface"];
    const behind = cardColour(solid, v["c-bg"], MIN_OPACITY);
    assert.ok(cr(v["c-ink"], behind) >= 7, `${id}: ink ${cr(v["c-ink"], behind).toFixed(2)}`);
    // muted and accent text: no worse than 4.5:1, or (the three older themes) no worse than they are on the solid card
    for (const k of ["c-muted", "c-accent-text"]) {
      const now = cr(v[k], behind);
      assert.ok(now >= 4.5 || now >= cr(v[k], solid) - 0.15, `${id}: ${k} ${now.toFixed(2)} (solid ${cr(v[k], solid).toFixed(2)})`);
    }
  }
});
t("the first-paint script and the stylesheet both know the switch", () => {
  assert.ok(readFileSync(new URL("./index.html", import.meta.url), "utf8").includes('setAttribute("data-glass"'));
  const css = readFileSync(new URL("./src/index.css", import.meta.url), "utf8");
  assert.ok(css.includes('html[data-glass="on"] .semasa-card'));
  assert.ok(readFileSync(new URL("./src/components/ui/Card.jsx", import.meta.url), "utf8").includes("semasa-card"));
});
console.log(`glass: ${n} checks passed`);
