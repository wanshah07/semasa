-- Semasa · Module A · schema
-- Run in the Supabase SQL editor (or `supabase db push`). Idempotent.
--
-- SAFE IN A SHARED PROJECT: every object this file creates is named for Semasa
-- (isu_semasa_trends, media_generations, scrape_runs, semasa_*), so it can live
-- beside another app's tables and functions without replacing any of them.

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- isu_semasa_trends — one row per headline the scraper has seen.
-- `url` is the identity: the scraper upserts on it, so a headline that appears
-- in two feeds is one row and a re-run inserts nothing twice.
-- ---------------------------------------------------------------------------
create table if not exists public.isu_semasa_trends (
  id             uuid primary key default gen_random_uuid(),
  title          text        not null,
  source         text        not null,                 -- publisher, e.g. "Berita Harian"
  url            text        not null unique,
  summary        text,                                 -- 1–2 sentences, BM or EN as the source
  category       text        not null default 'lain',  -- see CHECK below
  lang           text        not null default 'ms',    -- 'ms' | 'en'
  summary_source text        not null default 'none',  -- 'llm' | 'rules' | 'none'  (rule: a rules-only
                                                       -- verdict must never read like a reviewed one)
  published_at   timestamptz,                          -- the feed's own date, if it gave one
  scraped_at     timestamptz not null default now(),
  created_at     timestamptz not null default now(),
  tags           text[]      not null default '{}',
  raw            jsonb       not null default '{}'::jsonb,
  constraint isu_semasa_trends_category_check check (category in (
    'kosmetik','halal','makanan','farmaseutikal','kesihatan','ekonomi','politik',
    'jenayah','sosial','teknologi','hiburan','sukan','pendidikan','alam_sekitar','lain'
  )),
  constraint isu_semasa_trends_lang_check check (lang in ('ms','en')),
  constraint isu_semasa_trends_summary_source_check check (summary_source in ('llm','rules','none'))
);

create index if not exists isu_semasa_trends_created_at_idx on public.isu_semasa_trends (created_at desc);
create index if not exists isu_semasa_trends_category_idx   on public.isu_semasa_trends (category, created_at desc);
create index if not exists isu_semasa_trends_source_idx     on public.isu_semasa_trends (source);
create index if not exists isu_semasa_trends_title_trgm_idx on public.isu_semasa_trends using gin (to_tsvector('simple', title));

-- ---------------------------------------------------------------------------
-- media_generations — one row per job. The UI inserts `pending`; the runner
-- moves it processing → done | error and writes the generated address back.
-- ---------------------------------------------------------------------------
create table if not exists public.media_generations (
  id                  uuid primary key default gen_random_uuid(),
  reference_url       text        not null,             -- public URL of the uploaded reference
  reference_path      text,                             -- storage path inside bucket `reference`
  generated_media_url text,                             -- public URL inside bucket `generated`
  type                text        not null default 'image',
  status              text        not null default 'pending',
  prompt              text        not null default '',
  provider            text,                             -- 'replicate' | 'openai' (null = runner default)
  model               text,                             -- filled by the runner with what actually ran
  error               text,
  attempts            int         not null default 0,
  created_by          uuid        references auth.users (id) on delete set null,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  meta                jsonb       not null default '{}'::jsonb,  -- sha256, bytes, duration, provider ids
  constraint media_generations_type_check   check (type in ('image','video')),
  constraint media_generations_status_check check (status in ('pending','processing','done','error'))
);

create index if not exists media_generations_status_idx     on public.media_generations (status, created_at);
create index if not exists media_generations_created_at_idx on public.media_generations (created_at desc);

-- ---------------------------------------------------------------------------
-- scrape_runs — one row per scraper run. This is how a dead source or a dead
-- LLM endpoint becomes VISIBLE instead of silently producing zero.
-- ---------------------------------------------------------------------------
create table if not exists public.scrape_runs (
  id           uuid primary key default gen_random_uuid(),
  started_at   timestamptz not null default now(),
  finished_at  timestamptz,
  sources      jsonb not null default '[]'::jsonb,  -- [{name, kind, ok, items, error}]
  seen         int   not null default 0,
  inserted     int   not null default 0,
  llm_ok       boolean,
  llm_model    text,
  git_sha      text,
  note         text
);

-- Who may upload. The project may be shared with another app whose users can
-- sign in too; only the user ids listed here can queue a (paid) generation job
-- or add a headline. Add yourself once, after your first sign-in:
--   insert into public.semasa_uploaders (user_id, note)
--   select id, email from auth.users where email = 'you@example.com';
create table if not exists public.semasa_uploaders (
  user_id  uuid primary key references auth.users (id) on delete cascade,
  note     text,
  added_at timestamptz not null default now()
);

create or replace function public.semasa_is_uploader() returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.semasa_uploaders where user_id = auth.uid())
$$;

-- updated_at maintenance
create or replace function public.semasa_set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

drop trigger if exists media_generations_set_updated_at on public.media_generations;
create trigger media_generations_set_updated_at
  before update on public.media_generations
  for each row execute function public.semasa_set_updated_at();

-- Realtime for the gallery (status flips pending → done live in the page)
do $$
begin
  if not exists (
    select 1 from pg_publication_tables
    where pubname = 'supabase_realtime' and tablename = 'media_generations'
  ) then
    alter publication supabase_realtime add table public.media_generations;
  end if;
end $$;
