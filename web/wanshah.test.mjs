// Wanshah: prompts are one robot in four poses; the cut-out removes only the OUTSIDE white; only https pictures are approved.
import assert from "node:assert/strict";
import { DEFAULT_LOOK, POSES, approvedPoses, buildPrompt, floodTransparent, opaqueBox } from "./src/lib/wanshah.js";

let n = 0;
const ok = (name, fn) => { fn(); n++; };

ok("four poses, one character half", () => {
  assert.deepEqual(POSES.map((p) => p.k), ["wave", "point", "confused", "shocked"]);   // the names the card renderer matches on
  const prompts = POSES.map((p) => buildPrompt(p.k, ""));
  for (const p of prompts) assert.ok(p.startsWith(DEFAULT_LOOK) && /pure white background/.test(p) && /no text/.test(p));
  assert.equal(new Set(prompts).size, 4);
  assert.ok(buildPrompt("wave", "a purple robot").startsWith("a purple robot."));
  assert.throws(() => buildPrompt("dance", ""));
});

const px = (w, h, f) => { const a = new Uint8ClampedArray(w * h * 4); for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const c = f(x, y); a.set([...c, 255], (y * w + x) * 4); } return a; };
const W = [255, 255, 255], B = [20, 120, 140];

ok("outside white goes, white inside the body stays", () => {
  // a teal ring (x,y 3..16) with a white eye inside it and white all round
  const a = px(20, 20, (x, y) => (x >= 3 && x <= 16 && y >= 3 && y <= 16 && !(x >= 8 && x <= 11 && y >= 8 && y <= 11) ? B : W));
  const cleared = floodTransparent(a, 20, 20);
  assert.ok(cleared > 0);
  assert.equal(a[(0 * 20 + 0) * 4 + 3], 0);                 // a corner
  assert.equal(a[(9 * 20 + 9) * 4 + 3], 255);               // the eye: white, but enclosed
  assert.equal(a[(10 * 20 + 5) * 4 + 3] > 0, true);          // the body
  const box = opaqueBox(a, 20, 20);
  assert.ok(box.x >= 3 && box.x <= 4 && box.w <= 14 && box.w >= 12);
});

ok("a picture with no flat ground is left alone", () => {
  const a = px(10, 10, (x, y) => (x < 5 ? W : B));
  const before = Array.from(a);
  assert.equal(floodTransparent(a, 10, 10), -1);
  assert.deepEqual(Array.from(a), before);
});

ok("nothing left means no box", () => {
  const a = px(6, 6, () => W);
  floodTransparent(a, 6, 6);
  assert.equal(opaqueBox(a, 6, 6), null);
});

ok("only https pictures for known poses are approved", () => {
  assert.deepEqual(approvedPoses(null), {});
  assert.deepEqual(approvedPoses({ poses: { wave: { url: "https://x/y.png" }, point: { url: "http://x/y.png" }, dance: { url: "https://x" }, shocked: {} } }), { wave: "https://x/y.png" });
});

console.log(`wanshah.test.mjs: ${n} groups OK`);
