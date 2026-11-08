-- Semasa · the API status refreshed every 5 minutes and shown live (feature B, 8 Nov 2026). Run ONCE in the SQL editor, after
-- 035 (semasa_api_status) and 009 (the clock). Idempotent: safe to run again.
--
-- What it does
--   1. semasa_api_status and semasa_settings join the supabase_realtime publication, so the API page, Papan and the Technology
--      overview redraw each robot's dot the moment a row changes (web useTable realtime:true), instead of on a 5-minute poll.
--   2. A pg_cron job `semasa_pulse` every 5 minutes calls public.semasa_clock_pulse(), which POSTs to the Edge Function
--      semasa-pulse with the header x-semasa-pulse read from Vault. The function probes every robot the edge can reach and
--      writes the rows (supabase/functions/semasa-pulse/index.ts). The 6-hourly probe (api.yml) stays the authority and the
--      net for the robots the edge cannot reach.
--
-- BEFORE this does anything, Wan creates TWO secrets with the SAME random value (for example `openssl rand -hex 32`):
--   * Vault secret `semasa_pulse_secret`  (Supabase dashboard → Project Settings → Vault → New secret), read here;
--   * GitHub repo secret `PULSE_SECRET`   (Settings → Secrets and variables → Actions), which .github/workflows/functions.yml
--     writes to the function as its secret PULSE_SECRET with `supabase secrets set --yes` when it deploys.
-- Type the value into those two places only, never into a chat. Until the Vault secret exists every tick writes one warning
-- to semasa_log (once per 6 hours) and calls nothing, as 009 does for the dispatch token. Until the function secret exists the
-- function answers 401 to the clock and the page's "Semak sekarang" still works with a signed-in uploader's login.
--
-- SAFE IN A SHARED PROJECT (KPI): one function and one cron job under semasa_* names; two of Semasa's own tables are added to the
-- realtime publication. No other app's table, policy or function is read or changed.

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 1 · realtime for the status rows and the settings (the page's `api_pulse` row) -----------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['semasa_api_status', 'semasa_settings'] loop
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

-- 2 · the clock's call to the function --------------------------------------------------------------------------------------------
create or replace function public.semasa_clock_pulse() returns text
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_secret text;
begin
  select decrypted_secret into v_secret from vault.decrypted_secrets where name = 'semasa_pulse_secret';
  if v_secret is null or v_secret = '' then
    -- say it once every 6 hours, not on every 5-minute tick
    if exists (select 1 from public.semasa_log where event = 'clock.no_pulse_secret' and at > now() - interval '6 hours') then
      return 'no secret';
    end if;
    perform public.semasa_log_write('warn', 'system', 'clock.no_pulse_secret',
      'Jam Supabase: rahsia semasa_pulse_secret tiada dalam Vault, jadi denyut API tidak dihantar (supabase/075_api_pulse.sql)',
      null, null, '{}'::jsonb);
    return 'no secret';
  end if;
  perform net.http_post(
    url     := 'https://mwaocnbgvbkhovktgods.supabase.co/functions/v1/semasa-pulse',
    headers := jsonb_build_object('x-semasa-pulse', v_secret, 'Content-Type', 'application/json', 'User-Agent', 'semasa-clock'),
    body    := jsonb_build_object('by', 'clock'),
    timeout_milliseconds := 30000);
  return 'sent pulse';
exception when others then
  raise warning 'semasa_clock_pulse: %', sqlerrm;
  return 'error: ' || sqlerrm;
end $$;
revoke execute on function public.semasa_clock_pulse() from public, anon, authenticated;

-- cron.schedule with an existing job name replaces that job, so this file can be run again safely.
do $$
begin
  perform cron.schedule('semasa_pulse', '*/5 * * * *', $cmd$select public.semasa_clock_pulse()$cmd$);
exception when others then
  raise notice 'semasa_pulse was not scheduled (%). The 6-hourly api.yml probe still writes the rows.', sqlerrm;
end $$;

-- Check (should print 2 | 1 | 1):
select (select count(*) from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public'
          and tablename in ('semasa_api_status', 'semasa_settings')) as realtime,
       (select count(*) from pg_proc where proname = 'semasa_clock_pulse') as fn,
       (select count(*) from cron.job where jobname = 'semasa_pulse') as clock;
-- What the clock did lately:
--   select start_time, status, return_message from cron.job_run_details d join cron.job j using (jobid)
--    where j.jobname = 'semasa_pulse' order by start_time desc limit 10;
-- Stop it:  select cron.unschedule('semasa_pulse');
