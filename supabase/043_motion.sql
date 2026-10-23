-- 043 · Motion: a motion-graphics video from an idea or a link, written as an HTML composition by the AI and rendered to MP4
-- by HyperFrames on the runner (Wan, 23 Oct 2026: "in video segment, add motion segment that can create the motion video
-- from repo claude motion provide, using the token and appear the video ... add this skill/prompt to create motion, create
-- the video for this [link/idea]").
--
-- Flow: the page inserts a row (brief or link, size, seconds) with status 'pending' → the database wakes the worker
-- (repository_dispatch 'motion_pending', the same Vault token 036 uses) → backend/semasa/motion.py asks the AI team's
-- writer for the composition (HTML + GSAP, the HyperFrames contract), checks it with `hyperframes check`, repairs once,
-- renders it with `hyperframes render`, stores the MP4 and a poster in semasa-generated, and writes the row 'done'. The
-- page plays the video. Nothing is posted: a motion video is a file to use, like a Kanvas design.
--
-- settings.motion: {"prompt": "<Wan's own skill/prompt text, added to every brief>", "cli": "0.8.188"}.
-- status: pending → working → done | error.
-- Needs 042 (semasa_repo_library) first.
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, one trigger function, one settings row. Run once; re-running changes nothing.

create table if not exists public.semasa_motions (
  id             uuid primary key default gen_random_uuid(),
  status         text        not null default 'pending',
  brief          text        not null default '',                      -- the idea in Wan's words
  source_url     text        not null default '',                      -- a link the video is about (its words are read)
  stream         text        not null default 'regulab',               -- regulab (BM) | linkedin (EN)
  resolution     text        not null default 'portrait',              -- portrait 1080x1920 | landscape 1920x1080 | square 1080x1080
  seconds        int         not null default 12,
  style_repo_id  uuid        references public.semasa_repo_library (id) on delete set null,   -- a motion repo from Pustaka repo
                                                                      -- whose README/skill files set the look (Wan, 23 Oct 2026:
                                                                      -- "allow me to add repo motion, so I can have choice to
                                                                      -- create different angle of motion video")
  style_note     text        not null default '',                     -- what was read from that repo, for the record
  title          text        not null default '',
  html           text        not null default '',                      -- the composition the AI wrote (index.html)
  check_report   jsonb       not null default '{}'::jsonb,             -- hyperframes check: {ok, errors, warnings}
  video_path     text        not null default '',
  video_url      text        not null default '',
  poster_url     text        not null default '',
  width          int         not null default 0,
  height         int         not null default 0,
  duration_s     numeric     not null default 0,
  bytes          int         not null default 0,
  model          text        not null default '',
  attempts       int         not null default 0,
  error          text        not null default '',
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_motions_status_check     check (status in ('pending', 'working', 'done', 'error')),
  constraint semasa_motions_stream_check     check (stream in ('regulab', 'linkedin')),
  constraint semasa_motions_resolution_check check (resolution in ('portrait', 'landscape', 'square')),
  constraint semasa_motions_seconds_check    check (seconds between 3 and 60)
);
create index if not exists semasa_motions_status_idx on public.semasa_motions (status, created_at);

drop trigger if exists semasa_motions_set_updated_at on public.semasa_motions;
create trigger semasa_motions_set_updated_at before update on public.semasa_motions
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_motions enable row level security;
drop policy if exists "semasa motions: uploaders read" on public.semasa_motions;
create policy "semasa motions: uploaders read" on public.semasa_motions
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa motions: uploaders insert" on public.semasa_motions;
create policy "semasa motions: uploaders insert" on public.semasa_motions
  for insert to authenticated with check (public.semasa_is_uploader());
drop policy if exists "semasa motions: uploaders update" on public.semasa_motions;
create policy "semasa motions: uploaders update" on public.semasa_motions
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa motions: uploaders delete" on public.semasa_motions;
create policy "semasa motions: uploaders delete" on public.semasa_motions
  for delete to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_motions from anon;
grant select, insert, update, delete on public.semasa_motions to authenticated;

create or replace function public.semasa_notify_motion_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the motion worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'motion_pending', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_motions_notify on public.semasa_motions;
create trigger semasa_motions_notify after insert or update of status on public.semasa_motions
  for each row when (new.status = 'pending') execute function public.semasa_notify_motion_pending();

insert into public.semasa_settings (key, value) values ('motion', '{"prompt": "", "cli": "0.8.188"}'::jsonb)
on conflict (key) do nothing;
