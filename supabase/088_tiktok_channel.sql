-- Semasa · TikTok as a platform a post can be queued to (Wan, 20 Nov 2026: TikTok only when he asks, a yes or no on each post).
-- Run ONCE in the SQL editor, after 087. Idempotent: safe to run again.
--
-- `semasa_posts.channels` lists the platforms a post goes to (051). It was limited to facebook, instagram, threads and linkedin, so a
-- post could not say "and TikTok". The publisher (backend/semasa/publisher.post_channels) now sends a ws.regulab film to TikTok only when
-- "tiktok" is in that list, or the post already holds a TikTok record. Nothing else changes: a post with no choice (channels null) still
-- means every platform of its stream, and TikTok is not one of them.
--
-- Additive: no row is touched, no function changes (semasa_queue_motion passes p_channels straight into this column).
alter table public.semasa_posts drop constraint if exists semasa_posts_channels_check;
alter table public.semasa_posts add constraint semasa_posts_channels_check
  check (channels is null or channels <@ array['facebook', 'instagram', 'threads', 'linkedin', 'tiktok']::text[]);

notify pgrst, 'reload schema';

-- Check (should print the list with tiktok in it):
select pg_get_constraintdef(oid) from pg_constraint where conrelid = 'public.semasa_posts'::regclass and conname = 'semasa_posts_channels_check';
-- To undo (only while no post lists tiktok):
--   alter table public.semasa_posts drop constraint semasa_posts_channels_check;
--   alter table public.semasa_posts add constraint semasa_posts_channels_check
--     check (channels is null or channels <@ array['facebook','instagram','threads','linkedin']::text[]);
