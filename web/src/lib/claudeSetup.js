/* The "Claude for text, ChatGPT for pictures" card on the API tab (Wan, 24 Nov 2026: "use claude API for all functions and chatgpt auth
   CLI for image generation, ... button so we can test new api if okay or not or live, and button to fix"). Pure helpers, tested in
   claudeSetup.test.mjs. The page never holds a key: it reads the provider row, the probe's row and the two settings the backend reads
   (ai_team.prefer, ai_team.pins) and writes only those. backend/semasa/ai_providers.resolve_model is the same rule as resolveModel. */

export const CHATGPT = "chatgpt";

const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");

/** The real model id for a typed name from the gateway's list: an id in the list stays; "Claude Opus 5.5" becomes claude-opus-5-5; a family
    with no date takes its dated id (eight digits); anything else is returned as it was, never an invented id. */
export function resolveModel(name, listed) {
  const n = String(name || "").trim();
  const list = (Array.isArray(listed) ? listed : []).map(String).filter(Boolean);
  if (!n || !list.length || list.includes(n)) return n;
  const by = new Map(list.map((m) => [norm(m.replace(/^models\//, "")), m]));
  const key = norm(n.replace(/^models\//, ""));
  for (const k of [key, `claude-${key}`]) if (by.has(k)) return by.get(k);
  const dated = [...by].filter(([k]) => new RegExp(`^(claude-)?${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}-\\d{8}$`).test(k)).map(([, m]) => m).sort();
  return dated.length ? dated[dated.length - 1] : n;
}

/** The Anthropic provider Wan added: the row with id "claude" first, else any row speaking the Anthropic dialect. */
export function claudeRow(rows) {
  const list = Array.isArray(rows) ? rows : [];
  return list.find((r) => r.id === "claude") || list.find((r) => r.dialect === "anthropic") || null;
}

/** What the page knows about the Claude provider: is it there, on, does its probe answer, is its saved model one the gateway lists. */
export function claudeFacts(row, status) {
  if (!row) return { has: false, verdict: "none" };
  const listed = Array.isArray(status?.models) ? status.models : [];
  const saved = row.model || "";
  const inList = !!listed.length && listed.includes(saved);
  const fixedTo = listed.length && !inList ? resolveModel(saved, listed) : saved;
  const needsFix = !!listed.length && !inList && fixedTo !== saved && listed.includes(fixedTo);
  const noKey = !row.key_hint;
  let verdict;
  if (row.enabled === false) verdict = "off";
  else if (noKey) verdict = "nokey";
  else if (!status) verdict = "unchecked";
  else if (status.key_ok === false) verdict = "keyrefused";
  else if (status.reachable === false) verdict = "unreachable";
  else if (listed.length && !inList && !needsFix) verdict = "nomodel";          // the saved model is not in the list and nothing matches it
  else if (needsFix) verdict = "fixable";
  else verdict = status.chat_ok ? "ok" : "failing";
  return { has: true, id: row.id, saved, fixedTo, needsFix, listed, verdict, error: status?.error || "", ms: status?.chat_ms ?? null };
}

/** The best listed Claude id to suggest when the saved name matches nothing: the newest opus, else sonnet, else the first listed. */
export function suggestModel(listed) {
  const list = (Array.isArray(listed) ? listed : []).filter((m) => /claude/i.test(m));
  const pick = (re) => list.filter((m) => re.test(m)).sort().reverse()[0];
  return pick(/opus-\d+(-\d+)?$/) || pick(/sonnet-\d+(-\d+)?$/) || list[0] || "";
}

/** settings.ai_team with the whole plan applied: Claude first for every text job (prefer + the text writer pinned to its real model),
    ChatGPT's login for pictures. Everything else (other pins, defaults, efforts) is kept; `changed_at` wakes the worker (supabase/057). */
export function applyPlan(team, row, model, now = new Date()) {
  const t = team || {};
  const pins = { ...(t.pins || {}) };
  pins.reader = { gateway: row.id, model: model || row.model || "" };
  pins.image_gen = { gateway: CHATGPT, model: pins.image_gen?.gateway === CHATGPT ? pins.image_gen.model || "" : "" };
  return { ...t, prefer: row.id, pins, changed_at: now.toISOString() };
}

/** Where the plan stands now: text (Claude preferred and pinned for the text writer) and pictures (ChatGPT pinned). */
export function planState(team, row) {
  const t = team || {};
  return {
    text: !!row && t.prefer === row.id && t.pins?.reader?.gateway === row.id,
    pictures: t.pins?.image_gen?.gateway === CHATGPT,
  };
}

/** The ChatGPT picture test as the page shows it: not yet, running (asked after the last result), passed or failed (with the failing steps). */
export function pictureTest(request, result, now = Date.now()) {
  const asked = Date.parse(request?.at || "") || 0;
  const done = Date.parse(result?.at || "") || 0;
  if (asked && asked > done) return { state: now - asked > 12 * 60_000 ? "lost" : "running", at: request.at };
  if (!done) return { state: "none" };
  if (result.not_connected) return { state: "notconnected", at: result.at };
  const bad = Object.entries(result.steps || {}).filter(([, v]) => !v.ok).map(([k, v]) => ({ step: k, detail: v.detail || "" }));
  return { state: result.ok ? "ok" : "failed", at: result.at, model: result.model || "", bad };
}
