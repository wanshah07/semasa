import assert from "node:assert/strict";
import { learningOf, learningOn, learningRows, ratePct } from "./src/lib/hookLearning.js";

assert.deepEqual(learningOf(undefined), { at: null, windowDays: 60, minPosts: 3, measured: 0, ranking: [] });
assert.deepEqual(learningOf("junk"), { at: null, windowDays: 60, minPosts: 3, measured: 0, ranking: [] });
const got = learningOf({ at: "t", window_days: 45, min_posts: 4, measured: 12, ranking: [
  { shape: 17, style: "", n: 5, views: 900.5, rate: 0.05, score: 1, films: 2 }, { shape: "x" }, null, { shape: 21, n: 3 }] });
assert.equal(got.windowDays, 45); assert.equal(got.minPosts, 4); assert.equal(got.measured, 12);
assert.deepEqual(got.ranking.map((r) => r.shape), [17, 21], "rows with no shape number are dropped");
assert.equal(got.ranking[0].films, 2); assert.equal(got.ranking[1].views, 0);
assert.equal(learningOn(undefined), true); assert.equal(learningOn({}), true); assert.equal(learningOn({ enabled: true }), true);
assert.equal(learningOn({ enabled: false }), false); assert.equal(learningOn("x"), true);
assert.equal(ratePct(0.05), "5.0%"); assert.equal(ratePct(0.0123), "1.2%"); assert.equal(ratePct(undefined), "0.0%");
assert.deepEqual(learningRows([{ shape: 1 }, { shape: 2 }, { shape: 3 }, { shape: 4 }]).map((r) => r.top), [true, true, true, false]);
assert.deepEqual(learningRows(undefined), []);
console.log("hookLearning.test.mjs: ok");
