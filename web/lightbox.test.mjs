import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/* The picture viewer must be drawn into document.body (Wan, 14 Nov 2026: opened from the post editor it sat inside the editor's
   Glass card, clipped, with no way to close it): a backdrop-filter on any ancestor makes that ancestor the containing block of a
   `fixed` child. And its overlay must be dark under every theme (bg-ink is light under the dark ones). */
const src = readFileSync(new URL("./src/components/ImageLightbox.jsx", import.meta.url), "utf8");
assert.match(src, /import \{ createPortal \} from "react-dom"/, "imports createPortal");
assert.match(src, /createPortal\(\s*<div className="fixed inset-0/, "the viewer is returned through a portal");
assert.match(src, /document\.body,\s*\)/, "into document.body");
const classes = src.match(/className="[^"]*"/g).join(" ");
assert.ok(/bg-black\/85/.test(classes), "a dark overlay");
assert.ok(!/\bbg-ink\b|\bbg-bg\b|\btext-bg\b/.test(classes), "no theme-coloured overlay or text (they flip under dark themes)");
assert.match(src, /z-\[70\]/, "above the Modal (z-50) and the drawers");

// every place that mounts it keeps working: they only render <ImageLightbox {...props} />, never wrap it
for (const f of ["PostEditor", "SlidesEditor", "MyDesigns", "LookPicker"]) {
  const s = readFileSync(new URL(`./src/components/${f}.jsx`, import.meta.url), "utf8");
  assert.match(s, /<ImageLightbox \{\.\.\.[\w.]+\} \/>/, `${f} mounts the viewer`);
}
console.log("lightbox: ok");
