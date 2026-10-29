-- Semasa · Postiz-first publishing with revision-bound provider/account/media approval.
-- Run ONCE after 001–051. Idempotent and non-destructive; does not enable publishing or change existing routes.

alter table public.semasa_posts add column if not exists provider text;
alter table public.semasa_posts add column if not exists approval_token text;
alter table public.semasa_posts drop constraint if exists semasa_posts_provider_check;
alter table public.semasa_posts add constraint semasa_posts_provider_check
  check (provider is null or provider in ('postiz', 'buffer', 'composio'));

create or replace function public.semasa_posts_gate() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then return new; end if;
  if tg_op = 'INSERT' then
    if new.status not in ('draft', 'rejected') then raise exception 'semasa: a new post starts as draft'; end if;
    new.approved_by := null; new.approved_at := null; new.approval_token := null;
    new.published := '{}'::jsonb; new.errors := '{}'::jsonb;
    return new;
  end if;
  if new.status in ('scheduled', 'posted') and new.status is distinct from old.status then
    raise exception 'semasa: only the publisher sets %', new.status;
  end if;
  if old.status in ('scheduled', 'posted') and new.status is distinct from old.status then
    raise exception 'semasa: a % post cannot be moved back from the page', old.status;
  end if;
  new.published := old.published; new.errors := old.errors;
  if new.status = 'approved' and old.status is distinct from 'approved' then
    new.approved_by := auth.uid(); new.approved_at := now();
  elsif new.status = 'approved' and (new.text is distinct from old.text or new.citation is distinct from old.citation
        or new.media_ids is distinct from old.media_ids or new.date is distinct from old.date
        or new.slot is distinct from old.slot or new.lang is distinct from old.lang
        or new.stream is distinct from old.stream or new.slides is distinct from old.slides
        or new.channels is distinct from old.channels or new.provider is distinct from old.provider) then
    new.status := 'draft'; new.approved_by := null; new.approved_at := null; new.approval_token := null;
  elsif new.status <> 'approved' then
    new.approved_by := null; new.approved_at := null; new.approval_token := null;
  else
    new.approved_by := old.approved_by; new.approved_at := old.approved_at;
    new.approval_token := old.approval_token;
  end if;
  return new;
end $$;

-- Staged settings example (SQL editor only; browser still cannot edit publishing):
-- update public.semasa_settings set value = value || '{"default_provider":"postiz"}'::jsonb where key = 'publishing';
-- update public.semasa_settings set value = value || '{"postiz":{"enabled":true,"linkedin":"POSTIZ_INTEGRATION_ID","facebook":"...","instagram":"...","threads":"..."}}'::jsonb where key = 'channels';
-- Existing posts with provider NULL retain Buffer/Composio routing until explicitly edited and re-approved.
