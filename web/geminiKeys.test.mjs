import assert from "node:assert/strict";
import { DEFAULTS, JOB_CHOICES, keyState, restMinutes, settingsOf, toggleJob, usableCount, validKey } from "./src/lib/geminiKeys.js";

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
for (const bad of ["", "short", "has space in it 12345678901234567890", "a".repeat(121), "key/with/slash/12345678901234567890", null, undefined]) assert.equal(validKey(bad), false, String(bad));
assert.equal(validKey("  AIzaSyD-0123456789abcdefghijklmnopqrstu  "), true, "surrounding spaces are trimmed");

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
