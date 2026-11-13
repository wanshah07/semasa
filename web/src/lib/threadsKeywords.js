/* The Threads keywords (and optional handles) the sweep searches, edited from the Threads tab (Wan, 13 Nov 2026: "add, edit,
   remove threads keywords so you can search"). They are saved in the `sources` setting at community.threads.queries and
   community.threads.accounts, which backend/semasa/intake.py merges over its defaults. Pure helpers, tested in
   threadsKeywords.test.mjs; the limits are the backend's (threads_web.MAX_QUERIES / MAX_ACCOUNTS). */

export const MAX_KEYWORDS = 8;
export const MAX_HANDLES = 10;
export const DEFAULT_KEYWORDS = ["halal kosmetik", "sunscreen", "sijil halal"];

/** A keyword list as the sweep will see it: trimmed, spaces collapsed, 2 to 60 letters, no repeats (any case), at most 8. */
export function cleanKeywords(list) {
  const seen = new Set();
  const out = [];
  for (const raw of Array.isArray(list) ? list : []) {
    const k = String(raw ?? "").replace(/\s+/g, " ").trim();
    if (k.length < 2 || k.length > 60 || seen.has(k.toLowerCase())) continue;
    seen.add(k.toLowerCase());
    out.push(k);
    if (out.length >= MAX_KEYWORDS) break;
  }
  return out;
}

/** Handles without the @, letters digits . and _ only (1 to 30), no repeats, at most 10. */
export function cleanHandles(list) {
  const seen = new Set();
  const out = [];
  for (const raw of Array.isArray(list) ? list : []) {
    const h = String(raw ?? "").trim().replace(/^@+/, "");
    if (!/^[\w.]{1,30}$/.test(h) || seen.has(h.toLowerCase())) continue;
    seen.add(h.toLowerCase());
    out.push(h);
    if (out.length >= MAX_HANDLES) break;
  }
  return out;
}

/** The keywords in force: what Wan saved, else the sweep's defaults. A saved EMPTY list is respected (a handles-only sweep). */
export function keywordsOf(sources) {
  const saved = sources?.community?.threads?.queries;
  return Array.isArray(saved) ? cleanKeywords(saved) : DEFAULT_KEYWORDS;
}

export function handlesOf(sources) {
  return cleanHandles(sources?.community?.threads?.accounts);
}

/** The whole `sources` value with the Threads lists replaced and everything else (other sources, the last report) kept. */
export function withThreads(sources, queries, accounts) {
  const s = sources || {};
  const community = s.community || {};
  return { ...s, community: { ...community, threads: { ...(community.threads || {}), queries: cleanKeywords(queries), accounts: cleanHandles(accounts) } } };
}
