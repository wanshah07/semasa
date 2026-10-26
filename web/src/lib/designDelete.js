/* Who may delete a generated design (Wan, 26 Oct 2026: "make sure design in draft can be deleted"). The worker makes most
   pictures, so created_by is null; the database policy (supabase/056) lets an uploader delete those and their own, and the
   buttons follow the same rule. Retrying a failed job stays with the person who started it (supabase/002). */

/** True when `user` may delete `row`: the creator, or anyone signed in for a picture the worker made (no owner). */
export function canDeleteDesign(row, user) {
  return !!user && !!row && (!row.created_by || row.created_by === user.id);
}

/** True when `user` started `row` and so may put a failed job back in the queue. */
export function ownsDesign(row, user) {
  return !!user && !!row && row.created_by === user.id;
}
