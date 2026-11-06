import assert from "node:assert/strict";
import { PARSE_ERRORS, claims, parseAuth, stateOf, validModel } from "./src/lib/chatgptLogin.js";

const enc = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const jwt = (o) => `${enc({ alg: "none" })}.${enc(o)}.sig`;
const access = jwt({ exp: 1_900_000_000, pad: "x".repeat(20) });
const idt = jwt({ email: "wan@example.com" });
const refresh = "rt_" + "a".repeat(40);
const full = { OPENAI_API_KEY: null, tokens: { id_token: idt, access_token: access, refresh_token: refresh, account_id: "acct-1" }, last_refresh: "2026-11-05T00:00:00Z" };

// a JWT is read, not trusted
assert.equal(claims(idt).email, "wan@example.com");
assert.deepEqual(claims("nope"), {});
assert.deepEqual(claims(""), {});

// the whole auth.json
let r = parseAuth(JSON.stringify(full));
assert.equal(r.ok, true);
assert.deepEqual(Object.keys(r.auth), ["tokens"]);
assert.deepEqual(r.auth.tokens, { access_token: access, refresh_token: refresh, id_token: idt, account_id: "acct-1" });
assert.equal(r.account, "wan@example.com");
assert.equal(r.expires, "2030-03-17T17:46:40.000Z");

// just the tokens object, with surrounding whitespace
r = parseAuth("  \n" + JSON.stringify(full.tokens) + "\n");
assert.equal(r.ok, true);
assert.equal(r.account, "wan@example.com");

// an API key beside the tokens is dropped and never sent
r = parseAuth(JSON.stringify({ ...full, OPENAI_API_KEY: "sk-secret-secret-secret" }));
assert.equal(JSON.stringify(r.auth).includes("sk-secret"), false);
assert.equal("last_refresh" in r.auth, false);

// the refusals each have a bilingual sentence
const code = (text) => parseAuth(text).code;
assert.equal(code(""), "empty");
assert.equal(code("   "), "empty");
assert.equal(code("{nope"), "json");
assert.equal(code("[1,2]"), "json");
assert.equal(code("null"), "json");
assert.equal(code(JSON.stringify({ OPENAI_API_KEY: "sk-" + "a".repeat(40) })), "apikey");
assert.equal(code(JSON.stringify({ tokens: { access_token: access } })), "tokens");
assert.equal(code(JSON.stringify({ tokens: { access_token: "short", refresh_token: "short" } })), "shape");
assert.equal(code(JSON.stringify({ tokens: { access_token: "has space " + "a".repeat(50), refresh_token: refresh } })), "shape");
for (const c of ["empty", "json", "apikey", "tokens", "shape"]) assert.ok(PARSE_ERRORS[c][0] && PARSE_ERRORS[c][1], c);

// a token with no readable expiry or e-mail is still accepted
r = parseAuth(JSON.stringify({ tokens: { access_token: "a".repeat(60), refresh_token: refresh } }));
assert.equal(r.ok, true);
assert.equal(r.account, null);
assert.equal(r.expires, null);

// the card's state
assert.equal(stateOf(null), "none");
assert.equal(stateOf({ connected: false }), "none");
assert.equal(stateOf({ connected: true }), "idle");
assert.equal(stateOf({ connected: true, checked_at: "2026-11-05T10:00:00Z" }), "ready", "accepted by ChatGPT, no picture yet");
assert.equal(stateOf({ connected: true, last_ok_at: "2026-11-05T10:00:00Z" }), "ok");
assert.equal(stateOf({ connected: true, enabled: false, last_ok_at: "2026-11-05T10:00:00Z" }), "off");
assert.equal(stateOf({ connected: true, last_ok_at: "2026-11-05T10:00:00Z", last_error_at: "2026-11-05T11:00:00Z", last_error: "x" }), "error");
assert.equal(stateOf({ connected: true, last_ok_at: "2026-11-05T12:00:00Z", last_error_at: "2026-11-05T11:00:00Z" }), "ok", "a later success clears an old error");
assert.equal(stateOf({ connected: true, enabled: false, last_error_at: "2026-11-05T11:00:00Z" }), "error", "a fault is shown even when switched off");

// the model field
assert.equal(validModel("gpt-5"), true);
assert.equal(validModel("gpt-5.1-codex"), true);
assert.equal(validModel(""), false);
assert.equal(validModel("bad model"), false);
assert.equal(validModel("a".repeat(65)), false);
console.log("chatgptLogin.test.mjs: ok");
