/* The Threads keywords (and optional handles) the sweep searches, edited from the Threads tab (Wan, 13 Nov 2026: "add, edit,
   remove threads keywords so you can search"). They are saved in the `sources` setting at community.threads.queries and
   community.threads.accounts, which backend/semasa/intake.py merges over its defaults. Pure helpers, tested in
   threadsKeywords.test.mjs; the limits are the backend's (threads_web.MAX_QUERIES / MAX_ACCOUNTS). */

export const MAX_KEYWORDS = 8;
export const MAX_HANDLES = 10;
export const DEFAULT_KEYWORDS = ["halal kosmetik", "sunscreen", "sijil halal"];
/* Facebook and Instagram are read by hashtag (backend/semasa/social_web.py turns each entry into #letters-and-digits). */
export const DEFAULT_TAGS = ["halalmalaysia", "sijilhalal", "kosmetikmalaysia"];
export const PLATFORMS = ["threads", "facebook", "instagram"];
export const defaultsOf = (platform) => (platform === "threads" ? DEFAULT_KEYWORDS : DEFAULT_TAGS);

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
export function keywordsOf(sources, platform = "threads") {
  const saved = sources?.community?.[platform]?.queries;
  return Array.isArray(saved) ? cleanKeywords(saved) : defaultsOf(platform);
}

export function handlesOf(sources, platform = "threads") {
  return cleanHandles(sources?.community?.[platform]?.accounts);
}

/** The whole `sources` value with one platform's lists replaced and everything else (other sources, the last report) kept. */
export function withPlatform(sources, platform, queries, accounts) {
  const s = sources || {};
  const community = s.community || {};
  const mine = { ...(community[platform] || {}), queries: cleanKeywords(queries) };
  if (platform === "threads") mine.accounts = cleanHandles(accounts);     // only Threads reads a watchlist of accounts
  return { ...s, community: { ...community, [platform]: mine } };
}

export const withThreads = (sources, queries, accounts) => withPlatform(sources, "threads", queries, accounts);
