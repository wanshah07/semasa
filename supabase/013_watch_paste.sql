-- Semasa · Paste a link into Regulatory or Latest publication, and the worker reads it like a swept item.
-- Run ONCE in the SQL editor, after 001–012. Idempotent: safe to run again.
--
-- Wan, 26 Sep 2026: "for regulatory and latest publication, allow us to paste the link as well".
--
-- SAFE IN A SHARED PROJECT (KPI): it adds columns to semasa_watch, two policies and one trigger on it, and replaces
-- semasa_clock_worker() with 011's version plus the pasted links. No other app's table, policy or function is touched.
--
-- The flow: the page inserts a row (the link, the segment, optionally a name) with status 'pending'; the insert wakes
-- the worker; the worker reads the link (a PubMed link or DOI through PubMed itself, a regulator's page or PDF, a
-- journal's page), fills the row like a swept one and marks it 'ready', or 'error' with the reason.

alter table public.semasa_watch add column if not exists status     text        not null default 'ready';
alter table public.semasa_watch add column if not exists pasted     boolean     not null default false;
alter table public.semasa_watch add column if not exists error      text;
alter table public.semasa_watch add column if not exists attempts   int         not null default 0;
alter table public.semasa_watch add column if not exists claimed_at timestamptz;
alter table public.semasa_watch add column if not exists created_by uuid references auth.users (id) on delete set null;
alter table public.semasa_watch drop constraint if exists semasa_watch_status_check;
alter table public.semasa_watch add constraint semasa_watch_status_check
  check (status in ('pending', 'working', 'ready', 'error'));
create index if not exists semasa_watch_waiting_idx on public.semasa_watch (status, created_at)
  where status in ('pending', 'working');

-- the page may add a link waiting to be read, and nothing else (the worker, as service role, fills the rest)
drop policy if exists "semasa watch: uploaders paste" on public.semasa_watch;
create policy "semasa watch: uploaders paste" on public.semasa_watch
  for insert to authenticated
  with check (public.semasa_is_uploader() and pasted and status = 'pending' and created_by = auth.uid());
revoke insert on public.semasa_watch from anon, authenticated;
grant insert (section, url, title, source, status, pasted, created_by) on public.semasa_watch to authenticated;

-- a pasted link may be removed (a wrong paste, or one that failed); a swept item is only ever hidden
drop policy if exists "semasa watch: uploaders remove pasted" on public.semasa_watch;
create policy "semasa watch: uploaders remove pasted" on public.semasa_watch
  for delete to authenticated using (public.semasa_is_uploader() and pasted);
revoke delete on public.semasa_watch from anon;
grant delete on public.semasa_watch to authenticated;

-- a paste wakes the worker at once (same dispatch as 009's clock, same Vault secrets)
create or replace function public.semasa_watch_wake() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform public.semasa_clock_dispatch('media_pending');
  return new;
exception when others then
  raise warning 'semasa_watch_wake: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_watch_wake on public.semasa_watch;
create trigger semasa_watch_wake after insert on public.semasa_watch
  for each row when (new.status = 'pending') execute function public.semasa_watch_wake();
revoke execute on function public.semasa_watch_wake() from public, anon, authenticated;

-- 011's net, now also counting pasted links waiting to be read (everything else exactly as 011 wrote it)
create or replace function public.semasa_clock_worker() returns text
language plpgsql security definer set search_path = public as $$
declare
  v_waiting int := 0;
begin
  select count(*) into v_waiting from public.media_generations
   where status = 'pending' or (status = 'processing' and updated_at < now() - interval '60 minutes');
  v_waiting := v_waiting + (select count(*) from public.semasa_ideas
   where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  begin
    v_waiting := v_waiting + (select count(*) from public.semasa_faqs
     where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  exception when undefined_table then null;            -- 007 not run yet
  end;
  v_waiting := v_waiting + (select count(*) from public.semasa_videos
   where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  v_waiting := v_waiting + (select count(*) from public.semasa_watch
   where status = 'pending' or (status = 'working' and claimed_at < now() - interval '30 minutes' and attempts < 3));
  if v_waiting = 0 then
    return 'nothing waiting';
  end if;
  return public.semasa_clock_dispatch('media_pending');
end $$;
revoke execute on function public.semasa_clock_worker() from public, anon, authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from information_schema.columns where table_name = 'semasa_watch' and column_name = 'pasted'),
--          (select count(*) from pg_policies where tablename = 'semasa_watch' and policyname = 'semasa watch: uploaders paste'),
--          (select count(*) from pg_trigger where tgname = 'semasa_watch_wake');
