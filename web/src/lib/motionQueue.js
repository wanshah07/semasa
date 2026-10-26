/* A finished Motion film queued to the platforms Wan picks (Wan, 26 Oct 2026: "allow me to choose which platform to post, so from
   the video can directly post or queue to post to platform ... remove from motion list"). The film becomes a DRAFT post in the
   Posts queue through semasa_queue_motion (supabase/051): the single gate stays Wan's Approve click there, and the publisher scans
   the post again before it sends. No imports beyond the scanners, the slots and platformFormat.js, so web/motionQueue.test.mjs runs this under Node as it is. */
import { LIMITS, hardCount, platformsFor, scan } from "./compliance.js";
import { sizeFor } from "./platformFormat.js";
import { nextFreeSlot } from "./slots.js";

export const CHANNEL_LABEL = { facebook: "Facebook", instagram: "Instagram", threads: "Threads", linkedin: "LinkedIn" };

/** The platforms a film can go to: its stream's own (ws.regulab speaks BM to SMEs on Facebook, Instagram and Threads; the LinkedIn
    stream is Wan's own English byline). Two voices are never mixed, so a film is never offered to the other stream's platforms. */
export const channelsFor = (film) => platformsFor(film?.stream || "regulab");

/** The language of the post a film becomes: what the film says, and for a bilingual film the stream's own. */
export const postLang = (film) => (film?.language === "en" ? "en" : film?.language === "bm" ? "bm" : film?.stream === "linkedin" ? "en" : "bm");

/** A film that is done, has its file and has not been queued yet: the only kind that can be queued. */
export const canQueue = (film) => !!film && film.status === "done" && !!film.video_url && !film.queued_post_id;

/** The Motion list shows what is still to be made or used: a film that went to the post queue leaves it. */
export const inMotionList = (film) => !film.queued_post_id;

/** How long each platform's caption is asked to be when it has to be cut down; the rule's own maximum is the hard stop. */
export const SOFT = { instagram: 900, facebook: 1100, threads: 420, linkedin: 1400 };

/** `body` cut to `budget` characters at the last paragraph end, else sentence end, else word end that fits (backend/semasa/motion_captions.py). */
function cut(body, budget) {
  if (body.length <= budget) return body;
  const head = body.slice(0, budget);
  const para = head.lastIndexOf("\n\n");
  if (para >= budget * 0.4) return head.slice(0, para).trimEnd();
  let end = -1;
  for (const m of head.matchAll(/[.!?](?=\s|$)/g)) end = m.index + 1;
  if (end >= budget * 0.4) return head.slice(0, end).trimEnd();
  const room = body.slice(0, Math.max(budget - 1, 1));
  const space = room.lastIndexOf(" ");
  return `${(space > 0 ? room.slice(0, space) : room).replace(/[ ,;:]+$/, "")}.`;
}

/** `text` shortened to what the platform takes: its character maximum and its hashtag count (rules/compliance.json). */
export function fitCaption(text, stream, platform) {
  const lim = (LIMITS[stream] || {})[platform] || {};
  const lines = String(text || "").trim().split("\n");
  let tags = [];
  while (lines.length && lines[lines.length - 1].trim() && lines[lines.length - 1].trim().split(/\s+/).every((w) => w.startsWith("#"))) {
    tags = [...lines.pop().trim().split(/\s+/), ...tags];
  }
  tags = [...new Set(tags)];
  if (lim.hashtags != null) tags = tags.slice(0, lim.hashtags);
  const tail = tags.length ? `\n\n${tags.join(" ")}` : "";
  let body = lines.join("\n").trimEnd();
  if (lim.max && body.length + tail.length > lim.max) body = cut(body, lim.max - tail.length);
  return (body + tail).trim();
}

/** The caption each platform starts from, each fitted to that platform: what the worker wrote for it with the film (in the film's
    language, from its own script), else the idea's own draft for that platform, else the draft's words for any platform, else the
    film's title. Wan edits them before queueing. */
export function startingCaptions({ film, post, channels }) {
  const lang = postLang(film);
  const stream = film?.stream || "regulab";
  const text = (post && post.text) || {};
  const first = (o) => Object.values(o || {}).find((v) => typeof v === "string" && v.trim()) || "";
  const fallback = first(text[lang]) || first(text.bm) || first(text.en) || String(film?.title || film?.brief || "").trim();
  const written = (film && film.captions) || {};
  return Object.fromEntries(channels.map((c) => {
    const own = String(written[c] || "").trim();
    if (own) return [c, fitCaption(own, stream, c)];
    const draft = ((text[lang] || {})[c] || "").trim();
    return [c, fitCaption(cut(draft || fallback, SOFT[c] || 900), stream, c)];
  }));
}

/** The format a film should be in for its platforms, and whether it is. A film made before the format followed the platform may not be. */
export const filmFormat = (film) => {
  const want = sizeFor(film?.stream);
  return { want, ok: !film?.resolution || film.resolution === want };
};

/** The next free position for the film's stream (a date and a slot), or null when none is free in 60 days. */
export function pickPosition({ film, posts, brand, post, now = Date.now() }) {
  return nextFreeSlot({ posts, brand, stream: film?.stream || "regulab", domain: post?.domain || null, now });
}

/** The arguments of semasa_queue_motion, with the page's own scan of the caption each platform will carry. */
export function queueArgs({ film, channels, captions, date, slot, brand, post, indo, approve = false, override = false }) {
  const lang = postLang(film);
  const text = { [lang]: Object.fromEntries(channels.map((c) => [c, String(captions?.[c] || "").trim()])) };
  const draft = { stream: film.stream || "regulab", lang, channels, text, date, slot, domain: post?.domain || null,
    media: [{ alt: film.title || "" }] };
  const reg = brand?.regulab || {};
  const flags = scan(draft, reg, reg.schedule, indo);
  return {
    p_motion: film.id, p_channels: channels, p_lang: lang, p_hook: String(film.title || "").trim(), p_text: text,
    p_citation: post?.citation || "", p_date: date, p_slot: slot, p_flags: flags, p_hard: hardCount(flags),
    p_approve: !!approve && hardCount(flags) === 0,        // Wan's own Approve click, taken only when nothing blocks
    p_override: !!override,                                // take the slot from the draft or approved post that holds it (supabase/054)
  };
}
