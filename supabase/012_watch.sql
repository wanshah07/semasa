-- Semasa · Regulatory and Latest publication: two segments beside Isu Semasa, swept once every 24 hours.
-- Run ONCE in the SQL editor, after 001–011. Idempotent: safe to run again.
--
-- Wan, 26 Sep 2026: "add segment like current issue for regulatory and latest publication - do the same mechanism like
-- current issue but for these segments run every 24 hours - can add as post and idea".
--
-- SAFE IN A SHARED PROJECT (KPI): it creates one table (semasa_watch), one semasa_settings row ('watch') and one
-- semasa_* trigger function on semasa_settings. No other app's table, policy or function is read or changed.
--
-- The worker writes the rows (backend/semasa/watch.py): the regulators' own list pages (NPRA, Portal Halal Malaysia,
-- HSA, EU SCCS, UK OPSS, China NMPA) and PubMed's newest papers, each with a Malay summary, a domain, a line on why it
-- matters and a "relevant" verdict. The page reads them, may hide one, and turns one into an idea.

create table if not exists public.semasa_watch (
  id             uuid primary key default gen_random_uuid(),
  section        text        not null,                   -- regulatory | publication
  source         text        not null default '',        -- NPRA, HSA Singapore, PubMed · <journal>, ...
  kind           text,                                   -- Kenyataan Media KKM, Safety alert, SCCS opinion, Paper, ...
  country        text,                                   -- MY, SG, EU, UK, CN (empty for papers)
  title          text        not null,
  url            text        not null unique,
  summary        text,
  why            text,                                   -- why it matters to a Malaysian business
  domain         text,
  relevant       boolean     not null default true,      -- the writer's verdict; the page hides false by default
  dismissed      boolean     not null default false,     -- Wan hid it
  lang           text        not null default 'en',
  summary_source text        not null default 'none',    -- llm | source | none
  published_at   timestamptz,
  raw            jsonb       not null default '{}'::jsonb, -- a paper's DOI, journal, authors; an opinion's reference
  created_at     timestamptz not null default now(),
  constraint semasa_watch_section_check check (section in ('regulatory', 'publication'))
);
create index if not exists semasa_watch_section_idx on public.semasa_watch (section, published_at desc);

alter table public.semasa_watch enable row level security;
drop policy if exists "semasa watch: uploaders read" on public.semasa_watch;
create policy "semasa watch: uploaders read" on public.semasa_watch
  for select to authenticated using (public.semasa_is_uploader());
-- the page may only hide or show an item; the worker (service role) writes everything else
drop policy if exists "semasa watch: uploaders hide" on public.semasa_watch;
create policy "semasa watch: uploaders hide" on public.semasa_watch
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
revoke update on public.semasa_watch from authenticated;
grant select on public.semasa_watch to authenticated;
grant update (dismissed) on public.semasa_watch to authenticated;

-- the sweep's own row: when it last ran, the page's "sweep now", and the last report
insert into public.semasa_settings (key, value) values ('watch', '{}'::jsonb) on conflict (key) do nothing;

-- "Sweep now" in the page wakes the worker at once (a person's save only; the worker's own writes do not wake it)
create or replace function public.semasa_watch_force() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.key = 'watch' and auth.uid() is not null and coalesce((new.value ->> 'force')::boolean, false)
     and not coalesce((old.value ->> 'force')::boolean, false) then
    perform public.semasa_clock_dispatch('media_pending');
  end if;
  return new;
exception when others then
  raise warning 'semasa_watch_force: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_watch_force on public.semasa_settings;
create trigger semasa_watch_force after update on public.semasa_settings
  for each row execute function public.semasa_watch_force();
revoke execute on function public.semasa_watch_force() from public, anon, authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from information_schema.tables where table_name = 'semasa_watch'),
--          (select count(*) from public.semasa_settings where key = 'watch'),
--          (select count(*) from pg_trigger where tgname = 'semasa_watch_force');
