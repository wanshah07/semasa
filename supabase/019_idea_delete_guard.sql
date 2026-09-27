-- Semasa · keep the "never write the same news twice" rule when an idea is deleted (review of 27 Sep 2026).
-- Run ONCE in the SQL editor, after 001–018. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): one Semasa trigger function and its trigger are added. No table, policy or data is
-- changed, and no other app's object is touched.
--
-- The worker finds an earlier post of the same news through the IDEA it came from (ideas.already_published: other
-- ideas with the same headline or link, then posts.idea_id). Deleting that idea set the post's idea_id to null, so
-- the next idea from the same headline found nothing and a published story was written again as a new draft — the
-- rule 010 enforces (Wan, 25 Sep 2026). Now an idea whose post is approved, scheduled or posted cannot be deleted by
-- a signed-in user; reject it instead. The worker (service_role) is not limited, and an idea whose draft was never
-- approved, or was rejected, still deletes as before.

create or replace function public.semasa_ideas_keep_published() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_post record;
begin
  if auth.uid() is null then
    return old;
  end if;
  select id, status, date, hook into v_post from public.semasa_posts
   where idea_id = old.id and status in ('approved', 'scheduled', 'posted')
   order by created_at desc limit 1;
  if found then
    raise exception 'semasa: this idea''s post is % (%): the idea is kept so the same news is never written again', v_post.status,
      coalesce(nullif(v_post.hook, ''), v_post.date::text, v_post.id::text)
      using hint = 'Reject the idea instead of deleting it.';
  end if;
  return old;
end $$;
drop trigger if exists semasa_ideas_keep_published on public.semasa_ideas;
create trigger semasa_ideas_keep_published before delete on public.semasa_ideas
  for each row execute function public.semasa_ideas_keep_published();
revoke execute on function public.semasa_ideas_keep_published() from public, anon, authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from pg_proc where proname = 'semasa_ideas_keep_published'),
--          (select (prosrc like '%auth.uid() is null%')::int from pg_proc where proname = 'semasa_ideas_keep_published'),
--          (select count(*) from pg_trigger where tgname = 'semasa_ideas_keep_published');
