import assert from "node:assert/strict";
import { DEFAULT_KEYWORDS, DEFAULT_TAGS, MAX_HANDLES, MAX_KEYWORDS, cleanHandles, cleanKeywords, handlesOf, keywordsOf, withPlatform, withThreads } from "./src/lib/threadsKeywords.js";

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

// Facebook and Instagram: hashtags, their own defaults, their own saved lists, and no accounts watchlist
assert.deepEqual(keywordsOf(undefined, "facebook"), DEFAULT_TAGS);
assert.deepEqual(keywordsOf({ community: { threads: { queries: ["x y"] } } }, "instagram"), DEFAULT_TAGS);          // another platform's list is not borrowed
assert.deepEqual(keywordsOf({ community: { instagram: { queries: ["halalmalaysia"] } } }, "instagram"), ["halalmalaysia"]);
const fb = withPlatform({ community: { threads: { queries: ["a b"], accounts: ["ali"] }, facebook: { hours: 72 } } }, "facebook", ["Halal Malaysia", "halal malaysia"], ["ignored"]);
assert.deepEqual(fb.community.facebook, { hours: 72, queries: ["Halal Malaysia"] });                              // no accounts key for Facebook
assert.deepEqual(fb.community.threads, { queries: ["a b"], accounts: ["ali"] });                                    // Threads untouched
assert.deepEqual(withThreads({}, ["x y"], ["@a"]).community.threads, { queries: ["x y"], accounts: ["a"] });
console.log("threadsKeywords: ok");
