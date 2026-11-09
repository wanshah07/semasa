import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { rateCheck, rateImage, robotsFor, teamCards } from "./src/lib/aiTeam.js";

const good = { model: "m", listed: { read: true, exact: true }, image: { tested: true, reads: true, answer: "Red" }, tools: { tested: true, calls: true }, image_ms: 1500 };
let r = rateCheck(good);
assert.deepEqual([r.tested, r.score, r.stars], [true, 100, 5]);
assert.equal(r.parts.speed, 25);

// speed is linear between 2 s and 15 s and never negative
assert.equal(rateCheck({ ...good, image_ms: 8500 }).parts.speed, 13);          // halfway: 12.5 rounds to 13
assert.equal(rateCheck({ ...good, image_ms: 30000 }).parts.speed, 0);
assert.equal(rateCheck({ ...good, image_ms: 30000 }).score, 75);

// a model that answers but reads no picture and calls no tool is a middling score with a plain note
r = rateCheck({ ...good, image: { tested: true, reads: false, answer: "blue" }, tools: { tested: true, calls: false } });
assert.equal(r.score, 25 + 10 + 25) ; assert.equal(r.stars, 3); assert.match(r.note, /reads no picture/);

// listed by a different spelling earns half; a refused call earns nothing for answering or speed
assert.equal(rateCheck({ ...good, listed: { read: true, exact: false, spelled_as: "M" } }).score, 95);
r = rateCheck({ ...good, image: { tested: true, reads: false, error: "HTTP 400" }, tools: { tested: true, error: "HTTP 400" } });
assert.deepEqual([r.score, r.stars, r.parts.answered], [10, 1, false]); assert.equal(r.note, "did not answer");

// a check that could not run is "not tested", never a low score
for (const x of [null, undefined, { error: "no robot can be tested" }, "x"]) assert.equal(rateCheck(x).tested, false);
assert.match(rateCheck({ error: "the Test button asks the OpenAI dialect" }).why, /OpenAI dialect/);

// the AI team card offers models as buttons (no dropdown), rates a model right after it is picked unless the switch is off
const card = readFileSync(new URL("./src/components/AiTeam.jsx", import.meta.url), "utf8");
assert.ok(card.includes("data-model-button") && card.includes("data-robot-button") && card.includes("data-ai-rate") && card.includes("data-live-switch"));
assert.ok(!/<Select[^>]*aria-label=\{t\("Model"/.test(card), "the model dropdown is gone");
assert.ok(card.includes("rateCheck(") && card.includes("checkAI("));
// the Gambar tile shows a sample picture until the post has its own (Wan, 9 Nov 2026)
const picker = readFileSync(new URL("./src/components/LookPicker.jsx", import.meta.url), "utf8");
assert.ok(/const sampleBg = bgUrl \|\| groundOf\("g_makmal02"\)/.test(picker) && /look: "image", bg: sampleBg/.test(picker), "the Gambar tile has a sample picture");
console.log("aiRate: ok");

// a picture maker is rated from one small real drawing (9 Nov 2026: "allow model button to be clicked and run")
{
  const drew = (ms, over = {}) => ({ model: "gpt-image-2.5", kind: "image", listed: { read: true, exact: true }, image_gen: { tested: true, ok: true, ms, ...over } });
  const fast = rateImage(drew(9000));
  assert.equal(fast.tested, true); assert.equal(fast.kind, "image");
  assert.equal(fast.score, 100); assert.equal(fast.stars, 5); assert.equal(fast.parts.drew, true);
  assert.equal(rateImage(drew(60000)).score, 70, "a drawing that took a minute scores what it drew and is listed, nothing for speed");
  assert.equal(rateImage(drew(37500)).score, 85, "halfway between 15 s and 60 s is half the speed points");
  assert.equal(rateImage({ ...drew(5000), listed: { read: true, exact: false, spelled_as: "gpt-image-2-5" } }).score, 95);
  const none = rateImage(drew(1200, { ok: false, error: "HTTP 404: no such endpoint" }));
  assert.equal(none.tested, true); assert.equal(none.score, 10); assert.equal(none.stars, 1); assert.match(none.note, /404/);
  assert.equal(rateImage({ error: "function belum dipasang" }).tested, false, "a check that could not run is not a low score");
  assert.equal(rateImage({ model: "m", image_gen: { tested: false } }).tested, false);
  assert.equal(rateImage(null).tested, false);
  // Mireld (Wanshah 2) is offered for the picture maker, beside Wanshah 3
  const cards = teamCards([{ slug: "mireld", key_set: true, reachable: true, key_ok: true, chat_ok: true, checked_at: new Date().toISOString(), models: [] }]);
  assert.ok(robotsFor(cards, "image_gen").some((c) => c.slug === "mireld"), "Wanshah 2 is a picture maker option");
  assert.ok(robotsFor(cards, "image_gen").some((c) => c.slug === "kiosapi"));
}
console.log("aiRate image: ok");
