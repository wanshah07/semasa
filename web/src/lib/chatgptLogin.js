/* Motion's ChatGPT login (Wan, 5 Nov 2026: "for motion - add codex or chatgpt login Oauth, so image motion can generate based on
   story board and styles apply"). Wan pastes ~/.codex/auth.json (written by `codex login`, the ChatGPT option); the page checks it,
   sends it to supabase/058's semasa_chatgpt_connect and never reads it back. Pure helpers, tested in chatgptLogin.test.mjs. */

const b64json = (part) => {
  try {
    const s = String(part).replace(/-/g, "+").replace(/_/g, "/");
    const bin = typeof atob === "function" ? atob(s + "=".repeat((4 - (s.length % 4)) % 4)) : Buffer.from(s, "base64").toString("binary");
    return JSON.parse(decodeURIComponent(Array.from(bin, (c) => "%" + c.charCodeAt(0).toString(16).padStart(2, "0")).join("")));
  } catch { return {}; }
};
/** The payload of a JWT, unverified; {} when it is not one. */
export const claims = (token) => b64json(String(token || "").split(".")[1] || "");

export const PARSE_ERRORS = {
  empty: ["Tampal kandungan auth.json dahulu.", "Paste the contents of auth.json first."],
  json: ["Itu bukan JSON yang sah. Salin seluruh fail auth.json.", "That is not valid JSON. Copy the whole auth.json file."],
  apikey: ["Fail ini log masuk dengan kunci API, bukan ChatGPT. Jalankan `codex login` dan pilih Sign in with ChatGPT.",
    "This file is an API-key login, not ChatGPT. Run `codex login` and choose Sign in with ChatGPT."],
  tokens: ["auth.json tiada access_token dan refresh_token. Jalankan `codex login` dengan ChatGPT.",
    "auth.json has no access_token and refresh_token. Run `codex login` with ChatGPT."],
  shape: ["Token itu tidak kelihatan betul (panjang, tanpa ruang).", "Those tokens do not look right (long strings, no spaces)."],
};

/** {ok:true, auth, account, expires} or {ok:false, code}. Accepts the whole auth.json or just its "tokens" object. Only the tokens are
    kept: an API key sitting beside them in the file is dropped here and never sent. */
export function parseAuth(text) {
  const raw = String(text || "").trim();
  if (!raw) return { ok: false, code: "empty" };
  let obj;
  try { obj = JSON.parse(raw); } catch { return { ok: false, code: "json" }; }
  if (!obj || typeof obj !== "object" || Array.isArray(obj)) return { ok: false, code: "json" };
  const t = obj.tokens && typeof obj.tokens === "object" ? obj.tokens : obj;
  const access = typeof t.access_token === "string" ? t.access_token.trim() : "";
  const refresh = typeof t.refresh_token === "string" ? t.refresh_token.trim() : "";
  if (!access || !refresh) return { ok: false, code: obj.OPENAI_API_KEY && !obj.tokens ? "apikey" : "tokens" };
  if (/\s/.test(access) || /\s/.test(refresh) || access.length < 40 || refresh.length < 20) return { ok: false, code: "shape" };
  const tokens = { access_token: access, refresh_token: refresh };
  for (const k of ["id_token", "account_id"]) if (typeof t[k] === "string" && t[k].trim()) tokens[k] = t[k].trim();
  const exp = claims(access).exp;
  return {
    ok: true, auth: { tokens },
    account: String(claims(tokens.id_token).email || "").slice(0, 120) || null,
    expires: typeof exp === "number" ? new Date(exp * 1000).toISOString() : null,
  };
}

/** What the card says about the saved login, from semasa_chatgpt_status(). state: none | error | off | ok | ready | idle.
    A last_error newer than the last success is an error; ok is a real picture drawn; ready is a login ChatGPT accepted (a refresh
    worked) with no picture drawn yet; idle is saved and not yet checked. */
export function stateOf(status) {
  if (!status || !status.connected) return "none";
  const ok = Date.parse(status.last_ok_at || "") || 0;
  const bad = Date.parse(status.last_error_at || "") || 0;
  if (bad > ok) return "error";
  if (status.enabled === false) return "off";
  if (ok) return "ok";
  return status.checked_at ? "ready" : "idle";
}

export const STATE_WORDS = {
  none: ["Belum disambung", "Not connected"],
  idle: ["Disimpan, belum diuji", "Saved, not tested yet"],
  ready: ["Log masuk diterima, belum ada gambar", "Login accepted, no picture yet"],
  ok: ["Berfungsi", "Working"],
  off: ["Dimatikan", "Switched off"],
  error: ["Ada masalah", "Needs attention"],
};
export const STATE_CLS = { none: "bg-muted/15 text-muted", idle: "bg-warn/15 text-warn", ready: "bg-accent/15 text-accent", ok: "bg-ok/15 text-ok", off: "bg-muted/15 text-muted", error: "bg-danger/15 text-danger" };

export const MAX_IMAGES = [1, 2, 3, 4, 5, 6, 7, 8];
export const DEFAULT_MODEL = "gpt-5.5";   // "gpt-5" is refused for a ChatGPT account (Codex)
/** The model field: letters, digits and . _ : - (the database checks the same). */
export const validModel = (m) => /^[A-Za-z0-9._:-]{1,64}$/.test(String(m || "").trim());
