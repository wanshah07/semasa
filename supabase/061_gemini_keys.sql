-- 061 · Gemini with several API keys, picked automatically (Wan, 6 Nov 2026: "add gemini api key I can add multiple and its auto
-- select same like chatgpt").
--
-- Wan adds any number of Google AI Studio keys on the API tab. They are kept here, where NO policy lets the page read them back:
-- only the worker (service_role) reads them, picks one each time (the one used least recently that is not refused and not cooling
-- down after a rate-limit answer) and writes back how it went. The page sees a hint (the last four characters), a status, when the
-- key last worked, and the last error, through the functions below.
--
-- Gemini then serves two jobs (backend/semasa/gemini_keys.py): a text/vision robot (Wanshah 4) in the AI team for the jobs Wan allows,
-- and Motion's scene pictures after ChatGPT. The switches (on/off, which jobs, models, picture count) are the row `gemini` in
-- semasa_settings, which the page edits like any other setting. Safe to re-run.

create table if not exists public.semasa_gemini_keys (
  id             uuid primary key default gen_random_uuid(),
  label          text not null default '',
  api_key        text not null,                       -- private: never returned by a function below
  hint           text not null,                       -- the last four characters, to recognise it
  enabled        boolean not null default true,
  status         text not null default 'new' check (status in ('new', 'ok', 'limited', 'bad')),
  cooldown_until timestamptz,                         -- a rate-limited key rests until then
  last_ok_at     timestamptz,
  last_used_at   timestamptz,
  last_error     text,
  last_error_at  timestamptz,
  calls          integer not null default 0,
  failures       integer not null default 0,
  created_by     uuid references auth.users (id) on delete set null default auth.uid(),
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_gemini_keys_key_unique unique (api_key)
);

alter table public.semasa_gemini_keys enable row level security;
revoke all on public.semasa_gemini_keys from anon, authenticated;           -- no policy: the page uses the functions below

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
  if v_key !~ '^[A-Za-z0-9_-]{20,120}$' then
    raise exception 'that does not look like a Google AI Studio key (20 to 120 letters, digits, - and _, no spaces)';
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

-- switch a key on or off, or rename it; switching it on forgets a refusal and a rest, so a key Google refused can be tried again
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
    updated_at = now()
  where id = p_id;
  if not found then
    raise exception 'that key is not there';
  end if;
  return public.semasa_gemini_keys_list();
end $$;

create or replace function public.semasa_gemini_key_delete(p_id uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may delete a Gemini key' using errcode = '42501';
  end if;
  delete from public.semasa_gemini_keys where id = p_id;
  return public.semasa_gemini_keys_list();
end $$;

revoke execute on function public.semasa_gemini_keys_list() from public, anon;
revoke execute on function public.semasa_gemini_key_add(text, text) from public, anon;
revoke execute on function public.semasa_gemini_key_set(uuid, boolean, text) from public, anon;
revoke execute on function public.semasa_gemini_key_delete(uuid) from public, anon;
grant execute on function public.semasa_gemini_keys_list() to authenticated;
grant execute on function public.semasa_gemini_key_add(text, text) to authenticated;
grant execute on function public.semasa_gemini_key_set(uuid, boolean, text) to authenticated;
grant execute on function public.semasa_gemini_key_delete(uuid) to authenticated;

-- the switches: the page edits this row (the settings policy lets an uploader update any key but 'publishing')
insert into public.semasa_settings (key, value) values ('gemini', '{}'::jsonb) on conflict (key) do nothing;

notify pgrst, 'reload schema';
