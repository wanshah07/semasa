import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// the Ideas tab says so when auto-fill is waiting on Buffer's queue, from the row the worker writes (settings.buffer_queue)
const tab = readFileSync(new URL("./src/pages/IdeasTab.jsx", import.meta.url), "utf8");
assert.ok(tab.includes("data-queue-pause") && /<QueuePause q=\{motionSettings\?\.buffer_queue\}/.test(tab));
assert.ok(/if \(!q\?\.paused\) return null/.test(tab), "nothing shows unless the queue is paused");
// the worker writes the same keys the banner reads
const py = readFileSync(new URL("../backend/semasa/buffer_queue.py", import.meta.url), "utf8");
for (const k of ['"paused"', '"full"', '"counts"', '"limit"']) assert.ok(py.includes(k), `buffer_queue.py writes ${k}`);
// the rulebook no longer bans a follow invitation but still bans the other asks
const rules = JSON.parse(readFileSync(new URL("../rules/compliance.json", import.meta.url), "utf8"));
const labels = rules.cta.map((c) => c.label);
assert.ok(!labels.includes("CTA: asks for a follow"));
for (const l of ["CTA: 'komen di bawah'", "CTA: 'hubungi kami'", "CTA: 'klik link'", "CTA: asks for a share"]) assert.ok(labels.includes(l), l);
console.log("queuePause: ok");
