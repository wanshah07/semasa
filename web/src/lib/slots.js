/* Positions: a date AND a slot, for one stream (Studio's coverage / nextFreeSlot / claimSlot / postsOn / offRota,
   brought over 27 Sep 2026). The worker's own rule is backend/semasa/ideas.py next_free_position; this file answers
   the same questions for the page, so the Schedule view, the editor's "next free slot" and the worker agree.
   Plain functions with no imports, so web/slots.test.mjs runs them under Node as they are. */

export const LATE_GRACE_MIN = 45;                  // publisher.py: a slot more than 45 minutes gone is never sent
export const PURGE_HOURS = 72;                     // backend/semasa/archive.py REJECT_PURGE
export const ANY_DAY_DOMAINS = ["kajian_kes"];     // rules/compliance.json rota_any_day: a case study is a format
const DEFAULT_SLOTS = { regulab: ["08:00", "13:00", "21:00"], linkedin: ["06:00"] };
const MYT_MS = 8 * 3600_000;

/** Malaysia's date and clock for a moment: {date: "YYYY-MM-DD", time: "HH:MM", dow: 0..6 (0 = Sunday)}. */
export function myt(now = Date.now()) {
  const d = new Date(+now + MYT_MS);
  const iso = d.toISOString();
  return { date: iso.slice(0, 10), time: iso.slice(11, 16), dow: d.getUTCDay() };
}
export const dowOf = (iso) => new Date(`${iso}T00:00:00Z`).getUTCDay();
export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
/** The moment a position is due, in ms. */
export const dueMs = (date, slot) => Date.parse(`${date}T${slot}:00+08:00`);

export function slotsOf(brand, stream) {
  const s = (brand?.[stream] || {}).slots;
  return [...(Array.isArray(s) && s.length ? s : DEFAULT_SLOTS[stream] || DEFAULT_SLOTS.regulab)].sort();
}

/** The domains the rota gives a weekday (ws.regulab), or null when the rota says nothing about that day. */
export function domainsOn(brand, iso) {
  const allow = ((brand?.regulab || {}).schedule || {})[String(dowOf(iso))];
  if (allow == null) return null;                  // the rota says nothing: posts (ideas.py: allow is None)
  return Array.isArray(allow) ? allow : typeof allow === "string" && allow ? [allow] : [];
}

/** Does this stream post on this date at all? ws.regulab: an empty rota day is a no-posting day. LinkedIn: its
    weekday list, where an empty or missing list means every day (never a stream that has silently stopped). */
export function postsOn(brand, stream, iso) {
  if (stream === "regulab") {
    const allow = domainsOn(brand, iso);
    return allow === null || allow.length > 0;
  }
  const days = (brand?.[stream] || {}).days;
  return !Array.isArray(days) || !days.length || days.includes(dowOf(iso));
}

/** May a ws.regulab post of this domain sit on this date by the rota? (A note, never a block.) */
export function onRota(brand, iso, domain) {
  if (!domain) return true;
  const allow = domainsOn(brand, iso);
  return !allow || !allow.length || allow.includes(domain) || ANY_DAY_DOMAINS.includes(domain);
}

const holds = (p) => p && p.status !== "rejected" && p.date && p.slot;
const keyOf = (date, slot) => `${date} ${slot}`;

/** Every position this stream's posts hold, except `skipId` (the post being moved). */
export function takenSet(posts, stream, skipId = null) {
  return new Set(posts.filter((p) => holds(p) && (p.stream || "regulab") === stream && p.id !== skipId)
    .map((p) => keyOf(p.date, p.slot)));
}

/** The first free position for this stream from `fromDate` (default today), never one due within `leadMin` minutes,
    on a day the stream posts and, for ws.regulab with a domain, a day the rota gives that domain. */
export function nextFreeSlot({ posts, brand, stream, domain = null, skipId = null, fromDate = null, now = Date.now(),
  leadMin = 30, horizon = 60, taken = null }) {
  const t = taken || takenSet(posts, stream, skipId);
  const slots = slotsOf(brand, stream);
  const start = fromDate && fromDate > myt(now).date ? fromDate : myt(now).date;
  for (let i = 0; i < horizon; i++) {
    const date = addDays(start, i);
    if (!postsOn(brand, stream, date)) continue;
    if (stream === "regulab" && !onRota(brand, date, domain)) continue;
    for (const slot of slots) {
      if (dueMs(date, slot) <= +now + leadMin * 60_000) continue;
      if (!t.has(keyOf(date, slot))) return { date, slot };
    }
  }
  return null;
}

/** The calendar: `days` dates from today, each with its slots, who holds them, and what is wrong. */
export function coverage({ posts, brand, stream, days = 21, now = Date.now() }) {
  const mine = posts.filter((p) => holds(p) && (p.stream || "regulab") === stream);
  const slots = slotsOf(brand, stream);
  const today = myt(now).date;
  const out = [];
  for (let i = 0; i < days; i++) {
    const date = addDays(today, i);
    const posting = postsOn(brand, stream, date);
    const at = mine.filter((p) => p.date === date);
    const cells = slots.map((slot) => {
      const here = at.filter((p) => p.slot === slot);
      const past = dueMs(date, slot) < +now;
      return { slot, posts: here, past, gap: posting && !past && !here.length, clash: here.length > 1 };
    });
    const extra = at.filter((p) => !slots.includes(p.slot));     // "another time"
    out.push({ date, dow: dowOf(date), posting, domains: stream === "regulab" ? domainsOn(brand, date) : null, cells, extra });
  }
  return out;
}

/** Positions held by more than one post: [{date, slot, stream, posts}]. */
export function clashes(posts) {
  const by = new Map();
  for (const p of posts) {
    if (!holds(p)) continue;
    const k = `${p.stream || "regulab"} ${keyOf(p.date, p.slot)}`;
    by.set(k, [...(by.get(k) || []), p]);
  }
  return [...by.values()].filter((v) => v.length > 1)
    .map((v) => ({ date: v[0].date, slot: v[0].slot, stream: v[0].stream || "regulab", posts: v }));
}

/* ---- Blockers: one post to a slot, and the same words never twice (Wan, 3 Oct 2026: "blocker to avoid duplicate post
   to be posted, and more than 1 post in 1 slot"). Three layers say the same thing: this file (what the page offers and
   refuses), supabase/026_slot_and_duplicate_guard.sql (what the database accepts from a browser) and
   backend/semasa/guard.py (what the publisher sends). The caption key is the same in all three. */

export const DUP_KEY_LEN = 120;                    // letters of a caption that must match
export const DUP_MIN_LEN = 20;                     // a caption shorter than this carries too little to call a copy
export const DUP_WINDOW_DAYS = 90;                 // a repost of the same words months later is not what this stops

/** A caption's fingerprint: its first 120 letters and digits, lower-cased, everything else squeezed out. */
export function captionKey(text) {
  const k = String(text || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "").slice(0, DUP_KEY_LEN);
  return k.length >= DUP_MIN_LEN ? k : "";
}
/** The keys of every caption a post would send (its sent language, each platform), without empties. */
export function captionKeys(post) {
  const lang = post?.lang || (post?.stream === "linkedin" ? "en" : "bm");      // rules/compliance.json default_lang
  const byPlat = ((post?.text || {})[lang]) || {};
  return [...new Set(Object.values(byPlat).map(captionKey).filter(Boolean))];
}
const LIVE = ["approved", "scheduled", "posted"];
const dayGap = (a, b) => Math.abs(Date.parse(`${a}T00:00:00Z`) - Date.parse(`${b}T00:00:00Z`)) / 86_400_000;

/** Other posts of the same stream that already carry the same words: approved, scheduled or posted, within 90 days. */
export function duplicatesOf(post, posts) {
  const mine = captionKeys(post);
  if (!mine.length) return [];
  return posts.filter((p) => p.id !== post.id && LIVE.includes(p.status) && (p.stream || "regulab") === (post.stream || "regulab")
    && (!p.date || !post.date || dayGap(p.date, post.date) <= DUP_WINDOW_DAYS)
    && captionKeys(p).some((k) => mine.includes(k)));
}

/** Who already holds a position (same stream, date and slot, any post that is not rejected), except `skipId`. */
export function holdersOf(posts, stream, date, slot, skipId = null) {
  return posts.filter((p) => holds(p) && p.id !== skipId && (p.stream || "regulab") === stream && p.date === date && p.slot === slot);
}

/** May `post` be moved to date+slot? {ok, why?, note?}. `why` is a refusal; `note` is a warning that does not block
    (the rota is a plan, never a block). The database refuses the same moves, so this is the polite version. */
export function moveCheck({ post, date, slot, posts, brand, now = Date.now(), leadMin = 30 }) {
  const stream = post.stream || "regulab";
  if (!["draft", "approved"].includes(post.status)) return { ok: false, why: "status" };
  if (post.date === date && post.slot === slot) return { ok: false, why: "same" };
  if (!slotsOf(brand, stream).includes(slot)) return { ok: false, why: "slot" };
  if (!postsOn(brand, stream, date)) return { ok: false, why: "day" };
  if (dueMs(date, slot) <= +now + leadMin * 60_000) return { ok: false, why: "past" };
  const held = holdersOf(posts, stream, date, slot, post.id);
  if (held.length) return { ok: false, why: "taken", by: held };
  const note = stream === "regulab" && post.domain && !onRota(brand, date, post.domain) ? "rota" : undefined;
  return { ok: true, ...(note ? { note } : {}) };
}

/** Every waiting ws.regulab post from today on whose domain the rota does not give that day (Studio's offRota). */
export function offRota(posts, brand, now = Date.now()) {
  const today = myt(now).date;
  return posts.filter((p) => (p.stream || "regulab") === "regulab" && ["draft", "approved", "scheduled"].includes(p.status)
    && p.date && p.date >= today && p.domain && !onRota(brand, p.date, p.domain));
}

/** A draft or approved post whose slot went by more than 45 minutes ago: the publisher will never send it. */
export const isPastDue = (p, now = Date.now()) => ["draft", "approved"].includes(p.status) && !!(p.date && p.slot)
  && dueMs(p.date, p.slot) < +now - LATE_GRACE_MIN * 60_000;

/** Milliseconds until a rejected post is deleted, or null when it never will be by the clock (no stamp: never purged,
    or a delivery record kept as evidence). May be negative: due at the next publisher run. */
export function purgeLeftMs(p, now = Date.now()) {
  if (p.status !== "rejected" || !p.rejected_at) return null;
  if (p.published && Object.keys(p.published).length) return null;
  const at = Date.parse(p.rejected_at);
  return Number.isNaN(at) ? null : at + PURGE_HOURS * 3600_000 - now;
}

/** "2d 5h", "5h 59m", "12m": whole minutes first, so 5h59m45s never prints "5h 60m" (Studio's bug). */
export function fmtLeft(ms) {
  const m = Math.max(0, Math.floor(ms / 60_000));
  const d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60), mm = m % 60;
  return d ? `${d}d ${h}h` : h ? `${h}h ${mm}m` : `${mm}m`;
}

/** Studio's short reference: R0909c = ws.regulab, 9 Sep, third slot; L0925a = LinkedIn. Another time → R0909-1430. */
export function refOf(p, brand) {
  if (!p?.date) return "";
  const mmdd = p.date.slice(5, 7) + p.date.slice(8, 10);
  const s = (p.stream || "regulab") === "linkedin" ? "L" : "R";
  const i = p.slot ? slotsOf(brand, p.stream || "regulab").indexOf(p.slot) : -1;
  return `${s}${mmdd}${i >= 0 && i < 26 ? String.fromCharCode(97 + i) : p.slot ? `-${p.slot.replace(":", "")}` : ""}`;
}
