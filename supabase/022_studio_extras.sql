-- Semasa · Wan's own picture into a post, and the switch for filling empty slots (Studio features, 27 Sep 2026).
-- Run ONCE in the SQL editor, after 021. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): one check constraint on media_generations (Semasa's table) is widened by one mode,
-- and one Semasa settings row is seeded. Nothing else is read or changed.
--
-- 1. own picture
-- The page puts the file in semasa-reference and queues a job of mode 'upload' on the post; the worker checks it is a
-- picture, makes it a clean JPEG, hosts it in semasa-generated (an address that never expires), attaches it to the
-- draft and removes the temporary copy (backend/semasa/own_picture.py). An upload always carries its file, like a
-- recreate. Every file that defines this constraint (005, 006, 011, 014, 017, 022) carries the same list, so re-running
-- an older file never drops a mode a later one added.

alter table public.media_generations drop constraint if exists media_generations_mode_check;
alter table public.media_generations add constraint media_generations_mode_check
  check (mode in ('recreate', 'prompt', 'slides', 'clip', 'fragrance', 'upload') and (mode not in ('recreate', 'upload') or reference_url is not null));

-- 2. autofill: Studio's nightly drafter as a switch, OFF. Switched on in Settings, each worker run writes ideas for
--    the empty slots of the next few days from the Regulatory and Latest publication feed, rota-true, drafts only
--    (backend/semasa/autofill.py). Off, nothing is written without Wan's click, as before. A row already there is kept.
insert into public.semasa_settings (key, value)
  values ('autofill', '{"enabled": false, "days_ahead": 3, "per_run": 2, "streams": ["regulab", "linkedin"]}'::jsonb)
  on conflict (key) do nothing;

-- Check (should print 1 | 1):
--   select (select count(*) from pg_constraint where conname = 'media_generations_mode_check'
--             and pg_get_constraintdef(oid) like '%upload%'),
--          (select count(*) from public.semasa_settings where key = 'autofill' and value->>'enabled' = 'false');
