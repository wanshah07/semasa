import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { liveName } from "./src/lib/liveChannel.js";

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
console.log("liveChannel: ok");
