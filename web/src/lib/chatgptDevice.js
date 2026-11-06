/* Log in to ChatGPT from the Motion tab with a link and a one-time code (Wan, 6 Nov 2026). The page asks for a code
   (supabase/059 semasa_chatgpt_device_start), the worker gets it from OpenAI, and this file turns the status the page reads into
   what the card shows. Pure helpers, tested in chatgptDevice.test.mjs. */

export const VERIFY_URL = "https://auth.openai.com/codex/device";
/** A code lives 15 minutes at OpenAI. */
export const LIFETIME_S = 15 * 60;
/** A request the worker has not answered after this long is "stalled": the workflow did not start (the Vault token, or Actions). */
export const STALLED_AFTER_S = 150;

/** The link is only ever OpenAI's own device page: whatever the row holds, anything else falls back to it. */
export const safeUrl = (u) => (typeof u === "string" && /^https:\/\/auth\.openai\.com\//.test(u) ? u : VERIFY_URL);

/** "14:59" for a number of seconds. */
export function clock(seconds) {
  const s = Math.max(0, Math.floor(seconds || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** What the card shows for semasa_chatgpt_device_status(). `skew` is server time minus this browser's clock (ms), measured when the
    status was fetched, so a wrong clock on the phone cannot shorten or lengthen the code's life.
    phase: idle | requested | waiting | expired | error | done. */
export function deviceView(status, now = Date.now(), skew = 0) {
  const s = status || {};
  const state = ["requested", "waiting", "done", "error", "expired"].includes(s.state) ? s.state : "idle";
  const server = now + skew;
  const ends = Date.parse(s.expires_at || "");
  const left = Number.isFinite(ends) ? Math.max(0, Math.floor((ends - server) / 1000)) : 0;
  if (state === "waiting") {
    if (left <= 0) return { phase: "expired", secondsLeft: 0, code: "", url: VERIFY_URL, error: "", stalled: false };
    return { phase: "waiting", secondsLeft: left, code: String(s.user_code || ""), url: safeUrl(s.verification_url), error: "", stalled: false };
  }
  if (state === "requested") {
    const asked = Date.parse(s.requested_at || "");
    const stalled = Number.isFinite(asked) && (server - asked) / 1000 > STALLED_AFTER_S;
    return { phase: "requested", secondsLeft: 0, code: "", url: VERIFY_URL, error: "", stalled };
  }
  return { phase: state, secondsLeft: 0, code: "", url: VERIFY_URL, error: state === "error" ? String(s.error || "").slice(0, 300) : "", stalled: false };
}

/** Whether the card should keep asking the database (every few seconds) for the status. */
export const polling = (view) => view.phase === "requested" || view.phase === "waiting";
export const POLL_MS = 3000;
