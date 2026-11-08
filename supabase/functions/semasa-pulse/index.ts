// semasa-pulse: the API status refreshed every 5 minutes and shown live (feature B, 8 Nov 2026).
//
// The 6-hourly probe (backend/semasa/api_status.py, api.yml) is the authority on every robot; this function does the same small
// check from the edge far more often, for the robots whose key the edge can already reach: the same gates the AI chat assembles
// (../semasa-chat/logic.js assembleTeam, read with the service role: function secrets AI_*/MIRELD_*, the page's AI slots,
// semasa_gemini_keys, semasa_chatgpt_auth). Each gate gets GET /models and one five-token chat, in parallel, capped at 8 s.
// Gemini: one key, its cheapest listed model. ChatGPT: no call (its check is refused by design); the row says what the login
// state says. A robot whose key is only a GitHub secret (LLM_* fallbacks) is left to api.yml and named in settings.api_pulse as
// unreachable_from_edge.
//
// It writes: semasa_api_status rows by slug (the columns api_status.py writes; role and models kept from the row when the pulse
// cannot say), semasa_api_usage rows area "pulse" (zero tokens, like the probe, so ai_team.health sees the call), the settings row
// `api_pulse` {at, took_ms, every_min, results:{slug:{ok, ms, error}}, unreachable_from_edge}, and one semasa_log warn when a robot
// that answered last time fails now. It never returns a key, a key's last4 or a row with a key in it.
//
// Who may call it (deployed --no-verify-jwt, like semasa-telegram):
//   * the database clock: POST with header x-semasa-pulse = function secret PULSE_SECRET (supabase/075_api_pulse.sql,
//     pg_cron `semasa_pulse` every 5 minutes, the secret from Vault `semasa_pulse_secret`; the two must hold the SAME value);
//   * a signed-in Semasa uploader: Authorization: Bearer <their JWT>, checked with auth.getUser + semasa_is_uploader() exactly as
//     semasa-chat does ("Semak sekarang" on the API page). Six presses per ten minutes per login.
// Two callers at once share one run (a pulse already under way answers both).
//
// Secrets: PULSE_SECRET (functions.yml sets it from the GitHub secret of the same name), SUPABASE_SERVICE_ROLE_KEY (given by
// Supabase), and whatever semasa-chat already has (AI_API_KEY/AI_BASE_URL/AI_MODEL or MIRELD_*).
import { createClient } from "npm:@supabase/supabase-js@2";
import { allow, assembleTeam, cors, geminiKeyPatch, netError, whoIs } from "../semasa-chat/logic.js";
import {
  CADENCE_MIN, HEADER, PULSE_TIMEOUT_MS, SETTINGS_KEY, chatBody, chatgptRow, flips, modelIds, pulsePlan, pulseRows, sameSecret, statusRow, usageOf,
} from "./logic.js";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "content-type": "application/json" } });

const hits = new Map<string, number[]>();                     // presses per login (logic.js allow)
const RATE: [number, number] = [6, 600_000];
let running: Promise<any> | null = null;                       // one pulse at a time on this instance; callers join it

/** One call to a gateway, never throwing: a time-out or DNS failure is { ok:false, status:0 } (semasa-chat upstream). */
async function call(base: string, key: string, path: string, init: RequestInit = {}, ms = PULSE_TIMEOUT_MS) {
  const t0 = Date.now();
  try {
    const res = await fetch(base.replace(/\/+$/, "") + path, {
      ...init, headers: { ...(init.headers || {}), authorization: `Bearer ${key}`, "content-type": "application/json" },
      signal: AbortSignal.timeout(ms),
    });
    const text = await res.text();
    let data: any = null;
    try { data = JSON.parse(text); } catch { /* not JSON */ }
    return { ok: res.ok, status: res.status, data, text, ms: Date.now() - t0 };
  } catch (e) {
    return { ok: false, status: 0, data: null, text: netError(e), ms: Date.now() - t0 };
  }
}

/** GET /models and the five-token chat for one robot, at the same time, each under the cap. */
async function measure(p: any) {
  const [list, chat] = await Promise.all([
    call(p.base, p.key, "/models", { method: "GET" }),
    (async () => {
      if (!p.chat) return null;
      const body = chatBody(p);
      let r = await call(p.base, p.key, "/chat/completions", { method: "POST", body: JSON.stringify(body) });
      if (r.status === 400 && "reasoning_effort" in body && /reasoning/i.test(r.text)) {
        delete body.reasoning_effort;                          // a model that does not take the field is asked plainly
        r = await call(p.base, p.key, "/chat/completions", { method: "POST", body: JSON.stringify(body) });
      }
      return r;
    })(),
  ]);
  const errOf = (r: any) => (r.ok ? "" : r.status ? `${r.status} ${String(r.data?.error?.message || r.text || "").slice(0, 200)}` : r.text);
  return {
    listHttp: list.status || null, listMs: list.status ? list.ms : null, listed: list.ok ? modelIds(list.data) : null, listError: list.ok ? "" : errOf(list),
    chatOk: !!chat?.ok, chatMs: chat ? chat.ms : null, chatHttp: chat?.status || 0, chatError: chat ? errOf(chat) : "", usage: chat?.ok ? usageOf(chat.data) : null,
  };
}

async function pulse(admin: any) {
  const startedAt = Date.now();
  const [st, sets, cfg, sec, gk, ga] = await Promise.all([
    admin.from("semasa_api_status").select("*"),
    admin.from("semasa_settings").select("key,value").in("key", ["gemini", "gemini_models"]),
    admin.from("semasa_ai_config").select("slot,provider,base_url,model,key_host"),
    admin.from("semasa_ai_secrets").select("slot,api_key"),
    admin.from("semasa_gemini_keys").select("id,api_key,enabled,status,cooldown_until,last_used_at,last_ok_at,calls,failures"),
    admin.from("semasa_chatgpt_auth").select("auth,model,checked_at,last_ok_at,last_error,last_error_at").eq("id", "main").maybeSingle(),
  ]);
  if (st.error) throw new Error(`semasa_api_status could not be read (${String(st.error.message).slice(0, 120)}): run supabase/035_repos_api.sql`);
  const setting = (k: string) => ((sets.data || []).find((r: any) => r.key === k)?.value) || {};
  const keyOf = new Map((sec.data || []).map((r: any) => [r.slot, r.api_key]));
  const slots = (cfg.data || []).map((r: any) => ({ ...r, api_key: keyOf.get(r.slot) || "" }));
  const prevRows = st.data || [];
  const team = assembleTeam({ env: (k: string) => Deno.env.get(k), slots, status: prevRows, serviceRole: true,
    gemini: { settings: setting("gemini"), models: setting("gemini_models"), keys: gk.data || [] }, chatgpt: { row: ga.data || null } });
  const plan = pulsePlan({ ...team, chatgptRow: ga.data || null }, prevRows);
  const prev = Object.fromEntries(prevRows.map((r: any) => [r.slug, r]));
  const now = new Date();

  const rows: any[] = await Promise.all(plan.probes.map(async (p: any) => {
    const m = await measure(p);
    if (p.slug === "gemini" && p.keyId != null) {            // the key's own marks, as the chat and the worker write them
      await admin.from("semasa_gemini_keys").update(geminiKeyPatch(p.keyRow, m.chatOk, m.chatHttp, m.chatError)).eq("id", p.keyId).then(() => {}, () => {});
    }
    return statusRow(p, m, prev[p.slug] || null, now);
  }));
  const skipped: Record<string, string> = {};
  if (plan.chatgpt) {
    rows.push(chatgptRow(prev.chatgpt || null, plan.chatgpt.row, now));
    skipped.chatgpt = "no chat sent: ChatGPT's check is refused by design; the state is the login's";
  }
  const out = pulseRows(rows, { startedAt, now, unreachable: plan.unreachable, skipped });

  const writes: Promise<any>[] = [];
  if (out.status.length) writes.push(admin.from("semasa_api_status").upsert(out.status, { onConflict: "slug" }));
  if (out.usage.length) writes.push(admin.from("semasa_api_usage").insert(out.usage));
  writes.push(admin.from("semasa_settings").upsert({ key: SETTINGS_KEY, value: out.settings }, { onConflict: "key" }));
  const broke = flips(prevRows, out.status);
  if (broke.length) {
    writes.push(admin.from("semasa_log").insert({ level: "warn", area: "api", event: "api_pulse.down",
      title: "Denyut API: " + broke.map((b) => `${b.name} gagal`).join(", "),
      detail: { robots: broke, every_min: CADENCE_MIN } }));
  }
  const results = await Promise.all(writes.map((w) => w.then((r: any) => r, (e: any) => ({ error: e }))));
  const failed = results.map((r: any) => r?.error).filter(Boolean).map((e: any) => String(e.message || e).slice(0, 120));
  // what goes back to the caller: the settings value (no key, no last4) plus which writes failed
  return { ...out.settings, probed: out.status.map((r: any) => r.slug), write_errors: failed };
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  const url = Deno.env.get("SUPABASE_URL") || "", anon = Deno.env.get("SUPABASE_ANON_KEY") || "", service = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!url || !anon || !service) return json({ error: "function is missing SUPABASE_URL / SUPABASE_ANON_KEY / SUPABASE_SERVICE_ROLE_KEY" }, 500);

  // ---- who is calling: the clock with the shared secret, or a signed-in Semasa uploader
  const pulseSecret = Deno.env.get("PULSE_SECRET") || "";
  const byClock = sameSecret(req.headers.get(HEADER) || "", pulseSecret);
  if (!byClock) {
    const token = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "").trim();
    if (!token) return json({ error: `sign in first (no login token reached the function${pulseSecret ? "" : "; PULSE_SECRET is not set either"})` }, 401);
    if (token === anon) return json({ error: "sign in first (the page sent the public key, not your login; sign out and in again)" }, 401);
    const who = await whoIs(fetch, url, anon, token);
    if (!who.user) return json({ error: `sign in first (${who.why})` }, 401);
    const db = createClient(url, anon, { global: { headers: { authorization: `Bearer ${token}` } } });
    const { data: allowed, error: rpcErr } = await db.rpc("semasa_is_uploader");
    if (rpcErr) return json({ error: `could not check the Semasa user list (${String(rpcErr.message || rpcErr).slice(0, 120)})` }, 500);
    if (allowed !== true) return json({ error: "this account is not a Semasa user" }, 403);
    const list = hits.get(who.user.id) || [];
    const gate = allow(list, Date.now(), RATE[0], RATE[1]);
    hits.set(who.user.id, list);
    if (hits.size > 1000) hits.clear();
    if (!gate.ok) return new Response(JSON.stringify({ error: `terlalu kerap; cuba lagi dalam ${gate.retryAfter} saat / too often; try again in ${gate.retryAfter} seconds` }),
      { status: 429, headers: { ...cors, "content-type": "application/json", "retry-after": String(gate.retryAfter) } });
  }

  const admin = createClient(url, service, { auth: { persistSession: false, autoRefreshToken: false } });
  try {
    if (!running) running = pulse(admin).finally(() => { running = null; });
    const result = await running;
    return json({ ok: true, by: byClock ? "clock" : "page", ...result });
  } catch (e) {
    return json({ error: String((e as any)?.message || e).slice(0, 300) }, 500);
  }
});
