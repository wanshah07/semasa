-- 057 · A pin on the API tab is decided at once, live (Wan, 31 Oct 2026: "why I cannot change the model, make sure for auto model
-- search is live"). Saving settings.ai_team used to change nothing until the next worker run or the 6-hourly probe, and then the
-- router judged the pinned robot by a probe of ANOTHER model. Now the database wakes the API workflow the moment the pin row is
-- written (repository_dispatch 'ai_team_changed', the same Vault token 042 uses); the workflow probes the gateways, asks the
-- pinned model live and records the decision in settings.ai_team_state, which the tab then shows. No Vault token: the pin takes
-- effect at the next run, as before. Safe to re-run.

create or replace function public.semasa_notify_ai_team() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; an AI team pin takes effect at the next run';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'ai_team_changed')
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_ai_team() from public, anon, authenticated;

drop trigger if exists semasa_settings_ai_team_notify on public.semasa_settings;
create trigger semasa_settings_ai_team_notify after insert or update of value on public.semasa_settings
  for each row when (new.key = 'ai_team') execute function public.semasa_notify_ai_team();
