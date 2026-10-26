-- 056 · Delete a design that sits in a DRAFT post (Wan, 26 Oct 2026: "make sure design in draft can be deleted").
-- All 71 pictures in draft posts were made by the worker, so created_by is null, and 002's delete policy only lets the
-- creator delete (created_by = auth.uid()): neither the page nor the database would let Wan remove any of them.
--   1. The delete policy also covers a picture with no owner (the worker's), for an uploader. Another uploader's own picture
--      stays theirs. The approved/scheduled/posted lock (semasa_media_gate, 017/018) is untouched and still refuses.
--   2. Deleting a picture takes its id out of the media_ids of every DRAFT post, so a draft is never left pointing at a picture
--      that is gone (media_ids is an array, so no foreign key does this). An approved, scheduled or posted post is not touched:
--      the gate refuses the delete before this runs.
-- Safe to re-run.

drop policy if exists "media: owner can delete" on public.media_generations;
create policy "media: owner can delete"
  on public.media_generations for delete
  to authenticated
  using ((created_by = auth.uid() or created_by is null) and public.semasa_is_uploader());

create or replace function public.semasa_media_unlink_drafts() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  update public.semasa_posts set media_ids = array_remove(media_ids, old.id)
   where status = 'draft' and old.id = any(media_ids);
  return old;
end $$;
drop trigger if exists semasa_media_unlink_drafts on public.media_generations;
create trigger semasa_media_unlink_drafts after delete on public.media_generations
  for each row execute function public.semasa_media_unlink_drafts();
revoke execute on function public.semasa_media_unlink_drafts() from public, anon, authenticated;
notify pgrst, 'reload schema';
