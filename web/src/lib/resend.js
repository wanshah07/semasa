/* What the post editor says about a half-sent post (Wan, 16 Nov 2026: "move to new slot"), as one plain function so
   web/resend.test.mjs runs it under Node. The rules themselves are in slots.js (canResend, resendChannels), the same ones the
   publisher (backend/semasa/publisher.py stale_failures) and the database (supabase/084_resend_failed_channels.sql) apply. */
import { LATE_GRACE_MIN, dueMs, failedChannels, queuedChannels, resendChannels, sentChannels } from "./slots.js";

export const RESEND_STATUSES = ["draft", "approved", "scheduled"];

/** {show, state, failed, sent, queued, again, lost, reasons} for one post.
 *  state: "move"    every channel is settled and one failed: moving the post sends the failed ones again;
 *         "queued"  a channel is still in the scheduler's queue: the post cannot move yet;
 *         "waiting" the post has been moved: the publisher hands the failed channels over at its next run;
 *         "approve" the same, for a post the move sent back to draft: it must be approved again first;
 *         "missed"  it was moved, and the new slot passed before the publisher handed it over: move it again. */
export function resendView(post, now = Date.now()) {
  const failed = post ? failedChannels(post) : [];
  if (!post || !failed.length || !RESEND_STATUSES.includes(post.status)) {
    return { show: false, state: "", failed: [], sent: [], queued: [], again: [], lost: [], reasons: {} };
  }
  const again = resendChannels(post);
  const queued = queuedChannels(post);
  const gone = !!(post.date && post.slot) && dueMs(post.date, post.slot) < +now - LATE_GRACE_MIN * 60_000;
  const reasons = {};
  for (const c of failed) reasons[c] = String(((post.errors || {})[c] || {}).message || "");
  const state = again.length && !gone ? (post.status === "draft" ? "approve" : "waiting")
    : queued.length ? "queued" : again.length ? "missed" : "move";
  return { show: true, state, failed, sent: sentChannels(post), queued, again,
    lost: failed.filter((c) => post.published[c].lost === true), reasons };
}
