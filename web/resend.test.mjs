/* web/src/lib/resend.js: what the post editor says about a half-sent post (Wan, 16 Nov 2026: "move to new slot"). */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resendView } from "./src/lib/resend.js";

const NOW = Date.parse("2026-11-16T10:00:00Z");           // 16 Nov, 18:00 MYT
let n = 0;
const t = (name, fn) => { fn(); n++; };
const rec = (status, over = {}) => ({ id: "a".repeat(24), route: "zernio", mode: "customScheduled", status, dueAt: "2026-11-16T00:00:00.000Z", ...over });
/* the post of 16 Nov 08:00: Instagram went out, TikTok and Threads failed */
const post = (over = {}) => ({ id: "p", stream: "regulab", status: "scheduled", date: "2026-11-16", slot: "08:00",
  published: { instagram: rec("sent"), tiktok: rec("error"), threads: rec("error") },
  errors: { tiktok: { message: "tiktok: Failed to download video: 402 Payment Required" }, threads: { message: "threads: token refresh failed" } }, ...over });

t("a half-sent post names its failed channels with the platform's own words and offers the move", () => {
  const v = resendView(post(), NOW);
  assert.deepEqual([v.show, v.state, v.failed, v.sent, v.queued, v.again], [true, "move", ["tiktok", "threads"], ["instagram"], [], []]);
  assert.equal(v.reasons.tiktok, "tiktok: Failed to download video: 402 Payment Required");
  assert.equal(resendView(post({ status: "approved" }), NOW).state, "move");
});
t("while a channel is still queued the post cannot move, and the box says which", () => {
  const v = resendView(post({ published: { instagram: rec("scheduled"), threads: rec("error") } }), NOW);
  assert.deepEqual([v.state, v.queued, v.failed], ["queued", ["instagram"], ["threads"]]);
});
t("once moved it waits for the publisher; a draft must be approved again first; a missed slot is moved again", () => {
  const moved = post({ date: "2026-11-17" });
  assert.deepEqual([resendView(moved, NOW).state, resendView(moved, NOW).again], ["waiting", ["threads", "tiktok"]]);
  assert.equal(resendView({ ...moved, status: "draft" }, NOW).state, "approve");
  // one channel already handed over again for the new slot, the other still to go: still the publisher's, not a person's
  const part = post({ date: "2026-11-17", published: { instagram: rec("sent"), tiktok: rec("scheduled", { dueAt: "2026-11-17T00:00:00.000Z" }), threads: rec("error") } });
  assert.equal(resendView(part, NOW).state, "waiting");
  assert.equal(resendView(post({ slot: "13:00" }), NOW).state, "missed", "moved to 13:00 today and it is 18:00: move it again");
});
t("a record the scheduler lost is named, so the platform is checked before the move", () => {
  const li = { id: "l", stream: "linkedin", status: "scheduled", date: "2026-11-16", slot: "19:00",
    published: { linkedin: rec("error", { dueAt: "2026-11-16T11:00:00.000Z", lost: true }) },
    errors: { linkedin: { message: "linkedin: Zernio no longer holds this post and it was not sent" } } };
  const v = resendView(li, NOW);
  assert.deepEqual([v.state, v.lost, v.sent], ["move", ["linkedin"], []]);
});
t("nothing is shown for a post with no failed channel, or one that is posted or rejected", () => {
  assert.equal(resendView(post({ published: { instagram: rec("sent") } }), NOW).show, false);
  assert.equal(resendView(post({ published: {} }), NOW).show, false);
  assert.equal(resendView(post({ status: "posted" }), NOW).show, false);
  assert.equal(resendView(post({ status: "rejected" }), NOW).show, false);
  assert.equal(resendView(null, NOW).show, false);
});
t("the editor draws the box, and the box writes the date and slot and nothing else, pinned to the post as it was", () => {
  const editor = readFileSync(new URL("./src/components/PostEditor.jsx", import.meta.url), "utf8");
  assert.match(editor, /<PostResend post=\{post\} posts=\{posts\} brand=\{brand\}/);
  const box = readFileSync(new URL("./src/components/PostResend.jsx", import.meta.url), "utf8");
  assert.match(box, /const patch = \{ date, slot, \.\.\.\("decisions" in post/);
  assert.match(box, /\.eq\("date", post\.date\)\.eq\("slot", post\.slot\)\s*\.eq\("status", post\.status\)/);
  assert.match(box, /moveCheck\(\{ post, date, slot, posts: live \|\| \[\], brand \}\)/);
  assert.ok(!/status: "approved"|status: "scheduled"/.test(box), "the page never writes a status here: the approval gate is the database's");
  assert.ok(!/—/.test(box));
});
console.log(`resend: ${n} checks passed`);
