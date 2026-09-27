/* A Wangian design as Kanvas layers (Wan, 26 Sep 2026: "add any repo that the design can similar like canva").
   The worker keeps each render's pieces (the scene without a word, and the real bottle cut out); this lays them out
   the way web/public/cards/fragrance.css draws them, so the editor opens the same design with every piece movable.
   Positions are CENTRES: Fabric.js 7 anchors objects at their centre. Sizes follow the same rule as the CSS: type and
   badges follow the shorter side (u), positions follow the width and height. */

import { tr } from "./i18n";

export const FONTS = {
  "Playfair Display": [700, 800], Anton: [400], Poppins: [600, 700, 800], "Instrument Sans": [400, 500, 600],
  "JetBrains Mono": [400, 500], Caveat: [700],
};

/** { width, height, name, layers: [...] } for the editor to build; layers are plain descriptions, not Fabric objects. */
export function fragranceSeed(render, meta, product) {
  const c = meta.rendered || meta.concepts?.[meta.rendered_pick ?? meta.pick ?? 0] || {};
  const [w, h] = meta.size?.length === 2 ? meta.size : meta.format === "portrait" ? [1080, 1350] : [1080, 1080];
  const u = Math.min(w, h);
  const ink = c.ink || "#fffaf0";
  const accent = c.accent || "#f3e6c4";
  const layout = c.layout || "hero";
  const side = layout === "hero" ? (c.side || "left") : "center";
  const layers = [];
  const L = render.layers || {};
  if (L.scene?.url) layers.push({ kind: "image", role: "bg", url: L.scene.url, cover: true, name: tr("Latar (babak AI)", "Background (AI scene)") });
  else layers.push({ kind: "image", role: "bg", url: render.url, cover: true, name: tr("Latar", "Background") });
  if (product?.logo_url) {
    layers.push({ kind: "image", url: product.logo_url, name: "Logo", x: w / 2, top: h * 0.035, height: h * 0.075 });
  } else {
    layers.push({ kind: "text", name: tr("Jenama", "Brand"), text: product?.brand || "Valorith", font: "Playfair Display", weight: 700,
      italic: true, size: u * 0.062, fill: ink, x: w / 2, top: h * 0.03, width: w * 0.8, align: "center", shadow: true });
  }
  if (L.bottle?.url) {
    const glossy = c.surface === "glossy";
    const bh = h * ((layout === "behind" ? 0.70 : 0.64) - (glossy ? 0.1 : 0));
    const bottom = h * (glossy ? 0.17 : 0.06);
    layers.push({ kind: "image", role: "bottle", url: L.bottle.url, name: tr("Botol (gambar sebenar)", "Bottle (real photo)"), height: bh,
      bottomY: h - bottom, side, xLeft: w * 0.10, xRight: w - w * 0.10, x: w / 2, shadow: true });
  }
  if (layout === "hero") {
    const onLeft = side === "right";
    const cx = onLeft ? w * 0.04 + w * 0.25 : w - w * 0.04 - w * 0.25;
    layers.push({ kind: "text", name: tr("Tajuk", "Headline"), text: (c.headline || product?.name || "").split(/\s+/).join("\n"),
      font: "Playfair Display", weight: 800, size: u * 0.16, lineHeight: 0.95, fill: ink, x: cx, top: h * 0.20,
      width: w * 0.5, align: "center", shadow: true, fit: true });
    if (c.tagline) {
      layers.push({ kind: "text", name: tr("Slogan", "Tagline"), text: c.tagline, font: "Poppins", weight: 700, size: u * 0.034,
        spacing: 320, fill: ink, x: cx, below: "Tajuk", gap: h * 0.018, width: w * 0.5, align: "center", shadow: true });
    }
  } else if (layout === "behind") {
    layers.push({ kind: "text", name: tr("Tajuk", "Headline"), text: (c.headline || "").toUpperCase(), font: "Anton", weight: 400,
      size: u * 0.20, lineHeight: 0.92, fill: ink, x: w / 2, top: h * 0.135, width: w * 0.92, align: "center",
      fit: true, under: "Botol (gambar sebenar)" });
  } else {
    const spots = [[w * 0.04, h * 0.50, "left"], [w * 0.96, h * 0.40, "right"], [w * 0.96, h * 0.68, "right"]];
    (c.callouts || []).slice(0, 3).forEach((k, i) => {
      const [x, y, align] = spots[i];
      const cw = w * 0.30;
      layers.push({ kind: "text", name: tr("Nota {n}", "Note {n}", { n: i + 1 }), text: `${(k.title || "").toUpperCase()}\n${(k.line || "").toUpperCase()}`,
        font: "Poppins", weight: 800, size: u * 0.036, lineHeight: 1.15, fill: ink, x: align === "left" ? x + cw / 2 : x - cw / 2,
        top: y, width: cw, align, shadow: true });
    });
  }
  const badges = c.badges || [];
  if (badges.length) {
    const wrap = layout !== "hero";
    const d = u * (wrap ? 0.12 : 0.15);
    const gap = u * 0.012;
    const atLeft = layout === "hero" ? side === "right" : layout === "notes";
    const perRow = wrap ? 2 : 3;
    badges.forEach((b, i) => {
      const row = Math.floor(i / perRow);
      const col = i % perRow;
      const inRow = Math.min(perRow, badges.length - row * perRow);
      const edge = w * 0.035;
      const x = atLeft ? edge + d / 2 + col * (d + gap) : w - edge - d / 2 - (inRow - 1 - col) * (d + gap);
      const rowsTotal = Math.ceil(badges.length / perRow);
      const y = h - h * 0.07 - d / 2 - (rowsTotal - 1 - row) * (d + gap);
      layers.push({ kind: "badge", name: tr("Lencana {n}", "Badge {n}", { n: i + 1 }), text: b, x, y, d });
    });
    if (badges.some((b) => b.includes("*")) && product?.footnote) {
      layers.push({ kind: "text", name: tr("Nota kaki", "Footnote"), text: product.footnote.toUpperCase(), font: "Poppins", weight: 700,
        size: u * 0.0135, spacing: 220, fill: ink, x: atLeft ? w * 0.035 + w * 0.2 : w - w * 0.035 - w * 0.2,
        top: h - h * 0.022 - u * 0.02, width: w * 0.4, align: atLeft ? "left" : "right" });
    }
  }
  return { width: w, height: h, name: `${product?.name || tr("Wangian", "Fragrance")} · ${c.title || tr("reka bentuk", "design")}`, layers, accent };
}
