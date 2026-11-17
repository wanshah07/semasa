-- Semasa · Import video (Wan, 17 Nov 2026: an MP4 made OUTSIDE Semasa, by Nous Hermes / Nexabot / huashu-motion, is sent in and
-- posted through the normal path).
-- Run ONCE in the SQL editor, after 086. Idempotent: safe to run again.
--
-- What it does
--   1. `semasa_import_tokens`: the keys an outside agent sends the video with. Wan makes one on the page (Motion → Import video);
--      the plain token is shown ONCE, here only its sha256 is kept, so a database read can never give a token back. A token can be
--      revoked at any time. The page reads id, label, created_at, last_used_at and revoked_at; the hash column is not readable by
--      any browser login at all (column grant).
--   2. `semasa_import_token_create(label)` and `semasa_import_token_revoke(id)`: the only ways a token is made or stopped, for a
--      signed-in Semasa uploader (security definer, like 069's link code).
--   3. `semasa_video_imports`: one row per video received. The Edge Function `semasa-import-video` (service role, the bearer token
--      is its gate) writes it as `received` with the file already in the public bucket semasa-generated under imports/<id>.mp4 (or
--      the address the agent gave). The Motion worker (backend/semasa/video_import.py) then checks the file and the caption, and
--      ends the row as `done` (a Motion film row exists and a DRAFT post waits for Wan) or `error` with a human reason.
--      Why a table of its own and not a `pending` Motion film: the Motion worker makes films from a storyboard, and 071's guard
--      refuses any film turning `done` without an approved storyboard. An import has no storyboard; the film row is inserted only
--      once the file has passed, already `done`, and 071 is untouched.
--   4. A trigger: a new `received` row wakes the Motion worker (the same dispatch 086's clock uses), so the import is checked in
--      minutes and not at the next hourly run. If the dispatch fails nothing is lost: the hourly schedule is the net.
--
-- THE GATE IS UNTOUCHED. Nothing here, and nothing in the worker, approves, schedules or posts. The import makes a DRAFT post
-- (semasa_posts_gate stamps nothing on a draft); Wan's own Approve click, in the page or on Telegram, is the only gate.
--
-- Limits (the numbers are the repo's own, none invented): a stored file is at most 50 MB (bucket semasa-generated, 003), the
-- posted copy at most 48 MB (video.MAX_OUT_BYTES) and at most 90 s (video.MAX_CLIP).
-- Not applied by anyone but Wan.

-- 1 · tokens ------------------------------------------------------------------------------------------------------------------
create table if not exists public.semasa_import_tokens (
  id           uuid primary key default gen_random_uuid(),
  label        text not null,
  token_hash   text not null unique,                                     -- sha256 (hex) of the token; the token is never stored
  created_by   uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  last_used_at timestamptz,
  revoked_at   timestamptz,
  constraint semasa_import_tokens_label_check check (char_length(btrim(label)) between 1 and 60)
);

alter table public.semasa_import_tokens enable row level security;
drop policy if exists "semasa import tokens: uploaders read" on public.semasa_import_tokens;
create policy "semasa import tokens: uploaders read" on public.semasa_import_tokens
  for select to authenticated using (public.semasa_is_uploader());
-- no insert / update / delete policy: a token is made and revoked by the two functions below, never by a direct write
revoke all on public.semasa_import_tokens from anon, authenticated;
grant select (id, label, created_at, last_used_at, revoked_at) on public.semasa_import_tokens to authenticated;

create or replace function public.semasa_import_token_create(p_label text) returns text
language plpgsql security definer set search_path = public, extensions as $$
declare
  v_token text;
  v_label text := btrim(coalesce(p_label, ''));
begin
  if auth.uid() is null or not public.semasa_is_uploader() then
    raise exception 'semasa: sign in first';
  end if;
  if char_length(v_label) not between 1 and 60 then
    raise exception 'semasa: give the token a name of 1 to 60 characters';
  end if;
  if (select count(*) from public.semasa_import_tokens where revoked_at is null) >= 10 then
    raise exception 'semasa: ten tokens are in use; revoke one first';
  end if;
  v_token := 'smi_' || encode(extensions.gen_random_bytes(24), 'hex');   -- 192 random bits; shown once, below
  insert into public.semasa_import_tokens (label, token_hash, created_by)
    values (v_label, encode(extensions.digest(v_token, 'sha256'), 'hex'), auth.uid());
  return v_token;
end $$;

create or replace function public.semasa_import_token_revoke(p_id uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or not public.semasa_is_uploader() then
    raise exception 'semasa: sign in first';
  end if;
  update public.semasa_import_tokens set revoked_at = now() where id = p_id and revoked_at is null;
end $$;

revoke execute on function public.semasa_import_token_create(text), public.semasa_import_token_revoke(uuid) from public, anon;
grant execute on function public.semasa_import_token_create(text), public.semasa_import_token_revoke(uuid) to authenticated;

-- 2 · the imports ---------------------------------------------------------------------------------------------------------------
create table if not exists public.semasa_video_imports (
  id              uuid primary key default gen_random_uuid(),
  token_id        uuid references public.semasa_import_tokens (id) on delete set null,
  token_label     text not null default '',                              -- the label at the time: it survives a deleted token
  status          text not null default 'received',                      -- received | working | done | error
  source          text not null default '',                              -- free text from the sender, e.g. 'hermes'
  idempotency_key text,
  fingerprint     text not null default '',                              -- sha256 of the request (same key + other request = 409)
  source_url      text not null default '',                              -- an https address the worker fetches, when no file was sent
  stored_path     text not null default '',                              -- imports/<id>.mp4 in semasa-generated, when a file was sent
  bytes           bigint not null default 0,
  params          jsonb not null default '{}'::jsonb,                    -- title, caption(s), lang, stream, channels, date, slot
  error           text not null default '',                              -- why it ended in error (a sentence a person can act on)
  note            text not null default '',                              -- what the worker did that Wan should know (a copy made, a flag)
  attempts        int not null default 0,
  motion_id       uuid references public.semasa_motions (id) on delete set null,
  post_id         uuid references public.semasa_posts (id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint semasa_video_imports_status_check check (status in ('received', 'working', 'done', 'error'))
);

-- the same key twice from one token is one import (a second insert is refused; the function answers with the first)
create unique index if not exists semasa_video_imports_key_idx on public.semasa_video_imports (token_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists semasa_video_imports_status_idx on public.semasa_video_imports (status, created_at);
create index if not exists semasa_video_imports_token_idx on public.semasa_video_imports (token_id, created_at desc);

drop trigger if exists semasa_video_imports_set_updated_at on public.semasa_video_imports;
create trigger semasa_video_imports_set_updated_at before update on public.semasa_video_imports
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_video_imports enable row level security;
drop policy if exists "semasa video imports: uploaders read" on public.semasa_video_imports;
create policy "semasa video imports: uploaders read" on public.semasa_video_imports
  for select to authenticated using (public.semasa_is_uploader());
-- writes are the Edge Function's and the worker's (service role); a browser only reads
revoke all on public.semasa_video_imports from anon, authenticated;
grant select on public.semasa_video_imports to authenticated;

-- 3 · a new import wakes the Motion worker -----------------------------------------------------------------------------------
create or replace function public.semasa_video_import_received() returns trigger
language plpgsql security definer set search_path = public as $$
begin
  if new.status = 'received' then
    perform public.semasa_clock_dispatch('motion_pending');
  end if;
  return new;
exception when others then
  raise warning 'semasa_video_import_received: %', sqlerrm;
  return new;
end $$;
revoke execute on function public.semasa_video_import_received() from public, anon, authenticated;

drop trigger if exists semasa_video_import_received on public.semasa_video_imports;
create trigger semasa_video_import_received after insert on public.semasa_video_imports
  for each row execute function public.semasa_video_import_received();

notify pgrst, 'reload schema';

-- Check (should print 1 and 1):
select (select count(*) from information_schema.tables where table_schema = 'public' and table_name = 'semasa_import_tokens') as tokens_table,
       (select count(*) from information_schema.tables where table_schema = 'public' and table_name = 'semasa_video_imports') as imports_table;
-- Stop every key at once:
--   update public.semasa_import_tokens set revoked_at = now() where revoked_at is null;
