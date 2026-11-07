import assert from "node:assert/strict";
import { AUTO, DEFAULTS, FALLBACK_TEXT, JOB_CHOICES, STATE_WORDS, effectiveModel, keyProblem, keyState, modelOptions, modelsOf, restMinutes, settingsOf, toggleJob, usableCount, validKey } from "./src/lib/geminiKeys.js";

const NOW = Date.parse("2026-11-06T12:00:00Z");
const at = (m) => new Date(NOW + m * 60000).toISOString();

// the settings, over the defaults and cleaned
assert.deepEqual(settingsOf(undefined), DEFAULTS);
assert.deepEqual(settingsOf({}), DEFAULTS);
assert.deepEqual(settingsOf({ jobs: ["reader", "bogus", "motion"], max_images: 99, model: " gemini-x ", enabled: false, images: false }),
  { enabled: false, model: "gemini-x", image_model: DEFAULTS.image_model, images: false, max_images: 8, jobs: ["reader", "motion"] });
assert.equal(settingsOf({ max_images: 0 }).max_images, 6, "zero is not a count");
assert.equal(settingsOf({ model: "   " }).model, DEFAULTS.model);
assert.deepEqual(settingsOf("junk"), DEFAULTS);
assert.deepEqual(DEFAULTS.jobs, ["motion", "ideas"], "the sensitive jobs are off until Wan switches them on");

// jobs
assert.deepEqual(toggleJob(["motion"], "ideas", true), ["motion", "ideas"]);
assert.deepEqual(toggleJob(["ideas", "motion"], "motion", false), ["ideas"]);
assert.deepEqual(toggleJob(["reader"], "motion", true), ["motion", "reader"], "a steady order");
assert.deepEqual(toggleJob(undefined, "reader", true), ["reader"]);
assert.deepEqual(JOB_CHOICES.map(([k]) => k), ["motion", "ideas", "reader"]);

// a pasted key: the same rule as the database
assert.equal(validKey("AIzaSyD-0123456789abcdefghijklmnopqrstu"), true);
for (const bad of ["", "short", "has space in it 12345678901234567890", "a".repeat(201), "key/with/slash/12345678901234567890", null, undefined]) assert.equal(validKey(bad), false, String(bad));
assert.equal(validKey("  AIzaSyD-0123456789abcdefghijklmnopqrstu  "), true, "surrounding spaces are trimmed");
assert.equal(validKey("AQ.Ab8RN6Kx0123456789abcdefghijklmnopqrstuvwx"), true, "Google's newer keys hold a dot");
assert.equal(validKey("a".repeat(200)), true);

// why a key is refused: one reason, in both languages, and null when it is fine
assert.equal(keyProblem("AQ.Ab8RN6Kx0123456789abcdefghijklmnopqrstuvwx"), null);
assert.match(keyProblem("")[1], /Paste the API key/);
assert.match(keyProblem("AIza abc def 1234567890123456")[0], /ruang/);
assert.match(keyProblem("AIza\nabc1234567890123456789")[1], /line break/);
assert.match(keyProblem("short")[1], /too short \(5 characters/);
assert.match(keyProblem("a".repeat(201))[1], /too long \(201/);
assert.match(keyProblem("key/with/slash/12345678901234567890")[1], /characters a key never has: \//);
assert.equal(keyProblem(" AIzaSyD-0123456789abcdefghijklmnopqrstu "), null);
for (const bad of ["", "short", "a".repeat(201), "x/y/z/12345678901234567890"]) assert.ok(keyProblem(bad), bad);

// a key's state
assert.equal(keyState(null, NOW), "off");
assert.equal(keyState({ enabled: false, status: "ok" }, NOW), "off");
assert.equal(keyState({ enabled: true, status: "bad" }, NOW), "bad");
assert.equal(keyState({ enabled: true, status: "limited", cooldown_until: at(10) }, NOW), "resting");
assert.equal(keyState({ enabled: true, status: "limited", cooldown_until: at(-1) }, NOW), "new", "a rested key is tried again");
assert.equal(keyState({ enabled: true, status: "ok" }, NOW), "ok");
assert.equal(keyState({ enabled: true, status: "new" }, NOW), "new");
assert.equal(keyState({ status: "ok" }, NOW), "ok", "a row with no enabled flag counts as on");
assert.equal(restMinutes({ cooldown_until: at(0.2) }, NOW), 1);
assert.equal(restMinutes({ cooldown_until: at(29.5) }, NOW), 30);
assert.equal(restMinutes({ cooldown_until: at(-5) }, NOW), 0);
assert.equal(restMinutes({}, NOW), 0);

// how many can be used now
const rows = [{ enabled: true, status: "ok" }, { enabled: true, status: "new" }, { enabled: true, status: "bad" }, { enabled: false, status: "ok" },
  { enabled: true, status: "limited", cooldown_until: at(5) }];
assert.equal(usableCount(rows, NOW), 2);
assert.equal(usableCount([], NOW), 0);
assert.equal(usableCount(undefined, NOW), 0);
console.log("geminiKeys.test.mjs: ok");

// the models: "auto" follows what the keys list and what answered; Wan's own choice holds while it can
assert.equal(DEFAULTS.model, AUTO); assert.equal(DEFAULTS.image_model, AUTO);
assert.deepEqual(modelsOf(undefined), { text: [], image: [], textPick: "", imagePick: "", unavailable: [], at: null, from: "" });
assert.deepEqual(modelsOf({ text: ["a", 1, "", "b"], text_pick: "b", unavailable: ["a"], at: "t", from: "Key 1" }),
  { text: ["a", "b"], image: [], textPick: "b", imagePick: "", unavailable: ["a"], at: "t", from: "Key 1" });
const listed = ["gemini-3-flash", "gemini-2.5-flash", "gemini-2.5-pro"];
assert.equal(effectiveModel("auto", listed, "gemini-3-flash", FALLBACK_TEXT), "gemini-3-flash");
assert.equal(effectiveModel("auto", [], "", FALLBACK_TEXT), FALLBACK_TEXT, "nothing found yet: Google's own alias");
assert.equal(effectiveModel("gemini-2.5-pro", listed, "gemini-3-flash", FALLBACK_TEXT), "gemini-2.5-pro", "his choice holds while listed");
assert.equal(effectiveModel("gemini-1.5-flash", listed, "gemini-3-flash", FALLBACK_TEXT), "gemini-3-flash", "no longer listed");
assert.equal(effectiveModel("gemini-2.5-flash", listed, "gemini-3-flash", FALLBACK_TEXT, ["gemini-2.5-flash"]), "gemini-3-flash", "found gone");
assert.equal(effectiveModel("gemini-x", [], "", FALLBACK_TEXT), "gemini-x", "nothing listed yet: his choice is trusted");
const opts = modelOptions(listed, "gemini-1.5-flash", "gemini-3-flash", ["gemini-2.5-flash"], 1);
assert.deepEqual(opts.map((o) => o.value), ["auto", ...listed, "gemini-1.5-flash"]);
assert.match(opts[0].label, /Auto \(recommended\): now gemini-3-flash/);
assert.match(opts[2].label, /gemini-2.5-flash \(not available to your keys\)/);
assert.match(opts.at(-1).label, /not in your keys' list/);
assert.match(modelOptions([], "auto", "", [], 0)[0].label, /Auto \(disyorkan\): kini \?/);
assert.equal(modelOptions(listed, "auto", "x").length, 4, "auto adds no extra row");
assert.equal(modelOptions([], "gemini-x", "x").at(-1).label, "gemini-x", "nothing listed: no 'not in list' scare");

assert.equal(STATE_WORDS.resting[1], "Resting (will retry)", "a rest is not always a rate limit");
