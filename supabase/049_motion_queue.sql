-- Motion queue (Wan, 26 Oct 2026: "when I click Idea to be motion video, it will queue to motion video for me to choose styles").
-- An idea or a draft made into a video now lands as 'waiting': the worker ignores it (it only claims 'pending'), and the Motion
-- tab shows it with the style choices; "Mula" sets it 'pending' and the database wakes the worker as before.
-- Safe to re-run. 046 and 047 each rewrite semasa_motions constraints: this one keeps every earlier status and adds 'waiting'.
-- 'review' is 071's (a storyboard waiting for approval); it is listed here too so re-running this file never drops it.
alter table public.semasa_motions drop constraint if exists semasa_motions_status_check;
alter table public.semasa_motions add constraint semasa_motions_status_check
  check (status in ('waiting', 'pending', 'working', 'review', 'done', 'error'));
notify pgrst, 'reload schema';
