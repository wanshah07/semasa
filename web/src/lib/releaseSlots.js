/* Release every booked slot of one stream (Wan, 26 Oct 2026: "make sure ada button untuk clear semua book slot"). A draft or an
   approved post is let go of its date and slot (an approved one goes back to draft, which semasa_posts_gate does itself when its
   slot changes, and needs approving again); a post the publisher has scheduled or sent is never touched. The posts are asked of the
   DATABASE first, and each write is pinned to the position the post still holds and to a status that can be released, so a post
   moved, approved-and-sent or edited meanwhile is left alone. Shared by the Schedule view and the Motion panel. */
import { TABLES, supabase } from "./SupabaseClient";
import { withDecision } from "./workflow";

export async function releaseSlots(stream) {
  const { data, error } = await supabase.from(TABLES.posts).select("id,stream,status,date,slot,decisions")
    .eq("stream", stream).in("status", ["draft", "approved"]).not("slot", "is", null);
  if (error) return { error, freed: 0, stuck: 0 };
  let freed = 0, stuck = 0;
  for (const p of data || []) {
    if (!p.date || !p.slot) continue;
    const patch = { date: null, slot: null, ...("decisions" in p ? { decisions: withDecision(p, "moved", `slot ${p.date} ${p.slot} released: clear all booked slots`) } : {}) };
    const res = await supabase.from(TABLES.posts).update(patch).eq("id", p.id).eq("date", p.date).eq("slot", p.slot)
      .in("status", ["draft", "approved"]).select("id");
    if (res.error || !(res.data || []).length) stuck++; else freed++;
  }
  return { freed, stuck };
}
