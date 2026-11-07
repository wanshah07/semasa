// Semasa's Telegram webhook (Wan, 7 Nov 2026: "communicate from telegram, approve post and attach link so semasa can read").
//
// Telegram POSTs every update here. This function:
//   1. checks the X-Telegram-Bot-Api-Secret-Token header against TELEGRAM_WEBHOOK_SECRET (set by functions.yml from the
//      bot token; anything without it is refused, so nobody else can feed the inbox);
//   2. links Wan's Telegram account when he sends the one-time code from the page (semasa_telegram_claim);
//   3. stores the update in semasa_telegram_inbox (the database wakes the "Telegram" workflow for his messages and taps);
//   4. answers at once with a method in the response body ("typing…", "Sedang diproses…"), so it never holds the bot token.
// It never approves, writes an idea or calls a model: backend/semasa/telegram_bot.py does, for the linked account only.
//
// Deployed with --no-verify-jwt (Telegram sends no Supabase login); the secret header is the gate.
import { createClient } from "npm:@supabase/supabase-js@2";
import { BUSY_WINDOW_MS, fastEligible, fastMessages, fastReply, inboxRow, instantReply, kindOf, linkCode, newestNotes, sameSecret, turnsOf } from "./logic.js";
import { MEMORY, gatewayConfig, withInstructions } from "../semasa-chat/logic.js";

const FAST_MS = 22000;        // Telegram waits for the webhook's answer; past this the worker answers instead

/** A plain question answered here with the AI chat's gateway: the answer, or null to hand it to the worker. */
async function fastAnswer(db: any, link: any, text: string, pin: any, state: any, busy: boolean) {
  const gw = gatewayConfig((k: string) => Deno.env.get(k));
  if (gw.error || !gw.key || !gw.model || !fastEligible({ kind: "private", text, owner: true, state, pin, gwName: gw.name, busy })) return null;
  const [notesQ, msgsQ, draftsQ] = await Promise.all([
    // the newest notes, as the AI chat allows them (MEMORY.notes); ascending with a limit kept the oldest ones
    db.from("semasa_chat_memory").select("note").eq("user_id", link.user_id).order("created_at", { ascending: false }).limit(MEMORY.notes),
    state?.thread_id ? db.from("semasa_chat_messages").select("role,content,id").eq("thread_id", state.thread_id).order("id", { ascending: false }).limit(16)
      : Promise.resolve({ data: [] }),
    db.from("semasa_posts").select("status").in("status", ["draft", "approved", "scheduled"]),
  ]);
  const posts = draftsQ.data || [];
  const count = (s: string) => posts.filter((p: any) => p.status === s).length;
  const snapshot = `Draf menunggu: ${count("draft")} · Diluluskan: ${count("approved")} · Dijadualkan: ${count("scheduled")}`;
  let messages = fastMessages({ text, notes: newestNotes(notesQ.data || [], MEMORY.notes), turns: turnsOf((msgsQ.data || []).reverse()),
    snapshot, gwName: gw.name, model: gw.model });
  if (gw.repeatSystem) messages = withInstructions(messages);
  try {
    const res = await fetch(gw.base.replace(/\/+$/, "") + "/chat/completions", {
      method: "POST", signal: AbortSignal.timeout(FAST_MS),
      headers: { authorization: `Bearer ${gw.key}`, "content-type": "application/json" },
      body: JSON.stringify({ model: gw.model, messages, max_tokens: 900, temperature: 0.3 }),
    });
    if (!res.ok) return null;
    const j = await res.json();
    const answer = String(j?.choices?.[0]?.message?.content || "").trim();
    return answer ? { answer, who: `${gw.name} · ${j?.model || gw.model}` } : null;
  } catch {
    return null;
  }
}

/** Keep the exchange in the AI chat page's Telegram thread, as the worker does (telegram_tools.log_turn). */
async function logTurn(db: any, link: any, state: any, question: string, answer: string) {
  let tid = state?.thread_id;
  if (!tid) {
    const { data } = await db.from("semasa_chat_threads").insert({ user_id: link.user_id, title: "Telegram" }).select("id").single();
    tid = data?.id;
    if (tid) {
      // only thread_id is ours: merged onto a fresh read taken now, never onto the copy read before the model answered (the
      // worker writes pending, await_note, likes and videos_sent to the same row in the meantime)
      const { data: fresh } = await db.from("semasa_settings").select("value").eq("key", "telegram_chat").maybeSingle();
      await db.from("semasa_settings").upsert({ key: "telegram_chat", value: { ...(fresh?.value || {}), thread_id: tid } }, { onConflict: "key" });
    }
  }
  if (tid) await db.from("semasa_chat_messages").insert([{ thread_id: tid, user_id: link.user_id, role: "user", content: question },
    { thread_id: tid, user_id: link.user_id, role: "assistant", content: answer }]);
}

const ok = (body: unknown = { ok: true }) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("method not allowed", { status: 405 });
  const secret = Deno.env.get("TELEGRAM_WEBHOOK_SECRET") || "";
  if (!sameSecret(req.headers.get("x-telegram-bot-api-secret-token") || "", secret)) {
    return new Response("forbidden", { status: 403 });
  }
  let update: any;
  try {
    update = await req.json();
  } catch {
    return ok();
  }
  if (typeof update?.update_id !== "number") return ok();

  const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
    auth: { persistSession: false },
  });
  const kind = kindOf(update);
  const { data: link } = await db.from("semasa_telegram_link").select("telegram_user_id,user_id").eq("id", 1).maybeSingle();
  const from = update?.callback_query?.from?.id ?? update?.message?.from?.id ?? null;
  let owner = !!link && Number(link.telegram_user_id) === Number(from);

  // the one-time code from Semasa → Settings → Telegram links this account (only in a private chat)
  if (kind === "private") {
    const code = linkCode(update.message?.text);
    if (code) {
      const { data: claimed } = await db.rpc("semasa_telegram_claim", {
        p_code: code, p_telegram_user_id: from, p_chat_id: update.message.chat.id,
        p_username: update.message.from?.username ?? update.message.from?.first_name ?? null,
      });
      await db.from("semasa_telegram_inbox").upsert({ ...inboxRow(update, "other", false), note: claimed ? "linked" : "bad code" },
        { onConflict: "update_id", ignoreDuplicates: true });
      return ok({
        method: "sendMessage", chat_id: update.message.chat.id,
        text: claimed
          ? "Bersambung ✅ Semasa kini boleh dikawal dari sini. Taip /help untuk senarai arahan.\nLinked ✅ Type /help for the commands."
          : "Kod tidak sah atau sudah tamat (15 minit). Jana kod baharu di Semasa → Tetapan → Telegram.",
      });
    }
  }

  // a plain question from Wan: answered here in seconds when it can be, else the worker answers (30-60 s)
  if (kind === "private" && owner && fastEligible({ kind, text: update.message?.text, owner, state: {}, pin: null, gwName: "" })) {
    const [{ data: st }, { data: team }, { data: waiting }] = await Promise.all([
      db.from("semasa_settings").select("value").eq("key", "telegram_chat").maybeSingle(),
      db.from("semasa_settings").select("value").eq("key", "ai_team").maybeSingle(),
      // anything of his the worker has not finished (a 👎 or a menu tap whose pending/await_note is not written yet)
      db.from("semasa_telegram_inbox").select("id").eq("chat_id", update.message.chat.id).in("kind", ["private", "callback"])
        .in("status", ["new", "working"]).gte("created_at", new Date(Date.now() - BUSY_WINDOW_MS).toISOString()).limit(1),
    ]);
    const state = st?.value || {};
    // unreadable counts as busy: the worker then answers in order, as it did before the fast path
    const busy = waiting == null || waiting.length > 0;
    const fast = await fastAnswer(db, link, String(update.message.text), team?.value?.pins?.reader || null, state, busy);
    if (fast) {
      const { data: saved } = await db.from("semasa_telegram_inbox").upsert(
        { ...inboxRow(update, kind, owner), status: "done", note: `answered (fast, ${fast.who}): ${fast.answer.slice(0, 700)}`,
          done_at: new Date().toISOString() }, { onConflict: "update_id", ignoreDuplicates: true }).select("id").maybeSingle();
      try { await logTurn(db, link, state, String(update.message.text), fast.answer); } catch (e) { console.error("turn not kept", String(e)); }
      return ok(fastReply(update.message.chat.id, update.message.message_id, fast.answer, fast.who, saved?.id ?? 0));
    }
  }

  const row = inboxRow(update, kind, owner);
  const { error } = await db.from("semasa_telegram_inbox").upsert(row, { onConflict: "update_id", ignoreDuplicates: true });
  if (error) {
    console.error("inbox write failed", error.message);
    owner = false;            // nothing was stored, so do not promise work
  }
  return ok(instantReply(kind, update, { linked: !!link, owner }) ?? { ok: true });
});
