-- Semasa · a published post is never written again, and is archived 24 hours after it went out
-- Run ONCE in the SQL editor after 001–009. Idempotent (safe to run again).
--
-- Wan, 25 Sep 2026: "for posted post, make sure it will not recreate as another draft, and will be auto compact and
-- archived after 24 hours posted".
--
-- 1. posted_at   the moment a post became `posted` (stamped here, whoever wrote the status)
-- 2. archived_at set by the publisher run 24 hours after posted_at, when it also compacts the row: only the captions
--                that were actually sent are kept, the page's old scan is cleared, and picture jobs made for the post
--                but never used are deleted with their files (backend/semasa/archive.py)
-- 3. an idea whose post is approved, scheduled or published cannot be sent back to the writer, from the page or
--    from anywhere else: that would write the same story as a second draft
--
-- SAFE IN A SHARED PROJECT (KPI): semasa_* tables and one semasa_* function each; nothing else is read or changed.

alter table public.semasa_posts add column if not exists posted_at   timestamptz;
alter table public.semasa_posts add column if not exists archived_at timestamptz;
create index if not exists semasa_posts_archive_idx on public.semasa_posts (status, archived_at, posted_at);

-- 1. stamp the moment of publishing (the publisher sets `posted`; the stamp cannot be forgotten by any writer)
create or replace function public.semasa_posts_posted_at() returns trigger
language plpgsql set search_path = public as $$
begin
  if new.status = 'posted' and (tg_op = 'INSERT' or old.status is distinct from 'posted') and new.posted_at is null then
    new.posted_at := now();
  end if;
  return new;
end $$;
drop trigger if exists semasa_posts_posted_at on public.semasa_posts;
create trigger semasa_posts_posted_at before insert or update on public.semasa_posts
  for each row execute function public.semasa_posts_posted_at();

-- 3. never write a published story again
create or replace function public.semasa_ideas_no_rewrite() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_post record;
begin
  if new.status = 'new' and old.status is distinct from 'new' then
    select id, status, date, hook into v_post from public.semasa_posts
     where idea_id = new.id and status in ('approved', 'scheduled', 'posted')
     order by created_at desc limit 1;
    if found then
      raise exception 'semasa: this idea already has a % post (%): it is not written again', v_post.status,
        coalesce(nullif(v_post.hook, ''), v_post.date::text, v_post.id::text)
        using hint = 'Start a new idea with a different angle if a follow-up is wanted.';
    end if;
  end if;
  return new;
end $$;
drop trigger if exists semasa_ideas_no_rewrite on public.semasa_ideas;
create trigger semasa_ideas_no_rewrite before update on public.semasa_ideas
  for each row execute function public.semasa_ideas_no_rewrite();

-- Check:
--   select status, count(*) filter (where archived_at is not null) as archived, count(*) from public.semasa_posts group by 1;
