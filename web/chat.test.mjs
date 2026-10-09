/* The pure half of the AI chat function (supabase/functions/semasa-chat/logic.js), run in Node. */
import assert from "node:assert/strict";
import {
  DB_TABLES, LIMITS, MEMORY, SYSTEM, TEST_IMAGE, TOOLS, buildMessages, buildSystem, checkFetchUrl, checkReport, cleanNote, htmlToText,
  MODEL_PREFERENCE, cleanModelId, isPrivateIp, modelNote, parseArgs, planFold, planQuery, rankModels, resolveModel, shapeRows, summaryMessages,
  userAskedToRemember, whoIs, foldDelta, lastQuestion, sseEvents,
} from "../supabase/functions/semasa-chat/logic.js";

let n = 0;
const t = (name, fn) => { fn(); n++; };
const user = (text) => ({ role: "user", text });

t("system prompt first, then the conversation; the page's own notes never reach the model", () => {
  const { messages } = buildMessages([user("a"), { role: "note", text: "AI belum disambungkan" }, { role: "assistant", text: "b" }, user("c")]);
  assert.deepEqual(messages.map((m) => m.role), ["system", "user", "assistant", "user"]);
  assert.equal(messages[0].content, SYSTEM);
  assert.ok(/Bahasa Malaysia \(bukan Bahasa Indonesia/.test(SYSTEM));
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


// ---- which model answers (Wan, 1 Oct 2026) -----------------------------------------------------------------------
t("a model id is a plain name: path tricks, spaces, newlines and empty values are refused", () => {
  assert.equal(cleanModelId("claude-sonnet-5.5"), "claude-sonnet-5.5");
  assert.equal(cleanModelId("  gpt-4o:mini "), "gpt-4o:mini");
  for (const bad of ["", null, undefined, "../x", "a b", "a\nb", "x".repeat(81), "-lead", "a;b", "a/../b\u0000"]) assert.equal(cleanModelId(bad), "", String(bad));
});

t("the default is the first preferred model Mireld lists: Sonnet 5.5, then Opus 5.5; Opus is the deep choice, not the everyday default", () => {
  assert.equal(MODEL_PREFERENCE[0], "claude-sonnet-5.5");
  const r = rankModels(["claude-haiku-4.5", "claude-opus-5.5", "claude-sonnet-5.5", "claude-fable-5.1"]);
  assert.equal(r.recommended, "claude-sonnet-5.5");
  assert.deepEqual(r.models.map((m) => m.id), ["claude-sonnet-5.5", "claude-opus-5.5", "claude-fable-5.1", "claude-haiku-4.5"]);
  assert.deepEqual(r.models.map((m) => m.recommended), [true, false, false, false]);
  assert.equal(rankModels(["claude-haiku-4.5", "claude-opus-5.5"]).recommended, "claude-opus-5.5");
});

t("models that cannot chat are not offered; a different spelling of a preferred model still counts", () => {
  const r = rankModels(["text-embedding-3-large", "whisper-1", "dall-e-3", "flux-pro", "Claude_Sonnet_5.5", "gpt-5"]);
  assert.deepEqual(r.models.map((m) => m.id), ["Claude_Sonnet_5.5", "gpt-5"]);
  assert.equal(r.recommended, "Claude_Sonnet_5.5");
});

t("nothing preferred is listed: the configured model if listed, else a Claude, else the first; an unreadable list offers nothing", () => {
  assert.equal(rankModels(["mistral-large", "my-model"], "my-model").recommended, "my-model");
  assert.equal(rankModels(["mistral-large", "claude-x-1"], "absent").recommended, "claude-x-1");
  assert.equal(rankModels(["mistral-large", "llama"], "absent").recommended, "mistral-large");
  assert.deepEqual(rankModels(null, "claude-sonnet-5.5"), { models: [], recommended: "claude-sonnet-5.5" });
});

t("what is said about a model comes from its name alone and never states a price or a speed figure", () => {
  assert.equal(modelNote("claude-opus-5.5").family, "opus");
  assert.equal(modelNote("claude-sonnet-5.5").family, "sonnet");
  assert.equal(modelNote("claude-haiku-4.5").family, "haiku");
  assert.equal(modelNote("gpt-5").family, "other");
  for (const id of ["claude-opus-5.5", "claude-sonnet-5.5", "claude-haiku-4.5", "claude-fable-5.1", "gpt-5"]) {
    const n = modelNote(id);
    assert.ok(n.note_bm && n.note_en);
    assert.ok(!/\d+\s*(ms|s\b|sec|second|\$|usd|rm)/i.test(n.note_en), n.note_en);
  }
  assert.ok(/Uji/.test(modelNote("gpt-5").note_bm) && /Test/.test(modelNote("gpt-5").note_en), "an unknown model says to test it");
});

t("the model asked for is used only when Mireld lists it; otherwise the default, and the page is told", () => {
  const listed = ["claude-sonnet-5.5", "claude-opus-5.5"];
  assert.deepEqual(resolveModel("claude-opus-5.5", listed, "claude-sonnet-5.5"), { model: "claude-opus-5.5", changed: false });
  assert.deepEqual(resolveModel("gpt-nope", listed, "claude-sonnet-5.5"), { model: "claude-sonnet-5.5", changed: true, asked: "gpt-nope" });
  assert.deepEqual(resolveModel("", listed, "claude-sonnet-5.5"), { model: "claude-sonnet-5.5", changed: false });
  assert.deepEqual(resolveModel(undefined, null, "claude-sonnet-5.5"), { model: "claude-sonnet-5.5", changed: false });
  // the list could not be read: a sane id is passed on (Mireld refuses a wrong one); an insane one never is
  assert.deepEqual(resolveModel("claude-opus-5.5", null, "claude-sonnet-5.5"), { model: "claude-opus-5.5", changed: false });
  assert.deepEqual(resolveModel("../../etc", null, "claude-sonnet-5.5"), { model: "claude-sonnet-5.5", changed: false });
});

// ---- streaming and regenerate (1 Oct 2026: "improve the system and how the AI respond especially for chat AI feature") ----------
t("the system prompt is Wan's own brief: answer first, Markdown, Malaysian Malay, never 'consult a professional', facts never invented", () => {
  for (const needle of [/jawapan terus pada baris pertama/, /Markdown/, /bukan Bahasa Indonesia/, /rujuk profesional/, /jangan reka nombor notifikasi/i, /Tiada em dash/, /ACD Annex III/]) assert.match(SYSTEM, needle);
});

t("SSE events are split on blank lines, data lines joined, the unfinished tail kept for the next read", () => {
  const { events, rest } = sseEvents("data: a\n\ndata: b\ndata: c\n\n: ping\n\ndata: {\"half");
  assert.deepEqual(events, ["a", "b\nc"]);
  assert.equal(rest, "data: {\"half");
  assert.deepEqual(sseEvents("data: x\r\n\r\n").events, ["x"]);
  assert.deepEqual(sseEvents(""), { events: [], rest: "" });
});

t("streamed deltas fold into one answer: text pieces append, tool-call pieces assemble by index, the finish reason and model are kept", () => {
  let a = null;
  a = foldDelta(a, { model: "claude-sonnet-5.5", choices: [{ delta: { role: "assistant", content: "Hal" } }] });
  a = foldDelta(a, { choices: [{ delta: { content: "o" } }] });
  a = foldDelta(a, { choices: [{ delta: { tool_calls: [{ index: 0, id: "c1", function: { name: "fetch_", arguments: "{\"ur" } }] } }] });
  a = foldDelta(a, { choices: [{ delta: { tool_calls: [{ index: 0, function: { name: "url", arguments: "l\":\"https://x\"}" } }] } }] });
  a = foldDelta(a, { choices: [{ delta: { tool_calls: [{ index: 1, id: "c2", function: { name: "remember", arguments: "{}" } }] } }] });
  a = foldDelta(a, { choices: [{ delta: {}, finish_reason: "tool_calls" }] });
  assert.equal(a.content, "Halo");
  assert.deepEqual(a.toolCalls, [{ id: "c1", name: "fetch_url", arguments: "{\"url\":\"https://x\"}" }, { id: "c2", name: "remember", arguments: "{}" }]);
  assert.equal(a.finish, "tool_calls");
  assert.equal(a.model, "claude-sonnet-5.5");
  assert.equal(foldDelta(a, { choices: [] }).content, "Halo");
  assert.equal(foldDelta(null, { choices: [{ delta: { content: [{ type: "text", text: "parts" }] } }] }).content, "parts");
});

t("regenerate answers the last user question, without the attachment note the function appended", () => {
  assert.equal(lastQuestion([{ role: "user", content: "a" }, { role: "assistant", content: "b" }, { role: "user", content: "soalan\n[lampiran: x.pdf, y.png]" }]), "soalan");
  assert.equal(lastQuestion([{ role: "user", content: "a" }, { role: "assistant", content: "b" }]), "a");
  assert.equal(lastQuestion([]), "");
  assert.equal(lastQuestion(null), "");
});

console.log(`chat: ${n} ok`);

// ---- attachments folded per file (lib/chatFiles.js) ---------------------------------------------------------------------------
import { foldAttachments } from "./src/lib/chatFiles.js";
t("a PDF read as pages and a workbook read as sheets become one attachment each; pictures and refusals pass through", () => {
  const out = foldAttachments([
    { name: "a.pdf · halaman 1", text: "p1" }, { name: "scan.png", dataUrl: "data:image/png;base64,AA" }, { name: "a.pdf · halaman 2", text: "p2" },
    { name: "b.xlsx · helaian Harga", text: "rows" }, { name: "c.txt", text: "plain" }, { name: "d.doc", skipped: "lama" }, null,
  ]);
  assert.deepEqual(out.map((o) => o.name), ["scan.png", "d.doc", "a.pdf", "b.xlsx", "c.txt"]);
  assert.equal(out.find((o) => o.name === "a.pdf").text, "[halaman 1]\np1\n\n[halaman 2]\np2");
  assert.equal(out.find((o) => o.name === "b.xlsx").text, "[helaian Harga]\nrows");
  assert.equal(out.find((o) => o.name === "c.txt").text, "plain");
  assert.equal(out.find((o) => o.name === "d.doc").skipped, "lama");
  assert.deepEqual(foldAttachments(null), []);
});
console.log(`chat files: ok`);

// ---- hardening (1 Oct 2026: "check the security and the flow") ------------------------------------------------------------
import { OWN_HOSTS, RATE, allow, rateKind } from "../supabase/functions/semasa-chat/logic.js";
t("fetch_url refuses the project's own hosts and any supabase host, and drops a fragment", () => {
  assert.match(checkFetchUrl("https://mwaocnbgvbkhovktgods.supabase.co/rest/v1/semasa_posts").why, /own hosts/);
  assert.match(checkFetchUrl("https://x.supabase.in/auth/v1/user").why, /own hosts/);
  OWN_HOSTS.push("my.own.example");
  assert.match(checkFetchUrl("https://my.own.example/x").why, /own hosts/);
  OWN_HOSTS.pop();
  assert.equal(checkFetchUrl("https://www.npra.gov.my/index.php/ms#top").url, "https://www.npra.gov.my/index.php/ms");
});

t("the rate guard allows up to the limit inside the window, then says how long to wait, and forgets old calls", () => {
  const times = [];
  for (let i = 0; i < 3; i++) assert.equal(allow(times, 1000 + i, 3, 10_000).ok, true);
  const no = allow(times, 1005, 3, 10_000);
  assert.equal(no.ok, false);
  assert.equal(no.retryAfter, 10);
  assert.equal(allow(times, 11_001, 3, 10_000).ok, true, "the first call fell out of the window");
  assert.deepEqual(rateKind("design_clone"), "design"); assert.deepEqual(rateKind("design_refine"), "design");
  assert.deepEqual(rateKind("faq_extract"), "faq"); assert.deepEqual(rateKind("models"), ""); assert.deepEqual(rateKind("chat"), "chat"); assert.deepEqual(rateKind(undefined), "chat");
  assert.ok(RATE.chat[0] >= 20 && RATE.design[0] >= 4, "the limits leave room for real work");
});

t("documents together never exceed the total cap: the one that crosses it is cut, the next is named as skipped", () => {
  const big = "y".repeat(LIMITS.fileChars);
  const files = Array.from({ length: 5 }, (_, i) => ({ name: `d${i}.txt`, text: big }));
  const { messages, sent } = buildMessages([user("x")], files);
  const body = messages.at(-1).content;
  const used = (body.match(/\[Fail: d\d\.txt\]/g) || []).length;
  assert.equal(used, 3, "150k of 60k-character files is two whole ones and a third cut");
  assert.ok(sent.skipped.some((s) => /had keseluruhan/.test(s)));
  assert.ok(body.length < LIMITS.totalFileChars + 2000);
});
console.log("hardening: ok");

// ---- reader calls that survive a slow first output (2 Oct 2026, "HTTP 500: Member first-output deadline") ---------------------
import { attemptCap, gatewayConfig, gatewayDown, pickFallback, readerMessage, retryPause, retryable, withInstructions } from "../supabase/functions/semasa-chat/logic.js";
t("a deadline, a timeout, a throttle or any 5xx may pass on another try; a 400, 401, 403 or 404 never will", () => {
  assert.equal(retryable(500, "Member first-output deadline"), true);
  assert.equal(retryable(0, "the model did not answer in time"), true);
  assert.equal(retryable(429, ""), true);
  assert.equal(retryable(503, ""), true);
  assert.equal(retryable(408, ""), true);
  assert.equal(retryable(400, "this model is overloaded"), true, "the message counts too");
  for (const st of [400, 401, 403, 404]) assert.equal(retryable(st, "invalid image"), false);
  assert.equal(retryable(undefined, undefined), true, "no status at all is a failed connection");
});

t("the fallback is the best OTHER chat model Mireld lists, never the failed one, never a non-chat model, and empty when there is none", () => {
  const ids = ["text-embedding-3", "claude-haiku-4.5", "claude-opus-5.5", "claude-sonnet-5.5", "whisper-1"];
  assert.equal(pickFallback(ids, "claude-sonnet-5.5"), "claude-opus-5.5");
  assert.equal(pickFallback(ids, "claude-opus-5.5"), "claude-sonnet-5.5");
  assert.equal(pickFallback(["claude-sonnet-5.5"], "claude-sonnet-5.5"), "");
  assert.equal(pickFallback(["claude-sonnet-5-5", "claude-opus-5-5"], "claude-sonnet-5.5"), "claude-opus-5-5", "spelled differently is still the same model");
  assert.equal(pickFallback(null, "claude-sonnet-5.5"), "");
  assert.equal(pickFallback([], "x"), "");
});
console.log("reader retry: ok");

// The gateway being down is said plainly, and is not "pick another model" (Wan, 9 Oct 2026, screenshot: HTTP 503 Scheduled server upgrade).
assert.equal(gatewayDown(503, "Scheduled server upgrade in progress. Please retry later."), true);
assert.equal(gatewayDown(500, "Member first-output deadline"), false, "a slow model is not a down gateway: another model may answer");
assert.equal(gatewayDown(0, "the model did not answer in time"), false);
assert.equal(gatewayDown(400, "invalid image"), false);
assert.equal(gatewayDown(200, "down for maintenance"), true, "the words count when the status is odd");
assert.equal(retryPause(503, ""), 4000);
assert.equal(retryPause(500, "Member first-output deadline"), 0);
{
  const down = readerMessage({ ok: false, status: 503, err: "Scheduled server upgrade in progress. Please retry later.", tried: ["claude-sonnet-5-5", "claude-sonnet-5-5"], gateway: "Mireld" });
  assert.match(down, /HTTP 503: Scheduled server upgrade/);
  assert.match(down, /tried claude-sonnet-5-5\)/, "the same model twice is named once");
  assert.match(down, /Mireld\) is down or being upgraded/);
  assert.doesNotMatch(down, /pick another model/, "another model on the same gateway cannot help");
  const slow = readerMessage({ ok: false, status: 500, err: "Member first-output deadline", tried: ["a", "b"] });
  assert.match(slow, /pick another model/);
  assert.match(readerMessage({ ok: true, status: 200, err: "", tried: ["a"] }), /an empty answer/);
}
console.log("reader message: ok");

// The function can run on another gateway by secrets alone (Wan, 9 Oct 2026: move to Afiq's rootsys).
{
  const env = (o) => (k) => o[k];
  const m = gatewayConfig(env({ MIRELD_API_KEY: "k1" }));
  assert.equal(m.error, ""); assert.equal(m.name, "Mireld"); assert.equal(m.base, "https://api.mireld.my/v1");
  assert.equal(m.keyName, "MIRELD_API_KEY"); assert.equal(m.repeatSystem, false, "Mireld passes the system message on");
  const r = gatewayConfig(env({ AI_API_KEY: "k2", AI_BASE_URL: "https://rootsys.cloud/v1", AI_MODEL: "kimi-k3", MIRELD_API_KEY: "k1", MIRELD_MODEL: "claude-sonnet-5.5" }));
  assert.equal(r.error, ""); assert.equal(r.name, "rootsys"); assert.equal(r.key, "k2"); assert.equal(r.base, "https://rootsys.cloud/v1");
  assert.equal(r.model, "kimi-k3", "AI_MODEL wins, and MIRELD_MODEL is ignored with AI_API_KEY"); assert.equal(r.repeatSystem, true, "rootsys drops the system message");
  const noModel = gatewayConfig(env({ AI_API_KEY: "k2", AI_BASE_URL: "https://rootsys.cloud/v1", MIRELD_MODEL: "claude-sonnet-5.5" }));
  assert.equal(noModel.model, "", "a Mireld model id is never carried to another gateway");
  const leak = gatewayConfig(env({ AI_API_KEY: "k2", MIRELD_BASE_URL: "https://api.mireld.my/v1" }));
  assert.match(leak.error, /AI_BASE_URL/); assert.equal(leak.base, "", "the AI key is never sent to Mireld's address");
  assert.equal(gatewayConfig(env({ AI_API_KEY: "k2", AI_BASE_URL: "https://example.org/v1", AI_REPEAT_SYSTEM: "1" })).repeatSystem, true);
  assert.equal(gatewayConfig(env({ AI_API_KEY: "k2", AI_BASE_URL: "https://rootsys.cloud/v1", AI_REPEAT_SYSTEM: "0" })).repeatSystem, false);
  assert.equal(gatewayConfig({ MIRELD_API_KEY: "k1" }).name, "Mireld", "a plain object works as the source too");
  assert.equal(gatewayConfig(env({ AI_API_KEY: "k", AI_BASE_URL: "https://llm.example.org/v1" })).name, "llm.example.org");
}
{
  const msgs = [{ role: "system", content: "Be brief." }, { role: "user", content: "Hi" }, { role: "assistant", content: "Hello" }, { role: "user", content: "Again" }];
  const out = withInstructions(msgs);
  assert.equal(out[0].content, "Be brief.", "the system message stays");
  assert.match(out[1].content, /^INSTRUCTIONS \(follow them exactly\):\nBe brief\.\n\nINPUT:\nHi$/);
  assert.equal(out[3].content, "Again", "only the first user turn carries them"); assert.equal(msgs[1].content, "Hi", "the argument is not mutated");
  const parts = withInstructions([{ role: "system", content: "S" }, { role: "user", content: [{ type: "text", text: "read" }, { type: "image_url", image_url: { url: "data:x" } }] }]);
  assert.equal(parts[1].content.length, 3); assert.match(parts[1].content[0].text, /^INSTRUCTIONS/); assert.equal(parts[1].content[2].type, "image_url");
  const same = [{ role: "user", content: "no system" }];
  assert.equal(withInstructions(same), same, "nothing to repeat");
}
{
  // rootsys's list, as on its page: the vision models lead, a non-vision one is never the default, and Claude still wins on Mireld
  const ids = ["glm-5.1", "glm-5.2", "glm-5.3", "glm-5.3-flash", "glm-5.3-flashx", "kimi-k2.7", "kimi-k3", "deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4.1-flash", "minimax-m3", "hy3-tencent", "hy4-preview", "gpt-5.6-luna"];
  assert.equal(rankModels(ids, "").recommended, "glm-5.3-flashx", "a fast vision model first: a layout is thousands of tokens");
  assert.equal(rankModels(ids.filter((x) => x !== "glm-5.3-flashx"), "").recommended, "glm-5.3-flash");
  assert.equal(rankModels(["kimi-k3", "glm-5.1", "deepseek-v4-pro"], "").recommended, "kimi-k3", "with no flash model listed, the best vision one");
  assert.equal(rankModels([...ids, "claude-sonnet-5.5"], "").recommended, "claude-sonnet-5.5");
  assert.equal(readerMessage({ ok: false, status: 503, err: "Scheduled server upgrade", tried: ["kimi-k3"], gateway: "rootsys" }).includes("(rootsys) is down"), true);
  assert.equal(readerMessage({ ok: false, status: 503, err: "upgrade", tried: ["a"] }).includes("The AI gateway is down"), true, "no name, no empty brackets");
}
console.log("gateway config: ok");

// The reader's time budget (Wan, 9 Oct 2026: kimi-k3 then glm-5.3-flash both timed out at 70 s and 50 s).
{
  const t0 = 1_000_000;
  assert.equal(attemptCap(t0, t0, 0), 130000, "the first attempt may use nearly everything");
  assert.equal(attemptCap(t0, t0 + 5000, 1) > 25000, true, "a second try after a quick failure still has real time");
  assert.equal(attemptCap(t0, t0 + 115000, 1), 0, "no 20-second afterthought after a slow first try");
  assert.equal(attemptCap(t0, t0 + 100000, 1), 34000, "a second try with 34 s left is still allowed");
  assert.equal(attemptCap(t0, t0 + 100000, 0), 34000, "the first attempt never runs past the budget either");
  assert.equal(attemptCap(t0, t0 + 200000, 0), 0);
  assert.match(readerMessage({ ok: false, status: 0, err: "the model did not answer in time", tried: ["kimi-k3", "glm-5.3-flash"], gateway: "rootsys" }), /too slowly[\s\S]*flash/);
  assert.doesNotMatch(readerMessage({ ok: false, status: 400, err: "bad image", tried: ["x"] }), /too slowly/);
}
console.log("reader budget: ok");
