-- Semasa · add Facebook and Instagram to Wan's own sources (079 added Threads; this widens the same check by two more sections).
-- Run ONCE in the SQL editor, after 079. Idempotent: safe to run again.
--
-- What it does
--   semasa_watch takes two more community sections, facebook and instagram. The page shows each as a tab in the Isu semasa row, fed
--   by backend/semasa/social_web.py: a browser reads the public hashtag pages (Facebook) or, with a saved login, the hashtag pages
--   and posts (Instagram). Until this is run the sweep reads and judges the posts but cannot store a row, and says so in its report.
-- Nothing here posts, approves or drafts: it writes feed rows only, exactly like the other community sections.

alter table public.semasa_watch drop constraint if exists semasa_watch_section_check;
alter table public.semasa_watch add constraint semasa_watch_section_check
  check (section in ('regulatory', 'publication', 'reddit', 'youtube', 'threads', 'facebook', 'instagram', 'folder', 'myra'));

-- Check (should print 1):
select (select count(*) from pg_constraint where conname = 'semasa_watch_section_check'
          and pg_get_constraintdef(oid) like '%facebook%' and pg_get_constraintdef(oid) like '%instagram%') as sections;
