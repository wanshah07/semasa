/** Telling "the server blinked" from "you may not". Pure, so SupabaseClient.errText and storage.uploadReference share one answer and Node tests it.
    Wan hit a Supabase storage 520 on 4 Oct 2026: Cloudflare's whole HTML error page came back as the message, and the upload was not retried. */
export function statusOf(error) {
  const n = Number(error?.statusCode ?? error?.status ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** The upstream answered with an error page or a 5xx (500, 502-504, Cloudflare's 520-527), not with a refusal of its own. */
export function isOutage(error) {
  const text = String(error?.message || "");
  const code = statusOf(error);
  return /<!DOCTYPE|<html/i.test(text) || code >= 500 || /\b(50[0234]|52[0-7])\b.*(web server|bad gateway|unavailable|timeout)/i.test(text);
}

/** Worth trying again: an outage, or the network itself failed. */
export function transient(error) {
  return isOutage(error) || /failed to fetch|networkerror|network request failed|timed? ?out/i.test(String(error?.message || ""));
}
