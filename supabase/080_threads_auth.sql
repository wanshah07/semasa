-- 080 · Wan's own Threads app (Wan, 13 Nov 2026: "add in semasa for threads" — the Threads app ID and app secret).
--
-- Why: the Composio route (THREADS_SEARCH_POSTS) answers "Application does not have permission for this action" (OAuthException
-- code 10, subcode 4279067): the app behind Composio has no threads_keyword_search. Meta's own docs say an app without that
-- permission searches only the authenticated user's own posts; after approval, public posts. So Semasa keeps Wan's own app here
-- and reads Threads directly (graph.threads.com), falling back to nothing if the permission is not approved.
--
-- Wan pastes three things from developers.facebook.com: the Threads app ID, the Threads app secret and a long-lived user token
-- (60 days; the worker refreshes it, as long as it is at least 24 hours old and not expired). They are kept here, where NO policy
-- lets the page read them back: only the worker (service_role, on the GitHub runner) reads them and writes the refreshed token.
-- The page sees a status: connected or not, the app ID, the account, when the token ends, the last success and the last error.
-- Nothing here posts, approves or drafts. Safe to re-run.

create table if not exists public.semasa_threads_auth (
  id            text primary key default 'main' check (id = 'main'),
  app_id        text not null,
  app_secret    text not null,                     -- never SELECTable by the page
  access_token  text not null,                     -- the long-lived user token: never SELECTable by the page
  expires_at    timestamptz,                       -- when the long-lived token ends (the worker refreshes it before)
  username      text,                              -- the account the token belongs to (filled by the worker's first check)
  user_id       text,
  enabled       boolean not null default true,     -- Wan's switch: read Threads through this app
  connected_at  timestamptz not null default now(),
  checked_at    timestamptz,                       -- the token was accepted (the account was read)
  last_ok_at    timestamptz,                       -- public posts were read
  last_error    text,
  last_error_at timestamptz,
  updated_by    uuid references auth.users (id) on delete set null,
  updated_at    timestamptz not null default now()
);

alter table public.semasa_threads_auth enable row level security;
revoke all on public.semasa_threads_auth from anon, authenticated;       -- no policy at all: the page uses the functions below

-- what the page may see (never the secret or the token)
create or replace function public.semasa_threads_status() returns jsonb
language plpgsql security definer set search_path = public as $$
declare r public.semasa_threads_auth;
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may see the Threads connection' using errcode = '42501';
  end if;
  select * into r from public.semasa_threads_auth where id = 'main';
  if not found then
    return jsonb_build_object('connected', false);
  end if;
  return jsonb_build_object(
    'connected', true, 'app_id', r.app_id, 'username', r.username, 'enabled', r.enabled, 'expires_at', r.expires_at,
    'connected_at', r.connected_at, 'checked_at', r.checked_at, 'last_ok_at', r.last_ok_at,
    'last_error', r.last_error, 'last_error_at', r.last_error_at, 'updated_at', r.updated_at);
end $$;

-- Wan pastes the app ID, the app secret and the long-lived token
create or replace function public.semasa_threads_connect(p_app_id text, p_app_secret text, p_token text,
                                                         p_expires timestamptz default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_id     text := btrim(coalesce(p_app_id, ''));
  v_secret text := btrim(coalesce(p_app_secret, ''));
  v_token  text := btrim(coalesce(p_token, ''));
  v_uid    uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may connect Threads' using errcode = '42501';
  end if;
  if v_id !~ '^[0-9]{6,24}$' then
    raise exception 'the Threads app ID is digits only (Meta dashboard: Use cases, Access the Threads API, Settings)';
  end if;
  if v_secret !~ '^[A-Za-z0-9]{16,64}$' then
    raise exception 'the Threads app secret is letters and digits only, without spaces (use Show on the same page)';
  end if;
  if length(v_token) < 40 or v_token ~ '\s' then
    raise exception 'that does not look like a long-lived Threads token (a long string with no spaces)';
  end if;
  insert into public.semasa_threads_auth as c (id, app_id, app_secret, access_token, expires_at, username, user_id, connected_at,
                                              checked_at, last_ok_at, last_error, last_error_at, updated_by, updated_at)
  values ('main', v_id, v_secret, v_token, p_expires, null, null, now(), null, null, null, null, v_uid, now())
  on conflict (id) do update set
    app_id = excluded.app_id, app_secret = excluded.app_secret, access_token = excluded.access_token,
    expires_at = excluded.expires_at, username = null, user_id = null, connected_at = now(), checked_at = null,
    last_ok_at = null, last_error = null, last_error_at = null, updated_by = v_uid, updated_at = now();
  return public.semasa_threads_status();
end $$;

create or replace function public.semasa_threads_set(p_enabled boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the Threads connection' using errcode = '42501';
  end if;
  update public.semasa_threads_auth set enabled = coalesce(p_enabled, enabled), updated_by = auth.uid(), updated_at = now()
  where id = 'main';
  if not found then
    raise exception 'connect Threads first';
  end if;
  return public.semasa_threads_status();
end $$;

create or replace function public.semasa_threads_disconnect() returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may disconnect Threads' using errcode = '42501';
  end if;
  delete from public.semasa_threads_auth where id = 'main';
end $$;

revoke execute on function public.semasa_threads_status() from public, anon;
revoke execute on function public.semasa_threads_connect(text, text, text, timestamptz) from public, anon;
revoke execute on function public.semasa_threads_set(boolean) from public, anon;
revoke execute on function public.semasa_threads_disconnect() from public, anon;
grant execute on function public.semasa_threads_status() to authenticated;
grant execute on function public.semasa_threads_connect(text, text, text, timestamptz) to authenticated;
grant execute on function public.semasa_threads_set(boolean) to authenticated;
grant execute on function public.semasa_threads_disconnect() to authenticated;

notify pgrst, 'reload schema';

-- Check (should print 1, 0 and 4): the table exists, no policy lets the page read it, and the four functions are there.
select (select count(*) from information_schema.tables where table_name = 'semasa_threads_auth') as table_exists,
       (select count(*) from pg_policies where tablename = 'semasa_threads_auth') as policies,
       (select count(*) from pg_proc where proname in ('semasa_threads_status', 'semasa_threads_connect', 'semasa_threads_set',
                                                       'semasa_threads_disconnect')) as functions;
