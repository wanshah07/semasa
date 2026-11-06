-- 059 · Log in to ChatGPT from the Motion tab with a link and a one-time code, no file to paste (Wan, 6 Nov 2026: "can we implement
-- this, and the code can refresh, link can click in semasa to link with motion").
--
-- The device-code login the Codex CLI itself offers (`codex login --device-auth`): Semasa asks auth.openai.com for a code, the page
-- shows it beside a link to https://auth.openai.com/codex/device, Wan signs in there and types the code, and the worker (a GitHub
-- run, because a browser page cannot call that host) receives the tokens and saves them where 058 keeps them. The page never
-- sees a token, nor the private device id kept in this table.
--
--   Start / new code   semasa_chatgpt_device_start()  -> state 'requested'; the database wakes the "ChatGPT login" workflow
--   Read               semasa_chatgpt_device_status() -> state, code, link, when it ends (never the device id)
--   Stop               semasa_chatgpt_device_cancel()
--
-- states: idle · requested (waiting for the worker to get a code) · waiting (code shown, Wan has not approved yet) · done ·
-- expired (the code lived 15 minutes) · error. Safe to re-run.

create table if not exists public.semasa_chatgpt_device (
  id               text primary key default 'main' check (id = 'main'),
  state            text not null default 'idle' check (state in ('idle', 'requested', 'waiting', 'done', 'expired', 'error')),
  requested_at     timestamptz not null default now(),   -- bumped by each start: it wakes the worker, and tells a stale run to stop
  user_code        text,
  verification_url text,
  expires_at       timestamptz,
  interval_s       integer not null default 5,
  device_auth_id   text,                                  -- private: never returned by a function below
  error            text,
  requested_by     uuid references auth.users (id) on delete set null,
  updated_at       timestamptz not null default now()
);

alter table public.semasa_chatgpt_device enable row level security;
revoke all on public.semasa_chatgpt_device from anon, authenticated;       -- no policy: the page uses the functions below

create or replace function public.semasa_chatgpt_device_status() returns jsonb
language plpgsql security definer set search_path = public as $$
declare r public.semasa_chatgpt_device; v_state text;
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may use the ChatGPT login' using errcode = '42501';
  end if;
  select * into r from public.semasa_chatgpt_device where id = 'main';
  if not found then
    return jsonb_build_object('state', 'idle', 'server_now', now());
  end if;
  v_state := r.state;
  if v_state in ('waiting') and r.expires_at is not null and r.expires_at < now() then
    v_state := 'expired';                                -- the code is dead whether or not the worker has noticed
  end if;
  return jsonb_build_object('state', v_state, 'user_code', r.user_code, 'verification_url', r.verification_url,
                            'expires_at', r.expires_at, 'error', r.error, 'requested_at', r.requested_at, 'server_now', now());
end $$;

create or replace function public.semasa_chatgpt_device_start() returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may use the ChatGPT login' using errcode = '42501';
  end if;
  insert into public.semasa_chatgpt_device as d (id, state, requested_at, user_code, verification_url, expires_at, device_auth_id,
                                                 error, requested_by, updated_at)
  values ('main', 'requested', now(), null, null, null, null, null, v_uid, now())
  on conflict (id) do update set
    state = 'requested', requested_at = now(), user_code = null, verification_url = null, expires_at = null,
    device_auth_id = null, error = null, requested_by = v_uid, updated_at = now();
  return public.semasa_chatgpt_device_status();
end $$;

create or replace function public.semasa_chatgpt_device_cancel() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may use the ChatGPT login' using errcode = '42501';
  end if;
  update public.semasa_chatgpt_device set state = 'idle', user_code = null, verification_url = null, expires_at = null,
    device_auth_id = null, error = null, updated_at = now() where id = 'main' and state in ('requested', 'waiting');
  return public.semasa_chatgpt_device_status();
end $$;

revoke execute on function public.semasa_chatgpt_device_status() from public, anon;
revoke execute on function public.semasa_chatgpt_device_start() from public, anon;
revoke execute on function public.semasa_chatgpt_device_cancel() from public, anon;
grant execute on function public.semasa_chatgpt_device_status() to authenticated;
grant execute on function public.semasa_chatgpt_device_start() to authenticated;
grant execute on function public.semasa_chatgpt_device_cancel() to authenticated;

-- a start wakes the "ChatGPT login" workflow (repository_dispatch 'chatgpt_login'), with the same Vault token as 042 and 057.
-- Without it the request waits and the card says the worker has not picked it up.
create or replace function public.semasa_notify_chatgpt_login() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the ChatGPT login cannot start itself';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'chatgpt_login')
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_chatgpt_login() from public, anon, authenticated;

drop trigger if exists semasa_chatgpt_device_notify on public.semasa_chatgpt_device;
create trigger semasa_chatgpt_device_notify after insert or update of requested_at on public.semasa_chatgpt_device
  for each row when (new.state = 'requested') execute function public.semasa_notify_chatgpt_login();

notify pgrst, 'reload schema';
