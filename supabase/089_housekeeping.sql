-- Semasa · housekeeping: pg_cron's own run history for Semasa's clock jobs (Wan, 22 Nov 2026: "make do routine cleaning to make
-- sure supabase or egress/db is not tight"). Run ONCE in the SQL editor, after 088. Idempotent: safe to run again.
--
-- pg_cron writes one row in cron.job_run_details per run and never deletes it. Semasa's six jobs (semasa_worker every 10 minutes,
-- semasa_pulse every 5) add about 450 rows a day; on 22 Nov 2026 the table held 12,800 rows (2.2 MB) going back to 25 Sep.
-- The worker (backend/semasa/housekeeping.py, housekeeping.yml) cannot reach the cron schema through the API, so it calls this.
--
-- Only rows of jobs named semasa_* are counted or deleted: the project is shared with KPI, and any job of KPI's is left alone.
-- p_dry = true only counts. Callable by service_role only.
create or replace function public.semasa_housekeeping_cron(p_days integer default 14, p_dry boolean default true)
returns integer
language plpgsql security definer set search_path = public, cron as $$
declare
  v_n integer;
begin
  if p_days is null or p_days < 3 then
    raise exception 'semasa: keep at least 3 days of cron history';
  end if;
  if p_dry then
    select count(*) into v_n from cron.job_run_details d
     where d.start_time < now() - make_interval(days => p_days)
       and d.jobid in (select j.jobid from cron.job j where j.jobname like 'semasa\_%');
    return v_n;
  end if;
  delete from cron.job_run_details d
   where d.start_time < now() - make_interval(days => p_days)
     and d.jobid in (select j.jobid from cron.job j where j.jobname like 'semasa\_%');
  get diagnostics v_n = row_count;
  return v_n;
end $$;

revoke execute on function public.semasa_housekeeping_cron(integer, boolean) from public, anon, authenticated;
grant execute on function public.semasa_housekeeping_cron(integer, boolean) to service_role;

notify pgrst, 'reload schema';

-- Check (counts only, deletes nothing):
select public.semasa_housekeeping_cron(14, true) as semasa_cron_rows_older_than_14_days;
-- To undo:
--   drop function if exists public.semasa_housekeeping_cron(integer, boolean);
