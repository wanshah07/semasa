/* semasa-pulse: the pure half of the API pulse (index.ts does the calling and the writing). Node runs this file in
   web/apiPulse.test.mjs, so nothing here touches Deno, fetch or a database.

   What a pulse is: the same probe backend/semasa/api_status.py runs every 6 hours, done from the edge every 5 minutes for the
   robots whose key the edge can reach (the chat's own team: logic.js assembleTeam). Each robot gets GET /models and one
   five-token chat, both capped at PULSE_TIMEOUT_MS. Gemini is asked on one key and its cheapest listed model. ChatGPT is never
   asked (its check is refused by design in semasa-chat): its row is marked reachable from the login state alone. A robot whose key
   is only a GitHub secret cannot be pulsed from here and is left to api.yml, named in the settings row as unreachable_from_edge. */
import { CHAT_ROBOTS, chatgptState, cleanModelId, probeState } from "../semasa-chat/logic.js";

export const PULSE_TIMEOUT_MS = 8000;
export const SETTINGS_KEY = "api_pulse";
export const USAGE_AREA = "pulse";
export const CADENCE_MIN = 5;                       // the cron in supabase/075_api_pulse.sql
export const HEADER = "x-semasa-pulse";
/** Gemini's cheapest chat models, cheapest first (a 5-token question wants the smallest bill, never the configured 3.x Pro). */
export const GEMINI_CHEAP = ["gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-flash-latest"];
/** The row names api_status.py writes (NAMES), so a row the pulse creates reads the same as one the 6-hourly probe wrote. */
export const NAMES = { rootsys: "rootsys (Afiq)", mireld: "Mireld", kiosapi: "KiosAPI (Wanshah 3)", gemini: "Gemini (Wanshah 4)", chatgpt: "ChatGPT (Wanshah 5)" };

/** Constant-time string compare for the pulse secret (the same shape semasa-telegram uses for its header). */
export function sameSecret(got, want) {
  if (typeof got !== "string" || typeof want !== "string" || !want || got.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return diff === 0;
}

/** The Gemini model a pulse asks: the cheapest of GEMINI_CHEAP that the robot lists, else the configured one. */
export function geminiModel(listed, configured) {
  const ids = new Set((Array.isArray(listed) ? listed : []).map((x) => cleanModelId(String(x || "").replace(/^models\//, ""))));
  for (const m of GEMINI_CHEAP) if (ids.has(m)) return m;
  return cleanModelId(configured) || GEMINI_CHEAP[0];
}

/** What to probe, from assembleTeam's answer and the current status rows.
    { probes: [{slug, kind, base, key, keyId, keyRow, model, chat}], chatgpt: {slug, row, gate} | null, unreachable: [slug] }.
    `chat` is false when no model is known for the robot (api_status.py says "no model configured" for that). */
export function pulsePlan(team, statusRows = []) {
  const status = Object.fromEntries((statusRows || []).filter((r) => r?.slug).map((r) => [r.slug, r]));
  const probes = [], unreachable = [];
  for (const [slug, g] of Object.entries(team?.gates || {})) {
    if (!g || g.kind !== "openai") continue;
    const row = status[slug];
    let key = g.key || "", keyId = null, keyRow = null;
    if (slug === "gemini") {                                           // one key, the one the chat would use next
      const k = Array.isArray(g.keys) ? g.keys[0] : null;
      if (!k?.key) continue;
      key = k.key; keyId = k.id ?? null; keyRow = k.row || null;
    }
    if (!key || !g.base) continue;
    let model = cleanModelId(g.model) || cleanModelId(row?.model) || "";
    if (slug === "gemini") model = geminiModel(row?.models, model);
    probes.push({ slug, kind: "openai", base: g.base, key, keyId, keyRow, model, chat: !!model, from: g.from || "" });
  }
  for (const r of team?.robots || []) {
    if (r?.slug && !r.enabled && /GitHub's secrets/i.test(String(r.why || ""))) unreachable.push(r.slug);
  }
  const gpt = team?.gates?.chatgpt ? { slug: "chatgpt", gate: team.gates.chatgpt, row: team.chatgptRow || null } : null;
  return { probes, chatgpt: gpt, unreachable };
}

/** {prompt_tokens, completion_tokens, total_tokens} from a chat answer (api_status.usage_of). */
export function usageOf(j) {
  const u = j && typeof j === "object" ? j.usage : null;
  if (!u || typeof u !== "object") return { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 };
  const p = Number(u.prompt_tokens || u.input_tokens || 0) || 0, c = Number(u.completion_tokens || u.output_tokens || 0) || 0;
  return { prompt_tokens: p, completion_tokens: c, total_tokens: Number(u.total_tokens) || p + c };
}

/** Model ids out of a /models answer, sorted, at most 300 (api_status._models). */
export function modelIds(data) {
  const items = Array.isArray(data?.data) ? data.data : Array.isArray(data) ? data : [];
  return [...new Set(items.map((m) => String((m && typeof m === "object" ? m.id : m) || "")).filter(Boolean))].sort().slice(0, 300);
}

/** The body of the five-token question (api_status._chat): Gemini is told not to think first. */
export function chatBody(probe) {
  const body = { model: probe.model, max_tokens: 5, messages: [{ role: "user", content: "Say OK" }] };
  if (/generativelanguage\.googleapis\.com/.test(String(probe.base || ""))) body.reasoning_effort = "low";
  return body;
}

const clip = (s, n) => String(s || "").replace(/\s+/g, " ").slice(0, n);

/** One probe's measurements into the semasa_api_status row api_status.py would write.
    `m` = { listHttp, listMs, listed: string[]|null, listError, chatOk, chatMs, chatError, netError }. The row the probe wrote
    before (`prev`) keeps its role, name, balance and models when this pulse could not list. */
export function statusRow(probe, m, prev = null, now = new Date()) {
  const meta = CHAT_ROBOTS[probe.slug] || null;
  const listed = Array.isArray(m.listed) ? m.listed : null;
  const models = listed && listed.length ? listed : (Array.isArray(prev?.models) ? prev.models : []);
  const http = Number.isFinite(m.listHttp) ? m.listHttp : null;
  // a host that answered anything (a model list, a chat, even a refusal with a status) is reachable; a time-out or DNS failure is not
  const reachable = http !== null || m.chatOk === true || (Number.isFinite(m.chatHttp) && m.chatHttp > 0);
  let keyOk = http === null ? null : !(http === 401 || http === 403);
  if (m.chatOk) keyOk = true;
  const named = models.map((x) => String(x).replace(/^models\//, ""));
  const modelListed = models.length && probe.model ? named.includes(String(probe.model).replace(/^models\//, "")) : null;
  const error = clip(m.listError || "", 200) || clip(m.chatError || "", 300);
  return {
    slug: probe.slug,
    name: prev?.name || NAMES[probe.slug] || (meta ? meta.provider : probe.slug),
    role: prev?.role || "pulse",
    base_url: String(probe.base || "").replace(/\/+$/, ""),
    key_set: true,
    key_last4: probe.key ? String(probe.key).slice(-4) : "",
    model: probe.model || prev?.model || "",
    model_listed: modelListed,
    reachable: !!reachable,
    http,
    latency_ms: Number.isFinite(m.listMs) ? m.listMs : null,
    key_ok: keyOk,
    chat_ok: probe.chat ? m.chatOk === true : false,
    chat_ms: Number.isFinite(m.chatMs) ? m.chatMs : null,
    models,
    balance: prev?.balance && typeof prev.balance === "object" ? prev.balance : {},
    error: probe.chat ? error : (error || "no model configured"),
    checked_at: now.toISOString(),
  };
}

/** ChatGPT's row from the login state alone: no call is made (its check is refused by design). The row keeps the 6-hourly
    probe's chat_ok, models and model; reachable/key_ok follow chatgptState. */
export function chatgptRow(prev, authRow, now = new Date()) {
  const st = chatgptState(authRow, now.getTime());
  const connected = !!authRow?.auth?.tokens?.refresh_token;
  return {
    slug: "chatgpt", name: prev?.name || NAMES.chatgpt, role: prev?.role || "pulse",
    base_url: prev?.base_url || "https://chatgpt.com/backend-api/codex", key_set: connected, key_last4: "",
    model: prev?.model || cleanModelId(authRow?.model) || "", model_listed: prev?.model_listed ?? null,
    reachable: connected && st.state !== "down", http: prev?.http ?? null, latency_ms: prev?.latency_ms ?? null,
    key_ok: !connected ? null : st.state === "down" ? false : true,
    chat_ok: prev?.chat_ok ?? null, chat_ms: prev?.chat_ms ?? null,
    models: Array.isArray(prev?.models) ? prev.models : [], balance: prev?.balance || {},
    error: !connected ? "not connected: paste auth.json on the API page" : st.state === "down" ? clip(st.why, 300) : "",
    checked_at: now.toISOString(),
  };
}

/** Everything a pulse writes, from the rows statusRow/chatgptRow built: the api_status upserts, the usage rows (area "pulse",
    zero tokens like the 6-hourly probe, only for a chat that answered) and the settings value the page reads. */
export function pulseRows(rows, { startedAt, now = new Date(), unreachable = [], skipped = {} } = {}) {
  const list = Array.isArray(rows) ? rows.filter(Boolean) : [];
  const usage = list.filter((r) => r.chat_ok === true && r.slug !== "chatgpt").map((r) => ({
    gateway: r.slug, model: r.model || "", area: USAGE_AREA, ms: r.chat_ms || 0, ok: true,
    prompt_tokens: 0, completion_tokens: 0, total_tokens: 0,
  }));
  const results = {};
  for (const r of list) {
    const ok = r.slug === "chatgpt" ? r.reachable === true && r.key_ok !== false : r.chat_ok === true;
    results[r.slug] = { ok, ms: r.chat_ms ?? r.latency_ms ?? null, error: ok ? "" : clip(r.error, 200), ...(skipped[r.slug] ? { skipped: skipped[r.slug] } : {}) };
  }
  const took = Number.isFinite(startedAt) ? Math.max(0, now.getTime() - startedAt) : 0;
  return { status: list, usage, settings: { at: now.toISOString(), took_ms: took, every_min: CADENCE_MIN, results, unreachable_from_edge: [...unreachable] } };
}

/** Robots that flipped from answering to failing since their previous row: the one thing worth a log line every 5 minutes. */
export function flips(prevRows, nextRows) {
  const prev = Object.fromEntries((prevRows || []).filter((r) => r?.slug).map((r) => [r.slug, r]));
  return (nextRows || []).filter((r) => r && r.slug !== "chatgpt" && prev[r.slug]?.chat_ok === true && r.chat_ok === false)
    .map((r) => ({ slug: r.slug, name: r.name, error: clip(r.error, 160) }));
}

/** The page's reading of a robot's state after a pulse, the same rule the chat uses (probeState), for the test. */
export const stateAfter = (row, now = Date.now()) => probeState(row, now).state;
