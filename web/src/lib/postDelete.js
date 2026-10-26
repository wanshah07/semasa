/* May a post be deleted from the Posts list (Wan, 26 Oct 2026: "add button delete in table or in card")? The database lets a
   browser delete only a draft or a rejected post (supabase/005), so an approved one is put back to draft first, and one the
   publisher has scheduled or sent, or one with a record on any channel, is never deleted from here. `why` is the [BM, EN] reason.
   No imports, so web/postDelete.test.mjs runs this under Node as it is. */
export function deleteCheck(post) {
  const delivered = Object.keys((post && post.published) || {}).length > 0;
  if (!post) return { ok: false, why: ["Tiada post", "No post"] };
  if (post.status === "scheduled" || post.status === "posted" || post.status === "archived") {
    return { ok: false, why: ["Sudah dijadualkan atau disiarkan: tidak boleh dipadam di sini", "Already scheduled or sent: it cannot be deleted here"] };
  }
  if (delivered) return { ok: false, why: ["Sudah dihantar ke satu saluran: rekodnya dikekalkan", "Already delivered to a channel: its record is kept"] };
  if (post.status === "approved") return { ok: true, backToDraft: true };
  if (post.status === "draft" || post.status === "rejected") return { ok: true, backToDraft: false };
  return { ok: false, why: ["Status ini tidak boleh dipadam", "This status cannot be deleted"] };
}
