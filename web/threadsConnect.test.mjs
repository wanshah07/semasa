import assert from "node:assert/strict";
import { FIELD_ERRORS, fieldProblem, needsApproval, stateOf, validAppId, validSecret, validToken } from "./src/lib/threadsConnect.js";

// the same rules as supabase/080's semasa_threads_connect
assert.equal(validAppId("123456789012345"), true);
assert.equal(validAppId(" 123456 "), true);
assert.equal(validAppId("12345"), false);
assert.equal(validAppId("12ab56"), false);
assert.equal(validSecret("a".repeat(32)), true);
assert.equal(validSecret("a".repeat(15)), false);
assert.equal(validSecret("ab cd".padEnd(32, "x")), false);
assert.equal(validToken("T".repeat(60)), true);
assert.equal(validToken("T".repeat(39)), false);
assert.equal(validToken("T".repeat(30) + " " + "T".repeat(30)), false);

// the first thing wrong is the one named, in the order the dashboard shows them
const id = "123456789", secret = "s".repeat(32), token = "t".repeat(60);
assert.equal(fieldProblem(id, secret, token), "");
assert.equal(fieldProblem("", secret, token), "app_id");
assert.equal(fieldProblem(id, "short", token), "secret");
assert.equal(fieldProblem(id, secret, "short"), "token");
for (const k of ["app_id", "secret", "token"]) assert.equal(FIELD_ERRORS[k].length, 2);       // Bahasa Malaysia first, English second

// the state the card shows
assert.equal(stateOf(null), "none");
assert.equal(stateOf({ connected: false }), "none");
assert.equal(stateOf({ connected: true }), "idle");
assert.equal(stateOf({ connected: true, checked_at: "2026-11-13T06:00:00Z" }), "ready");
assert.equal(stateOf({ connected: true, checked_at: "2026-11-13T06:00:00Z", last_ok_at: "2026-11-13T07:00:00Z" }), "ok");
assert.equal(stateOf({ connected: true, enabled: false, last_ok_at: "2026-11-13T07:00:00Z" }), "off");
assert.equal(stateOf({ connected: true, last_ok_at: "2026-11-13T07:00:00Z", last_error: "x", last_error_at: "2026-11-13T08:00:00Z" }), "error");
assert.equal(stateOf({ connected: true, last_ok_at: "2026-11-13T09:00:00Z", last_error: "x", last_error_at: "2026-11-13T08:00:00Z" }), "ok");

// a keyword-search refusal is recognised so the card can point at Meta's review
assert.equal(needsApproval({ last_error: "Threads searched only this account's own posts: threads_keyword_search is not approved" }), true);
assert.equal(needsApproval({ last_error: "Invalid OAuth access token" }), false);
assert.equal(needsApproval(null), false);
console.log("threadsConnect: ok");
