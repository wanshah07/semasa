/* Expert content (14 Nov 2026): the page's logic. `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { DEFAULT_EXPERTS, MAX_HANDLES, READS_PER_SWEEP, addCategory, addHandle, brainRow, cleanHandle, configOf, dismissSuggestion, keywordsFrom, patchCategory,
  readLoad, removeCategory, removeHandle, rowsFor, slugOf, suggestionsFor, togglePlatform } from "./src/lib/experts.js";
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
t("more profile pages than one sweep opens is said, not hidden", () => {
  let cfg = base();
  for (let i = 0; i < 8; i++) cfg = addHandle(cfg, "ai", `h${i}`, ["threads", "facebook", "instagram"]).cfg;
  assert.deepEqual(readLoad(cfg), { reads: 24, limit: READS_PER_SWEEP, over: true });
  assert.equal(readLoad(base()).over, false);
  const py = readFileSync(new URL("../backend/semasa/experts.py", import.meta.url), "utf8");
  assert.equal(Number(/^MAX_READS = (\d+)/m.exec(py)[1]), READS_PER_SWEEP, "the page's number is the sweep's number");
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

console.log(`experts.test.mjs: ${n} groups OK`);
