import assert from "node:assert/strict";
import { LIFETIME_S, STALLED_AFTER_S, VERIFY_URL, clock, deviceView, polling, safeUrl } from "./src/lib/chatgptDevice.js";

const T0 = Date.parse("2026-11-06T17:00:00Z");
const at = (s) => new Date(T0 + s * 1000).toISOString();

// nothing asked, or an unknown state: idle
for (const s of [null, undefined, {}, { state: "weird" }]) assert.equal(deviceView(s, T0).phase, "idle");
assert.equal(polling(deviceView(null)), false);

// asked, the worker has not answered: requested, then stalled
let v = deviceView({ state: "requested", requested_at: at(0) }, T0 + 30_000);
assert.deepEqual([v.phase, v.stalled, polling(v)], ["requested", false, true]);
assert.equal(deviceView({ state: "requested", requested_at: at(0) }, T0 + (STALLED_AFTER_S + 1) * 1000).stalled, true);

// the code is on the card, with a countdown
const waiting = { state: "waiting", user_code: "3CA1-GJOWC", verification_url: VERIFY_URL, expires_at: at(LIFETIME_S) };
v = deviceView(waiting, T0);
assert.deepEqual([v.phase, v.code, v.url, v.secondsLeft, polling(v)], ["waiting", "3CA1-GJOWC", VERIFY_URL, 900, true]);
assert.equal(deviceView(waiting, T0 + 60_000).secondsLeft, 840);
assert.equal(clock(840), "14:00");
assert.equal(clock(65), "1:05");
assert.equal(clock(-3), "0:00");
assert.equal(clock(undefined), "0:00");

// the clock runs out: expired, even if the row still says waiting
v = deviceView(waiting, T0 + LIFETIME_S * 1000 + 1000);
assert.deepEqual([v.phase, v.code, polling(v)], ["expired", "", false]);
assert.equal(deviceView({ state: "expired" }, T0).phase, "expired");

// a phone whose clock is 10 minutes slow does not get a 25 minute code: the server's time is the measure
const skew = 10 * 60 * 1000;                                    // server is 10 minutes ahead of this browser
assert.equal(deviceView(waiting, T0 - skew, skew).secondsLeft, 900);
assert.equal(deviceView(waiting, T0 - skew + 60_000, skew).secondsLeft, 840);

// done and error
assert.equal(deviceView({ state: "done" }, T0).phase, "done");
v = deviceView({ state: "error", error: "x".repeat(400) }, T0);
assert.deepEqual([v.phase, v.error.length, polling(v)], ["error", 300, false]);

// the link is only ever OpenAI's device page
assert.equal(safeUrl("https://auth.openai.com/codex/device"), "https://auth.openai.com/codex/device");
for (const bad of ["https://evil.example/codex/device", "http://auth.openai.com/x", "javascript:alert(1)", "", null, undefined, 5]) {
  assert.equal(safeUrl(bad), VERIFY_URL, String(bad));
}
assert.equal(deviceView({ ...waiting, verification_url: "https://evil.example/" }, T0).url, VERIFY_URL);
console.log("chatgptDevice.test.mjs: ok");
