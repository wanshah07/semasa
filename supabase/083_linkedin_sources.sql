-- Semasa · Wan's own websites and LinkedIn posts as sources for LinkedIn ideas (Wan, 16 Nov 2026: "add segment in linkedn that
-- I can add url website to scrape such as https://lom.agc.gov.my/index.php" and "for linkedn ... scrape also from linkedns
-- based on recent case, and big impression").
-- Run ONCE in the SQL editor, after 082. Idempotent: safe to run again.
--
-- What it does
--   semasa_watch takes two more sections:
--     website   what a page Wan listed newly shows (backend/semasa/own_links.py, a part of the Sources sweep);
--     linkedin  LinkedIn posts he pasted, and the loud recent posts of company pages he listed (the same module).
--   The lists themselves live in the settings row `sources` (websites.sites, linkedin.posts, linkedin.pages), which the page
--   already saves. What each website has already shown is remembered in a row of its own, `sources_seen`, written by the sweep.
-- Until this is run the sweep reads the pages but cannot store a row, and says so in its report.
-- Nothing here posts, approves or drafts: feed rows and one settings row only.

alter table public.semasa_watch drop constraint if exists semasa_watch_section_check;
alter table public.semasa_watch add constraint semasa_watch_section_check
  check (section in ('regulatory', 'publication', 'reddit', 'youtube', 'threads', 'facebook', 'instagram', 'folder', 'myra',
                     'expert', 'website', 'linkedin'));

insert into public.semasa_settings (key, value) values ('sources_seen', '{}'::jsonb)
on conflict (key) do nothing;

-- Check (should print 1 and 1):
select (select count(*) from pg_constraint where conname = 'semasa_watch_section_check'
          and pg_get_constraintdef(oid) like '%linkedin%' and pg_get_constraintdef(oid) like '%website%') as section_ok,
       (select count(*) from public.semasa_settings where key = 'sources_seen') as seen_row;
