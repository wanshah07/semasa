// Import video (Wan, 17 Nov 2026): the Edge Function an outside agent sends a finished MP4 to, the page's Import video card, and the
// promise that an import is only ever a DRAFT. The function's entry point runs here with only the database and the bucket replaced.
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";

const here = new URL(".", import.meta.url);
const dir = new URL("../supabase/functions/semasa-import-video/", here);
const L = await import(new URL("logic.js", dir).href);

const TOKEN = "smi_" + "0123456789abcdef".repeat(3);
const OTHER = "smi_" + "fedcba9876543210".repeat(3);
const MP4 = new Uint8Array([0, 0, 0, 24, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d, 0, 0, 2, 0, 1, 2, 3, 4, 5, 6, 7, 8]);

// ---- the pure half
assert.equal(await L.sha256Hex("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", "the same sha256 the database computes");
assert.equal(L.tokenFrom(new Headers({ authorization: `Bearer ${TOKEN}` })), TOKEN);
assert.equal(L.tokenFrom(new Headers({ "x-semasa-import-token": TOKEN })), TOKEN);
assert.equal(L.tokenFrom(new Headers({ authorization: "Basic abc" })), "");
assert.ok(L.looksLikeToken(TOKEN) && !L.looksLikeToken("smi_short") && !L.looksLikeToken("x" + TOKEN) && !L.looksLikeToken(""));
assert.ok(L.sameHash("abcd", "abcd") && !L.sameHash("abcd", "abce") && !L.sameHash("abcd", "abc") && !L.sameHash("", ""));
const hash = await L.sha256Hex(TOKEN);
assert.equal(L.tokenDecision(hash, [{ token_hash: hash, revoked_at: null, id: "t" }]).ok, true);
assert.equal(L.tokenDecision(hash, [{ token_hash: hash, revoked_at: "2026-11-17T00:00:00Z" }]).status, 401, "a revoked token is no token");
assert.equal(L.tokenDecision(hash, []).code, "bad_token");
assert.equal(L.tokenDecision(hash, [{ token_hash: "0".repeat(64) }]).status, 401);
assert.equal(L.perHour(undefined), 20); assert.equal(L.perHour({ max_per_hour: 5 }), 5); assert.equal(L.perHour({ max_per_hour: 0 }), 20); assert.equal(L.perHour({ max_per_hour: "x" }), 20);
assert.equal(L.rateDecision(19, 20).ok, true); assert.equal(L.rateDecision(20, 20).status, 429);

for (const bad of ["http://x.com/a.mp4", "https://localhost/a.mp4", "https://127.0.0.1/a.mp4", "https://10.1.2.3/a.mp4", "https://192.168.0.1/a.mp4", "https://172.20.1.1/a.mp4",
  "https://169.254.169.254/latest", "https://[::1]/a", "https://user:pw@x.com/a.mp4", "https://x.com:8443/a.mp4", "https://intranet/a.mp4", "https://box.local/a.mp4", "nonsense", ""]) {
  assert.equal(L.publicHttpsUrl(bad), null, bad);
}
assert.equal(L.publicHttpsUrl("https://cdn.example.com/clips/a.mp4?x=1"), "https://cdn.example.com/clips/a.mp4?x=1");

assert.ok(L.looksLikeMp4(MP4) && !L.looksLikeMp4(new Uint8Array(40)) && !L.looksLikeMp4(new TextEncoder().encode("<html>............")));
assert.deepEqual([...L.decodeBase64("AQID")], [1, 2, 3]); assert.deepEqual([...L.decodeBase64("data:video/mp4;base64,AQID")], [1, 2, 3]);
assert.equal(L.decodeBase64("not base64!!"), null); assert.equal(L.decodeBase64(""), null);
assert.equal(L.fileDecision(MP4).ok, true);
assert.equal(L.fileDecision(new Uint8Array(0)).code, "empty_file");
assert.equal(L.fileDecision(new TextEncoder().encode("GIF89a not a video at all")).status, 415);
assert.equal(L.fileDecision({ length: L.MAX_FILE_BYTES + 1 }).status, 413);
assert.equal(L.MAX_FILE_BYTES, 50 * 1024 * 1024, "the bucket's own ceiling (supabase/003)");
assert.equal(L.tooBigByHeader("60000000", L.MAX_FILE_BYTES), true); assert.equal(L.tooBigByHeader("100", L.MAX_FILE_BYTES), false); assert.equal(L.tooBigByHeader(null, 1), false);
assert.equal(L.headDecision(200, new Headers({ "content-type": "text/html" })).status, 415);
assert.equal(L.headDecision(200, new Headers({ "content-type": "video/mp4", "content-length": String(L.MAX_FILE_BYTES + 1) })).status, 413);
assert.equal(L.headDecision(405, new Headers()).ok, true, "a host that will not answer a HEAD is not an error");

// options: defaults by stream, LinkedIn is English, channels are the stream's own, date and slot go together
const o = (x) => L.parseOptions(x);
assert.deepEqual(o({}).opts.channels, ["instagram", "facebook", "threads"]); assert.equal(o({}).opts.lang, "bm"); assert.equal(o({}).opts.stream, "regulab");
assert.deepEqual(o({ stream: "linkedin" }).opts, { title: "", caption: "", lang: "en", stream: "linkedin", channels: ["linkedin"], date: "", slot: "", source: "", idempotency_key: "" });
assert.equal(o({ stream: "linkedin", lang: "bm" }).code, "bad_lang");
assert.equal(o({ stream: "tiktok" }).code, "bad_stream");
assert.equal(o({ channels: "instagram, threads" }).opts.channels.join(), "instagram,threads");
assert.equal(o({ channels: ["linkedin"] }).code, "bad_channels", "LinkedIn is not a ws.regulab channel");
assert.equal(o({ stream: "linkedin", channels: ["instagram"] }).code, "bad_channels");
assert.equal(o({ date: "2026-11-20" }).code, "bad_slot"); assert.equal(o({ date: "2026-11-20", slot: "13:00" }).ok, true);
assert.equal(o({ date: "20-11-2026", slot: "13:00" }).code, "bad_date"); assert.equal(o({ date: "2026-11-20", slot: "25:00" }).code, "bad_slot");
assert.equal(o({ idempotency_key: "has space" }).code, "bad_key"); assert.equal(o({ idempotency_key: "run-42:a.b" }).opts.idempotency_key, "run-42:a.b");
assert.equal(o({ lang: "id" }).code, "bad_lang");
assert.deepEqual(o({ caption: { instagram: " Hi ", threads: "" } }).opts.caption, { instagram: "Hi" });
assert.equal(o({ caption: { tiktok: "x" } }).code, "bad_caption"); assert.equal(o({ caption: "x".repeat(5001) }).code, "caption_too_long"); assert.equal(o({ caption: 5 }).code, "bad_caption");
assert.equal(o({ caption: "A caption with www.kkmhalalconsultant.com in it" }).opts.caption, "A caption with www.kkmhalalconsultant.com in it", "never altered here: the worker's scan judges it");

// the source of a JSON body: exactly one
assert.equal(L.jsonSource({}).code, "bad_source"); assert.equal(L.jsonSource({ video_url: "https://a.com/x.mp4", video_base64: "AQID" }).code, "bad_source");
assert.equal(L.jsonSource({ video_url: "http://a.com/x.mp4" }).code, "bad_url"); assert.equal(L.jsonSource({ video_base64: "@@@" }).code, "bad_base64");
assert.equal(L.jsonSource({ video_url: "https://a.com/x.mp4" }).url, "https://a.com/x.mp4");
assert.equal(L.jsonSource({ video_base64: "AQID" }).bytes.length, 3);

// idempotency: the same key and request is the first import; the same key and another request is a conflict
const fp = L.fingerprintInput(L.parseOptions({ title: "a" }).opts, "h1", "");
assert.equal(L.replyFor(null, fp), null);
assert.deepEqual(L.replyFor({ id: "i1", status: "done", fingerprint: fp }, fp), { ok: true, status: 200, body: { ok: true, import_id: "i1", status: "done", duplicate: true } });
assert.equal(L.replyFor({ id: "i1", status: "done", fingerprint: fp }, fp + "x").status, 409);
assert.equal(L.answer({ id: "i2", status: "error", error: "too long" }).reason, "too long");

// ---- the entry point, with the database and the bucket replaced
const state = { tokens: [], imports: [], settings: [], files: {}, touched: new Set(), logs: [] };
const sha = L.sha256Hex;
class Q {
  constructor(table) { this.table = table; this.f = []; this.op = "select"; this.row = null; this.n = null; }
  select() { return this; } insert(r) { this.op = "insert"; this.row = r; return this; } update(r) { this.op = "update"; this.row = r; return this; }
  eq(k, v) { this.f.push((r) => r[k] === v); return this; } gte(k, v) { this.f.push((r) => String(r[k]) >= String(v)); return this; }
  limit(n) { this.n = n; return this; }
  rows() { const t = { semasa_import_tokens: state.tokens, semasa_video_imports: state.imports, semasa_settings: state.settings }[this.table]; return t; }
  run(single) {
    state.touched.add(this.table);
    const t = this.rows();
    if (!t) throw new Error(`the function touched ${this.table}`);
    if (this.op === "insert") {
      if (this.row.idempotency_key && t.some((r) => r.token_id === this.row.token_id && r.idempotency_key === this.row.idempotency_key)) return { error: { code: "23505", message: "duplicate" } };
      t.push({ created_at: new Date().toISOString(), ...structuredClone(this.row) }); return { error: null };
    }
    const hit = t.filter((r) => this.f.every((f) => f(r)));
    if (this.op === "update") { hit.forEach((r) => Object.assign(r, this.row)); return { error: null }; }
    const data = hit.slice(0, this.n ?? undefined).map((r) => structuredClone(r));
    return { data: single ? data[0] || null : data, error: null };
  }
  maybeSingle() { return Promise.resolve(this.run(true)); }
  then(ok, bad) { return Promise.resolve().then(() => this.run(false)).then(ok, bad); }
}
const admin = {
  from: (t) => new Q(t),
  storage: { from: (b) => { assert.equal(b, "semasa-generated", "the public bucket the worker already uses");
    return { upload: async (p, bytes, opts) => { assert.equal(opts.contentType, "video/mp4"); state.files[p] = bytes; return { error: null }; }, remove: async (ps) => { ps.forEach((p) => delete state.files[p]); return { error: null }; } }; } },
};
let handler;
const realLog = console.log, realErr = console.error, realWarn = console.warn;
for (const k of ["log", "error", "warn", "info"]) console[k] = (...a) => state.logs.push(a.join(" "));
globalThis.Deno = { env: { get: (k) => ({ SUPABASE_URL: "https://project.supabase.co", SUPABASE_SERVICE_ROLE_KEY: "service-key" })[k] }, serve: (fn) => { handler = fn; } };
let headStatus = 200, headType = "video/mp4", headLen = "1000";
globalThis.fetch = async (u, init) => { assert.equal(init.method, "HEAD"); return new Response(null, { status: headStatus, headers: { "content-type": headType, "content-length": headLen } }); };
const entry = new URL("index.ts", dir);
let src = ts.transpileModule(readFileSync(entry, "utf8"), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } }).outputText;
src = src.replace(/import \{ createClient \} from "npm:@supabase\/supabase-js@2";/, "const createClient = globalThis.__importAdmin;");
src = src.replace(/from "(\.[^"]+)"/g, (_a, p) => `from ${JSON.stringify(new URL(p, entry).href)}`);
globalThis.__importAdmin = () => admin;
await import("data:text/javascript;base64," + Buffer.from(src).toString("base64"));

const reset = async () => {
  state.tokens = [{ id: "tok1", label: "hermes", token_hash: await sha(TOKEN), revoked_at: null }];
  state.imports = []; state.settings = []; state.files = {}; state.touched = new Set();
};
const call = (init = {}, token = TOKEN, url = "https://f.example/functions/v1/semasa-import-video") =>
  handler(new Request(url, { method: "POST", ...init, headers: { ...(token ? { authorization: `Bearer ${token}` } : {}), ...(init.headers || {}) } }));
const form = (bytes, fields = {}) => { const f = new FormData(); f.set("file", new Blob([bytes], { type: "video/mp4" }), "a.mp4"); for (const [k, v] of Object.entries(fields)) f.set(k, v); return { body: f }; };
const json = (body, headers = {}) => ({ body: JSON.stringify(body), headers: { "content-type": "application/json", ...headers } });
const read = async (r) => ({ status: r.status, body: await r.json() });

await reset();
assert.equal((await handler(new Request("https://f.example", { method: "GET" }))).status, 405);
assert.equal((await handler(new Request("https://f.example", { method: "OPTIONS" }))).status, 200);

// the token: missing, wrong, malformed, revoked
for (const t of ["", OTHER, "smi_nope", "Bearer"]) {
  const r = await read(await call(form(MP4), t));
  assert.equal(r.status, 401, `token "${t}"`); assert.equal(r.body.error, "bad_token");
}
state.tokens[0].revoked_at = "2026-11-17T00:00:00Z";
assert.equal((await call(form(MP4))).status, 401, "a revoked token is refused");
assert.equal(state.imports.length, 0, "a refused call writes nothing"); assert.equal(Object.keys(state.files).length, 0);
await reset();

// a good upload: stored in the public bucket, one row, received
let r = await read(await call(form(MP4, { title: "Notifikasi kosmetik", caption: "Satu ayat.", source: "hermes", idempotency_key: "run-1" })));
assert.equal(r.status, 202); assert.equal(r.body.ok, true); assert.equal(r.body.status, "received");
const id = r.body.import_id;
assert.equal(state.imports.length, 1);
const stored = state.imports[0];
assert.equal(stored.status, "received"); assert.equal(stored.stored_path, `imports/${id}.mp4`); assert.ok(state.files[`imports/${id}.mp4`]);
assert.equal(stored.token_id, "tok1"); assert.equal(stored.token_label, "hermes"); assert.equal(stored.source, "hermes"); assert.equal(stored.bytes, MP4.length);
assert.equal(stored.params.title, "Notifikasi kosmetik"); assert.equal(stored.params.stream, "regulab"); assert.deepEqual(stored.params.channels, ["instagram", "facebook", "threads"]);
assert.ok(state.tokens[0].last_used_at, "last_used_at is stamped");

// the same key again is the FIRST import, never a second one and never a second file
const before = JSON.stringify(state.files);
r = await read(await call(form(MP4, { title: "Notifikasi kosmetik", caption: "Satu ayat.", source: "hermes", idempotency_key: "run-1" })));
assert.equal(r.status, 200); assert.equal(r.body.import_id, id); assert.equal(r.body.duplicate, true);
assert.equal(state.imports.length, 1); assert.equal(JSON.stringify(state.files), before);
// the same key with a different request is a conflict
r = await read(await call(form(MP4, { title: "Another title", idempotency_key: "run-1" })));
assert.equal(r.status, 409); assert.equal(r.body.error, "idempotency_conflict"); assert.equal(state.imports.length, 1);
// another token's key of the same name is its own
state.tokens.push({ id: "tok2", label: "nexabot", token_hash: await sha(OTHER), revoked_at: null });
r = await read(await call(form(MP4, { title: "Notifikasi kosmetik", caption: "Satu ayat.", source: "hermes", idempotency_key: "run-1" }), OTHER));
assert.equal(r.status, 202); assert.notEqual(r.body.import_id, id); assert.equal(state.imports.length, 2);
// the Idempotency-Key header works for a raw upload
r = await read(await call({ body: MP4, headers: { "content-type": "video/mp4", "idempotency-key": "raw-1" } }, TOKEN, "https://f.example/x?title=Raw&stream=linkedin&caption=Hello"));
assert.equal(r.status, 202); const raw = state.imports.find((x) => x.idempotency_key === "raw-1");
assert.equal(raw.params.stream, "linkedin"); assert.equal(raw.params.lang, "en"); assert.deepEqual(raw.params.channels, ["linkedin"]); assert.equal(raw.params.title, "Raw");
r = await read(await call({ body: MP4, headers: { "content-type": "video/mp4", "idempotency-key": "raw-1" } }, TOKEN, "https://f.example/x?title=Raw&stream=linkedin&caption=Hello"));
assert.equal(r.status, 200); assert.equal(r.body.duplicate, true);
await reset();

// not an MP4, too big, empty, bad fields: the right status and nothing stored
r = await read(await call(form(new TextEncoder().encode("this is a text file, not video"))));
assert.equal(r.status, 415); assert.equal(r.body.error, "not_mp4");
r = await read(await call({ body: MP4, headers: { "content-type": "video/mp4", "content-length": String(L.MAX_FILE_BYTES + L.MAX_BODY_SLACK + 5) } }));
assert.equal(r.status, 413); assert.equal(r.body.error, "too_big");
r = await read(await call(json({ video_base64: Buffer.from(new Uint8Array(L.MAX_BASE64_BYTES + 10)).toString("base64") })));
assert.equal(r.status, 413);
r = await read(await call(json({ video_base64: Buffer.from(MP4).toString("base64"), stream: "linkedin", lang: "bm" })));
assert.equal(r.status, 422); assert.equal(r.body.error, "bad_lang");
r = await read(await call(json({ video_url: "http://a.com/x.mp4" })));
assert.equal(r.status, 422);
r = await read(await call(json({ video_base64: Buffer.from("not an mp4 but long enough....").toString("base64") })));
assert.equal(r.status, 415);
assert.equal(state.imports.length, 0, "a refused request records nothing"); assert.equal(Object.keys(state.files).length, 0, "and stores nothing");

// base64 and a link are accepted
r = await read(await call(json({ video_base64: Buffer.from(MP4).toString("base64"), title: "B64" })));
assert.equal(r.status, 202); assert.ok(state.files[`imports/${r.body.import_id}.mp4`]);
r = await read(await call(json({ video_url: "https://cdn.example.com/a.mp4", caption: { instagram: "Hi" } })));
assert.equal(r.status, 202); const linked = state.imports.find((x) => x.id === r.body.import_id);
assert.equal(linked.source_url, "https://cdn.example.com/a.mp4"); assert.equal(linked.stored_path, ""); assert.deepEqual(linked.params.caption, { instagram: "Hi" });
headType = "text/html";
assert.equal((await call(json({ video_url: "https://cdn.example.com/page" }))).status, 415, "a link that is a web page is refused now");
headType = "video/mp4"; headLen = String(L.MAX_FILE_BYTES + 1);
assert.equal((await call(json({ video_url: "https://cdn.example.com/huge.mp4" }))).status, 413);
await reset();

// the rate: setting-driven, per token, an hour
state.settings = [{ key: "video_import", value: { max_per_hour: 2 } }];
for (const k of ["a", "b"]) assert.equal((await call(form(MP4, { idempotency_key: k }))).status, 202);
r = await read(await call(form(MP4, { idempotency_key: "c" })));
assert.equal(r.status, 429); assert.equal(r.body.error, "rate_limited"); assert.equal(state.imports.length, 2);
await reset();

// THE GATE: the function writes `received` and nothing else, and never touches a post, a film or the media table
await call(form(MP4, { idempotency_key: "g1" })); await call(json({ video_url: "https://cdn.example.com/g.mp4" }));
assert.ok(state.imports.every((x) => x.status === "received"), "an import is only ever received here");
for (const t of state.touched) assert.ok(["semasa_import_tokens", "semasa_video_imports", "semasa_settings"].includes(t), `touched ${t}`);

// THE TOKEN: never stored, never echoed, never logged
const everything = JSON.stringify([state.tokens, state.imports, state.settings, Object.keys(state.files), state.logs]);
assert.ok(!everything.includes(TOKEN) && !everything.includes(OTHER), "the plain token is in no row, no path and no log line");
assert.ok(state.tokens[0].token_hash === hash && /^[0-9a-f]{64}$/.test(hash), "only its sha256 is kept");
for (const resp of [await call(form(MP4, { idempotency_key: "echo" })), await call(form(MP4), OTHER)]) assert.ok(!(await resp.text()).includes(TOKEN));
for (const k of ["log", "error", "warn", "info"]) console[k] = { log: realLog, error: realErr, warn: realWarn, info: realLog }[k];

// ---- the deploy and the SQL
const wf = readFileSync(new URL("../.github/workflows/functions.yml", here), "utf8");
assert.match(wf, /semasa-telegram\|semasa-pulse\|semasa-import-video\) extra="--no-verify-jwt"/, "deployed --no-verify-jwt: the caller has no Supabase login");
assert.match(wf, /Three exceptions/);
const sql = readFileSync(new URL("../supabase/087_video_import.sql", here), "utf8");
assert.match(sql, /token_hash\s+text not null unique/); assert.match(sql, /encode\(extensions\.digest\(v_token, 'sha256'\), 'hex'\)/);
assert.match(sql, /grant select \(id, label, created_at, last_used_at, revoked_at\)/, "the hash column is not readable by a browser login");
assert.doesNotMatch(sql, /status\s*=\s*'(approved|scheduled|posted)'|insert into public\.semasa_posts/i, "the SQL never makes or approves a post");
assert.match(sql, /semasa_is_uploader\(\)/); assert.match(sql, /notify pgrst, 'reload schema'/);

// ---- the page: the card exists, is on the Video page and reads/writes only what the SQL allows
const card = readFileSync(new URL("src/components/VideoImportCard.jsx", here), "utf8");
const lib = readFileSync(new URL("src/lib/videoImport.js", here), "utf8");
const tab = readFileSync(new URL("src/pages/VideoTab.jsx", here), "utf8");
assert.match(tab, /VideoImportCard/);
assert.match(card, /semasa_import_token_create/); assert.match(card, /semasa_import_token_revoke/);
assert.doesNotMatch(card, /token_hash/, "the page never asks for the hash");
const dir2 = mkdtempSync(join(tmpdir(), "vi-"));
writeFileSync(join(dir2, "videoImport.js"), lib);
const V = await import(pathToFileURL(join(dir2, "videoImport.js")).href);
assert.equal(V.endpointUrl("https://abc.supabase.co"), "https://abc.supabase.co/functions/v1/semasa-import-video");
assert.equal(V.endpointUrl("https://abc.supabase.co/"), "https://abc.supabase.co/functions/v1/semasa-import-video");
const curl = V.curlExample("https://abc.supabase.co", "smi_xyz");
assert.match(curl, /curl -X POST "https:\/\/abc\.supabase\.co\/functions\/v1\/semasa-import-video"/); assert.match(curl, /Authorization: Bearer smi_xyz/); assert.match(curl, /-F "file=@/); assert.match(curl, /idempotency_key/);
assert.match(V.curlExample("https://abc.supabase.co", ""), /Bearer <token>/, "no token is shown once it is gone");
const tk = V.tokenRows([{ id: "a", label: "hermes", created_at: "2026-11-10T00:00:00Z", last_used_at: null, revoked_at: null },
  { id: "b", label: "old", created_at: "2026-11-01T00:00:00Z", last_used_at: "2026-11-05T00:00:00Z", revoked_at: "2026-11-06T00:00:00Z" }]);
assert.deepEqual(tk.map((x) => [x.id, x.active]), [["a", true], ["b", false]]);
const st = V.importStatus({ status: "done", error: "", note: "a platform copy was made (3.1 MB)", post_id: "p1" });
assert.equal(st.tone, "ok"); assert.match(st.words[1], /draft/i);
assert.equal(V.importStatus({ status: "error", error: "the video is 100 s" }).tone, "danger");
assert.equal(V.importStatus({ status: "received" }).tone, "muted"); assert.equal(V.importStatus({ status: "working" }).tone, "muted");
assert.ok(!JSON.stringify(V.importStatus({ status: "done", post_id: "p" })).match(/approved|dilulus|diluluskan/i), "the card never says an import was approved");

console.log("video import: ok");
