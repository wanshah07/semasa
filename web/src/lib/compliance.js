/* Pre-publish checks, ported from ws.regulab Studio's scanInner. The patterns are in
   rules/compliance.json, shared with backend/semasa/compliance.py, so the badge shown here
   before Approve and the check the publisher runs before it sends are the same rules.
   rules/cases.json is run by both test suites (npm test / pytest). */
import RULES from "../../../rules/compliance.json";

const rx = (r) => new RegExp(r.re, (r.flags || "").includes("i") ? "i" : "");
const HARD = [...RULES.hard, ...RULES.cta].map((r) => [rx(r), r.label]);
const CTA = RULES.cta.map((r) => [rx(r), r.label]);
const SOFT = RULES.soft.map((r) => [rx(r), r.label]);
const SAHKAN_EMPTY = rx(RULES.sahkan_empty);
const SAHKAN_ANY = rx(RULES.sahkan_any);
const SOCIAL_SRC = rx(RULES.social_src);
const AGGREGATOR = rx(RULES.aggregator);
const ANY_URL = rx(RULES.any_url);
const DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export const PLATFORMS = RULES.platforms;
export const LIMITS = RULES.limits;
export const DEFAULT_BRAND = RULES.brand;

function brandUrlRe(brand) {
  const parts = [RULES.brand_url_always];
  const host = String(brand.website || "").replace(/^https?:\/\//, "").replace(/^www\./, "").replace(/\/.*$/, "").trim();
  if (host && !/kkmhalalconsultant/i.test(host)) parts.push(esc(host));
  return new RegExp("(" + parts.join("|") + ")", "i");
}

function brandMarkRe(brand) {
  const bits = ["website", "name", "handle", "tagline"].map((k) => brand[k])
    .filter((x) => typeof x === "string" && x.trim().length > 2)
    .map((x) => esc(x.trim().replace(/^www\./i, "")));
  return bits.length ? new RegExp("(?:www\\.)?(?:" + bits.join("|") + ")", "i") : null;
}

export function platformsFor(stream) { return RULES.platforms[stream] || RULES.platforms.regulab; }
export function langOf(post) { return post.lang || RULES.default_lang[post.stream || "regulab"] || "bm"; }
/** Language is the OUTER key and platform the inner one: text[lang][plat]. */
export function textOf(post, plat, lang) { return String(((post.text || {})[lang] || {})[plat] || ""); }

export function dowOf(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return null;
  return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).getUTCDay();
}

/** -> [{hard, where, msg}]. Any hard flag blocks Approve and blocks the send. */
export function scan(post, brandIn = null, schedule = null) {
  const brand = { ...RULES.brand, ...(brandIn || {}) };
  const stream = post.stream || "regulab";
  const flags = [];
  const add = (hard, where, msg) => flags.push({ hard, where, msg });
  const lang = langOf(post);
  const burl = brandUrlRe(brand);
  const limits = RULES.limits[stream] || {};

  for (const p of platformsFor(stream)) {
    const where = `Caption (${p})`;
    const t = textOf(post, p, lang);
    if (!t) { add(true, where, "empty"); continue; }
    const lim = limits[p];
    if (lim && t.length > lim.max) add(true, where, `${t.length} chars, over the ${lim.max} limit`);
    if (SAHKAN_EMPTY.test(t)) add(true, where, "a [SAHKAN] that names nothing. Name the exact missing fact, or find the source and delete the marker.");
    for (const [re, label] of HARD) if (re.test(t)) add(true, where, label);
    for (const [re, label] of SOFT) if (re.test(t)) add(false, where, label);
    if (SOCIAL_SRC.test(t)) add(true, where, "names a social source. Never say the idea came from Reddit, YouTube, a forum or a post.");
    const words = t.toLowerCase().match(/[a-z]+/g) || [];
    for (const w of RULES.indo) if (words.includes(w)) add(true, where, `Bahasa Indonesia word "${w}"`);
    for (const [w, why] of RULES.indo_soft) if (words.includes(w)) add(false, where, why);
    if (burl.test(t)) add(true, where, "the ws.regulab website. The artwork footer already carries it.");
    else if (ANY_URL.test(t)) add(false, where, "a link. Naming the instrument usually reads better than pasting a URL.");
    if (/kepada\s+bapak/i.test(t)) add(false, where, "\"kepada bapak\" reads as Bahasa Indonesia");
    const tags = (t.match(/#\w+/g) || []).length;
    if (lim && tags > lim.hashtags) add(false, where, `${tags} hashtags, over the ${lim.hashtags} limit`);
    if (p === "linkedin" && t.trim().endsWith("?")) add(false, where, "ends with a question");
    if (stream === "linkedin") {
      const hit = t.match(AGGREGATOR);
      if (hit) add(true, where, `cites "${hit[0]}", a blog or news aggregator. On LinkedIn cite the instrument, not where you read it.`);
      const mark = brandMarkRe(brand);
      if (mark && mark.test(t)) add(true, where, "a ws.regulab mark on LinkedIn. That stream is Wan's own byline.");
    }
  }

  const other = lang === "bm" ? "en" : "bm";
  for (const p of platformsFor(stream)) {
    const t = textOf(post, p, other);
    if (!t) continue;
    const tag = other === "bm" ? "BM" : "EN";
    for (const [re, label] of HARD) if (re.test(t)) add(false, `${tag} variant (${p})`, label);
    const words = t.toLowerCase().match(/[a-z]+/g) || [];
    for (const w of RULES.indo) if (words.includes(w)) add(false, `${tag} variant (${p})`, `Bahasa Indonesia word "${w}"`);
  }

  const cit = String(post.citation || "");
  const alts = (post.media || []).filter((m) => m && typeof m === "object").map((m) => String(m.alt || ""));
  for (const [where, t] of [["Source", cit], ...alts.map((a, i) => [`Picture ${i + 1} alt text`, a])]) {
    if (!t) continue;
    if (SAHKAN_EMPTY.test(t)) add(true, where, "a [SAHKAN] that names nothing");
    else if (SAHKAN_ANY.test(t)) add(true, where, "an unresolved [SAHKAN]");
    for (const [re, label] of CTA) if (re.test(t)) add(true, where, label);
    if (burl.test(t)) add(true, where, "the ws.regulab website");
    if (SOCIAL_SRC.test(t)) add(true, where, "names a social source. A post stands on the instrument, never on where the idea was spotted.");
    if (stream === "linkedin") {
      const hit = t.match(AGGREGATOR);
      if (hit) add(true, where, `cites "${hit[0]}", a blog or news aggregator. Cite the instrument.`);
      const mark = brandMarkRe(brand);
      if (mark && mark.test(t)) add(true, where, "a ws.regulab mark on LinkedIn");
    }
  }

  if (stream === "regulab" && post.domain === "fatwa") {
    const body = textOf(post, "facebook", lang) + textOf(post, "instagram", lang);
    if (!/diwartakan/i.test(body)) add(true, "Post", "fatwa: gazette warning missing (diwartakan)");
  }
  if (stream === "regulab" && platformsFor(stream).includes("instagram") && !(post.media || []).length)
    add(true, "Post", "instagram needs an image");
  if (stream === "regulab" && schedule && post.date && post.domain) {
    const dow = dowOf(post.date);
    const allow = dow === null ? null : schedule[String(dow)];
    if (allow && allow.length && !allow.includes(post.domain))
      add(false, "Rota", `${DOW[dow]} carries ${allow.join(" and ")}, and this is ${post.domain}. A note, not a block.`);
  }
  return flags;
}

export const hardCount = (flags) => flags.filter((f) => f.hard).length;
