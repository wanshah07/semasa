import assert from "node:assert/strict";
import { LIGHT_BG, lightOf, STALE_MS } from "./src/lib/sourceLights.js";

const NOW = Date.parse("2026-11-14T12:00:00Z");
const setting = (at, lights) => ({ at, lights });
const fresh = new Date(NOW - 3600e3).toISOString();

assert.deepEqual(lightOf(setting(fresh, { threads: { light: "green", why: "live: 24 read" } }), "threads", NOW), { light: "green", why: "live: 24 read" });
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

for (const l of ["green", "orange", "red", "unknown"]) assert.ok(LIGHT_BG[l], `${l} has a colour`);
console.log("sourceLights: ok");
