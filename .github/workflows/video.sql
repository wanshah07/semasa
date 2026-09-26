-- Semasa · Video: a long video (a YouTube ceramah, or a link to a video file) becomes short clips and draft posts.
-- Run ONCE in the SQL editor, after 001–010. Idempotent: safe to run again.
--
-- Wan, 26 Sep 2026: "add segment that can cut, edit video for short video such as youtube video (ceramah agama) to
-- able act idea and post, allow me to paste youtube page to you scrape, once approve can cut edit and create into
-- short video".
--
-- SAFE IN A SHARED PROJECT (KPI): it creates one table (semasa_videos), widens one check on media_generations
-- (mode 'clip'), replaces two semasa_* functions with a version that also counts videos, and adds one trigger.
-- No other app's table, policy or function is read or changed.
--
-- The flow:
--   1. the page adds a row (a link, and optionally a transcript Wan pasted) with status 'new';
--   2. the worker reads the video's details and words, asks the writer for 3–6 short clips, status 'ready';
--   3. Wan confirms he may use the video (rights), edits a clip, and approves it: the page queues a media job
--      (mode 'clip'); the worker cuts it to a 9:16 short with captions, stores it and writes a DRAFT post with it.
--      Nothing is published by this: the post goes through the same gate as every other post.

create table if not exists public.semasa_videos (
  id                uuid primary key default gen_random_uuid(),
  source_url        text        not null,
  source_kind       text        not null default 'youtube',  -- youtube | link (a direct or Google Drive video file)
  stream            text        not null default 'regulab',
  domain            text,
  angle             text,
  note              text        not null default '',         -- what Wan wants from it
  transcript_paste  text,                                    -- Wan's own copy of the transcript, used first
  status            text        not null default 'new',
  title             text,
  channel           text,
  channel_url       text,
  duration_s        int,
  thumbnail_url     text,
  upload_date       text,
  license           text,                                    -- what the source says ("Creative Commons", ...)
  transcript        jsonb       not null default '[]'::jsonb, -- [{s, e, t}] seconds and words
  transcript_source text,                                    -- pasted | subtitles | auto-captions | whisper | none
  clips             jsonb       not null default '[]'::jsonb, -- the writer's proposals
  rights            text,                                    -- own | permission | cc: Wan's statement, needed to cut
  rights_note       text,
  rights_by         uuid        references auth.users (id) on delete set null,
  rights_at         timestamptz,
  error             text,
  attempts          int         not null default 0,
  created_by        uuid        references auth.users (id) on delete set null,
  created_at        timestamptz not null default now(),
  updated_at        timestamptz not null default now(),
  constraint semasa_videos_status_check check (status in ('new', 'working', 'ready', 'error')),
  constraint semasa_videos_kind_check   check (source_kind in ('youtube', 'link')),
  constraint semasa_videos_stream_check check (stream in ('regulab', 'linkedin')),
  constraint semasa_videos_rights_check check (rights is null or rights in ('own', 'permission', 'cc'))
);
create index if not exists semasa_videos_status_idx on public.semasa_videos (status, created_at);

drop trigger if exists semasa_videos_set_updated_at on public.semasa_videos;
create trigger semasa_videos_set_updated_at before update on public.semasa_videos
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_videos enable row level security;
drop policy if exists "semasa videos: uploaders read" on public.semasa_videos;
create policy "semasa videos: uploaders read" on public.semasa_videos
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa videos: uploaders insert" on public.semasa_videos;
create policy "semasa videos: uploaders insert" on public.semasa_videos
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid() and status = 'new');
-- the page may re-queue (new), edit the clips, and record the rights; 'working' and 'ready' are the worker's
drop policy if exists "semasa videos: uploaders update" on public.semasa_videos;
create policy "semasa videos: uploaders update" on public.semasa_videos
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('new', 'ready', 'error'));
drop policy if exists "semasa videos: uploaders delete" on public.semasa_videos;
create policy "semasa videos: uploaders delete" on public.semasa_videos
  for delete to authenticated using (public.semasa_is_uploader());

-- a cut clip is a media job like any other, of its own mode
alter table public.media_generations drop constraint if exists media_generations_mode_check;
alter table public.media_generations add constraint media_generations_mode_check
  check (mode in ('recreate', 'prompt', 'slides', 'clip') and (mode <> 'recreate' or reference_url is not null));

do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'semasa_videos') then
    alter publication supabase_realtime add table public.semasa_videos;
  end if;
end $$;

-- A new or re-queued video wakes the worker at once (same dispatch as 009's clock, same Vault secrets).
create or replace function public.semasa_videos_wake() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  perform public.semasa_clock_dispatch('media_pending');
  return new;
exception when others then
  raise warning 'semasa_videos_wake: %', sqlerrm;
  return new;
end $$;
drop trigger if exists semasa_videos_wake on public.semasa_videos;
create trigger semasa_videos_wake after insert or update of status on public.semasa_videos
  for each row when (new.status = 'new') execute function public.semasa_videos_wake();

-- 009's net, now also counting videos waiting to be read (everything else exactly as 009 wrote it)
create or replace function public.semasa_clock_worker() returns text
language plpgsql security definer set search_path = public as $$
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
  v_waiting := v_waiting + (select count(*) from public.semasa_videos
   where status = 'new' or (status = 'working' and updated_at < now() - interval '30 minutes'));
  if v_waiting = 0 then
    return 'nothing waiting';
  end if;
  return public.semasa_clock_dispatch('media_pending');
end $$;
revoke execute on function public.semasa_clock_worker() from public, anon, authenticated;
revoke execute on function public.semasa_videos_wake() from public, anon, authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from information_schema.tables where table_name = 'semasa_videos'),
--          (select count(*) from pg_constraint where conname = 'media_generations_mode_check'
--             and pg_get_constraintdef(oid) like '%clip%'),
--          (select count(*) from pg_trigger where tgname = 'semasa_videos_wake');
