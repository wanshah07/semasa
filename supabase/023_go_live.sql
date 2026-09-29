-- Semasa · go live (Wan, 29 Sep 2026: "we will start using semasa this friday and will delete ws.regulab studio
-- permanently ... make sure semasa 100% functioning without wait my approval on friday night 2 oct").
--
-- Run ONCE in the SQL editor, any time before Friday 2 Oct 2026 19:45 MYT, after 001–022. Safe to run again.
-- SAFE IN A SHARED PROJECT (KPI): touches only semasa_settings and semasa_publish_log's action list.
--
-- What it does
--   1. The publishing switch OPENS BY ITSELF on Friday 2 Oct 2026 at 20:00 MYT (12:00 UTC). Nobody needs to be at a
--      keyboard that night. Before that moment the publisher stays a dry run, exactly as today.
--      By then Studio's Routines are switched off (19:45 MYT) and Studio's queue has been copied in, so there is never
--      a moment with two publishers on one Buffer account.
--      To stop it at any time:  update public.semasa_settings set value = value || '{"paused": true}' where key = 'publishing';
--   2. Where posts go: the Buffer organization and the three ws.regulab channels (Facebook, Instagram, Threads), and
--      the LinkedIn profile that Composio posts as. The keys themselves are GitHub secrets, never here:
--      BUFFER_API_KEY and COMPOSIO_API_KEY.
--   3. Auto-fill (writing ideas for empty slots) opens at the same moment, because Studio's nightly drafter stops then.
--      Everything it writes is a draft: your Approve click is still the only way a post goes out.
--   4. The publish log learns the words the live publisher writes (scheduled, sent, wait, adopted, sending, confirmed).
begin;

-- 1. the switch
update public.semasa_settings
   set value = coalesce(value, '{}'::jsonb)
             || jsonb_build_object(
                  'enabled_from', '2026-10-02T12:00:00Z',
                  'why', 'Opens by itself on Fri 2 Oct 2026 20:00 MYT, after ws.regulab Studio''s Routines are switched off '
                         || 'and its queue is copied in. To stop it: set "paused": true in the SQL editor.'),
       updated_at = now()
 where key = 'publishing';

-- 2. where posts go (the same ids Studio used: its settings/channels, read 29 Sep 2026)
insert into public.semasa_settings (key, value) values ('channels', '{}'::jsonb) on conflict (key) do nothing;
update public.semasa_settings
   set value = value || jsonb_build_object(
         'buffer', jsonb_build_object(
            'organizationId', '6a95af5215d5d6e8f5b223f5',
            'facebook',  '6a99932c065799be467f22d2',
            'instagram', '6a999175065799be467f1985',
            'threads',   '6a95afe0065799be465f15cb',
            'enabled', jsonb_build_object('facebook', true, 'instagram', true, 'threads', true)),
         'linkedin', jsonb_build_object(
            'author', 'urn:li:person:z1rfeC-Z85',
            'name', 'Ts. Muhammad Ridzuan')),
       updated_at = now()
 where key = 'channels';

-- 3. auto-fill opens with the switch
insert into public.semasa_settings (key, value)
values ('autofill', '{"enabled": false, "days_ahead": 3, "per_run": 2, "streams": ["regulab","linkedin"]}'::jsonb)
on conflict (key) do nothing;
update public.semasa_settings
   set value = value || '{"enabled_from": "2026-10-02T12:00:00Z"}'::jsonb, updated_at = now()
 where key = 'autofill';

-- 4. the log's words
alter table public.semasa_publish_log drop constraint if exists semasa_publish_log_action_check;
alter table public.semasa_publish_log add constraint semasa_publish_log_action_check
  check (action in ('dry_run', 'sent', 'error', 'blocked', 'scheduled', 'wait', 'adopted', 'sending', 'confirmed'));

commit;

-- Check (should print: 2026-10-02T12:00:00Z | 6a95af5215d5d6e8f5b223f5 | urn:li:person:z1rfeC-Z85 | 2026-10-02T12:00:00Z | 1):
select (select value->>'enabled_from' from public.semasa_settings where key = 'publishing') as opens,
       (select value->'buffer'->>'organizationId' from public.semasa_settings where key = 'channels') as buffer_org,
       (select value->'linkedin'->>'author' from public.semasa_settings where key = 'channels') as linkedin,
       (select value->>'enabled_from' from public.semasa_settings where key = 'autofill') as autofill_opens,
       (select count(*) from pg_constraint where conname = 'semasa_publish_log_action_check'
          and pg_get_constraintdef(oid) like '%confirmed%') as log_words;
