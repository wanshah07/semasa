/* semasa-import-video: the pure half of the video intake (index.ts does the reading, the storing and the writing). Node runs this
   file in web/videoImport.test.mjs, so nothing here touches Deno, fetch or a database.

   What the function is: an outside agent (Nous Hermes, Nexabot, huashu-motion) POSTs a finished MP4 with a bearer token Wan made on
   the page. The function checks the token, stores the file in the public bucket semasa-generated as imports/<id>.mp4 (or keeps the
   https address the agent gave), and writes one `semasa_video_imports` row as `received`. The Motion worker
   (backend/semasa/video_import.py) checks the file and the caption and makes a DRAFT post. Nothing here approves anything. */

export const TOKEN_PREFIX = "smi_";
export const MAX_FILE_BYTES = 52_428_800;              // the bucket's own ceiling (supabase/003: 50 MB a file)
export const MAX_BASE64_BYTES = 15_728_640;            // a file sent inside JSON: 15 MiB decoded (the text is a third bigger, held twice)
export const MAX_BODY_SLACK = 1_048_576;               // the form fields and the multipart framing on top of a 50 MB file
export const DEFAULT_PER_HOUR = 20;
export const STREAMS = { regulab: ["instagram", "facebook", "threads"], linkedin: ["linkedin"] };
export const KEY_RE = /^[A-Za-z0-9._:-]{1,128}$/;
export const SLOT_RE = /^([01]\d|2[0-3]):[0-5]\d$/;
export const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** A refusal in one shape: the HTTP status, a code a program can read, a sentence a person can act on. */
export const fail = (status, code, message) => ({ ok: false, status, code, message });

/** The bearer token of a request, or "" (Authorization: Bearer <token>, or x-semasa-import-token). Never logged by anyone. */
export function tokenFrom(headers) {
  const get = (k) => (typeof headers?.get === "function" ? headers.get(k) : (headers || {})[k]) || "";
  const auth = String(get("authorization")).trim();
  const m = /^Bearer\s+(\S+)$/i.exec(auth);
  return (m ? m[1] : String(get("x-semasa-import-token")).trim());
}

/** A string that could be one of our tokens: the prefix and 48 hex characters. Anything else is refused before the database. */
export const looksLikeToken = (t) => typeof t === "string" && new RegExp(`^${TOKEN_PREFIX}[0-9a-f]{48}$`).test(t);

export async function sha256Hex(input) {
  const data = typeof input === "string" ? new TextEncoder().encode(input) : input;
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

/** Constant-time compare of two hex hashes (the same shape semasa-pulse uses for its header secret). */
export function sameHash(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || !a || a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** The token row for a request: the hash is looked up, then compared again in constant time, and a revoked token is no token.
    `rows` is what the database returned for that hash. One answer for every reason, so a caller learns nothing about which. */
export function tokenDecision(hash, rows) {
  const row = (rows || []).find((r) => sameHash(String(r?.token_hash || ""), hash));
  if (!row || row.revoked_at) return fail(401, "bad_token", "The token is missing, wrong or revoked.");
  return { ok: true, row };
}

/** How many imports a token may make in an hour: the setting `video_import.max_per_hour`, else 20. */
export function perHour(setting) {
  const n = Number(setting?.max_per_hour);
  return Number.isFinite(n) && n >= 1 && n <= 1000 ? Math.floor(n) : DEFAULT_PER_HOUR;
}
export function rateDecision(countLastHour, limit) {
  return countLastHour >= limit ? fail(429, "rate_limited", `Too many imports from this token: at most ${limit} an hour.`) : { ok: true };
}

/** An https address that is not obviously inside a network: no credentials, no port other than 443, no localhost, no literal
    private or link-local address. The worker resolves the name again before it fetches (a name can point inward). */
export function publicHttpsUrl(value) {
  let u;
  try { u = new URL(String(value || "")); } catch { return null; }
  if (u.protocol !== "https:" || u.username || u.password || (u.port && u.port !== "443")) return null;
  const h = u.hostname.toLowerCase().replace(/^\[|\]$/g, "");
  if (!h || h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal")) return null;
  if (/^\d+\.\d+\.\d+\.\d+$/.test(h)) {
    const [a, b] = h.split(".").map(Number);
    if (a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168)
      || (a === 100 && b >= 64 && b <= 127) || a >= 224) return null;
  }
  if (h.includes(":") && /^(::1?|f[cd]|fe[89ab])/i.test(h)) return null;            // IPv6 loopback, unique-local, link-local
  if (!h.includes(".") && !h.includes(":")) return null;
  return u.toString();
}

/** An MP4 starts with a box whose type, bytes 4 to 8, is `ftyp`. A cheap sniff; the worker's ffprobe is the real check. */
export function looksLikeMp4(bytes) {
  const b = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes || []);
  return b.length >= 12 && b[4] === 0x66 && b[5] === 0x74 && b[6] === 0x79 && b[7] === 0x70;
}

/** base64 (also base64url, also with a data: prefix) to bytes, or null when it is not base64. */
export function decodeBase64(text) {
  let s = String(text || "").trim().replace(/^data:[^;,]*;base64,/i, "").replace(/\s+/g, "").replace(/-/g, "+").replace(/_/g, "/");
  if (!s || !/^[A-Za-z0-9+/]+={0,2}$/.test(s)) return null;
  while (s.length % 4) s += "=";
  try {
    const bin = atob(s);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  } catch { return null; }
}

const str = (v, max) => (typeof v === "string" ? v.trim().slice(0, max) : "");

/** The caption: one text for every channel, or an object {channel: text}. Never altered here; the worker's compliance scan judges
    it and a caption that fails is refused with the reason, never shortened behind the sender's back. */
export function captionOf(v) {
  if (v == null || v === "") return { ok: true, value: "" };
  if (typeof v === "string") return v.length > 5000 ? fail(422, "caption_too_long", "The caption is over 5000 characters.") : { ok: true, value: v.trim() };
  if (typeof v === "object" && !Array.isArray(v)) {
    const out = {};
    for (const [k, t] of Object.entries(v)) {
      if (!["instagram", "facebook", "threads", "linkedin"].includes(k) || typeof t !== "string") return fail(422, "bad_caption", `caption.${k} is not a channel's text.`);
      if (t.length > 5000) return fail(422, "caption_too_long", `caption.${k} is over 5000 characters.`);
      if (t.trim()) out[k] = t.trim();
    }
    return { ok: true, value: out };
  }
  return fail(422, "bad_caption", "caption must be text or an object of channel texts.");
}

/** The request's options, from a JSON body, a form or a query string alike (`get(name)` gives a string or undefined; `caption`
    may be an object in JSON). Returns {ok, opts} or the refusal. */
export function parseOptions(raw) {
  const o = raw || {};
  const stream = o.stream === undefined || o.stream === "" ? "regulab" : String(o.stream).toLowerCase();
  if (!STREAMS[stream]) return fail(422, "bad_stream", 'stream must be "regulab" or "linkedin".');
  let lang = o.lang === undefined || o.lang === "" ? (stream === "linkedin" ? "en" : "bm") : String(o.lang).toLowerCase();
  if (lang !== "bm" && lang !== "en") return fail(422, "bad_lang", 'lang must be "bm" or "en".');
  if (stream === "linkedin" && lang !== "en") return fail(422, "bad_lang", "LinkedIn is English: lang must be \"en\" for stream linkedin.");
  let channels = o.channels;
  if (typeof channels === "string") channels = channels.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean);
  if (channels === undefined || channels === null || (Array.isArray(channels) && !channels.length)) channels = [...STREAMS[stream]];
  if (!Array.isArray(channels)) return fail(422, "bad_channels", "channels must be a list.");
  channels = [...new Set(channels.map((x) => String(x).toLowerCase()))];
  const bad = channels.filter((c) => !STREAMS[stream].includes(c));
  if (bad.length) return fail(422, "bad_channels", `${bad.join(", ")} is not a channel of stream ${stream} (${STREAMS[stream].join(", ")}).`);
  const cap = captionOf(o.caption);
  if (!cap.ok) return cap;
  const date = str(o.date, 10), slot = str(o.slot, 5);
  if (date && !DATE_RE.test(date)) return fail(422, "bad_date", "date must be YYYY-MM-DD.");
  if (slot && !SLOT_RE.test(slot)) return fail(422, "bad_slot", "slot must be HH:MM (Malaysia time).");
  if (!!date !== !!slot) return fail(422, "bad_slot", "send date and slot together, or neither.");
  const key = str(o.idempotency_key, 128);
  if (key && !KEY_RE.test(key)) return fail(422, "bad_key", "idempotency_key may use letters, digits and . _ : - only, up to 128 characters.");
  const title = str(o.title, 160);
  return { ok: true, opts: { title, caption: cap.value, lang, stream, channels, date, slot, source: str(o.source, 60), idempotency_key: key } };
}

/** What the sender's request amounts to, as one string to hash: the same key with a different request is a conflict (409). */
export function fingerprintInput(opts, fileHash, url) {
  return JSON.stringify([opts.title, opts.caption, opts.lang, opts.stream, [...opts.channels].sort(), opts.date, opts.slot, opts.source,
    fileHash || "", url || ""]);
}

/** Same key from the same token: the first import is the answer (200), unless the request is not the same one (409). */
export function replyFor(existing, fingerprint) {
  if (!existing) return null;
  if (existing.fingerprint && existing.fingerprint !== fingerprint) {
    return fail(409, "idempotency_conflict", "This idempotency_key was already used for a different video or caption. Use a new key.");
  }
  return { ok: true, status: 200, body: answer(existing, true) };
}

/** The response body for an import row. */
export function answer(row, duplicate = false) {
  return { ok: true, import_id: row.id, status: row.status, ...(row.error ? { reason: row.error } : {}), ...(duplicate ? { duplicate: true } : {}) };
}

/** `Content-Length` known and over what this function will take: refused before a byte is read. */
export function tooBigByHeader(contentLength, limit) {
  const n = Number(contentLength);
  return Number.isFinite(n) && n > limit;
}

/** Metadata an upload carries in its query string and headers (a raw body has no JSON to carry it). */
export function optionsFromQuery(searchParams, headers) {
  const get = (k) => searchParams.get(k) ?? undefined;
  const hdr = typeof headers?.get === "function" ? headers.get("idempotency-key") : undefined;
  return { title: get("title"), caption: get("caption"), lang: get("lang"), stream: get("stream"), channels: get("channels"), date: get("date"),
    slot: get("slot"), source: get("source"), idempotency_key: get("idempotency_key") ?? hdr ?? undefined };
}

/** A JSON body: which one source it names. Exactly one of video_url / video_base64. */
export function jsonSource(body) {
  const hasUrl = body?.video_url !== undefined && body.video_url !== "";
  const hasB64 = body?.video_base64 !== undefined && body.video_base64 !== "";
  if (hasUrl === hasB64) return fail(422, "bad_source", "Send exactly one of video_url or video_base64 (or upload the file as multipart or a raw body).");
  if (hasUrl) {
    const url = publicHttpsUrl(body.video_url);
    return url ? { ok: true, url } : fail(422, "bad_url", "video_url must be a public https address.");
  }
  const bytes = decodeBase64(body.video_base64);
  if (!bytes) return fail(422, "bad_base64", "video_base64 is not valid base64.");
  if (bytes.length > MAX_BASE64_BYTES) {
    return fail(413, "too_big", `A file inside JSON may be ${MAX_BASE64_BYTES / 1_048_576} MiB at most; upload it as multipart or a raw body (up to ${MAX_FILE_BYTES / 1_048_576} MiB), or send video_url.`);
  }
  return { ok: true, bytes };
}

/** A body of bytes (multipart file, raw upload, decoded base64): too big, then not an MP4. */
export function fileDecision(bytes) {
  if (!bytes || !bytes.length) return fail(422, "empty_file", "The file is empty.");
  if (bytes.length > MAX_FILE_BYTES) return fail(413, "too_big", `The file is over ${MAX_FILE_BYTES / 1_048_576} MB, the most Semasa stores.`);
  if (!looksLikeMp4(bytes)) return fail(415, "not_mp4", "The file is not an MP4 (it has no ftyp header). Send H.264/AAC in an .mp4 container.");
  return { ok: true };
}

/** What a HEAD on video_url may already say: refuse the obvious (a page, an image, a file over the ceiling). Silence is fine. */
export function headDecision(status, headers) {
  if (!(status >= 200 && status < 300)) return { ok: true };
  const type = String((typeof headers?.get === "function" ? headers.get("content-type") : "") || "").toLowerCase();
  const len = Number(typeof headers?.get === "function" ? headers.get("content-length") : NaN);
  if (/^(text\/|image\/|application\/json)/.test(type)) return fail(415, "not_mp4", `video_url answers ${type.split(";")[0]}, not a video.`);
  if (Number.isFinite(len) && len > MAX_FILE_BYTES) return fail(413, "too_big", `The file at video_url is over ${MAX_FILE_BYTES / 1_048_576} MB, the most Semasa stores.`);
  return { ok: true };
}

export const cors = {
  "access-control-allow-origin": "*",
  "access-control-allow-headers": "authorization, content-type, idempotency-key, x-semasa-import-token",
  "access-control-allow-methods": "POST, OPTIONS",
};
