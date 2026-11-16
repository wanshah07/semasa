/* Wan's own lists for LinkedIn ideas (16 Nov 2026): websites that list what is new, LinkedIn posts he pasted, and LinkedIn
   company pages to watch. The lists live in the settings row `sources` (websites.sites, linkedin.posts, linkedin.pages),
   beside the Threads, Facebook and Instagram ones; the sweep that reads them is backend/semasa/own_links.py, whose rules
   for an address these mirror (web_url, linkedin_kind): what the page refuses here the worker would have skipped. */
export const LINK_SECTIONS = ["website", "linkedin"];
export const MAX_SITES = 12, MAX_POSTS = 30, MAX_PAGES = 12;
export const MIN_REACTIONS = 50, DAYS = 30;

/** An http(s) address with no fragment, or "" for anything else. */
export function webUrl(raw) {
  let u;
  try { u = new URL(String(raw ?? "").trim()); } catch { return ""; }
  if (!/^https?:$/.test(u.protocol) || !u.hostname.includes(".")) return "";
  u.hash = "";
  return u.toString();
}

/** ["post" | "page" | "profile" | "", the address the sweep reads]. A post or article is read as it is; a company, school or
    showcase page at its root; a person's profile cannot be read without signing in, so it is told apart to say so. */
export function linkedinKind(raw) {
  const url = webUrl(raw);
  if (!url) return ["", ""];
  const u = new URL(url);
  if (!(u.hostname === "linkedin.com" || u.hostname.endsWith(".linkedin.com"))) return ["", ""];
  if (/^\/(posts\/[^/?#]+|feed\/update\/urn:li:[a-zA-Z]+:\d+|pulse\/[^/?#]+)/i.test(u.pathname)) return ["post", "https://www.linkedin.com" + u.pathname.replace(/\/+$/, "")];
  const m = /^\/(company|school|showcase)\/([^/?#]+)/i.exec(u.pathname);
  if (m) return ["page", `https://www.linkedin.com/${m[1].toLowerCase()}/${m[2]}/`];
  if (u.pathname.startsWith("/in/")) return ["profile", url];
  return ["", ""];
}

const uniq = (list) => [...new Set(list)];
const lines = (v) => (Array.isArray(v) ? v : String(v ?? "").split(/[\s,]+/)).map((x) => String(x ?? "").trim()).filter(Boolean);
export const cleanSites = (v) => uniq(lines(v).map(webUrl).filter(Boolean)).slice(0, MAX_SITES);
export const cleanPosts = (v) => uniq(lines(v).map(linkedinKind).filter(([k]) => k === "post").map(([, u]) => u)).slice(0, MAX_POSTS);
export const cleanPages = (v) => uniq(lines(v).map(linkedinKind).filter(([k]) => k === "page").map(([, u]) => u)).slice(0, MAX_PAGES);
/** What of a pasted list cannot be used, and why: {profiles, other}. */
export function refused(v, want) {
  const kinds = lines(v).map((x) => linkedinKind(x)[0]);
  return { profiles: kinds.filter((k) => k === "profile").length, other: kinds.filter((k) => k !== want && k !== "profile").length };
}

export const sitesOf = (sources) => cleanSites(sources?.websites?.sites || []);
export function linkedinOf(sources) {
  const li = sources?.linkedin || {};
  const n = Number(li.min_reactions);
  return { posts: cleanPosts(li.posts || []), pages: cleanPages(li.pages || []),
    min_reactions: Number.isFinite(n) && n >= 0 ? Math.round(n) : MIN_REACTIONS, days: Number(li.days) > 0 ? Math.round(Number(li.days)) : DAYS };
}
/** The settings row with one list replaced: everything else in it (the other sources, the last report) stays as it was. */
export const withSites = (sources, sites) => ({ ...(sources || {}), websites: { ...(sources?.websites || {}), enabled: true, sites: cleanSites(sites) } });
export const withLinkedin = (sources, { posts, pages, min_reactions }) => ({ ...(sources || {}),
  linkedin: { ...(sources?.linkedin || {}), enabled: true, posts: cleanPosts(posts), pages: cleanPages(pages),
    min_reactions: Math.max(0, Math.round(Number(min_reactions) || 0)) } });

/** What the last sweep said about one of the two lists, in the shape WatchSegment's header reads (ownSummary's). */
export function linkSummary(section, s, t = (bm, en) => en) {
  const rep = ((s && s.report) || {})[section === "website" ? "websites" : "linkedin"] || {};
  const failing = [];
  if (rep.ok === false) failing.push({ name: section, error: rep.error });
  for (const [where, error] of Object.entries(rep.errors || {})) failing.push({ name: where.replace(/^https?:\/\/(www\.)?/, "").slice(0, 60), error });
  if (rep.profiles_skipped) failing.push({ name: "LinkedIn", error: t("{n} profil peribadi tidak boleh dibaca tanpa log masuk", "{n} personal profile(s) cannot be read without signing in", { n: rep.profiles_skipped }) });
  return { new: rep.new ?? 0, shown: rep.shown ?? 0, failing, last: rep.at || (s && s.last_run) };
}
