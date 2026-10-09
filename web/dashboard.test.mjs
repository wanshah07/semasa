/* Papan: the home dashboard's numbers (lib/dashboard.js). `npm test`. */
import assert from "node:assert/strict";
import { mondayOf, mytDate, nextInQueue, recentActivity, systemStats, weeklyPosts } from "./src/lib/dashboard.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

t("Malaysia's date and the Monday of a week", () => {
  assert.equal(mytDate(Date.parse("2026-10-08T17:30:00Z")), "2026-10-09");   // 01:30 MYT the next day
  assert.equal(mondayOf("2026-10-09"), "2026-10-05");                        // Friday
  assert.equal(mondayOf("2026-10-05"), "2026-10-05");                        // Monday
  assert.equal(mondayOf("2026-10-11"), "2026-10-05");                        // Sunday belongs to the week before
});

const TODAY = "2026-10-09";
const IDEAS = [{ status: "new" }, { status: "new" }, { status: "working" }, { status: "drafted" }, { status: "error" }, { status: "rejected" }];
const POSTS = [
  { id: "a", status: "draft", date: "2026-10-09", slot: "21:00", created_at: "2026-10-08T12:00:00Z", stream: "regulab" },
  { id: "b", status: "approved", date: "2026-10-09", slot: "13:00", created_at: "2026-10-07T12:00:00Z", stream: "regulab" },
  { id: "c", status: "scheduled", date: "2026-10-10", slot: "08:00", created_at: "2026-09-28T12:00:00Z", stream: "regulab" },
  { id: "d", status: "posted", date: "2026-10-08", slot: "08:00", created_at: "2026-09-21T12:00:00Z", stream: "regulab" },
  { id: "e", status: "approved", date: "2026-10-01", slot: "08:00", created_at: "2026-09-21T12:00:00Z", stream: "regulab" },   // past: not queued
  { id: "f", status: "rejected", date: "2026-10-12", slot: "08:00", created_at: "2026-10-08T12:00:00Z", stream: "regulab" },
  { id: "g", status: "draft", date: null, slot: null, created_at: "2026-10-09T01:00:00Z", stream: "linkedin" },
];
const LOG = [
  { post_id: "d", channel: "facebook", action: "sent", at: "2026-10-08T00:05:00Z" },
  { post_id: "d", channel: "instagram", action: "sent", at: "2026-10-08T00:05:30Z" },     // same post, same week: counted once
  { post_id: "d", channel: "threads", action: "error", at: "2026-10-08T00:06:00Z" },
  { post_id: "e", channel: "facebook", action: "sent", at: "2026-10-01T00:05:00Z" },      // last week
  { post_id: "x", channel: "facebook", action: "dry_run", at: "2026-10-09T00:05:00Z" },
];

t("stats", () => {
  const s = systemStats({ ideas: IDEAS, posts: POSTS, log: LOG, today: TODAY });
  assert.deepEqual(s, { ideasNew: 2, ideasWorking: 2, ideasError: 1, drafts: 2, queued: 2, queuedToday: 1, sentThisWeek: 1, errorsThisWeek: 1 });
});

t("weekly: drafted by creation week, published by distinct post per week, eight weeks ending today's", () => {
  const w = weeklyPosts(POSTS, LOG, TODAY, 8);
  assert.equal(w.length, 8);
  assert.deepEqual(w.map((x) => x.week), ["17/08", "24/08", "31/08", "07/09", "14/09", "21/09", "28/09", "05/10"]);
  assert.deepEqual(w[7], { week: "05/10", drafted: 4, published: 1 });     // a, b, f, g drafted this week; d published once
  assert.deepEqual(w[6], { week: "28/09", drafted: 1, published: 1 });     // c drafted; e published
  assert.deepEqual(w[5], { week: "21/09", drafted: 2, published: 0 });
});

t("next in queue: from today, soonest first, scheduled before approved before draft on one position", () => {
  const q = nextInQueue(POSTS, TODAY, 6);
  assert.deepEqual(q.map((p) => p.id), ["b", "a", "c"]);
  assert.deepEqual(nextInQueue(POSTS, TODAY, 1).map((p) => p.id), ["b"]);
  const tie = [{ id: "p", status: "draft", date: "2026-10-09", slot: "08:00" }, { id: "q", status: "scheduled", date: "2026-10-09", slot: "08:00" }];
  assert.deepEqual(nextInQueue(tie, TODAY).map((p) => p.id), ["q", "p"]);
});

t("recent activity: newest first, trimmed", () => {
  const rows = [{ id: 1, at: "2026-10-09T01:00:00Z" }, { id: 2, at: "2026-10-09T03:00:00Z" }, { id: 3, at: "2026-10-08T03:00:00Z" }];
  assert.deepEqual(recentActivity(rows, 2).map((r) => r.id), [2, 1]);
});

console.log(`dashboard: ${n} checks passed`);
