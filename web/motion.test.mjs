import assert from "node:assert/strict";
import { FORMAT_WORDS, LANGUAGES, defaultLanguage, formOf, formatOf, freshUrl, motionDefaults, motionFromIdea, motionFromPost, motionVariantMatches, startFields, STATUS_WORDS, STAGES, motionTrack, plannedShots, stageSteps, withDefaults, RESOLUTIONS, SECONDS, checkItems, clampSeconds, fmtBytes, motionLabel, motionRepoRow, motionRow, styleRepos } from "./src/lib/motion.js";

assert.equal(clampSeconds("abc"), SECONDS.default);
assert.equal(clampSeconds(1), SECONDS.min);
assert.equal(clampSeconds(999), SECONDS.max);
assert.equal(clampSeconds("14.6"), 30);

assert.deepEqual(motionRow({}), { error: "empty" });
assert.deepEqual(motionRow({ url: "github.com/x" }), { error: "url" });
const ok = motionRow({ brief: "  PFAS  ", url: "", stream: "linkedin", resolution: "square", seconds: "20" }, "u1");
assert.deepEqual(ok.row, { brief: "PFAS", source_url: "", stream: "linkedin", language: "en", resolution: "square", seconds: 30, status: "pending", options: { style: "bright-education", mode: "auto", design: "auto", ambient: "mint", effects:["B04"], effect_mode:"auto", asset_mode:"auto", assets:[], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true} }, style_repo_id: null, ai_background: false, created_by: "u1", voice: "auto", mascot: "" });
// the voice: Wan can choose it or turn it off
assert.equal(motionRow({ brief: "x", voice: "female" }).row.voice, "female");
assert.equal(motionRow({ brief: "x", voice: "nope" }).row.voice, "auto");
assert.equal(motionRow({ brief: "x", mascot: true }).row.mascot, "", "no talking mascot in any video (Wan, 25 Oct 2026)");
// the words on screen: the row's choice, else the stream's own language
assert.equal(motionRow({ brief: "x", stream: "regulab", language: "both" }).row.language, "both");
assert.equal(motionRow({ brief: "x", stream: "regulab", language: "nope" }).row.language, "en");
assert.equal(motionRow({ brief: "x", stream: "linkedin" }).row.language, "en");
assert.deepEqual(LANGUAGES.map(([k]) => k), ["bm", "en", "both"]);
assert.equal(defaultLanguage("linkedin"), "en"); assert.equal(defaultLanguage("regulab"), "en");
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
assert.equal(ok.row.style_repo_id, null);
assert.equal(motionRow({ brief: "x", aiBackground: true }).row.ai_background, true);
assert.equal(motionRow({ brief: "x", styleRepoId: "r1" }).row.style_repo_id, "r1");

const lib = [
  { id: "a", name: "zeta", full_name: "z/zeta", category: "motion", category_by: "bot", status: "done" },
  { id: "b", name: "alpha", full_name: "a/alpha", category: "motion", category_by: "wan", status: "pending" },
  { id: "c", name: "voice", category: "suara", status: "done" },
  { id: "d", name: "dead", category: "motion", status: "error" },
];
assert.deepEqual(styleRepos(lib).map((r) => r.id), ["b", "a"], "Wan's own filing first, then by name; errors and other categories out");
assert.deepEqual(styleRepos(null), []);
assert.deepEqual(motionRepoRow("https://github.com/heygen-com/hyperframes/tree/main", "u1"),
  { url: "https://github.com/heygen-com/hyperframes", full_name: "heygen-com/hyperframes", note: "motion style", category: "motion", category_by: "wan", status: "pending", created_by: "u1" });
assert.equal(motionRepoRow("skills.sh"), null);
const idea = { id: "i1", source_title: "NPRA batalkan 12 produk", note: "tekankan label", source_summary: "Ringkasan.", source_url: "https://npra.gov.my/x", stream: "regulab" };
assert.deepEqual(motionFromIdea(idea, "u1"), { brief: "NPRA batalkan 12 produk\nWan: tekankan label\nRingkasan.", source_url: "https://npra.gov.my/x", stream: "regulab", language: "en", resolution: "portrait", seconds: 30, status: "waiting", idea_id: "i1", ai_background: false, options: { style: "bright-education", mode: "auto", design: "auto", ambient: "mint", effects:["B04"], effect_mode:"auto", asset_mode:"auto", assets:[], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true}, evidence: {source_url: idea.source_url, source_title: idea.source_title, source_summary: idea.source_summary, id: idea.id} }, style_repo_id: null, voice: "auto", mascot: "", created_by: "u1" });
// the saved defaults ("the skill") apply to an idea and to a post
const saved = withDefaults({ prompt: "P" }, { language: "en", voice: "female", resolution: "square", seconds: "25", aiBackground: true, styleRepoId: "r9" });
assert.deepEqual(saved, { prompt: "P", defaults: { effects:["B04"], effectMode:"auto", assetMode:"auto", language: "en", voice: "female", design: "auto", ambient: "mint", previewMusic: "user-reel", style: "bright-education", mode: "auto", resolution: "square", seconds: 30, aiBackground: true, styleRepoId: "r9" } });
const dflts = motionDefaults({ motion: saved });
const fromIdea = motionFromIdea(idea, "u1", dflts);
assert.deepEqual([fromIdea.language, fromIdea.voice, fromIdea.mascot, fromIdea.resolution, fromIdea.seconds, fromIdea.ai_background, fromIdea.style_repo_id], ["en", "female", "", "square", 30, true, "r9"]);
assert.equal(motionFromIdea({ id: "i3", source_title: "T", stream: "linkedin" }, null, motionDefaults({})).language, "en", "no saved language: the stream's own");
assert.equal(motionFromPost({ lang: "bm", text: { bm: { facebook: "K" } } }, null, dflts).language, "en");
assert.equal(motionDefaults(null).voice, "auto");
assert.equal(freshUrl("https://x/a.mp4", "2026-10-24T05:00:00Z"), "https://x/a.mp4?v=2026-10-24T05%3A00%3A00Z");
assert.equal(freshUrl("", "x"), "");
assert.equal(motionFromIdea({ id: "i2", source_title: "T", stream: "linkedin", source_url: "not a url" }).stream, "linkedin");
assert.equal(motionFromIdea({ id: "i2", source_title: "T", source_url: "not a url" }).source_url, "");
assert.equal(motionFromIdea({ id: "i3" }), null);
assert.equal(motionFromIdea({ id: "i4", source_title: "x".repeat(3000) }).brief.length, 1900);
console.log("motion.test.mjs: ok");

// a post draft: slides first, else the caption in the post's own language
const post = { lang: "bm", stream: "regulab", idea_id: "i9", slides: [{ title: "Tiga perkara", points: ["Satu", "Dua"] }, { title: "Penutup" }], text: { bm: { facebook: "Kapsyen" } } };
assert.deepEqual(motionFromPost(post, "u1"), { brief: "Tiga perkara\n- Satu\n- Dua\n\nPenutup", source_url: "", stream: "regulab", language: "en", resolution: "portrait", seconds: 30, status: "waiting", idea_id: "i9", ai_background: false, options: { style: "bright-education", mode: "auto", design: "auto", ambient: "mint", effects:["B04"], effect_mode:"auto", asset_mode:"auto", assets:[], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true}, evidence: {idea_id:"i9"} }, style_repo_id: null, voice: "auto", mascot: "", created_by: "u1" });
assert.equal(motionFromPost({ lang: "en", stream: "linkedin", text: { en: { linkedin: "Words" } } }).brief, "Words");
assert.equal(motionFromPost({ lang: "en", stream: "linkedin", text: { en: { linkedin: "Words" } } }).language, "en");
assert.equal(motionFromPost({ lang: "bm", text: {} }), null);
// the direction chosen on the idea or the draft itself wins over the saved default and the stream
assert.equal(motionFromIdea(idea, "u1", dflts, "bm").language, "bm");
assert.equal(motionFromIdea(idea, "u1", null, "en").language, "en");
assert.equal(motionFromPost(post, "u1", null, "both").language, "both");
assert.equal(motionFromPost(post, "u1", null, "nope").language, "en", "an unknown choice falls back to current English defaults");

// the queue (Wan, 26 Oct 2026): an idea or a draft waits for its styles to be chosen; the worker only claims 'pending'
assert.equal(motionFromIdea(idea, "u1").status, "waiting");
assert.equal(motionFromPost(post, "u1").status, "waiting");
assert.equal(motionRow({ brief: "x" }).row.status, "pending", "the form's own button still starts the video at once");
assert.deepEqual(STATUS_WORDS.waiting, ["Pilih gaya", "Choose styles"]);
const waiting = { ...motionFromIdea(idea, "u1"), id: "m1" };
assert.ok(motionVariantMatches(waiting, motionFromIdea(idea, "u1", { language: "bm" })), "a waiting row is the idea's video, whatever it is set to so far");
assert.ok(!motionVariantMatches({ ...waiting, idea_id: "other" }, motionFromIdea(idea, "u1")));
const form = formOf(waiting);
assert.deepEqual([form.language, form.voice, form.mode, form.seconds, form.design, form.effectMode], ["en", "auto", "auto", 30, "auto", "auto"]);
const go = startFields(waiting, { ...form, language: "bm", voice: "male", design: "continuous-line", effectMode: "manual", effects: ["V04", "H02", "ZZZ"] });
assert.equal(go.status, "pending"); assert.equal(go.attempts, 0); assert.equal(go.error, "");
assert.deepEqual([go.language, go.voice], ["bm", "male"]);
assert.equal(go.options.design, "continuous-line"); assert.equal(go.options.effect_mode, "manual");
assert.deepEqual(go.options.effects, ["V04", "H02"], "an unknown style id never reaches the worker");
assert.deepEqual(go.options.evidence, waiting.options.evidence, "the idea's evidence rides along");
assert.equal(startFields(waiting, { ...form, language: "bm", voice: "kitten" }).voice, "female", "Kitten is English only");
assert.equal(startFields(waiting, { ...form, mode: "teaser", seconds: 10 }).seconds, 10);
assert.equal(startFields({ ...waiting, stream: "linkedin" }, form).language, "en");
// the four approved formats, as the worker (motion.format_of) names them
assert.equal(formatOf({ mode: "teaser", seconds: 10, language: "bm" }), "gimmick");
assert.equal(formatOf({ mode: "explainer", seconds: 30, design: "continuous-line", language: "en" }), "preview");
assert.equal(formatOf({ mode: "explainer", seconds: 30, design: "bright-editorial", language: "both" }), "malay");
assert.equal(formatOf({ mode: "explainer", seconds: 30, design: "bright-editorial", language: "en" }), "english");
assert.deepEqual(Object.keys(FORMAT_WORDS).sort(), ["english", "gimmick", "malay", "preview"]);
console.log("motion queue: waiting rows, start fields and formats ok");

// the ambient colour behind every scene is Wan's choice, mint by default (26 Oct 2026)
import { AMBIENTS, ambientOf, motionRow as motionRow2, formOf as formOf2, startFields as startFields2 } from "./src/lib/motion.js";
assert.deepEqual(AMBIENTS.map(a => a[0]), ["mint", "lime", "cream", "sky", "blush"]);
assert.equal(ambientOf("lime"), "lime"); assert.equal(ambientOf("nonsense"), "mint"); assert.equal(ambientOf(undefined), "mint");
assert.equal(motionRow2({ brief: "x y" }).row.options.ambient, "mint");
assert.equal(motionRow2({ brief: "x y", ambient: "sky" }).row.options.ambient, "sky");
assert.equal(formOf2({ options: { ambient: "cream" } }).ambient, "cream");
assert.equal(startFields2({ stream: "regulab" }, { ...formOf2({ options: {} }), ambient: "blush" }).options.ambient, "blush");
console.log("motion ambient colour: ok");

/* the format follows the platform; a film is remade in another language in its platform's size (Wan, 26 Oct 2026) */
import { RESOLUTION_CHOICES, derivedSize, formSize, remakeFields, RESOLUTIONS as RES2 } from "./src/lib/motion.js";
assert.deepEqual(Object.keys(RESOLUTION_CHOICES), ["auto", "portrait", "square", "landscape"], "automatic first");
assert.equal(formSize("auto", "regulab"), "portrait"); assert.equal(formSize("auto", "linkedin"), "square");
assert.equal(formSize("landscape", "linkedin"), "landscape", "an explicit choice in the form stands");
assert.equal(formSize("portrait", "linkedin"), "portrait");
assert.equal(derivedSize("portrait", "linkedin"), "square", "the old saved default follows the platform");
assert.equal(derivedSize("landscape", "regulab"), "landscape", "a saved explicit choice is kept");
assert.equal(derivedSize(undefined, "linkedin"), "square");
assert.equal(motionRow({ brief: "x", stream: "linkedin" }).row.resolution, "square");
assert.equal(motionRow({ brief: "x", stream: "regulab", resolution: "auto" }).row.resolution, "portrait");
const li = motionFromIdea({ id: "i2", stream: "linkedin", source_title: "ISO 24444", source_summary: "SPF in vivo" }, "u1");
assert.equal(li.stream, "linkedin"); assert.equal(li.resolution, "square"); assert.equal(li.language, "en");
assert.equal(motionDefaults({ motion: { defaults: { resolution: "portrait" } } }).resolution, "auto", "the old default means automatic now");
assert.equal(motionDefaults({ motion: { defaults: { resolution: "square" } } }).resolution, "square");
const mk = remakeFields({ stream: "linkedin", voice: "kitten" }, "bm");
assert.deepEqual([mk.status, mk.attempts, mk.language, mk.resolution, mk.voice, mk.error], ["pending", 0, "bm", "square", "female", ""]);
assert.deepEqual(mk.captions, {}, "the captions are written again with the film");
assert.equal(remakeFields({ stream: "regulab", voice: "auto" }, "both").resolution, "portrait");
assert.equal(Object.keys(RES2).length, 3);
console.log("motion platform format and remake: ok");

/* a ws.regulab film can be switched to LinkedIn, and back (Wan, 26 Oct 2026) */
import { STREAM_CHOICES, streamOf } from "./src/lib/motion.js";
assert.deepEqual(STREAM_CHOICES.map(([k]) => k), ["regulab", "linkedin"]);
assert.equal(streamOf("linkedin"), "linkedin"); assert.equal(streamOf("x"), "regulab");
const toLi = remakeFields({ stream: "regulab", voice: "male", language: "bm" }, "en", "linkedin");
assert.deepEqual([toLi.stream, toLi.language, toLi.resolution, toLi.status, toLi.attempts, toLi.voice], ["linkedin", "en", "square", "pending", 0, "male"]);
assert.deepEqual(toLi.captions, {}, "the captions are written again for the new stream");
const back = remakeFields({ stream: "linkedin", voice: "kitten" }, "bm", "regulab");
assert.deepEqual([back.stream, back.resolution, back.voice], ["regulab", "portrait", "female"], "a BM film cannot keep the English-only voice");
assert.equal(remakeFields({ stream: "linkedin" }, "en").stream, "linkedin", "no stream given: the film's own");
const waitingRow = { stream: "regulab", options: {}, language: "bm" };
const sf = formOf(waitingRow);
assert.equal(sf.stream, "regulab");
assert.equal(startFields(waitingRow, sf).stream, undefined, "unchanged: nothing about the stream is written");
const swFields = startFields(waitingRow, { ...sf, stream: "linkedin", language: "en" });
assert.deepEqual([swFields.stream, swFields.resolution, swFields.language], ["linkedin", "square", "en"]);
assert.equal(startFields({ stream: "linkedin" }, { ...formOf({ stream: "linkedin" }), stream: "regulab" }).resolution, "portrait");
console.log("motion stream switch: ok");

// the stages a film goes through (063): the status is unchanged, the stage says what a working film is doing
assert.deepEqual(STAGES.map(([id]) => id), ["storyboard", "pictures", "film"]);
const states = (row) => stageSteps(row).map((x) => x.state);
assert.deepEqual(states({ status: "working", stage: "storyboard" }), ["active", "todo", "todo"]);
assert.deepEqual(states({ status: "working", stage: "pictures" }), ["done", "active", "todo"]);
assert.deepEqual(states({ status: "working", stage: "film" }), ["done", "done", "active"]);
assert.deepEqual(states({ status: "done", stage: "done" }), ["done", "done", "done"]);
assert.deepEqual(states({ status: "done" }), ["done", "done", "done"], "a finished film made before stages existed");
assert.deepEqual(states({ status: "pending", stage: "" }), ["todo", "todo", "todo"]);
assert.deepEqual(states({ status: "working" }), ["todo", "todo", "todo"], "working but no stage yet: nothing active");
assert.deepEqual(states({ status: "pending", stage: "pictures" }), ["todo", "todo", "todo"], "a film waiting again is in no stage");
assert.deepEqual(states(undefined), ["todo", "todo", "todo"]);
assert.deepEqual(plannedShots({ script: [{ id: "s1", heading: "H", hook_shape: 17, shot: "a shelf", mood: "calm" }, { id: "s2", heading: "x" }, null] }),
  [{ id: "s1", heading: "H", shot: "a shelf", mood: "calm", hookShape: 17 }]);
assert.deepEqual(plannedShots({ script: "junk" }), []);

// the tracker (064): Idea -> Storyboard -> Pictures -> Film, each with when it began
const track = (row) => motionTrack(row, { L: 1, stamp: (iso) => (iso ? `@${iso}` : "") });
const shape = (row) => track(row).map((x) => (x.isFailed ? "x" : x.isCompleted ? "v" : x.isActive ? ">" : "."));
assert.deepEqual(track({}).map((x) => x.name), ["Idea", "Storyboard", "Pictures", "Film"]);
assert.deepEqual(shape({ status: "waiting", created_at: "t0" }), ["v", ".", ".", "."]);
assert.equal(track({ status: "waiting" })[1].timestamp, "Queued: choose the styles first");
assert.deepEqual(shape({ status: "working", stage: "pictures", stage_times: { storyboard: "t1", pictures: "t2" } }), ["v", "v", ">", "."]);
assert.deepEqual(track({ status: "working", stage: "pictures", stage_times: { storyboard: "t1", pictures: "t2" } }).map((x) => x.timestamp),
  ["", "@t1", "@t2", "Waiting"]);
assert.equal(track({ status: "working", stage: "film" })[3].timestamp, "Running now", "a stage with no stamp yet (before 064) still says it runs");
assert.deepEqual(shape({ status: "done", stage: "done", stage_times: { done: "t9" }, updated_at: "u" }), ["v", "v", "v", "v"]);
assert.equal(track({ status: "done", stage_times: { done: "t9" }, updated_at: "u" })[3].timestamp, "@t9");
assert.equal(track({ status: "done", updated_at: "u" })[3].timestamp, "@u", "an older film: its last change is when it finished");
assert.deepEqual(shape({ status: "error", stage: "", stage_times: { storyboard: "t1", pictures: "t2" } }), ["v", "v", "x", "."], "failed at the last stage it stamped");
assert.deepEqual(shape({ status: "error" }), ["v", "x", ".", "."], "no stamps: the failure is shown at the first stage");
assert.equal(motionTrack({}, { L: 0 })[1].name, "Papan cerita");
console.log("motion tracker: ok");
assert.deepEqual(plannedShots(undefined), []);

// one reference box (Wan, 10 Nov 2026): a video is a style, a repo is a style, a page is the story
const { refKind } = await import("./src/lib/motion.js");
assert.equal(refKind("https://github.com/heygen-com/hyperframes"), "repo");
assert.equal(refKind("https://youtu.be/abc"), "video");
assert.equal(refKind("https://www.tiktok.com/@a/video/1"), "video");
assert.equal(refKind("https://cdn.example.com/f.MP4?x=1"), "video");
assert.equal(refKind("https://www.npra.gov.my/a"), "page");
assert.equal(refKind("https://github.com/heygen-com"), "page");
assert.equal(refKind("nope"), "");
assert.deepEqual(motionRow({ url: "https://youtu.be/abc" }), { error: "ref:brief" });
const refRow = motionRow({ brief: "PFAS", url: "https://youtu.be/abc" }).row;
assert.equal(refRow.source_url, "");
assert.equal(refRow.options.reference_video, "https://youtu.be/abc");
const pageRow = motionRow({ url: "https://www.npra.gov.my/a" }).row;
assert.equal(pageRow.source_url, "https://www.npra.gov.my/a");
assert.equal(pageRow.options.reference_video, undefined);
console.log("motion reference box: ok");

// eight more film modes (Wan, 11 Nov 2026: "make as many model for motion as you can")
{
  const { MODES: M, modeOf: mo, selectedSeconds: ss } = await import("./src/lib/motion.js");
  assert.deepEqual(M.slice(0, 6), ["auto", "explainer", "news", "myth", "howto", "case"], "the original modes keep their places");
  for (const m of ["compare", "change", "define", "decide", "mistake", "checklist", "number", "qna"]) assert.equal(mo(m), m, `${m} is a mode`);
  assert.equal(mo("nonsense"), "auto");
  assert.equal(M.at(-1), "teaser");
  assert.equal(ss(10, "teaser"), 10, "the teaser is still its own 10 s thing");
  assert.notEqual(ss(10, "qna"), 10, "a new mode is a four-scene film, never the 10 s teaser");
  console.log("motion modes: 13 content modes + auto + teaser ok");
}

// LinkedIn gets no film (Wan, 11 Nov 2026: "for linkedn, no need to do motion, only carousel or single card")
{
  const { canFilm } = await import("./src/lib/motion.js");
  assert.equal(canFilm("linkedin"), false); assert.equal(canFilm("regulab"), true); assert.equal(canFilm(undefined), true);
  // a LinkedIn film can still be built by the pure row builders (tests above), the screens simply never call them for LinkedIn
  console.log("linkedin: no film ok");
}

// the film's look (Wan, 11 Nov 2026): nothing chosen is "auto" (the worker picks one of the seven 2D styles at random); a style
// or an older design chosen by hand is kept on the film; an older design is never saved as the default
{
  const { designOf, defaultDesignOf } = await import("./src/lib/motion.js");
  const { designOptions, SKIN_IDS, LEGACY_DESIGN_IDS } = await import("./src/lib/motionStyles.js");
  assert.equal(designOf(undefined), "auto"); assert.equal(designOf("nonsense"), "auto");
  for (const id of [...SKIN_IDS, ...LEGACY_DESIGN_IDS]) assert.equal(designOf(id), id);
  assert.equal(SKIN_IDS.length, 7);
  assert.deepEqual(designOptions.map(d => d.id), ["auto", ...SKIN_IDS, ...LEGACY_DESIGN_IDS]);
  assert.equal(motionRow({ brief: "x", design: "papercut" }).row.options.design, "papercut");
  assert.equal(motionRow({ brief: "x", design: "blur-full" }).row.options.design, "blur-full");
  for (const id of LEGACY_DESIGN_IDS) assert.equal(defaultDesignOf(id), "auto");
  assert.equal(defaultDesignOf("pixel"), "pixel");
  assert.equal(withDefaults({}, { design: "blur-photo" }).defaults.design, "auto");
  assert.equal(withDefaults({}, { design: "chalk" }).defaults.design, "chalk");
}
