import assert from "node:assert/strict";
import { DEFAULT_KEYWORDS, MAX_HANDLES, MAX_KEYWORDS, cleanHandles, cleanKeywords, handlesOf, keywordsOf, withThreads } from "./src/lib/threadsKeywords.js";

// keywords: trimmed, collapsed, 2..60 letters, no repeats in any case, at most eight
assert.deepEqual(cleanKeywords(["  halal   kosmetik ", "Halal Kosmetik", "x", "", null, "sunscreen"]), ["halal kosmetik", "sunscreen"]);
assert.deepEqual(cleanKeywords("nope"), []);
assert.equal(cleanKeywords(["a".repeat(61)]).length, 0);
assert.equal(cleanKeywords(Array.from({ length: 20 }, (_, i) => `kata ${i}`)).length, MAX_KEYWORDS);

// handles: no @, word characters and dots, at most ten
assert.deepEqual(cleanHandles(["@wan.ridzuan", "wan.ridzuan", "bad handle!", " @@jakim_malaysia "]), ["wan.ridzuan", "jakim_malaysia"]);
assert.equal(cleanHandles(Array.from({ length: 30 }, (_, i) => `akaun${i}`)).length, MAX_HANDLES);

// what is in force: saved wins (even empty), else the sweep's defaults
assert.deepEqual(keywordsOf(undefined), DEFAULT_KEYWORDS);
assert.deepEqual(keywordsOf({ community: { threads: { queries: ["sijil halal"] } } }), ["sijil halal"]);
assert.deepEqual(keywordsOf({ community: { threads: { queries: [] } } }), []);
assert.deepEqual(handlesOf({ community: { threads: { accounts: ["@a", "b"] } } }), ["a", "b"]);
assert.deepEqual(handlesOf(null), []);

// saving keeps every other source setting, the last report and the other Threads options
const before = { report: { community: { ok: true } }, last_run: "2026-11-13T00:00:00Z", community: { subreddit: "malaysia", threads: { hours: 72, web: true } } };
const after = withThreads(before, ["halal", " halal ", "kosmetik"], ["@ali"]);
assert.deepEqual(after.community.threads, { hours: 72, web: true, queries: ["halal", "kosmetik"], accounts: ["ali"] });
assert.equal(after.community.subreddit, "malaysia");
assert.deepEqual(after.report, before.report);
assert.equal(after.last_run, before.last_run);
assert.deepEqual(withThreads(undefined, ["x y"], []).community.threads, { queries: ["x y"], accounts: [] });
assert.equal(before.community.threads.queries, undefined);          // the input is never changed
console.log("threadsKeywords: ok");
