/* Papan (the home dashboard, pages/HomeTab.jsx): the whole system's numbers from the rows the page already holds. Plain
   functions with no imports so web/dashboard.test.mjs runs them under Node. Every date is Malaysia's calendar day
   (the same MYT arithmetic as lib/slots.js), never the browser's. */

const MYT_MS = 8 * 3600_000;
export const mytDate = (ms) => new Date(ms + MYT_MS).toISOString().slice(0, 10);
export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}
/** The Monday of the week an ISO date falls in. */
export function mondayOf(iso) {
  const dow = new Date(`${iso}T00:00:00Z`).getUTCDay();          // 0 = Sunday
  return addDays(iso, dow === 0 ? -6 : 1 - dow);
}
const weekOf = (stamp) => (stamp ? mondayOf(mytDate(Date.parse(stamp))) : null);
const ddmm = (iso) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

/** How far a post is through the pipeline, for the progress bar: draft 25, approved 50, scheduled 75, posted 100. */
export const POST_PROGRESS = { draft: 25, approved: 50, scheduled: 75, posted: 100, rejected: 0 };

/** The stat tiles. `log` is semasa_publish_log (action sent/error/...), `docs` the Bil documents, `subs` the subscriptions. */
export function systemStats({ ideas = [], posts = [], log = [], today }) {
  const monday = mondayOf(today);
  const sentThisWeek = new Set(log.filter((r) => r.action === "sent" && r.at && mytDate(Date.parse(r.at)) >= monday).map((r) => r.post_id)).size;
  const queue = posts.filter((p) => ["approved", "scheduled"].includes(p.status) && p.date && p.date >= today);
  return {
    ideasNew: ideas.filter((i) => i.status === "new").length,
    ideasWorking: ideas.filter((i) => ["working", "drafted"].includes(i.status)).length,
    ideasError: ideas.filter((i) => i.status === "error").length,
    drafts: posts.filter((p) => p.status === "draft").length,
    queued: queue.length,
    queuedToday: queue.filter((p) => p.date === today).length,
    sentThisWeek,
    errorsThisWeek: log.filter((r) => r.action === "error" && r.at && mytDate(Date.parse(r.at)) >= monday).length,
  };
}

/** Posts drafted against posts published, by week (Monday-start), the last `weeks` weeks ending in today's week.
    Drafted counts the post's creation week; published counts distinct posts with a "sent" line that week. */
export function weeklyPosts(posts, log, today, weeks = 8) {
  const last = mondayOf(today);
  const out = [];
  for (let i = weeks - 1; i >= 0; i--) out.push({ key: addDays(last, -7 * i), drafted: 0, published: 0 });
  const by = Object.fromEntries(out.map((w) => [w.key, w]));
  for (const p of posts || []) {
    const w = weekOf(p.created_at);
    if (w && by[w]) by[w].drafted++;
  }
  const seen = new Set();
  for (const r of log || []) {
    if (r.action !== "sent") continue;
    const w = weekOf(r.at);
    const k = `${w}|${r.post_id}`;
    if (w && by[w] && !seen.has(k)) { seen.add(k); by[w].published++; }
  }
  return out.map((w) => ({ week: ddmm(w.key), drafted: w.drafted, published: w.published }));
}

/** The next posts to go out: approved or scheduled, from today, soonest first, then today's drafts still to approve. */
export function nextInQueue(posts, today, n = 6) {
  const live = (posts || []).filter((p) => p.date && p.date >= today && ["approved", "scheduled", "draft"].includes(p.status));
  const rank = { scheduled: 0, approved: 1, draft: 2 };
  return live
    .sort((a, b) => a.date.localeCompare(b.date) || String(a.slot || "").localeCompare(String(b.slot || "")) || rank[a.status] - rank[b.status])
    .slice(0, n);
}

/** The lines for the activity list: the newest log rows, trimmed. */
export function recentActivity(rows, n = 12) {
  return (rows || []).slice().sort((a, b) => String(b.at).localeCompare(String(a.at))).slice(0, n);
}

/* Which widgets the home dashboard shows (Wan, 7 Nov 2026: the dashboard configuration panel; supabase/065 settings.dashboard).
   The setting keeps the HIDDEN ones, so a widget added later shows by default instead of vanishing until it is ticked. The
   headline tiles are permanent: a dashboard with nothing on it is not a choice worth offering. */
export const DASHBOARD_WIDGETS = ["stats", "chart", "charts", "queue", "activity", "ai", "subs"];
export const PERMANENT_WIDGETS = ["stats"];
export function visibleWidgets(setting) {
  const hidden = new Set(Array.isArray(setting?.hidden) ? setting.hidden : []);
  return DASHBOARD_WIDGETS.filter((id) => PERMANENT_WIDGETS.includes(id) || !hidden.has(id));
}
export function hiddenFrom(visible) {
  const on = new Set(visible || []);
  return DASHBOARD_WIDGETS.filter((id) => !on.has(id) && !PERMANENT_WIDGETS.includes(id));
}

/* More graphs on Papan (Wan, 7 Nov 2026: "can add more graph in overview"). Each reads rows the page already holds. */

/** Ideas by status, the order a pipeline reads in; a status with no idea is left out. */
export const IDEA_STATES = ["new", "working", "drafted", "error", "rejected"];
export function ideaStatusCounts(ideas) {
  const n = {};
  for (const i of ideas || []) n[i.status] = (n[i.status] || 0) + 1;
  return IDEA_STATES.filter((k) => n[k]).map((k) => ({ status: k, n: n[k] }));
}

/** Per channel, the posts sent and the publisher errors in the last `days` days (semasa_publish_log). */
export function sentByChannel(log, today, days = 30) {
  const from = addDays(today, -(days - 1));
  const by = {};
  for (const r of log || []) {
    if (!r.at || !r.channel || !["sent", "error"].includes(r.action)) continue;
    if (mytDate(Date.parse(r.at)) < from) continue;
    const c = (by[r.channel] ||= { channel: r.channel, sent: 0, error: 0 });
    c[r.action === "sent" ? "sent" : "error"]++;
  }
  return Object.values(by).sort((a, b) => b.sent + b.error - (a.sent + a.error) || a.channel.localeCompare(b.channel));
}

/** AI tokens a day for the last `days` days (semasa_api_usage), every day present, and the calls that failed. */
export function tokensByDay(usage, today, days = 14) {
  const out = [];
  for (let i = days - 1; i >= 0; i--) out.push({ date: addDays(today, -i), tokens: 0, calls: 0, failed: 0 });
  const by = Object.fromEntries(out.map((d) => [d.date, d]));
  for (const u of usage || []) {
    if (!u.created_at) continue;
    const d = by[mytDate(Date.parse(u.created_at))];
    if (!d) continue;
    d.tokens += Number(u.total_tokens) || 0;
    d.calls++;
    if (u.ok === false) d.failed++;
  }
  return out;
}

/** Posts written in the last `days` days by what they are about: a ws.regulab post by its domain, a LinkedIn post as one. */
export function postsByTopic(posts, today, days = 30) {
  const from = addDays(today, -(days - 1));
  const n = {};
  for (const p of posts || []) {
    if (!p.created_at || p.status === "rejected" || mytDate(Date.parse(p.created_at)) < from) continue;
    const k = p.stream === "linkedin" ? "linkedin" : p.domain || "other";
    n[k] = (n[k] || 0) + 1;
  }
  return Object.entries(n).map(([topic, count]) => ({ topic, n: count })).sort((a, b) => b.n - a.n || a.topic.localeCompare(b.topic));
}
