-- 044 · A separate AI slot for motion video, and a motion made from an idea (Wan, 23 Oct 2026: "make the idea as short motion
-- video, add new separate API for motion video").
--
--   slot 'motion'   the writer that writes the HyperFrames composition (backend/semasa/motion.py). Same shape as the text reader:
--                   provider openai | anthropic, endpoint, model, a key bound to its endpoint. Empty = the AI team's text router
--                   picks (supabase/041). If the motion writer is down the router's other robots still answer.
--   idea_id         the idea a motion was made from, so the Ideas tab can show it was made.
--
-- Re-creates semasa_save_ai_slot / semasa_clear_ai_slot with the fourth slot (the bodies are 016's, only the slot list changes).
-- SAFE IN A SHARED PROJECT (KPI): semasa_ai_* and semasa_motions only. Run once after 041-043; re-running changes nothing.

alter table public.semasa_ai_config drop constraint if exists semasa_ai_config_slot_check;
alter table public.semasa_ai_config add constraint semasa_ai_config_slot_check
  check (slot in ('reader', 'image_gen', 'image_reader', 'motion'));
alter table public.semasa_ai_config drop constraint if exists semasa_ai_config_provider_check;
alter table public.semasa_ai_config add constraint semasa_ai_config_provider_check check (
  provider is null
  or (slot in ('reader', 'image_reader', 'motion') and provider in ('openai', 'anthropic'))
  or (slot = 'image_gen' and provider in ('cloudflare', 'openai', 'replicate')));

alter table public.semasa_motions add column if not exists idea_id uuid references public.semasa_ideas (id) on delete set null;
create index if not exists semasa_motions_idea_idx on public.semasa_motions (idea_id);

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
  if p_slot not in ('reader', 'image_gen', 'image_reader', 'motion') then
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

revoke all on function public.semasa_save_ai_slot(text, text, text, text, text, text, boolean) from public, anon;
grant execute on function public.semasa_save_ai_slot(text, text, text, text, text, text, boolean) to authenticated;
-- semasa_clear_ai_slot(p_slot) deletes whatever slot it is given, so it already serves 'motion'.
