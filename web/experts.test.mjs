/* Expert content (14 Nov 2026): the page's logic. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_EXPERTS, LOADS_PER_SWEEP, LOAD_COST, MAX_HANDLES, accountOf, canSearchAgain, chainParts, notInBrain, ownerStats, requestDiscovery, addCategory, addHandle, brainRow, cleanHandle, configOf, dismissSuggestion, keywordsFrom,
  patchCategory, readLoad, removeCategory, removeHandle, rowsFor, setAccountNames, slugOf, suggestionsFor, togglePlatform } from "./src/lib/experts.js";
import { watchIdea } from "./src/lib/watchIdea.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const base = () => configOf(undefined);

t("with nothing saved the page shows AI Expert and Halal Expert, and only AI Expert sends to the AI brain", () => {
  const cfg = base();
  assert.deepEqual(cfg.categories.map((c) => [c.id, c.name, c.brain]), [["ai", "AI Expert", true], ["halal", "Halal Expert", false]]);
  assert.deepEqual(configOf(DEFAULT_EXPERTS), cfg);
});
t("a handle is read from a name, an @name or a pasted profile link on any of the three platforms", () => {
  assert.equal(cleanHandle(" @some.one_1 "), "some.one_1");
  assert.equal(cleanHandle("https://www.threads.com/@some.one?igshid=1"), "some.one");
  assert.equal(cleanHandle("threads.net/@abc/post/123"), "abc");
  assert.equal(cleanHandle("https://www.instagram.com/abc/"), "abc");
  assert.equal(cleanHandle("https://m.facebook.com/halal.page/posts/9"), "halal.page");
  assert.equal(cleanHandle("two words"), "");
  assert.equal(cleanHandle(""), "");
});
t("registering: several platforms for one name, a second registration adds platforms instead of a second row", () => {
  let got = addHandle(base(), "ai", "@Expert", ["instagram", "threads"]);
  assert.deepEqual(got.cfg.categories[0].handles, [{ handle: "Expert", platforms: ["threads", "instagram"] }]);
  got = addHandle(got.cfg, "ai", "expert", ["facebook"]);
  assert.equal(got.merged, true);
  assert.deepEqual(got.cfg.categories[0].handles, [{ handle: "Expert", platforms: ["threads", "facebook", "instagram"] }]);
  assert.deepEqual(got.cfg.categories[1].handles, [], "another category is untouched");
  assert.equal(addHandle(base(), "ai", "bad name", ["threads"]).error, "handle");
  assert.equal(addHandle(base(), "ai", "ok", []).error, "platform");
  assert.equal(addHandle(base(), "ai", "ok", ["tiktok"]).error, "platform");
  let full = base();
  for (let i = 0; i < MAX_HANDLES; i++) full = addHandle(full, "ai", `h${i}`, ["threads"]).cfg;
  assert.equal(addHandle(full, "ai", "onemore", ["threads"]).error, "full");
  assert.ok(addHandle(full, "ai", "h3", ["instagram"]).cfg, "a platform for a name already there is not a new account");
});
t("a platform can be unticked but never the last one; removing the handle is its own action", () => {
  let cfg = addHandle(base(), "ai", "a", ["threads", "instagram"]).cfg;
  cfg = togglePlatform(cfg, "ai", "A", "threads");
  assert.deepEqual(cfg.categories[0].handles[0].platforms, ["instagram"]);
  assert.deepEqual(togglePlatform(cfg, "ai", "a", "instagram").categories[0].handles[0].platforms, ["instagram"]);
  assert.deepEqual(togglePlatform(cfg, "ai", "a", "facebook").categories[0].handles[0].platforms, ["facebook", "instagram"]);
  assert.deepEqual(removeHandle(cfg, "ai", "A").categories[0].handles, []);
});
t("categories: add (a fresh id, brain off), rename, niche, search words, brain switch, delete", () => {
  const got = addCategory(base(), "  Pakar Kosmetik ");
  assert.equal(got.id, "pakar-kosmetik");
  const c = got.cfg.categories[2];
  assert.deepEqual([c.name, c.brain, c.handles, c.keywords], ["Pakar Kosmetik", false, [], []]);
  assert.equal(addCategory(got.cfg, "pakar kosmetik").error, "exists");
  assert.equal(addCategory(base(), " ").error, "name");
  assert.equal(slugOf("AI", ["ai", "ai-2"]), "ai-3");
  let cfg = patchCategory(got.cfg, "pakar-kosmetik", { name: "Cosmetic Expert", niche: " safety ", keywords: "SCCS, sccs, MoS,\nNOAEL, a, b, c", brain: true });
  const p = cfg.categories[2];
  assert.deepEqual([p.id, p.name, p.niche, p.brain], ["pakar-kosmetik", "Cosmetic Expert", "safety", true], "the id never changes, so its posts stay with it");
  assert.deepEqual(p.keywords, ["SCCS", "MoS", "NOAEL", "a", "b"]);
  assert.deepEqual(keywordsFrom(""), []);
  cfg = removeCategory(cfg, "pakar-kosmetik");
  assert.deepEqual(cfg.categories.map((x) => x.id), ["ai", "halal"]);
});
t("accounts worth following: a name that is added or dismissed leaves the list at once, before any sweep", () => {
  const sug = { at: "2026-11-14T00:00:00Z", lists: { ai: [{ handle: "one", platform: "threads", why: "x" }, { handle: "Two", why: "y" }, { handle: "one" }, { handle: "" }], halal: [] } };
  let cfg = base();
  assert.deepEqual(suggestionsFor(sug, cfg, "ai").map((s) => s.handle), ["one", "Two"]);
  cfg = addHandle(cfg, "ai", "ONE", ["threads"]).cfg;
  assert.deepEqual(suggestionsFor(sug, cfg, "ai").map((s) => s.handle), ["Two"]);
  cfg = dismissSuggestion(cfg, "ai", "@two");
  assert.deepEqual(suggestionsFor(sug, cfg, "ai"), []);
  assert.deepEqual(cfg.categories[0].dismissed, ["two"]);
  assert.deepEqual(addHandle(cfg, "ai", "two", ["threads"]).cfg.categories[0].dismissed, [], "adding a dismissed name by hand forgives it");
  assert.deepEqual(suggestionsFor(undefined, cfg, "ai"), []);
  assert.deepEqual(suggestionsFor(sug, cfg, "gone"), []);
});
const ROWS = [
  { id: 1, section: "expert", relevant: true, title: "Agen AI", summary: "s", published_at: "2026-11-13T00:00:00Z", raw: { category: "ai", handle: "a", platform: "threads", original: "narrow tools" } },
  { id: 2, section: "expert", relevant: true, title: "Lama", summary: "s", published_at: "2026-11-10T00:00:00Z", dismissed: true, raw: { category: "ai", handle: "b", platform: "instagram" } },
  { id: 3, section: "expert", relevant: false, title: "holiday", raw: { category: "ai", handle: "a" } },
  { id: 4, section: "expert", relevant: true, title: "Halal", summary: "s", published_at: "2026-11-14T00:00:00Z", raw: { category: "halal", handle: "h", platform: "facebook" } },
  { id: 5, section: "threads", relevant: true, title: "not expert", raw: { category: "ai" } },
];
t("the feed of one category: newest first, no hidden markers, hidden rows only on request, search reads the original too", () => {
  assert.deepEqual(rowsFor(ROWS, "ai").map((r) => r.id), [1]);
  assert.deepEqual(rowsFor(ROWS, "ai", { hidden: true }).map((r) => r.id), [1, 2]);
  assert.deepEqual(rowsFor(ROWS, "halal").map((r) => r.id), [4]);
  assert.deepEqual(rowsFor(ROWS, "ai", { q: "NARROW" }).map((r) => r.id), [1]);
  assert.deepEqual(rowsFor(ROWS, "ai", { hidden: true, handle: "B" }).map((r) => r.id), [2]);
  assert.deepEqual(rowsFor(undefined, "ai"), []);
});
t("a sweep's load is counted in pages, as the sweep counts it, and over the budget is said, not hidden", () => {
  let cfg = base();
  for (let i = 0; i < 8; i++) cfg = addHandle(cfg, "ai", `h${i}`, ["threads", "facebook", "instagram"]).cfg;
  assert.deepEqual(readLoad(cfg), { loads: 72, accounts: 24, limit: LOADS_PER_SWEEP, over: true }, "8 x (1 + 1 + 7)");
  assert.equal(readLoad(base()).over, false);
  const twice = addHandle(addHandle(base(), "ai", "same", ["threads"]).cfg, "halal", "SAME", ["threads"]).cfg;
  assert.equal(readLoad(twice).loads, 1, "one account on one platform is read once, whoever lists it");
  const py = readFileSync(new URL("../backend/semasa/experts.py", import.meta.url), "utf8");
  assert.equal(Number(/^MAX_LOADS = (\d+)/m.exec(py)[1]), LOADS_PER_SWEEP, "the page's budget is the sweep's budget");
  assert.deepEqual(JSON.parse(/^LOAD_COST = (\{[^}]*\})/m.exec(py)[1]), LOAD_COST, "and the cost of each platform too");
});
t("an original post is shown part by part when it is a chain", () => {
  assert.deepEqual(chainParts("one\n\n— 2/3 —\n\ntwo\nlines\n\n— 3/3 —\n\nthree"), ["one", "two\nlines", "three"]);
  assert.deepEqual(chainParts("a single post\n\nwith a paragraph"), ["a single post\n\nwith a paragraph"]);
  assert.deepEqual(chainParts(""), []);
});
t("per owner: shown, hidden by Wan and judged off the niche are told apart", () => {
  const rows = [
    { section: "expert", relevant: true, raw: { category: "ai", handle: "dr.a", owner: "A" } },
    { section: "expert", relevant: true, dismissed: true, raw: { category: "ai", handle: "a", owner: "a" } },
    { section: "expert", relevant: false, raw: { category: "ai", handle: "a" } }, { section: "expert", relevant: false, raw: { category: "ai", handle: "a" } },
    { section: "expert", relevant: true, raw: { category: "halal", handle: "a" } }, { section: "threads", relevant: true, raw: { category: "ai", handle: "a" } },
  ];
  assert.deepEqual(ownerStats(rows, "ai"), { a: { shown: 1, hidden: 1, off: 2 } });
  assert.deepEqual(ownerStats(undefined, "ai"), {});
  assert.deepEqual(notInBrain([{ id: 1, section: "expert", relevant: true, raw: { category: "ai", handle: "a" } }, { id: 2, section: "expert", relevant: true, raw: { category: "ai", handle: "a", brain: true } },
    { id: 3, section: "expert", relevant: true, raw: { category: "ai", handle: "a" } }], "ai", new Set([3])).map((r) => r.id), [1]);
});
t("search again: the request is a time in the setting, at most once an hour, and it survives a save", () => {
  const NOW = Date.parse("2026-11-15T10:00:00Z");
  assert.deepEqual(canSearchAgain(base(), { at: "2026-11-15T08:00:00Z" }, NOW), { ok: true, waitMin: 0, pending: false });
  assert.deepEqual(canSearchAgain(base(), { at: "2026-11-15T09:30:00Z" }, NOW), { ok: false, waitMin: 30, pending: false }, "the sweep searched half an hour ago");
  const asked = requestDiscovery(base(), "2026-11-15T09:50:00.000Z");
  assert.deepEqual(canSearchAgain(asked, { at: "2026-11-15T08:00:00Z" }, NOW), { ok: false, waitMin: 50, pending: true }, "asked, not answered yet");
  assert.equal(canSearchAgain(asked, { at: "2026-11-15T09:55:00Z" }, NOW).pending, false, "answered");
  assert.equal(configOf(JSON.parse(JSON.stringify(asked))).discover_request, "2026-11-15T09:50:00.000Z");
  assert.equal(addHandle(asked, "ai", "x", ["threads"]).cfg.discover_request, "2026-11-15T09:50:00.000Z", "another change keeps the request");
  assert.equal("discover_request" in configOf({ discover_request: "nonsense" }), false);
  assert.deepEqual(canSearchAgain(base(), undefined, NOW), { ok: true, waitMin: 0, pending: false });
});
t("a post sent to the AI brain by hand is a reference carrying the expert's own words; as an idea it never names the account", () => {
  const row = { ...ROWS[0], url: "https://www.threads.com/@a/post/1", why: "w", raw: { ...ROWS[0].raw, category_name: "AI Expert" } };
  const b = brainRow(row);
  assert.deepEqual([b.hint, b.source_kind, b.url, b.title], ["reference", "text", row.url, "Agen AI"]);
  assert.match(b.body, /Original post:\nnarrow tools/);
  assert.match(b.note, /a reference only/);
  const idea = watchIdea(row, {});
  assert.match(idea.summary, /Catatan asal pakar \(rujukan sahaja\):\nnarrow tools/);
  assert.match(idea.summary, /jangan sebut nama akaun, platform atau pautannya/);
  assert.equal(idea.section, "expert");
});
t("the page and the migration agree on the defaults, and the page is wired into the menu", () => {
  const sql = readFileSync(new URL("../supabase/082_expert_content.sql", import.meta.url), "utf8");
  const json = JSON.parse(/values \('experts', '([\s\S]*?)'::jsonb\)/.exec(sql)[1]);
  assert.deepEqual(configOf(json), configOf(DEFAULT_EXPERTS));
  assert.match(sql, /'myra',\s*'expert'\)\)/);
  const py = readFileSync(new URL("../backend/semasa/experts.py", import.meta.url), "utf8");
  for (const c of DEFAULT_EXPERTS.categories) assert.ok(py.includes(`"id": "${c.id}", "name": "${c.name}", "brain": ${c.brain ? "True" : "False"}`), `${c.id} matches the sweep's default`);
  const page = readFileSync(new URL("./src/pages/ExpertTab.jsx", import.meta.url), "utf8");
  assert.ok(page.includes('save("experts"') && !page.includes('save("expert_suggestions"'), "the page never writes the sweep's own list");
});

t("one owner, a different username on each platform (Wan, 15 Nov 2026): kept per platform, merged on a second add, dropped with its platform", () => {
  let cfg = addHandle(base(), "ai", "aiman", ["threads", "instagram", "facebook"], { instagram: "@dr.aiman", facebook: "Aiman AI", threads: "AIMAN", tiktok: "x" }).cfg;
  const h = () => cfg.categories[0].handles[0];
  assert.deepEqual(h(), { handle: "aiman", platforms: ["threads", "facebook", "instagram"], names: { instagram: "dr.aiman" } }, "a name with a space, the main name itself and an unknown platform are not kept");
  assert.deepEqual(["threads", "instagram", "facebook"].map((p) => accountOf(h(), p)), ["aiman", "dr.aiman", "aiman"]);
  cfg = addHandle(cfg, "ai", "aiman", ["facebook"], { facebook: "aiman.fb" }).cfg;
  assert.deepEqual(h().names, { instagram: "dr.aiman", facebook: "aiman.fb" }, "adding the owner again adds to the owner, never a second row");
  assert.equal(cfg.categories[0].handles.length, 1);
  cfg = setAccountNames(cfg, "ai", "AIMAN", { instagram: "", threads: "ai_man" });
  assert.deepEqual(h().names, { facebook: "aiman.fb", threads: "ai_man" }, "empty means the same as the main name; several platforms change in one save");
  cfg = togglePlatform(cfg, "ai", "aiman", "facebook");
  assert.deepEqual(h().names, { threads: "ai_man" }, "unticking a platform takes its username with it");
  assert.deepEqual(configOf(JSON.parse(JSON.stringify(cfg))), cfg, "a saved setting reads back as it was");
  cfg = setAccountNames(cfg, "ai", "aiman", { threads: "" });
  assert.equal("names" in h(), false);
  assert.deepEqual(addHandle(base(), "ai", "x1", ["threads"], {}).cfg.categories[0].handles[0], { handle: "x1", platforms: ["threads"] }, "no names key when none differ");
});
t("a username of an owner keeps it off the suggestions, and the feed filters by owner", () => {
  const cfg = addHandle(base(), "ai", "aiman", ["instagram"], { instagram: "dr.aiman" }).cfg;
  const sug = { lists: { ai: [{ handle: "dr.aiman" }, { handle: "aiman" }, { handle: "fresh" }] } };
  assert.deepEqual(suggestionsFor(sug, cfg, "ai").map((s) => s.handle), ["fresh"]);
  const rows = [{ id: 1, section: "expert", relevant: true, raw: { category: "ai", handle: "dr.aiman", owner: "aiman", original: "x" } },
    { id: 2, section: "expert", relevant: true, raw: { category: "ai", handle: "other", owner: "other" } }];
  assert.deepEqual(rowsFor(rows, "ai", { handle: "AIMAN" }).map((r) => r.id), [1]);
  assert.deepEqual(rowsFor(rows, "ai", { q: "aiman" }).map((r) => r.id), [1]);
});
t("a chain is sent to the brain with its length said, and the post as a whole", () => {
  const b = brainRow({ title: "t", url: "u", summary: "s", raw: { handle: "a", platform: "threads", category_name: "AI", parts: 3, original: "one\n\n— 2/3 —\n\ntwo\n\n— 3/3 —\n\nthree" } });
  assert.match(b.body, /Original post \(a chain of 3 posts\):\none/);
  assert.match(b.body, /three/);
});

console.log(`experts.test.mjs: ${n} groups OK`);
