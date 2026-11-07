-- 062 · Gemini keys: say whether each key is live, and accept the newer key format
-- (Wan, 7 Nov 2026: "cannot add api and save the api key, and don't know if the api is live or not").
--
-- * A key was refused by the page's own format check when it held a dot (Google's newer keys can: AQ.Ab...). The database and the page
--   now accept letters, digits, . _ ~ and - (20 to 200 characters, no spaces).
-- * A new key stayed "Not tried yet" until Motion or the AI team happened to use it. Now a new key, a key switched on, and the
--   "Check now" button (semasa_gemini_keys_check) wake the Gemini check workflow (repository_dispatch 'gemini_check'), which asks every
--   switched-on key and writes the answer on its row: checked_at and check_note, beside the status 061 already kept.
-- Safe to re-run.

alter table public.semasa_gemini_keys add column if not exists checked_at timestamptz;
alter table public.semasa_gemini_keys add column if not exists check_note text;

-- one dispatch for all three callers; false when the token is not in the vault
create or replace function public.semasa_dispatch_gemini_check() returns boolean
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the Gemini check cannot start itself';
    return false;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'gemini_check')
  );
  return true;
end $$;
revoke execute on function public.semasa_dispatch_gemini_check() from public, anon, authenticated;

create or replace function public.semasa_notify_gemini_check() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform public.semasa_dispatch_gemini_check();
  return new;
end $$;
revoke execute on function public.semasa_notify_gemini_check() from public, anon, authenticated;

drop trigger if exists semasa_gemini_keys_notify on public.semasa_gemini_keys;
create trigger semasa_gemini_keys_notify after insert on public.semasa_gemini_keys
  for each row execute function public.semasa_notify_gemini_check();

create or replace function public.semasa_gemini_keys_list() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may see the Gemini keys' using errcode = '42501';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
      'id', k.id, 'label', k.label, 'hint', k.hint, 'enabled', k.enabled, 'status', k.status,
      'cooldown_until', k.cooldown_until, 'last_ok_at', k.last_ok_at, 'last_used_at', k.last_used_at,
      'last_error', k.last_error, 'last_error_at', k.last_error_at, 'calls', k.calls, 'failures', k.failures,
      'checked_at', k.checked_at, 'check_note', k.check_note,
      'created_at', k.created_at) order by k.created_at) from public.semasa_gemini_keys k), '[]'::jsonb);
end $$;

create or replace function public.semasa_gemini_key_add(p_label text, p_key text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_key   text := btrim(coalesce(p_key, ''));
  v_label text := left(btrim(coalesce(p_label, '')), 60);
  v_uid   uuid := auth.uid();
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may add a Gemini key' using errcode = '42501';
  end if;
  if v_key !~ '^[A-Za-z0-9._~-]{20,200}$' then
    raise exception 'that does not look like a Google AI Studio key (20 to 200 letters, digits, . _ ~ and -, no spaces)';
  end if;
  if (select count(*) from public.semasa_gemini_keys) >= 10 then
    raise exception 'ten keys is the most: delete one first';
  end if;
  if exists (select 1 from public.semasa_gemini_keys where api_key = v_key) then
    raise exception 'that key is already added';
  end if;
  insert into public.semasa_gemini_keys (label, api_key, hint, created_by)
  values (v_label, v_key, '…' || right(v_key, 4), v_uid);
  return public.semasa_gemini_keys_list();
end $$;

-- switching a key on also asks it again
create or replace function public.semasa_gemini_key_set(p_id uuid, p_enabled boolean default null, p_label text default null) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change a Gemini key' using errcode = '42501';
  end if;
  update public.semasa_gemini_keys set
    label = coalesce(left(btrim(p_label), 60), label),
    enabled = coalesce(p_enabled, enabled),
    status = case when p_enabled is true then 'new' else status end,
    cooldown_until = case when p_enabled is true then null else cooldown_until end,
    last_error = case when p_enabled is true then null else last_error end,
    last_error_at = case when p_enabled is true then null else last_error_at end,
    checked_at = case when p_enabled is true then null else checked_at end,
    check_note = case when p_enabled is true then null else check_note end,
    updated_at = now()
  where id = p_id;
  if not found then
    raise exception 'that key is not there';
  end if;
  if p_enabled is true then
    perform public.semasa_dispatch_gemini_check();
  end if;
  return public.semasa_gemini_keys_list();
end $$;

-- the "Check now" button
create or replace function public.semasa_gemini_keys_check() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may check the Gemini keys' using errcode = '42501';
  end if;
  if not public.semasa_dispatch_gemini_check() then
    raise exception 'the check cannot start itself: the GitHub dispatch token is missing from the vault';
  end if;
  return public.semasa_gemini_keys_list();
end $$;

revoke execute on function public.semasa_gemini_keys_check() from public, anon;
grant execute on function public.semasa_gemini_keys_check() to authenticated;

notify pgrst, 'reload schema';
