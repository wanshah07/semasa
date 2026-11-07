// The Telegram webhook's decisions (supabase/functions/semasa-telegram/logic.js): only Telegram with our secret gets in,
// only the linked account wakes the worker, a one-time code is recognised, and the instant reply never needs the bot token.
import assert from "node:assert/strict";
import { inboxRow, instantReply, kindOf, linkCode, sameSecret } from "../supabase/functions/semasa-telegram/logic.js";

const priv = (text, from = 111) => ({ update_id: 1, message: { message_id: 5, chat: { id: from, type: "private" }, from: { id: from }, text } });
const group = { update_id: 2, message: { message_id: 6, chat: { id: -100, type: "supergroup", title: "Halal" }, from: { id: 7 }, text: "Soalan?" } };
const tap = (from = 111) => ({ update_id: 3, callback_query: { id: "cq", from: { id: from }, data: "ok:p1", message: { message_id: 9, chat: { id: from } } } });

// the secret header
assert.equal(sameSecret("abc", "abc"), true);
assert.equal(sameSecret("abd", "abc"), false);
assert.equal(sameSecret("", ""), false, "no secret configured: nothing gets in");
assert.equal(sameSecret(undefined, "abc"), false);

// kinds
assert.equal(kindOf(priv("hi")), "private");
assert.equal(kindOf(group), "group");
assert.equal(kindOf(tap()), "callback");
assert.equal(kindOf({ update_id: 4, edited_message: {} }), "other");
assert.equal(kindOf({ update_id: 5, message: { chat: { type: "channel" } } }), "other");

// the one-time code
assert.equal(linkCode("/start ab12cd34"), "AB12CD34");
assert.equal(linkCode("/start@semasa_bot AB12CD34"), "AB12CD34");
assert.equal(linkCode("AB12CD34"), "AB12CD34");
assert.equal(linkCode("/start"), null);
assert.equal(linkCode("hello world"), null);
assert.equal(linkCode("/start AB12CD3"), null, "seven characters is not a code");

// only the owner wakes the worker; groups always go to the FAQ reader; strangers are skipped
assert.equal(inboxRow(priv("hi"), "private", true).status, "new");
assert.equal(inboxRow(priv("hi", 999), "private", false).status, "skipped");
assert.equal(inboxRow(priv("hi", 999), "private", false).note, "not the linked account");
assert.equal(inboxRow(group, "group", false).status, "new");
assert.equal(inboxRow(tap(999), "callback", false).status, "skipped");
assert.deepEqual(Object.keys(inboxRow(group, "group", false)).sort(), ["chat_id", "from_id", "kind", "note", "payload", "status", "update_id"]);

// instant replies: a method in the response body, never the token
assert.deepEqual(instantReply("private", priv("hi"), { linked: true, owner: true }), { method: "sendChatAction", chat_id: 111, action: "typing" });
assert.match(instantReply("private", priv("hi", 999), { linked: true, owner: false }).text, /peribadi/);
assert.match(instantReply("private", priv("hi", 999), { linked: false, owner: false }).text, /Jana kod/);
assert.equal(instantReply("callback", tap(), { linked: true, owner: true }).text, "Sedang diproses…");
assert.equal(instantReply("callback", tap(999), { linked: true, owner: false }).show_alert, true);
assert.equal(instantReply("group", group, { linked: true, owner: false }), null, "the bot never talks in a group");

console.log("telegram: ok");

// ---- fast answers in the webhook (Wan, 7 Nov 2026: "make sure telegram answer more fast") ----
import { fastEligible, fastMessages, fastReply, turnsOf } from "../supabase/functions/semasa-telegram/logic.js";
const base = { kind: "private", owner: true, state: {}, pin: null, gwName: "Mireld" };
assert.equal(fastEligible({ ...base, text: "apa beza notifikasi dan pendaftaran?" }), true);
assert.equal(fastEligible({ ...base, text: "/draf" }), false, "a command goes to the worker");
assert.equal(fastEligible({ ...base, text: "baca ini https://npra.gov.my/x" }), false, "a link becomes an idea on a tap");
assert.equal(fastEligible({ ...base, text: "AB12CD34" }), false, "a link code is never answered by the AI");
assert.equal(fastEligible({ ...base, text: "topik saya", state: { pending: "poster" } }), false, "the menu is waiting for a topic");
assert.equal(fastEligible({ ...base, text: "ringkas lagi", state: { await_note: 5 } }), false, "a correction after 👎");
assert.equal(fastEligible({ ...base, text: "hai", pin: { gateway: "rootsys", model: "glm-5.3" } }), false, "pinned elsewhere: the worker uses the pin");
assert.equal(fastEligible({ ...base, text: "hai", pin: { gateway: "mireld", model: "kimi-k3" } }), true);
assert.equal(fastEligible({ ...base, text: "hai", owner: false }), false);
const msgs = fastMessages({ text: "model apa?", notes: ["jawab ringkas"], turns: [["test", "ok"]], snapshot: "Draf menunggu: 3", gwName: "Mireld", model: "kimi-k3" });
assert.match(msgs[0].content, /never Bahasa Indonesia/);
assert.match(msgs[0].content, /through Mireld running the model kimi-k3/);
assert.match(msgs[1].content, /- jawab ringkas/);
assert.match(msgs[1].content, /Wan: test\nSemasa: ok/);
assert.deepEqual(turnsOf([{ role: "user", content: "a" }, { role: "assistant", content: "b" }, { role: "user", content: "c" }]), [["a", "b"]]);
const fr = fastReply(111, 5, "Jawapan", "Mireld · kimi-k3", 42);
assert.equal(fr.text, "Jawapan\n\n— Mireld · kimi-k3");
assert.deepEqual(fr.reply_markup.inline_keyboard[0].map((b) => b.callback_data), ["fb:up:42", "fb:down:42"]);
console.log("telegram fast: ok");

// ---- 7 Nov 2026 review ----
import { BUSY_WINDOW_MS, newestNotes } from "../supabase/functions/semasa-telegram/logic.js";
// a 👎 or a menu tap the worker has not finished: the next message waits for it, never answered as a question
assert.equal(fastEligible({ ...base, text: "jawab lebih ringkas", busy: true }), false);
assert.equal(fastEligible({ ...base, text: "jawab lebih ringkas", busy: false }), true);
assert.ok(BUSY_WINDOW_MS >= 5 * 60_000 && BUSY_WINDOW_MS < 30 * 60_000, "shorter than the watchdog's 30 minutes");
// the newest 40 notes (read newest first), in the order they were written
const rows = Array.from({ length: 45 }, (_, i) => ({ note: `n${44 - i}` }));
const kept = newestNotes(rows, 40);
assert.equal(kept.length, 40);
assert.deepEqual([kept[0], kept[39]], ["n5", "n44"]);
console.log("telegram review: ok");
