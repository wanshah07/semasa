// Comic as a Design choice: the page reads the same styles and series as the worker (rules/comic.json), merges Wan's own over
// them the same way, judges a typed script by the same rules, and builds the job the worker expects.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const here = new URL(".", import.meta.url);
const read = (p) => readFileSync(new URL(p, here), "utf8");
const rules = JSON.parse(read("../rules/comic.json"));
// Node needs an import attribute for JSON that Vite does not: inline the rules, as the other suites do
const dir = mkdtempSync(join(tmpdir(), "cmc-"));
writeFileSync(join(dir, "compliance.js"), read("src/lib/compliance.js").replace(/^import RULES from .*$/m, `const RULES = ${read("../rules/compliance.json")};`));
writeFileSync(join(dir, "bi.js"), read("src/lib/bi.js"));
writeFileSync(join(dir, "comic.js"), read("src/lib/comic.js").replace(/^import RULES from .*$/m, `const RULES = ${JSON.stringify(rules)};`)
  .replace('from "./bi"', 'from "./bi.js"').replace('from "./compliance"', 'from "./compliance.js"'));
const C = await import(pathToFileURL(join(dir, "comic.js")).href);

// ---- the library: the file's styles and series, with Wan's merged over them by id
const lib = C.comicLibrary(undefined);
assert.equal(lib.styles.length, rules.styles.length);
assert.ok(lib.styles.length >= 6 && lib.styles.length <= 8);
assert.deepEqual(lib.styles.map((s) => s.id), rules.styles.map((s) => s.id));
assert.equal(lib.defaultStyle, "moden-bersih");
assert.equal(lib.defaultSeries, rules.series[0].id);
for (const s of lib.styles) { assert.ok(s.name.bm && s.name.en && s.about.bm && s.about.en, s.id); assert.equal(s.prompt, rules.styles.find((x) => x.id === s.id).prompt); }
for (const s of lib.series) for (const who of ["A", "B"]) assert.equal(s.cast[who].look, rules.series.find((x) => x.id === s.id).cast[who].look);

const ownStyle = { id: "", name: "Pensel kasar", about: "Lakaran pensel.", prompt: "Rough graphite pencil sketch on cream paper, heavy cross hatching, no colour at all, tall thin people.", lettering: "Hand-written pencil capitals." };
ownStyle.id = C.newId(ownStyle.name, lib.styles.map((s) => s.id));
assert.equal(ownStyle.id, "pensel-kasar");
assert.equal(C.newId("Moden bersih", ["moden-bersih"]), "moden-bersih-2");
assert.equal(C.newId("!!!", []), "komik");
let value = C.withEntry(undefined, "styles", ownStyle);
assert.deepEqual(value.styles.map((s) => s.id), ["pensel-kasar"]);
value = C.withEntry(value, "styles", { ...rules.styles[1], prompt: "A different newspaper look, written by Wan, with thick lines everywhere." });
const merged = C.comicLibrary(value);
assert.equal(merged.styles.length, rules.styles.length + 1);
assert.equal(merged.styles[1].edited, true);
assert.ok(merged.styles[1].prompt.startsWith("A different newspaper look"));
assert.equal(merged.styles.at(-1).own, true);
assert.deepEqual(merged.styles.at(-1).name, { bm: "Pensel kasar", en: "Pensel kasar" });
// saving a style keeps the series Wan already has, and the other way round
const ownSeries = { ...structuredClone(rules.series[0]), id: "kedai-runcit", name: "Kedai Runcit Pak Mat" };
value = C.withEntry(value, "series", ownSeries);
assert.equal(value.styles.length, 2);
assert.equal(C.comicLibrary(value).series.at(-1).id, "kedai-runcit");
// putting a built-in one back, and deleting his own
value = C.withoutEntry(value, "styles", rules.styles[1].id);
assert.equal(C.comicLibrary(value).styles[1].prompt, rules.styles[1].prompt);
assert.equal(C.comicLibrary(C.withoutEntry(value, "series", "kedai-runcit")).series.length, rules.series.length);
// an entry that is not whole is refused, and the page says why
assert.equal(C.withEntry(value, "styles", { ...ownStyle, prompt: "too short" }), null);
assert.equal(C.withEntry(value, "series", { id: "x1", name: "X", cast: { A: { name: "A", look: "short" } } }), null);
assert.match(C.entryProblem("styles", { ...ownStyle, prompt: "too short" }), /Terangkan gaya/);
assert.match(C.entryProblem("series", { ...ownSeries, cast: { ...ownSeries.cast, B: { ...ownSeries.cast.B, look: "tall" } } }), /watak B/);
assert.equal(C.entryProblem("styles", ownStyle), "");
assert.equal(C.entryProblem("series", ownSeries), "");
assert.equal(C.cleanStyle({ ...ownStyle, prompt: "x ".repeat(2000) }), null);
assert.deepEqual(C.comicLibrary("rubbish"), lib);

// ---- the script as typed
const script = C.blankScript();
assert.equal(script.panels.length, 4);
assert.match(C.scriptProblem(script), /tajuk/);
script.title = "Logo halal bukan *hijau*. Palsu ke?";
assert.match(C.scriptProblem(script), /Panel 1/);
const words = [["A", "Eh, logo halal kat paket ni warna hitam. Bukan sepatutnya hijau ke?"], ["A", "Jangan-jangan logo palsu?", "Tak semestinya. Warna bukan penentu."],
  ["B", "Pemegang sijil boleh cetak logo ikut warna pembungkusan, asalkan spesifikasi logo tak diubah."], ["A", "Mana tulis tu?", "MPPHM (Domestik) 2020, Klausa 40(2)."]];
words.forEach(([who, first, second], i) => { script.panels[i].lines = [{ who, text: first }, { who: who === "A" ? "B" : "A", text: second || "" }]; });
assert.equal(C.scriptProblem(script), "");
const tidy = C.tidyScript(script);
assert.equal(tidy.title, "Logo halal bukan hijau. Palsu ke?");          // no emphasis marks in a comic
assert.deepEqual(tidy.panels.map((p) => p.lines.length), [1, 2, 1, 2]);   // an empty second bubble is no bubble
assert.deepEqual(C.formScript(tidy).panels.map((p) => p.lines.length), [2, 2, 2, 2]);
assert.equal(C.formScript(tidy).panels[2].lines[1].who, "A");
assert.deepEqual(C.scriptFlags(script, "regulab", "MPPHM (Domestik) 2020, Klausa 40(2)"), []);
const long = structuredClone(script); long.panels[0].lines[0].text = "kata ".repeat(30);
assert.match(C.scriptProblem(long), /Panel 1.*aksara/);
const twice = structuredClone(script); twice.panels[1].lines[1].who = "A";
assert.match(C.scriptProblem(twice), /sekali sahaja/);
assert.match(C.scriptProblem({ ...script, title: "t".repeat(rules.limits.title + 1) }), /Tajuk/);
// the post rules, on the title and on each bubble by name
const cta = structuredClone(script); cta.panels[3].lines[1].text = "Hubungi kami untuk semakan percuma.";
const found = C.scriptFlags(cta, "regulab");
assert.ok(found.some((f) => f.hard && f.where === "Comic panel 4"), JSON.stringify(found));
assert.ok(C.scriptFlags({ ...script, title: "Hubungi kami untuk tahu lagi" }, "regulab").some((f) => f.where === "Comic title"));
// a panel still empty does not shift the names of the ones after it
const partial = C.blankScript(); partial.title = "Tajuk"; partial.panels[2].lines[0].text = "Klik link di bio sekarang.";
assert.deepEqual(C.scriptFlags(partial, "regulab").filter((f) => f.hard).map((f) => f.where), ["Comic panel 3"]);
assert.deepEqual(C.scriptFlags(C.blankScript(), "regulab"), []);
// vague wording, pinned down or not, in reading order
const vague = structuredClone(script); vague.panels[3].lines[1].text = "Ada beberapa syarat penting yang perlu dipatuhi.";
assert.ok(C.scriptFlags(vague, "regulab").some((f) => f.hard && /^vague/.test(f.msg)));
const pinned = structuredClone(script); pinned.panels[2].lines[0].text = "Ada beberapa syarat dalam klausa itu.";
assert.ok(!C.scriptFlags(pinned, "regulab").some((f) => /^vague/.test(f.msg)));
// LinkedIn is English, and the source is judged like any artwork's source line
assert.ok(C.scriptFlags({ ...script, title: "Produk yang tidak boleh dijual kerana anda tidak ada sijil untuk produk dengan logo" }, "linkedin").some((f) => /LinkedIn stream is English/.test(f.msg)));
assert.ok(C.scriptFlags(script, "regulab", "www.kkmhalalconsultant.com").some((f) => f.where === "Source" && f.hard));
assert.equal(C.sourceLine("JAKIM, MPPHM 2020", "regulab"), "Sumber: JAKIM, MPPHM 2020");
assert.equal(C.sourceLine("JAKIM, MPPHM 2020", "linkedin"), "Source: JAKIM, MPPHM 2020");
assert.equal(C.sourceLine("Sumber: JAKIM", "linkedin"), "Sumber: JAKIM");
assert.deepEqual(C.scriptArtwork(script)[2], { title: "", points: ["Jangan-jangan logo palsu?", "Tak semestinya. Warna bukan penentu."] });

// ---- episodes
const done = (id, series, episode, status = "done") => ({ id, status, meta: { design: "comic", comic: { series, episode } } });
const rows = [done("a", "kak-lin-tanya", 1), done("b", "kak-lin-tanya", 2), done("c", "kak-lin-tanya", 3), done("d", "nota-makmal", 9),
  done("e", "kak-lin-tanya", 7, "error"), done("f", "kak-lin-tanya", null), { id: "g", status: "done", meta: { design: "poster" } }];
assert.equal(C.nextEpisode(rows, "kak-lin-tanya"), 4);
assert.equal(C.nextEpisode(rows, "nota-makmal"), 10);
assert.equal(C.nextEpisode(rows, "siri-baharu"), 1);
assert.equal(C.nextEpisode([done("a", "s1", 1), done("c", "s1", 3)], "s1"), 4);     // a deleted episode's number is not reused
assert.equal(C.nextEpisode(null, "s1"), 1);
assert.equal(C.episodeLine("Kak Lin Tanya", 4), "Siri Kak Lin Tanya · Episod 4");
assert.equal(C.episodeLine("Kak Lin Tanya", 4, "en"), "Kak Lin Tanya · Episode 4");

// ---- the job the worker expects
const series = lib.series[0], style = lib.styles[3];
const own = C.comicMeta({ stream: "regulab", series, style, source: " MPPHM  2020 ", script, wordsMode: "art", episode: "12" });
assert.equal(own.design, "comic"); assert.equal(own.flow, "design"); assert.equal(own.citation, "MPPHM 2020");
assert.deepEqual([own.comic.series, own.comic.style, own.comic.words_mode, own.comic.episode], ["kak-lin-tanya", style.id, "art", 12]);
assert.deepEqual(own.comic.script, tidy);
assert.equal(own.comic.series_copy.cast.A.look, series.cast.A.look);     // a copy rides along in case the series is deleted later
assert.equal(own.comic.style_copy.prompt, style.prompt);
assert.ok(!("brief" in own) && !("review" in own.comic) && own.slides.length === 5);
const ai = C.comicMeta({ stream: "linkedin", series, style, brief: "  an idea  ", review: true, episode: "0" });
assert.deepEqual([ai.brief, ai.comic.review, ai.comic.words_mode, "script" in ai.comic, "episode" in ai.comic], ["an idea", true, "auto", false, false]);
assert.equal(C.comicMeta({ stream: "regulab", series, style, brief: "x", review: false }).comic.review, false);

// ---- a script waiting for Wan, then sent back with his edit
const waiting = { id: "w", status: "done", generated_media_url: null, meta: { ...ai, comic: { ...ai.comic, stage: "script", script: tidy, episode: 3, revise: { note: "x" } } } };
assert.equal(C.comicStage(waiting), "script");
assert.equal(C.comicStage({ ...waiting, status: "processing" }), "working");
assert.equal(C.comicStage({ ...waiting, status: "error" }), "error");
assert.equal(C.comicStage({ ...waiting, generated_media_url: "https://x/y.jpg", meta: { ...waiting.meta, comic: { ...waiting.meta.comic, stage: "done" } } }), "done");
const edited = structuredClone(script); edited.panels[0].lines[0].text = "Eh, logo halal ni hitam. Betul ke?";
const back = C.redrawMeta(waiting.meta, edited);
assert.equal(back.comic.stage, "draw"); assert.equal(back.comic.episode, 3); assert.ok(!("revise" in back.comic));
assert.equal(back.comic.script.panels[0].lines[0].text, "Eh, logo halal ni hitam. Betul ke?");
assert.equal(back.slides[1].points[0], "Eh, logo halal ni hitam. Betul ke?");
assert.equal(back.brief, "an idea");

// ---- what the card says about the words
assert.equal(C.wordsNote(null), null);
assert.equal(C.wordsNote({ path: "" }), null);
const checked = C.wordsNote({ path: "full", checked: true, draws: 1 });
assert.equal(checked.tone, "ok"); assert.match(checked.bm, /disemak/); assert.match(checked.en, /checked/);
assert.match(C.wordsNote({ path: "full", checked: true, draws: 2 }).en, /drawn 2 times/);
const fell = C.wordsNote({ path: "art", why: "the picture maker's words differed from the script twice (panel 4: ...)", draws: 3 });
assert.equal(fell.tone, "warn"); assert.match(fell.bm, /dicetak oleh Semasa/); assert.match(fell.en, /differed from the script twice/);
assert.match(C.wordsNote({ path: "art", why: "no picture reader is available, so ..." }).bm, /tiada pembaca gambar/);
assert.equal(C.wordsNote({ path: "art", why: "Semasa was asked to print the words itself" }).tone, "ok");
// every sentence is in one language only
for (const n of [checked, fell]) { assert.ok(!/\b(the|was|checked)\b/.test(n.bm), n.bm); assert.ok(!/\b(dan|yang|oleh)\b/.test(n.en), n.en); }

// ---- the page offers it
const tab = read("src/pages/DesignTab.jsx");
assert.match(tab, /\["comic", t\("Komik", "Comic"\)\]/);
assert.match(tab, /design === "comic" && <ComicMaker/);
const maker = read("src/components/ComicMaker.jsx");
assert.ok(!/\u2014/.test(maker) && !/\u2014/.test(read("src/lib/comic.js")), "no em dash in anything a person reads");
assert.match(maker, /supabase\/085_comic\.sql/);
console.log("comic: ok");
