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
export const BUILT_IN_INDO = RULES.indo;
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

/** Wan's own list of Indonesian words to avoid (semasa_settings.bahasa.indo, edited in Tetapan):
    [[indo, bm]], lowercase, deduped, minus the built-in list. Mirrors tabung() in compliance.py. */
export function tabung(raw) {
  const out = [];
  const seen = new Set(RULES.indo);
  for (const e of Array.isArray(raw) ? raw : []) {
    const isObj = e && typeof e === "object";
    const indo = String((isObj ? e.indo : e) ?? "").replace(/\s+/g, " ").trim().toLowerCase();
    const bm = String((isObj ? e.bm : "") ?? "").trim();
    if (indo && !seen.has(indo)) { seen.add(indo); out.push([indo, bm]); }
  }
  return out;
}

const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** Messages for every Indonesian word in `text`: the built-in list, then the tabung. */
export function indoHits(text, extra) {
  const low = String(text).toLowerCase();
  const words = low.match(/[a-z]+/g) || [];
  const msgs = RULES.indo.filter((w) => words.includes(w)).map((w) => `Bahasa Indonesia word "${w}"`);
  for (const [indo, bm] of extra) {
    const hit = /^[a-z]+$/.test(indo) ? words.includes(indo) : new RegExp(`(?<![a-z])${escRe(indo)}(?![a-z])`).test(low);
    if (hit) msgs.push(`Bahasa Indonesia word "${indo}" (tabung${bm ? `: write "${bm}")` : ")"}`);
  }
  return msgs;
}

const MAX_SLIDES = 10;
const MAX_POINTS = 5;

/** [{title, points[]}]: the one shape the writer, this page, the renderer and the scan use.
    Mirrors normalise_slides in backend/semasa/compliance.py exactly. */
export function normaliseSlides(raw) {
  const out = [];
  if (!Array.isArray(raw)) return out;
  for (let s of raw.slice(0, MAX_SLIDES)) {
    if (typeof s === "string") s = { title: s };
    if (!s || typeof s !== "object" || Array.isArray(s)) continue;
    const title = String(s.title ?? "").trim().slice(0, 240);
    let pts = s.points;
    if (typeof pts === "string") pts = pts.split("\n");
    let points = (Array.isArray(pts) ? pts : []).map((p) => String(p ?? "").trim()).filter(Boolean)
      .map((p) => p.slice(0, 400)).slice(0, MAX_POINTS);
    const body = String(s.body ?? "").trim();
    if (body && !points.length) points = [body.slice(0, 400)];
    if (title || points.length) out.push({ title, points });
  }
  return out;
}

/** Comparable form of a slide list: equal keys mean the same words. */
export const slidesKey = (raw) => JSON.stringify(normaliseSlides(raw));

/** What the scan needs of one attached media row: its alt text and, for a drawn slide set, the words
    it was drawn from (the publisher builds the same entry: backend/semasa/publisher.py scan_entry). */
export const scanMedia = (m) => (m.mode === "slides"
  ? { alt: m.meta?.alt || "", slides: m.meta?.slides || [] }
  : { alt: m.meta?.alt || "" });

/** -> [{hard, where, msg}]. Any hard flag blocks Approve and blocks the send. */
export function scan(post, brandIn = null, schedule = null, indoExtra = null) {
  const brand = { ...RULES.brand, ...(brandIn || {}) };
  const stream = post.stream || "regulab";
  const flags = [];
  const add = (hard, where, msg) => flags.push({ hard, where, msg });
  const extra = tabung(indoExtra);
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
    for (const msg of indoHits(t, extra)) add(true, where, msg);
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
    for (const msg of indoHits(t, extra)) add(false, `${tag} variant (${p})`, msg);
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

  // Slides are artwork: judged like a caption, and what is DRAWN must be what is written.
  const slides = normaliseSlides(post.slides);
  slides.forEach((sl, i) => {
    const where = `Slide ${i + 1}`;
    const t = [sl.title, ...sl.points].join("\n");
    if (SAHKAN_EMPTY.test(t)) add(true, where, "a [SAHKAN] that names nothing");
    for (const [re, label] of HARD) if (re.test(t)) add(true, where, label);
    if (SOCIAL_SRC.test(t)) add(true, where, "names a social source. A post stands on the instrument, never on where the idea was spotted.");
    for (const msg of indoHits(t, extra)) add(true, where, msg);
    if (burl.test(t)) add(true, where, "the ws.regulab website. Only the artwork footer carries it.");
    if (stream === "linkedin") {
      const hit = t.match(AGGREGATOR);
      if (hit) add(true, where, `cites "${hit[0]}", a blog or news aggregator. Cite the instrument.`);
      const mark = brandMarkRe(brand);
      if (mark && mark.test(t)) add(true, where, "a ws.regulab mark on LinkedIn");
    }
  });
  const drawn = (post.media || []).filter((m) => m && typeof m === "object" && "slides" in m).map((m) => m.slides);
  const key = slidesKey(slides);
  if (drawn.some((d) => slidesKey(d) !== key))
    add(true, "Slides", "the slide pictures carry different words from the slides written here. Draw them again (Jana slaid) so what is sent is what was checked.");
  else if (slides.length && !drawn.length) add(false, "Slides", "written but not drawn yet. Only drawn slides are sent.");

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
