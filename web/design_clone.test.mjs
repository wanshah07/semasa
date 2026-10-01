/* "Rebuild this design" (Wan, 1 Oct 2026): the reader's contract (supabase/functions/semasa-chat/design.js) and the layout → Kanvas layers
   step (src/lib/designCloneSeed.js), in Node. The AI call itself and Fabric's drawing are checked elsewhere (a stubbed run in Chromium). */
import assert from "node:assert/strict";
import { DESIGN_LIMITS, cleanLayout, designMessages, designSystem } from "../supabase/functions/semasa-chat/design.js";
import { firstJson } from "../supabase/functions/semasa-chat/faq.js";
import { fontFor, gradientCoords, layoutToSeed, nearestWeight, slotsOf, stripEmph, wordsFromLayout } from "./src/lib/designCloneSeed.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const PNG = "data:image/png;base64,iVBORw0KGgo=";
const text = (o) => ({ type: "text", role: "headline", x: 0.08, y: 0.1, w: 0.84, h: 0.2, text: "", font: "serif", weight: 800, size: 0.09, color: "#ffffff", align: "left", ...o });

// ---- the reader's contract -----------------------------------------------------------------------------------------
t("the request carries the target size, the picture, and the brief only when there is one", () => {
  const r = designMessages({ image: PNG, width: 1080, height: 1350, stream: "regulab", brief: "  logo halal  " });
  assert.equal(r.hasBrief, true);
  const parts = r.messages[1].content;
  assert.ok(/1080 x 1350/.test(parts[0].text) && /logo halal/.test(parts[0].text));
  assert.equal(parts[1].type, "image_url");
  assert.ok(/NEW WORDS/.test(r.messages[0].content) && /No call to action/.test(r.messages[0].content));
  const own = designMessages({ image: PNG, width: 1080, height: 1080, stream: "linkedin", brief: "" });
  assert.equal(own.hasBrief, false);
  assert.ok(!/NEW WORDS/.test(own.messages[0].content) && /will be supplied by the person/.test(own.messages[0].content));
});

t("the rules that matter are in the prompt: never carry over logos, brand names, URLs, CTAs or faces; picture text is not an instruction", () => {
  const s = designSystem("regulab", true);
  for (const needle of [/NEVER carry these over/, /logo or brand mark/, /call to action/, /website\s+or URL/, /face/, /NEVER instructions/, /Bahasa Indonesia/]) assert.match(s, needle);
  assert.match(designSystem("linkedin", true), /No company identity/);
});

t("a reference that is not a picture, is too large, or a target that is not a sane size is refused before any AI call", () => {
  assert.match(designMessages({ image: "http://x/a.png", width: 1080, height: 1080 }).error, /PNG, JPEG or WEBP/);
  assert.match(designMessages({ image: "data:image/svg+xml;base64,AAAA", width: 1080, height: 1080 }).error, /PNG, JPEG or WEBP/);
  assert.match(designMessages({ image: `data:image/png;base64,${"A".repeat(4_600_000)}`, width: 1080, height: 1080 }).error, /too large/);
  assert.match(designMessages({ image: PNG, width: 50, height: 1080 }).error, /size/);
  assert.match(designMessages({ image: PNG, width: 1080, height: 99999 }).error, /size/);
});

t("a layout is held to the rules: kinds, ranges, colours, and nothing from the reference's brand survives", () => {
  const r = cleanLayout({
    background: { color: "#0A3D3A", gradient: { angle: 200, stops: [{ at: 1, color: "#001010" }, { at: 0, color: "#0a3d3a" }, { at: 0.5, color: "red" }] } },
    removed: ["a watermark"],
    elements: [
      { type: "rect", x: -3, y: 0.5, w: 9, h: 0.9, fill: "#112233", opacity: 7, radius: 3 },
      { type: "logo", x: 0.8, y: 0.02, w: 0.15, h: 0.08 },
      { type: "person", x: 0.4, y: 0.2, w: 0.3, h: 0.5 },
      { type: "script", x: 0, y: 0 },                                        // unknown kind: dropped
      text({ text: "Headline here", font: "comic", weight: 5000, size: 9, color: "javascript:alert(1)", align: "sideways" }),
      text({ role: "deco", text: "www.brand.com", x: 0.1, y: 0.95 }),        // a URL in a decorative text: dropped
      text({ role: "deco", text: "@brand_official", x: 0.5, y: 0.95 }),      // a handle: dropped
      text({ role: "point", text: "Order at brand.my now", x: 0.1, y: 0.5 }), // a URL inside a real block: the words go, the slot stays
      { type: "photo", x: 0.1, y: 0.1, w: 0.5, h: 0.5, shape: "star", description: "a bottle" },
    ],
  });
  assert.ok(r.layout, r.error);
  const els = r.layout.elements;
  assert.equal(els.some((e) => e.type === "logo" || e.type === "person" || e.type === "script"), false);
  assert.equal(els.filter((e) => e.type === "text").length, 2, "the two decorative URL/handle texts are gone");
  const rect = els.find((e) => e.type === "rect");
  assert.deepEqual([rect.x, rect.w, rect.opacity, rect.radius], [0, 1, 1, 0.5]);
  assert.ok(rect.y + rect.h <= 1 + 1e-9);
  const head = els.find((e) => e.role === "headline");
  assert.deepEqual([head.font, head.weight, head.size, head.color, head.align], ["sans", 900, 0.4, "#111111", "left"]);
  const pt = els.find((e) => e.role === "point");
  assert.equal(pt.text, "", "a URL inside a block is not carried");
  assert.equal(els.find((e) => e.type === "photo").shape, "rect");
  assert.deepEqual(r.layout.background.gradient.stops.map((s) => s.at), [0, 1], "an unreadable colour stop is dropped and stops are ordered");
  assert.equal(r.layout.background.color, "#0a3d3a");
  assert.ok(r.removed.includes("a watermark") && r.removed.includes("a logo or brand mark") && r.removed.includes("a person's face"));
  assert.ok(r.removed.some((x) => /web address/.test(x)));
});

t("a reply with no text blocks, or no layout at all, is an error the page can show", () => {
  assert.match(cleanLayout({ elements: [{ type: "rect", x: 0, y: 0, w: 1, h: 1, fill: "#fff" }] }).error, /no text/);
  assert.match(cleanLayout(null).error, /layout/);
  assert.match(cleanLayout({ elements: "none" }).error, /layout/);
  assert.match(cleanLayout(firstJson("sorry, I cannot")).error, /layout/);
});

t("a layout is capped at the element limit and text at its length", () => {
  const many = Array.from({ length: 80 }, (_, i) => text({ role: "point", text: `Poin ${i}`, y: i / 100 }));
  assert.equal(cleanLayout({ elements: many }).layout.elements.length, DESIGN_LIMITS.elements);
  const long = cleanLayout({ elements: [text({ text: "x".repeat(2000) })] }).layout.elements[0];
  assert.equal(long.text.length, DESIGN_LIMITS.text);
});

// ---- layout → Kanvas layers -----------------------------------------------------------------------------------------
const LAYOUT = cleanLayout({
  background: { color: "#0a3d3a", gradient: { angle: 180, stops: [{ at: 0, color: "#0a3d3a" }, { at: 1, color: "#021a19" }] } },
  elements: [
    { type: "photo", x: 0, y: 0, w: 1, h: 1, description: "a dark corridor" },
    { type: "rect", x: 0, y: 0.55, w: 1, h: 0.45, gradient: { angle: 180, stops: [{ at: 0, color: "#000000" }, { at: 1, color: "#000000" }] }, opacity: 0.6 },
    text({ role: "eyebrow", x: 0.08, y: 0.06, w: 0.5, h: 0.04, text: "LABEL", font: "sans", weight: 600, size: 0.025, uppercase: true, letter_spacing: 0.2 }),
    text({ role: "headline", x: 0.08, y: 0.5, w: 0.84, h: 0.2, text: "Headline", size: 0.1 }),
    text({ role: "point", x: 0.08, y: 0.74, w: 0.84, h: 0.06, text: "one", font: "sans", weight: 500, size: 0.032, color: "#e5e5e5" }),
    text({ role: "point", x: 0.08, y: 0.82, w: 0.84, h: 0.06, text: "two", font: "sans", weight: 500, size: 0.032, color: "#e5e5e5" }),
    text({ role: "source", x: 0.08, y: 0.94, w: 0.5, h: 0.03, text: "src", font: "mono", weight: 400, size: 0.02 }),
    text({ role: "deco", x: 0.8, y: 0.06, w: 0.15, h: 0.03, text: "01/10" }),
    { type: "ellipse", x: 0.85, y: 0.85, w: 0.08, h: 0.08, fill: "#e8c872" },
    { type: "line", x: 0.08, y: 0.72, w: 0.84, h: 0, stroke: "#ffffff", stroke_w: 0.002 },
  ],
}).layout;
const WORDS = { eyebrow: "Halal Malaysia", headline: "Logo halal *tidak* boleh dicetak sebarangan", points: ["Ikut spesifikasi semasa.", "Warna boleh berbeza.", "Rujuk MPPHM."], source: "MPPHM (Domestik) 2020" };
const keys = (seed) => seed.layers.map((l) => `${l.kind}:${l.name}`);

t("slots: the headline is the largest title block, points are read top to bottom, small decorative text is set aside", () => {
  const s = slotsOf(LAYOUT);
  assert.equal(s.headline.text, "Headline");
  assert.deepEqual(s.points.map((p) => p.text), ["one", "two"]);
  assert.equal(s.eyebrow.text, "LABEL");
  assert.equal(s.deco.length, 1);
  assert.deepEqual(wordsFromLayout(LAYOUT), { eyebrow: "LABEL", headline: "Headline", points: ["one", "two"], source: "src" });
});

t("new words go into the reference's own blocks, in its own style, at its own place; emphasis marks are not printed", () => {
  const { seed } = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1350 });
  const head = seed.layers.find((l) => l.kind === "text" && l.name === "Headline");
  assert.equal(head.text, "Logo halal tidak boleh dicetak sebarangan");
  assert.equal(head.font, "Playfair Display");
  assert.equal(head.weight, 800);
  assert.equal(head.size, Math.round(0.1 * 1080));
  assert.equal(head.top, 0.5 * 1350);
  assert.equal(head.x, (0.08 + 0.42) * 1080, "x is the centre of the box");
  assert.equal(head.width, 0.84 * 1080);
  assert.equal(head.maxHeight, 0.2 * 1350);
  const eyebrow = seed.layers.find((l) => l.name === "Label");
  assert.equal(eyebrow.text, "HALAL MALAYSIA", "the reference's capitals are kept");
  assert.equal(eyebrow.spacing, 200);
  const pts = seed.layers.filter((l) => /^Point/.test(l.name));
  assert.equal(pts.length, 3);
  assert.ok(pts[2].top > pts[1].top && pts[2].top > pts[0].top, "the extra point is stacked below the last block");
  assert.equal(pts[0].font, "Instrument Sans", "a regular-weight sans is Instrument Sans");
});

t("extra points are spread through the room the points had and never land on the source line below them", () => {
  const { seed, notes } = layoutToSeed(LAYOUT, { ...WORDS, points: ["a", "b", "c", "d", "e"] }, { width: 1080, height: 1350 });
  const pts = seed.layers.filter((l) => /^Point/.test(l.name)).sort((p, q) => p.top - q.top);
  const src = seed.layers.find((l) => l.name === "Source");
  assert.ok(pts.length >= 3);
  for (let i = 1; i < pts.length; i++) assert.ok(pts[i - 1].top + pts[i - 1].maxHeight <= pts[i].top + 1e-6, "points do not overlap each other");
  for (const p of pts) assert.ok(p.top + p.maxHeight <= src.top, "a point stops above the source line");
  assert.ok(pts.length === 5 ? notes.some((x) => /spread evenly/.test(x)) : notes.some((x) => /no room/.test(x)));
  const first = layoutToSeed(LAYOUT, { ...WORDS, points: ["a", "b"] }, { width: 1080, height: 1350 }).seed.layers.filter((l) => /^Point/.test(l.name));
  assert.deepEqual(first.map((l) => l.top), [0.74 * 1350, 0.82 * 1350], "as many points as blocks: the reference's own positions are kept");
});

t("no word of the reference is ever drawn: decorative texts and unused blocks are left out, never filled with the old words", () => {
  const { seed, notes } = layoutToSeed(LAYOUT, { headline: "Tajuk baharu", points: ["Satu"] }, { width: 1080, height: 1350 });
  const all = seed.layers.filter((l) => l.kind === "text").map((l) => l.text).join("|");
  for (const old of ["LABEL", "Headline", "two", "src", "01/10"]) assert.ok(!all.includes(old), old);
  assert.equal(seed.layers.filter((l) => l.kind === "text").length, 2);
  assert.ok(notes.some((x) => /label|Label/.test(x)) && notes.some((x) => /source|Source/i.test(x)) && notes.some((x) => /decorative/.test(x)));
});

t("shapes keep the reference's stacking order; a full-bleed photo becomes the background colour, and a picture goes behind everything else", () => {
  const without = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1350 });
  assert.equal(without.seed.layers[0].role, "bg");
  assert.equal(without.seed.layers.some((l) => l.kind === "photo" || l.kind === "image"), false);
  assert.ok(without.notes.some((x) => /background photo/.test(x)));
  const scrim = without.seed.layers.find((l) => l.kind === "rect" && l.name === "Shape");
  assert.equal(scrim.opacity, 0.6);
  assert.equal(scrim.y, 0.55 * 1350);
  const ord = keys(without.seed);
  assert.ok(ord.indexOf("rect:Shape") < ord.indexOf("text:Headline"), "the scrim sits under the headline, as in the reference");
  const withPic = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1350, pictureUrl: "blob:x" });
  assert.deepEqual(withPic.seed.layers.slice(0, 2).map((l) => [l.kind, l.role]), [["rect", "bg"], ["image", "bg"]]);
  assert.equal(withPic.seed.layers[1].cover, true);
});

t("a smaller picture area takes the picture clipped to its shape; with no picture it is an empty box named for what it showed", () => {
  const lay = cleanLayout({ elements: [{ type: "photo", x: 0.1, y: 0.1, w: 0.4, h: 0.3, shape: "ellipse", description: "a serum bottle" }, text({ text: "h" })] }).layout;
  const a = layoutToSeed(lay, { headline: "T" }, { width: 1000, height: 1000, pictureUrl: "blob:x" });
  const ph = a.seed.layers.find((l) => l.kind === "photo");
  assert.deepEqual([ph.url, ph.shape, ph.x, ph.w], ["blob:x", "ellipse", 100, 400]);
  assert.equal(a.seed.layers.some((l) => l.kind === "image"), false);
  const b = layoutToSeed(lay, { headline: "T" }, { width: 1000, height: 1000 });
  const empty = b.seed.layers.find((l) => l.kind === "photo");
  assert.equal(empty.url, "");
  assert.ok(/a serum bottle/.test(empty.name));
});

t("the target canvas decides the pixels: the same layout at 1080x1080 and 1080x1920 scales every box", () => {
  const sq = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1080 }).seed;
  const tall = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1920 }).seed;
  assert.equal([sq.width, sq.height].join("x"), "1080x1080");
  assert.equal(tall.layers.find((l) => l.name === "Headline").top, 0.5 * 1920);
  assert.equal(sq.layers.find((l) => l.name === "Headline").size, tall.layers.find((l) => l.name === "Headline").size, "type follows the shorter side");
});

t("a reference with no title block still gets one; one with no point blocks says the points were left out", () => {
  const noTitle = cleanLayout({ elements: [text({ role: "eyebrow", text: "x", y: 0.9, h: 0.04, size: 0.02 })] }).layout;
  const r = layoutToSeed(noTitle, { headline: "Tajuk", points: ["Satu"] }, { width: 1000, height: 1000 });
  assert.ok(r.seed.layers.some((l) => l.name === "Headline" && l.text === "Tajuk"));
  assert.ok(r.notes.some((x) => /no headline block/.test(x)) && r.notes.some((x) => /no point block/.test(x)));
});

t("a point with no room left on the canvas is dropped and said so, not stacked off the edge", () => {
  const lay = cleanLayout({ elements: [text({ text: "h" }), text({ role: "point", y: 0.8, h: 0.15, text: "p" })] }).layout;
  const r = layoutToSeed(lay, { headline: "T", points: ["a", "b", "c", "d"] }, { width: 1000, height: 1000 });
  assert.equal(r.seed.layers.filter((l) => /^Point/.test(l.name)).length, 2, "a tall block holds two points with the type shrunk");
  assert.equal(r.notes.filter((x) => /no room/.test(x)).length, 2);
});

t("gradient end points run through the box for CSS-style angles", () => {
  const r0 = (v) => Math.round(v) + 0;                      // + 0 turns -0 into 0
  const down = gradientCoords(180, 100, 200);
  assert.deepEqual([down.x1, down.y1, down.x2, down.y2].map(r0), [50, 0, 50, 200]);
  const right = gradientCoords(90, 100, 200);
  assert.deepEqual([right.x1, right.y1, right.x2, right.y2].map(r0), [0, 100, 100, 100]);
  const up = gradientCoords(0, 100, 200);
  assert.deepEqual([up.y1, up.y2].map(r0), [200, 0]);
});

t("fonts: classes map to the faces Kanvas has, bold sans is Poppins, weights snap to what the face offers", () => {
  assert.equal(fontFor("serif", 800), "Playfair Display");
  assert.equal(fontFor("sans", 800), "Poppins");
  assert.equal(fontFor("sans", 400), "Instrument Sans");
  assert.equal(fontFor("condensed", 700), "Anton");
  assert.equal(fontFor("mono", 400), "JetBrains Mono");
  assert.equal(fontFor("nope", 400), "Poppins");
  assert.equal(nearestWeight("Anton", 900), 400);
  assert.equal(nearestWeight("Poppins", 500), 600);
  assert.equal(stripEmph("a *b* c *d*"), "a b c d");
  assert.equal(stripEmph("2*3 only"), "2*3 only");
});

console.log(`${n} design clone tests passed`);

// ---- second pass (1 Oct 2026): "almost 100% serupa" and "inspired ... generate" ---------------------------------------------------
import { MODES, REFINE_SYSTEM, inspireSystem, keepWords, refineMessages } from "../supabase/functions/semasa-chat/design.js";
import { medianRgb, patchBoxes, patchFromRings, rgbHex } from "./src/lib/designCloneSeed.js";
import { sizeLike } from "./src/lib/designPatch.js";

t("the reader is asked for tight boxes, the colour behind each block and the logo/face boxes; clone keeps the arrangement, inspire must not", () => {
  const s = designSystem("regulab", true);
  for (const needle of [/TIGHT box/, /"behind"/, /"lines"/, /"palette"/, /AS CLOSE TO IDENTICAL/]) assert.match(s, needle);
  const i = inspireSystem("regulab", true);
  for (const needle of [/Do NOT copy its layout/, /ORIGINAL design/, /NEVER carry these over/, /two to five points/]) assert.match(i, needle);
  assert.deepEqual(MODES, ["clone", "inspire"]);
  assert.equal(designMessages({ image: PNG, width: 1080, height: 1080, brief: "x", mode: "inspire" }).mode, "inspire");
  assert.match(designMessages({ image: PNG, width: 1080, height: 1080, brief: "x", mode: "inspire" }).messages[0].content, /art director/);
  assert.equal(designMessages({ image: PNG, width: 1080, height: 1080, brief: "x", mode: "nonsense" }).mode, "clone");
});

t("cleanLayout keeps what the second pass needs: behind colours, line counts, the palette, and the boxes of logos and faces as covers", () => {
  const r = cleanLayout({ palette: ["#AABBCC", "bad", "#aabbcc", "#112233"], elements: [
    { type: "logo", x: 0.8, y: 0.02, w: 0.15, h: 0.08 }, { type: "person", x: 0.4, y: 0.2, w: 0.3, h: 0.5 },
    text({ text: "Hi", behind: "#0A3D3A", lines: 3 }), text({ role: "point", text: "p", behind: "nope", lines: 0, y: 0.5 })] });
  assert.deepEqual(r.layout.palette, ["#aabbcc", "#112233"]);
  assert.deepEqual(r.layout.covers.map((c) => c.kind), ["logo", "person"]);
  assert.equal(r.layout.covers[0].x, 0.8);
  const [h, p] = r.layout.elements;
  assert.deepEqual([h.behind, h.lines, p.behind, p.lines], ["#0a3d3a", 3, null, 1]);
  assert.ok(!r.layout.elements.some((e) => e.type === "logo"), "a logo is a cover, never a layer");
});

t("the refine request carries both pictures and the cleaned layout, and refuses a bad picture or layout before any AI call", () => {
  const r = refineMessages({ image: PNG, render: PNG, layout: LAYOUT, width: 1080, height: 1350 });
  assert.ok(!r.error, r.error);
  assert.equal(r.messages[0].content, REFINE_SYSTEM);
  assert.match(REFINE_SYSTEM, /never the words themselves/);
  const parts = r.messages[1].content;
  assert.deepEqual(parts.map((p) => p.type), ["text", "image_url", "image_url"]);
  assert.match(parts[0].text, /"elements"/);
  assert.match(refineMessages({ image: PNG, render: "nope", layout: LAYOUT, width: 1080, height: 1350 }).error, /rebuild must be sent/);
  assert.match(refineMessages({ image: PNG, render: PNG, layout: { elements: [] }, width: 1080, height: 1350 }).error, /not a layout/);
  assert.match(refineMessages({ image: PNG, render: PNG, layout: LAYOUT, width: 10, height: 1350 }).error, /size/);
});

t("a refined layout keeps the words and roles of the layout it refines, by role and order, even when the reader rewrote them", () => {
  const moved = { ...LAYOUT, elements: LAYOUT.elements.map((e) => (e.type === "text" ? { ...e, y: e.y + 0.05, text: "REWRITTEN" } : e)) };
  const kept = keepWords(LAYOUT, moved);
  const texts = kept.elements.filter((e) => e.type === "text");
  assert.deepEqual(texts.map((e) => e.text), ["LABEL", "Headline", "one", "two", "src", "01/10"]);
  assert.ok(texts.every((e, i) => e.y === LAYOUT.elements.filter((x) => x.type === "text")[i].y + 0.05), "the moves are kept");
  const fewer = { ...LAYOUT, elements: LAYOUT.elements.filter((e) => e.role !== "point") };
  assert.equal(keepWords(LAYOUT, fewer).elements.filter((e) => e.role === "point").length, 0, "a dropped block stays dropped");
  assert.equal(keepWords(null, moved), moved);
});

t("patches: the median colour of a ring, a vertical gradient from the top ring to the bottom one, flat only when they agree, the reader's guess as the fallback", () => {
  assert.deepEqual(medianRgb([[10, 10, 10], [250, 250, 250], [12, 11, 10]]), [12, 11, 10]);
  assert.equal(medianRgb([]), null);
  assert.equal(rgbHex([255, 0, 128]), "#ff0080");
  assert.deepEqual(patchFromRings([[20, 20, 20]], [[21, 20, 20]]), { fill: "#141414" });
  assert.ok(patchFromRings([[20, 20, 20]], [[30, 28, 26]]).gradient, "even a small run is a gradient, so it blends on a gradient background");
  const g = patchFromRings([[0, 0, 0]], [[255, 255, 255]]);
  assert.deepEqual(g.gradient.stops.map((s) => s.color), ["#000000", "#ffffff"]);
  assert.deepEqual(patchFromRings([], [], "#0a3d3a"), { fill: "#0a3d3a" });
  assert.equal(patchFromRings([], [], null), null);
  assert.deepEqual(patchFromRings([], [[9, 9, 9]]), { fill: "#090909" });
});

t("patch boxes cover every text block and every logo or face box, grown a little and never past the canvas", () => {
  const lay = cleanLayout({ elements: [{ type: "logo", x: 0.9, y: 0.9, w: 0.1, h: 0.1 }, text({ text: "Hi", x: 0, y: 0, w: 0.5, h: 0.1, behind: "#123456" })] }).layout;
  const boxes = patchBoxes(lay);
  assert.deepEqual(boxes.map((b) => b.kind), ["text", "logo"]);
  assert.deepEqual([boxes[0].x, boxes[0].y, boxes[0].behind], [0, 0, "#123456"]);
  assert.ok(boxes[0].w > 0.5 && boxes[0].h > 0.1, "grown");
  assert.ok(boxes[1].x + boxes[1].w <= 1 + 1e-9 && boxes[1].y + boxes[1].h <= 1 + 1e-9, "never past the canvas");
});

t("on the reference picture only the words and the patches are drawn, the picture itself is the background, and nothing is rebuilt twice", () => {
  const patches = patchBoxes(LAYOUT).map((b, i) => ({ ...b, fill: i % 2 ? "#000000" : null, gradient: i % 2 ? null : { angle: 180, stops: [{ at: 0, color: "#000000" }, { at: 1, color: "#ffffff" }] } }));
  const { seed, notes } = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1350, referenceUrl: "blob:ref", patches });
  assert.equal(seed.source, "design-clone-ref");
  assert.equal(seed.layers[1].kind, "image");
  assert.equal(seed.layers[1].url, "blob:ref");
  assert.ok(seed.layers[1].cover);
  const kinds = seed.layers.map((l) => l.kind);
  assert.ok(!kinds.includes("photo") && !kinds.includes("line"), "shapes of the reference are in the picture already");
  assert.equal(seed.layers.filter((l) => l.role === "patch").length, patches.length);
  assert.equal(seed.layers.filter((l) => l.kind === "text").length, 6, "eyebrow, headline, three points (spread over the two blocks), source");
  assert.ok(seed.layers.findIndex((l) => l.role === "patch") < seed.layers.findIndex((l) => l.kind === "text"), "patches go under the words");
  assert.ok(!notes.some((n) => /background photo/.test(n)));
  const withPhoto = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1350, referenceUrl: "blob:ref", patches: [{ ...patches[0], onPhoto: true }] });
  assert.ok(withPhoto.notes.some((n) => /photograph/.test(n)), "a patch on a photograph is said");
  const plain = layoutToSeed(LAYOUT, WORDS, { width: 1080, height: 1350 });
  assert.equal(plain.seed.source, "design-clone");
  assert.ok(plain.seed.layers.some((l) => l.kind === "line"), "without the reference every shape is rebuilt as before");
});

t("a canvas the reference's own shape: the shorter side is 1080 and the longer side keeps the ratio, capped at the function's limit", () => {
  assert.deepEqual(sizeLike(1200, 1500), [1080, 1350]);
  assert.deepEqual(sizeLike(1920, 1080), [1920, 1080]);
  assert.deepEqual(sizeLike(500, 500), [1080, 1080]);
  assert.deepEqual(sizeLike(100, 3000), [1080, 4096]);
  assert.deepEqual(sizeLike(0, 0), [1080, 1080]);
});

console.log(`design_clone: ${n} ok`);
