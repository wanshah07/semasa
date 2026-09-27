-- Semasa · fixes from the full review of 27 Sep 2026 (Wan: "find any bugs and blockers and fix it immediatly").
-- Run ONCE in the SQL editor, after 001–016. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): only Semasa's own tables, triggers, functions and storage policies (all named
-- semasa…) are touched. No other app's table, policy or function is read or changed.
--
-- 1. An approved post's pictures cannot be changed or deleted from the page. The post gate watched the post's own
--    columns only, so a picture could be deleted, or sent back to be redrawn, after Wan approved the post, and the post
--    stayed approved (tested: deleted, and redrawn with a new picture). Now the page must return the post to draft first.
-- 2. An approved post that gains a hard flag on save goes back to draft, instead of failing with the raw error
--    "violates check constraint semasa_posts_approve_clean". The page cannot write posted_at or archived_at.
-- 3. The anon key can no longer LIST the storage buckets. Pictures still open by their public address (a public
--    bucket serves /object/public/ without any policy); the page reads nothing else. Before this, anyone holding the
--    published anon key could list every uploaded reference and every generated picture, including unapproved artwork.
-- 4. The worker's own writes to Tetapan (the sweep's clock, the trial, the FAQ sorter) no longer show as
--    "Tetapan diubah" in the log.
-- 5. The full list of job kinds, and the worker clock counting every queue, again here, so re-running an older file
--    can never narrow them (005, 006, 009, 011 and 013 now carry the same full versions too).

-- 1 ---------------------------------------------------------------------------------------------------------------
create or replace function public.semasa_media_gate() returns trigger
language plpgsql security definer set search_path = public as $$
declare
  v_post uuid;
begin
  if auth.uid() is null then
    return coalesce(new, old);          -- the worker (service_role) finishes jobs; its own gate is attach_media_to_draft
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
-- A second gate, run after semasa_posts_gate (triggers of one kind fire in name order), adding only what it lacked.
-- Kept apart so re-running 005 or 006, which redefine the first gate, cannot remove these rules.
create or replace function public.semasa_posts_gate_v2() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null then
    return new;                          -- the publisher and the worker
  end if;
  if tg_op = 'INSERT' then
    new.posted_at := null; new.archived_at := null;
    return new;
  end if;
  new.posted_at := old.posted_at;
  new.archived_at := old.archived_at;
  if old.status = 'approved' and new.status = 'approved' and coalesce(new.hard_flags, 0) > 0 then
    new.status := 'draft'; new.approved_by := null; new.approved_at := null;
  end if;
  return new;
end $$;
drop trigger if exists semasa_posts_gate_v2 on public.semasa_posts;
create trigger semasa_posts_gate_v2 before insert or update on public.semasa_posts
  for each row execute function public.semasa_posts_gate_v2();
revoke execute on function public.semasa_posts_gate_v2() from public, anon, authenticated;

-- 3 ---------------------------------------------------------------------------------------------------------------
drop policy if exists "semasa generated: public read" on storage.objects;
drop policy if exists "semasa reference: public read" on storage.objects;
-- a signed-in uploader still sees their own files (the storage API needs it to delete them)
drop policy if exists "semasa reference: owner read" on storage.objects;
create policy "semasa reference: owner read"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'semasa-reference' and (storage.foldername(name))[1] = auth.uid()::text);

-- 4 ---------------------------------------------------------------------------------------------------------------
create or replace function public.semasa_log_settings() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  -- a PERSON's change of a setting (the worker's own writes: the sweep's clock, the trial, the FAQ sorter, are not)
  if auth.uid() is null or new.key in ('faq_sheet', 'log_sheet', 'telegram') or new.value is not distinct from old.value then
    return new;
  end if;
  perform public.semasa_log_write('info', 'settings', 'settings.changed',
    'Tetapan diubah: ' || case new.key when 'brand' then 'slot dan giliran' when 'faq' then 'kategori FAQ'
                                        when 'bahasa' then 'tabung perkataan Indonesia'
                                        when 'publishing' then 'suis penerbitan' else new.key end,
    'semasa_settings', new.key, jsonb_build_object('key', new.key));
  return new;
exception when others then
  raise warning 'semasa_log_settings: %', sqlerrm;
  return new;
end $$;

-- 5 ---------------------------------------------------------------------------------------------------------------
alter table public.media_generations drop constraint if exists media_generations_mode_check;
alter table public.media_generations add constraint media_generations_mode_check
  check (mode in ('recreate', 'prompt', 'slides', 'clip', 'fragrance') and (mode <> 'recreate' or reference_url is not null));

create or replace function public.semasa_clock_worker() returns text
language plpgsql security definer set search_path = public as $$
-- ONE body in every file that defines this function (009, 011, 013, 017): re-running an older file must never drop what
-- a later one added. A table or column a later file creates is counted only once it exists.
declare
  v_waiting int := 0;
begin
  select count(*) into v_waiting from public.media_generations
   where status = 'pending' or (status = 'processing' and updated_at < now() - interval '60 minutes');
  v_waiting := v_waiting + (select count(*) from public.semasa_ideas
   where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  begin
    v_waiting := v_waiting + (select count(*) from public.semasa_faqs
     where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  exception when undefined_table then null;            -- 007 not run yet
  end;
  begin
    v_waiting := v_waiting + (select count(*) from public.semasa_videos
     where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  exception when undefined_table then null;            -- 011 not run yet
  end;
  begin
    -- a stuck link is counted whatever its attempts: the worker ends it in error rather than leave it spinning
    v_waiting := v_waiting + (select count(*) from public.semasa_watch
     where status = 'pending' or (status = 'working' and claimed_at < now() - interval '30 minutes'));
  exception when undefined_table or undefined_column then null;   -- 012 / 013 not run yet
  end;
  if v_waiting = 0 then
    return 'nothing waiting';
  end if;
  return public.semasa_clock_dispatch('media_pending');
end $$;
revoke execute on function public.semasa_clock_worker() from public, anon, authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from pg_trigger where tgname = 'semasa_media_gate'),
--          (select count(*) from pg_trigger where tgname = 'semasa_posts_gate_v2'),
--          (select (count(*) = 0)::int from pg_policies where tablename = 'objects'
--             and policyname in ('semasa generated: public read', 'semasa reference: public read'));
