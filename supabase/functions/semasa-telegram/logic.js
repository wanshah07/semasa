// The Telegram webhook's decisions, kept pure so web/telegram.test.mjs can test them with node (index.ts does the I/O).
//
// One rule above all: this function only RECORDS what Telegram sends and answers at once. It never approves, writes an
// idea or calls a model; the worker (backend/semasa/telegram_bot.py) does that, for the one linked Telegram account only.

/** Constant-time compare of Telegram's X-Telegram-Bot-Api-Secret-Token with ours. */
export function sameSecret(got, want) {
  if (typeof got !== "string" || typeof want !== "string" || !want || got.length !== want.length) return false;
  let diff = 0;
  for (let i = 0; i < want.length; i++) diff |= got.charCodeAt(i) ^ want.charCodeAt(i);
  return diff === 0;
}

/** What kind of update this is: "private" (a message to the bot), "callback" (a button tap), "group" (a message in a
 *  group the bot sits in, for the FAQ reader) or "other" (joins, edits, channels: stored, never acted on). */
export function kindOf(update) {
  if (update?.callback_query) return "callback";
  const m = update?.message;
  if (!m) return "other";
  const type = m.chat?.type;
  if (type === "private") return "private";
  if (type === "group" || type === "supergroup") return "group";
  return "other";
}

export function chatOf(update) {
  return update?.callback_query?.message?.chat?.id ?? update?.message?.chat?.id ?? null;
}

export function fromOf(update) {
  return update?.callback_query?.from?.id ?? update?.message?.from?.id ?? null;
}

/** "/start AB12CD34", "/link AB12CD34" or the bare 8-character code: the code, upper-cased, else null. */
export function linkCode(text) {
  const t = String(text || "").trim();
  const m = t.match(/^\/(?:start|link)(?:@\w+)?\s+([A-Za-z0-9]{8})\s*$/) || t.match(/^([A-Fa-f0-9]{8})$/);
  return m ? m[1].toUpperCase() : null;
}

/** The webhook's own reply (Telegram runs a method returned in the response body, so no bot token is needed here). */
export function instantReply(kind, update, { linked, owner }) {
  const chat = chatOf(update);
  if (kind === "callback") {
    const id = update.callback_query.id;
    return owner ? { method: "answerCallbackQuery", callback_query_id: id, text: "Sedang diproses…" }
                 : { method: "answerCallbackQuery", callback_query_id: id, text: "Bot ini peribadi.", show_alert: true };
  }
  if (kind !== "private") return null;
  if (owner) return { method: "sendChatAction", chat_id: chat, action: "typing" };
  return {
    method: "sendMessage", chat_id: chat,
    text: linked
      ? "Bot ini peribadi untuk Semasa. / This bot is private to Semasa."
      : "Belum disambung. Buka Semasa → Tetapan → Telegram, tekan \"Jana kod\", kemudian hantar /start KOD di sini.\n" +
        "Not linked yet. Open Semasa → Settings → Telegram, press \"Make a code\", then send /start CODE here.",
  };
}

/** The inbox row for an update; `owner` decides whether the worker is woken (status new) or not (skipped). */
export function inboxRow(update, kind, owner) {
  const status = kind === "group" ? "new" : kind === "other" ? "skipped" : owner ? "new" : "skipped";
  return {
    update_id: update.update_id, kind, chat_id: chatOf(update), from_id: fromOf(update), payload: update, status,
    note: status === "skipped" && (kind === "private" || kind === "callback") ? "not the linked account" : null,
  };
}
