-- 092 · Baki kredit API: "Refresh now" and the figure Wan types by hand (Wan, 23 Nov 2026: "satu segment untuk pantau berapa banyak
-- realtime baki credit API tinggal dan validity for mireld, rootsys dan KioskAPI").
--
-- NOTHING ELSE needs SQL: the readings themselves go into semasa_api_status.balance (jsonb, supabase/035) as `credit` and `tried`,
-- written by .github/workflows/api-credit.yml every 15 minutes with the service role. Run this file once, by hand, in the SQL editor.
-- Until it is run the page still shows every reading; only its two buttons say "run supabase/092 first".
--
-- Two rows in semasa_settings, because the browser may UPDATE a setting but never INSERT one (005_studio.sql):
--   credit_check       {requested_at}   the page's "Refresh now" writes it; the trigger below wakes the workflow (event `credit_check`)
--   api_credit_manual  {<slug>: {remaining, total, unit, expires_at, entered_at, note}}
--                      a figure Wan copied from a gateway's own dashboard, for a gateway whose balance the API cannot be asked.
--                      The page labels it MANUAL with its date and never mixes it into a live reading.
-- The trigger uses the same Vault secrets as 057 / 042 (semasa_github_dispatch_token, semasa_github_dispatch_repo). Without them
-- "Refresh now" does nothing but the 15-minute run goes on. Safe to re-run.

insert into public.semasa_settings (key, value) values ('credit_check', '{}'::jsonb) on conflict (key) do nothing;
insert into public.semasa_settings (key, value) values ('api_credit_manual', '{}'::jsonb) on conflict (key) do nothing;

create or replace function public.semasa_notify_credit_check() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the credit check waits for its 15-minute run';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'credit_check')
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_credit_check() from public, anon, authenticated;

drop trigger if exists semasa_settings_credit_check_notify on public.semasa_settings;
create trigger semasa_settings_credit_check_notify after update of value on public.semasa_settings
  for each row when (new.key = 'credit_check') execute function public.semasa_notify_credit_check();

-- Check (should print 2):
select count(*) as credit_rows from public.semasa_settings where key in ('credit_check', 'api_credit_manual');
