/* Papan: the home dashboard's numbers (lib/dashboard.js). `npm test`. */
import assert from "node:assert/strict";
import { DASHBOARD_WIDGETS, hiddenFrom, mondayOf, mytDate, nextInQueue, recentActivity, systemStats, visibleWidgets, weeklyPosts } from "./src/lib/dashboard.js";

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

t("the dashboard layout keeps the hidden widgets, so a new widget shows by default and the tiles never go", () => {
  assert.deepEqual(visibleWidgets(undefined), DASHBOARD_WIDGETS);
  assert.deepEqual(visibleWidgets({ hidden: ["chart", "subs", "stats", "gone"] }), ["stats", "charts", "queue", "activity", "ai"], "a widget added later (charts) shows for a layout saved before it");
  assert.deepEqual(hiddenFrom(["stats", "queue"]), ["chart", "charts", "activity", "ai", "subs"]);
  assert.deepEqual(hiddenFrom([]), ["chart", "charts", "queue", "activity", "ai", "subs"], "the tiles cannot be hidden");
  assert.deepEqual(visibleWidgets({ hidden: hiddenFrom(["queue"]) }), ["stats", "queue"]);
});

console.log(`dashboard: ${n} checks passed`);

// ---- more graphs (Wan, 7 Nov 2026) ----
import { ideaStatusCounts, postsByTopic, sentByChannel, tokensByDay } from "./src/lib/dashboard.js";
{
  const assert2 = (await import("node:assert/strict")).default;
  assert2.deepEqual(ideaStatusCounts([{ status: "error" }, { status: "new" }, { status: "error" }, { status: "odd" }]), [{ status: "new", n: 1 }, { status: "error", n: 2 }]);
  const log = [
    { channel: "instagram", action: "sent", at: "2026-11-06T02:00:00Z" }, { channel: "instagram", action: "error", at: "2026-11-06T03:00:00Z" },
    { channel: "facebook", action: "sent", at: "2026-11-05T02:00:00Z" }, { channel: "facebook", action: "sent", at: "2026-09-01T02:00:00Z" },
    { channel: "threads", action: "queued", at: "2026-11-06T02:00:00Z" }, { action: "sent", at: "2026-11-06T02:00:00Z" },
  ];
  const row = (channel, sent = 0, queued = 0, error = 0) => ({ channel, sent, queued, error });
  assert2.deepEqual(sentByChannel(log, "2026-11-07", 30).map((r) => r.channel), ["facebook", "instagram", "threads", "tiktok", "linkedin"],
    "every platform is a bar, in this order, even with nothing");
  assert2.deepEqual(sentByChannel(log, "2026-11-07", 30), [row("facebook", 1), row("instagram", 1, 0, 1), row("threads"), row("tiktok"), row("linkedin")],
    "only sent, queued and error lines in the window, with a channel");
  const fixed = [
    { post_id: "p1", channel: "threads", action: "error", at: "2026-11-06T01:00:00Z" }, { post_id: "p1", channel: "threads", action: "scheduled", at: "2026-11-06T02:00:00Z" },
    { post_id: "p2", channel: "threads", action: "error", at: "2026-11-06T03:00:00Z" }, { post_id: "p2", channel: "threads", action: "scheduled", at: "2026-11-06T02:00:00Z" },
    { post_id: "p3", channel: "tiktok", action: "scheduled", at: "2026-11-06T02:00:00Z" },
    { post_id: "p4", channel: "tiktok", action: "scheduled", at: "2026-11-06T02:00:00Z" }, { post_id: "p4", channel: "tiktok", action: "sent", at: "2026-11-06T05:00:00Z" },
  ];
  assert2.deepEqual(sentByChannel(fixed, "2026-11-07", 30).filter((r) => r.channel === "threads" || r.channel === "tiktok"), [row("threads", 0, 2, 1), row("tiktok", 1, 1, 0)],
    "an error put right by a later line is not counted; a queued post stops being queued when it is sent");
  const tk = tokensByDay([{ created_at: "2026-11-06T17:30:00Z", total_tokens: 100, ok: true }, { created_at: "2026-11-07T01:00:00Z", total_tokens: 50, ok: false },
    { created_at: "2026-10-01T00:00:00Z", total_tokens: 999 }], "2026-11-07", 3);
  assert2.deepEqual(tk.map((d) => d.date), ["2026-11-05", "2026-11-06", "2026-11-07"]);
  assert2.deepEqual(tk[2], { date: "2026-11-07", tokens: 150, calls: 2, failed: 1 }, "17:30Z on the 6th is 01:30 MYT on the 7th");
  assert2.equal(tk[0].tokens, 0, "a quiet day is still drawn");
  const topics = postsByTopic([{ stream: "regulab", domain: "kosmetik", created_at: "2026-11-01T00:00:00Z" }, { stream: "linkedin", created_at: "2026-11-02T00:00:00Z" },
    { stream: "regulab", domain: "kosmetik", created_at: "2026-11-03T00:00:00Z" }, { stream: "regulab", domain: "halal_my", status: "rejected", created_at: "2026-11-03T00:00:00Z" },
    { stream: "regulab", created_at: "2026-11-04T00:00:00Z" }, { stream: "regulab", domain: "fatwa", created_at: "2026-08-01T00:00:00Z" }], "2026-11-07", 30);
  assert2.deepEqual(topics, [{ topic: "kosmetik", n: 2 }, { topic: "linkedin", n: 1 }, { topic: "other", n: 1 }]);
  console.log("dashboard graphs: 5 checks passed");
}
