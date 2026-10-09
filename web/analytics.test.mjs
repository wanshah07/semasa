/* Prestasi: the post analytics arithmetic (lib/analytics.js). `npm test`. */
import assert from "node:assert/strict";
import { bestWindow, byChannel, cellLabel, daily, engagementOf, filterRows, heatmap, mytSlot, overview, ranked, viewsOf } from "./src/lib/analytics.js";

let n = 0;
const t = (name, fn) => { try { fn(); n++; } catch (e) { console.error("FAIL:", name); throw e; } };

const ROWS = [
  // Fri 3 Oct 21:03 MYT (13:03Z): the Threads peak, 274 views, 10 reactions, 4 reposts
  { id: 1, channel: "threads", sent_at: "2026-10-03T13:03:20Z", views: 274, reactions: 10, comments: 0, reposts: 4, quotes: 0, engagement: 5.11 },
  { id: 2, channel: "instagram", sent_at: "2026-10-03T13:04:28Z", views: 11, reach: 7, reactions: 0, comments: 0, shares: 0, saves: 0 },
  { id: 3, channel: "facebook", sent_at: "2026-10-03T13:01:58Z", impressions: 30, reactions: 1, comments: 0, shares: 1, clicks: 1 },
  // Fri 3 Oct 13:01 MYT (05:01Z)
  { id: 4, channel: "threads", sent_at: "2026-10-03T05:01:01Z", views: 36, reactions: 0, comments: 0 },
  // Thu 8 Oct 21:04 MYT and 13:01 MYT
  { id: 5, channel: "threads", sent_at: "2026-10-08T13:04:20Z", views: 28, reactions: 0, comments: 2 },
  { id: 6, channel: "threads", sent_at: "2026-10-08T05:01:29Z", views: 22, reactions: 1, comments: 0, engagement: 4.55 },
  // Sat 9 Oct 02:30 MYT (Fri 18:30Z): the date rolls over in Malaysia
  { id: 7, channel: "threads", sent_at: "2026-10-09T18:30:00Z", views: 5, reactions: 0, comments: 0 },
  { id: 8, channel: "threads", sent_at: null, views: 999 },                                              // no stamp: never counted
  { id: 9, channel: "threads", sent_at: "2026-08-01T05:00:00Z", views: 500, reactions: 50 },           // old: out of a 30-day window
];
const TODAY = "2026-10-10";

t("Malaysia's slot: day, hour, 3-hour window, and the date rolling over", () => {
  assert.deepEqual(mytSlot("2026-10-03T13:03:20Z"), { dow: 6, hour: 21, win: 7, date: "2026-10-03" });   // Saturday 21:03 MYT
  assert.deepEqual(mytSlot("2026-10-09T18:30:00Z"), { dow: 6, hour: 2, win: 0, date: "2026-10-10" });    // Saturday 02:30 MYT
  assert.equal(mytSlot(null), null);
  assert.equal(mytSlot("nonsense"), null);
});

t("views: views, else impressions, else reach; engagement is interactions over views", () => {
  assert.equal(viewsOf(ROWS[0]), 274);
  assert.equal(viewsOf(ROWS[2]), 30);
  assert.equal(viewsOf({ reach: 7 }), 7);
  assert.equal(engagementOf([ROWS[0]]), 5.11);                      // 14 / 274
  assert.equal(engagementOf([]), 0);
});

t("filter: channel and the last N Malaysian days; rows without a stamp are out", () => {
  const all = filterRows(ROWS, { days: 30, today: TODAY });
  assert.deepEqual(all.map((r) => r.id), [1, 2, 3, 4, 5, 6, 7]);
  assert.deepEqual(filterRows(ROWS, { channel: "instagram", days: 30, today: TODAY }).map((r) => r.id), [2]);
  assert.deepEqual(filterRows(ROWS, { days: 2, today: TODAY }).map((r) => r.id), [7]);               // 9 and 10 Oct only
  assert.deepEqual(filterRows(ROWS, { days: 365, today: TODAY }).map((r) => r.id), [1, 2, 3, 4, 5, 6, 7, 9]);
});

t("overview: totals, average a post, engagement, replies, the peak post", () => {
  const o = overview(filterRows(ROWS, { channel: "threads", days: 30, today: TODAY }));
  assert.equal(o.posts, 5);
  assert.equal(o.views, 365);
  assert.equal(o.avgViews, 73);
  assert.equal(o.replies, 2);
  assert.equal(o.peak.id, 1);
  assert.equal(o.engagement, 4.66);                                  // (14 + 0 + 2 + 1 + 0) / 365
});

t("heatmap: 56 cells, the posts land in Malaysia's day and window, heat is relative to the best average", () => {
  const cells = heatmap(filterRows(ROWS, { days: 30, today: TODAY }));
  assert.equal(cells.length, 56);
  const sat21 = cells[6 * 8 + 7];
  assert.equal(sat21.posts, 3);                                      // Threads, Instagram, Facebook at 21:0x MYT on Sat 3 Oct
  assert.equal(sat21.views, 315);
  assert.equal(sat21.avgViews, 105);
  assert.equal(sat21.heat, 1);
  const thu21 = cells[4 * 8 + 7];
  assert.equal(thu21.posts, 1);
  assert.equal(thu21.replies, 2);
  assert.equal(cells[0].posts, 0);
  assert.equal(cells.reduce((a, c) => a + c.posts, 0), 7);
});

t("best window: the highest average among windows with enough posts", () => {
  const cells = heatmap(filterRows(ROWS, { days: 30, today: TODAY }));
  assert.equal(cellLabel(bestWindow(cells)), "Sat 21-24 MYT");
  assert.equal(bestWindow(cells, 4), null);
  assert.equal(bestWindow([], 1), null);
});

t("daily series and the channel split", () => {
  const d = daily(filterRows(ROWS, { days: 30, today: TODAY }), TODAY, 8);
  assert.equal(d.length, 8);
  assert.equal(d[0].date, "2026-10-03");
  assert.equal(d[0].views, 351);                                     // the four Friday 3 Oct posts
  assert.equal(d[7].date, "2026-10-10");
  assert.equal(d[7].views, 5);                                       // the 02:30 MYT post sits on 10 Oct
  const ch = byChannel(filterRows(ROWS, { days: 30, today: TODAY }));
  assert.deepEqual(ch.map((c) => [c.channel, c.posts, c.views]), [["threads", 5, 365], ["instagram", 1, 11], ["facebook", 1, 30]]);
  assert.deepEqual(ranked(filterRows(ROWS, { days: 30, today: TODAY })).slice(0, 3).map((r) => r.id), [1, 4, 3]);
});

console.log(`analytics: ${n} checks passed`);
