/* web/src/lib/slots.js, the page's half of the position rules (the worker's half is ideas.next_free_position). */
import assert from "node:assert/strict";
import { clashes, coverage, fmtLeft, isPastDue, nextFreeSlot, offRota, onRota, postsOn, purgeLeftMs, refOf, slotsOf } from "./src/lib/slots.js";

const BRAND = {
  regulab: { slots: ["13:00", "08:00", "21:00"],
    schedule: { 0: ["halal_my", "fatwa"], 1: ["kosmetik", "sains_kosmetik"], 2: ["halal_my", "fatwa"], 3: ["kosmetik", "kajian_kes"],
      4: ["farmaseutikal", "makanan"], 5: ["kosmetik", "sains_kosmetik"], 6: [] } },
  linkedin: { slots: ["06:00", "19:00"], days: [1, 3, 5] },
};
const NOW = Date.parse("2026-09-24T02:00:00Z");     // Thu 24 Sep, 10:00 MYT
let n = 0;
const t = (name, fn) => { fn(); n++; };

t("slots sorted, defaults", () => {
  assert.deepEqual(slotsOf(BRAND, "regulab"), ["08:00", "13:00", "21:00"]);
  assert.deepEqual(slotsOf({}, "linkedin"), ["06:00"]);
});
t("posting days", () => {
  assert.equal(postsOn(BRAND, "regulab", "2026-09-26"), false);          // Saturday: empty rota
  assert.equal(postsOn(BRAND, "regulab", "2026-09-27"), true);
  assert.equal(postsOn({ regulab: { schedule: { 6: null } } }, "regulab", "2026-09-26"), true);   // unspecified = posts
  assert.equal(postsOn(BRAND, "linkedin", "2026-09-24"), false);          // Thursday not in days
  assert.equal(postsOn({ linkedin: { days: [] } }, "linkedin", "2026-09-24"), true);
});
t("rota, case study any posting day", () => {
  assert.equal(onRota(BRAND, "2026-09-27", "kosmetik"), false);
  assert.equal(onRota(BRAND, "2026-09-27", "kajian_kes"), true);
  assert.equal(onRota(BRAND, "2026-09-27", null), true);
});
t("next free slot: today's later slots, lead time, rota, taken", () => {
  // 10:00 now: 13:00 today is free and more than 30 minutes away; Thursday takes farmaseutikal
  assert.deepEqual(nextFreeSlot({ posts: [], brand: BRAND, stream: "regulab", domain: "farmaseutikal", now: NOW }), { date: "2026-09-24", slot: "13:00" });
  const posts = [{ id: "a", stream: "regulab", status: "draft", date: "2026-09-24", slot: "13:00" },
    { id: "b", stream: "regulab", status: "rejected", date: "2026-09-24", slot: "21:00" }];
  assert.deepEqual(nextFreeSlot({ posts, brand: BRAND, stream: "regulab", now: NOW }), { date: "2026-09-24", slot: "21:00" });
  assert.deepEqual(nextFreeSlot({ posts, brand: BRAND, stream: "regulab", skipId: "a", now: NOW }), { date: "2026-09-24", slot: "13:00" });
  // halal: Fri no, Sat no posting, Sun yes
  assert.deepEqual(nextFreeSlot({ posts: [], brand: BRAND, stream: "regulab", domain: "halal_my", now: NOW }), { date: "2026-09-27", slot: "08:00" });
  // 12:40 MYT: 13:00 is inside the 30-minute lead, so 21:00
  assert.deepEqual(nextFreeSlot({ posts: [], brand: BRAND, stream: "regulab", now: Date.parse("2026-09-24T04:40:00Z") }), { date: "2026-09-24", slot: "21:00" });
  // a date in the past is never returned, whatever fromDate says
  assert.deepEqual(nextFreeSlot({ posts: [], brand: BRAND, stream: "linkedin", fromDate: "2026-09-01", now: NOW }), { date: "2026-09-25", slot: "06:00" });
});
t("coverage: gaps, past, no-posting day, clash, another time", () => {
  const posts = [{ id: "a", stream: "regulab", status: "draft", date: "2026-09-24", slot: "13:00" },
    { id: "b", stream: "regulab", status: "approved", date: "2026-09-24", slot: "13:00" },
    { id: "c", stream: "regulab", status: "draft", date: "2026-09-25", slot: "10:30" },
    { id: "d", stream: "linkedin", status: "draft", date: "2026-09-24", slot: "08:00" }];
  const c = coverage({ posts, brand: BRAND, stream: "regulab", days: 3, now: NOW });
  assert.equal(c.length, 3);
  assert.deepEqual(c[0].cells.map((x) => [x.slot, x.past, x.gap, x.clash, x.posts.length]),
    [["08:00", true, false, false, 0], ["13:00", false, false, true, 2], ["21:00", false, true, false, 0]]);
  assert.deepEqual(c[1].extra.map((p) => p.id), ["c"]);
  assert.equal(c[2].posting, false);
  assert.ok(c[2].cells.every((x) => !x.gap));
  assert.equal(clashes(posts).length, 1);
});
t("off rota only for waiting ws.regulab posts from today", () => {
  const posts = [{ id: "a", stream: "regulab", status: "draft", date: "2026-09-27", domain: "kosmetik" },
    { id: "b", stream: "regulab", status: "posted", date: "2026-09-27", domain: "kosmetik" },
    { id: "c", stream: "regulab", status: "draft", date: "2026-09-20", domain: "kosmetik" },
    { id: "d", stream: "regulab", status: "draft", date: "2026-09-27", domain: "kajian_kes" }];
  assert.deepEqual(offRota(posts, BRAND, NOW).map((p) => p.id), ["a"]);
});
t("past due: 45 minutes of grace", () => {
  assert.equal(isPastDue({ status: "approved", date: "2026-09-24", slot: "09:20" }, NOW), false);
  assert.equal(isPastDue({ status: "approved", date: "2026-09-24", slot: "09:10" }, NOW), true);
  assert.equal(isPastDue({ status: "posted", date: "2026-09-20", slot: "08:00" }, NOW), false);
});
t("purge countdown, never 60m, guards", () => {
  const p = { status: "rejected", rejected_at: "2026-09-22T00:00:00Z" };
  const left = purgeLeftMs(p, Date.parse("2026-09-24T18:00:15Z"));          // 72h - 66h0m15s = 5h59m45s
  assert.equal(fmtLeft(left), "5h 59m");
  assert.equal(fmtLeft(50 * 3600_000), "2d 2h");
  assert.equal(fmtLeft(-5), "0m");
  assert.equal(purgeLeftMs({ status: "rejected" }, NOW), null);
  assert.equal(purgeLeftMs({ ...p, published: { facebook: {} } }, NOW), null);
  assert.equal(purgeLeftMs({ ...p, status: "draft" }, NOW), null);
});
t("short references", () => {
  assert.equal(refOf({ stream: "regulab", date: "2026-09-09", slot: "21:00" }, BRAND), "R0909c");
  assert.equal(refOf({ stream: "linkedin", date: "2026-09-25", slot: "06:00" }, BRAND), "L0925a");
  assert.equal(refOf({ stream: "regulab", date: "2026-09-09", slot: "14:30" }, BRAND), "R0909-1430");
  assert.equal(refOf({ stream: "regulab" }, BRAND), "");
});
console.log(`${n}/9 slot tests pass`);
