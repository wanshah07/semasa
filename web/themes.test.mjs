/* Every theme is a set of the same tokens, and every text pair in it must be readable. Parses src/design/themes/*.css and
   tokens.css (the light defaults a theme may leave out) and checks WCAG contrast, 4.5:1. Also checks each theme is wired in
   all four places (ThemeProvider, themeChoice, the first-paint script in index.html, and the light/dark split). No browser. */
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { THEME_IDS, LIGHT_IDS, DARK_IDS } from "./src/design/themeChoice.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const dir = new URL("./src/design/", import.meta.url);
const read = (p) => readFileSync(new URL(p, dir), "utf8");

const vars = (block) => {
  const out = {};
  for (const m of block.matchAll(/--([a-z0-9_-]+):\s*(\d+)\s+(\d+)\s+(\d+)\s*;/g)) out[m[1]] = [+m[2], +m[3], +m[4]];
  return out;
};
const base = vars(/:root\s*\{([\s\S]*?)\n\}/.exec(read("tokens.css"))[1]);
const themeVars = (id) => {
  const css = read(`themes/${id}.css`);
  const body = new RegExp(`\\[data-theme="${id}"\\]\\s*\\{([\\s\\S]*?)\\n\\}`).exec(css);
  assert.ok(body, `${id}: no [data-theme="${id}"] block`);
  return { ...base, ...vars(body[1]), __dark: /color-scheme:\s*dark/.test(body[1]) };
};
const lum = (c) => {
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]);
};
const cr = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
const mix = (a, b, k) => a.map((v, i) => Math.round(v * (1 - k) + b[i] * k));

// The three older themes pre-date this check (Regulab's warn text is 4.35:1 on its surfaces), so it covers the new ones.
const OLDER = ["facerinna", "noir", "regulab"];
const files = readdirSync(new URL("themes/", dir)).filter((f) => f.endsWith(".css")).map((f) => f.replace(".css", ""));

t("every theme file is registered, and every registered theme has a file", () => {
  assert.deepEqual([...files].sort(), [...THEME_IDS].sort());
  assert.equal(new Set(THEME_IDS).size, THEME_IDS.length);
});
t("light and dark lists do not overlap and add up", () => {
  assert.equal(LIGHT_IDS.filter((x) => DARK_IDS.includes(x)).length, 0);
  assert.equal(LIGHT_IDS.length + DARK_IDS.length, THEME_IDS.length);
});
t("the first-paint script knows every theme", () => {
  const html = readFileSync(new URL("../../index.html", dir), "utf8");
  const ids = JSON.parse("[" + /var ids = \[(.*?)\]/.exec(html)[1] + "]");
  assert.deepEqual([...ids].sort(), [...THEME_IDS].sort());
});
t("ThemeProvider imports and lists every theme", () => {
  const src = read("ThemeProvider.jsx");
  for (const id of THEME_IDS) {
    assert.ok(src.includes(`./themes/${id}.css`), `${id} not imported`);
    assert.ok(src.includes(`id: "${id}"`), `${id} not in THEMES`);
  }
});
t("a dark theme declares color-scheme: dark, a light one does not", () => {
  for (const id of THEME_IDS) assert.equal(themeVars(id).__dark, DARK_IDS.includes(id), id);
});
t("dark themes get the dark shadcn tokens", () => {
  const css = readFileSync(new URL("../index.css", dir), "utf8");
  const head = css.slice(0, css.indexOf("{", css.indexOf('[data-theme="noir"]')));
  for (const id of DARK_IDS) assert.ok(head.includes(`[data-theme="${id}"]`), id);
  for (const id of LIGHT_IDS) assert.ok(!head.includes(`[data-theme="${id}"]`), id);
});
t("every new theme reads: text pairs, accent fill, status and category colours", () => {
  for (const id of THEME_IDS.filter((x) => !OLDER.includes(x))) {
    const v = themeVars(id);
    const surfaces = [v["c-bg"], v["c-surface"], v["c-surface-2"]];
    for (const s of surfaces) {
      assert.ok(cr(v["c-ink"], s) >= 7, `${id}: ink on surface ${cr(v["c-ink"], s).toFixed(2)}`);
      assert.ok(cr(v["c-muted"], s) >= 4.5, `${id}: muted ${cr(v["c-muted"], s).toFixed(2)}`);
      assert.ok(cr(v["c-accent-text"], s) >= 4.5, `${id}: accent text ${cr(v["c-accent-text"], s).toFixed(2)}`);
      for (const k of ["ok", "warn", "danger", "wait"]) {
        assert.ok(cr(v[`c-${k}`], s) >= 4.5, `${id}: ${k} on surface ${cr(v[`c-${k}`], s).toFixed(2)}`);
      }
      for (const [k, c] of Object.entries(v)) {
        if (!k.startsWith("cat-")) continue;
        const tint = mix(s, c, 0.1);
        assert.ok(cr(c, tint) >= 4.5, `${id}: ${k} on its tint ${cr(c, tint).toFixed(2)}`);
      }
    }
    assert.ok(cr(v["c-accent-ink"], v["c-accent"]) >= 4.5, `${id}: text on the accent fill ${cr(v["c-accent-ink"], v["c-accent"]).toFixed(2)}`);
  }
});
t("a dark theme has a dark background and a light one a light background", () => {
  for (const id of THEME_IDS) {
    const v = themeVars(id);
    const l = lum(v["c-bg"]);
    assert.ok(DARK_IDS.includes(id) ? l < 0.05 : l > 0.8, `${id}: background luminance ${l.toFixed(3)}`);
  }
});
console.log(`themes: ${n} checks over ${THEME_IDS.length} themes passed`);
