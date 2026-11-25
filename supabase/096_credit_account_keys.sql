-- 096 · The account key that reads a gateway's balance, typed into Semasa (Wan, 24 Nov 2026: "add segment that I can add key
-- directly in the semasa so can read balance").
--
-- KiosAPI is a New-API panel: its top-up sits on the ACCOUNT, which an API key cannot read (the key answers "no limit, no end
-- date"). The account is read with the access token made in the panel (Personal settings, Security) plus the user id. Until now
-- the only place for the pair was two GitHub secrets (KIOSAPI_ACCESS_TOKEN, KIOSAPI_USER_ID); this table is the same pair, typed
-- on the API credit page instead. The secrets still work and win when both are set.
--
-- The token is kept like every other key here: no policy lets the page read it back; only the worker (service_role) reads it,
-- and it is sent ONLY to that gateway's own host. The page sees the user id, the token's last four characters and when it was
-- saved. An access token can manage the account, so it is worth more than an API key: remove it here when it is not wanted.
-- Safe to re-run.

create table if not exists public.semasa_credit_accounts (
  slug         text primary key check (slug in ('kiosapi', 'mireld', 'rootsys')),
  access_token text not null,                          -- never SELECTable by the page
  user_id      text not null,
  token_hint   text,                                   -- the last four characters, for display
  updated_by   uuid references auth.users (id) on delete set null,
  updated_at   timestamptz not null default now()
);

alter table public.semasa_credit_accounts enable row level security;
revoke all on public.semasa_credit_accounts from anon, authenticated;      -- no policy at all: the page uses the functions below

create or replace function public.semasa_credit_accounts_status() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may see the account keys' using errcode = '42501';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object('slug', a.slug, 'user_id', a.user_id, 'token_hint', a.token_hint,
                                                       'updated_at', a.updated_at) order by a.slug)
                   from public.semasa_credit_accounts a), '[]'::jsonb);
end $$;

create or replace function public.semasa_credit_account_save(p_slug text, p_access_token text, p_user_id text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_token text := btrim(coalesce(p_access_token, ''));
  v_user  text := btrim(coalesce(p_user_id, ''));
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may save an account key' using errcode = '42501';
  end if;
  if p_slug not in ('kiosapi', 'mireld', 'rootsys') then
    raise exception 'unknown gateway';
  end if;
  if v_token ~ '\s' or length(v_token) < 16 or length(v_token) > 400 then
    raise exception 'that does not look like an access token (one long string, no spaces)';
  end if;
  if v_user !~ '^[0-9]{1,12}$' then
    raise exception 'the user id is the NUMBER the panel shows for your account (digits only)';
  end if;
  insert into public.semasa_credit_accounts as a (slug, access_token, user_id, token_hint, updated_by, updated_at)
  values (p_slug, v_token, v_user, right(v_token, 4), auth.uid(), now())
  on conflict (slug) do update set access_token = excluded.access_token, user_id = excluded.user_id,
    token_hint = excluded.token_hint, updated_by = excluded.updated_by, updated_at = now();
  return public.semasa_credit_accounts_status();
end $$;

create or replace function public.semasa_credit_account_remove(p_slug text) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may remove an account key' using errcode = '42501';
  end if;
  delete from public.semasa_credit_accounts where slug = p_slug;
  return public.semasa_credit_accounts_status();
end $$;

revoke execute on function public.semasa_credit_accounts_status() from public, anon;
revoke execute on function public.semasa_credit_account_save(text, text, text) from public, anon;
revoke execute on function public.semasa_credit_account_remove(text) from public, anon;
grant execute on function public.semasa_credit_accounts_status() to authenticated;
grant execute on function public.semasa_credit_account_save(text, text, text) to authenticated;
grant execute on function public.semasa_credit_account_remove(text) to authenticated;

notify pgrst, 'reload schema';
