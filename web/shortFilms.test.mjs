// Short-film categories: the page reads the same built-in categories as the film scripts (rules/short_films.json), merges Wan's
// own over them the same way (backend/semasa/short_films.py library), and writes the settings value the scripts read.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const here = new URL(".", import.meta.url);
const read = (p) => readFileSync(new URL(p, here), "utf8");
const rules = JSON.parse(read("../rules/short_films.json"));
// Node needs an import attribute for JSON that Vite does not: inline the rules, as the other suites do
const dir = mkdtempSync(join(tmpdir(), "sfc-"));
writeFileSync(join(dir, "bi.js"), read("src/lib/bi.js"));
writeFileSync(join(dir, "shortFilms.js"), read("src/lib/shortFilms.js").replace(/^import RULES from .*$/m, `const RULES = ${JSON.stringify(rules)};`)
  .replace('from "./bi"', 'from "./bi.js"'));
const S = await import(pathToFileURL(join(dir, "shortFilms.js")).href);

// ---- the two built-in categories, as the file holds them
const lib = S.shortFilmLibrary(undefined);
assert.deepEqual(lib.categories.map((c) => c.id), ["kisah-keluarga-halal", "cats"]);
assert.deepEqual(S.BUILT_IN, ["kisah-keluarga-halal", "cats"]);
assert.equal(lib.defaultId, "cats");
const [family, cats] = lib.categories;
assert.ok(family.builtIn && cats.builtIn && !family.own && !cats.hidden);
assert.equal(family.voice.mode, "in_prompt");
assert.equal(family.workflow, "nexabot-film-api.yml");
assert.equal(family.scene_count, rules.categories[0].script.scenes.length);
assert.deepEqual(family.cast.map((p) => p.name), ["Hana", "Hassan"]);
assert.equal(cats.voice.mode, "narrator");
assert.equal(cats.voice.name, "Sulafat");
assert.equal(cats.workflow, "nexabot-cat-film.yml");
assert.equal(cats.scene_count, 4);
assert.deepEqual(cats.cast.map((p) => p.name), ["Comot", "Putih", "Belang"]);
assert.ok(cats.script && family.script, "both built-ins film their own hand-written script");
// every cat's look is in the hand-written sheet prompt word for word (the cast and the script cannot drift apart unseen)
for (const p of rules.categories[1].cast) assert.ok(rules.categories[1].script.sheet_prompt.includes(p.look), p.name);

// ---- Wan's own: added by id, always narrated, never replacing a built-in one
const rabbit = { id: "arnab-di-kebun", name: "Arnab di kebun", about: "Dua ekor arnab", setting: "kebun sayur di belakang rumah kampung",
  style: "Photorealistic video.", scene_count: 9, voice: { mode: "in_prompt", name: "Aoede", notes: "lembut" },
  cast: [{ name: "Tompok", look: "arnab putih gebu dengan tompok coklat di telinga kiri" }, { name: "Labu", look: "arnab kelabu kecil dengan ekor putih gebu" }] };
const mine = S.shortFilmLibrary({ categories: [rabbit, { ...rabbit, id: "cats", name: "Not the cats" }], hidden: ["cats"] });
assert.deepEqual(mine.categories.map((c) => c.id), ["kisah-keluarga-halal", "cats", "arnab-di-kebun"]);
assert.equal(mine.categories[1].name.bm, "Kucing (Comot, Putih dan Belang)", "a built-in category is never replaced");
assert.equal(mine.categories[1].hidden, true);
const own = mine.categories[2];
assert.ok(own.own && !own.builtIn && !own.script);
assert.equal(own.voice.mode, "narrator", "an own category is always narrated");
assert.equal(own.voice.name, "Aoede");
assert.equal(own.scene_count, rules.limits.scenes_max, "the scene count is held to the limits");
assert.equal(own.workflow, "nexabot-cat-film.yml");
assert.deepEqual(S.howToFilm(own), { workflow: "nexabot-cat-film.yml", inputs: "category = arnab-di-kebun, topic = …" });
assert.deepEqual(S.howToFilm(cats), { workflow: "nexabot-cat-film.yml", inputs: "category = cats" });

// a broken entry is left out whole: no look, a too-short look, two of one name, too many people, no place, a bad id
const bad = [{ ...rabbit, cast: [{ name: "Tompok", look: "" }] }, { ...rabbit, cast: [{ name: "Tompok", look: "putih" }] },
  { ...rabbit, cast: [rabbit.cast[0], { ...rabbit.cast[1], name: "tompok" }] },
  { ...rabbit, cast: Array.from({ length: rules.limits.cast + 1 }, (_, i) => ({ name: `K${i}`, look: "seekor kucing oren dengan dada putih" })) },
  { ...rabbit, setting: "" }, { ...rabbit, id: "Bad Id" }, { ...rabbit, name: "x".repeat(rules.limits.name + 1) }, null, "cats"];
for (const b of bad) assert.equal(S.shortFilmLibrary({ categories: [b] }).categories.length, 2, JSON.stringify(b)?.slice(0, 80));
// at most `own` of his
const many = Array.from({ length: rules.limits.own + 5 }, (_, i) => ({ ...rabbit, id: `arnab-${i}` }));
assert.equal(S.shortFilmLibrary({ categories: many }).categories.length, 2 + rules.limits.own);

// ---- writing the settings value
const v1 = S.withCategory(undefined, rabbit);
assert.equal(v1.categories.length, 1);
assert.equal(v1.categories[0].workflow, undefined, "the workflow is the file's rule, not stored");
assert.equal(S.withCategory(v1, { ...rabbit, id: "cats" }), null, "a built-in id is refused");
assert.equal(S.withCategory(v1, { ...rabbit, cast: [] }), null);
const v2 = S.withCategory(v1, { ...rabbit, about: "edited" });
assert.equal(v2.categories.length, 1);
assert.equal(v2.categories[0].about.bm, "edited");
const v3 = S.withHidden(S.withHidden(v2, "cats", true), "arnab-di-kebun", true);
assert.deepEqual(v3.hidden, ["cats", "arnab-di-kebun"]);
assert.deepEqual(S.withHidden(v3, "cats", false).hidden, ["arnab-di-kebun"]);
const v4 = S.withoutCategory(v3, "arnab-di-kebun");
assert.deepEqual(v4.categories, []);
assert.deepEqual(v4.hidden, ["cats"], "deleting his own category drops it from hidden too");
assert.equal(S.withoutCategory(v4, "cats").hidden.length, 1, "a built-in category is not removed by delete");

// ---- the form
assert.deepEqual(S.castFromText("Tompok: arnab putih\n\n  Labu : arnab kelabu  \nTanpa"), [
  { name: "Tompok", look: "arnab putih" }, { name: "Labu", look: "arnab kelabu" }, { name: "Tanpa", look: "" }]);
assert.equal(S.newId("Arnab di Kebun!", ["arnab-di-kebun"]), "arnab-di-kebun-2");
assert.equal(S.newId("Cats", S.BUILT_IN), "cats-2");
assert.equal(S.categoryProblem(rabbit), "");
assert.match(S.categoryProblem({ ...rabbit, name: "" }), /nama|name/i);
assert.match(S.categoryProblem({ ...rabbit, cast: [] }), /watak|character/i);
assert.match(S.categoryProblem({ ...rabbit, cast: [{ name: "Tompok", look: "putih" }] }), /Tompok/);
assert.match(S.categoryProblem({ ...rabbit, setting: "kebun" }), /tempat|place/i);
assert.match(S.categoryProblem({ ...rabbit, id: "cats" }), /terbina|built-in/i);

// ---- the page offers this card in the Motion part of Generate video, and the row it saves has its SQL file
const tab = read("src/pages/VideoTab.jsx");
assert.match(tab, /mode === "motion" && <ShortFilmCategories settings=\{settings\} saveSetting=\{saveSetting\}/);
assert.match(read("src/App.jsx"), /<VideoTab [^>]*\n?[^>]*settings=\{settings\} saveSetting=\{save\}/);
assert.match(read("../supabase/089_short_films.sql"), /'short_films'/);
const card = read("src/components/ShortFilmCategories.jsx");
assert.ok(card.includes('saveSetting("short_films"'));
assert.ok(!/\u2014/.test(card), "no em dash in what a person reads");

console.log("shortFilms.test.mjs: ok");
