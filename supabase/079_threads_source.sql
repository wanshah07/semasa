-- Semasa · add Threads to Wan's own sources (supabase/024 brought Reddit + YouTube; this widens the same check
-- constraint by one more section). Run ONCE in the SQL editor, after 024. Idempotent: safe to run again.
--
-- What it does
--   semasa_watch takes a fifth community section beside reddit and youtube: threads. The page shows it as a tab in the
--   Isu semasa row (Threads), fed by backend/semasa/community.py through Composio For You (THREADS_SEARCH_POSTS).
--   Until this is run the sweep reads and judges Threads posts but cannot store a row, and says so in its report.
-- Nothing here posts, approves or drafts: it writes feed rows only, exactly like the other community sections.

alter table public.semasa_watch drop constraint if exists semasa_watch_section_check;
alter table public.semasa_watch add constraint semasa_watch_section_check
  check (section in ('regulatory', 'publication', 'reddit', 'youtube', 'threads', 'folder', 'myra'));

-- Check (should print 1):
select (select count(*) from pg_constraint where conname = 'semasa_watch_section_check'
          and pg_get_constraintdef(oid) like '%threads%') as sections;
