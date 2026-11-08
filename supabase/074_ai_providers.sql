-- 074 · Extra AI providers, added from the page (Wan, Nov 2026: the owner adds an Anthropic key, a second KiosAPI key or any other
-- OpenAI-compatible gateway on the API tab, and it becomes a robot the whole backend can use: Wanshah 6, 7, ...).
--
-- Two tables, the same split as 016 (semasa_ai_config / semasa_ai_secrets):
--   semasa_ai_providers          what the page may SEE: slug, name, dialect, endpoint, default model, the key's last four
--                                characters, the host the key is bound to, on/off, the jobs it may do, notes.
--   semasa_ai_provider_secrets   the key itself. NO policy, revoked from the page roles: once saved a key never comes back to
--                                the browser; only the worker (service_role) and the edge functions read it.
--   A key is BOUND to the endpoint it was entered with (key_host, the same rule as semasa_ai_key_host). Change the endpoint
--   without typing the key again and the key is dropped, so a key is never sent to a host it was not meant for.
--
-- The five built-in robots keep their own cards and their own keys: rootsys, mireld, kiosapi (GitHub secrets and the AI slots),
-- gemini (061, several keys) and chatgpt (Wan's login). Those ids are refused here. Gemini is NOT a dialect here: its keys go on
-- the Gemini card, where they are picked automatically.
--
-- jobs: which of the router's jobs may use the robot (backend/semasa/ai_team.py): reader (every worker: scrape, Otak AI, receipts,
-- billing, CRM), ideas (the idea writer and picture reader), motion (the Motion writer), chat (the AI chat page and Telegram's fast
-- answers: the edge functions read this table and the secret with the service role). Default: all four.
--
-- SAFE IN A SHARED PROJECT (KPI): two new tables and two functions, all prefixed semasa_. Re-runnable.

create table if not exists public.semasa_ai_providers (
  id          text primary key check (id ~ '^[a-z0-9-]{2,24}$'),      -- the robot's slug (semasa_api_status.slug, pins, usage)
  name        text not null check (length(btrim(name)) between 1 and 60),
  dialect     text not null check (dialect in ('openai', 'anthropic')),
  base_url    text not null check (base_url ~ '^https://[^/:?#\s]+'),
  model       text not null default '',                                -- the default model asked (the router may search others)
  key_hint    text,                                                     -- "…abcd": enough to recognise the key, never to use it
  key_host    text,                                                     -- the host the key was entered for
  enabled     boolean not null default true,
  jobs        text[] not null default '{reader,ideas,motion,chat}',
  notes       text,
  created_by  uuid references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table if not exists public.semasa_ai_provider_secrets (
  id          text primary key references public.semasa_ai_providers (id) on delete cascade,
  api_key     text not null,
  updated_at  timestamptz not null default now()
);

alter table public.semasa_ai_providers        enable row level security;
alter table public.semasa_ai_provider_secrets enable row level security;

drop policy if exists "semasa ai providers: uploaders read" on public.semasa_ai_providers;
create policy "semasa ai providers: uploaders read" on public.semasa_ai_providers
  for select to authenticated using (public.semasa_is_uploader());
-- no write policy on the providers and no policy at all on the secrets: the page writes ONLY through the two functions below
revoke all on public.semasa_ai_providers        from anon, authenticated;
revoke all on public.semasa_ai_provider_secrets from anon, authenticated;
grant select on public.semasa_ai_providers to authenticated;

-- the page sees a row change (a save, a key dropped) without reloading
do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public'
                   and tablename = 'semasa_ai_providers') then
    execute 'alter publication supabase_realtime add table public.semasa_ai_providers';
  end if;
end $$;

create or replace function public.semasa_save_ai_provider(
  p_id text, p_name text, p_dialect text, p_base_url text, p_model text,
  p_api_key text default null, p_enabled boolean default true, p_jobs text[] default null, p_notes text default null
) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  v_id      text := lower(btrim(coalesce(p_id, '')));
  v_name    text := left(btrim(coalesce(p_name, '')), 60);
  v_dialect text := lower(btrim(coalesce(p_dialect, 'openai')));
  v_base    text := nullif(btrim(coalesce(p_base_url, '')), '');
  v_model   text := btrim(coalesce(p_model, ''));
  v_key     text := nullif(btrim(coalesce(p_api_key, '')), '');
  v_jobs    text[] := coalesce(p_jobs, '{reader,ideas,motion,chat}'::text[]);
  v_notes   text := nullif(left(btrim(coalesce(p_notes, '')), 400), '');
  v_host    text;
  v_old     public.semasa_ai_providers;
  v_dropped boolean := false;
  j         text;
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the AI providers' using errcode = '42501';
  end if;
  if v_id !~ '^[a-z0-9-]{2,24}$' then
    raise exception 'the id is 2 to 24 small letters, digits and dashes (it names the robot everywhere)';
  end if;
  if v_id in ('rootsys', 'mireld', 'kiosapi', 'gemini', 'chatgpt') then
    raise exception 'the id % is one of the built-in robots: those have their own cards', v_id;
  end if;
  if v_name = '' then
    raise exception 'give the provider a name';
  end if;
  if v_dialect = 'gemini' then
    raise exception 'a Gemini key goes on the Gemini card, where several keys are picked automatically';
  end if;
  if v_dialect not in ('openai', 'anthropic') then
    raise exception 'the dialect is openai (any OpenAI-compatible gateway) or anthropic';
  end if;
  if v_base is null then
    raise exception 'give the endpoint (an https:// API root)';
  end if;
  v_base := regexp_replace(v_base, '/+$', '');
  if v_base !~ '^https://[^/:?#\s]+' then
    raise exception 'the endpoint must start with https://';
  end if;
  foreach j in array v_jobs loop
    if j not in ('reader', 'ideas', 'motion', 'chat') then
      raise exception 'unknown job % (reader, ideas, motion, chat)', j;
    end if;
  end loop;
  if v_key is not null then
    if v_key ~ '\s' or length(v_key) < 8 then
      raise exception 'that does not look like an API key (no spaces, at least 8 characters)';
    end if;
    if v_model = '' then
      raise exception 'name the model together with the key';
    end if;
  end if;
  v_host := public.semasa_ai_key_host('provider', v_dialect, v_base);

  select * into v_old from public.semasa_ai_providers where id = v_id;
  insert into public.semasa_ai_providers as p (id, name, dialect, base_url, model, enabled, jobs, notes, created_by, created_at, updated_at)
  values (v_id, v_name, v_dialect, v_base, v_model, coalesce(p_enabled, true), v_jobs, v_notes, auth.uid(), now(), now())
  on conflict (id) do update
    set name = excluded.name, dialect = excluded.dialect, base_url = excluded.base_url, model = excluded.model,
        enabled = excluded.enabled, jobs = excluded.jobs, notes = excluded.notes, updated_at = now();

  if v_key is not null then
    insert into public.semasa_ai_provider_secrets (id, api_key, updated_at) values (v_id, v_key, now())
    on conflict (id) do update set api_key = excluded.api_key, updated_at = now();
    update public.semasa_ai_providers set key_hint = '…' || right(v_key, 4), key_host = v_host where id = v_id;
  elsif v_old.key_host is not null and v_old.key_host is distinct from v_host then
    -- the endpoint moved to another host and no new key was typed: the old key is not sent there
    v_dropped := exists (select 1 from public.semasa_ai_provider_secrets where id = v_id);
    delete from public.semasa_ai_provider_secrets where id = v_id;
    update public.semasa_ai_providers set key_hint = null, key_host = null where id = v_id;
  end if;

  return (select to_jsonb(p) || jsonb_build_object('key_dropped', v_dropped)
            from public.semasa_ai_providers p where p.id = v_id);
end $$;

create or replace function public.semasa_delete_ai_provider(p_id text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the AI providers' using errcode = '42501';
  end if;
  delete from public.semasa_ai_providers where id = lower(btrim(coalesce(p_id, '')));   -- the key goes with it (cascade)
  delete from public.semasa_api_status where slug = lower(btrim(coalesce(p_id, '')));    -- and its card on the API tab
end $$;

revoke all on function public.semasa_save_ai_provider(text, text, text, text, text, text, boolean, text[], text) from public, anon;
revoke all on function public.semasa_delete_ai_provider(text) from public, anon;
grant execute on function public.semasa_save_ai_provider(text, text, text, text, text, text, boolean, text[], text) to authenticated;
grant execute on function public.semasa_delete_ai_provider(text) to authenticated;

notify pgrst, 'reload schema';

-- Check (should print 1 | 1 | 1):
--   select (select (count(*) = 2)::int from information_schema.tables
--             where table_name in ('semasa_ai_providers', 'semasa_ai_provider_secrets')),
--          (select (count(*) = 0)::int from pg_policies where tablename = 'semasa_ai_provider_secrets'),
--          (select (count(*) = 2)::int from pg_proc where proname in ('semasa_save_ai_provider', 'semasa_delete_ai_provider'));
