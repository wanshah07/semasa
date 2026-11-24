-- 094 · The API tab's "Test pictures" button (Wan, 24 Nov 2026: "button so we can test new api if okay or not or live").
-- Writing settings.ai_test wakes the ChatGPT live test (repository_dispatch 'ai_test', the same Vault token 057 uses): one short
-- answer, one picture read, one picture drawn through Wan's own ChatGPT login. The workflow writes the outcome to
-- settings.ai_test_result, which the tab reads. No Vault token: the button explains that nothing ran. Safe to re-run.

create or replace function public.semasa_notify_ai_test() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the picture test did not start';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'ai_test')
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_ai_test() from public, anon, authenticated;

drop trigger if exists semasa_settings_ai_test_notify on public.semasa_settings;
create trigger semasa_settings_ai_test_notify after insert or update of value on public.semasa_settings
  for each row when (new.key = 'ai_test') execute function public.semasa_notify_ai_test();

-- the page saves with an UPDATE (an update that matches nothing is an error), so both rows exist from the start
insert into public.semasa_settings (key, value) values ('ai_test', '{}'::jsonb), ('ai_test_result', '{}'::jsonb)
  on conflict (key) do nothing;
