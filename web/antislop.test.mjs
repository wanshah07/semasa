import assert from "node:assert/strict";
import { LEVELS, levelOf, summarise, verdict } from "./src/lib/antislop.js";

assert.deepEqual(LEVELS, ["off", "clean", "full"]);
assert.equal(levelOf({ level: "clean" }), "clean");
assert.equal(levelOf("off"), "off");
assert.equal(levelOf({ level: "x" }), "full");
assert.equal(levelOf(null), "full");

const row = (level, chars, raw_hits, final_hits) => ({ level, chars, raw_hits, final_hits });
const rows = [
  ...Array.from({ length: 10 }, () => row("off", 1000, 6, 6)),
  ...Array.from({ length: 10 }, () => row("clean", 1000, 6, 2)),
  ...Array.from({ length: 4 }, () => row("full", 1000, 1, 0)),
  row("unknown", 5, 5, 5),
];
const s = summarise(rows);
assert.equal(s.length, 3);
const by = Object.fromEntries(s.map((x) => [x.level, x]));
assert.equal(by.off.outputs, 10);
assert.equal(by.off.rawPer1k, 6);
assert.equal(by.clean.finalPer1k, 2);
assert.equal(by.full.enough, false, "four outputs is too few to read");
assert.deepEqual(verdict(s), { ready: true, best: "clean" }, "only levels with enough outputs are compared");
assert.equal(verdict(summarise([])).ready, false);
assert.equal(summarise([])[0].rawPer1k, null, "no output, no rate");
console.log("antislop ok");
