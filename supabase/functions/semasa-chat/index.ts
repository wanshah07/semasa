// Semasa AI chat: the one place the page's chat reaches a model (web/src/lib/chat.js askAI calls this).
//
// Wan, 30 Sep 2026: "for AI chat link to open AI model claude-sonnet-5.5, Base URL https://api.mireld.my/v1".
//
// Why a function and not the browser: the page is public, so a key in it is every visitor's key. The key lives in this
// function's secrets and never leaves; the page sends only the conversation.
//
// Who may call it: a signed-in Semasa user. Checking the JWT alone is not enough, because the project's public anon
// key is itself a valid JWT and the project is shared with another app's users. So the caller must be found by
// auth.getUser AND pass public.semasa_is_uploader() (supabase/001_schema.sql), the same test Semasa's tables use.
//
// Secrets (Supabase dashboard → Edge Functions → Secrets, or `supabase secrets set`):
//   MIRELD_API_KEY    required (unless AI_API_KEY is set)
//   MIRELD_BASE_URL   optional, default https://api.mireld.my/v1
//   MIRELD_MODEL      optional, default claude-sonnet-5.5  (the "check" action says how Mireld spells it)
//   AI_API_KEY, AI_BASE_URL, AI_MODEL   the neutral names, for any OpenAI-compatible gateway (9 Oct 2026: Afiq's rootsys,
//                     https://rootsys.cloud/v1). When AI_API_KEY is set they win and MIRELD_* are ignored; AI_BASE_URL is then
//                     required, so a key never goes to a host it was not set for. AI_REPEAT_SYSTEM=1/0 forces the instructions to be
//                     repeated in the user turn (rootsys drops the system message, so it is on for that host by itself).
//
// Actions: {action:"chat", thread_id?, text, files, stream?, regenerate?}  (stream:true answers as SSE; regenerate answers the last
// question again)  and  {action:"check"}  (lists Mireld's models, asks the model the
// colour of a red square, which tells "accepts an image" from "reads one", and whether it calls tools), and
// {action:"faq_extract", note?, files}  (the FAQ page's AI bar, 1 Oct 2026: reads pictures, PDF text and typed text and
// returns the question-and-answer pairs found; writes nothing, see ./faq.js), {action:"models"} (the chat models Mireld lists,
// best default first; `chat` and `check` also take {model} to use another listed model for that call), and
// {action:"design_clone", image, width, height, stream, brief?, mode?}  (the Design tab: a reference picture read as a LAYOUT to
// rebuild as editable layers with new words, or with mode "inspire" an original layout in its visual language; see ./design.js), and
// {action:"design_refine", image, render, layout, width, height}  (the reference and the page's own rendering side by side; a
// corrected layout back, which is how the rebuild gets to "almost identical").
//
// 1 Oct 2026 (Wan: "let AI Chat access the website and any database live, ... memory stable and always remember"):
//   * MEMORY. History is kept in semasa_chat_* (supabase/025_chat_memory.sql), read and written with the CALLER's login
//     so row-level security is the only gate. Every call sends: the system rules, Wan's pinned notes, a rolling summary
//     of old turns, the recent turns. The page sends only the new message and a thread id.
//   * TOOLS (OpenAI function calling, at most 4 rounds): fetch_url, search_web, query_semasa, remember.
//       - fetch_url: https only, no IP literals or internal names, every resolved address checked, redirects re-checked.
//       - query_semasa: read only, an allow-list of Semasa tables, through the caller's login (RLS), secrets never listed.
//       - remember: only when Wan's own message asks for it; a web page cannot make the chat write a note.
//       - Whatever a page, a search or a table returns is handed to the model as UNTRUSTED data.
//     Optional secret BRAVE_API_KEY turns on search_web; without it that tool says it is not installed.
import { createClient } from "npm:@supabase/supabase-js@2";
import { cleanLayout, designMessages, keepWords, refineMessages } from "./design.js";
import { faqMessages, parseFaqItems } from "./faq.js";
import { firstJson } from "./faq.js";
import {
  MEMORY, SYSTEM, rankModels, resolveModel, TEST_IMAGE, TOOLS, UNTRUSTED, buildMessages, buildSystem, checkFetchUrl, checkReport, cleanNote, cors,
  OWN_HOSTS, RATE, allow, foldDelta, gatewayConfig, withInstructions, htmlToText, isPrivateIp, lastQuestion, parseArgs, pickFallback, planFold, planQuery, rateKind, readerMessage, retryPause, retryable,
  shapeRows, sseEvents, summaryMessages, userAskedToRemember, whoIs,
} from "./logic.js";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "content-type": "application/json" } });

async function upstream(base: string, key: string, path: string, init: RequestInit = {}, ms = 55000) {
  const res = await fetch(base.replace(/\/+$/, "") + path, {
    ...init,
    headers: { ...(init.headers || {}), authorization: `Bearer ${key}`, "content-type": "application/json" },
    signal: AbortSignal.timeout(ms),
  });
  const text = await res.text();
  let data: any = null;
  try { data = JSON.parse(text); } catch { /* not JSON */ }
  return { ok: res.ok, status: res.status, data, text };
}

const asText = (d: any) => {
  const c = d?.choices?.[0]?.message?.content;
  return typeof c === "string" ? c : Array.isArray(c) ? c.map((p: any) => p?.text || "").join("") : "";
};

let modelCache: { at: number; ids: string[] | null } = { at: 0, ids: null };   // Mireld's model list, kept five minutes
const MAX_BODY = 40_000_000;                                   // bytes: six pictures of 4 MB plus text; anything more is not a request
const hits = new Map<string, number[]>();                      // recent calls per user and kind (logic.js allow)

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const auth = req.headers.get("authorization") || "";
  const url = Deno.env.get("SUPABASE_URL"), anon = Deno.env.get("SUPABASE_ANON_KEY");
  if (!url || !anon) return json({ error: "function is missing SUPABASE_URL / SUPABASE_ANON_KEY" }, 500);
  const declared = Number(req.headers.get("content-length") || 0);
  if (declared > MAX_BODY) return json({ error: "the request is too large" }, 413);
  try { const own = new URL(url).hostname.toLowerCase(); if (own && !OWN_HOSTS.includes(own)) OWN_HOSTS.push(own); } catch { /* keep the list as is */ }
  const db = createClient(url, anon, { global: { headers: { authorization: auth } } });
  const token = auth.replace(/^Bearer\s+/i, "").trim(); // pass the JWT: a server client has no stored session
  // Say WHY sign-in failed (never the token itself), so the check button tells us what to fix.
  if (!token) return json({ error: "sign in first (no login token reached the function)" }, 401);
  if (token === anon) return json({ error: "sign in first (the page sent the public key, not your login; sign out and in again)" }, 401);
  const who = await whoIs(fetch, url, anon, token);
  if (!who.user) return json({ error: `sign in first (${who.why})` }, 401);
  const { data: allowed, error: rpcErr } = await db.rpc("semasa_is_uploader");
  if (rpcErr) return json({ error: `could not check the Semasa user list (${String(rpcErr.message || rpcErr).slice(0, 120)})` }, 500);
  if (allowed !== true) return json({ error: "this account is not a Semasa user" }, 403);

  const gw = gatewayConfig((k: string) => Deno.env.get(k));
  if (gw.error) return json({ error: gw.error }, 503);
  const { key, base, model: envModel } = gw;
  if (!key) return json({ error: `${gw.keyName} is not set on the function` }, 503);
  const outbound = (p: any) => (gw.repeatSystem && p?.messages ? { ...p, messages: withInstructions(p.messages) } : p);
  let model = envModel || "claude-sonnet-5.5";            // the default; the page may ask for another (below)
  if (!/^https:\/\//.test(base)) return json({ error: `${gw.baseName} must be https` }, 500);
  const uid = who.user.id;

  let body: any;
  try {
    const raw = await req.text();
    if (raw.length > MAX_BODY) return json({ error: "the request is too large" }, 413);
    body = JSON.parse(raw);
  } catch { return json({ error: "body is not JSON" }, 400); }
  if (!body || typeof body !== "object") return json({ error: "body is not JSON" }, 400);

  // ---- rate guard: a flood from one login is slowed, never the whole function
  const kind = rateKind(String(body.action || "chat"));
  if (kind) {
    const k = `${uid}:${kind}`;
    const list = hits.get(k) || [];
    const gate = allow(list, Date.now(), RATE[kind as keyof typeof RATE][0], RATE[kind as keyof typeof RATE][1]);
    hits.set(k, list);
    if (!gate.ok) return new Response(JSON.stringify({ error: `terlalu banyak permintaan; cuba lagi dalam ${gate.retryAfter} saat / too many requests; try again in ${gate.retryAfter} seconds` }),
      { status: 429, headers: { ...cors, "content-type": "application/json", "retry-after": String(gate.retryAfter) } });
    if (hits.size > 5000) hits.clear();                     // a map that only grows is a leak; starting over costs one window of leniency
  }

  // ---- which model answers (Wan, 1 Oct 2026): the one the page asked for if Mireld lists it, else the default. The default is
  // MIRELD_MODEL when set, else the best of Mireld's list by logic.js MODEL_PREFERENCE (Sonnet 5.5 first).
  async function listModelIds(): Promise<string[] | null> {
    if (modelCache.ids && Date.now() - modelCache.at < 300000) return modelCache.ids;
    const l = await upstream(base, key, "/models", { method: "GET" }, 15000).catch(() => null);
    if (l?.ok && Array.isArray(l.data?.data)) {
      const ids = l.data.data.map((m: any) => String(m?.id || "")).filter(Boolean);
      modelCache = { at: Date.now(), ids };
      return ids;
    }
    return null;
  }
  let modelIds: string[] | null = null;
  if (body?.model || body?.action === "models" || (!envModel && gw.name !== "Mireld")) modelIds = await listModelIds();
  const ranked = rankModels(modelIds, envModel || "claude-sonnet-5.5");
  const defaultModel = envModel || ranked.recommended || "claude-sonnet-5.5";
  const picked = resolveModel(body?.model, modelIds, defaultModel);
  model = picked.model;

  // ---- reader calls (faq_extract, design_clone, design_refine): streamed, and asked once more on another model --------------
  // One attempt: the answer is STREAMED so the gateway sees the first token at once (its "first-output deadline" is what failed a long
  // layout when the call was not streamed), and the pieces are folded back into one text. Never throws.
  type Read = { ok: boolean; status: number; content: string; err: string };
  async function readOnce(payload: any, ms: number): Promise<Read> {
    try {
      const res = await fetch(base.replace(/\/+$/, "") + "/chat/completions", {
        method: "POST", headers: { authorization: `Bearer ${key}`, "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify(outbound({ ...payload, stream: true })), signal: AbortSignal.timeout(ms),
      });
      const type = res.headers.get("content-type") || "";
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "");
        let j: any = null; try { j = JSON.parse(text); } catch { /* not JSON */ }
        return { ok: false, status: res.status, content: "", err: String(j?.error?.message || text).slice(0, 200) };
      }
      if (!/event-stream/.test(type)) {                      // a gateway that ignores stream:true answers one JSON
        const j: any = await res.json().catch(() => null);
        return { ok: true, status: res.status, content: asText(j), err: "" };
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "", acc: any = null;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const { events, rest } = sseEvents(buf);
        buf = rest;
        for (const ev of events) {
          if (ev.trim() === "[DONE]") continue;
          let chunk: any = null; try { chunk = JSON.parse(ev); } catch { continue; }
          if (chunk?.error) return { ok: false, status: Number(chunk.error?.code) || 502, content: "", err: String(chunk.error?.message || chunk.error).slice(0, 200) };
          acc = foldDelta(acc, chunk);
        }
      }
      return { ok: true, status: res.status, content: acc?.content || "", err: "" };
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return { ok: false, status: 0, content: "", err: /abort|time/i.test(msg) ? "the model did not answer in time" : msg.slice(0, 200) };
    }
  }
  /** The reader's answer. First the chosen model; if that fails in a way another try could fix (a deadline, a timeout, a 5xx, an empty
      answer), once more on the best OTHER model Mireld lists (or the same one when it lists no other). 70 s then 50 s, so both fit
      inside the function's own limit. `tried` names the models asked, for the error the page shows. */
  async function readerCall(payload: any): Promise<Read & { model: string; tried: string[] }> {
    const tried: string[] = [];
    let last: Read = { ok: false, status: 0, content: "", err: "no answer" };
    let used = model;
    for (let i = 0; i < 2; i++) {
      used = i === 0 ? model : (pickFallback(await listModelIds(), model) || model);
      tried.push(used);
      last = await readOnce({ ...payload, model: used }, i === 0 ? 70000 : 50000);
      if (last.ok && last.content.trim()) return { ...last, model: used, tried };
      if (!last.ok && !retryable(last.status, last.err)) break;
      const pause = last.ok ? 0 : retryPause(last.status, last.err);          // a gateway being upgraded may be back in seconds
      if (pause && i === 0) await new Promise((r) => setTimeout(r, pause));
    }
    return { ...last, ok: false, model: used, tried };
  }
  const readerError = (r: Read & { tried: string[] }) => readerMessage({ ...r, gateway: gw.name });

  // ---- tools -------------------------------------------------------------------------------------------
  async function addressesOk(host: string): Promise<string | null> {
    const found: string[] = [];
    for (const type of ["A", "AAAA"] as const) {
      try { found.push(...(await Deno.resolveDns(host, type))); } catch { /* none of this type */ }
    }
    if (!found.length) return "the host name did not resolve";
    if (found.some((ip) => isPrivateIp(ip))) return "the host resolves to a private address";
    return null;
  }

  async function fetchUrl(raw: string): Promise<string> {
    let current = String(raw || "");
    for (let hop = 0; hop < 4; hop++) {
      const ok = checkFetchUrl(current);
      if (!ok.ok) return `fetch_url refused: ${ok.why}`;
      const bad = await addressesOk(ok.host);
      if (bad) return `fetch_url refused: ${bad}`;
      const res = await fetch(ok.url, {
        redirect: "manual", signal: AbortSignal.timeout(15000),
        headers: { "user-agent": "SemasaChat/1.0", accept: "text/html,text/plain,application/json;q=0.9,*/*;q=0.1" },
      });
      if (res.status >= 300 && res.status < 400 && res.headers.get("location")) {
        current = new URL(res.headers.get("location")!, ok.url).toString();
        continue;
      }
      const type = (res.headers.get("content-type") || "").toLowerCase();
      if (/pdf|image\/|audio\/|video\/|zip|octet-stream/.test(type)) return `fetch_url: HTTP ${res.status}, ${type.split(";")[0]} cannot be read as text yet (PDF/Word not supported here).`;
      const reader = res.body?.getReader();
      let got = new Uint8Array(0);
      if (reader) {
        const parts: Uint8Array[] = []; let n = 0;
        while (n < 1_500_000) {
          const { done, value } = await reader.read();
          if (done || !value) break;
          parts.push(value); n += value.length;
        }
        try { await reader.cancel(); } catch { /* already closed */ }
        got = new Uint8Array(n); let o = 0;
        for (const p of parts) { got.set(p, o); o += p.length; }
      }
      const raw2 = new TextDecoder("utf-8", { fatal: false }).decode(got);
      const text = /html/.test(type) || /^\s*<(!doctype|html)/i.test(raw2) ? htmlToText(raw2, 8000) : raw2.slice(0, 8000);
      return `${UNTRUSTED}URL: ${ok.url}\nHTTP ${res.status}\n${text}`;
    }
    return "fetch_url refused: too many redirects";
  }

  async function searchWeb(q: string): Promise<string> {
    const k = Deno.env.get("BRAVE_API_KEY");
    if (!k) return "search_web belum dipasang: tiada BRAVE_API_KEY pada fungsi. Guna fetch_url dengan URL yang diketahui.";
    const query = String(q || "").trim().slice(0, 200);
    if (!query) return "search_web: empty query";
    const res = await fetch(`https://api.search.brave.com/res/v1/web/search?q=${encodeURIComponent(query)}&count=5`, {
      headers: { "x-subscription-token": k, accept: "application/json" }, signal: AbortSignal.timeout(15000),
    });
    if (!res.ok) return `search_web: HTTP ${res.status}`;
    const j: any = await res.json().catch(() => null);
    const items = (j?.web?.results || []).slice(0, 5).map((r: any) => ({ title: String(r.title || "").slice(0, 160), url: r.url, snippet: String(r.description || "").replace(/<[^>]+>/g, "").slice(0, 300) }));
    return UNTRUSTED + JSON.stringify(items);
  }

  async function querySemasa(args: unknown): Promise<string> {
    const plan = planQuery(args);
    if (!plan.ok) return `query_semasa refused: ${plan.why}`;
    let q: any = db.from(plan.table).select(plan.columns.length ? plan.columns.join(",") : "*");
    for (const [col, op, val] of plan.filters) q = q[op === "neq" ? "neq" : op](col, val);
    if (plan.order) q = q.order(plan.order.column, { ascending: plan.order.ascending });
    const { data, error } = await q.limit(plan.limit);
    if (error) return `query_semasa: ${String(error.message || error).slice(0, 160)}`;
    return UNTRUSTED + JSON.stringify({ table: plan.table, rows: shapeRows(data) });
  }

  async function remember(note: unknown, userText: string): Promise<{ text: string; saved: boolean }> {
    if (!userAskedToRemember(userText)) return { text: "Nota tidak disimpan: mesej Wan ini tidak meminta anda mengingatinya.", saved: false };
    const n = cleanNote(note);
    if (!n) return { text: "Nota tidak disimpan: mesti 3 hingga 500 aksara.", saved: false };
    const { count } = await db.from("semasa_chat_memory").select("id", { count: "exact", head: true });
    if ((count ?? 0) >= MEMORY.notes) return { text: `Nota tidak disimpan: sudah ada ${MEMORY.notes} nota. Minta Wan padam yang lama.`, saved: false };
    const { error } = await db.from("semasa_chat_memory").insert({ user_id: uid, note: n, source: "chat" });
    return error ? { text: `Nota tidak disimpan: ${String(error.message).slice(0, 100)}`, saved: false } : { text: "Nota disimpan.", saved: true };
  }

  try {
    // ---- models: what the page's picker offers (Wan, 1 Oct 2026) ------------------------------------------
    if (body?.action === "models") {
      if (!modelIds) return json({ models: [], recommended: ranked.recommended, default: defaultModel, listed: false, gateway: gw.name });
      return json({ models: ranked.models, recommended: ranked.recommended, default: defaultModel, listed: true, gateway: gw.name });
    }

    // ---- check: models, picture reading, tool calling -------------------------------------------------
    if (body?.action === "check") {
      let ids: string[] | null = null;
      const list = await upstream(base, key, "/models", { method: "GET" }, 20000).catch((e) => ({ ok: false, status: 0, data: null, text: String(e) }));
      if (list.ok && Array.isArray(list.data?.data)) ids = list.data.data.map((m: any) => String(m?.id || "")).filter(Boolean);
      const probe = await upstream(base, key, "/chat/completions", {
        method: "POST",
        body: JSON.stringify({
          model, max_tokens: 20, temperature: 0,
          messages: [{ role: "user", content: [
            { type: "text", text: "What colour is this image? Answer with one word." },
            { type: "image_url", image_url: { url: TEST_IMAGE } }] }],
        }),
      }).catch((e) => ({ ok: false, status: 0, data: null, text: String(e) }));
      const image = probe.ok ? { answer: asText(probe.data) }
        : { error: `HTTP ${probe.status}: ${String(probe.data?.error?.message || probe.text).slice(0, 160)}` };
      const tp = await upstream(base, key, "/chat/completions", {
        method: "POST",
        body: JSON.stringify({
          model, max_tokens: 60, temperature: 0, tool_choice: "auto",
          tools: [{ type: "function", function: { name: "ping", description: "Reply to the user by calling this.", parameters: { type: "object", properties: { word: { type: "string" } }, required: ["word"] } } }],
          messages: [{ role: "user", content: "Call the ping tool with word = hello. Do not answer in text." }],
        }),
      }).catch((e) => ({ ok: false, status: 0, data: null, text: String(e) }));
      const tools = tp.ok ? { calls: Array.isArray(tp.data?.choices?.[0]?.message?.tool_calls) && tp.data.choices[0].message.tool_calls.length > 0 }
        : { error: `HTTP ${tp.status}: ${String(tp.data?.error?.message || tp.text).slice(0, 160)}` };
      return json({ ...checkReport(model, ids, image, tools), base_url: base, gateway: gw.name, list_status: list.status, search_configured: !!Deno.env.get("BRAVE_API_KEY") });
    }

    // ---- faq_extract: the FAQ page's AI bar (Wan, 1 Oct 2026) -------------------------------------------
    // Reads pictures / PDF text / typed text and returns the Q&A pairs found, anonymised. It writes nothing: the page
    // shows them and inserts the ones kept as `new` FAQ rows, and backend/semasa/faq.py rewrites and categorises them.
    if (body?.action === "faq_extract") {
      const built = faqMessages(body?.note, body?.files);
      if (built.error) return json({ error: built.error, skipped: built.skipped }, 400);
      const r = await readerCall({ max_tokens: 6000, temperature: 0, messages: built.messages });
      if (!r.ok) return json({ error: readerError(r) }, 502);
      const parsed = parseFaqItems(r.content);
      if (parsed.error) return json({ error: parsed.error, skipped: built.skipped }, 502);
      return json({ items: parsed.items, skipped: parsed.skipped, not_read: built.skipped, pictures: built.pictures, files: built.files, model: r.model });
    }

    // ---- design_clone: the Design tab's "rebuild this design" (Wan, 1 Oct 2026) ----------------------------
    // Reads a reference picture as a layout artist would and returns a LAYOUT (background, shapes, photo areas, text blocks with
    // place, size, colour and type style), never a picture. With a `brief` it also writes the new words for each text block under
    // the post rules; without one the page supplies the words. Logos, brand names, URLs, calls to action and faces are never
    // rebuilt, and are listed in `removed` (their boxes in layout.covers, for patching). `mode: "inspire"` composes an ORIGINAL
    // layout in the reference's visual language instead of describing its arrangement. It writes nothing: the page lays the
    // layout out as editable layers in Kanvas.
    if (body?.action === "design_clone") {
      const built = designMessages({ image: body?.image, width: body?.width, height: body?.height, stream: body?.stream, brief: body?.brief, mode: body?.mode });
      if (built.error) return json({ error: built.error }, 400);
      const r = await readerCall({ max_tokens: 6000, temperature: built.mode === "inspire" ? 0.5 : 0.1, messages: built.messages });
      if (!r.ok) return json({ error: readerError(r) }, 502);
      const cleaned = cleanLayout(firstJson(r.content));
      if (cleaned.error) return json({ error: cleaned.error }, 502);
      return json({ layout: cleaned.layout, removed: cleaned.removed, has_words: built.hasBrief, mode: built.mode, model: r.model });
    }

    // ---- design_refine: reference and rebuild side by side, a corrected layout back (same day) ---------------------------
    // The page draws the layout, sends the reference and the drawing together, and the reader moves, resizes and recolours the
    // elements until the two match. The words are never the reader's to change here: `keepWords` copies them back.
    if (body?.action === "design_refine") {
      const built = refineMessages({ image: body?.image, render: body?.render, layout: body?.layout, width: body?.width, height: body?.height });
      if (built.error) return json({ error: built.error }, 400);
      const r = await readerCall({ max_tokens: 6000, temperature: 0, messages: built.messages });
      if (!r.ok) return json({ error: readerError(r) }, 502);
      const cleaned = cleanLayout(firstJson(r.content));
      if (cleaned.error) return json({ error: cleaned.error }, 502);
      const before = cleanLayout(body.layout).layout;
      return json({ layout: keepWords(before, cleaned.layout), removed: cleaned.removed, model: r.model });
    }

    // ---- chat: thread, memory, tools, streaming -----------------------------------------------------------
    // {stream:true} answers as Server-Sent Events (data: {type:"delta",text} ... {type:"done",...}) so the page shows the words as they
    // come, like Claude; without it the answer is one JSON as before. {regenerate:true, thread_id} drops the last answer and answers the
    // last question again (its attachments are not re-sent).
    const wantStream = body?.stream === true;
    const regenerate = body?.regenerate === true;
    let userText = String(body?.text ?? "").trim();
    if (!userText && !regenerate) return json({ error: Array.isArray(body?.messages) ? "this page is an old version: reload it" : "empty message" }, 400);
    if (regenerate && !body?.thread_id) return json({ error: "nothing to answer again: no conversation" }, 400);

    let threadId: string | null = body?.thread_id ? String(body.thread_id) : null;
    let thread: any = null;
    if (threadId) {
      const { data, error } = await db.from("semasa_chat_threads").select("id,summary,summarized_upto").eq("id", threadId).maybeSingle();
      if (error) return json({ error: `could not open the conversation (${String(error.message).slice(0, 100)})` }, 500);
      thread = data;
      if (!thread) return json({ error: "that conversation was not found" }, 404);
    } else {
      const { data, error } = await db.from("semasa_chat_threads").insert({ user_id: uid, title: userText.slice(0, 60) }).select("id,summary,summarized_upto").single();
      if (error) return json({ error: `could not start a conversation (${String(error.message).slice(0, 100)}). Has supabase/025_chat_memory.sql been run?` }, 500);
      thread = data; threadId = data.id;
    }

    const { data: storedRows } = await db.from("semasa_chat_messages").select("id,role,content")
      .eq("thread_id", threadId).gt("id", thread.summarized_upto || 0).order("id", { ascending: true }).limit(200);
    const stored: any[] = storedRows || [];
    if (regenerate) {
      const last = stored[stored.length - 1];
      if (last?.role === "assistant") { await db.from("semasa_chat_messages").delete().eq("id", last.id); stored.pop(); }
      userText = lastQuestion(stored);
      if (!userText) return json({ error: "nothing to answer again: no question in this conversation" }, 400);
    }
    const plan = planFold(stored);
    let summary: string = thread.summary || "";
    if (plan.fold.length) {
      const r = await upstream(base, key, "/chat/completions", { method: "POST", body: JSON.stringify(outbound({ model, max_tokens: 1800, temperature: 0.2, messages: summaryMessages(summary, plan.fold) })) }).catch(() => null);
      const t = r?.ok ? asText(r.data).trim() : "";
      if (t) {
        summary = t.slice(0, 12000);
        await db.from("semasa_chat_threads").update({ summary, summarized_upto: plan.upto }).eq("id", threadId);
      }
    }
    const { data: noteRows } = await db.from("semasa_chat_memory").select("id,note").order("created_at", { ascending: true }).limit(MEMORY.notes * 2);

    const fileNames = (Array.isArray(body?.files) ? body.files : []).map((f: any) => String(f?.name || "")).filter(Boolean).slice(0, 8);
    if (!regenerate) {
      const saved = await db.from("semasa_chat_messages").insert({ thread_id: threadId, user_id: uid, role: "user", content: userText + (fileNames.length ? `\n[lampiran: ${fileNames.join(", ")}]` : "") });
      if (saved.error) return json({ error: `could not save your message (${String(saved.error.message).slice(0, 100)})` }, 500);
    }

    let toolsOn = body?.tools !== false;
    const system = buildSystem({ notes: noteRows || [], summary, now: new Date(), tools: toolsOn });
    const recent = plan.recent.map((m: any) => ({ role: m.role, text: m.content }));
    const history = regenerate && recent.length && recent[recent.length - 1].role === "user" ? recent : [...recent, { role: "user", text: userText }];
    const built = buildMessages(history, regenerate ? [] : body?.files, system);
    const msgs: any[] = built.messages;

    // one upstream call, streamed or not, answered in one shape: { ok, status, content, toolCalls, model, err }
    type Turn = { ok: boolean; status: number; content: string; toolCalls: { id: string; name: string; arguments: string }[]; model: string; err: string };
    async function turn(payload: any, onText: (t: string) => void): Promise<Turn> {
      const path = base.replace(/\/+$/, "") + "/chat/completions";
      if (!wantStream) {
        const r = await upstream(base, key, "/chat/completions", { method: "POST", body: JSON.stringify(outbound(payload)) });
        if (!r.ok) return { ok: false, status: r.status, content: "", toolCalls: [], model: "", err: String(r.data?.error?.message || r.text).slice(0, 200) };
        const m = r.data?.choices?.[0]?.message;
        const calls = (Array.isArray(m?.tool_calls) ? m.tool_calls : []).map((c: any) => ({ id: String(c?.id || ""), name: String(c?.function?.name || ""), arguments: typeof c?.function?.arguments === "string" ? c.function.arguments : JSON.stringify(c?.function?.arguments || {}) }));
        return { ok: true, status: r.status, content: asText(r.data), toolCalls: calls, model: String(r.data?.model || ""), err: "" };
      }
      const res = await fetch(path, { method: "POST", headers: { authorization: `Bearer ${key}`, "content-type": "application/json", accept: "text/event-stream" },
        body: JSON.stringify(outbound({ ...payload, stream: true })), signal: AbortSignal.timeout(110000) });
      if (!res.ok || !res.body) {
        const text = await res.text().catch(() => "");
        let j: any = null; try { j = JSON.parse(text); } catch { /* not JSON */ }
        return { ok: false, status: res.status, content: "", toolCalls: [], model: "", err: String(j?.error?.message || text).slice(0, 200) };
      }
      const type = res.headers.get("content-type") || "";
      if (!/event-stream/.test(type)) {                       // a gateway that ignores stream:true answers one JSON: read it as such
        const j: any = await res.json().catch(() => null);
        const m = j?.choices?.[0]?.message;
        const calls = (Array.isArray(m?.tool_calls) ? m.tool_calls : []).map((c: any) => ({ id: String(c?.id || ""), name: String(c?.function?.name || ""), arguments: typeof c?.function?.arguments === "string" ? c.function.arguments : JSON.stringify(c?.function?.arguments || {}) }));
        const content = asText(j);
        if (content) onText(content);
        return { ok: true, status: res.status, content, toolCalls: calls, model: String(j?.model || ""), err: "" };
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "", acc: any = null;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const { events, rest } = sseEvents(buf);
        buf = rest;
        for (const ev of events) {
          if (ev.trim() === "[DONE]") continue;
          let chunk: any = null; try { chunk = JSON.parse(ev); } catch { continue; }
          if (chunk?.error) return { ok: false, status: 502, content: "", toolCalls: [], model: "", err: String(chunk.error?.message || chunk.error).slice(0, 200) };
          const before = acc?.content || "";
          acc = foldDelta(acc, chunk);
          if (acc.content.length > before.length) onText(acc.content.slice(before.length));
        }
      }
      acc = acc || { content: "", toolCalls: [], finish: null, model: "" };
      return { ok: true, status: res.status, content: acc.content, toolCalls: acc.toolCalls.filter((c: any) => c.name), model: acc.model, err: "" };
    }

    // the whole exchange, with `emit` telling the page what is happening (a no-op when not streaming)
    async function runChat(emit: (o: any) => void) {
      const used: string[] = [];
      let memorySaved = false, toolsNote = "";
      let final = "", shown = "", lastModel = model;
      for (let round = 0; round < 5 && !final; round++) {
        const withTools = toolsOn && round < 4;
        const payload = { model, messages: msgs, max_tokens: 2400, temperature: 0.3, ...(withTools ? { tools: TOOLS, tool_choice: "auto" } : {}) };
        let r = await turn(payload, (t) => emit({ type: "delta", text: t }));
        if (!r.ok && withTools && r.status === 400) {      // this model/gateway does not take tools: answer without them, and say so
          toolsOn = false; toolsNote = "tools_unsupported";
          r = await turn({ model, messages: msgs, max_tokens: 2400, temperature: 0.3 }, (t) => emit({ type: "delta", text: t }));
        }
        if (!r.ok) throw new Error(`the model answered HTTP ${r.status}: ${r.err}`);
        if (r.model) lastModel = r.model;
        if (r.toolCalls.length && withTools) {
          if (r.content.trim()) shown += (shown ? "\n\n" : "") + r.content.trim();
          msgs.push({ role: "assistant", content: r.content || null, tool_calls: r.toolCalls.map((c) => ({ id: c.id, type: "function", function: { name: c.name, arguments: c.arguments } })) });
          for (const c of r.toolCalls.slice(0, 3)) {
            const name = c.name, args = parseArgs(c.arguments);
            emit({ type: "status", tool: name, detail: String(args.url || args.query || args.table || "").slice(0, 120) });
            let out = "unknown tool";
            try {
              if (name === "fetch_url") out = await fetchUrl(String(args.url || ""));
              else if (name === "search_web") out = await searchWeb(String(args.query || ""));
              else if (name === "query_semasa") out = await querySemasa(args);
              else if (name === "remember") { const x = await remember(args.note, userText); out = x.text; memorySaved = memorySaved || x.saved; }
            } catch (e) { out = `${name} failed: ${String(e instanceof Error ? e.message : e).slice(0, 120)}`; }
            used.push(name);
            msgs.push({ role: "tool", tool_call_id: c.id, content: out.slice(0, 9000) });
          }
          if (r.content.trim()) emit({ type: "delta", text: "\n\n" });
          continue;
        }
        final = r.content.trim();
        if (!final) throw new Error("the model answered with nothing");
        if (shown) final = shown + "\n\n" + final;
      }
      if (!final) throw new Error("the model kept calling tools and never answered");
      await db.from("semasa_chat_messages").insert({ thread_id: threadId, user_id: uid, role: "assistant", content: final, tools: used.length ? [...new Set(used)] : null });
      return { text: final, thread_id: threadId, model: lastModel, tools: [...new Set(used)], memory_saved: memorySaved, notice: toolsNote || undefined, sent: built.sent,
        ...(picked.changed ? { model_changed: { asked: picked.asked, used: model } } : {}) };
    }

    if (!wantStream) return json(await runChat(() => {}));
    const enc = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        const emit = (o: any) => { try { controller.enqueue(enc.encode(`data: ${JSON.stringify(o)}\n\n`)); } catch { /* the page went away */ } };
        emit({ type: "start", thread_id: threadId, model });
        try {
          emit({ type: "done", ...(await runChat(emit)) });
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          emit({ type: "error", error: /timed? ?out|abort/i.test(msg) ? "the model did not answer in time" : msg.slice(0, 200) });
        }
        try { controller.close(); } catch { /* already closed */ }
      },
    });
    return new Response(stream, { headers: { ...cors, "content-type": "text/event-stream; charset=utf-8", "cache-control": "no-cache", "x-accel-buffering": "no" } });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ error: /timed? ?out|abort/i.test(msg) ? "the model did not answer in time" : msg.slice(0, 200) }, 502);
  }
});
