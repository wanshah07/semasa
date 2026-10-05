/* "Make the rebuild follow the reference" (Wan, 4 Oct 2026): colours measured from the reference's own pixels, a score for how close a
   rebuild is, a refine that is never accepted when it is worse, our logo and replaceable picture boxes where the reference had its own,
   and the 5xx that used to print a whole HTML page. Pictures are drawn here, pixel by pixel; nothing third-party is committed. */
import assert from "node:assert/strict";
import { backgroundPromptOf, compareImages, dropBrandPhotos, fillerOf, fillerSlide, fromHex, judgePass, measureBackground, measureFill, measureInk, snapLayout, toHex } from "./src/lib/designFidelity.js";
import { layoutToSeed } from "./src/lib/designCloneSeed.js";
import { isOutage, transient } from "./src/lib/upstream.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

// ---- pictures drawn by hand ------------------------------------------------------------------------------------------
const make = (w, h, fill) => {
  const data = new Uint8ClampedArray(w * h * 4);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const c = typeof fill === "function" ? fill(x / w, y / h) : fill; data.set([c[0], c[1], c[2], 255], (y * w + x) * 4); }
  return { data, width: w, height: h };
};
const paint = (img, b, color) => {
  const x0 = Math.round(b.x * img.width), x1 = Math.round((b.x + b.w) * img.width), y0 = Math.round(b.y * img.height), y1 = Math.round((b.y + b.h) * img.height);
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) { const c = typeof color === "function" ? color(x, y) : color; img.data.set([c[0], c[1], c[2], 255], (y * img.width + x) * 4); }
};
// "letters": vertical stripes 2px on / 3px off, painted only where on
const letters = (img, b, ink) => {
  const x0 = Math.round(b.x * img.width), x1 = Math.round((b.x + b.w) * img.width), y0 = Math.round(b.y * img.height), y1 = Math.round((b.y + b.h) * img.height);
  for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) if (x % 5 < 2) img.data.set([ink[0], ink[1], ink[2], 255], (y * img.width + x) * 4);
};
const near = (hex, rgb, tol = 6) => { const c = fromHex(hex); return Math.hypot(c[0] - rgb[0], c[1] - rgb[1], c[2] - rgb[2]) <= tol; };

// ---- measuring --------------------------------------------------------------------------------------------------------
t("hex helpers round-trip and refuse junk", () => {
  assert.equal(toHex([12, 27, 39]), "#0c1b27");
  assert.deepEqual(fromHex("#0c1b27"), [12, 27, 39]);
  assert.equal(fromHex("0c1b27"), null);
  assert.equal(fromHex(null), null);
});

t("a flat background is read as one colour, whatever the reader guessed", () => {
  const img = make(120, 160, [236, 237, 242]);
  const bg = measureBackground(img, { color: "#ffffff", gradient: null });
  assert.ok(near(bg.color, [236, 237, 242]) && bg.gradient === null);
});

t("a top-to-bottom gradient keeps its direction and its measured stops (the poster's pale lilac fade)", () => {
  const img = make(120, 200, (fx, fy) => [218 + 27 * fy, 218 + 26 * fy, 228 + 21 * fy]);
  const bg = measureBackground(img, { color: "#ffffff", gradient: { angle: 180, stops: [{ at: 0, color: "#ffffff" }, { at: 1, color: "#000000" }] } });
  assert.ok(bg.gradient && bg.gradient.angle === 180);
  assert.ok(near(bg.gradient.stops[0].color, [219, 219, 229], 8), bg.gradient.stops[0].color);
  assert.ok(near(bg.gradient.stops[1].color, [244, 243, 248], 8), bg.gradient.stops[1].color);
});

t("a shape's fill is its measured middle; a box on a photograph is refused rather than averaged", () => {
  const img = make(200, 200, [240, 240, 240]);
  paint(img, { x: 0.1, y: 0.1, w: 0.5, h: 0.3 }, [92, 118, 145]);
  assert.ok(near(measureFill(img, { x: 0.1, y: 0.1, w: 0.5, h: 0.3 }), [92, 118, 145], 3));
  const noisy = make(200, 200, (fx, fy) => [(fx * 977 * 255) % 255, (fy * 631 * 255) % 255, ((fx + fy) * 313 * 255) % 255]);
  assert.equal(measureFill(noisy, { x: 0.1, y: 0.1, w: 0.5, h: 0.3 }), null);
});

t("ink is the colour of the letters, not the paper, and a box with no letters measures nothing", () => {
  const img = make(300, 300, [245, 244, 249]);
  letters(img, { x: 0.1, y: 0.2, w: 0.6, h: 0.1 }, [12, 27, 39]);
  const m = measureInk(img, { x: 0.1, y: 0.2, w: 0.6, h: 0.1 });
  assert.ok(near(m.ink, [12, 27, 39], 4) && near(m.paper, [245, 244, 249], 4));
  assert.equal(measureInk(img, { x: 0.1, y: 0.6, w: 0.6, h: 0.1 }), null);
});

t("ink over a coloured band is measured against THAT band (white words on the blue box)", () => {
  const img = make(300, 300, [245, 244, 249]);
  paint(img, { x: 0.05, y: 0.15, w: 0.9, h: 0.2 }, [29, 72, 114]);
  letters(img, { x: 0.1, y: 0.2, w: 0.6, h: 0.1 }, [255, 255, 255]);
  const m = measureInk(img, { x: 0.1, y: 0.2, w: 0.6, h: 0.1 });
  assert.ok(near(m.ink, [255, 255, 255], 4) && near(m.paper, [29, 72, 114], 6), JSON.stringify(m));
});

t("snapLayout replaces every guessed colour with the measured one, names the changes, and leaves the original untouched", () => {
  const img = make(300, 400, [245, 244, 249]);
  paint(img, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [92, 118, 145]);
  letters(img, { x: 0.1, y: 0.1, w: 0.7, h: 0.1 }, [12, 27, 39]);
  const layout = { background: { color: "#ffffff", gradient: null }, covers: [], palette: [], elements: [
    { type: "rect", x: 0.05, y: 0.5, w: 0.9, h: 0.2, fill: "#336699" },
    { type: "text", role: "headline", x: 0.1, y: 0.1, w: 0.7, h: 0.1, color: "#000000", text: "x" },
    { type: "text", role: "point", x: 0.1, y: 0.8, w: 0.7, h: 0.1, color: "#123456", text: "y" }] };
  const before = JSON.stringify(layout);
  const out = snapLayout(layout, img);
  assert.equal(JSON.stringify(layout), before);
  assert.ok(near(out.layout.background.color, [245, 244, 249], 3));
  assert.ok(near(out.layout.elements[0].fill, [92, 118, 145], 3));
  assert.ok(near(out.layout.elements[1].color, [12, 27, 39], 4));
  assert.equal(out.layout.elements[2].color, "#123456");                      // no letters there: the guess stands
  assert.ok(out.kept.some((k) => /point/.test(k)) && out.changes.length >= 3);
});

// ---- scoring ----------------------------------------------------------------------------------------------------------
const poster = () => {
  const img = make(240, 320, [245, 244, 249]);
  paint(img, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [92, 118, 145]);
  letters(img, { x: 0.1, y: 0.1, w: 0.7, h: 0.15 }, [12, 27, 39]);
  return img;
};

t("the same picture scores 100, and the score does not depend on the picture's size", () => {
  const a = compareImages(poster(), poster());
  assert.equal(a.score, 100);
  const small = make(120, 160, [245, 244, 249]);
  paint(small, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [92, 118, 145]);
  letters(small, { x: 0.1, y: 0.1, w: 0.7, h: 0.15 }, [12, 27, 39]);
  assert.ok(compareImages(poster(), small).score > 90);
});

t("a tint scores lower, a wrong colour scores lower still, a missing block lower than a tint, and the worst cells name where", () => {
  const ref = poster();
  const tint = poster(); paint(tint, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [100, 124, 150]);
  const wrong = poster(); paint(wrong, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [200, 60, 60]);
  const gone = poster(); paint(gone, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [245, 244, 249]);
  const s = (x) => compareImages(ref, x).score;
  assert.ok(s(tint) < 100 && s(tint) > s(wrong) && s(wrong) < 97, `${s(tint)} ${s(wrong)}`);
  assert.ok(s(gone) < s(tint));
  const w = compareImages(ref, wrong).worst;
  assert.ok(w.length > 0 && w.every((c) => c.y >= 0.45 && c.y <= 0.72), JSON.stringify(w));
});

t("words in the wrong place cost points even when the average colour is the same (structure counts)", () => {
  const ref = poster();
  const moved = make(240, 320, [245, 244, 249]);
  paint(moved, { x: 0.05, y: 0.5, w: 0.9, h: 0.2 }, [92, 118, 145]);
  letters(moved, { x: 0.1, y: 0.8, w: 0.7, h: 0.15 }, [12, 27, 39]);
  assert.ok(compareImages(ref, moved).score < compareImages(ref, poster()).score - 3);
  assert.ok(compareImages(ref, moved).structure < 100);
});

t("a refine pass that is not closer is NOT accepted; one that is closer is; a good-enough score stops the loop", () => {
  const a = judgePass({ score: 80 }, { score: 76 });
  assert.equal(a.accepted, false); assert.equal(a.stop, true); assert.equal(a.keep.score, 80);
  const b = judgePass({ score: 80 }, { score: 80.2 });
  assert.equal(b.accepted, false);
  const c = judgePass({ score: 80 }, { score: 86 });
  assert.equal(c.accepted, true); assert.equal(c.stop, false); assert.equal(c.keep.score, 86);
  const d = judgePass({ score: 80 }, { score: 91 });
  assert.equal(d.accepted, true); assert.equal(d.stop, true);
  const e = judgePass({ score: 80 }, { score: 80.9 });             // better, but by less than a point: take it, stop asking
  assert.equal(e.accepted, true); assert.equal(e.stop, true);
});

// ---- logo and picture slots -------------------------------------------------------------------------------------------
const L = () => ({ background: { color: "#eeeeee", gradient: null }, summary: "", elements: [
  { type: "text", role: "headline", x: 0.1, y: 0.2, w: 0.8, h: 0.2, text: "H", font: "serif", weight: 800, size: 0.08, color: "#111111", align: "left" }],
  covers: [{ kind: "logo", x: 0.05, y: 0.03, w: 0.2, h: 0.05 }, { kind: "person", x: 0.6, y: 0.5, w: 0.3, h: 0.3 }, { kind: "logo", x: 0.7, y: 0.9, w: 0.2, h: 0.05 }] });

t("our logo goes where theirs was (once), a face becomes an empty replaceable picture box; neither is copied", () => {
  const { seed } = layoutToSeed(L(), { headline: "Tajuk" }, { width: 1000, height: 1000, logoUrl: "/cards/logo-ink.png" });
  const logos = seed.layers.filter((l) => l.role === "logo");
  assert.equal(logos.length, 1);
  assert.deepEqual(logos[0].fitIn, { x: 50, y: 30, w: 200, h: 50 });
  const pic = seed.layers.filter((l) => l.kind === "photo");
  assert.equal(pic.length, 1);
  assert.equal(pic[0].url, "");
  assert.match(pic[0].name, /replace/);
  assert.deepEqual([pic[0].x, pic[0].y, pic[0].w, pic[0].h], [600, 500, 300, 300]);
});

t("no logoUrl (LinkedIn) means no logo layer at all: a LinkedIn card carries no ws.regulab identity", () => {
  const { seed } = layoutToSeed(L(), { headline: "Tajuk" }, { width: 1000, height: 1000 });
  assert.equal(seed.layers.filter((l) => l.role === "logo").length, 0);
});

// ---- the 520 ----------------------------------------------------------------------------------------------------------
const cf = { statusCode: 520, message: "Unable to parse error message: <!DOCTYPE html><html><head><title>supabase.co | 520: Web server is returning an unknown error</title>" };

t("Cloudflare's HTML error page and 5xx codes are an outage and worth retrying; a refusal is neither", () => {
  assert.equal(isOutage(cf), true); assert.equal(transient(cf), true);
  assert.equal(isOutage({ message: "<html>bad gateway</html>" }), true);
  assert.equal(isOutage({ status: 503, message: "" }), true);
  assert.equal(transient(new TypeError("Failed to fetch")), true);
  for (const e of [{ statusCode: 403, message: "new row violates row-level security policy" }, { statusCode: 413, message: "The object exceeded the maximum allowed size" }, { message: "Duplicate" }, null]) {
    assert.equal(isOutage(e), false); assert.equal(transient(e), false);
  }
});

// ---- sample words the length of the reference's own ----------------------------------------------------------------------------
t("filler is about the length asked, cut at a word, never empty, and differs by seed", () => {
  for (const len of [8, 24, 60, 140]) { const f = fillerOf(len); assert.ok(f.length >= Math.min(len, 8) && f.length <= len + 8 && !/\s$/.test(f), `${len}: ${f.length}`); }
  assert.notEqual(fillerOf(40, 0), fillerOf(40, 3));
  assert.ok(fillerOf(0).length >= 4);
});
t("a filler slide has a slot's worth of words for every slot the layout has, and nothing for the slots it lacks", () => {
  const L = { elements: [{ type: "text", role: "headline", chars: 30 }, { type: "text", role: "point", chars: 50, y: 0.4 }, { type: "text", role: "point", chars: 20, y: 0.5 },
    { type: "text", role: "eyebrow", chars: 14 }, { type: "text", role: "deco", chars: 5 }] };
  const f = fillerSlide(L);
  assert.ok(f.title.length >= 20 && f.points.length === 2 && f.eyebrow && !("footnote" in f));
  assert.ok(f.points[0].length > f.points[1].length);
  assert.equal(fillerSlide({ elements: [{ type: "rect" }] }).points.length, 0);
});

// ---- what the image provider is asked to paint --------------------------------------------------------------------------------
t("the background description comes from the largest picture area and the colours, never from the reference's words", () => {
  const L = { background: { color: "#e6dfec", gradient: { angle: 160, stops: [{ at: 0, color: "#D9D1E2" }, { at: 1, color: "#f7f3f8" }] } }, summary: "a calm clinical poster",
    elements: [{ type: "photo", x: 0, y: 0, w: 0.2, h: 0.2, description: "a small logo" }, { type: "photo", x: 0.5, y: 0.5, w: 0.7, h: 0.55, description: "a pink glass sphere filled with bubbles." },
      { type: "text", role: "headline", text: "SCIENTIFIC SYMPOSIUM", x: 0, y: 0, w: 1, h: 0.1 }] };
  const p = backgroundPromptOf(L);
  assert.ok(p.startsWith("a pink glass sphere filled with bubbles; soft colours close to #d9d1e2, #f7f3f8, #e6dfec") && p.includes("mood: a calm clinical poster"), p);
  assert.ok(!/SYMPOSIUM|logo/i.test(p));
  assert.equal(backgroundPromptOf({ elements: [{ type: "text", text: "x" }] }), "");
  assert.ok(backgroundPromptOf({ ...L, summary: "x".repeat(2000) }).length <= 600);
});

t("a picture area showing a brand, an icon, a product or a person is dropped and never becomes a background", () => {
  const L = { background: { color: "#c00018", gradient: null }, summary: "",
    elements: [{ type: "photo", x: 0, y: 0.7, w: 0.6, h: 0.3, description: "line drawing of skincare bottles icon" },
      { type: "photo", x: 0, y: 0, w: 0.3, h: 0.1, description: "Eucerin brand logo" }, { type: "photo", x: 0.6, y: 0.2, w: 0.4, h: 0.5, description: "a doctor's portrait" },
      { type: "photo", x: 0, y: 0, w: 1, h: 1, description: "deep red satin with soft light" }, { type: "text", role: "headline", x: 0, y: 0, w: 1, h: 0.1 }] };
  const kept = dropBrandPhotos(L).elements;
  assert.deepEqual(kept.filter((e) => e.type === "photo").map((e) => e.description), ["deep red satin with soft light"]);
  assert.equal(kept.length, 2);
  assert.ok(backgroundPromptOf(L).startsWith("deep red satin with soft light"));
  assert.equal(backgroundPromptOf({ ...L, elements: L.elements.slice(0, 3) }), "");
});

console.log(`design_fidelity: ${n} cases ok`);
