/* Prestasi (pages/PrestasiTab.jsx): the figures Threads' own analytics screen shows, computed from semasa_post_metrics rows
   (supabase/034_post_metrics.sql, written by backend/semasa/metrics.py from Buffer). Plain functions with no imports so
   web/analytics.test.mjs runs them under Node. Every clock is Malaysia's (UTC+8), never the browser's.

   Words, as the screen Wan attached uses them:
     views       what the network counts as views (Threads/Instagram `views`; Facebook has only `impressions`, used in its place)
     reach       distinct accounts (Instagram only through Buffer); the page says "views" where reach is not given
     engagement  interactions ÷ views, as a percentage (interactions = reactions + comments + shares + saves + reposts + quotes)
     replies     the network's comments
     window      a 3-hour band of the Malaysian day: 00-03, 03-06, … 21-24 (eight a day, seven days: the heatmap) */

const MYT_MS = 8 * 3600_000;
export const WINDOWS = ["00-03", "03-06", "06-09", "09-12", "12-15", "15-18", "18-21", "21-24"];
export const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
export const CHANNELS = ["threads", "instagram", "facebook"];

const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : Number(v) || 0);

/** Malaysia's day-of-week (0 = Sunday), hour and 3-hour window for a UTC stamp; null when unreadable. */
export function mytSlot(stamp) {
  const ms = Date.parse(stamp || "");
  if (!Number.isFinite(ms)) return null;
  const d = new Date(ms + MYT_MS);
  const hour = d.getUTCHours();
  return { dow: d.getUTCDay(), hour, win: Math.floor(hour / 3), date: d.toISOString().slice(0, 10) };
}

/** The view figure a row carries: views, else impressions (Facebook), else reach. */
export const viewsOf = (r) => (r.views != null ? num(r.views) : r.impressions != null ? num(r.impressions) : num(r.reach));
export const interactionsOf = (r) => num(r.reactions) + num(r.comments) + num(r.shares) + num(r.saves) + num(r.reposts) + num(r.quotes);
export const engagementOf = (rows) => {
  const v = rows.reduce((a, r) => a + viewsOf(r), 0);
  return v ? Math.round((rows.reduce((a, r) => a + interactionsOf(r), 0) / v) * 10000) / 100 : 0;
};

/** The rows inside the filter: channel ("" = all) and the last `days` Malaysian days ending `today` (ISO). Rows with no
    sent stamp are left out: a post with no time cannot sit in a window. */
export function filterRows(rows, { channel = "", days = 30, today } = {}) {
  const from = today ? addDays(today, -(days - 1)) : null;
  return (rows || []).filter((r) => {
    if (channel && r.channel !== channel) return false;
    const s = mytSlot(r.sent_at);
    if (!s) return false;
    return !from || s.date >= from;
  });
}
export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** The headline tiles: total views, average views a post, engagement %, replies, the peak post. */
export function overview(rows) {
  const posts = rows.length;
  const views = rows.reduce((a, r) => a + viewsOf(r), 0);
  const replies = rows.reduce((a, r) => a + num(r.comments), 0);
  const reach = rows.reduce((a, r) => a + num(r.reach), 0);
  const peak = rows.reduce((best, r) => (!best || viewsOf(r) > viewsOf(best) ? r : best), null);
  return { posts, views, reach, avgViews: posts ? Math.round(views / posts) : 0, engagement: engagementOf(rows), replies, peak };
}

/** The 7 × 8 heatmap: one cell per Malaysian weekday and 3-hour window, with the posts that went out in it. */
export function heatmap(rows) {
  const cells = [];
  for (let dow = 0; dow < 7; dow++) for (let win = 0; win < 8; win++) cells.push({ dow, win, posts: 0, views: 0, replies: 0, rows: [] });
  for (const r of rows) {
    const s = mytSlot(r.sent_at);
    if (!s) continue;
    const c = cells[s.dow * 8 + s.win];
    c.posts++; c.views += viewsOf(r); c.replies += num(r.comments); c.rows.push(r);
  }
  const max = Math.max(0, ...cells.map((c) => (c.posts ? c.views / c.posts : 0)));
  return cells.map((c) => ({ ...c, avgViews: c.posts ? Math.round(c.views / c.posts) : 0, engagement: engagementOf(c.rows),
    heat: max && c.posts ? Math.round(((c.views / c.posts) / max) * 100) / 100 : 0 }));
}

/** The best publishing window: the cell with the highest average views among cells carrying at least `minPosts`
    posts; null when nothing qualifies. Ties go to the window with more posts, then the earlier one. */
export function bestWindow(cells, minPosts = 1) {
  let best = null;
  for (const c of cells) {
    if (c.posts < minPosts) continue;
    if (!best || c.avgViews > best.avgViews || (c.avgViews === best.avgViews && c.posts > best.posts)) best = c;
  }
  return best;
}

/** One cell's words: "Fri 12-15 MYT". */
export const cellLabel = (c) => `${DAYS[c.dow]} ${WINDOWS[c.win]} MYT`;

/** Views a day for the last `days` Malaysian days ending `today`, for the trend chart. */
export function daily(rows, today, days = 30) {
  const out = [];
  for (let i = days - 1; i >= 0; i--) out.push({ date: addDays(today, -i), views: 0, posts: 0, replies: 0 });
  const by = Object.fromEntries(out.map((d) => [d.date, d]));
  for (const r of rows) {
    const s = mytSlot(r.sent_at);
    if (s && by[s.date]) { by[s.date].views += viewsOf(r); by[s.date].posts++; by[s.date].replies += num(r.comments); }
  }
  return out;
}

/** Per channel: posts, views, average views, engagement, replies. */
export function byChannel(rows) {
  return CHANNELS.map((ch) => ({ channel: ch, ...overview(rows.filter((r) => r.channel === ch)) }));
}

/** The posts, most viewed first, for the table. */
export const ranked = (rows) => [...rows].sort((a, b) => viewsOf(b) - viewsOf(a) || String(b.sent_at).localeCompare(String(a.sent_at)));
