-- 095 · More than one ChatGPT account for pictures (Wan, 24 Nov 2026: "add chatgpt segment that I can add multiple accounts to
-- support image gen using chatgpt").
--
-- One ChatGPT plan draws only so many pictures before it answers "usage limit" (the carousels of 24 Nov hit it and fell to
-- KiosAPI). The main login (058, the row 'main' of semasa_chatgpt_auth) stays exactly as it is: the text jobs, the chat and the
-- 6-hourly check all use it. EXTRA accounts live here, are used for PICTURES only, and are asked in order after the main one:
-- when an account says its allowance is used up, the next one draws (chatgpt_login.picture_logins).
--
-- The tokens are kept like 058's: no policy lets the page read them back; only the worker (service_role) reads and refreshes
-- them. The page sees the e-mail, the switch, the last success, the last error and when a used-up account is asked again.
-- An extra account is added with the same link-and-code login as the main one (059): the request names its target ('new').
-- Safe to re-run.

create table if not exists public.semasa_chatgpt_accounts (
  id                text primary key check (id ~ '^acc[0-9]{1,2}$'),
  auth              jsonb not null,                    -- {"tokens": {...}}: never SELECTable by the page
  account           text,                              -- the e-mail on the login, for display
  access_expires_at timestamptz,
  enabled           boolean not null default true,
  model             text not null default 'gpt-5',     -- the chat model that calls the picture tool (replaced when refused)
  max_images        integer not null default 6 check (max_images between 1 and 8),
  connected_at      timestamptz not null default now(),
  checked_at        timestamptz,
  last_ok_at        timestamptz,                       -- a picture was drawn with this account
  last_error        text,
  last_error_at     timestamptz,
  limit_until       timestamptz,                       -- the account said its allowance is used up: not asked again before this
  updated_by        uuid references auth.users (id) on delete set null,
  updated_at        timestamptz not null default now()
);

alter table public.semasa_chatgpt_accounts enable row level security;
revoke all on public.semasa_chatgpt_accounts from anon, authenticated;      -- no policy at all: the page uses the functions below

-- which login a code request is for: 'main' (058's row) or 'new' (one more row here)
alter table public.semasa_chatgpt_device add column if not exists target text not null default 'main';
alter table public.semasa_chatgpt_device drop constraint if exists semasa_chatgpt_device_target_check;
alter table public.semasa_chatgpt_device add constraint semasa_chatgpt_device_target_check check (target in ('main', 'new'));

-- the status now says which login the code is for, so each card shows only its own request
create or replace function public.semasa_chatgpt_device_status() returns jsonb
language plpgsql security definer set search_path = public as $$
declare r public.semasa_chatgpt_device; v_state text;
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may use the ChatGPT login' using errcode = '42501';
  end if;
  select * into r from public.semasa_chatgpt_device where id = 'main';
  if not found then
    return jsonb_build_object('state', 'idle', 'target', 'main', 'server_now', now());
  end if;
  v_state := r.state;
  if v_state in ('waiting') and r.expires_at is not null and r.expires_at < now() then
    v_state := 'expired';
  end if;
  return jsonb_build_object('state', v_state, 'user_code', r.user_code, 'verification_url', r.verification_url,
                            'expires_at', r.expires_at, 'error', r.error, 'requested_at', r.requested_at, 'target', r.target,
                            'server_now', now());
end $$;

-- the main login's request: as 059, and it says so (a request for an extra account must never be mistaken for it)
create or replace function public.semasa_chatgpt_device_start() returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may use the ChatGPT login' using errcode = '42501';
  end if;
  insert into public.semasa_chatgpt_device as d (id, state, requested_at, user_code, verification_url, expires_at, device_auth_id,
                                                 error, requested_by, updated_at, target)
  values ('main', 'requested', now(), null, null, null, null, null, v_uid, now(), 'main')
  on conflict (id) do update set
    state = 'requested', requested_at = now(), user_code = null, verification_url = null, expires_at = null,
    device_auth_id = null, error = null, requested_by = v_uid, updated_at = now(), target = 'main';
  return public.semasa_chatgpt_device_status();
end $$;

-- one more account: the same code request, for a new row here. At most 8 extra accounts.
create or replace function public.semasa_chatgpt_account_start() returns jsonb
language plpgsql security definer set search_path = public as $$
declare v_uid uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may use the ChatGPT login' using errcode = '42501';
  end if;
  if (select count(*) from public.semasa_chatgpt_accounts) >= 8 then
    raise exception 'eight extra ChatGPT accounts is the most: remove one first';
  end if;
  insert into public.semasa_chatgpt_device as d (id, state, requested_at, user_code, verification_url, expires_at, device_auth_id,
                                                 error, requested_by, updated_at, target)
  values ('main', 'requested', now(), null, null, null, null, null, v_uid, now(), 'new')
  on conflict (id) do update set
    state = 'requested', requested_at = now(), user_code = null, verification_url = null, expires_at = null,
    device_auth_id = null, error = null, requested_by = v_uid, updated_at = now(), target = 'new';
  return public.semasa_chatgpt_device_status();
end $$;

-- what the page may see of the extra accounts: never a token
create or replace function public.semasa_chatgpt_accounts_status() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may see the ChatGPT logins' using errcode = '42501';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
    'id', a.id, 'account', a.account, 'enabled', a.enabled, 'connected_at', a.connected_at, 'checked_at', a.checked_at,
    'last_ok_at', a.last_ok_at, 'last_error', a.last_error, 'last_error_at', a.last_error_at, 'limit_until', a.limit_until)
    order by a.id) from public.semasa_chatgpt_accounts a), '[]'::jsonb);
end $$;

create or replace function public.semasa_chatgpt_account_set(p_id text, p_enabled boolean) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the ChatGPT logins' using errcode = '42501';
  end if;
  -- saving the switch ends a rest ("ask again now"), and the "limit reached" message that started it goes with it: an account
  -- Wan just told Semasa to ask again must not read as an error. (The right-hand sides read the row as it was.)
  update public.semasa_chatgpt_accounts set enabled = coalesce(p_enabled, enabled),
    last_error = case when limit_until is not null then null else last_error end,
    last_error_at = case when limit_until is not null then null else last_error_at end,
    limit_until = null, updated_by = auth.uid(), updated_at = now() where id = p_id;
  if not found then
    raise exception 'no such ChatGPT account';
  end if;
  return public.semasa_chatgpt_accounts_status();
end $$;

create or replace function public.semasa_chatgpt_account_remove(p_id text) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the ChatGPT logins' using errcode = '42501';
  end if;
  delete from public.semasa_chatgpt_accounts where id = p_id;      -- the tokens go with the row
  return public.semasa_chatgpt_accounts_status();
end $$;

revoke execute on function public.semasa_chatgpt_account_start() from public, anon;
revoke execute on function public.semasa_chatgpt_accounts_status() from public, anon;
revoke execute on function public.semasa_chatgpt_account_set(text, boolean) from public, anon;
revoke execute on function public.semasa_chatgpt_account_remove(text) from public, anon;
grant execute on function public.semasa_chatgpt_account_start() to authenticated;
grant execute on function public.semasa_chatgpt_accounts_status() to authenticated;
grant execute on function public.semasa_chatgpt_account_set(text, boolean) to authenticated;
grant execute on function public.semasa_chatgpt_account_remove(text) to authenticated;

notify pgrst, 'reload schema';
