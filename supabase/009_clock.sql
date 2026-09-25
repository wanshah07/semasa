-- Semasa · a clock that does not skip · run ONCE in the SQL editor after 001–008. Idempotent.
--
-- Why: GitHub runs scheduled workflows "best effort". On 24–25 Sep 2026 the 15-minute media poll ran 4 times in 6
-- hours, the scrape went more than 5 hours without a run and the 11:20 MYT publisher slot never fired, so an
-- idea sat on "Menunggu bot". Supabase's own scheduler (pg_cron) keeps time; it wakes the same workflows through
-- repository_dispatch, with the same Vault token 004 uses. GitHub's schedules stay as a second, slower net: both
-- start the same workflow, and each workflow's `concurrency` group runs them one at a time, so a double start
-- costs one extra quick run and never a double result (scrape upserts, the worker claims rows conditionally, the
-- publisher logs by fingerprint and skips a channel already published).
--
-- NEEDS the Vault secrets from README step 4 (semasa_github_dispatch_token, semasa_github_dispatch_repo).
-- Without them every tick writes one warning to the log instead of calling GitHub, and nothing else happens.
--
-- SAFE IN A SHARED PROJECT (KPI): it adds the pg_cron extension if absent (Supabase ships it), one function
-- family named semasa_clock_*, one trigger on semasa_settings and three cron jobs named semasa_*. It never touches
-- another app's jobs.

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- Wake one workflow. Returns what it did, for the SQL editor.
create or replace function public.semasa_clock_dispatch(p_event text) returns text
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    -- say it once every 6 hours, not on every 10-minute tick
    if exists (select 1 from public.semasa_log where event = 'clock.no_token' and at > now() - interval '6 hours') then
      return 'no token';
    end if;
    perform public.semasa_log_write('warn', 'system', 'clock.no_token',
      'Jam Supabase: token GitHub tiada dalam Vault, jadi "' || p_event || '" tidak dihantar (README langkah 4)',
      null, null, jsonb_build_object('event', p_event));
    return 'no token';
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-clock'),
    body    := jsonb_build_object('event_type', p_event, 'client_payload', jsonb_build_object('by', 'clock')));
  return 'sent ' || p_event;
exception when others then
  raise warning 'semasa_clock_dispatch: %', sqlerrm;
  return 'error: ' || sqlerrm;
end $$;

-- The worker's net: wake it only when something is actually waiting, so an idle day costs no Actions minutes.
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
  if v_waiting = 0 then
    return 'nothing waiting';
  end if;
  return public.semasa_clock_dispatch('media_pending');
end $$;

-- Wan saved the FAQ categories in Tetapan: wake the worker once, so the bot re-sorts "Lain-lain" against the new
-- list now rather than at the next unrelated job. Only a person's save counts (the worker's own saves do not wake
-- itself), and only when the list itself changed.
create or replace function public.semasa_clock_faq_changed() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.key = 'faq' and auth.uid() is not null
     and (new.value -> 'categories') is distinct from (old.value -> 'categories') then
    perform public.semasa_clock_dispatch('media_pending');
  end if;
  return new;
exception when others then
  raise warning 'semasa_clock_faq_changed: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_clock_faq_changed on public.semasa_settings;
create trigger semasa_clock_faq_changed after update on public.semasa_settings
  for each row execute function public.semasa_clock_faq_changed();

revoke execute on function public.semasa_clock_dispatch(text) from public, anon, authenticated;
revoke execute on function public.semasa_clock_worker() from public, anon, authenticated;

-- cron.schedule with an existing job name replaces that job, so this file can be run again safely.
-- Times are UTC: 23:17 · 07:17 · 15:17 UTC is 07:17 · 15:17 · 23:17 MYT; 22:20 · 03:20 · 11:20 UTC is 06:20 · 11:20 · 19:20 MYT.
select cron.schedule('semasa_scrape',  '17 23,7,15 * * *',  $$select public.semasa_clock_dispatch('scrape_due')$$);
select cron.schedule('semasa_worker',  '*/10 * * * *',      $$select public.semasa_clock_worker()$$);
select cron.schedule('semasa_publish', '20 22,3,11 * * *',  $$select public.semasa_clock_dispatch('publish_due')$$);

-- Check (should list the three semasa_* jobs):
--   select jobname, schedule, active from cron.job where jobname like 'semasa_%' order by jobname;
-- What the clock did lately:
--   select start_time, status, return_message from cron.job_run_details d join cron.job j using (jobid)
--    where j.jobname like 'semasa_%' order by start_time desc limit 20;
-- Stop it (for example if Semasa is retired):
--   select cron.unschedule(jobname) from cron.job where jobname like 'semasa_%';
