import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MAX_ACCOUNTS, accountState, canAdd, ordered, restMinutes, restText, usable } from "./src/lib/chatgptAccounts.js";
import { deviceView, forTarget } from "./src/lib/chatgptDevice.js";

const T0 = Date.parse("2026-11-24T18:00:00Z");
const at = (min) => new Date(T0 + min * 60000).toISOString();

// ---- one account's state
assert.equal(accountState(null, T0), "idle");
assert.equal(accountState({ id: "acc1" }, T0), "idle");
assert.equal(accountState({ checked_at: at(-5) }, T0), "ready");
assert.equal(accountState({ last_ok_at: at(-5), checked_at: at(-5) }, T0), "ok");
assert.equal(accountState({ enabled: false, last_ok_at: at(-5) }, T0), "off");
assert.equal(accountState({ enabled: false, limit_until: at(60) }, T0), "off", "off wins over resting");
// resting until limit_until, then asked again
assert.equal(accountState({ limit_until: at(90), last_error_at: at(-1), last_error: "usage limit" }, T0), "resting");
assert.equal(accountState({ limit_until: at(-1), last_ok_at: at(-200), last_error_at: at(-181), checked_at: at(-10) }, T0), "ok",
  "the rest is over and a later check accepted the login: not an error any more");
assert.equal(accountState({ limit_until: "not a date", checked_at: at(-5) }, T0), "ready");
assert.equal(accountState({ limit_until: at(-1), last_error_at: at(-181), last_error: "usage limit" }, T0), "idle",
  "a rest that is over is not an error: the limit message is history");
assert.equal(accountState({ limit_until: at(-100), last_error_at: at(-5), last_error: "refused" }, T0), "error",
  "an error AFTER the rest ended is a real one");
// an error newer than the last picture and the last check
assert.equal(accountState({ last_ok_at: at(-60), last_error_at: at(-5), checked_at: at(-30) }, T0), "error");
assert.equal(accountState({ last_error_at: at(-5) }, T0), "error");
assert.equal(accountState({ last_ok_at: at(-5), last_error_at: at(-60) }, T0), "ok");

// ---- the rest
assert.equal(restMinutes({ limit_until: at(125) }, T0), 125);
assert.equal(restMinutes({ limit_until: at(0.2) }, T0), 1, "rounded up: never '0 minutes' while still resting");
assert.equal(restMinutes({ limit_until: at(-1) }, T0), 0);
assert.equal(restMinutes({}, T0), 0);
assert.equal(restText(125, true), "2h 5m");
assert.equal(restText(125, false), "2j 5m");
assert.equal(restText(59, true), "59m");
assert.equal(restText(60, true), "1h 0m");
assert.equal(restText(-3, true), "0m");

// ---- the order the worker asks them: by number, not by text (acc10 after acc2)
const rows = [{ id: "acc10" }, { id: "acc2", enabled: false }, { id: "acc1", limit_until: at(30) }, null, { account: "no id" }];
assert.deepEqual(ordered(rows).map((r) => r.id), ["acc1", "acc2", "acc10"]);
assert.deepEqual(ordered(null), []);
assert.equal(usable(rows, T0), 1, "one is off and one is resting");
assert.equal(usable(rows, T0 + 31 * 60000), 2, "the rest is over");
assert.equal(canAdd(rows), true);
assert.equal(canAdd(Array.from({ length: MAX_ACCOUNTS }, (_, i) => ({ id: `acc${i + 1}` }))), false);

// ---- one code request, two cards: each sees only its own
const waiting = { state: "waiting", user_code: "3CA1-GJOWC", expires_at: at(15), server_now: at(0) };
assert.equal(deviceView(forTarget({ ...waiting, target: "new" }, "new"), T0).phase, "waiting");
assert.equal(deviceView(forTarget({ ...waiting, target: "new" }, "main"), T0).phase, "idle", "the main card never shows the extra account's code");
assert.equal(deviceView(forTarget({ ...waiting, target: "main" }, "new"), T0).phase, "idle");
assert.equal(deviceView(forTarget({ ...waiting, target: "main" }, "main"), T0).phase, "waiting");
assert.equal(deviceView(forTarget(waiting, "main"), T0).phase, "waiting", "a row from before 095 has no target: it is the main login's");
assert.equal(deviceView(forTarget(waiting, "new"), T0).phase, "idle");
assert.equal(deviceView(forTarget({ state: "done", target: "new" }, "main"), T0).phase, "idle", "and never says 'connected' for it");
assert.equal(forTarget({ state: "done", target: "new", server_now: at(0) }, "main").server_now, at(0), "the clock reading is kept");
assert.equal(deviceView(forTarget(null, "main"), T0).phase, "idle");

// ---- the way in: a button at the top of the API tab jumps to the card, and the card carries the id it jumps to
const tab = readFileSync(new URL("./src/pages/ApiTab.jsx", import.meta.url), "utf8");
const card = readFileSync(new URL("./src/components/ChatGptAccounts.jsx", import.meta.url), "utf8");
const target = /jumpTo\("([a-z-]+)"\)/.exec(tab)?.[1];
assert.equal(target, "chatgpt-accounts", "the top button jumps to the accounts card");
assert.equal((card.match(new RegExp(`id="${target}"`, "g")) || []).length, 2, "both the card and its 'run 095 first' stand-in carry that id");
assert.ok(/data-api-add-chatgpt/.test(tab) && tab.indexOf("data-api-add-chatgpt") > tab.indexOf("data-api-nav"), "the button sits in the jump row at the top");

console.log("chatgptAccounts: ok");
