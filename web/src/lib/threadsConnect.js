/* Wan's own Threads app (supabase/080, 13 Nov 2026): the Threads app ID, the Threads app secret and a long-lived user token are
   typed once into a card on the API page and sent to semasa_threads_connect; the page can never read the secret or the token back
   (no policy on semasa_threads_auth). These checks are the same rules as the function's, so a typo is caught before it is sent.
   Pure helpers, tested in threadsConnect.test.mjs. */

export const validAppId = (s) => /^[0-9]{6,24}$/.test(String(s ?? "").trim());
export const validSecret = (s) => /^[A-Za-z0-9]{16,64}$/.test(String(s ?? "").trim());
export const validToken = (s) => { const v = String(s ?? "").trim(); return v.length >= 40 && !/\s/.test(v); };

/** Why the three fields cannot be sent yet, as a key into FIELD_ERRORS, or "" when they can. */
export function fieldProblem(appId, secret, token) {
  if (!validAppId(appId)) return "app_id";
  if (!validSecret(secret)) return "secret";
  if (!validToken(token)) return "token";
  return "";
}

export const FIELD_ERRORS = {
  app_id: ["ID aplikasi Threads ialah nombor sahaja (Meta: Use cases, Access the Threads API, Settings).", "The Threads app ID is digits only (Meta: Use cases, Access the Threads API, Settings)."],
  secret: ["Rahsia aplikasi Threads ialah huruf dan nombor sahaja, tanpa ruang (tekan Show di halaman yang sama).", "The Threads app secret is letters and digits only, no spaces (press Show on the same page)."],
  token: ["Token itu tidak kelihatan betul: ia rentetan panjang tanpa ruang.", "That does not look like a long-lived Threads token: a long string with no spaces."],
};

/** What the card says about the saved connection, from semasa_threads_status(). state: none | error | off | ok | ready | idle.
    A last_error newer than the last success is an error; ok is public posts read; ready is a token Threads accepted (the account
    was read) with no public posts yet; idle is saved and not yet checked by the next Sources run. */
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
  idle: ["Disimpan, belum disemak", "Saved, not checked yet"],
  ready: ["Token diterima, belum ada pos awam", "Token accepted, no public posts yet"],
  ok: ["Berfungsi", "Working"],
  off: ["Dimatikan", "Switched off"],
  error: ["Ada masalah", "Needs attention"],
};
export const STATE_CLS = { none: "bg-muted/15 text-muted", idle: "bg-warn/15 text-warn", ready: "bg-accent/15 text-accent", ok: "bg-ok/15 text-ok", off: "bg-muted/15 text-muted", error: "bg-danger/15 text-danger" };

/** The error line when Meta has not approved keyword search: it names the permission so the card can say what to do next. */
export const needsApproval = (status) => /threads_keyword_search/i.test(String(status?.last_error || ""));
