/* The pure half of the AI chat function (supabase/functions/semasa-chat/logic.js), run in Node. */
import assert from "node:assert/strict";
import {
  DB_TABLES, LIMITS, MEMORY, SYSTEM, TEST_IMAGE, TOOLS, buildMessages, buildSystem, checkFetchUrl, checkReport, cleanNote, htmlToText,
  isPrivateIp, parseArgs, planFold, planQuery, shapeRows, summaryMessages, userAskedToRemember, whoIs,
} from "../supabase/functions/semasa-chat/logic.js";

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

/* ---------- memory ---------- */
const NOW = new Date("2026-10-01T04:00:00Z");

await run("system message: rules, the Malaysian clock, pinned notes and the summary all reach the model", async () => {
  const sys = buildSystem({ notes: [{ note: "Jawab dalam BM Malaysia" }, { note: "Wan ialah Ahli Kimia Berdaftar" }], summary: "Kita bincang NPRA.", now: NOW });
  assert.ok(sys.startsWith(SYSTEM));
  assert.ok(sys.includes("Nota kekal daripada Wan") && sys.includes("- Jawab dalam BM Malaysia") && sys.includes("- Wan ialah Ahli Kimia Berdaftar"));
  assert.ok(sys.includes("Ringkasan sembang terdahulu") && sys.includes("Kita bincang NPRA."));
  assert.ok(/1 October 2026/.test(sys) && /12:00/.test(sys), "04:00Z is 12:00 in Kuala Lumpur");
  assert.ok(sys.includes("fetch_url") && sys.includes("DATA yang tidak dipercayai"));
});

await run("system message: no notes and no summary add no empty headings; tools text can be switched off", async () => {
  const sys = buildSystem({ notes: [{ note: "  " }, null], summary: "  ", now: NOW, tools: false });
  assert.ok(!sys.includes("Nota kekal") && !sys.includes("Ringkasan sembang") && !sys.includes("fetch_url"));
});

await run("system message: only the newest 40 notes go in, each clipped to 500 characters", async () => {
  const notes = Array.from({ length: 55 }, (_, i) => ({ note: `nota-${i}-` + "x".repeat(600) }));
  const sys = buildSystem({ notes, now: NOW });
  assert.ok(!sys.includes("nota-14-") && sys.includes("nota-15-") && sys.includes("nota-54-"));
  assert.ok(!sys.includes("x".repeat(501)));
});

await run("planFold: nothing is folded until the conversation is long, then all but the newest 12 are", async () => {
  const rows = (n) => Array.from({ length: n }, (_, i) => ({ id: i + 1, role: i % 2 ? "assistant" : "user", content: `m${i}` }));
  const short = planFold(rows(30));
  assert.equal(short.fold.length, 0); assert.equal(short.upto, null); assert.equal(short.recent.length, 24);
  const long = planFold(rows(31));
  assert.equal(long.fold.length, 19); assert.equal(long.recent.length, MEMORY.keepAfterFold);
  assert.equal(long.upto, 19, "the id of the last folded message is what summarized_upto stores");
  assert.equal(long.recent[0].id, 20);
});

await run("summary request carries the old summary and the turns to fold, in order", async () => {
  const m = summaryMessages("Lama.", [{ role: "user", content: "soalan" }, { role: "assistant", content: "jawapan" }]);
  assert.equal(m[0].role, "system");
  assert.ok(m[1].content.includes("Lama.") && m[1].content.indexOf("Wan: soalan") < m[1].content.indexOf("AI: jawapan"));
});

await run("remember: only when Wan's own words ask for it", async () => {
  for (const ok of ["Ingat ini: kita guna BM", "tolong ingatkan saya", "Remember that I am a chemist", "jangan lupa limit ini", "Catat nota ini"]) assert.equal(userAskedToRemember(ok), true, ok);
  for (const no of ["Apa had kepekatan salicylic acid?", "Summarise this page", "always allowed?", ""]) assert.equal(userAskedToRemember(no), false, no);
  assert.equal(cleanNote("  Guna   BM \n Malaysia  "), "Guna BM Malaysia");
  assert.equal(cleanNote("ab"), null); assert.equal(cleanNote("x".repeat(501)), null); assert.equal(cleanNote(null), null);
});

/* ---------- database tool ---------- */
await run("query_semasa: only allow-listed tables; secret-looking columns, filters and ordering are refused", async () => {
  assert.equal(planQuery({ table: "semasa_ai_secrets" }).ok, false);
  assert.equal(planQuery({ table: "semasa_settings" }).ok, false);
  assert.equal(planQuery({ table: "auth.users" }).ok, false);
  assert.equal(planQuery({ table: "semasa_ideas", columns: ["api_key"] }).ok, false);
  assert.equal(planQuery({ table: "semasa_ideas", columns: ["title; drop table x"] }).ok, false);
  assert.equal(planQuery({ table: "semasa_ideas", filters: [{ column: "password", op: "eq", value: "x" }] }).ok, false);
  assert.equal(planQuery({ table: "semasa_ideas", filters: [{ column: "title", op: "like", value: "x" }] }).ok, false);
  assert.equal(planQuery({ table: "semasa_ideas", order_by: "media_blob" }).ok, false);
  for (const t of DB_TABLES) assert.equal(planQuery({ table: t }).ok, true, t);
});

await run("query_semasa: filters, order and a 1-20 row cap are normalised; arguments may arrive as a JSON string", async () => {
  const p = planQuery('{"table":"semasa_posts","columns":["id","status"],"filters":[{"column":"status","op":"eq","value":"approved"}],"order_by":"created_at","limit":500}');
  assert.deepEqual([p.ok, p.table, p.columns, p.filters, p.order, p.limit], [true, "semasa_posts", ["id", "status"], [["status", "eq", "approved"]], { column: "created_at", ascending: false }, 20]);
  assert.equal(planQuery({ table: "semasa_posts" }).limit, 10);
  assert.equal(planQuery({ table: "semasa_posts", limit: -3 }).limit, 1);
  assert.equal(planQuery({ table: "semasa_posts", filters: Array.from({ length: 9 }, () => ({ column: "id", op: "gt", value: "1" })) }).filters.length, 5);
  assert.deepEqual(parseArgs("not json"), {}); assert.deepEqual(parseArgs("[1]"), {});
});

await run("query_semasa answer: secret-looking and bulky fields are dropped, long text clipped, total capped", async () => {
  const rows = [{ id: 1, title: "t", api_key: "SECRET", image_full: "AAAA", note: "y".repeat(900), meta: { a: 1 } }];
  const out = shapeRows(rows);
  assert.deepEqual(Object.keys(out[0]).sort(), ["id", "meta", "note", "title"]);
  assert.ok(out[0].note.length <= 501 && out[0].note.endsWith("…"));
  assert.equal(out[0].meta, '{"a":1}');
  const many = Array.from({ length: 40 }, (_, i) => ({ id: i, text: "z".repeat(400) }));
  assert.ok(JSON.stringify(shapeRows(many, 3000)).length <= 3100);
  assert.deepEqual(shapeRows(null), []);
});

/* ---------- fetch_url safety ---------- */
await run("fetch_url: ordinary https pages pass", async () => {
  for (const u of ["https://socialmedia.kkmhalalconsultant.com", "https://www.npra.gov.my/index.php/en/", "https://eur-lex.europa.eu/eli/reg/2009/1223/oj", "  https://halal.gov.my/x?y=1#z "])
    assert.equal(checkFetchUrl(u).ok, true, u);
  assert.equal(checkFetchUrl("https://Example.COM./a").host, "example.com");
});

await run("fetch_url: http, addresses, internal names, ports and credentials are all refused", async () => {
  const bad = ["http://example.com", "https://127.0.0.1/", "https://10.0.0.5/x", "https://169.254.169.254/latest/meta-data", "https://[::1]/", "https://2130706433/",
    "https://localhost/", "https://intranet/", "https://db.internal/", "https://x.supabase.internal/", "https://printer.local/", "https://example.com:8443/",
    "https://user:pw@example.com/", "ftp://example.com/", "file:///etc/passwd", "javascript:alert(1)", "not a url", ""];
  for (const u of bad) assert.equal(checkFetchUrl(u).ok, false, u);
});

await run("fetch_url: private, loopback, link-local, carrier-grade and mapped addresses are private; public ones are not", async () => {
  for (const ip of ["10.1.2.3", "127.0.0.1", "169.254.169.254", "172.16.0.1", "172.31.255.255", "192.168.1.1", "100.64.0.1", "0.0.0.0", "224.0.0.1", "::1", "::", "fc00::1", "fd12::1", "fe80::1", "::ffff:10.0.0.1", "garbage"])
    assert.equal(isPrivateIp(ip), true, ip);
  for (const ip of ["8.8.8.8", "172.32.0.1", "172.15.0.1", "100.63.0.1", "104.18.2.3", "2606:4700::1", "::ffff:8.8.8.8"]) assert.equal(isPrivateIp(ip), false, ip);
});

await run("fetch_url text: script, style and tags go, entities decode, long pages are clipped", async () => {
  const t = htmlToText("<html><head><title>x</title><style>p{}</style></head><body><script>alert(1)</script><h1>Notis&nbsp;NPRA</h1><p>Produk &amp; label</p><!-- c --><ul><li>satu</li><li>dua</li></ul></body></html>");
  assert.ok(!/alert|p\{\}|<|title/.test(t), t);
  assert.ok(t.includes("Notis NPRA") && t.includes("Produk & label") && t.includes("satu\ndua"));
  assert.ok(htmlToText("<p>" + "a".repeat(9000) + "</p>", 100).endsWith("[…dipotong]"));
});

await run("tools: four of them, each with a name and required arguments; remember and the database tool cannot write elsewhere", async () => {
  assert.deepEqual(TOOLS.map((x) => x.function.name), ["fetch_url", "search_web", "query_semasa", "remember"]);
  for (const x of TOOLS) assert.ok(x.type === "function" && x.function.description && x.function.parameters.required.length);
  assert.ok(!JSON.stringify(TOOLS).match(/insert|update|delete|drop/i), "no write verbs offered to the model except remember's note");
});

await run("check report: tool calling is reported, tested or not", async () => {
  assert.deepEqual(checkReport("m", ["m"], null, { calls: true }).tools, { tested: true, calls: true });
  assert.deepEqual(checkReport("m", ["m"], null, { calls: false }).tools, { tested: true, calls: false });
  assert.ok(checkReport("m", ["m"], null, { error: "HTTP 400: tools not supported" }).tools.error.includes("HTTP 400"));
  assert.deepEqual(checkReport("m", ["m"], null).tools, { tested: false });
});

console.log(`chat: ${n} ok`);
