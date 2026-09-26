-- Semasa · AI settings: the text reader/writer, the image generator and the picture reader, set from the page.
-- Run ONCE in the SQL editor, after 001–015. Idempotent: safe to run again.
--
-- Wan, 27 Sep 2026: "can add in setting reader, image generation, image reader key and endpoint".
--
-- SAFE IN A SHARED PROJECT (KPI): it creates two tables (semasa_ai_config, semasa_ai_secrets) and two functions
-- (semasa_save_ai_slot, semasa_clear_ai_slot). No other app's table, policy or function is read or changed.
--
-- How a key is kept:
--   semasa_ai_config   what the page may SEE: provider, endpoint, model, and the key's last four characters.
--   semasa_ai_secrets  the key itself. No policy lets the page read it, so once saved a key never comes back to the
--                      browser; only the worker (service_role, on the GitHub runner) reads it.
--   A key is BOUND to the endpoint it was entered with (key_host). Change the endpoint without typing the key again
--   and the key is dropped, so a key can never be sent to a host it was not meant for.
--   An empty slot, or an empty field, means "use the GitHub secret/variable", exactly as before this file.

create table if not exists public.semasa_ai_config (
  slot        text primary key check (slot in ('reader', 'image_gen', 'image_reader')),
  provider    text,
  base_url    text,          -- an https:// API root; for Cloudflare, the Account ID
  model       text,
  edit_model  text,          -- image_gen only: the model that redraws WITH a picture (Cloudflare FLUX.2, Replicate)
  key_hint    text,          -- "…abcd": enough to recognise the key, never enough to use it
  key_host    text,          -- the endpoint the key was entered for
  updated_by  uuid references auth.users (id) on delete set null,
  updated_at  timestamptz not null default now(),
  constraint semasa_ai_config_provider_check check (
    provider is null
    or (slot in ('reader', 'image_reader') and provider in ('openai', 'anthropic'))
    or (slot = 'image_gen' and provider in ('cloudflare', 'openai', 'replicate')))
);

create table if not exists public.semasa_ai_secrets (
  slot        text primary key references public.semasa_ai_config (slot) on delete cascade,
  api_key     text not null,
  updated_at  timestamptz not null default now()
);

alter table public.semasa_ai_config  enable row level security;
alter table public.semasa_ai_secrets enable row level security;

drop policy if exists "semasa ai config: uploaders read" on public.semasa_ai_config;
create policy "semasa ai config: uploaders read" on public.semasa_ai_config
  for select to authenticated using (public.semasa_is_uploader());
-- no write policy on either table and no policy at all on the secrets: the page writes ONLY through the two
-- functions below, which check the caller and keep the key bound to its endpoint
revoke all on public.semasa_ai_config  from anon, authenticated;
revoke all on public.semasa_ai_secrets from anon, authenticated;
grant select on public.semasa_ai_config to authenticated;

-- the host a key belongs to, worked out the same way by the worker (backend/semasa/ai_config.py key_host)
create or replace function public.semasa_ai_key_host(p_slot text, p_provider text, p_base_url text) returns text
language sql immutable set search_path = public as $$
  select case
    when p_slot = 'image_gen' and p_provider = 'replicate' then 'api.replicate.com'
    when p_slot = 'image_gen' and p_provider = 'cloudflare' then
      case when coalesce(p_base_url, '') = '' then null else 'cloudflare:' || lower(p_base_url) end
    else lower(substring(coalesce(p_base_url, '') from '^https://([^/:?#]+)'))
  end
$$;

create or replace function public.semasa_save_ai_slot(
  p_slot text, p_provider text, p_base_url text, p_model text, p_edit_model text,
  p_key text default null, p_clear_key boolean default false
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_provider text := nullif(btrim(coalesce(p_provider, '')), '');
  v_base     text := nullif(btrim(coalesce(p_base_url, '')), '');
  v_model    text := nullif(btrim(coalesce(p_model, '')), '');
  v_edit     text := nullif(btrim(coalesce(p_edit_model, '')), '');
  v_key      text := nullif(btrim(coalesce(p_key, '')), '');
  v_host     text;
  v_old      public.semasa_ai_config;
  v_dropped  boolean := false;
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the AI settings' using errcode = '42501';
  end if;
  if p_slot not in ('reader', 'image_gen', 'image_reader') then
    raise exception 'unknown AI slot %', p_slot;
  end if;
  if v_provider is null then
    v_provider := case when p_slot = 'image_gen' then 'cloudflare' else 'openai' end;
  end if;
  v_provider := lower(v_provider);
  if (p_slot = 'image_gen' and v_provider not in ('cloudflare', 'openai', 'replicate'))
     or (p_slot <> 'image_gen' and v_provider not in ('openai', 'anthropic')) then
    raise exception 'provider % cannot serve %', v_provider, p_slot;
  end if;
  if p_slot = 'image_gen' and v_provider = 'replicate' then
    v_base := null;                                       -- Replicate has one address
  elsif p_slot = 'image_gen' and v_provider = 'cloudflare' then
    if v_base is not null then
      v_base := lower(v_base);
      if v_base !~ '^[0-9a-f]{32}$' then
        raise exception 'the Cloudflare Account ID is 32 letters and digits (0-9, a-f)';
      end if;
    end if;
  elsif v_base is not null then
    v_base := regexp_replace(v_base, '/+$', '');
    if v_base !~ '^https://[^/:?#\s]+' then
      raise exception 'the endpoint must start with https://';
    end if;
  end if;
  if v_key is not null then
    if v_key ~ '\s' or length(v_key) < 8 then
      raise exception 'that does not look like an API key (no spaces, at least 8 characters)';
    end if;
    if v_base is null and not (p_slot = 'image_gen' and v_provider = 'replicate') then
      raise exception 'give the endpoint together with the key: a key is only ever sent to the address it was entered for';
    end if;
    if v_model is null and p_slot <> 'image_gen' then
      raise exception 'name the model together with the key';
    end if;
  end if;
  v_host := public.semasa_ai_key_host(p_slot, v_provider, v_base);

  select * into v_old from public.semasa_ai_config where slot = p_slot;
  insert into public.semasa_ai_config as c (slot, provider, base_url, model, edit_model, updated_by, updated_at)
  values (p_slot, v_provider, v_base, v_model, v_edit, auth.uid(), now())
  on conflict (slot) do update
    set provider = excluded.provider, base_url = excluded.base_url, model = excluded.model,
        edit_model = excluded.edit_model, updated_by = excluded.updated_by, updated_at = now();

  if v_key is not null then
    insert into public.semasa_ai_secrets (slot, api_key, updated_at) values (p_slot, v_key, now())
    on conflict (slot) do update set api_key = excluded.api_key, updated_at = now();
    update public.semasa_ai_config set key_hint = '…' || right(v_key, 4), key_host = v_host where slot = p_slot;
  elsif p_clear_key or (v_old.key_host is not null and v_old.key_host is distinct from v_host) then
    v_dropped := not p_clear_key and exists (select 1 from public.semasa_ai_secrets where slot = p_slot);
    delete from public.semasa_ai_secrets where slot = p_slot;
    update public.semasa_ai_config set key_hint = null, key_host = null where slot = p_slot;
  end if;

  return (select to_jsonb(c) || jsonb_build_object('key_dropped', v_dropped)
            from public.semasa_ai_config c where c.slot = p_slot);
end $$;

create or replace function public.semasa_clear_ai_slot(p_slot text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the AI settings' using errcode = '42501';
  end if;
  delete from public.semasa_ai_config where slot = p_slot;     -- the key goes with it (on delete cascade)
end $$;

revoke all on function public.semasa_save_ai_slot(text, text, text, text, text, text, boolean) from public, anon;
revoke all on function public.semasa_clear_ai_slot(text) from public, anon;
grant execute on function public.semasa_save_ai_slot(text, text, text, text, text, text, boolean) to authenticated;
grant execute on function public.semasa_clear_ai_slot(text) to authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select (count(*) = 2)::int from information_schema.tables
--             where table_name in ('semasa_ai_config', 'semasa_ai_secrets')),
--          (select (count(*) = 0)::int from pg_policies where tablename = 'semasa_ai_secrets'),
--          (select (count(*) = 2)::int from pg_proc where proname in ('semasa_save_ai_slot', 'semasa_clear_ai_slot'));
