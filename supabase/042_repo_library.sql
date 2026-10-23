-- 042 · Pustaka repo: a library of repositories Wan adds by link, each read, checked for safety, summarised and filed
-- under a category by the AI (Wan, 23 Oct 2026: "add REPO segment, I will add repo link and AI will analyze and ensure it
-- safe and make summary and categorize, for example motion repo in motion category, so for AI brain make it separately").
--
-- This is NOT the repo tracker (semasa_repos, 035: the office repositories in six dimensions) and NOT Otak AI (036): it is
-- its own table and its own worker (backend/semasa/repo_library.py, .github/workflows/repo-library.yml).
--
-- Flow: the page inserts a row with url + status 'pending' → the database wakes the worker (repository_dispatch
-- 'repo_pending', the same Vault token 036 uses) → the worker reads GitHub (metadata, README, root files, manifests,
-- workflows), runs the static safety checks, asks the AI for a summary, category, tags and a safety verdict, and writes the
-- row 'done'. Nothing is cloned or executed: the check is a reading, never a run. The daily schedule re-reads a repo whose
-- last push moved, so a summary follows the repo.
--
-- status: pending → working → done | error.   safety: unknown | safe | caution | avoid.   category_by: bot | wan.
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, one trigger function, one settings row. Run once; re-running changes nothing.

create table if not exists public.semasa_repo_library (
  id             uuid primary key default gen_random_uuid(),
  url            text        not null,
  full_name      text        not null default '',                      -- owner/name, as GitHub spells it
  status         text        not null default 'pending',
  note           text        not null default '',                      -- Wan's own words when adding it
  name           text        not null default '',
  description    text        not null default '',
  html_url       text        not null default '',
  default_branch text        not null default '',
  language       text        not null default '',
  languages      jsonb       not null default '{}'::jsonb,
  license        text        not null default '',
  topics         text[]      not null default '{}',
  stars          int         not null default 0,
  forks          int         not null default 0,
  archived       boolean     not null default false,
  pushed_at      timestamptz,
  last_sha       text        not null default '',                      -- the commit the summary was written from
  files          jsonb       not null default '[]'::jsonb,             -- root listing [{path, type, size}]
  readme_excerpt text        not null default '',
  category       text        not null default 'lain',
  category_by    text        not null default 'bot',
  tags           text[]      not null default '{}',
  summary_bm     text        not null default '',
  summary_en     text        not null default '',
  use_for        text        not null default '',                      -- what Semasa / Wan could use it for
  how_to_run     text        not null default '',                      -- install + run, as the README says
  safety         text        not null default 'unknown',
  safety_flags   jsonb       not null default '[]'::jsonb,             -- [{code, where, detail}] from the static checks and the AI
  model          text        not null default '',
  attempts       int         not null default 0,
  error          text        not null default '',
  checked_at     timestamptz,
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_repo_library_status_check check (status in ('pending', 'working', 'done', 'error')),
  constraint semasa_repo_library_safety_check check (safety in ('unknown', 'safe', 'caution', 'avoid')),
  constraint semasa_repo_library_by_check     check (category_by in ('bot', 'wan'))
);
create unique index if not exists semasa_repo_library_url_uidx on public.semasa_repo_library (lower(url));
create index if not exists semasa_repo_library_status_idx on public.semasa_repo_library (status, created_at);
create index if not exists semasa_repo_library_category_idx on public.semasa_repo_library (category);

drop trigger if exists semasa_repo_library_set_updated_at on public.semasa_repo_library;
create trigger semasa_repo_library_set_updated_at before update on public.semasa_repo_library
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_repo_library enable row level security;
drop policy if exists "semasa repo library: uploaders read" on public.semasa_repo_library;
create policy "semasa repo library: uploaders read" on public.semasa_repo_library
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa repo library: uploaders insert" on public.semasa_repo_library;
create policy "semasa repo library: uploaders insert" on public.semasa_repo_library
  for insert to authenticated with check (public.semasa_is_uploader());
drop policy if exists "semasa repo library: uploaders update" on public.semasa_repo_library;
create policy "semasa repo library: uploaders update" on public.semasa_repo_library
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa repo library: uploaders delete" on public.semasa_repo_library;
create policy "semasa repo library: uploaders delete" on public.semasa_repo_library
  for delete to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_repo_library from anon;
grant select, insert, update, delete on public.semasa_repo_library to authenticated;

-- the database wakes the worker on a new pending row (and on "Semak semula", which sets pending again)
create or replace function public.semasa_notify_repo_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the repo library worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'repo_pending', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_repo_library_notify on public.semasa_repo_library;
create trigger semasa_repo_library_notify after insert or update of status on public.semasa_repo_library
  for each row when (new.status = 'pending') execute function public.semasa_notify_repo_pending();

-- the categories the page offers and the worker files under (Tetapan may edit the list later)
insert into public.semasa_settings (key, value) values ('repo_library', jsonb_build_object(
  'categories', jsonb_build_array('motion', 'video', 'suara', 'imej', 'kemahiran-ai', 'scraper', 'regulatori', 'web', 'data',
                                  'automasi', 'alatan', 'lain')
)) on conflict (key) do nothing;
