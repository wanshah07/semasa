-- Semasa · Wan's own sources: Reddit, YouTube, the OneDrive reference folders and MYRA's daily sheet (Studio's ideas
-- sweep, nightly drafter §2 and Cosmetic Reg Daily Sweep reader, brought over 30 Sep 2026: "port all three before
-- Friday"). Run ONCE in the SQL editor, after 023. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): one check constraint on semasa_watch (Semasa's own table) is widened by four sections,
-- and one cron job is added under a semasa_* name. No other app's table, policy or function is read or changed.
--
-- What it does
--   1. semasa_watch takes four new sections beside regulatory and publication: reddit, youtube, folder, myra. The page
--      shows them as tabs in the Isu semasa row (Reddit, YouTube, OneDrive, MYRA). Until this is run the sweep reads
--      and judges everything but cannot store a row, and says so in its report.
--   2. The clock wakes the sweep twice a day, 05:10 and 17:10 MYT (21:10 and 09:10 UTC), through GitHub's
--      repository_dispatch, the same way the scrape and the publisher are woken. GitHub's own schedule in sources.yml is
--      the net.
-- Nothing here posts, approves or drafts. What the sweep writes is feed rows; Wan clicks "Jadikan idea", or autofill (off
-- until Fri 2 Oct 20:00 MYT) writes an idea for an empty slot, and the result is a draft that waits for his Approve.

alter table public.semasa_watch drop constraint if exists semasa_watch_section_check;
alter table public.semasa_watch add constraint semasa_watch_section_check
  check (section in ('regulatory', 'publication', 'reddit', 'youtube', 'folder', 'myra'));

-- the sweep's own row (Wan's overrides live in it; the sweep writes last_run and report). A row already there is kept.
insert into public.semasa_settings (key, value) values ('sources', '{}'::jsonb) on conflict (key) do nothing;

-- the clock. cron.schedule with an existing job name replaces that job, so this can be run again safely.
do $$
begin
  perform cron.schedule('semasa_sources', '10 21,9 * * *', $cmd$select public.semasa_clock_dispatch('sources_due')$cmd$);
exception when others then
  raise notice 'semasa_sources was not scheduled (%). GitHub''s own schedule in sources.yml still runs it.', sqlerrm;
end $$;

-- "Sweep now" on any of the four tabs saves force:true in the 'sources' row; a person's save wakes the sweep at once (the
-- sweep's own writes do not wake it) and the sweep clears the flag. Same pattern as the Regulatory tab (012).
create or replace function public.semasa_sources_force() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.key = 'sources' and auth.uid() is not null and coalesce((new.value ->> 'force')::boolean, false)
     and not coalesce((old.value ->> 'force')::boolean, false) then
    perform public.semasa_clock_dispatch('sources_due');
  end if;
  return new;
exception when others then
  raise warning 'semasa_sources_force: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_sources_force on public.semasa_settings;
create trigger semasa_sources_force after update on public.semasa_settings
  for each row execute function public.semasa_sources_force();
revoke execute on function public.semasa_sources_force() from public, anon, authenticated;

-- Check (should print 1 | 1 | 1 | 1):
select (select count(*) from pg_constraint where conname = 'semasa_watch_section_check'
          and pg_get_constraintdef(oid) like '%youtube%') as sections,
       (select count(*) from public.semasa_settings where key = 'sources') as settings_row,
       (select count(*) from cron.job where jobname = 'semasa_sources') as clock,
       (select count(*) from pg_trigger where tgname = 'semasa_sources_force') as sweep_now;
