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
