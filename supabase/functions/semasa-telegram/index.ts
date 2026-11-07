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
import { inboxRow, instantReply, kindOf, linkCode, sameSecret } from "./logic.js";

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
  const { data: link } = await db.from("semasa_telegram_link").select("telegram_user_id").eq("id", 1).maybeSingle();
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

  const row = inboxRow(update, kind, owner);
  const { error } = await db.from("semasa_telegram_inbox").upsert(row, { onConflict: "update_id", ignoreDuplicates: true });
  if (error) {
    console.error("inbox write failed", error.message);
    owner = false;            // nothing was stored, so do not promise work
  }
  return ok(instantReply(kind, update, { linked: !!link, owner }) ?? { ok: true });
});
