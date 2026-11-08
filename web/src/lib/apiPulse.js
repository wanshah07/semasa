/* The API pulse as the page sees it (components/ApiPulse.jsx): settings.api_pulse written by the Edge Function semasa-pulse every
   5 minutes (supabase/075_api_pulse.sql) and by "Semak sekarang". Pure helpers, tested in apiPulse.test.mjs; `runPulse` is the one
   network call and sends only the user's own login, never a key (no Supabase import here, so node can test the rest). */
export const PULSE_KEY = "api_pulse";
export const FUNCTION = "semasa-pulse";
export const EVERY_MIN = 5;
/** Past this the clock has missed at least two ticks: 075 is not applied, the Vault secret is missing, or the function is down. */
export const LATE_MS = 12 * 60_000;

/** settings.api_pulse read defensively: { at, tookMs, everyMin, results: [{slug, ok, ms, error, skipped}], unreachable: [slug] }. */
export function pulseOf(settings) {
  const v = settings && typeof settings === "object" ? settings[PULSE_KEY] : null;
  if (!v || typeof v !== "object") return { at: "", tookMs: 0, everyMin: EVERY_MIN, results: [], unreachable: [] };
  const results = Object.entries(v.results && typeof v.results === "object" ? v.results : {})
    .map(([slug, r]) => ({ slug, ok: r?.ok === true, ms: Number.isFinite(r?.ms) ? r.ms : null, error: String(r?.error || ""), skipped: String(r?.skipped || "") }))
    .sort((a, b) => a.slug.localeCompare(b.slug));
  return { at: typeof v.at === "string" ? v.at : "", tookMs: Number(v.took_ms) || 0, everyMin: Number(v.every_min) || EVERY_MIN, results,
    unreachable: Array.isArray(v.unreachable_from_edge) ? v.unreachable_from_edge.map(String) : [] };
}

/** "none" (never pulsed), "live" (within the cadence plus a little slack), "late" (one or two ticks missed), "stopped" (past LATE_MS). */
export function freshness(at, now = Date.now()) {
  const t = Date.parse(at || "");
  if (!Number.isFinite(t)) return "none";
  const age = now - t;
  if (age <= (EVERY_MIN + 2) * 60_000) return "live";
  return age <= LATE_MS ? "late" : "stopped";
}

/** How many robots answered of those probed, leaving out a robot whose check was skipped by design. */
export function tally(results) {
  const asked = (results || []).filter((r) => !r.skipped);
  return { ok: asked.filter((r) => r.ok).length, asked: asked.length, skipped: (results || []).length - asked.length };
}

/** The function's address from the project URL. */
export const pulseUrl = (base) => `${String(base || "").replace(/\/+$/, "")}/functions/v1/${FUNCTION}`;

/** What a function answer means for the page: { ok, error, missing } (missing = not deployed yet, a plain 404). */
export function readAnswer(status, body) {
  if (status === 404 && !(body && typeof body === "object" && body.error)) return { ok: false, missing: true, error: "" };
  if (status >= 200 && status < 300 && body?.ok) return { ok: true, missing: false, error: "" };
  return { ok: false, missing: false, error: String(body?.error || `HTTP ${status}`) };
}

/** The request the page sends: the user's own token and the anon key as headers, an empty body. Nothing else travels. */
export function pulseRequest({ url, anon, token }) {
  if (!url || !anon || !token) return null;
  return { url: pulseUrl(url), init: { method: "POST", headers: { apikey: anon, authorization: `Bearer ${token}`, "content-type": "application/json" }, body: "{}" } };
}

/** POST to semasa-pulse. `session` = { url, anon, token } (the component reads them); resolves to readAnswer's shape plus the body. */
export async function runPulse(session, fetchFn = fetch) {
  const req = pulseRequest(session || {});
  if (!req) return { ok: false, missing: false, error: "sign in first" };
  let res;
  try { res = await fetchFn(req.url, req.init); } catch (e) { return { ok: false, missing: false, error: String(e?.message || e) }; }
  let body = null; try { body = await res.json(); } catch { /* not JSON */ }
  return { ...readAnswer(res.status, body), body };
}
