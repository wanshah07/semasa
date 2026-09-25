-- Semasa · carousel slides · run ONCE in the SQL editor on a database that already ran 001–005.
-- Idempotent: safe to run again. A fresh install gets all of this from 005 and does not need it.
--
-- SAFE IN A SHARED PROJECT (KPI): it touches only semasa_ideas, semasa_posts, media_generations
-- and the semasa_posts_gate function. No other app's table, policy or function is read or changed.
--
-- What it adds:
--   semasa_ideas.make_slides   the idea asks the writer for a carousel too
--   semasa_posts.slides        the carousel's words, [{title, points[]}], edited in the Post tab
--   media_generations mode     'slides': drawn by the worker from words (no AI, no key, no cost)
--   the approval gate          changing the slides of an APPROVED post sends it back to draft,
--                              exactly as changing its caption does

alter table public.semasa_ideas add column if not exists make_slides boolean not null default false;
alter table public.semasa_posts add column if not exists slides jsonb not null default '[]'::jsonb;

alter table public.media_generations drop constraint if exists media_generations_mode_check;
alter table public.media_generations add constraint media_generations_mode_check
  check (mode in ('recreate', 'prompt', 'slides') and (mode <> 'recreate' or reference_url is not null));

-- Same function as 005 (kept identical by backend/tests/test_sql.py), now watching `slides` too.
create or replace function public.semasa_posts_gate() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then
    return new;                       -- service_role / SQL editor: the publisher itself
  end if;
  if tg_op = 'INSERT' then
    if new.status not in ('draft', 'rejected') then
      raise exception 'semasa: a new post starts as draft';
    end if;
    new.approved_by := null; new.approved_at := null;
    new.published := '{}'::jsonb; new.errors := '{}'::jsonb;
    return new;
  end if;
  if new.status in ('scheduled', 'posted') and new.status is distinct from old.status then
    raise exception 'semasa: only the publisher sets %', new.status;
  end if;
  if old.status in ('scheduled', 'posted') and new.status is distinct from old.status then
    raise exception 'semasa: a % post cannot be moved back from the page', old.status;
  end if;
  new.published := old.published;
  new.errors := old.errors;
  if new.status = 'approved' and old.status is distinct from 'approved' then
    new.approved_by := auth.uid(); new.approved_at := now();
  elsif new.status = 'approved' and (new.text is distinct from old.text or new.citation is distinct from old.citation
        or new.media_ids is distinct from old.media_ids or new.date is distinct from old.date
        or new.slot is distinct from old.slot or new.lang is distinct from old.lang
        or new.stream is distinct from old.stream or new.slides is distinct from old.slides) then
    new.status := 'draft'; new.approved_by := null; new.approved_at := null;
  elsif new.status <> 'approved' then
    new.approved_by := null; new.approved_at := null;
  else
    new.approved_by := old.approved_by; new.approved_at := old.approved_at;
  end if;
  return new;
end $$;

-- Check (should print: make_slides | slides | 1):
--   select (select count(*) from information_schema.columns where table_name = 'semasa_ideas' and column_name = 'make_slides') as make_slides,
--          (select count(*) from information_schema.columns where table_name = 'semasa_posts' and column_name = 'slides') as slides,
--          (select count(*) from pg_constraint where conname = 'media_generations_mode_check'
--             and pg_get_constraintdef(oid) like '%slides%') as mode_allows_slides;
