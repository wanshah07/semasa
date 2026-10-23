import assert from "node:assert/strict";
import { RESOLUTIONS, SECONDS, checkItems, clampSeconds, fmtBytes, motionLabel, motionRow } from "./src/lib/motion.js";

assert.equal(clampSeconds("abc"), SECONDS.default);
assert.equal(clampSeconds(1), SECONDS.min);
assert.equal(clampSeconds(999), SECONDS.max);
assert.equal(clampSeconds("14.6"), 15);

assert.deepEqual(motionRow({}), { error: "empty" });
assert.deepEqual(motionRow({ url: "github.com/x" }), { error: "url" });
const ok = motionRow({ brief: "  PFAS  ", url: "", stream: "linkedin", resolution: "square", seconds: "20" }, "u1");
assert.deepEqual(ok.row, { brief: "PFAS", source_url: "", stream: "linkedin", resolution: "square", seconds: 20, status: "pending", created_by: "u1" });
const dflt = motionRow({ url: "https://x/y", stream: "nope", resolution: "nope", seconds: 0 });
assert.equal(dflt.row.stream, "regulab"); assert.equal(dflt.row.resolution, "portrait"); assert.equal(dflt.row.seconds, SECONDS.min);
assert.equal(dflt.row.created_by, null);
assert.equal(Object.keys(RESOLUTIONS).length, 3);

assert.equal(motionLabel({ title: "T", brief: "b" }), "T");
assert.equal(motionLabel({ brief: " b " }), "b");
assert.equal(motionLabel({ source_url: "https://x" }), "https://x");
assert.equal(motionLabel(null), "");

const items = checkItems({ check_report: { errors: [{ code: "e1", message: "m" }], warnings: [{ code: "w1", message: "n" }] } });
assert.deepEqual(items.map((i) => [i.code, i.level]), [["e1", "error"], ["w1", "warning"]]);
assert.deepEqual(checkItems({}), []);
assert.equal(fmtBytes(2_200_000), "2.1 MB"); assert.equal(fmtBytes(2048), "2 KB"); assert.equal(fmtBytes(0), "0 B");
console.log("motion.test.mjs: ok");
