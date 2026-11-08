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

/* Fast answers (Wan, 7 Nov 2026: "make sure telegram answer more fast"). A plain question from the linked account is answered
   here, in the webhook, with the AI chat's own gateway (its secrets are this project's Edge Function secrets), instead of waking
   the GitHub worker (30-60 s). Only when nothing else must happen first: no command, no link (a link becomes an idea on a tap),
   no topic the menu is waiting for, no correction after 👎, and Wan's /robot pin is Auto or names this same gateway. Anything
   else, or a gateway that fails or is slow, goes to the worker exactly as before.
   `busy`: a message or tap of his the worker has not finished yet (inbox new/working). pending and await_note are written by
   the worker 30-60 s after a menu tap or a 👎, so until it is done they cannot be trusted: the message waits its turn, else it
   is answered as a question and the NEXT one is misfiled as the topic or the correction. */
export function fastEligible({ kind, text, owner, state, pin, gwName, busy = false }) {
  if (kind !== "private" || !owner || busy) return false;
  const t = String(text || "").trim();
  if (!t || t.startsWith("/") || /https?:\/\//i.test(t) || /^[A-Fa-f0-9]{8}$/.test(t)) return false;
  if (state?.pending || state?.await_note) return false;
  if (pin && pin.gateway && String(pin.gateway).toLowerCase() !== String(gwName || "").toLowerCase()) return false;
  return true;
}

/** 8 Nov 2026: the fast answer draws on the whole AI team (semasa-chat/logic.js assembleTeam: the function's secrets, the page's
    slots, the owner's providers, Mireld), not one gateway. The gates to try, at most `max`, fastest healthy first (pickWorkers: the
    probe's state and chat_ms; a stale or down robot last, never left out), never Gemini (free-key privacy) and never ChatGPT (another
    dialect). With a /robot pin that names a gateway, only the robot whose name, provider or slug matches it is tried; a pin on
    anything else leaves the worker to answer, as before. Returns [{ slug, name, model, gate }]. */
export function fastGatesFor(team, pin, pick, max = 2) {
  const robots = team?.robots || [], gates = team?.gates || {};
  const want = pin && pin.gateway ? String(pin.gateway).toLowerCase() : "";
  const matches = (r) => !want || [r.slug, r.name, r.provider].some((x) => String(x || "").toLowerCase() === want);
  const out = [];
  for (const c of pick(robots, { job: "telegram", fast: true })) {
    const r = robots.find((x) => x.slug === c.slug);
    const g = gates[c.slug];
    if (!r || !g || !matches(r)) continue;
    out.push({ slug: r.slug, name: `${r.name} (${r.provider})`, model: c.model || g.model, gate: { ...g, key: g.key || g.keys?.[0]?.key || "" } });
    if (out.length >= max) break;
  }
  return out;
}

export const FAST_SYSTEM = "You are Semasa's assistant on Telegram for Wan (Registered Chemist, regulatory affairs specialist, owner of " +
  "WS REGULAB). Answer briefly, in the language he writes: Malaysian Bahasa Malaysia (never Bahasa Indonesia) or English. Plain " +
  "text, no markdown. You cannot approve, post or change anything yourself: name the command that does it (/menu, /draf, /poster, " +
  "/karusel, /motion, /laporan, /robot, /ingat). On regulations, never invent a number, date, limit or reference; say what should be " +
  "checked and where (NPRA, ACD, EC 1223/2009). Follow WAN'S STANDING NOTES.";

export function fastMessages({ text, notes, turns, snapshot, gwName, model }) {
  const me = `You are answering through ${gwName} running the model ${model || "its default model"}. If Wan asks which model or ` +
    "robot you are, say exactly that and nothing else about your origin.";
  const known = "WAN'S STANDING NOTES (always follow)\n" + ((notes || []).map((n) => `- ${n}`).join("\n") || "(none)") +
    (snapshot ? `\n\nSNAPSHOT\n${snapshot}` : "") +
    "\n\nEARLIER\n" + ((turns || []).map(([q, a]) => `Wan: ${q}\nSemasa: ${a}`).join("\n") || "(none)");
  return [{ role: "system", content: `${FAST_SYSTEM} ${me}` },
    { role: "user", content: `${known}\n\nWAN ASKS\n${String(text).slice(0, 3000)}` }];
}

/** How far back an unfinished inbox row still holds the fast path: a row stuck longer (a run that died) is the watchdog's to
 *  report (30 minutes), and must not turn fast answers off for good. */
export const BUSY_WINDOW_MS = 15 * 60_000;

/** Wan's standing notes for the prompt: the NEWEST `max` rows (read newest first), put back in the order they were written. */
export function newestNotes(rowsNewestFirst, max = 40) {
  return (rowsNewestFirst || []).slice(0, max).reverse().map((n) => n.note);
}

/** Pairs (question, answer) from a thread's messages, oldest first. */
export function turnsOf(rows, n = 8) {
  const out = []; let q = null;
  for (const r of rows || []) {
    if (r.role === "user") q = String(r.content || "").slice(0, 600);
    else if (q !== null) { out.push([q, String(r.content || "").slice(0, 800)]); q = null; }
  }
  return out.slice(-n);
}

export function fastReply(chatId, replyTo, answer, who, rowId) {
  return {
    method: "sendMessage", chat_id: chatId, text: (String(answer).trim() + (who ? `\n\n— ${who}` : "")).slice(0, 4000),
    reply_parameters: { message_id: replyTo, allow_sending_without_reply: true },
    reply_markup: { inline_keyboard: [[{ text: "👍", callback_data: `fb:up:${rowId}` }, { text: "👎 perlu baiki", callback_data: `fb:down:${rowId}` }]] },
  };
}
