-- Semasa · FAQ · run ONCE in the SQL editor after 001–006. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): it creates only semasa_faqs, two semasa_settings rows, one
-- semasa_* function and one trigger. No other app's table, policy or function is read or changed.
--
-- A FAQ entry arrives three ways, and all three become the same row:
--   paste      Wan pastes a question (and an answer, if there is one) in the FAQ tab
--   headline   "Jadikan FAQ" on a scraped headline: the worker reads the article
--   auto       the scraper collects Q&A-shaped items (JAKIM Isu-Isu Tular Halal, Reddit) as
--              CANDIDATES; nothing is rewritten until Wan accepts one
-- The worker (media.yml) rewrites it into Malay and English, anonymises it, picks a category, and
-- marks it `ready`. Wan chose on 25 Sep 2026 to publish the rewrite as is: `needs_check` is a
-- warning shown on the entry, never a gate.
--
-- status:  candidate → new → working → ready | error;  dismissed (a candidate Wan skipped)

create table if not exists public.semasa_faqs (
  id             uuid primary key default gen_random_uuid(),
  status         text        not null default 'new',
  source_kind    text        not null default 'paste',     -- paste | headline | auto
  source_key     text,                                    -- dedupe key for auto candidates
  source_name    text,                                    -- e.g. "JAKIM · Isu-Isu Tular Halal" (internal)
  source_url     text,
  trend_id       uuid        references public.isu_semasa_trends (id) on delete set null,
  raw_question   text        not null default '',
  raw_answer     text        not null default '',
  question_bm    text        not null default '',
  answer_bm      text        not null default '',
  question_en    text        not null default '',
  answer_en      text        not null default '',
  category       text        not null default 'lain',
  subcategory    text        not null default '',
  tags           text[]      not null default '{}',
  instrument     text        not null default '',          -- the regulator/instrument named in the input
  answer_source  text        not null default 'given',     -- given | ai (no answer was supplied)
  needs_check    boolean     not null default false,
  check_note     text        not null default '',
  error          text,
  attempts       int         not null default 0,
  category_by    text        not null default 'bot',       -- bot | wan: Wan's own choice survives rewrites and sorting
  sorted_at      timestamptz,                             -- when the sorter last looked (semasa/faq_sort.py)
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_faqs_status_check check (status in ('candidate', 'new', 'working', 'ready', 'error', 'dismissed')),
  constraint semasa_faqs_kind_check   check (source_kind in ('paste', 'headline', 'auto')),
  constraint semasa_faqs_answer_check check (answer_source in ('given', 'ai'))
);
-- added after the first version of this file: safe to run again on a table made by it
alter table public.semasa_faqs add column if not exists category_by text not null default 'bot';
alter table public.semasa_faqs add column if not exists sorted_at timestamptz;
alter table public.semasa_faqs drop constraint if exists semasa_faqs_by_check;
alter table public.semasa_faqs add constraint semasa_faqs_by_check check (category_by in ('bot', 'wan'));
-- plain (not partial) so PostgREST upserts can name it; NULL keys stay distinct, so pastes never collide
create unique index if not exists semasa_faqs_source_key_uidx on public.semasa_faqs (source_key);
create index if not exists semasa_faqs_status_idx on public.semasa_faqs (status, category);

drop trigger if exists semasa_faqs_set_updated_at on public.semasa_faqs;
create trigger semasa_faqs_set_updated_at before update on public.semasa_faqs
  for each row execute function public.semasa_set_updated_at();

-- the category list lives here (Tetapan edits it); empty = the defaults in rules/faq_categories.json
insert into public.semasa_settings (key, value) values ('faq', '{}'::jsonb) on conflict (key) do nothing;

-- Wan's tabung of Indonesian words to avoid (Tetapan → Tabung perkataan Indonesia): every writer is
-- told, and the compliance scan blocks them, on top of the built-in list in rules/compliance.json
insert into public.semasa_settings (key, value) values ('bahasa', '{"indo": []}'::jsonb) on conflict (key) do nothing;

-- A new FAQ wakes the worker at once when the Vault token exists (004); the 15-minute poll is the net.
create or replace function public.semasa_notify_faq_new() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'media_pending',
                                  'client_payload', jsonb_build_object('faq_id', new.id))
  );
  return new;
end $$;

drop trigger if exists semasa_faqs_notify_new on public.semasa_faqs;
create trigger semasa_faqs_notify_new
  after insert or update of status on public.semasa_faqs
  for each row when (new.status = 'new')
  execute function public.semasa_notify_faq_new();

-- Row Level Security: private to listed uploaders, like ideas and posts.
alter table public.semasa_faqs enable row level security;
drop policy if exists "semasa faqs: uploaders read" on public.semasa_faqs;
create policy "semasa faqs: uploaders read" on public.semasa_faqs
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa faqs: uploaders insert" on public.semasa_faqs;
create policy "semasa faqs: uploaders insert" on public.semasa_faqs
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid() and status = 'new');
-- the page may queue, accept, dismiss or edit; `working`, `error` and `candidate` are the worker's
drop policy if exists "semasa faqs: uploaders update" on public.semasa_faqs;
create policy "semasa faqs: uploaders update" on public.semasa_faqs
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('new', 'ready', 'dismissed'));
drop policy if exists "semasa faqs: uploaders delete" on public.semasa_faqs;
create policy "semasa faqs: uploaders delete" on public.semasa_faqs
  for delete to authenticated using (public.semasa_is_uploader());

do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'semasa_faqs') then
    alter publication supabase_realtime add table public.semasa_faqs;
  end if;
end $$;

-- Check (should print 1 | 2): the table, and the two settings rows
--   select (select count(*) from information_schema.tables where table_name = 'semasa_faqs'),
--          (select count(*) from public.semasa_settings where key in ('faq', 'bahasa'));
