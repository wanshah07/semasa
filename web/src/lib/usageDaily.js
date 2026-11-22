/* AI usage as daily totals, summed by the database, not as one row per call (Wan, 22 Nov 2026: "Fix what you recommend").
   Papan's token chart re-read 2,000 semasa_api_usage rows every 5 minutes and the API page 5,000. The API pulse alone writes
   ~800 rows a day (area "pulse", 0 tokens), so those 2,000 rows went back about two days: the "14-day" chart showed two.
   supabase/091 adds semasa_api_usage_daily(p_days): one row per Malaysian day, gateway, area, model and ok, with the calls and
   the sums. 90 days of it was 545 rows (57 KB) on 22 Nov 2026, against 21,000 raw rows (5 MB).

   Days before yesterday no longer change, so after the first read only the last REFRESH_DAYS are asked for again, and those
   days are replaced; a full read again every FULL_EVERY_MS. Until 091 is run the function does not exist: `loadDaily` answers
   { missing: true } and the page reads raw rows instead (as before, through lib/appendDelta.js), so nothing breaks.
   Rows come back as { day, gateway, area, model, ok, calls, total_tokens, prompt_tokens, completion_tokens, ms }; lib/api.js
   and lib/dashboard.js read these and raw rows alike (`calls` absent = one call, `day` absent = the day of created_at).
   No React and no Supabase import: web/usageDaily.test.mjs runs this under Node. */

export const RPC = "semasa_api_usage_daily";
export const REFRESH_DAYS = 2;
export const FULL_EVERY_MS = 6 * 3600_000;

const MYT_MS = 8 * 3600_000;
export const mytDay = (t) => new Date(t + MYT_MS).toISOString().slice(0, 10);
const dayShift = (iso, d) => new Date(Date.parse(`${iso}T00:00:00Z`) + d * 86_400_000).toISOString().slice(0, 10);

/** Did the call fail because supabase/091 has not been run (the function is unknown)? */
export const isMissing = (error) => /semasa_api_usage_daily|PGRST202|42883|could not find the function/i.test(`${error?.code || ""} ${error?.message || ""}`);

export const newDailyState = () => ({ rows: [], days: 0, fullAt: 0, missing: false });

const num = (v) => Number(v) || 0;
export const normalise = (r) => ({
  day: String(r.day || "").slice(0, 10), gateway: r.gateway || "", area: r.area || "", model: r.model || "", ok: r.ok !== false,
  calls: num(r.calls), total_tokens: num(r.total_tokens), prompt_tokens: num(r.prompt_tokens),
  completion_tokens: num(r.completion_tokens), ms: num(r.ms),
});

const order = (a, b) => b.day.localeCompare(a.day) || a.gateway.localeCompare(b.gateway) || a.area.localeCompare(b.area)
  || a.model.localeCompare(b.model) || Number(a.ok) - Number(b.ok);

/** The held rows with the days from `fromDay` on replaced by `fresh` (a refresh), and nothing older than `days` back. */
export function replaceDays(held, fresh, fromDay, today, days) {
  const oldest = dayShift(today, -(days - 1));
  return [...held.filter((r) => r.day < fromDay && r.day >= oldest), ...fresh.map(normalise).filter((r) => r.day >= oldest)].sort(order);
}

/**
 * One read. `days`: how many Malaysian days back the page wants (a wider window than held means a full read).
 * Returns { rows, kind, fetched }, { missing: true } before supabase/091 is run, or { error }.
 */
export async function loadDaily({ client, state, days, now = Date.now() }) {
  const today = mytDay(now);
  const full = !state.fullAt || state.days < days || now - state.fullAt >= FULL_EVERY_MS;
  const ask = full ? days : REFRESH_DAYS;
  const { data, error } = await client.rpc(RPC, { p_days: ask });
  if (error) {
    if (isMissing(error)) { state.missing = true; return { missing: true }; }
    return { error };
  }
  state.missing = false;
  if (full) {
    state.rows = replaceDays([], data || [], "0000-00-00", today, days);
    state.days = days; state.fullAt = now;
  } else {
    state.rows = replaceDays(state.rows, data || [], dayShift(today, -(REFRESH_DAYS - 1)), today, state.days);
  }
  return { rows: state.rows, kind: full ? "full" : "refresh", fetched: data?.length ?? 0 };
}
