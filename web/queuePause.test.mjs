import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// the Ideas tab says so when auto-fill is waiting on a full queue, from the row the worker writes: Buffer's (settings.buffer_queue)
// or, while Zernio carries ws.regulab and Buffer rests, Zernio's (settings.zernio_queue; Wan, 10 Nov 2026)
const tab = readFileSync(new URL("./src/pages/IdeasTab.jsx", import.meta.url), "utf8");
assert.ok(tab.includes("data-queue-pause") && /<QueuePause q=\{queuePause\(motionSettings\)\}/.test(tab));
assert.ok(/s\?\.zernio_queue\?\.paused/.test(tab) && /s\?\.buffer_queue\?\.paused/.test(tab), "either queue can pause it");
assert.ok(tab.includes("const name = q.name ||"), "the banner names the queue that is full");
assert.ok(/if \(!q\?\.paused\) return null/.test(tab), "nothing shows unless the queue is paused");
// the worker writes the same keys the banner reads
const py = readFileSync(new URL("../backend/semasa/buffer_queue.py", import.meta.url), "utf8");
for (const k of ['"paused"', '"full"', '"counts"', '"limit"', 'ZKEY = "zernio_queue"']) assert.ok(py.includes(k), `buffer_queue.py writes ${k}`);
// the rulebook no longer bans a follow invitation but still bans the other asks
const rules = JSON.parse(readFileSync(new URL("../rules/compliance.json", import.meta.url), "utf8"));
const labels = rules.cta.map((c) => c.label);
assert.ok(!labels.includes("CTA: asks for a follow"));
for (const l of ["CTA: 'komen di bawah'", "CTA: 'hubungi kami'", "CTA: 'klik link'", "CTA: asks for a share"]) assert.ok(labels.includes(l), l);
console.log("queuePause: ok");
