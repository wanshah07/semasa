import assert from "node:assert/strict";
import {
  ALL_JOBS, DIALECTS, JOB_CHOICES, RESERVED, STATE_WORDS, formOf, formProblem, hostOf, jobsOf, keyWillDrop, numbered, providerState, rpcArgs, slugOf, toggleJob,
} from "./src/lib/aiProviders.js";
import { themeFor, THEMES } from "./src/lib/robots.js";

const NOW = Date.parse("2026-11-08T06:00:00Z");
const row = (over = {}) => ({ id: "claude", name: "Claude", dialect: "anthropic", base_url: "https://api.anthropic.com", model: "claude-sonnet-4-5",
  key_hint: "…1234", key_host: "api.anthropic.com", enabled: true, jobs: ["chat", "reader", "ideas", "motion", "telegram"], created_at: "2026-11-08T01:00:00Z", ...over });
const status = (over = {}) => ({ slug: "claude", key_set: true, reachable: true, key_ok: true, chat_ok: true, checked_at: "2026-11-08T05:00:00Z", role: "provider", ...over });

// the shape mirrors the database
assert.deepEqual(RESERVED, ["rootsys", "mireld", "kiosapi", "gemini", "chatgpt"]);
assert.deepEqual(ALL_JOBS, ["chat", "reader", "ideas", "motion", "telegram"], "the edge functions' and the worker's jobs together");
assert.deepEqual(DIALECTS.map(([k]) => k), ["openai", "anthropic"], "gemini is not a dialect here: its keys go on the Gemini card");
assert.equal(JOB_CHOICES.length, 5);
assert.deepEqual(jobsOf(null), ALL_JOBS, "null means every job"); assert.deepEqual(jobsOf([]), ALL_JOBS, "so does an empty list");
assert.deepEqual(jobsOf(["telegram", "bogus", "chat"]), ["chat", "telegram"]);

// the form
assert.deepEqual(formOf(null).jobs, ALL_JOBS);
assert.equal(formOf(null).dialect, "openai");
const f = formOf(row({ jobs: ["motion", "bogus"] }));
assert.deepEqual(f.jobs, ["motion"]); assert.equal(f.api_key, "", "the key is never in a row: empty means keep");
assert.equal(f.enabled, true);
assert.equal(slugOf("KiosAPI 2"), "kiosapi-2");
assert.equal(slugOf("  Claude (Anthropic) "), "claude-anthropic");
assert.equal(slugOf("x".repeat(40)).length, 24);
assert.equal(hostOf("https://API.Anthropic.com/v1/"), "api.anthropic.com");
assert.equal(hostOf("http://kiosapi.com/v1"), "", "https only");
assert.equal(hostOf(""), "");
assert.deepEqual(toggleJob(["chat", "reader"], "motion", true), ["chat", "reader", "motion"]);
assert.deepEqual(toggleJob(["reader", "motion"], "reader", false), ["motion"]);

// what cannot be saved, and why (the same checks the database makes)
const good = { ...formOf(null), id: "claude", name: "Claude", dialect: "anthropic", base_url: "https://api.anthropic.com", model: "claude-sonnet-4-5", api_key: "sk-ant-12345678" };
assert.equal(formProblem(good), null);
assert.match(formProblem({ ...good, id: "C" })[1], /2 to 24/);
assert.match(formProblem({ ...good, id: "gemini" })[1], /built-in/);
assert.match(formProblem({ ...good, id: "kiosapi" })[0], /sedia ada/);
assert.match(formProblem({ ...good, id: "claude" }, { rows: [row()] })[1], /already exists/, "a new provider cannot take an existing id");
assert.equal(formProblem({ ...good, id: "claude" }, { existing: row(), rows: [row()] }), null, "editing keeps its own id");
assert.match(formProblem({ ...good, name: " " })[1], /name/);
assert.match(formProblem({ ...good, dialect: "gemini" })[1], /Gemini card/);
assert.match(formProblem({ ...good, base_url: "http://x.y" })[1], /https/);
assert.match(formProblem({ ...good, base_url: "https://generativelanguage.googleapis.com/v1beta/openai" })[1], /Gemini/);
assert.match(formProblem({ ...good, api_key: "short" })[1], /8 characters/);
assert.match(formProblem({ ...good, api_key: "has space inside" })[1], /no spaces/);
assert.match(formProblem({ ...good, model: "" })[1], /model/);
assert.match(formProblem({ ...good, api_key: "" })[1], /Paste the API key/, "a new provider needs a key");
assert.equal(formProblem({ ...good, api_key: "" }, { existing: row() }), null, "an edit may keep the saved key");
assert.match(formProblem({ ...good, jobs: [] })[1], /at least one job/);

// a host move drops the key: said before the save
assert.equal(keyWillDrop({ ...good, api_key: "", base_url: "https://other.example/v1" }, row()), true);
assert.equal(keyWillDrop({ ...good, api_key: "sk-new-12345678", base_url: "https://other.example/v1" }, row()), false, "a new key goes with the move");
assert.equal(keyWillDrop({ ...good, api_key: "", base_url: "https://api.anthropic.com/" }, row()), false, "the same host, a trailing slash");
assert.equal(keyWillDrop(good, null), false);

// the RPC arguments
assert.deepEqual(rpcArgs({ ...good, id: " Claude ", base_url: "https://api.anthropic.com//", api_key: "", notes: " ", jobs: ["chat", "reader"] }), {
  p_id: "claude", p_name: "Claude", p_dialect: "anthropic", p_base_url: "https://api.anthropic.com", p_model: "claude-sonnet-4-5", p_api_key: null,
  p_enabled: true, p_jobs: ["chat", "reader"], p_notes: null });
assert.equal(rpcArgs({ ...good, enabled: false }).p_enabled, false);
assert.equal(rpcArgs(good).p_api_key, "sk-ant-12345678");

// the state dot: the provider's own switch and key first, then the probe's row
assert.equal(providerState(row({ enabled: false }), status()), "off");
assert.equal(providerState(row({ key_hint: null, key_host: null }), status()), "nokey");
assert.equal(providerState(row({ base_url: "https://moved.example/v1" }), status()), "nokey", "a key bound to another host is no key");
assert.equal(providerState(row(), null), "unchecked");
assert.equal(providerState(row(), status(), [], NOW), "standby");
assert.equal(providerState(row(), status(), [{ gateway: "claude", ok: true, area: "scrape", created_at: "2026-11-08T05:30:00Z" }], NOW), "active");
assert.equal(providerState(row(), status({ chat_ok: false }), [], NOW), "offline");
assert.equal(providerState(row(), status({ checked_at: "2026-11-06T05:00:00Z" }), [], NOW), "offline", "not checked in 13 h");
for (const k of ["off", "nokey", "unchecked", "active", "standby", "offline"]) assert.equal(STATE_WORDS[k].length, 2, k);

// numbering: oldest first, W6 up, whatever the order the rows arrive in
assert.deepEqual(numbered([row({ id: "b", created_at: "2026-11-08T02:00:00Z" }), row({ id: "a" })]).map((r) => [r.id, r.robot]), [["a", "W6"], ["b", "W7"]]);
assert.deepEqual(numbered(null), []);

// robots.js: a provider tone of its own, the guest slate for anything unnamed, the label overridden per robot
assert.ok(THEMES.provider && THEMES.provider.shell.length === 3);
assert.equal(themeFor("provider", "W7").label, "W7");
assert.equal(themeFor("provider").label, "W6");
assert.equal(themeFor("nobody", "W9").shell, THEMES.guest.shell);
assert.equal(themeFor("afiq").label, "W1");
console.log("aiProviders.test.mjs: ok");
