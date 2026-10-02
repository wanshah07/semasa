/* web/src/lib/slots.js, the page's half of the position rules (the worker's half is ideas.next_free_position). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { captionKey, captionKeys, clashes, coverage, duplicatesOf, fmtLeft, holdersOf, isPastDue, moveCheck, nextFreeSlot, offRota, onRota, postsOn, purgeLeftMs, refOf, slotsOf } from "./src/lib/slots.js";

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
// ---- one post to a slot, the same words never twice (Wan, 3 Oct 2026) ----
t("caption keys agree with the Python and SQL rule (rules/caption_keys.json)", () => {
  const { cases } = JSON.parse(readFileSync(new URL("../rules/caption_keys.json", import.meta.url), "utf8"));
  assert.ok(cases.length >= 6);
  for (const c of cases) assert.equal(captionKey(c.text), c.key, c.text.slice(0, 40));
});
const CAPA = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan.";
const live = (id, over = {}) => ({ id, stream: "regulab", lang: "bm", status: "approved", date: "2026-09-30", slot: "13:00", text: { bm: { instagram: CAPA } }, ...over });
t("a duplicate is the same opening words on the same stream within 90 days, only against approved, scheduled or posted", () => {
  const me = live("me", { status: "draft", slot: "08:00", text: { bm: { instagram: CAPA.toUpperCase() + "!!" } } });
  assert.deepEqual(duplicatesOf(me, [live("a")]).map((p) => p.id), ["a"]);
  assert.deepEqual(duplicatesOf(me, [live("d", { status: "draft" })]), []);                 // another draft is not yet a post to be sent
  assert.deepEqual(duplicatesOf(me, [live("r", { status: "rejected" })]), []);
  assert.deepEqual(duplicatesOf(me, [live("l", { stream: "linkedin" })]), []);              // the two voices are not compared
  assert.deepEqual(duplicatesOf(me, [live("far", { date: "2026-05-01" })]), []);            // five months apart
  assert.deepEqual(duplicatesOf(me, [live("me")]), []);                                      // never itself
  assert.deepEqual(duplicatesOf({ ...me, text: { bm: { instagram: "Ok" } } }, [live("a", { text: { bm: { instagram: "Ok" } } })]), []);   // too short to call a copy
  assert.deepEqual(captionKeys({ stream: "linkedin", text: { en: { linkedin: CAPA }, bm: { linkedin: "x" } } }).length, 1);     // linkedin sends English
});
t("holdersOf: a rejected post holds nothing, another stream holds nothing", () => {
  const ps = [live("a"), live("b", { status: "rejected" }), live("c", { stream: "linkedin" })];
  assert.deepEqual(holdersOf(ps, "regulab", "2026-09-30", "13:00").map((p) => p.id), ["a"]);
  assert.deepEqual(holdersOf(ps, "regulab", "2026-09-30", "13:00", "a"), []);
});
t("moveCheck: free future slot of the lane ok; locked, same, taken, past, off-day and foreign slots refused", () => {
  const me = live("me", { status: "draft", date: "2026-09-29", slot: "21:00", domain: "kosmetik" });
  const others = [live("a", { date: "2026-09-30", slot: "13:00", status: "scheduled" })];
  const mv = (over = {}, ps = others) => moveCheck({ post: { ...me, ...(over.post || {}) }, date: over.date || "2026-09-30", slot: over.slot || "21:00", posts: ps, brand: BRAND, now: NOW });
  assert.deepEqual(mv(), { ok: true });
  assert.equal(mv({ slot: "13:00" }).why, "taken");
  assert.deepEqual(mv({ slot: "13:00" }).by.map((p) => p.id), ["a"]);
  assert.equal(mv({ post: { status: "scheduled" } }).why, "status");
  assert.equal(mv({ post: { status: "posted" } }).why, "status");
  assert.equal(mv({ post: { status: "rejected" } }).why, "status");
  assert.equal(mv({ date: "2026-09-29", slot: "21:00" }).why, "same");
  assert.equal(mv({ slot: "09:00" }).why, "slot");                                           // not one of the lane's slots
  assert.equal(mv({ date: "2026-09-26", slot: "08:00" }).why, "day");                        // Saturday: no posting day
  assert.equal(mv({ date: "2026-09-24", slot: "08:00" }).why, "past");                       // this morning
  assert.equal(mv({ date: "2026-09-24", slot: "13:00" }).ok, true);                          // 13:00 is still ahead of 10:00
  assert.equal(mv({ date: "2026-09-27", slot: "08:00" }).note, "rota");                      // a kosmetik post on a halal Sunday: a note only
  assert.equal(mv({ slot: "13:00" }, [live("r", { date: "2026-09-30", slot: "13:00", status: "rejected" })]).ok, true);
  assert.equal(mv({ slot: "13:00" }, [live("l", { date: "2026-09-30", slot: "13:00", stream: "linkedin" })]).ok, true);
});
console.log(`${n} slot tests pass`);
