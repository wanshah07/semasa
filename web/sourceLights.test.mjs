import assert from "node:assert/strict";
import { LIGHT_BG, LIGHT_TINT, SOURCES, STALE_MS, checkedText, lightCounts, lightOf } from "./src/lib/sourceLights.js";
import { readFileSync } from "node:fs";

const NOW = Date.parse("2026-11-14T12:00:00Z");
const setting = (at, lights) => ({ at, lights });
const fresh = new Date(NOW - 3600e3).toISOString();

assert.deepEqual(lightOf(setting(fresh, { threads: { light: "green", why: "live: 24 read" } }), "threads", NOW), { light: "green", why: "live: 24 read", checked: "" });
assert.equal(lightOf(setting(fresh, { instagram: { light: "orange", why: "waiting for a saved login" } }), "instagram", NOW).light, "orange");
assert.equal(lightOf(setting(fresh, { youtube: { light: "red", why: "403" } }), "youtube", NOW).light, "red");

// nothing saved yet, a section the backend does not know, or a light name we do not draw: grey, never a guess
assert.equal(lightOf(undefined, "threads", NOW).light, "unknown");
assert.equal(lightOf(setting(fresh, {}), "threads", NOW).light, "unknown");
assert.equal(lightOf(setting(fresh, { threads: { light: "purple" } }), "threads", NOW).light, "unknown");

// a watchdog that stopped updating must not leave a stale green on the page
const old = new Date(NOW - STALE_MS - 3600e3).toISOString();
const stale = lightOf(setting(old, { threads: { light: "green", why: "live" } }), "threads", NOW);
assert.equal(stale.light, "unknown");
assert.match(stale.why, /has not updated for 14 h/);

for (const l of ["green", "orange", "red", "unknown"]) assert.ok(LIGHT_BG[l] && LIGHT_TINT[l], `${l} has a dot colour and a button tint`);

// when each source was checked (Wan, 14 Nov 2026: "what time checked"): its own sweep time, in Malaysia time
const withTime = setting(fresh, { threads: { light: "green", why: "live", checked: "2026-11-14T09:12:00Z" }, myra: { light: "green", why: "live", checked: "2026-11-13T21:10:00Z" } });
assert.equal(lightOf(withTime, "threads", NOW).checked, "2026-11-14T09:12:00Z");
assert.equal(checkedText("2026-11-14T09:12:00Z", NOW), "17:12", "today in MYT: the clock alone");
assert.equal(checkedText("2026-11-13T21:10:00Z", NOW), "05:10", "21:10 UTC is already the 14th in Malaysia");
assert.equal(checkedText("2026-11-13T09:12:00Z", NOW), "13 Nov 17:12", "another day carries its date");
assert.equal(checkedText("2026-08-01T09:12:00Z", NOW), "1 Ogo 17:12");
assert.equal(checkedText("2026-08-01T09:12:00Z", NOW, true), "1 Aug 17:12");
assert.equal(checkedText("", NOW), "");
assert.equal(checkedText("not a date", NOW), "");
assert.equal(lightOf(setting(old, { threads: { light: "green", checked: "2026-11-13T09:12:00Z" } }), "threads", NOW).checked, "2026-11-13T09:12:00Z", "a stale watchdog still says when the source was last swept");

// the dashboard card: every light the backend works out has a tile, and the counts add up
const py = readFileSync(new URL("../backend/semasa/source_lights.py", import.meta.url), "utf8");
const backend = JSON.parse(`[${/^SECTIONS = \(([^)]*)\)/m.exec(py)[1]}]`);
assert.deepEqual(SOURCES.map((s) => s[0]), backend, "the page lists the same sources, in the same order, as the watchdog");
assert.deepEqual(lightCounts(withTime, NOW), { green: 2, orange: 0, red: 0, unknown: SOURCES.length - 2 });
const app = readFileSync(new URL("./src/App.jsx", import.meta.url), "utf8");
assert.match(app, /LIGHT_TINT\[lt\.light\]/, "each Isu semasa button is tinted by its source's status");
assert.match(app, /checkedText\(lt\.checked/, "and carries the time it was checked");
assert.ok(readFileSync(new URL("./src/pages/HomeTab.jsx", import.meta.url), "utf8").includes("<SourceStatus "), "the dashboard shows the live status card");
console.log("sourceLights: ok");
