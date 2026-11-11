/* The post-slot check: what each channel of each post is doing, in four colours (Wan, 11 Nov 2026: "show green if passed, yellow
   queue, red fail, magenta wait for approval"). The worker half is backend/semasa/slotcheck.py (it reads Zernio back 25 minutes after
   each slot and writes sent or error onto the post); this file only READS what the posts say, so the page and the worker cannot
   disagree about a channel. Plain functions with one import, so web/slotCheck.test.mjs runs them under Node as they are. */
import { LATE_GRACE_MIN, dueMs } from "./slots.js";

export const STUCK_MIN = 20;                        // backend/semasa/slotcheck.py STUCK_AFTER: not sent this long after its slot
export const STATES = ["passed", "queued", "failed", "waiting"];
// the worst state first: a post with one failed channel reads failed however many passed
const RANK = { failed: 0, waiting: 1, queued: 2, passed: 3, off: 4 };
const DEFAULT_CHANNELS = { regulab: ["instagram", "facebook", "threads"], linkedin: ["linkedin"] };

/** The channels of a post: the ones it was queued to, plus any that already hold a record (TikTok rides with a film). */
export function channelsOf(post) {
  const base = Array.isArray(post.channels) && post.channels.length ? post.channels : DEFAULT_CHANNELS[post.stream || "regulab"] || [];
  const held = post.published && typeof post.published === "object" ? Object.keys(post.published) : [];
  return [...new Set([...base, ...held])];
}

const minutesPast = (post, now) => (now - dueMs(post.date, post.slot)) / 60000;
const errorOf = (post, ch) => {
  const e = (post.errors || {})[ch];
  return (e && (e.message || (typeof e === "string" ? e : ""))) || "";
};

/** One channel of one post: {state, label, detail, url}. `label` is [Malay, English]; `detail` is [Malay, English] too, except a
 *  platform's own words (an error it sent), which stay as it wrote them. */
export function channelState(post, ch, now = Date.now()) {
  if (post.status === "draft") {
    return { state: "waiting", label: ["Tunggu kelulusan", "Waiting for approval"], detail: "", url: "" };
  }
  const rec = (post.published || {})[ch];
  const late = post.date && post.slot ? minutesPast(post, now) : -1;
  if (rec && typeof rec === "object") {
    if (rec.status === "sent") return { state: "passed", label: ["Berjaya", "Sent"], detail: "", url: rec.url || "" };
    if (rec.status === "error") {
      return { state: "failed", label: ["Gagal", "Failed"], detail: errorOf(post, ch) || ["platform menolaknya", "the platform refused it"], url: "" };
    }
    if (late > STUCK_MIN) {
      return { state: "failed", label: ["Tersangkut", "Stuck"], detail: [`belum dihantar ${Math.floor(late)} minit selepas slotnya`, `not sent ${Math.floor(late)} minutes after its slot`], url: "" };
    }
    return { state: "queued", label: ["Dalam barisan", "Queued"], detail: "", url: "" };
  }
  const err = errorOf(post, ch);
  if (err) return { state: "failed", label: ["Gagal", "Failed"], detail: err, url: "" };
  if (post.status === "posted") return { state: "off", label: ["Tidak digunakan", "Not used"], detail: "", url: "" };
  const scan = (post.errors || {}).scan;
  if (Array.isArray(scan) && scan.length) {
    return { state: "failed", label: ["Disekat", "Blocked"], detail: String(scan[0]).slice(0, 160), url: "" };
  }
  if (late > LATE_GRACE_MIN) {
    return { state: "failed", label: ["Terlepas", "Missed"], detail: ["slotnya sudah lepas dan ia tidak pernah diserahkan", "its slot passed and it was never handed over"], url: "" };
  }
  return { state: "queued", label: ["Dalam barisan", "Queued"], detail: "", url: "" };
}

/** The colour of a whole post: its worst channel. */
export function postState(cells) {
  const live = cells.filter((c) => c.state !== "off");
  if (!live.length) return "off";
  return live.reduce((w, c) => (RANK[c.state] < RANK[w] ? c.state : w), "passed");
}

/** The rows to draw: posts from the start of today (Malaysia) to `days` ahead, oldest slot first, rejected and archived left out.
 *  `from` is a YYYY-MM-DD in Malaysia time. */
export function slotRows(posts, { from, days = 7, now = Date.now() } = {}) {
  const end = from ? Date.parse(`${from}T00:00:00+08:00`) + (days + 1) * 86400_000 : Infinity;
  const start = from ? Date.parse(`${from}T00:00:00+08:00`) : -Infinity;
  const rows = [];
  for (const p of posts) {
    if (!p.date || !p.slot || p.status === "rejected" || p.archived_at) continue;
    const due = dueMs(p.date, p.slot);
    if (due < start || due >= end) continue;
    const cells = channelsOf(p).map((ch) => ({ ch, ...channelState(p, ch, now) }));
    if (!cells.length) continue;
    rows.push({ post: p, due, cells, state: postState(cells) });
  }
  return rows.sort((a, b) => a.due - b.due || String(a.post.stream).localeCompare(String(b.post.stream)));
}

/** How many posts sit in each state, for the tiles above the list. */
export function tally(rows) {
  const out = { passed: 0, queued: 0, failed: 0, waiting: 0 };
  for (const r of rows) if (r.state in out) out[r.state]++;
  return out;
}

/** The colour of a whole row for a post in any list (Posts table and cards): a post is its worst channel, a rejected post has no
 *  colour (`off`), and a hint says why in both languages. */
export function rowState(post, now = Date.now()) {
  if (post.status === "rejected") return { state: "off", hint: ["Ditolak", "Rejected"] };
  const cells = channelsOf(post).map((ch) => ({ ch, ...channelState(post, ch, now) }));
  const state = postState(cells);
  const worst = cells.find((c) => c.state === state);
  return { state, hint: worst ? worst.label : ["Tiada saluran", "No channel"], detail: worst && worst.state === "failed" ? worst.detail : "" };
}
export const STATE_NAME = { passed: ["Berjaya", "Passed"], queued: ["Dalam barisan", "Queued"], failed: ["Gagal", "Failed"],
  waiting: ["Tunggu kelulusan", "Waiting for approval"], off: ["Tiada status", "No status"] };

/** A detail as text in the language of the page: a [Malay, English] pair is chosen from, a platform's own words are kept. */
export const detailText = (d, t) => (Array.isArray(d) ? t(d[0], d[1]) : String(d || ""));
