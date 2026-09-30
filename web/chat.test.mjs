/* The pure half of the AI chat function (supabase/functions/semasa-chat/logic.js), run in Node. */
import assert from "node:assert/strict";
import { LIMITS, SYSTEM, TEST_IMAGE, buildMessages, checkReport, whoIs } from "../supabase/functions/semasa-chat/logic.js";

let n = 0;
const t = (name, fn) => { fn(); n++; };
const user = (text) => ({ role: "user", text });

t("system prompt first, then the conversation; the page's own notes never reach the model", () => {
  const { messages } = buildMessages([user("a"), { role: "note", text: "AI belum disambungkan" }, { role: "assistant", text: "b" }, user("c")]);
  assert.deepEqual(messages.map((m) => m.role), ["system", "user", "assistant", "user"]);
  assert.equal(messages[0].content, SYSTEM);
  assert.ok(/Bahasa Malaysia \(bukan Bahasa Indonesia\)/.test(SYSTEM));
});

t("the last message has to be the user's", () => {
  assert.throws(() => buildMessages([user("a"), { role: "assistant", text: "b" }]), /last message/);
  assert.throws(() => buildMessages([]), /last message/);
  assert.throws(() => buildMessages("nope"), /last message/);
});

t("history is capped by turns and by characters", () => {
  const long = Array.from({ length: 50 }, (_, i) => user(`m${i}`));
  assert.equal(buildMessages(long).messages.length, LIMITS.turns + 1);
  const big = buildMessages([user("x".repeat(LIMITS.chars + 500))]).messages[1].content;
  assert.equal(big.length, LIMITS.chars);
});

t("a picture becomes an image_url part on the last user message only", () => {
  const { messages, sent } = buildMessages([user("first"), { role: "assistant", text: "ok" }, user("look")], [{ name: "a.png", dataUrl: TEST_IMAGE }]);
  assert.equal(typeof messages[1].content, "string");
  const last = messages.at(-1).content;
  assert.deepEqual(last.map((p) => p.type), ["text", "image_url"]);
  assert.equal(last[1].image_url.url, TEST_IMAGE);
  assert.equal(sent.images, 1);
});

t("a text file is appended to the message, a PDF is named as not read instead of vanishing", () => {
  const { messages, sent } = buildMessages([user("ringkaskan")], [{ name: "nota.txt", text: "isi nota" }, { name: "x.pdf", skipped: "jenis fail ini belum boleh dibaca" }]);
  const c = messages.at(-1).content;
  assert.ok(c.includes("[Fail: nota.txt]\nisi nota"));
  assert.ok(c.includes("tidak dapat dibaca dan tidak dihantar: x.pdf"));
  assert.equal(sent.docs, 1);
  assert.equal(sent.skipped.length, 1);
});

t("only real image data URLs get through, and only so many", () => {
  const bad = buildMessages([user("x")], [{ name: "e.png", dataUrl: "javascript:alert(1)" }, { name: "s.svg", dataUrl: "data:image/svg+xml;base64,AAAA" }]);
  assert.equal(bad.sent.images, 0);
  assert.equal(bad.sent.skipped.length, 2);
  const many = Array.from({ length: 6 }, (_, i) => ({ name: `${i}.png`, dataUrl: TEST_IMAGE }));
  assert.equal(buildMessages([user("x")], many).sent.images, LIMITS.images);
  const huge = { name: "h.jpg", dataUrl: "data:image/jpeg;base64," + "A".repeat(LIMITS.imageChars) };
  assert.equal(buildMessages([user("x")], [huge]).sent.images, 0);
});

t("check: 5.5 and 5-5 are the same model, and the report says how Mireld spells it", () => {
  const r = checkReport("claude-sonnet-5.5", ["gpt-x", "claude-sonnet-5-5", "claude-opus-5-5"], { answer: "Red." });
  assert.equal(r.listed.exact, false);
  assert.equal(r.listed.spelled_as, "claude-sonnet-5-5");
  assert.deepEqual(r.listed.related, ["claude-sonnet-5-5", "claude-opus-5-5"]);
  assert.equal(r.image.reads, true);
});

t("check: an exact match needs no respelling; 'Merah' counts as reading the picture", () => {
  const r = checkReport("claude-sonnet-5.5", ["claude-sonnet-5.5"], { answer: "merah" });
  assert.equal(r.listed.exact, true);
  assert.equal(r.listed.spelled_as, null);
  assert.equal(r.image.reads, true);
});

t("check: accepting an image is not reading it, and an error is reported as one", () => {
  assert.equal(checkReport("m", ["m"], { answer: "I cannot see any image." }).image.reads, false);
  assert.equal(checkReport("m", ["m"], { answer: "It is a blue square." }).image.reads, false);
  const e = checkReport("m", null, { error: "HTTP 400: model does not support image input" });
  assert.equal(e.listed.read, false);
  assert.equal(e.image.reads, false);
  assert.ok(e.image.error.includes("HTTP 400"));
  assert.deepEqual(checkReport("m", ["m"], null).image, { tested: false });
});

const reply = (status, type, body) => async () => ({
  ok: status >= 200 && status < 300, status, headers: { get: (h) => (h.toLowerCase() === "content-type" ? type : null) }, text: async () => body,
});
const run = async (name, fn) => { await fn(); n++; };

await run("whoIs: a real user comes back as {user}, and the call carries the token and the key as headers", async () => {
  let seen;
  const f = async (u, init) => { seen = { u, h: init.headers }; return reply(200, "application/json", '{"id":"abc","email":"w@x.my"}')(); };
  const r = await whoIs(f, "https://ref.supabase.co/", "ANON", "TOK");
  assert.equal(r.user.id, "abc");
  assert.equal(seen.u, "https://ref.supabase.co/auth/v1/user");
  assert.equal(seen.h.authorization, "Bearer TOK");
  assert.equal(seen.h.apikey, "ANON");
});

await run("whoIs: an HTML answer says the host, status, type and what it said, and never the token or key", async () => {
  const r = await whoIs(reply(502, "text/html; charset=utf-8", "<html>\n <head><title>502 Bad Gateway</title></head></html>"), "https://ref.supabase.co", "ANON-KEY-123", "TOKEN-456");
  assert.equal(r.user, undefined);
  assert.ok(r.why.includes("ref.supabase.co") && r.why.includes("HTTP 502") && r.why.includes("text/html"));
  assert.ok(r.why.includes("<html> <head><title>502"));
  assert.ok(!r.why.includes("ANON-KEY-123") && !r.why.includes("TOKEN-456"));
});

await run("whoIs: a JSON refusal is reported in its own words; a network failure is reported as unreachable", async () => {
  const j = await whoIs(reply(401, "application/json", '{"code":401,"msg":"invalid JWT: token is expired"}'), "https://ref.supabase.co", "A", "T");
  assert.ok(j.why.includes("HTTP 401") && j.why.includes("invalid JWT: token is expired"));
  const dead = await whoIs(async () => { throw new Error("connection refused"); }, "https://ref.supabase.co", "A", "T");
  assert.ok(dead.why.startsWith("could not reach auth at ref.supabase.co") && dead.why.includes("connection refused"));
});

await run("whoIs: a 200 that is not a user (no id) is not a login", async () => {
  assert.ok((await whoIs(reply(200, "application/json", "{}"), "https://r.supabase.co", "A", "T")).why);
});

console.log(`chat: ${n} ok`);
