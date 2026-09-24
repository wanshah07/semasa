-- Semasa · Module A · Database → GitHub Actions trigger
--
-- A new `pending` row fires a GitHub `repository_dispatch` so the media runner
-- starts within seconds instead of waiting for the 15-minute poll (media.yml
-- keeps the poll as the safety net, so a lost webhook costs minutes, not the job).
--
-- The GitHub token lives in Supabase Vault, never in this file and never in the
-- browser. Create it once (fine-grained PAT, this repo only, "Contents: read and
-- write" is the scope repository_dispatch needs):
--
--   select vault.create_secret('github_pat_xxx', 'semasa_github_dispatch_token',
--                              'PAT that may fire repository_dispatch on the semasa repo');
--
-- Then set the repo the dispatch goes to:
--
--   select vault.create_secret('wanshah07/semasa', 'semasa_github_dispatch_repo', 'owner/repo');
--
-- Requires the pg_net extension (Database → Extensions → pg_net).

create extension if not exists pg_net;

create or replace function public.semasa_notify_media_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  if new.status <> 'pending' then
    return new;
  end if;
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: semasa_github_dispatch_token / semasa_github_dispatch_repo missing from vault; relying on the 15-minute poll';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || v_token,
      'Accept', 'application/vnd.github+json',
      'Content-Type', 'application/json',
      'User-Agent', 'semasa-supabase-webhook'
    ),
    body    := jsonb_build_object(
      'event_type', 'media_pending',
      'client_payload', jsonb_build_object('id', new.id, 'type', new.type)
    )
  );
  return new;
end $$;

drop trigger if exists media_generations_notify_pending on public.media_generations;
create trigger media_generations_notify_pending
  after insert or update of status on public.media_generations
  for each row
  when (new.status = 'pending')
  execute function public.semasa_notify_media_pending();
