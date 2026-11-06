-- 058 · Motion draws its scene pictures through Wan's ChatGPT login (Wan, 5 Nov 2026: "for motion - add codex or chatgpt login
-- Oauth, so image motion can generate based on story board and styles apply").
--
-- Wan runs `codex login` once on his own computer and pastes the contents of ~/.codex/auth.json into the Motion tab. The three
-- tokens are kept here, where NO policy lets the page read them back: only the worker (service_role, on the GitHub runner) reads
-- and refreshes them, and writes the new tokens it is given. The page sees a status (connected or not, the account, when the
-- access token ends, the last success and the last error) and nothing else.
--
-- It uses OpenAI's own Codex login, not an app registered by Semasa, so OpenAI can change or limit it without notice; the film
-- never depends on it (a scene whose picture cannot be drawn keeps its Unsplash photo, or none). Safe to re-run.

create table if not exists public.semasa_chatgpt_auth (
  id                text primary key default 'main' check (id = 'main'),
  auth              jsonb not null,                    -- {"tokens": {id_token, access_token, refresh_token, account_id}}: never SELECTable
  account           text,                              -- the e-mail on the login, for display
  access_expires_at timestamptz,                       -- when the access token ends (the worker refreshes it before)
  enabled           boolean not null default true,     -- Wan's switch: draw a picture for each scene of a film
  model             text not null default 'gpt-5',     -- the ChatGPT model that calls the picture tool
  max_images        integer not null default 6 check (max_images between 1 and 8),
  connected_at      timestamptz not null default now(),-- bumped only by a new login: wakes the API check once (trigger below)
  checked_at        timestamptz,                       -- the login was accepted (a refresh worked) but no picture is proven yet
  last_ok_at        timestamptz,                       -- a picture was drawn
  last_error        text,
  last_error_at     timestamptz,
  updated_by        uuid references auth.users (id) on delete set null,
  updated_at        timestamptz not null default now()
);

alter table public.semasa_chatgpt_auth enable row level security;
revoke all on public.semasa_chatgpt_auth from anon, authenticated;     -- no policy at all: the page uses the functions below

-- what the page may see
create or replace function public.semasa_chatgpt_status() returns jsonb
language plpgsql security definer set search_path = public as $$
declare r public.semasa_chatgpt_auth;
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may see the ChatGPT login' using errcode = '42501';
  end if;
  select * into r from public.semasa_chatgpt_auth where id = 'main';
  if not found then
    return jsonb_build_object('connected', false);
  end if;
  return jsonb_build_object(
    'connected', true, 'account', r.account, 'access_expires_at', r.access_expires_at, 'enabled', r.enabled,
    'model', r.model, 'max_images', r.max_images, 'connected_at', r.connected_at, 'checked_at', r.checked_at,
    'last_ok_at', r.last_ok_at,
    'last_error', r.last_error, 'last_error_at', r.last_error_at, 'updated_at', r.updated_at);
end $$;

-- Wan pastes auth.json (or just its "tokens" object): keep the tokens and nothing else
create or replace function public.semasa_chatgpt_connect(p_auth jsonb, p_account text default null,
                                                         p_expires timestamptz default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  t jsonb := coalesce(p_auth -> 'tokens', p_auth);
  v_access  text := nullif(btrim(coalesce(t ->> 'access_token', '')), '');
  v_refresh text := nullif(btrim(coalesce(t ->> 'refresh_token', '')), '');
  v_id      text := nullif(btrim(coalesce(t ->> 'id_token', '')), '');
  v_acct    text := nullif(btrim(coalesce(t ->> 'account_id', '')), '');
  v_uid     uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may connect ChatGPT' using errcode = '42501';
  end if;
  if v_access is null or v_refresh is null then
    raise exception 'that is not a Codex auth.json: it needs tokens.access_token and tokens.refresh_token (run `codex login` with ChatGPT, not an API key)';
  end if;
  if v_access ~ '\s' or v_refresh ~ '\s' or length(v_access) < 40 or length(v_refresh) < 20 then
    raise exception 'those tokens do not look right (no spaces; they are long strings)';
  end if;
  insert into public.semasa_chatgpt_auth as c (id, auth, account, access_expires_at, connected_at, checked_at, last_ok_at, last_error,
                                              last_error_at, updated_by, updated_at)
  values ('main',
          jsonb_build_object('tokens', jsonb_strip_nulls(jsonb_build_object(
            'access_token', v_access, 'refresh_token', v_refresh, 'id_token', v_id, 'account_id', v_acct))),
          nullif(btrim(coalesce(p_account, '')), ''), p_expires, now(), null, null, null, null, v_uid, now())
  on conflict (id) do update set
    auth = excluded.auth, account = excluded.account, access_expires_at = excluded.access_expires_at,
    connected_at = now(), checked_at = null, last_ok_at = null, last_error = null, last_error_at = null, updated_by = v_uid,
    updated_at = now();
  return public.semasa_chatgpt_status();
end $$;

-- Wan's switch and the model / how many pictures a film may draw
create or replace function public.semasa_chatgpt_set(p_enabled boolean, p_model text default null,
                                                     p_max integer default null) returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the ChatGPT settings' using errcode = '42501';
  end if;
  if p_model is not null and (btrim(p_model) = '' or p_model !~ '^[A-Za-z0-9._:-]{1,64}$') then
    raise exception 'the model name is letters, digits and . _ : - only';
  end if;
  update public.semasa_chatgpt_auth set
    enabled = coalesce(p_enabled, enabled), model = coalesce(nullif(btrim(p_model), ''), model),
    max_images = coalesce(p_max, max_images), updated_by = v_uid, updated_at = now()
  where id = 'main';
  if not found then
    raise exception 'connect ChatGPT first';
  end if;
  return public.semasa_chatgpt_status();
end $$;

create or replace function public.semasa_chatgpt_disconnect() returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may disconnect ChatGPT' using errcode = '42501';
  end if;
  delete from public.semasa_chatgpt_auth where id = 'main';
end $$;

revoke execute on function public.semasa_chatgpt_status() from public, anon;
revoke execute on function public.semasa_chatgpt_connect(jsonb, text, timestamptz) from public, anon;
revoke execute on function public.semasa_chatgpt_set(boolean, text, integer) from public, anon;
revoke execute on function public.semasa_chatgpt_disconnect() from public, anon;
grant execute on function public.semasa_chatgpt_status() to authenticated;
grant execute on function public.semasa_chatgpt_connect(jsonb, text, timestamptz) to authenticated;
grant execute on function public.semasa_chatgpt_set(boolean, text, integer) to authenticated;
grant execute on function public.semasa_chatgpt_disconnect() to authenticated;

-- a NEW login wakes the API workflow once (the same repository_dispatch 'ai_team_changed' as 057), which refreshes the token and
-- writes last_ok_at or last_error, so the card says at once whether the login works. The worker's own refresh writes
-- access_expires_at and auth, not connected_at, so it never wakes itself.
drop trigger if exists semasa_chatgpt_auth_notify on public.semasa_chatgpt_auth;
create trigger semasa_chatgpt_auth_notify after insert or update of connected_at on public.semasa_chatgpt_auth
  for each row execute function public.semasa_notify_ai_team();

notify pgrst, 'reload schema';
