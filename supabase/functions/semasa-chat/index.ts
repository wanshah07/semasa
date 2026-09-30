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
//   MIRELD_API_KEY    required
//   MIRELD_BASE_URL   optional, default https://api.mireld.my/v1
//   MIRELD_MODEL      optional, default claude-sonnet-5.5  (the "check" action says how Mireld spells it)
//
// Actions: {action:"chat", messages, files}  and  {action:"check"}  (lists Mireld's models and asks the model the
// colour of a red square, which tells "accepts an image" from "reads one").
import { createClient } from "npm:@supabase/supabase-js@2";
import { SYSTEM, TEST_IMAGE, buildMessages, checkReport, cors } from "./logic.js";

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

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  const auth = req.headers.get("authorization") || "";
  const url = Deno.env.get("SUPABASE_URL"), anon = Deno.env.get("SUPABASE_ANON_KEY");
  if (!url || !anon) return json({ error: "function is missing SUPABASE_URL / SUPABASE_ANON_KEY" }, 500);
  const db = createClient(url, anon, { global: { headers: { authorization: auth } } });
  const { data: who } = await db.auth.getUser();
  if (!who?.user) return json({ error: "sign in first" }, 401);
  const { data: allowed } = await db.rpc("semasa_is_uploader");
  if (allowed !== true) return json({ error: "this account is not a Semasa user" }, 403);

  const key = Deno.env.get("MIRELD_API_KEY");
  if (!key) return json({ error: "MIRELD_API_KEY is not set on the function" }, 503);
  const base = Deno.env.get("MIRELD_BASE_URL") || "https://api.mireld.my/v1";
  const model = Deno.env.get("MIRELD_MODEL") || "claude-sonnet-5.5";
  if (!/^https:\/\//.test(base)) return json({ error: "MIRELD_BASE_URL must be https" }, 500);

  let body: any;
  try { body = await req.json(); } catch { return json({ error: "body is not JSON" }, 400); }

  try {
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
      return json({ ...checkReport(model, ids, image), base_url: base, list_status: list.status });
    }

    const { messages, sent } = buildMessages(body?.messages, body?.files, SYSTEM);
    const r = await upstream(base, key, "/chat/completions", {
      method: "POST", body: JSON.stringify({ model, messages, max_tokens: 1800, temperature: 0.3 }),
    });
    if (!r.ok) {
      const why = String(r.data?.error?.message || r.text).slice(0, 200);
      return json({ error: `the model answered HTTP ${r.status}: ${why}` }, 502);
    }
    const text = asText(r.data).trim();
    if (!text) return json({ error: "the model answered with nothing" }, 502);
    return json({ text, model: r.data?.model || model, sent });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return json({ error: /timed? ?out|abort/i.test(msg) ? "the model did not answer in time" : msg.slice(0, 200) }, 502);
  }
});
