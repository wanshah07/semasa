-- 098 · A model and a reasoning effort for each EXTRA ChatGPT account (Wan, 26 Nov 2026: "make sure extra chatgpt can add model and
-- reasoning if possible").
--
-- 095 already kept a `model` for every extra account (the chat model that calls the picture tool) but the page never showed it, so
-- every account asked with the default and an account whose plan names its models differently could not be told which one. This
-- adds the reasoning effort the chat model is asked to think with ('' = send nothing, the model decides; minimal, low, medium,
-- high), shows both in the status, and one function the page calls to save them. The worker sends `reasoning.effort` only when one
-- is set, and asks again without it when ChatGPT refuses the field for that model (chatgpt_login.py). Safe to re-run.

alter table public.semasa_chatgpt_accounts add column if not exists reasoning text not null default '';
alter table public.semasa_chatgpt_accounts drop constraint if exists semasa_chatgpt_accounts_reasoning_check;
alter table public.semasa_chatgpt_accounts add constraint semasa_chatgpt_accounts_reasoning_check
  check (reasoning in ('', 'minimal', 'low', 'medium', 'high'));

create or replace function public.semasa_chatgpt_accounts_status() returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may see the ChatGPT logins' using errcode = '42501';
  end if;
  return coalesce((select jsonb_agg(jsonb_build_object(
    'id', a.id, 'account', a.account, 'enabled', a.enabled, 'connected_at', a.connected_at, 'checked_at', a.checked_at,
    'last_ok_at', a.last_ok_at, 'last_error', a.last_error, 'last_error_at', a.last_error_at, 'limit_until', a.limit_until,
    'model', a.model, 'reasoning', a.reasoning, 'max_images', a.max_images)
    order by a.id) from public.semasa_chatgpt_accounts a), '[]'::jsonb);
end $$;

-- the model, the reasoning effort and how many pictures a film may draw with this account (null leaves a value as it is)
create or replace function public.semasa_chatgpt_account_config(p_id text, p_model text default null, p_reasoning text default null,
                                                                p_max integer default null) returns jsonb
language plpgsql security definer set search_path = public as $$
begin
  if not public.semasa_is_uploader() then
    raise exception 'only a Semasa uploader may change the ChatGPT logins' using errcode = '42501';
  end if;
  if p_model is not null and (btrim(p_model) = '' or p_model !~ '^[A-Za-z0-9._:-]{1,64}$') then
    raise exception 'the model name is letters, digits and . _ : - only';
  end if;
  if p_reasoning is not null and p_reasoning not in ('', 'minimal', 'low', 'medium', 'high') then
    raise exception 'the reasoning effort is minimal, low, medium or high (or empty)';
  end if;
  if p_max is not null and p_max not between 1 and 8 then
    raise exception 'pictures a film is 1 to 8';
  end if;
  update public.semasa_chatgpt_accounts set
    model = coalesce(nullif(btrim(p_model), ''), model), reasoning = coalesce(p_reasoning, reasoning),
    max_images = coalesce(p_max, max_images), updated_by = auth.uid(), updated_at = now()
  where id = p_id;
  if not found then
    raise exception 'no such ChatGPT account';
  end if;
  return public.semasa_chatgpt_accounts_status();
end $$;

revoke execute on function public.semasa_chatgpt_account_config(text, text, text, integer) from public, anon;
grant execute on function public.semasa_chatgpt_account_config(text, text, text, integer) to authenticated;
