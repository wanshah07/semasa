import assert from "node:assert/strict";
import { CATEGORIES, CATEGORY_WORDS, canonicalUrl, categoriesOf, filterRows, flagsOf, groupByCategory, librarySummary, parseRepoUrl } from "./src/lib/repoLibrary.js";

assert.equal(parseRepoUrl("https://github.com/blixvip/MotionClone"), "blixvip/MotionClone");
assert.equal(parseRepoUrl(" https://github.com/debpalash/VoiceStudio.git "), "debpalash/VoiceStudio");
assert.equal(parseRepoUrl("https://github.com/heygen-com/hyperframes/tree/main/skills#x"), "heygen-com/hyperframes");
assert.equal(parseRepoUrl("http://skills.sh/"), null);
assert.equal(parseRepoUrl(""), null);
assert.equal(canonicalUrl("https://github.com/a/b.git/tree/x"), "https://github.com/a/b");
assert.equal(canonicalUrl("nope"), "");

assert.deepEqual(categoriesOf(null).slice(-1), ["lain"]);
assert.deepEqual(categoriesOf({ repo_library: { categories: ["lain", "Motion", "voice", "motion"] } }), ["motion", "voice", "lain"]);

const rows = [
  { id: 1, category: "motion", status: "done", safety: "safe", full_name: "a/motion", tags: ["gsap"], updated_at: "2026-10-23T01:00:00Z" },
  { id: 2, category: "motion", status: "pending", safety: "unknown", full_name: "b/clone", tags: [], updated_at: "2026-10-23T02:00:00Z" },
  { id: 3, category: "ghost", status: "done", safety: "avoid", full_name: "c/x", summary_en: "pipes to shell", updated_at: "2026-10-22T00:00:00Z" },
  { id: 4, category: "suara", status: "error", safety: "caution", full_name: "d/voice", tags: [], updated_at: "2026-10-21T00:00:00Z" },
];
const cats = categoriesOf(null);
const g = groupByCategory(rows, cats);
assert.deepEqual(g.map((x) => x.category), ["motion", "suara", "lain"], "an unknown category files under lain, groups follow the list's order");
assert.deepEqual(g[0].rows.map((r) => r.id), [2, 1], "newest first inside a group");
assert.deepEqual(filterRows(rows, { q: "GSAP" }).map((r) => r.id), [1]);
assert.deepEqual(filterRows(rows, { q: "shell" }).map((r) => r.id), [3]);
assert.deepEqual(filterRows(rows, { category: "motion" }).map((r) => r.id), [1, 2]);
assert.deepEqual(filterRows(rows, { safety: "avoid" }).map((r) => r.id), [3]);
assert.deepEqual(librarySummary(rows), { total: 4, done: 2, pending: 1, avoid: 1, caution: 1 });
assert.deepEqual(flagsOf({ safety_flags: [{ severity: "caution" }, { severity: "avoid" }, { severity: "safe" }] }).map((f) => f.severity), ["avoid", "caution", "safe"]);
assert.deepEqual(flagsOf(null), []);
assert.ok(CATEGORIES.length >= 20 && CATEGORIES.at(-1) === "lain", "the library takes every kind of function, not only video");
for (const c of CATEGORIES) assert.ok(Array.isArray(CATEGORY_WORDS[c]) && CATEGORY_WORDS[c].length === 2, `category ${c} has a BM and an EN word`);
for (const c of ["agen-ai", "mcp", "api", "dokumen", "keselamatan", "devops"]) assert.ok(CATEGORIES.includes(c), `${c} is offered`);
console.log("repoLibrary.test.mjs: ok");
