/* What a generation card does to its row (retry on a provider, delete) and which rows a post has locked (supabase/017: the
   database refuses to delete a picture inside an approved, scheduled or posted post). One place, so the image, video and poster
   libraries all behave as the old Media tab did. Pure apart from the callbacks it is given. */
export function lockedMedia(posts) {
  return new Set((posts?.rows || []).filter((p) => ["approved", "scheduled", "posted"].includes(p.status)).flatMap((p) => p.media_ids || []));
}

export function genActions({ gens, onToast, t }) {
  const guard = async (fn) => { try { await fn(); } catch (e) { onToast(e.message, "danger"); } };
  return {
    onRequeue: (id, provider) => guard(async () => { await gens.requeue(id, provider); onToast(t("Dimasukkan semula ke giliran.", "Put back in the queue."), "ok"); }),
    onRemove: (row) => guard(async () => {
      if (window.confirm(t("Padam kerja ini?", "Delete this job?"))) { await gens.remove(row); onToast(t("Dipadam.", "Deleted."), "info"); }
    }),
  };
}

/** The picture to show for a generation row: the result, else the first slide, else the reference it was made from. */
export const thumbOf = (row) => row.generated_media_url || row.meta?.slide_urls?.[0] || row.reference_url || "";
