/* A finished Motion film queued to the platforms Wan picks (Wan, 26 Oct 2026: "allow me to choose which platform to post, so from
   the video can directly post or queue to post to platform ... remove from motion list"). The film becomes a DRAFT post in the
   Posts queue through semasa_queue_motion (supabase/051): the single gate stays Wan's Approve click there, and the publisher scans
   the post again before it sends. No imports beyond the two scanners, so web/motionQueue.test.mjs runs this under Node as it is. */
import { hardCount, platformsFor, scan } from "./compliance.js";
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

/** The caption each platform starts from: the words of the idea's own draft for that platform when there is one, else that
    draft's words for any platform, else the film's title. Wan edits them before queueing. */
export function startingCaptions({ film, post, channels }) {
  const lang = postLang(film);
  const text = (post && post.text) || {};
  const first = (o) => Object.values(o || {}).find((v) => typeof v === "string" && v.trim()) || "";
  const fallback = first(text[lang]) || first(text.bm) || first(text.en) || String(film?.title || film?.brief || "").trim();
  return Object.fromEntries(channels.map((c) => [c, ((text[lang] || {})[c] || "").trim() || fallback]));
}

/** The next free position for the film's stream (a date and a slot), or null when none is free in 60 days. */
export function pickPosition({ film, posts, brand, post, now = Date.now() }) {
  return nextFreeSlot({ posts, brand, stream: film?.stream || "regulab", domain: post?.domain || null, now });
}

/** The arguments of semasa_queue_motion, with the page's own scan of the caption each platform will carry. */
export function queueArgs({ film, channels, captions, date, slot, brand, post, indo, approve = false }) {
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
  };
}
