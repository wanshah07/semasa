// node usageDaily.test.mjs: AI usage as daily totals (supabase/091, lib/usageDaily.js), the fallback before 091 is run, and the
// charts reading totals and raw rows alike, with the API pulse left out of Papan's tokens chart.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { REFRESH_DAYS, isMissing, loadDaily, newDailyState, replaceDays } from "./src/lib/usageDaily.js";
import { usageByArea, usageByDay, usageByGateway } from "./src/lib/api.js";
import { tokensByDay } from "./src/lib/dashboard.js";

let n = 0;
const ok = (name, fn) => Promise.resolve(fn()).then(() => { n += 1; }, (e) => { console.error(`FAIL ${name}\n`, e); process.exit(1); });

const NOW = Date.parse("2026-11-22T04:00:00.000Z");   // 12:00 MYT, 22 Nov
const agg = (day, extra = {}) => ({ day, gateway: "rootsys", area: "media", model: "m", ok: true, calls: 10, total_tokens: 1000,
  prompt_tokens: 600, completion_tokens: 400, ms: 5000, ...extra });

function rpcClient(answer) {
  const c = { asked: [] };
  c.rpc = async (name, args) => { c.asked.push({ name, ...args }); return typeof answer === "function" ? answer(args) : answer; };
  return c;
}

await ok("the first read asks for the whole window, a later poll only for the last two days, replacing them", async () => {
  let data = [agg("2026-11-22"), agg("2026-11-21"), agg("2026-11-20"), agg("2026-11-09")];
  const c = rpcClient(() => ({ data, error: null }));
  const st = newDailyState();
  const a = await loadDaily({ client: c, state: st, days: 14, now: NOW });
  assert.equal(a.kind, "full");
  assert.equal(c.asked[0].p_days, 14);
  assert.equal(a.rows.length, 4);
  data = [agg("2026-11-22", { calls: 12, total_tokens: 1500 })];            // today grew; yesterday's row is gone from the answer
  const b = await loadDaily({ client: c, state: st, days: 14, now: NOW + 300_000 });
  assert.equal(b.kind, "refresh");
  assert.equal(c.asked[1].p_days, REFRESH_DAYS);
  assert.deepEqual(b.rows.map((r) => [r.day, r.calls]), [["2026-11-22", 12], ["2026-11-20", 10], ["2026-11-09", 10]]);
});

await ok("a wider window than held is a full read again", async () => {
  const c = rpcClient({ data: [agg("2026-11-22")], error: null });
  const st = newDailyState();
  await loadDaily({ client: c, state: st, days: 14, now: NOW });
  await loadDaily({ client: c, state: st, days: 90, now: NOW + 1000 });
  assert.deepEqual(c.asked.map((x) => x.p_days), [14, 90]);
});

await ok("before supabase/091 is run the function is missing: the page is told so, not shown an error", async () => {
  for (const error of [{ code: "PGRST202", message: "Could not find the function public.semasa_api_usage_daily(p_days) in the schema cache" },
    { code: "42883", message: "function public.semasa_api_usage_daily(integer) does not exist" }]) {
    assert.equal(isMissing(error), true);
    const st = newDailyState();
    assert.deepEqual(await loadDaily({ client: rpcClient({ data: null, error }), state: st, days: 14, now: NOW }), { missing: true });
    assert.equal(st.missing, true);
  }
  const other = { code: "57014", message: "canceling statement due to statement timeout" };
  assert.equal(isMissing(other), false);
  assert.ok((await loadDaily({ client: rpcClient({ data: null, error: other }), state: newDailyState(), days: 14, now: NOW })).error);
});

await ok("days older than the window are dropped, numbers come back as numbers", () => {
  const rows = replaceDays([], [agg("2026-11-22", { calls: "3", total_tokens: "40" }), agg("2026-11-01")], "0000-00-00", "2026-11-22", 14);
  assert.deepEqual(rows.map((r) => [r.day, r.calls, r.total_tokens]), [["2026-11-22", 3, 40]]);
});

await ok("Papan's tokens chart leaves the API pulse out, and reads daily totals as many calls", () => {
  const raw = [
    { created_at: "2026-11-21T02:00:00Z", area: "media", total_tokens: 100, ok: true },
    { created_at: "2026-11-21T02:05:00Z", area: "pulse", total_tokens: 0, ok: false },
    { created_at: "2026-11-21T02:10:00Z", area: "pulse", total_tokens: 0, ok: true },
  ];
  const r = tokensByDay(raw, "2026-11-22", 14).find((d) => d.date === "2026-11-21");
  assert.deepEqual(r, { date: "2026-11-21", tokens: 100, calls: 1, failed: 0 });
  const totals = [agg("2026-11-21", { calls: 5, ok: false, total_tokens: 20 }), agg("2026-11-21", { area: "pulse", calls: 800, total_tokens: 0 })];
  const t = tokensByDay(totals, "2026-11-22", 14);
  assert.equal(t.length, 14);
  assert.deepEqual(t.find((d) => d.date === "2026-11-21"), { date: "2026-11-21", tokens: 20, calls: 5, failed: 5 });
});

await ok("the API page's sums are the same from daily totals as from the raw rows they total", () => {
  const raw = [];
  for (let i = 0; i < 20; i++) raw.push({ created_at: `2026-11-2${i % 2 ? 1 : 2}T0${i % 10}:00:00Z`, gateway: i % 3 ? "rootsys" : "mireld",
    area: i < 12 ? "media" : "scrape", model: "m", ok: i !== 5, total_tokens: 100 * (i + 1), prompt_tokens: 60 * (i + 1),
    completion_tokens: 40 * (i + 1), ms: 1000 });
  const key = (r) => [r.created_at.slice(0, 10), r.gateway, r.area, r.model, r.ok].join("|");   // these hours are the same day in MYT
  const groups = {};
  for (const r of raw) {
    const g = groups[key(r)] ||= { day: r.created_at.slice(0, 10), gateway: r.gateway, area: r.area, model: r.model, ok: r.ok, calls: 0,
      total_tokens: 0, prompt_tokens: 0, completion_tokens: 0, ms: 0 };
    g.calls += 1; g.total_tokens += r.total_tokens; g.prompt_tokens += r.prompt_tokens; g.completion_tokens += r.completion_tokens; g.ms += r.ms;
  }
  const totals = Object.values(groups);
  assert.ok(totals.length < raw.length);
  assert.deepEqual(usageByGateway(totals, 7, "2026-11-22"), usageByGateway(raw, 7, "2026-11-22"));
  assert.deepEqual(usageByDay(totals, 7, "2026-11-22"), usageByDay(raw, 7, "2026-11-22"));
  assert.deepEqual(usageByArea(totals, 7, "2026-11-22"), usageByArea(raw, 7, "2026-11-22"));
});

await ok("supabase/091 is a security-invoker function only uploaders reach, numbered 091 and not shipped as applied", () => {
  const sql = readFileSync("../supabase/091_api_usage_daily.sql", "utf8");
  assert.match(sql, /create or replace function public\.semasa_api_usage_daily\(p_days integer/);
  assert.match(sql, /security invoker/);
  assert.match(sql, /revoke execute on function public\.semasa_api_usage_daily\(integer\) from public, anon/);
  assert.match(sql, /at time zone 'Asia\/Kuala_Lumpur'\)::date as day/);
  assert.doesNotMatch(sql, /security definer/);
});

console.log(`usageDaily: ${n} cases ok`);
