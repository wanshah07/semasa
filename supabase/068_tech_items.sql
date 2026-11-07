-- 068 · Technology list: the APIs, SDKs, CLIs and services Wan registers himself (Wan, 11 Oct 2026, Phase 4: "repo registration,
-- repo library dengan URL, API library dan model dia, satu senarai semua API/SDK/CLI").
--
-- The Senarai teknologi page draws ONE list. Most of it is read from what is already true: the APIs each worker holds a key for
-- and the CLIs the workflows run (web/src/lib/stack.js, checked against .github/workflows and backend/requirements.txt by
-- stack.test.mjs), the SDKs in web/package.json and backend/requirements.txt, the AI gateways the probe reads with their models
-- (semasa_api_status), the office repos (semasa_repos) and the repo library (semasa_repo_library). This table holds only what
-- Wan adds by hand: an API Semasa does not call yet, a tool on his own machine, a service with its models and its docs.
--
-- A secret's NAME may be noted (env_key, e.g. "OPENAI_API_KEY"), never its value: the column takes an upper-case name only.
-- Safe to re-run.

create table if not exists public.semasa_tech_items (
  id          uuid primary key default gen_random_uuid(),
  kind        text not null check (kind in ('api', 'sdk', 'cli', 'service')),
  name        text not null check (length(btrim(name)) between 1 and 80),
  url         text not null default '' check (url = '' or url ~ '^https?://'),
  docs_url    text not null default '' check (docs_url = '' or docs_url ~ '^https?://'),
  models      text[] not null default '{}' check (coalesce(array_length(models, 1), 0) <= 100),
  env_key     text not null default '' check (env_key = '' or env_key ~ '^[A-Z][A-Z0-9_]{1,63}$'),
  used_for    text not null default '' check (length(used_for) <= 300),
  status      text not null default 'active' check (status in ('active', 'trial', 'retired')),
  notes       text not null default '' check (length(notes) <= 1000),
  created_by  uuid references auth.users (id) on delete set null default auth.uid(),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create unique index if not exists semasa_tech_items_kind_name on public.semasa_tech_items (kind, lower(name));

alter table public.semasa_tech_items enable row level security;

drop policy if exists "semasa tech items: uploaders read" on public.semasa_tech_items;
create policy "semasa tech items: uploaders read" on public.semasa_tech_items
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa tech items: uploaders add" on public.semasa_tech_items;
create policy "semasa tech items: uploaders add" on public.semasa_tech_items
  for insert to authenticated with check (public.semasa_is_uploader() and created_by = auth.uid());
drop policy if exists "semasa tech items: uploaders edit" on public.semasa_tech_items;
create policy "semasa tech items: uploaders edit" on public.semasa_tech_items
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa tech items: uploaders delete" on public.semasa_tech_items;
create policy "semasa tech items: uploaders delete" on public.semasa_tech_items
  for delete to authenticated using (public.semasa_is_uploader());

revoke all on public.semasa_tech_items from anon;
grant select, insert, update, delete on public.semasa_tech_items to authenticated;

drop trigger if exists semasa_tech_items_set_updated_at on public.semasa_tech_items;
create trigger semasa_tech_items_set_updated_at before update on public.semasa_tech_items
  for each row execute function public.semasa_set_updated_at();

notify pgrst, 'reload schema';
