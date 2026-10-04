/* Pre-publish checks, ported from ws.regulab Studio's scanInner. The patterns are in
   rules/compliance.json, shared with backend/semasa/compliance.py, so the badge shown here
   before Approve and the check the publisher runs before it sends are the same rules.
   rules/cases.json is run by both test suites (npm test / pytest). */
import RULES from "../../../rules/compliance.json";

const rx = (r) => new RegExp(r.re, (r.flags || "").includes("i") ? "i" : "");
const HARD = [...RULES.hard, ...RULES.cta].map((r) => [rx(r), r.label]);
const CTA = RULES.cta.map((r) => [rx(r), r.label]);
const SOFT = RULES.soft.map((r) => [rx(r), r.label]);
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
/** Length and cut in characters as Python counts them (code points): an emoji is one, never two. */
export const charLen = (t) => [...String(t ?? "")].length;
const cut = (t, n) => { const a = [...t]; return a.length > n ? a.slice(0, n).join("") : t; };

export function normaliseSlides(raw) {
  const out = [];
  if (!Array.isArray(raw)) return out;
  for (let s of raw.slice(0, MAX_SLIDES)) {
    if (typeof s === "string") s = { title: s };
    if (!s || typeof s !== "object" || Array.isArray(s)) continue;
    const title = cut(String(s.title ?? "").trim(), 240);
    let pts = s.points;
    if (typeof pts === "string") pts = pts.split("\n");
    // a point is one line: the editor edits points as lines, so "a\nb" stored as one point reads as two there
    let points = (Array.isArray(pts) ? pts : []).flatMap((p) => String(p ?? "").split("\n")).map((p) => p.trim()).filter(Boolean)
      .map((p) => cut(p, 400)).slice(0, MAX_POINTS);
    const body = String(s.body ?? "").trim();
    if (body && !points.length) points = [cut(body, 400)];
    const extra = slideExtras(s);
    if (title || points.length || SLIDE_WORD_KEYS.some((k) => extra[k])) out.push({ title, points, ...extra });
  }
  return out;
}

/* A slide's own design (Studio's per-slide editor, brought over 27 Sep 2026): the words each design draws besides the
   headline and the points, and how it is drawn. Kept only when set, in this order, so a slide written before these
   existed compares equal to itself. Mirrored exactly by slide_extras in backend/semasa/compliance.py. */
export const SLIDE_WORDS = { lead: 400, eyebrow: 80, chip: 60, note: 240, footnote: 300 };
const SLIDE_WORD_KEYS = Object.keys(SLIDE_WORDS);
const SLIDE_STYLE = {
  template: /^[gep]_[a-z]{2,8}$/,
  scrim: /^(none|light|medium|heavy)$/,
  bg: /^(none|post_image|lib:g_[a-z0-9]{2,30}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/,
  mascot: /^(none|[a-z]{2,20})$/,
  // typography and the character's placement (Wan, 3 Oct 2026); 100% is the default and is never stored
  type_size: /^(60|70|80|90|110|120)$/,
  font: /^(sans|round|hand)$/,
  mascot_pos: /^(bl|bc|br)$/,
  mascot_size: /^(60|80|130|160)$/,
};
export function slideExtras(s) {
  const out = {};
  for (const [k, cap] of Object.entries(SLIDE_WORDS)) {
    const v = cut(String(s[k] ?? "").trim(), cap);
    if (v) out[k] = v;
  }
  for (const [k, rx] of Object.entries(SLIDE_STYLE)) {
    const v = String(s[k] ?? "").trim();
    if (v && rx.test(v)) out[k] = v;
  }
  return out;
}
/** Every word a slide can put on the picture, for the scan. */
export const slideText = (sl) => [sl.title || "", ...(sl.points || []), ...SLIDE_WORD_KEYS.map((k) => sl[k] || "")].join("\n");

/** Comparable form of a slide list: equal keys mean the same words. */
export const slidesKey = (raw) => JSON.stringify(normaliseSlides(raw));

/** What the scan needs of one attached media row: its alt text and, for a drawn slide set, the words
    it was drawn from (the publisher builds the same entry: backend/semasa/publisher.py scan_entry). */
export const scanMedia = (m) => (m.mode === "slides"
  ? { alt: m.meta?.alt || "", [m.meta?.design ? "artwork" : "slides"]: m.meta?.slides || [] }
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
    if (lim && charLen(t) > lim.max) add(true, where, `${charLen(t)} chars, over the ${lim.max} limit`);
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
  const artwork = (items, label) => items.forEach((sl, i) => {
    const where = `${label} ${i + 1}`;
    const t = slideText(sl);
    for (const [re, lab] of HARD) if (re.test(t)) add(true, where, lab);
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
  const slides = normaliseSlides(post.slides);
  artwork(slides, "Slide");
  // Wan's shape for a carousel (Studio, 7 Sep 2026): a cover, at least three slides carrying facts, then a closing line
  // that leaves them curious. One slide is a single card and is not a carousel.
  if (slides.length > 1) {
    const substance = (x) => !!(x.title || x.lead || x.points.length);
    const facts = slides.slice(1, -1).filter(substance).length;
    if (facts < RULES.carousel_min_facts)
      add(true, "Carousel", `${facts} slide${facts === 1 ? "" : "s"} of substance between the cover and the closing. At least ${RULES.carousel_min_facts}.`);
    const last = slides[slides.length - 1];
    if (!(last.title || last.lead)) add(true, "Carousel", "write the closing line: one statement that leaves them curious. Not a question, not an ask.");
  }
  // A poster, card or carousel from the Design tab carries its own words: the same rules, but it is not a drawing
  // of this post's slides, so it is never compared with them.
  (post.media || []).forEach((m, k) => {
    if (m && typeof m === "object" && "artwork" in m) artwork(normaliseSlides(m.artwork), `Design ${k + 1}, slide`);
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
    if (allow && allow.length && !allow.includes(post.domain) && !(RULES.rota_any_day || []).includes(post.domain))
      add(false, "Rota", `${DOW[dow]} carries ${allow.join(" and ")}, and this is ${post.domain}. A note, not a block.`);
  }
  return flags;
}

export const hardCount = (flags) => flags.filter((f) => f.hard).length;

/** A sentence that asks for something or carries the ws.regulab website: never built onto the artwork. */
export function isPromo(sentence, brand = null) {
  const t = String(sentence || "");
  return brandUrlRe(brand || RULES.brand).test(t) || CTA.some(([re]) => re.test(t));
}

/** One click for Studio's "strip the ask": every sentence that asks for something or carries the ws.regulab website
    comes out of a caption; everything else, line breaks included, stays exactly as written. A regulator's link is
    only a warning, so it stays. Returns {text, removed: [sentences]}. */
export function stripPromo(caption, brand = null) {
  const removed = [];
  const lines = String(caption || "").split("\n").map((line) => {
    if (!isPromo(line, brand)) return line;
    const kept = line.split(/(?<=[.!?])\s+/).filter((s) => {
      if (isPromo(s, brand)) { removed.push(s.trim()); return false; }
      return true;
    });
    return kept.join(" ");
  });
  const text = lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  return { text, removed };
}
