-- Semasa · Expert content (Wan, 14 Nov 2026: "add another segment Expert Content, under it put AI Expert, Halal Expert").
-- Run ONCE in the SQL editor, after 081. Idempotent: safe to run again, and it never overwrites handles already saved.
--
-- What it does
--   1. semasa_watch takes one more section, expert: the posts of the accounts Wan registers in the Expert content page, read by
--      backend/semasa/experts.py (a part of the Sources sweep). Each row keeps the post's own words (raw.original) beside the
--      bot's summary, and the category it belongs to (raw.category).
--   2. Two settings rows:
--        experts              the page's own: categories (AI Expert, Halal Expert, more later), their handles with the platforms
--                             ticked for each, the niche and search words, and the "send to AI brain" switch (on for AI Expert
--                             only). Only the page writes it.
--        expert_suggestions   the sweep's own: accounts worth following, found by searching Threads for a category's words and
--                             judged on the posts actually read. Only the sweep writes it.
--      The page can only UPDATE a settings row, so both must exist before it can save.
-- Until this is run the sweep reads and analyses the posts but cannot store a row, and says so in its report and its light.
-- Nothing here posts, approves or drafts: feed rows and settings only.

alter table public.semasa_watch drop constraint if exists semasa_watch_section_check;
alter table public.semasa_watch add constraint semasa_watch_section_check
  check (section in ('regulatory', 'publication', 'reddit', 'youtube', 'threads', 'facebook', 'instagram', 'folder', 'myra',
                     'expert'));

insert into public.semasa_settings (key, value) values ('experts', '{
  "enabled": true, "hours": 336, "per_handle": 5,
  "categories": [
    {"id": "ai", "name": "AI Expert", "brain": true, "handles": [], "dismissed": [],
     "niche": "artificial intelligence in practice: AI tools, large language models, agents, prompting, automation",
     "keywords": ["AI agent", "prompt engineering", "LLM"]},
    {"id": "halal", "name": "Halal Expert", "brain": false, "handles": [], "dismissed": [],
     "niche": "halal certification and compliance in Malaysia: JAKIM, MPPHM, MS 1500, halal assurance, ingredients",
     "keywords": ["sijil halal", "halal JAKIM", "pensijilan halal"]}
  ]}'::jsonb)
on conflict (key) do nothing;

insert into public.semasa_settings (key, value) values ('expert_suggestions', '{"at": null, "lists": {}}'::jsonb)
on conflict (key) do nothing;

-- Check (should print 1 and 2):
select (select count(*) from pg_constraint where conname = 'semasa_watch_section_check'
          and pg_get_constraintdef(oid) like '%expert%') as section_ok,
       (select count(*) from public.semasa_settings where key in ('experts', 'expert_suggestions')) as settings_rows;
