import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { SOFT } from "./src/lib/cards/studio.js";

// a photo that is the ground UNDER words is softened (blur + a veil that lowers its contrast); a hero panel with the words
// BELOW it stays sharp. Read from the source because the drawing needs a real canvas (the browser comparison is in the PR).
const src = readFileSync(new URL("./src/lib/cards/studio.js", import.meta.url), "utf8");
assert.ok(/function coverSoft\(/.test(src));
assert.ok(/coverSoft\(ctx, img, W, H, !!spec\._light\)/.test(src), "grid and ERA grounds (drawGround) are softened");
const full = src.match(/if \(bg\) \{ if \(h >= H\) coverSoft\(ctx, bg, w, h, false\); else coverDraw\(ctx, bg, w, h\); \}/g) || [];
assert.equal(full.length, 2, "the two photo-family painters soften only a full-bleed picture");
// the blur is not the browser's ctx.filter (iPhone Safari before 18 has none)
assert.ok(!/ctx\.filter\s*=|\.filter\s*=\s*["`']blur/.test(src), "no ctx.filter: iPhone Safari lacks it");
// numbers: a real blur and a real veil, but never a wipe-out of the picture
assert.ok(SOFT.blurDivisor >= 30 && SOFT.blurDivisor <= 90, "blur radius between a 30th and a 90th of the card");
const alpha = (c) => Number(/,\s*([\d.]+)\)$/.exec(c)[1]);
assert.ok(alpha(SOFT.veilDark) >= 0.2 && alpha(SOFT.veilDark) <= 0.5 && alpha(SOFT.veilLight) >= 0.15 && alpha(SOFT.veilLight) <= 0.4);

// the worker's slide drawer says the same thing for the same reason
const py = readFileSync(new URL("../backend/semasa/slides.py", import.meta.url), "utf8");
assert.ok(/def soften_ground\(/.test(py) && /soften_ground\(cover_fit\(/.test(py), "backend slides soften the ground too");
console.log("photoSoft: ok");
