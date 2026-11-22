/* web/src/lib/slots.js, the page's half of the position rules (the worker's half is ideas.next_free_position). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { approvePosition, canResend, captionKey, captionKeys, clashes, coverage, duplicatesOf, failedChannels, fmtLeft, handOverInTime, handedOver, holdersOf, isPastDue, lateLinkedInSlots, liSendDay, moveCheck, myt, nextFreeSlot, nextRunMs, offRota, onRota, overrideCheck, clearPlan, postsOn, purgeLeftMs, queuedChannels, refOf, resendChannels, sentChannels, slotGone, slotsOf, isCustomSlot, validClock } from "./src/lib/slots.js";

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

t("overrideCheck: a draft or an approved holder can be released, a scheduled or posted one locks the slot, rejected holds nothing", () => {
  const ps = [{ id: "d", stream: "regulab", status: "draft", date: "2026-10-30", slot: "08:00" }, { id: "a", stream: "regulab", status: "approved", date: "2026-10-30", slot: "13:00" },
    { id: "s", stream: "regulab", status: "scheduled", date: "2026-10-30", slot: "21:00" }, { id: "r", stream: "regulab", status: "rejected", date: "2026-10-31", slot: "08:00" },
    { id: "l", stream: "linkedin", status: "draft", date: "2026-10-30", slot: "08:00" }];
  const c = (date, slot, stream = "regulab") => overrideCheck({ posts: ps, stream, date, slot });
  assert.deepEqual([c("2026-10-30", "08:00").free, c("2026-10-30", "08:00").ok, c("2026-10-30", "08:00").release.map((p) => p.id)], [false, true, ["d"]]);
  assert.deepEqual(c("2026-10-30", "13:00").release.map((p) => p.id), ["a"]);
  assert.deepEqual([c("2026-10-30", "21:00").ok, c("2026-10-30", "21:00").locked.map((p) => p.id), c("2026-10-30", "21:00").release.length], [false, ["s"], 0]);
  assert.equal(c("2026-10-31", "08:00").free, true, "a rejected post holds nothing");
  assert.deepEqual(c("2026-10-30", "08:00", "linkedin").release.map((p) => p.id), ["l"], "the other stream's slot is its own");
});

t("clearPlan: drafts and approved are released, scheduled and posted are counted as kept, a post with no position is ignored", () => {
  const ps = [{ id: "d1", status: "draft", date: "2026-10-30", slot: "08:00" }, { id: "d2", stream: "regulab", status: "draft", date: "2026-10-31", slot: "08:00" },
    { id: "a", status: "approved", date: "2026-11-01", slot: "08:00" }, { id: "s", status: "scheduled", date: "2026-11-02", slot: "08:00" },
    { id: "p", status: "posted", date: "2026-10-20", slot: "08:00" }, { id: "n", status: "draft", date: null, slot: null }, { id: "r", status: "rejected", date: "2026-11-03", slot: "08:00" },
    { id: "l", stream: "linkedin", status: "draft", date: "2026-10-30", slot: "06:00" }];
  const plan = clearPlan(ps, "regulab");
  assert.deepEqual([plan.drafts, plan.approved, plan.locked, plan.release.map((p) => p.id).sort()], [2, 1, 2, ["a", "d1", "d2"]]);
  assert.equal(clearPlan(ps, "linkedin").release.length, 1);
});

t("LinkedIn lateness is the publisher's: a slot after the last run (19:20) goes at 06:20 the next day, never called overdue", () => {
  assert.equal(liSendDay("2026-09-24", "06:00"), "2026-09-24");
  assert.equal(liSendDay("2026-09-24", "19:20"), "2026-09-24");
  assert.equal(liSendDay("2026-09-24", "20:00"), "2026-09-25");
  const at = (iso) => Date.parse(iso);
  const li = (date, slot) => ({ stream: "linkedin", status: "approved", date, slot });
  // 06:20 MYT on 25 Sep: yesterday 20:00 is still to be sent, yesterday 06:00 is gone
  assert.equal(isPastDue(li("2026-09-24", "20:00"), at("2026-09-24T22:20:00Z")), false);
  assert.equal(isPastDue(li("2026-09-24", "06:00"), at("2026-09-24T22:20:00Z")), true);
  assert.equal(isPastDue(li("2026-09-24", "20:00"), at("2026-09-25T22:20:00Z")), true);       // a day later still: overdue
  // the same day, hours after its slot: LinkedIn still sends it that day (cap permitting); ws.regulab has 45 minutes
  assert.equal(slotGone("linkedin", "2026-09-24", "06:00", NOW), false);
  assert.equal(slotGone("regulab", "2026-09-24", "06:00", NOW), true);
  assert.deepEqual(lateLinkedInSlots(["06:00", "19:00", "19:21", "21:30"]), ["19:21", "21:30"]);
});

t("a post with a channel already in Buffer or LinkedIn cannot be moved or released by the page", () => {
  const rec = { facebook: { id: "a".repeat(24), status: "scheduled", dueAt: "2026-09-30T05:00:00Z" } };
  assert.equal(handedOver({ published: {} }), false);
  assert.equal(handedOver({ published: null }), false);
  assert.equal(handedOver({ published: rec }), true);
  const me = live("me", { status: "approved", date: "2026-09-30", slot: "13:00", published: rec });
  assert.equal(moveCheck({ post: me, date: "2026-09-30", slot: "21:00", posts: [], brand: BRAND, now: NOW }).why, "published");
  const o = overrideCheck({ posts: [me], stream: "regulab", date: "2026-09-30", slot: "13:00" });
  assert.deepEqual([o.ok, o.release.length, o.locked.map((p) => p.id)], [false, 0, ["me"]]);
  const plan = clearPlan([me, live("d", { status: "draft", date: "2026-10-01", slot: "08:00" })], "regulab");
  assert.deepEqual([plan.release.map((p) => p.id), plan.approved, plan.locked], [["d"], 0, 1]);
});

t("a time outside the fixed slots is a custom slot, and only a real 24-hour clock is accepted", () => {
  const slots = slotsOf(BRAND, "regulab");
  assert.equal(isCustomSlot(slots, "08:00"), false);
  assert.equal(isCustomSlot(slots, "10:30"), true);
  assert.equal(isCustomSlot(slots, ""), false);
  assert.deepEqual(["10:30", "00:00", "23:59", "24:00", "9:30", "10:60", "", null].map(validClock), [true, true, true, false, false, false, false, false]);
});

/* ---- sending the failed channels of a half-sent post again (Wan, 16 Nov 2026: "move to new slot") ---- */
const OLD = "2026-09-23T00:00:00.000Z";                   // 23 Sep 08:00 MYT: the slot the channels failed at
const zrec = (status, over = {}) => ({ id: "a".repeat(24), route: "zernio", mode: "customScheduled", status, dueAt: OLD, ...over });
const half = (over = {}) => ({ id: "h", stream: "regulab", status: "scheduled", date: "2026-09-23", slot: "08:00", domain: "kosmetik",
  published: { instagram: zrec("sent"), tiktok: zrec("error"), threads: zrec("error") }, ...over });

t("a half-sent post: which channels failed, went out, are still queued, and whether it may move", () => {
  const p = half();
  assert.deepEqual([failedChannels(p), sentChannels(p), queuedChannels(p)], [["tiktok", "threads"], ["instagram"], []]);
  assert.equal(canResend(p), true);
  assert.equal(canResend(half({ status: "approved" })), true);
  assert.equal(canResend(half({ status: "draft" })), true, "an approved post goes back to draft when it moves: that draft may move again");
  assert.equal(canResend(half({ status: "posted" })), false);
  assert.equal(canResend(half({ status: "rejected" })), false);
  const queued = half({ published: { instagram: zrec("scheduled"), threads: zrec("error") } });
  assert.deepEqual(queuedChannels(queued), ["instagram"]);
  assert.equal(canResend(queued), false, "a channel the scheduler still holds keeps the post where it is");
  assert.equal(canResend(half({ published: { instagram: zrec("sent"), threads: zrec("sending") } })), false);
  assert.equal(canResend(half({ published: { instagram: zrec("sent"), threads: true } })), false, "a record that cannot be read is not settled");
  assert.equal(canResend(half({ published: { instagram: zrec("sent") } })), false, "nothing failed: nothing to send again");
  assert.equal(canResend(half({ published: {} })), false);
});

t("moveCheck lets a settled half-sent post move, scheduled or not, and still refuses one with a channel queued", () => {
  const mv = (post, date = "2026-09-30", slot = "21:00", posts = []) => moveCheck({ post, date, slot, posts, brand: BRAND, now: NOW });
  assert.deepEqual(mv(half()), { ok: true, resend: true });
  assert.deepEqual(mv(half({ status: "approved" })), { ok: true, resend: true });
  assert.equal(mv(half({ published: { instagram: zrec("scheduled"), threads: zrec("error") } })).why, "status");
  assert.equal(mv(half({ status: "approved", published: { instagram: zrec("scheduled"), threads: zrec("error") } })).why, "published");
  assert.equal(mv(half({ status: "posted" })).why, "status");
  // one post to a slot holds for it as for any other post
  assert.equal(mv(half(), "2026-09-30", "13:00", [live("a", { date: "2026-09-30", slot: "13:00", status: "scheduled" })]).why, "taken");
  assert.equal(mv(half(), "2026-09-23", "08:00").why, "same");
  assert.equal(mv(half(), "2026-09-24", "08:00").why, "past");
});

t("the publisher hands posts over only at its runs: a scheduled post is never moved to a slot its next run comes too late for", () => {
  // NOW is 10:00 MYT: the next run is 11:20; after 19:20 it is 06:20 the next day
  assert.equal(myt(nextRunMs(NOW)).time, "11:20");
  assert.equal(myt(nextRunMs(Date.parse("2026-09-24T11:20:00Z"))).time, "19:20");
  assert.deepEqual(myt(nextRunMs(Date.parse("2026-09-24T12:00:00Z"))), { date: "2026-09-25", time: "06:20", dow: 5 });
  assert.equal(handOverInTime("2026-09-24", "13:00", NOW), true);
  assert.equal(handOverInTime("2026-09-24", "10:40", NOW), true, "11:20 is still inside the 45 minutes after 10:40");
  const at1140 = Date.parse("2026-09-24T03:40:00Z");                                        // 11:40 MYT: the 11:20 run has gone
  assert.equal(handOverInTime("2026-09-24", "13:00", at1140), false, "the next run is 19:20, six hours after a 13:00 slot");
  const chk = moveCheck({ post: half(), date: "2026-09-24", slot: "13:00", posts: [], brand: BRAND, now: at1140 });
  assert.deepEqual([chk.ok, chk.why, chk.run], [false, "run", "19:20"]);
  assert.equal(moveCheck({ post: half(), date: "2026-09-24", slot: "21:00", posts: [], brand: BRAND, now: at1140 }).ok, true);
  // an approved post is approved again after its move, as before: this refusal is for a scheduled one only
  assert.equal(moveCheck({ post: half({ status: "approved" }), date: "2026-09-24", slot: "13:00", posts: [], brand: BRAND, now: at1140 }).ok, true);
});

t("resendChannels is the publisher's stale_failures: a failure for another moment than the slot the post has now", () => {
  assert.deepEqual(resendChannels(half()), [], "not moved: nothing is sent again by itself");
  assert.deepEqual(resendChannels(half({ date: "2026-09-25" })), ["threads", "tiktok"]);
  assert.deepEqual(resendChannels(half({ date: "2026-09-25", published: { instagram: zrec("sent") } })), [], "a sent channel is never sent again");
  assert.deepEqual(resendChannels(half({ date: "2026-09-25", published: { threads: zrec("scheduled") } })), [], "a queued one is not a failure");
  assert.deepEqual(resendChannels(half({ date: "2026-09-25", published: { threads: { status: "error", route: "zernio" } } })), [], "no moment: left for a person");
  assert.deepEqual(resendChannels(half({ date: "2026-09-25", published: { linkedin: zrec("error", { route: "composio" }) } })), []);
  const now = { status: "error", route: "zernio", mode: "shareNow", dueAt: null, at: "2026-09-23T00:30:00+00:00" };   // fired 08:30
  assert.deepEqual(resendChannels(half({ published: { threads: now } })), [], "a send-now fired late is still its own slot");
  assert.deepEqual(resendChannels(half({ date: "2026-09-25", published: { threads: now } })), ["threads"]);
  // the two files keep the same numbers
  const py = readFileSync(new URL("../backend/semasa/publisher.py", import.meta.url), "utf8");
  assert.match(py, /ADOPT_WITHIN = timedelta\(minutes=2\)/);
  assert.match(py, /LATE_GRACE = timedelta\(minutes=45\)/);
  assert.match(py, /PUBLISH_RUNS_MYT = \("06:20", "11:20", "19:20"\)/);
});

t("supabase/084 says what the page says: settled and one failed may move, and a scheduled post's slot is checked", () => {
  const sql = readFileSync(new URL("../supabase/084_resend_failed_channels.sql", import.meta.url), "utf8");
  assert.match(sql, /old\.status in \('draft', 'approved', 'scheduled'\)/);
  assert.match(sql, /not in \('sent', 'error'\)/);
  assert.match(sql, /r\.value ->> 'status' = 'error'/);
  assert.match(sql, /\(moved and not resend\)/);
  assert.match(sql, /new\.status in \('draft', 'scheduled'\) and moved/);
  // a scheduled post takes the move and nothing else, and the policy lets that one write through (never `posted`)
  assert.match(sql, /to_jsonb\(new\) - array\['date', 'slot', 'decisions', 'updated_at'\]/);
  assert.match(sql, /with check \(public\.semasa_is_uploader\(\) and status in \('draft', 'approved', 'rejected', 'scheduled'\)\)/);
  assert.match(sql, /elsif old\.status in \('scheduled', 'posted'\) then\s+new\.approved_by := old\.approved_by/);
  assert.ok(!/—/.test(sql));
});

t("Approve keeps a usable slot, and moves a missing, gone or held one to the next free slot (Wan, 22 Nov 2026)", () => {
  const mine = { id: "a", stream: "regulab", status: "draft", domain: "farmaseutikal" };
  const at = (date, slot, posts = []) => approvePosition({ post: { ...mine, date, slot }, date, slot, posts, brand: BRAND, now: NOW });
  assert.deepEqual(at("2026-09-24", "21:00"), { date: "2026-09-24", slot: "21:00", moved: false });
  assert.deepEqual(at("2026-09-23", "08:00"), { date: "2026-09-24", slot: "13:00", moved: true, why: "past",
    from: { date: "2026-09-23", slot: "08:00" } }, "yesterday: today's next slot, not tomorrow's");
  const held = [{ id: "b", stream: "regulab", status: "draft", date: "2026-09-24", slot: "13:00" }];
  const taken = at("2026-09-24", "13:00", held);
  assert.equal(taken.why, "taken"); assert.equal(taken.slot, "21:00");
  assert.equal(at("2026-09-23", "08:00", held).slot, "21:00", "never onto a held slot");
  const rejected = [{ ...held[0], status: "rejected" }];
  assert.equal(at("2026-09-24", "13:00", rejected).moved, false, "a rejected post holds nothing");
  assert.equal(at(null, null).why, "none");
  assert.equal(at(null, null).slot, "13:00");
  // the rota is kept: a cosmetics post that missed Thursday goes on Friday
  const cos = approvePosition({ post: { ...mine, domain: "kosmetik", date: "2026-09-23", slot: "08:00" }, date: "2026-09-23",
    slot: "08:00", posts: [], brand: BRAND, now: NOW });
  assert.deepEqual([cos.date, cos.slot], ["2026-09-25", "08:00"]);
  // LinkedIn: its own slots and weekdays (Mon, Wed, Fri)
  const li = approvePosition({ post: { id: "l", stream: "linkedin", status: "draft" }, date: "2026-09-21", slot: "06:00",
    posts: [], brand: BRAND, now: NOW });
  assert.deepEqual([li.date, li.slot, li.why], ["2026-09-25", "06:00", "past"]);
  const closed = { regulab: { slots: ["08:00"], schedule: Object.fromEntries([0, 1, 2, 3, 4, 5, 6].map((d) => [d, []])) } };
  assert.equal(approvePosition({ post: mine, date: "2026-09-23", slot: "08:00", posts: [], brand: closed, now: NOW }), null);
});

t("the editor's Approve is no longer blocked by a past or held slot: it moves the post (PostEditor.jsx)", () => {
  const src = readFileSync(new URL("./src/components/PostEditor.jsx", import.meta.url), "utf8");
  const blocking = src.match(/const blocking = ([^;]+);/)[1];
  assert.ok(!/past|clash/.test(blocking), "past and clash are notes now");
  assert.match(src, /approvePosition\(\{ post, date, slot, posts: live \|\| posts, brand \}\)/, "approve re-reads the slots first");
  assert.ok(!/disabled=\{busy \|\| blocking > 0 \|\| !date/.test(src), "no date is not a block either: Approve picks a slot");
});

console.log(`${n} slot tests pass`);
