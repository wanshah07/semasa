/* API gateway arithmetic (Wan, 9 Oct 2026: "track status of token from mireld and afiq API including their models").
   Status rows are semasa_api_status (one a gateway, written by the probe); usage rows are semasa_api_usage (one an AI
   call, written by every worker run). Pure functions, tested in api.test.mjs. */

const MYT_MS = 8 * 3600_000;
export const mytDay = (iso) => new Date(new Date(iso).getTime() + MYT_MS).toISOString().slice(0, 10);

/** A gateway's one-word verdict: up (chat answered), key (key refused), down (unreachable), nokey, stale (not checked in 13 h). */
export function verdictOf(row, now = Date.now()) {
  if (!row) return "none";
  if (!row.key_set) return "nokey";
  if (row.checked_at && now - new Date(row.checked_at).getTime() > 13 * 3600_000) return "stale";
  if (!row.reachable) return "down";
  if (row.key_ok === false) return "key";
  if (row.chat_ok) return "up";
  return "models";                                   // listed its models but the configured model did not answer
}

/** Usage summed by gateway for a window: {gateway: {calls, failed, tokens, prompt, completion, ms}}. */
export function usageByGateway(rows, days = 30, today = mytDay(new Date().toISOString())) {
  const from = dayShift(today, -(days - 1));
  const out = {};
  for (const r of rows || []) {
    const d = mytDay(r.created_at);
    if (d < from || d > today) continue;
    const g = out[r.gateway] || (out[r.gateway] = { calls: 0, failed: 0, tokens: 0, prompt: 0, completion: 0, ms: 0, models: {} });
    g.calls += 1;
    if (!r.ok) g.failed += 1;
    g.tokens += r.total_tokens || 0; g.prompt += r.prompt_tokens || 0; g.completion += r.completion_tokens || 0; g.ms += r.ms || 0;
    if (r.model) g.models[r.model] = (g.models[r.model] || 0) + (r.total_tokens || 0);
  }
  return out;
}

/** Tokens a day, one row a day for the window, every gateway as a column: [{date, rootsys: n, mireld: n, ...}]. */
export function usageByDay(rows, days = 30, today = mytDay(new Date().toISOString())) {
  const from = dayShift(today, -(days - 1));
  const gateways = [...new Set((rows || []).map((r) => r.gateway))].sort();
  const byDay = {};
  for (let i = 0; i < days; i++) {
    const d = dayShift(from, i);
    byDay[d] = { date: d, calls: 0, ...Object.fromEntries(gateways.map((g) => [g, 0])) };
  }
  for (const r of rows || []) {
    const d = mytDay(r.created_at);
    if (!byDay[d]) continue;
    byDay[d][r.gateway] += r.total_tokens || 0;
    byDay[d].calls += 1;
  }
  return { gateways, series: Object.values(byDay) };
}

/** Usage summed by area (scrape, media, idea, receipt, probe) for the window. */
export function usageByArea(rows, days = 30, today = mytDay(new Date().toISOString())) {
  const from = dayShift(today, -(days - 1));
  const out = {};
  for (const r of rows || []) {
    const d = mytDay(r.created_at);
    if (d < from || d > today) continue;
    const a = r.area || "?";
    out[a] = (out[a] || 0) + (r.total_tokens || 0);
  }
  return Object.entries(out).sort((a, b) => b[1] - a[1]).map(([area, tokens]) => ({ area, tokens }));
}

/** Models a gateway lists, the configured one first, then those that look like chat models, then the rest. */
export function orderedModels(row) {
  const list = [...(row?.models || [])];
  const cfg = row?.model || "";
  const score = (m) => (m === cfg ? 0 : /claude|gpt|gemini|llama|qwen|deepseek|mistral|sonnet|opus|haiku/i.test(m) ? 1 : 2);
  return list.sort((a, b) => score(a) - score(b) || a.localeCompare(b));
}

export function fmtTokens(n) {
  n = n || 0;
  return n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 10_000 ? `${(n / 1000).toFixed(1)}k` : String(Math.round(n));
}

function dayShift(iso, days) {
  return new Date(Date.parse(`${iso}T00:00:00Z`) + days * 86_400_000).toISOString().slice(0, 10);
}
