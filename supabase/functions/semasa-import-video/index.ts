// semasa-import-video: the way an outside agent (Nous Hermes, Nexabot, huashu-motion) sends a finished MP4 into Semasa
// (Wan, 17 Nov 2026). It stores the file and writes a `semasa_video_imports` row as `received`; the Motion worker
// (backend/semasa/video_import.py) then checks the file and the caption and makes a DRAFT post. Nothing here approves,
// schedules or posts anything: Wan's own Approve click stays the only gate (docs/VIDEO-IMPORT.md).
//
// Who may call it: deployed --no-verify-jwt (the caller has no Supabase login, like semasa-telegram and semasa-pulse). The gate is
// a bearer token Wan made on the page (supabase/087_video_import.sql): the database keeps only its sha256, the function hashes what
// it is sent, looks the hash up, compares it again in constant time, and refuses a revoked one. The token is never logged, never
// stored and never echoed.
//
// Request: POST, Authorization: Bearer smi_...
//   * multipart/form-data: `file` (the MP4) and optional fields title, caption, lang, stream, channels, date, slot, source, idempotency_key;
//   * a raw body (Content-Type: video/mp4) with the same options in the query string (and an Idempotency-Key header);
//   * application/json: video_url (a public https address, fetched by the worker) OR video_base64 (small files), plus the options.
// Response: 202 { ok, import_id, status:"received" }; the same idempotency_key again answers 200 with the first import
// ({duplicate:true}) and never a second one; 401 bad token, 413 too big, 415 not an MP4, 422 a field is wrong, 409 the key was
// used for a different request, 429 too many an hour.
//
// Limits: a stored file is at most 50 MB (the bucket's own ceiling); inside JSON 15 MiB; the Edge runtime itself has 256 MB of
// memory and a 150 s wall clock on the free plan (400 s paid), which a 50 MB upload sits well inside. Secrets: none of its own
// (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are given by Supabase).
import { createClient } from "npm:@supabase/supabase-js@2";
import {
  MAX_BASE64_BYTES, MAX_BODY_SLACK, MAX_FILE_BYTES, answer, cors, fail, fileDecision, fingerprintInput, headDecision, jsonSource, looksLikeToken,
  optionsFromQuery, parseOptions, perHour, rateDecision, replyFor, sha256Hex, tokenDecision, tokenFrom, tooBigByHeader,
} from "./logic.js";

const BUCKET = "semasa-generated";

const send = (body: unknown, status = 200, extra: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "content-type": "application/json", ...extra } });
const refuse = (f: { status: number; code: string; message: string }, extra: Record<string, string> = {}) =>
  send({ ok: false, error: f.code, message: f.message }, f.status, extra);

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return refuse(fail(405, "post_only", "POST only."));
  const url = Deno.env.get("SUPABASE_URL") || "", service = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") || "";
  if (!url || !service) return refuse(fail(500, "not_configured", "The function is missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY."));
  const admin = createClient(url, service, { auth: { persistSession: false, autoRefreshToken: false } });

  // ---- 1 · the token: shape first (no database call for a guess), then the hash, then a constant-time compare, then revoked?
  const token = tokenFrom(req.headers);
  if (!looksLikeToken(token)) return refuse(fail(401, "bad_token", "The token is missing, wrong or revoked."));
  const hash = await sha256Hex(token);
  const found = await admin.from("semasa_import_tokens").select("id,label,token_hash,revoked_at").eq("token_hash", hash).limit(2);
  if (found.error) return refuse(fail(500, "token_table", "The import tables are not set up yet (supabase/087_video_import.sql)."));
  const who = tokenDecision(hash, found.data);
  if (!who.ok) return refuse(who);
  const tok = who.row;

  // ---- 2 · the rate: imports from this token in the last hour against the setting (default 20 an hour)
  const setting = await admin.from("semasa_settings").select("value").eq("key", "video_import").maybeSingle();
  const limit = perHour(setting.data?.value);
  const since = new Date(Date.now() - 3600_000).toISOString();
  const recent = await admin.from("semasa_video_imports").select("id").eq("token_id", tok.id).gte("created_at", since).limit(limit + 1);
  const rate = rateDecision((recent.data || []).length, limit);
  if (!rate.ok) return refuse(rate, { "retry-after": "600" });

  // ---- 3 · read the request: a file (multipart or raw), or JSON naming a file
  const type = (req.headers.get("content-type") || "").toLowerCase();
  const isJson = type.includes("application/json");
  const isForm = type.includes("multipart/form-data");
  const cap = isJson ? Math.ceil(MAX_BASE64_BYTES * 1.4) + MAX_BODY_SLACK : MAX_FILE_BYTES + MAX_BODY_SLACK;
  if (tooBigByHeader(req.headers.get("content-length"), cap)) {
    return refuse(fail(413, "too_big", `The request is over ${Math.round(cap / 1_048_576)} MB. A file may be ${MAX_FILE_BYTES / 1_048_576} MB at most (JSON: ${MAX_BASE64_BYTES / 1_048_576} MiB).`));
  }

  let raw: Record<string, unknown> = {};
  let bytes: Uint8Array | null = null;
  let sourceUrl = "";
  try {
    if (isJson) {
      const body = await req.json();
      raw = body && typeof body === "object" ? body : {};
      const src = jsonSource(raw);
      if (!src.ok) return refuse(src);
      if (src.bytes) bytes = src.bytes; else sourceUrl = src.url as string;
    } else if (isForm) {
      const form = await req.formData();
      const file = form.get("file");
      if (!file || typeof file === "string") return refuse(fail(422, "bad_source", "Send the MP4 as the multipart field `file`."));
      const chans = form.getAll("channels").map(String);
      raw = Object.fromEntries([...form.entries()].filter(([, v]) => typeof v === "string"));
      if (chans.length > 1) raw.channels = chans;
      bytes = new Uint8Array(await (file as File).arrayBuffer());
    } else {
      bytes = new Uint8Array(await req.arrayBuffer());
      raw = optionsFromQuery(new URL(req.url).searchParams, req.headers);
    }
  } catch {
    return refuse(fail(400, "bad_request", "The request body could not be read."));
  }
  if (isJson && raw.idempotency_key === undefined) raw.idempotency_key = req.headers.get("idempotency-key") ?? undefined;
  if (isForm && raw.idempotency_key === undefined) raw.idempotency_key = req.headers.get("idempotency-key") ?? undefined;

  const parsed = parseOptions(raw);
  if (!parsed.ok) return refuse(parsed);
  const opts = parsed.opts;
  if (bytes) {
    const checked = fileDecision(bytes);
    if (!checked.ok) return refuse(checked);
  } else {
    // a link: ask once what is there (a page or an over-size file is refused now); a host that will not answer a HEAD is not an error
    try {
      const head = await fetch(sourceUrl, { method: "HEAD", redirect: "follow", signal: AbortSignal.timeout(5000) });
      const verdict = headDecision(head.status, head.headers);
      if (!verdict.ok) return refuse(verdict);
    } catch { /* the worker fetches it and says what it found */ }
  }

  // ---- 4 · idempotency: the same key from this token is the first import, never a second one
  const fingerprint = await sha256Hex(fingerprintInput(opts, bytes ? await sha256Hex(bytes) : "", sourceUrl));
  const findFirst = async () => {
    const r = await admin.from("semasa_video_imports").select("id,status,error,fingerprint").eq("token_id", tok.id)
      .eq("idempotency_key", opts.idempotency_key).maybeSingle();
    return r.data || null;
  };
  if (opts.idempotency_key) {
    const again = replyFor(await findFirst(), fingerprint);
    if (again) return again.ok ? send(again.body, again.status, { "idempotent-replayed": "true" }) : refuse(again);
  }

  // ---- 5 · store the file, then the row
  const id = crypto.randomUUID();
  let storedPath = "";
  if (bytes) {
    storedPath = `imports/${id}.mp4`;
    const up = await admin.storage.from(BUCKET).upload(storedPath, bytes, { contentType: "video/mp4", upsert: false });
    if (up.error) return refuse(fail(502, "storage", "The file could not be stored. Try again."));
  }
  const row = {
    id, token_id: tok.id, token_label: tok.label, status: "received", source: opts.source, idempotency_key: opts.idempotency_key || null, fingerprint,
    source_url: sourceUrl, stored_path: storedPath, bytes: bytes ? bytes.length : 0,
    params: { title: opts.title, caption: opts.caption, lang: opts.lang, stream: opts.stream, channels: opts.channels, date: opts.date, slot: opts.slot },
  };
  const made = await admin.from("semasa_video_imports").insert(row);
  if (made.error) {
    if (storedPath) await admin.storage.from(BUCKET).remove([storedPath]).then(() => {}, () => {});
    if (String(made.error.code) === "23505" && opts.idempotency_key) {            // a second request with the same key landed first
      const again = replyFor(await findFirst(), fingerprint);
      if (again) return again.ok ? send(again.body, again.status, { "idempotent-replayed": "true" }) : refuse(again);
    }
    return refuse(fail(500, "write", "The import could not be recorded. Try again."));
  }
  await admin.from("semasa_import_tokens").update({ last_used_at: new Date().toISOString() }).eq("id", tok.id).then(() => {}, () => {});
  return send(answer({ id, status: "received" }), 202);
});
