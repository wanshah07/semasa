/* The API pulse (supabase/functions/semasa-pulse, supabase/075_api_pulse.sql, src/lib/apiPulse.js, components/ApiPulse.jsx):
   the pure half of the function, the page's reading of settings.api_pulse, and the text of the SQL, the workflow and the pages.
   `npm test`. */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  CADENCE_MIN, GEMINI_CHEAP, HEADER, NAMES, chatBody, chatgptRow, flips, geminiModel, modelIds, pulsePlan, pulseRows, sameSecret, stateAfter, statusRow, usageOf,
} from "../supabase/functions/semasa-pulse/logic.js";
import { EVERY_MIN, LATE_MS, PULSE_KEY, freshness, pulseOf, pulseRequest, pulseUrl, readAnswer, runPulse, tally } from "./src/lib/apiPulse.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };
const NOW = new Date("2026-11-08T04:00:00Z");
const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");

// ---- the secret header
t("the secret compares in full, and an empty secret never matches", () => {
  assert.equal(sameSecret("abc", "abc"), true);
  assert.equal(sameSecret("abd", "abc"), false);
  assert.equal(sameSecret("ab", "abc"), false);
  assert.equal(sameSecret("", ""), false, "no PULSE_SECRET set must not let an empty header in");
  assert.equal(sameSecret(null, "abc"), false);
  assert.equal(HEADER, "x-semasa-pulse");
});

// ---- the plan
const team = {
  gates: {
    rootsys: { kind: "openai", base: "https://rootsys.cloud/v1", host: "rootsys.cloud", key: "sk-root-1234", model: "glm-5.3-flashx", from: "AI_API_KEY secret" },
    kiosapi: { kind: "openai", base: "https://kiosapi.com/v1", host: "kiosapi.com", key: "sk-kios-9999", model: "", from: 'page AI slot "reader"' },
    gemini: { kind: "openai", base: "https://generativelanguage.googleapis.com/v1beta/openai", host: "generativelanguage.googleapis.com",
      keys: [{ id: "k1", key: "AIza-first", row: { id: "k1", calls: 3 } }, { id: "k2", key: "AIza-second", row: { id: "k2" } }], model: "gemini-3-pro", from: "Gemini keys (2 usable)" },
    chatgpt: { kind: "chatgpt", base: "https://chatgpt.com/backend-api/codex/responses", host: "chatgpt.com", model: "gpt-5.5", from: "ChatGPT login" },
  },
  robots: [
    { slug: "rootsys", enabled: true, why: "" },
    { slug: "mireld", enabled: false, why: "its key is only in GitHub's secrets, which Supabase cannot read: save it in a page AI slot (API tab) or as a function secret" },
    { slug: "kiosapi", enabled: true, why: "" },
    { slug: "gemini", enabled: true, why: "" },
    { slug: "chatgpt", enabled: true, why: "" },
  ],
  chatgptRow: { auth: { tokens: { refresh_token: "r" } }, model: "gpt-5.5", checked_at: "2026-11-08T03:00:00Z" },
};
const status = [
  { slug: "rootsys", name: "rootsys (Afiq)", role: "primary", model: "glm-5.3-flashx", models: ["glm-5.3-flashx", "kimi-k3"], chat_ok: true, checked_at: "2026-11-08T00:00:00Z", balance: { path: "/credits", credits: 12 } },
  { slug: "kiosapi", name: "KiosAPI (Wanshah 3)", role: "image", model: "gpt-image-2", models: ["gpt-image-2", "gpt-4.1-mini"], chat_ok: true, checked_at: "2026-11-08T00:00:00Z" },
  { slug: "gemini", name: "Gemini (Wanshah 4)", role: "primary", model: "gemini-3-pro", models: ["models/gemini-3-pro", "models/gemini-2.5-flash", "models/gemini-2.5-flash-lite"], chat_ok: true, checked_at: "2026-11-08T00:00:00Z" },
  { slug: "mireld", name: "Mireld", role: "backup", model: "claude-sonnet-5.5", models: ["claude-sonnet-5.5"], key_set: true, chat_ok: true, checked_at: "2026-11-08T00:00:00Z" },
];

t("every openai gate the edge holds a key for is probed, once, at its own address, and ChatGPT is never asked a question", () => {
  const plan = pulsePlan(team, status);
  assert.deepEqual(plan.probes.map((p) => p.slug).sort(), ["gemini", "kiosapi", "rootsys"]);
  const root = plan.probes.find((p) => p.slug === "rootsys");
  assert.equal(root.base, "https://rootsys.cloud/v1"); assert.equal(root.key, "sk-root-1234"); assert.equal(root.model, "glm-5.3-flashx"); assert.equal(root.chat, true);
  assert.ok(plan.chatgpt, "ChatGPT is in the plan from the login state");
  assert.equal(plan.chatgpt.row.model, "gpt-5.5");
});
t("the model Wan chose as a robot's own default is the one the pulse asks (settings.ai_team.models)", () => {
  const root = (models) => pulsePlan(team, status, models).probes.find((p) => p.slug === "rootsys");
  assert.equal(root({ rootsys: "kimi-k3" }).model, "kimi-k3");
  assert.equal(root({}).model, "glm-5.3-flashx", "nothing chosen: the configured model, as before");
  assert.equal(root(undefined).model, "glm-5.3-flashx");
  assert.equal(root({ mireld: "claude-fable-5.1" }).model, "glm-5.3-flashx", "another robot's choice does not move this one");
});
t("a robot whose key is only a GitHub secret is left to api.yml and named", () => {
  assert.deepEqual(pulsePlan(team, status).unreachable, ["mireld"]);
  assert.deepEqual(pulsePlan({ gates: {}, robots: [] }, []).unreachable, []);
});
t("a gate with no model configured and none in its row is listed but not asked a chat question", () => {
  const plan = pulsePlan(team, status.filter((r) => r.slug !== "kiosapi"));
  const k = plan.probes.find((p) => p.slug === "kiosapi");
  assert.equal(k.chat, false); assert.equal(k.model, "");
  const k2 = pulsePlan(team, status).probes.find((p) => p.slug === "kiosapi");
  assert.equal(k2.model, "gpt-image-2", "the row's model is used when the gate names none");
  assert.equal(k2.chat, false, "KiosAPI is a picture maker (role image, an image model): listed, never asked a chat question");
  assert.equal(k2.listOnly, true);
});
t("Gemini is probed on ONE key (the one the chat would use next) and the model the chat is configured with", () => {
  const g = pulsePlan(team, status).probes.find((p) => p.slug === "gemini");
  assert.equal(g.key, "AIza-first"); assert.equal(g.keyId, "k1"); assert.equal(g.keyRow.calls, 3);
  assert.notEqual(g.model, "gemini-2.5-flash-lite", "a model that is merely LISTED can be one Google no longer serves to this project (live 404, 8 Nov 2026)");
  assert.equal(geminiModel(["models/gemini-2.5-flash-lite", "models/gemini-3-pro"], "gemini-3-pro"), "gemini-3-pro", "the configured model wins when it is listed");
  assert.equal(geminiModel(["models/gemini-2.5-flash"], "gemini-3-pro"), "gemini-2.5-flash", "only when it is NOT listed does the cheapest listed one stand in");
  assert.equal(geminiModel([], "gemini-3-pro"), "gemini-3-pro", "with no list the configured model stands");
  assert.equal(geminiModel(null, ""), GEMINI_CHEAP[0]);
  assert.ok(chatBody(g).reasoning_effort === "low", "Gemini is told not to think over a five-token question");
  assert.equal(chatBody({ base: "https://rootsys.cloud/v1", model: "x" }).reasoning_effort, undefined);
  assert.equal(chatBody({ base: "https://rootsys.cloud/v1", model: "x" }).max_tokens, 5);
});
t("a Gemini gate with no usable key, or an openai gate with no key, is skipped rather than probed empty", () => {
  const plan = pulsePlan({ gates: { gemini: { kind: "openai", base: "https://g", keys: [] }, rootsys: { kind: "openai", base: "https://r", key: "" } }, robots: [] }, []);
  assert.deepEqual(plan.probes, []);
});

// ---- the measurements into rows
const root = pulsePlan(team, status).probes.find((p) => p.slug === "rootsys");
const prevRoot = status[0];
t("a robot that lists and answers reads up, keeps its role, name and balance from the probe's row, and never carries the key", () => {
  const row = statusRow(root, { listHttp: 200, listMs: 310, listed: ["glm-5.3-flashx", "kimi-k3", "new-model"], listError: "", chatOk: true, chatMs: 850, chatHttp: 200, chatError: "" }, prevRoot, NOW);
  assert.equal(row.slug, "rootsys"); assert.equal(row.role, "primary"); assert.equal(row.name, "rootsys (Afiq)");
  assert.deepEqual(row.balance, { path: "/credits", credits: 12 });
  assert.equal(row.reachable, true); assert.equal(row.key_ok, true); assert.equal(row.chat_ok, true); assert.equal(row.chat_ms, 850);
  assert.equal(row.http, 200); assert.equal(row.latency_ms, 310); assert.equal(row.model_listed, true);
  assert.deepEqual(row.models, ["glm-5.3-flashx", "kimi-k3", "new-model"], "a fresh list replaces the row's");
  assert.equal(row.key_last4, "1234"); assert.equal(row.key_set, true); assert.equal(row.checked_at, NOW.toISOString());
  assert.ok(!JSON.stringify(row).includes("sk-root"), "the key is not in the row");
  assert.equal(stateAfter(row, NOW.getTime()), "ok", "the chat reads this row as a healthy robot");
});
t("a refused key reads key_ok false and down; a time-out reads unreachable; the models are kept from the row when the pulse cannot list", () => {
  const refused = statusRow(root, { listHttp: 401, listMs: 120, listed: null, listError: "401 invalid api key", chatOk: false, chatMs: 130, chatHttp: 401, chatError: "401 invalid api key" }, prevRoot, NOW);
  assert.equal(refused.key_ok, false); assert.equal(refused.reachable, true); assert.equal(refused.chat_ok, false);
  assert.deepEqual(refused.models, ["glm-5.3-flashx", "kimi-k3"], "the probe's list is kept");
  assert.equal(refused.error, "401 invalid api key");
  assert.equal(stateAfter(refused, NOW.getTime()), "down");
  const out = statusRow(root, { listHttp: null, listMs: null, listed: null, listError: "timed out", chatOk: false, chatMs: null, chatHttp: 0, chatError: "timed out" }, prevRoot, NOW);
  assert.equal(out.reachable, false); assert.equal(out.key_ok, null); assert.equal(out.http, null);
  assert.equal(stateAfter(out, NOW.getTime()), "down");
});
t("a model that is listed but refuses reads reachable, key ok from the list, chat failed", () => {
  const row = statusRow(root, { listHttp: 200, listMs: 300, listed: ["glm-5.3-flashx"], listError: "", chatOk: false, chatMs: 400, chatHttp: 400, chatError: "400 model not found" }, prevRoot, NOW);
  assert.equal(row.reachable, true); assert.equal(row.key_ok, true); assert.equal(row.chat_ok, false); assert.equal(row.error, "400 model not found");
});
t("a chat that only timed out while the list answered is SLOW, not down: the last full answer is kept", () => {
  const prev = { ...prevRoot, chat_ok: true, chat_ms: 19000 };
  const row = statusRow(root, { listHttp: 200, listMs: 300, listed: ["glm-5.3-flashx"], listError: "", chatOk: false, chatMs: 8000, chatHttp: 0, chatError: "timed out" }, prev, NOW);
  assert.equal(row.chat_ok, true); assert.equal(row.chat_ms, 19000); assert.match(row.error, /^slow: no answer within 8 s/);
  const never = statusRow(root, { listHttp: 200, listMs: 300, listed: ["x"], listError: "", chatOk: false, chatMs: 8000, chatHttp: 0, chatError: "timed out" }, { ...prevRoot, chat_ok: false }, NOW);
  assert.equal(never.chat_ok, false, "a robot that was already down does not turn up because one answer was slow");
  const dead = statusRow(root, { listHttp: null, listMs: null, listed: null, listError: "timed out", chatOk: false, chatMs: 8000, chatHttp: 0, chatError: "timed out" }, prev, NOW);
  assert.equal(dead.chat_ok, false, "when the LIST does not answer either, the gateway is down");
});
t("a picture maker is judged by its model list alone and its error is the list's", () => {
  const k = { slug: "kiosapi", base: "https://kiosapi.com/v1", key: "k", model: "gpt-image-2", chat: false, listOnly: true };
  const up = statusRow(k, { listHttp: 200, listMs: 250, listed: ["gpt-image-2"], listError: "", chatOk: false, chatMs: null, chatHttp: 0, chatError: "" }, { name: "KiosAPI (Wanshah 3)", role: "image", chat_ms: 757 }, NOW);
  assert.equal(up.chat_ok, true); assert.equal(up.chat_ms, 757); assert.equal(up.error, ""); assert.equal(up.role, "image");
  const down = statusRow(k, { listHttp: 401, listMs: 250, listed: null, listError: "401 bad key", chatOk: false, chatMs: null, chatHttp: 0, chatError: "" }, null, NOW);
  assert.equal(down.chat_ok, false); assert.equal(down.error, "401 bad key");
});
t("a first row for a robot the probe never wrote gets the probe's names and role pulse", () => {
  const row = statusRow({ slug: "kiosapi", base: "https://kiosapi.com/v1", key: "k", model: "", chat: false }, { listHttp: 200, listMs: 200, listed: ["gpt-image-2"], listError: "", chatOk: false, chatMs: null, chatHttp: 0, chatError: "" }, null, NOW);
  assert.equal(row.name, NAMES.kiosapi); assert.equal(row.role, "pulse"); assert.deepEqual(row.balance, {});
  assert.equal(row.error, "no model configured"); assert.equal(row.chat_ok, false); assert.equal(row.model_listed, null);
});
t("the ChatGPT row follows the login state and keeps the 6-hourly probe's answer, since no question is sent", () => {
  const prev = { slug: "chatgpt", name: "ChatGPT (Wanshah 5)", role: "primary", model: "gpt-5.5", models: ["gpt-5.5"], chat_ok: true, chat_ms: 2200, base_url: "https://chatgpt.com/backend-api/codex" };
  const ok = chatgptRow(prev, { auth: { tokens: { refresh_token: "r" } }, model: "gpt-5.5", checked_at: "2026-11-08T03:00:00Z" }, NOW);
  assert.equal(ok.reachable, true); assert.equal(ok.key_ok, true); assert.equal(ok.chat_ok, true); assert.equal(ok.chat_ms, 2200); assert.equal(ok.role, "primary");
  const down = chatgptRow(prev, { auth: { tokens: { refresh_token: "r" } }, checked_at: "2026-11-08T03:00:00Z", last_error: "ChatGPT refused the saved login (401)", last_error_at: "2026-11-08T03:30:00Z" }, NOW);
  assert.equal(down.reachable, false); assert.equal(down.key_ok, false); assert.match(down.error, /refused the saved login/);
  const none = chatgptRow(null, null, NOW);
  assert.equal(none.key_set, false); assert.equal(none.key_ok, null); assert.match(none.error, /not connected/); assert.equal(none.name, NAMES.chatgpt);
});
t("usage and model lists are read as api_status.py reads them", () => {
  assert.deepEqual(usageOf({ usage: { prompt_tokens: 7, completion_tokens: 1 } }), { prompt_tokens: 7, completion_tokens: 1, total_tokens: 8 });
  assert.deepEqual(usageOf({ usage: { input_tokens: 3, output_tokens: 2, total_tokens: 9 } }), { prompt_tokens: 3, completion_tokens: 2, total_tokens: 9 });
  assert.deepEqual(usageOf({}), { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 });
  assert.deepEqual(modelIds({ data: [{ id: "b" }, { id: "a" }, { id: "a" }, {}] }), ["a", "b"]);
  assert.deepEqual(modelIds(["z", "y"]), ["y", "z"]);
  assert.deepEqual(modelIds(null), []);
});

// ---- what a pulse writes
t("pulseRows: status upserts, one zero-token usage row per answered chat (area pulse, never for ChatGPT), and the settings value", () => {
  const rows = [
    statusRow(root, { listHttp: 200, listMs: 310, listed: ["glm-5.3-flashx"], listError: "", chatOk: true, chatMs: 850, chatHttp: 200, chatError: "" }, prevRoot, NOW),
    statusRow({ slug: "kiosapi", base: "https://kiosapi.com/v1", key: "k", model: "gpt-4.1-mini", chat: true }, { listHttp: 200, listMs: 200, listed: ["gpt-4.1-mini"], listError: "", chatOk: false, chatMs: 400, chatHttp: 500, chatError: "500 upstream" }, status[1], NOW),
    chatgptRow(null, { auth: { tokens: { refresh_token: "r" } }, checked_at: "2026-11-08T03:00:00Z" }, NOW),
  ];
  const out = pulseRows(rows, { startedAt: NOW.getTime() - 4200, now: NOW, unreachable: ["mireld"], skipped: { chatgpt: "no chat sent" } });
  assert.equal(out.status.length, 3);
  assert.deepEqual(out.usage, [{ gateway: "rootsys", model: "glm-5.3-flashx", area: "pulse", ms: 850, ok: true, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 }]);
  assert.equal(out.settings.at, NOW.toISOString()); assert.equal(out.settings.took_ms, 4200); assert.equal(out.settings.every_min, CADENCE_MIN);
  assert.deepEqual(out.settings.unreachable_from_edge, ["mireld"]);
  assert.deepEqual(out.settings.results.rootsys, { ok: true, ms: 850, error: "" });
  assert.deepEqual(out.settings.results.kiosapi, { ok: false, ms: 400, error: "500 upstream" });
  assert.deepEqual(out.settings.results.chatgpt, { ok: true, ms: null, error: "", skipped: "no chat sent" });
  assert.ok(!JSON.stringify(out.settings).includes("1234"), "the settings row carries no key fragment");
});
t("flips: only a robot that answered before and fails now earns a log line", () => {
  const before = [{ slug: "rootsys", chat_ok: true }, { slug: "kiosapi", chat_ok: false }, { slug: "chatgpt", chat_ok: true }];
  const after = [{ slug: "rootsys", name: "rootsys (Afiq)", chat_ok: false, error: "timed out" }, { slug: "kiosapi", name: "KiosAPI", chat_ok: false, error: "x" }, { slug: "chatgpt", chat_ok: false }];
  assert.deepEqual(flips(before, after), [{ slug: "rootsys", name: "rootsys (Afiq)", error: "timed out" }]);
  assert.deepEqual(flips([], after), [], "a first pulse is never a flip");
});

// ---- the page
t("settings.api_pulse is read defensively, sorted, and an odd row is an empty pulse", () => {
  const p = pulseOf({ [PULSE_KEY]: { at: "2026-11-08T03:58:00Z", took_ms: 3100, every_min: 5, results: { rootsys: { ok: true, ms: 800 }, gemini: { ok: false, error: "429 quota" }, chatgpt: { ok: true, ms: null, skipped: "no chat" } }, unreachable_from_edge: ["mireld"] } });
  assert.deepEqual(p.results.map((r) => r.slug), ["chatgpt", "gemini", "rootsys"]);
  assert.equal(p.tookMs, 3100); assert.deepEqual(p.unreachable, ["mireld"]); assert.equal(p.results[1].error, "429 quota");
  assert.deepEqual(tally(p.results), { ok: 1, asked: 2, skipped: 1 });
  assert.deepEqual(pulseOf({}), { at: "", tookMs: 0, everyMin: EVERY_MIN, results: [], unreachable: [] });
  assert.deepEqual(pulseOf({ api_pulse: "junk" }).results, []);
  assert.deepEqual(pulseOf(null).results, []);
});
t("freshness: live within the cadence plus slack, late after a missed tick, stopped past twelve minutes, none when never pulsed", () => {
  const now = NOW.getTime();
  assert.equal(freshness("", now), "none");
  assert.equal(freshness("not a date", now), "none");
  assert.equal(freshness(new Date(now - 4 * 60_000).toISOString(), now), "live");
  assert.equal(freshness(new Date(now - 6 * 60_000).toISOString(), now), "live", "two minutes of slack for a slow tick");
  assert.equal(freshness(new Date(now - 9 * 60_000).toISOString(), now), "late");
  assert.equal(freshness(new Date(now - LATE_MS - 1000).toISOString(), now), "stopped");
});
t("the function's answer: a plain 404 is 'not deployed', an {error} is the error, {ok:true} is ok", () => {
  assert.deepEqual(readAnswer(404, null), { ok: false, missing: true, error: "" });
  assert.deepEqual(readAnswer(404, { error: "no such robot" }), { ok: false, missing: false, error: "no such robot" });
  assert.deepEqual(readAnswer(200, { ok: true, at: "x" }), { ok: true, missing: false, error: "" });
  assert.deepEqual(readAnswer(429, { error: "too often" }), { ok: false, missing: false, error: "too often" });
  assert.deepEqual(readAnswer(500, null), { ok: false, missing: false, error: "HTTP 500" });
  assert.equal(pulseUrl("https://x.supabase.co/"), "https://x.supabase.co/functions/v1/semasa-pulse");
  const req = pulseRequest({ url: "https://x.supabase.co", anon: "anon", token: "jwt" });
  assert.equal(req.init.headers.authorization, "Bearer jwt"); assert.equal(req.init.body, "{}");
  assert.equal(pulseRequest({ url: "https://x.supabase.co", anon: "anon", token: "" }), null, "no token, no call");
});
await (async () => {
  const calls = [];
  const fake = async (url, init) => { calls.push({ url, init }); return { status: 200, json: async () => ({ ok: true, at: "x" }) }; };
  const r = await runPulse({ url: "https://x.supabase.co", anon: "anon", token: "jwt" }, fake);
  assert.equal(r.ok, true); assert.equal(calls[0].url, "https://x.supabase.co/functions/v1/semasa-pulse");
  assert.ok(!JSON.stringify(calls[0].init).includes("service"), "only the login travels");
  const r2 = await runPulse({ url: "", anon: "", token: "" }, fake);
  assert.equal(r2.error, "sign in first"); assert.equal(calls.length, 1);
  const r3 = await runPulse({ url: "https://x", anon: "a", token: "t" }, async () => { throw new Error("offline"); });
  assert.equal(r3.error, "offline");
  n++;
})();

// ---- the files that carry the rest
t("the three pages read the status rows on realtime, and the API tab shows the pulse strip", () => {
  for (const f of ["ApiTab", "HomeTab", "TechOverviewTab"]) {
    const src = read(`./src/pages/${f}.jsx`);
    const line = src.split("\n").find((l) => l.includes("TABLES.apiStatus"));
    assert.ok(line && /realtime: true/.test(line) && /everyMs: 60_000/.test(line), `${f} reads semasa_api_status live with a 60 s poll behind it`);
  }
  const api = read("./src/pages/ApiTab.jsx");
  assert.ok(api.includes("<ApiPulse") && api.includes('import ApiPulse from "../components/ApiPulse"'));
  const strip = read("./src/components/ApiPulse.jsx");
  assert.ok(strip.includes("Semak sekarang") && strip.includes("runPulse") && strip.includes("realtime: true"), "the strip has the button and reads settings live");
  assert.ok(!/api_key|service_role/i.test(strip), "the strip never names a key");
  assert.ok(read("./src/lib/aiTeam.js").includes('u.area !== "pulse"'), "a pulse call never makes a robot read as actively writing");
});
t("supabase/075: realtime for the two tables (guarded), the clock function reading the Vault secret with a warning when missing, a 5-minute job", () => {
  const sql = read("../supabase/075_api_pulse.sql");
  assert.ok(sql.includes("array['semasa_api_status', 'semasa_settings']") && sql.includes("pg_publication_tables where pubname = 'supabase_realtime'"), "guarded publication add");
  assert.ok(sql.includes("create or replace function public.semasa_clock_pulse()"));
  assert.ok(sql.includes("where name = 'semasa_pulse_secret'") && sql.includes("clock.no_pulse_secret"), "the Vault secret is named and its absence logged once per 6 h");
  assert.ok(sql.includes("'x-semasa-pulse', v_secret") && sql.includes("https://mwaocnbgvbkhovktgods.supabase.co/functions/v1/semasa-pulse"));
  assert.ok(sql.includes("cron.schedule('semasa_pulse', '*/5 * * * *'"), "every 5 minutes");
  assert.ok(sql.includes("revoke execute on function public.semasa_clock_pulse() from public, anon, authenticated"));
  assert.ok(/PULSE_SECRET/.test(sql) && /SAME (random )?value/.test(sql), "the header says the two secrets share one value");
});
t("functions.yml deploys semasa-pulse without JWT verification and sets PULSE_SECRET from the GitHub secret with --yes", () => {
  const yml = read("../.github/workflows/functions.yml");
  assert.ok(/semasa-telegram\|semasa-pulse\) extra="--no-verify-jwt"/.test(yml), "the pulse's gate is its header, as Telegram's is");
  assert.ok(yml.includes('PULSE_SECRET: ${{ secrets.PULSE_SECRET }}'));
  assert.ok(/supabase secrets set "PULSE_SECRET=\$PULSE_SECRET" --project-ref "\$PROJECT_REF" --yes/.test(yml), "no terminal to confirm on");
  assert.ok(yml.includes('if [ -z "$PULSE_SECRET" ]'), "a missing secret is a notice, not a failed deploy");
});
t("the function imports the chat's team assembly rather than copying it, and never returns a key", () => {
  const ts = read("../supabase/functions/semasa-pulse/index.ts");
  assert.ok(ts.includes('from "../semasa-chat/logic.js"') && ts.includes("assembleTeam("));
  assert.ok(ts.includes('rpc("semasa_is_uploader")') && ts.includes("whoIs(fetch"), "an uploader's login is checked as semasa-chat checks it");
  assert.ok(ts.includes('Deno.env.get("PULSE_SECRET")') && ts.includes("sameSecret("));
  assert.ok(ts.includes("AbortSignal.timeout(ms)") && ts.includes("PULSE_TIMEOUT_MS"), "every call is capped");
  assert.ok(!/key_last4|\.key\b.*json\(/.test(ts.split("return json({ ok: true")[1] || ""), "the answer is the settings value, not the rows");
});

console.log(`apiPulse.test.mjs: ${n} checks passed`);
