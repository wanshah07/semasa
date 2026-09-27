-- Semasa · two trigger fixes found by the review of 27 Sep 2026, after 017 went live.
-- Run ONCE in the SQL editor, after 001–017. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): only two Semasa trigger functions are replaced (semasa_media_gate,
-- semasa_ideas_no_rewrite). No table, policy or data is changed, and no other app's object is touched.
--
-- 1. 017's picture lock refused ANY update to a picture in an approved post, including the one Postgres makes itself
--    when something the picture points at is deleted (idea_id, prompt_id, post_id and created_by are all
--    "on delete set null"). So deleting an idea or a saved prompt whose picture sat in an approved post failed with
--    "this picture belongs to an approved post", and once the post was posted it could never be deleted. Now an update
--    that changes only those link columns goes through; the picture itself is still locked.
-- 2. The worker puts back ideas its dead runner left "working" in one update. If any one of them already had an
--    approved post, 010's trigger raised and the WHOLE update failed, so every stuck idea stayed stuck and the clock
--    woke the worker every 10 minutes for nothing. Now that one idea is marked drafted (its draft was approved) and the
--    others go back to the queue. The page's own "try again" on such an idea is still refused, as before.
-- 010 and 017 carry the same bodies now, so re-running either can never put the old ones back.

-- 1 ---------------------------------------------------------------------------------------------------------------
create or replace function public.semasa_media_gate() returns trigger
language plpgsql security definer set search_path = public as $$
-- ONE body in every file that defines this function (017, 018).
declare
  v_post uuid;
  v_links text[] := array['idea_id', 'prompt_id', 'post_id', 'created_by', 'updated_at'];
begin
  if auth.uid() is null then
    return coalesce(new, old);          -- the worker (service_role) finishes jobs; its own gate is attach_media_to_draft
  end if;
  -- Deleting an idea, a prompt, a draft or a user clears the link on this row (on delete set null). That is not a change
  -- to the picture, and refusing it made those deletes fail for any idea or prompt whose picture sat in an approved post.
  if tg_op = 'UPDATE' and (to_jsonb(new) - v_links) = (to_jsonb(old) - v_links) then
    return new;
  end if;
  select id into v_post from public.semasa_posts
   where status in ('approved', 'scheduled', 'posted') and old.id = any(media_ids) limit 1;
  if v_post is not null then
    raise exception 'semasa: this picture belongs to an approved post: return the post to draft first, then change it'
      using errcode = '42501';
  end if;
  return coalesce(new, old);
end $$;
drop trigger if exists semasa_media_gate on public.media_generations;
create trigger semasa_media_gate before update or delete on public.media_generations
  for each row execute function public.semasa_media_gate();
revoke execute on function public.semasa_media_gate() from public, anon, authenticated;

-- 2 ---------------------------------------------------------------------------------------------------------------
create or replace function public.semasa_ideas_no_rewrite() returns trigger
language plpgsql security definer set search_path = public as $$
-- ONE body in every file that defines this function (010, 018).
declare
  v_post record;
begin
  if new.status = 'new' and old.status is distinct from 'new' then
    select id, status, date, hook into v_post from public.semasa_posts
     where idea_id = new.id and status in ('approved', 'scheduled', 'posted')
     order by created_at desc limit 1;
    if found then
      -- The worker putting back an idea its dead runner left `working` (db.requeue_stale): the draft it had written was
      -- approved since, so the idea is done. Raising here failed the whole recovery and left every stuck idea stuck.
      if auth.uid() is null and old.status = 'working' then
        new.status := 'drafted'; new.error := null;
        return new;
      end if;
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

-- Check (should print 1 | 1 | 1):
--   select (select (prosrc like '%v_links%')::int from pg_proc where proname = 'semasa_media_gate'),
--          (select (prosrc like '%old.status = ''working''%')::int from pg_proc where proname = 'semasa_ideas_no_rewrite'),
--          (select count(*) from pg_trigger where tgname in ('semasa_media_gate', 'semasa_ideas_no_rewrite')) / 2;
