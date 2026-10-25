import assert from "node:assert/strict";
import { LANGUAGES, defaultLanguage, freshUrl, motionDefaults, motionFromIdea, motionFromPost, withDefaults, RESOLUTIONS, SECONDS, checkItems, clampSeconds, fmtBytes, motionLabel, motionRepoRow, motionRow, styleRepos } from "./src/lib/motion.js";

assert.equal(clampSeconds("abc"), SECONDS.default);
assert.equal(clampSeconds(1), SECONDS.min);
assert.equal(clampSeconds(999), SECONDS.max);
assert.equal(clampSeconds("14.6"), 30);

assert.deepEqual(motionRow({}), { error: "empty" });
assert.deepEqual(motionRow({ url: "github.com/x" }), { error: "url" });
const ok = motionRow({ brief: "  PFAS  ", url: "", stream: "linkedin", resolution: "square", seconds: "20" }, "u1");
assert.deepEqual(ok.row, { brief: "PFAS", source_url: "", stream: "linkedin", language: "en", resolution: "square", seconds: 30, status: "pending", options: { style: "bright-education", mode: "explainer", design: "bright-editorial", effects:["B04"], effect_mode:"auto", asset_mode:"auto", assets:[], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true} }, style_repo_id: null, ai_background: false, created_by: "u1", voice: "kitten", mascot: "" });
// the presenter and the voice: on by default, Wan can turn either off
assert.equal(motionRow({ brief: "x", voice: "female" }).row.voice, "female");
assert.equal(motionRow({ brief: "x", voice: "nope" }).row.voice, "kitten");
assert.equal(motionRow({ brief: "x", mascot: false }).row.mascot, "");
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
assert.deepEqual(motionFromIdea(idea, "u1"), { brief: "NPRA batalkan 12 produk\nWan: tekankan label\nRingkasan.", source_url: "https://npra.gov.my/x", stream: "regulab", language: "en", resolution: "portrait", seconds: 30, status: "pending", idea_id: "i1", ai_background: false, options: { style: "bright-education", mode: "explainer", design: "bright-editorial", effects:["B04"], effect_mode:"auto", asset_mode:"auto", assets:[], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true}, evidence: {source_url: idea.source_url, source_summary: idea.source_summary, id: idea.id} }, style_repo_id: null, voice: "kitten", mascot: "", created_by: "u1" });
// the saved defaults ("the skill") apply to an idea and to a post
const saved = withDefaults({ prompt: "P" }, { language: "en", voice: "female", mascot: false, resolution: "square", seconds: "25", aiBackground: true, styleRepoId: "r9" });
assert.deepEqual(saved, { prompt: "P", defaults: { effects:["B04"], effectMode:"auto", assetMode:"auto", language: "en", voice: "female", mascot: false, design: "bright-editorial", previewMusic: "user-reel", style: "bright-education", mode: "explainer", resolution: "square", seconds: 30, aiBackground: true, styleRepoId: "r9" } });
const dflts = motionDefaults({ motion: saved });
const fromIdea = motionFromIdea(idea, "u1", dflts);
assert.deepEqual([fromIdea.language, fromIdea.voice, fromIdea.mascot, fromIdea.resolution, fromIdea.seconds, fromIdea.ai_background, fromIdea.style_repo_id], ["en", "female", "", "square", 30, true, "r9"]);
assert.equal(motionFromIdea({ id: "i3", source_title: "T", stream: "linkedin" }, null, motionDefaults({})).language, "en", "no saved language: the stream's own");
assert.equal(motionFromPost({ lang: "bm", text: { bm: { facebook: "K" } } }, null, dflts).language, "en");
assert.equal(motionDefaults(null).voice, "kitten");
assert.equal(freshUrl("https://x/a.mp4", "2026-10-24T05:00:00Z"), "https://x/a.mp4?v=2026-10-24T05%3A00%3A00Z");
assert.equal(freshUrl("", "x"), "");
assert.equal(motionFromIdea({ id: "i2", source_title: "T", stream: "linkedin", source_url: "not a url" }).stream, "linkedin");
assert.equal(motionFromIdea({ id: "i2", source_title: "T", source_url: "not a url" }).source_url, "");
assert.equal(motionFromIdea({ id: "i3" }), null);
assert.equal(motionFromIdea({ id: "i4", source_title: "x".repeat(3000) }).brief.length, 1900);
console.log("motion.test.mjs: ok");

// a post draft: slides first, else the caption in the post's own language
const post = { lang: "bm", stream: "regulab", idea_id: "i9", slides: [{ title: "Tiga perkara", points: ["Satu", "Dua"] }, { title: "Penutup" }], text: { bm: { facebook: "Kapsyen" } } };
assert.deepEqual(motionFromPost(post, "u1"), { brief: "Tiga perkara\n- Satu\n- Dua\n\nPenutup", source_url: "", stream: "regulab", language: "en", resolution: "portrait", seconds: 30, status: "pending", idea_id: "i9", ai_background: false, options: { style: "bright-education", mode: "explainer", design: "bright-editorial", effects:["B04"], effect_mode:"auto", asset_mode:"auto", assets:[], preferred_preview_music: {source:"user-reel", rights_status:"unverified", preview_only:true}, evidence: {idea_id:"i9"} }, style_repo_id: null, voice: "kitten", mascot: "", created_by: "u1" });
assert.equal(motionFromPost({ lang: "en", stream: "linkedin", text: { en: { linkedin: "Words" } } }).brief, "Words");
assert.equal(motionFromPost({ lang: "en", stream: "linkedin", text: { en: { linkedin: "Words" } } }).language, "en");
assert.equal(motionFromPost({ lang: "bm", text: {} }), null);
// the direction chosen on the idea or the draft itself wins over the saved default and the stream
assert.equal(motionFromIdea(idea, "u1", dflts, "bm").language, "bm");
assert.equal(motionFromIdea(idea, "u1", null, "en").language, "en");
assert.equal(motionFromPost(post, "u1", null, "both").language, "both");
assert.equal(motionFromPost(post, "u1", null, "nope").language, "en", "an unknown choice falls back to current English defaults");
