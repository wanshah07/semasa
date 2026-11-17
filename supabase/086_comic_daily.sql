-- Semasa · The daily comic series (Wan, 17 Nov 2026: "can start create comic series storyboard and after approve create motion -
-- this series will comeout everyday which contain about isu semasa>halal>regulatory>fatwa").
-- Run ONCE in the SQL editor, after 085. Idempotent: safe to run again.
--
-- What it does
--   1. Two rows in semasa_settings. The browser may UPDATE a setting but never INSERT one (005_studio.sql), so the page cannot make
--      them itself:
--        `comic_series`      Wan's own settings of the series, written by the page only: enabled (OFF), paused, the lane list in his
--                            order, the hour, the series, how the words are made, and `make_now` (the "Buat episod hari ini
--                            sekarang" button writes a timestamp here).
--        `comic_series_log`  the worker's own record, read by the page and written by the worker only: the last look at the day,
--                            the days made or skipped with the reason, and which button press it answered. Two rows, so a save
--                            from the page can never overwrite the worker's record and the other way round.
--   2. A trigger on semasa_settings: when Wan presses the button (a person's save that changes comic_series.make_now) the Motion
--      worker is woken (repository_dispatch 'motion_pending', the same dispatch 043's trigger uses), so the storyboard is written
--      within minutes instead of at the next hourly run. Only a person's save counts; the worker's own saves wake nothing.
--   3. The clock: one pg_cron job `semasa_comic_daily` at 22:40 UTC (06:40 Malaysia time) wakes Motion once a day, so a late GitHub
--      schedule never delays the day's storyboard. It only wakes the worker; whether an episode is made is decided by the switch,
--      the pause and the one-a-day check in backend/semasa/comic_daily.py.
--
-- What it does NOT need
--   No table, column or constraint changes. An episode is a Motion film (semasa_motions, `options.template = 'comic'`) that waits
--   in the existing 'review' status of 071's storyboard gate; its drawing is a `slides` job in media_generations with meta.design
--   'comic' (085); its post is a draft in semasa_posts. Before this file is run the series still works with its defaults (the
--   switch is off, so nothing is made); only the page's save of the settings is refused, and the page says to run this file.
-- Nothing here approves, schedules or posts anything.

insert into public.semasa_settings (key, value)
values ('comic_series', '{"enabled": false, "paused": false, "lanes": ["isu_semasa", "halal", "regulatori", "fatwa"], "at": "06:30", "series": "isu-semasa-harian", "words_mode": "art", "style": ""}'::jsonb)
on conflict (key) do nothing;

insert into public.semasa_settings (key, value)
values ('comic_series_log', '{"last": null, "log": []}'::jsonb)
on conflict (key) do nothing;

-- 2 · a person pressed "make today's episode now": wake the Motion worker ---------------------------------------------------
create or replace function public.semasa_clock_comic_changed() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.key = 'comic_series' and auth.uid() is not null
     and (new.value ->> 'make_now') is distinct from (old.value ->> 'make_now')
     and coalesce(new.value ->> 'make_now', '') <> '' then
    perform public.semasa_clock_dispatch('motion_pending');
  end if;
  return new;
exception when others then
  raise warning 'semasa_clock_comic_changed: %', sqlerrm;
  return new;
end $$;
revoke execute on function public.semasa_clock_comic_changed() from public, anon, authenticated;

drop trigger if exists semasa_clock_comic_changed on public.semasa_settings;
create trigger semasa_clock_comic_changed after update on public.semasa_settings
  for each row execute function public.semasa_clock_comic_changed();

-- 3 · the clock: 22:40 UTC is 06:40 MYT. cron.schedule with an existing job name replaces that job, so this can be run again. ---
do $$
begin
  perform cron.schedule('semasa_comic_daily', '40 22 * * *', $cmd$select public.semasa_clock_dispatch('motion_pending')$cmd$);
exception when others then
  raise notice 'semasa: the comic clock job was not scheduled (%): the hourly Motion schedule still runs the series', sqlerrm;
end $$;

-- Check (should print 2, and the job once; the job is missing only where pg_cron is not installed):
select count(*) as comic_series_rows from public.semasa_settings where key in ('comic_series', 'comic_series_log');
--   select jobname, schedule, active from cron.job where jobname = 'semasa_comic_daily';
-- Stop the daily clock (the series itself is stopped by its switch in the page):
--   select cron.unschedule('semasa_comic_daily');
