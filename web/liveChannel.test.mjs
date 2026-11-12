import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { coalesce, liveName } from "./src/lib/liveChannel.js";

// two subscriptions to the same table never share a name (a shared name is the blank-page crash)
const a = liveName("semasa_ai_providers_live"), b = liveName("semasa_ai_providers_live");
assert.notEqual(a, b); assert.ok(a.startsWith("semasa_ai_providers_live") && b.startsWith("semasa_ai_providers_live"));
assert.equal(new Set(Array.from({ length: 200 }, () => liveName("x"))).size, 200);

// no source file opens a realtime channel with a fixed name: every .channel( goes through liveName(
const walk = (d) => readdirSync(d).flatMap((f) => { const p = join(d, f); return statSync(p).isDirectory() ? walk(p) : /\.(jsx?|tsx?)$/.test(p) ? [p] : []; });
const offenders = [];
for (const f of walk(new URL("./src", import.meta.url).pathname)) {
  readFileSync(f, "utf8").split("\n").forEach((line, i) => {
    if (/\.channel\(/.test(line) && !/\.channel\(liveName\(/.test(line)) offenders.push(`${f}:${i + 1}: ${line.trim()}`);
  });
}
assert.deepEqual(offenders, [], "every realtime channel name must come from liveName()");
// a burst of realtime events is ONE read, and a read never starts while another is in flight
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
{
  let reads = 0, inFlight = 0, maxInFlight = 0;
  const kick = coalesce(async () => { reads++; inFlight++; maxInFlight = Math.max(maxInFlight, inFlight); await sleep(30); inFlight--; }, 20);
  for (let i = 0; i < 25; i++) kick();                        // 25 row changes in the same instant
  await sleep(120);
  assert.equal(reads, 1, "a burst of 25 events must be one read");
  kick.now(); kick.now(); kick.now();                         // three polls landing together
  await sleep(150);
  assert.equal(maxInFlight, 1, "never two reads in flight");
  assert.ok(reads >= 2 && reads <= 3, `polls on top of each other collapse (reads=${reads})`);
  const before = reads;
  kick(); kick.cancel(); await sleep(80);
  assert.equal(reads, before, "cancel drops a read that has not started");
  const bad = coalesce(async () => { throw new Error("x"); }, 5);
  bad.now(); await sleep(20);                                  // a failing loader does not throw out of the timer
}
console.log("liveChannel: ok");
