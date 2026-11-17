// The daily comic series on the page (Wan, 17 Nov 2026): the settings the worker reads, the lane list in Wan's order, the series'
// episodes and where each one is, the worker's record of days, the button, and the comic storyboard in the Motion review.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const here = new URL(".", import.meta.url);
const read = (p) => readFileSync(new URL(p, here), "utf8");
const rules = JSON.parse(read("../rules/comic.json"));
const dir = mkdtempSync(join(tmpdir(), "cmd-"));
writeFileSync(join(dir, "comicDaily.js"), read("src/lib/comicDaily.js").replace(/^import RULES from .*$/m, `const RULES = ${JSON.stringify(rules)};`));
writeFileSync(join(dir, "motionReview.js"), read("src/lib/motionReview.js"));
const D = await import(pathToFileURL(join(dir, "comicDaily.js")).href);
const R = await import(pathToFileURL(join(dir, "motionReview.js")).href);

// ---- the file: the four lanes in Wan's order, the series exists, nobody is a mascot
assert.deepEqual(D.LANE_IDS, ["isu_semasa", "halal", "regulatori", "fatwa"]);
assert.deepEqual(rules.daily.lanes, D.LANE_IDS);
for (const l of D.LANES) assert.ok(l.name.bm && l.name.en && l.reads.bm && l.reads.en, l.id);
assert.ok(rules.series.some((s) => s.id === rules.daily.series));
assert.ok(!JSON.stringify(rules.daily).includes("—"), "no em dash in anything a person reads");

// ---- the settings: OFF unless exactly true, Wan's order, an empty list is no lane at all
assert.deepEqual(D.dailyConfig(undefined), { enabled: false, paused: false, lanes: D.LANE_IDS, at: "06:30", series: "isu-semasa-harian", wordsMode: "art", makeNow: "" });
assert.equal(D.dailyConfig({ enabled: "yes" }).enabled, false);
assert.equal(D.dailyConfig({ enabled: true, paused: true }).paused, true);
assert.deepEqual(D.dailyConfig({ lanes: ["fatwa", "nope", "halal", "fatwa"], at: "25:99" }).lanes, ["fatwa", "halal"]);
assert.equal(D.dailyConfig({ at: "25:99" }).at, "06:30");
assert.deepEqual(D.dailyConfig({ lanes: [] }).lanes, [], "no lane is no episode, never the default");
assert.equal(D.dailyConfig({ words_mode: "auto" }).wordsMode, "auto");
assert.equal(D.dailyConfig({ words_mode: "x" }).wordsMode, "art");

// ---- the lane list: moving and switching a lane on and off
assert.deepEqual(D.moveLane(["a", "b", "c"], "b", -1), ["b", "a", "c"]);
assert.deepEqual(D.moveLane(["a", "b", "c"], "a", -1), ["a", "b", "c"], "the first stays first");
assert.deepEqual(D.moveLane(["a", "b", "c"], "c", 1), ["a", "b", "c"], "the last stays last");
assert.deepEqual(D.moveLane(["a", "b"], "zz", 1), ["a", "b"]);
assert.deepEqual(D.toggleLane(["halal"], "fatwa"), ["halal", "fatwa"], "switched on at the end");
assert.deepEqual(D.toggleLane(["halal", "fatwa"], "halal"), ["fatwa"]);
assert.deepEqual(D.toggleLane(["halal"], "made-up"), ["halal"]);
const rows = D.laneRows(D.dailyConfig({ lanes: ["regulatori", "isu_semasa"] }));
assert.deepEqual(rows.map((r) => [r.id, r.on]), [["regulatori", true], ["isu_semasa", true], ["halal", false], ["fatwa", false]], "on lanes first, in his order");

// ---- saving keeps what is in the row, and the button writes a timestamp the worker has not answered
const kept = D.withConfig({ enabled: false, extra: 7, lanes: ["halal"] }, { enabled: true });
assert.equal(kept.enabled, true); assert.equal(kept.extra, 7); assert.deepEqual(kept.lanes, ["halal"]); assert.equal(kept.at, "06:30");
const pressed = D.withMakeNow({ enabled: false }, new Date("2026-11-17T01:00:00Z"));
assert.equal(pressed.make_now, "2026-11-17T01:00:00.000Z"); assert.equal(pressed.enabled, false, "the button does not switch the series on");

// ---- the Malaysian day, not the UTC one
assert.equal(D.mytDay(new Date("2026-11-16T16:30:00Z")), "2026-11-17");
assert.equal(D.mytDay(new Date("2026-11-16T15:59:00Z")), "2026-11-16");

// ---- the episodes: only the series' films, newest first, and where each one is
const film = (over) => ({ id: "m1", status: "review", stage: "storyboard", error: "", title: "", created_at: "2026-11-17T00:00:00Z", queued_post_id: null,
  options: { template: "comic", series: { id: "isu-semasa-harian", episode: 12, day: "2026-11-17", lane: "halal", source: "Buletin TV3, 17 Nov 2026" } },
  storyboard: { kind: "comic", sb: { title: "Sijil halal palsu", source: "Buletin TV3, 17 Nov 2026" } }, ...over });
const eps = D.episodesOf([film({}), { id: "x", options: { template: "story" } }, film({ id: "m0", created_at: "2026-11-16T00:00:00Z", status: "done", queued_post_id: "p1",
  options: { template: "comic", series: { episode: 11, day: "2026-11-16", lane: "isu_semasa" } }, video_url: "https://cdn/v.mp4" })]);
assert.deepEqual(eps.map((e) => e.id), ["m1", "m0"]); assert.equal(eps[0].title, "Sijil halal palsu"); assert.equal(eps[0].episode, 12);
assert.equal(D.todayOf(eps, new Date("2026-11-17T03:00:00Z")).id, "m1");
assert.equal(D.todayOf(D.episodesOf([film({ status: "rejected" })]), new Date("2026-11-17T03:00:00Z")), null, "a rejected storyboard is no episode");
assert.equal(D.todayOf(eps, new Date("2026-11-20T03:00:00Z")), null);
assert.match(D.statusWords(eps[0])[0], /menunggu kelulusan anda: tiada gambar dibayar/);
assert.match(D.statusWords(eps[0])[1], /waits for your approval/);
assert.equal(D.statusWords(eps[0])[2], "warn");
assert.match(D.statusWords(eps[1])[0], /draf post sudah dibuat/); assert.equal(D.statusWords(eps[1])[2], "ok");
assert.match(D.statusWords(D.episodesOf([film({ status: "done" })])[0])[1], /draft post is made on the next run/);
const failed = D.statusWords(D.episodesOf([film({ status: "error", error: "x" })])[0]);
assert.equal(failed[2], "danger"); assert.match(failed[1], /not drawn again/);

// ---- the worker's record of days: newest first, a skipped day keeps its reason; the button's answer
const state = { log: [{ day: "2026-11-15", status: "planned", lane: "halal", episode: 11 }, { day: "2026-11-16", status: "skipped", reason: "Fatwa: read 1, refused 1 no issuing body and date" }, { bad: true }],
  make_now_done: "2026-11-17T01:00:00.000Z", make_now_result: "planned" };
assert.deepEqual(D.logLines(state).map((x) => x.day), ["2026-11-16", "2026-11-15"]);
assert.match(D.logLines(state)[0].reason, /no issuing body and date/);
assert.deepEqual(D.logLines(undefined), []);
assert.equal(D.makeNowAnswer(D.dailyConfig({}), state), null, "no press, no answer");
assert.equal(D.makeNowAnswer(D.dailyConfig({ make_now: "2026-11-17T02:00:00.000Z" }), state).status, "waiting");
assert.deepEqual(D.makeNowAnswer(D.dailyConfig({ make_now: "2026-11-17T01:00:00.000Z" }), state), { status: "planned", reason: "" });

// ---- the storyboard in the Motion review: the title with its source, four panels, the words as "Name: words", edits go back in shape
const sb = { kind: "comic", note: "x", written_at: "2026-11-17T00:00:00+00:00", sb: { series_name: "Isu Semasa di Kedai", episode: 12, title: "Sijil halal palsu", source: "Buletin TV3",
  names: { A: "Pak Mat", B: "Hana" }, panels: [
    { scene: "Pak Mat reads a newspaper.", lines: [{ who: "A", text: "Ada berita sijil halal palsu." }] },
    { scene: "Hana answers.", lines: [{ who: "B", text: "Dua individu ditahan." }, { who: "A", text: "Jual apa?" }] },
    { scene: "x", lines: [{ who: "B", text: "Pewarna rambut." }] }, { scene: "y", lines: [{ who: "A", text: "Oh." }, { who: "B", text: "Itu yang dilaporkan." }] }] } };
const sc = R.scenesOf(sb);
assert.deepEqual(sc.map((x) => x.label), ["Tajuk", "Panel 1", "Panel 2", "Panel 3", "Panel 4"]);
assert.deepEqual(sc[0].lines, ["Siri Isu Semasa di Kedai · Episod 12", "Sumber: Buletin TV3"]);
assert.equal(sc[0].edit.lines, false, "the source line is shown and never editable");
assert.deepEqual(sc[2].lines, ["Hana: Dua individu ditahan.", "Pak Mat: Jual apa?"]);
assert.equal(sc[1].shot, "Pak Mat reads a newspaper."); assert.equal(sc[1].edit.shot, true);
const edited = R.withEdits(sb, { title: { heading: "Sijil halal palsu: apa dilaporkan?", lines: "hack" }, c1: { lines: "Hana: Dua individu ditahan semalam.\nJual apa tu?\n\n", shot: "Hana points." }, c0: { heading: "nope" } });
assert.equal(edited.sb.title, "Sijil halal palsu: apa dilaporkan?"); assert.equal(edited.sb.source, "Buletin TV3");
assert.deepEqual(edited.sb.panels[1].lines, [{ who: "B", text: "Dua individu ditahan semalam." }, { who: "A", text: "Jual apa tu?" }], "a name sets the speaker; a line with none keeps the bubble's own");
assert.equal(edited.sb.panels[1].scene, "Hana points."); assert.deepEqual(edited.sb.panels[0], sb.sb.panels[0], "an untouched panel is kept exactly");
assert.deepEqual(R.comicLines(["Hana: a", "b"], [], { A: "Pak Mat", B: "Hana" }), [{ who: "B", text: "a" }, { who: "B", text: "b" }].map((x, i) => (i === 1 ? { who: "B", text: "b" } : x)));
assert.equal(R.changed(sb, {}), false); assert.equal(R.changed(sb, { c2: { lines: "Hana: Pewarna." } }), true);

console.log("comicDaily.test.mjs ok");
