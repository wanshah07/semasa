-- Semasa · Studio features (replaces ws.regulab Studio) · run AFTER 001–004. Idempotent.
--
-- Adds both flows:
--   Flow A  headline → idea → media (the bot READS the source and RECREATES) → post draft
--   Flow B  prompt alone, or prompt + uploaded reference (READ, then RECREATE) → media,
--           with a saved-prompt library
-- and Studio's gate: a post is `approved` only by a person clicking Approve, and nothing
-- is published while settings `publishing.enabled` is false — which it is, and which the
-- browser CANNOT change (only the SQL editor / service_role can; see the policy below).
--
-- SAFE IN A SHARED PROJECT (KKM): every object is named semasa_*; nothing here reads or
-- writes another app's tables, and nothing touches auth.users beyond a foreign key.

-- ---------------------------------------------------------------------------
-- Drafts are not public. Studio's rule: only an APPROVED post's artwork is public.
-- The media gallery was readable by anyone; it now carries unapproved Flow A artwork,
-- so reads are limited to listed uploaders. (isu_semasa_trends stays public: it is news.)
-- ---------------------------------------------------------------------------
drop policy if exists "media: anyone can read" on public.media_generations;
drop policy if exists "media: uploaders can read" on public.media_generations;
create policy "media: uploaders can read"
  on public.media_generations for select
  to authenticated
  using (public.semasa_is_uploader());

-- ---------------------------------------------------------------------------
-- settings
-- ---------------------------------------------------------------------------
create table if not exists public.semasa_settings (
  key        text primary key,
  value      jsonb       not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  updated_by uuid        references auth.users (id) on delete set null
);

insert into public.semasa_settings (key, value) values
  ('publishing', jsonb_build_object(
     'enabled', false,
     'why', 'Off until Semasa is proven end to end and ws.regulab Studio''s Routines are switched off. Two publishers on one Buffer account post everything twice. Turn on only in the SQL editor.')),
  ('brand', jsonb_build_object(
     'regulab', jsonb_build_object(
        'name', 'ws.regulab', 'website', 'www.kkmhalalconsultant.com', 'handle', '@ws.regulab',
        'slots', jsonb_build_array('08:00', '13:00', '21:00'),
        -- weekday (0 = Sunday) → the pair of domains that day carries
        'schedule', jsonb_build_object(
          '0', jsonb_build_array('halal_my', 'fatwa'),
          '1', jsonb_build_array('kosmetik', 'sains_kosmetik'),
          '2', jsonb_build_array('halal_my', 'fatwa'),
          '3', jsonb_build_array('kosmetik', 'kajian_kes'),
          '4', jsonb_build_array('farmaseutikal', 'makanan'),
          '5', jsonb_build_array('kosmetik', 'sains_kosmetik'),
          '6', jsonb_build_array('farmaseutikal', 'makanan')),
        'domains', jsonb_build_object(
          'kosmetik', 'Cosmetics (NPRA)', 'makanan', 'Food & beverage (FSQD/BKKM)',
          'halal_my', 'Halal Malaysia (JAKIM/JAIN)', 'farmaseutikal', 'Pharmaceuticals & supplements (NPRA/DCA)',
          'fatwa', 'Fatwa (MKI / State Muftis)', 'kajian_kes', 'Case studies',
          'sains_kosmetik', 'Cosmetic science (latest publications)')),
     'linkedin', jsonb_build_object(
        'name', 'Ts. ChM Muhammad Ridzuan',
        'slots', jsonb_build_array('06:00', '19:00'),
        'days', jsonb_build_array(0, 1, 2, 3, 4, 5, 6),
        'angles', jsonb_build_object(
          'A', 'Regulatory change', 'B', 'Halal', 'C', 'WTO TBT notification',
          'D', 'Regulation × mechanism', 'E', 'Case study', 'F', 'Cosmetic science (new paper)',
          'G', 'Medicine or dermatology in plain English'))))
on conflict (key) do nothing;

-- ---------------------------------------------------------------------------
-- saved prompts (Flow B library)
-- ---------------------------------------------------------------------------
create table if not exists public.semasa_prompts (
  id             uuid primary key default gen_random_uuid(),
  title          text        not null default '',
  prompt         text        not null,
  type           text        not null default 'image',
  reference_url  text,
  reference_path text,
  tags           text[]      not null default '{}',
  uses           int         not null default 0,
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_prompts_type_check check (type in ('image', 'video'))
);

-- ---------------------------------------------------------------------------
-- ideas (Flow A). The headline is COPIED in, because isu_semasa_trends is pruned
-- after SCRAPE_KEEP_DAYS and an idea must outlive the row it came from.
-- ---------------------------------------------------------------------------
create table if not exists public.semasa_ideas (
  id             uuid primary key default gen_random_uuid(),
  trend_id       uuid        references public.isu_semasa_trends (id) on delete set null,
  source_title   text        not null default '',
  source_url     text,
  source_name    text,
  source_summary text,
  stream         text        not null default 'regulab',
  domain         text,
  angle          text,
  note           text        not null default '',   -- what Wan wants from it
  make_media     text        not null default 'image',
  reference_urls text[]      not null default '{}', -- extra references Wan attached
  status         text        not null default 'new',
  brief          jsonb       not null default '{}'::jsonb, -- what the bot read and decided
  error          text,
  attempts       int         not null default 0,
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_ideas_stream_check check (stream in ('regulab', 'linkedin')),
  constraint semasa_ideas_status_check check (status in ('new', 'working', 'drafted', 'rejected', 'error')),
  constraint semasa_ideas_make_media_check check (make_media in ('image', 'video', 'none'))
);
create index if not exists semasa_ideas_status_idx on public.semasa_ideas (status, created_at);

-- ---------------------------------------------------------------------------
-- posts (drafts). text is { <lang>: { <platform>: caption } } — language OUTER,
-- platform inner, exactly Studio's shape (a BM caption at text.en.bm is invisible).
-- ---------------------------------------------------------------------------
create table if not exists public.semasa_posts (
  id          uuid primary key default gen_random_uuid(),
  idea_id     uuid        references public.semasa_ideas (id) on delete set null,
  stream      text        not null default 'regulab',
  domain      text,
  angle       text,
  lang        text        not null default 'bm',
  hook        text        not null default '',
  text        jsonb       not null default '{}'::jsonb,
  citation    text        not null default '',
  media_ids   uuid[]      not null default '{}',     -- media_generations used, in order
  date        date,
  slot        text,                                  -- 'HH:MM', Malaysia time
  status      text        not null default 'draft',
  flags       jsonb       not null default '[]'::jsonb, -- the page's last scan
  hard_flags  int         not null default 0,
  approved_by uuid        references auth.users (id) on delete set null,
  approved_at timestamptz,
  published   jsonb       not null default '{}'::jsonb, -- per channel, written by the publisher only
  errors      jsonb       not null default '{}'::jsonb,
  created_by  uuid        references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_posts_stream_check check (stream in ('regulab', 'linkedin')),
  constraint semasa_posts_lang_check   check (lang in ('bm', 'en')),
  constraint semasa_posts_status_check check (status in ('draft', 'approved', 'scheduled', 'posted', 'rejected')),
  constraint semasa_posts_slot_check   check (slot is null or slot ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$'),
  -- the page cannot approve a post its own scan says is blocked
  constraint semasa_posts_approve_clean check (status <> 'approved' or hard_flags = 0)
);
create index if not exists semasa_posts_status_idx on public.semasa_posts (status, date, slot);

-- ---------------------------------------------------------------------------
-- publish log: what the publisher did, or in dry-run what it WOULD have done
-- ---------------------------------------------------------------------------
create table if not exists public.semasa_publish_log (
  id      uuid primary key default gen_random_uuid(),
  post_id uuid        references public.semasa_posts (id) on delete cascade,
  channel text        not null,
  action  text        not null,
  detail  jsonb       not null default '{}'::jsonb,
  at      timestamptz not null default now(),
  constraint semasa_publish_log_action_check check (action in ('dry_run', 'sent', 'error', 'blocked'))
);
create index if not exists semasa_publish_log_post_idx on public.semasa_publish_log (post_id, at desc);

-- ---------------------------------------------------------------------------
-- media_generations: two modes and links back to the flow that asked
--   recreate  a reference picture is READ (vision) and a new one is generated from it
--   prompt    words only; for video a still is generated first, then animated
-- ---------------------------------------------------------------------------
alter table public.media_generations alter column reference_url drop not null;
alter table public.media_generations add column if not exists mode text not null default 'recreate';
alter table public.media_generations add column if not exists idea_id uuid references public.semasa_ideas (id) on delete set null;
alter table public.media_generations add column if not exists post_id uuid references public.semasa_posts (id) on delete set null;
alter table public.media_generations add column if not exists prompt_id uuid references public.semasa_prompts (id) on delete set null;
alter table public.media_generations add column if not exists reference_read text;
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'media_generations_mode_check') then
    alter table public.media_generations add constraint media_generations_mode_check
      check (mode in ('recreate', 'prompt') and (mode = 'prompt' or reference_url is not null));
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- triggers
-- ---------------------------------------------------------------------------
drop trigger if exists semasa_settings_set_updated_at on public.semasa_settings;
create trigger semasa_settings_set_updated_at before update on public.semasa_settings
  for each row execute function public.semasa_set_updated_at();
drop trigger if exists semasa_prompts_set_updated_at on public.semasa_prompts;
create trigger semasa_prompts_set_updated_at before update on public.semasa_prompts
  for each row execute function public.semasa_set_updated_at();
drop trigger if exists semasa_ideas_set_updated_at on public.semasa_ideas;
create trigger semasa_ideas_set_updated_at before update on public.semasa_ideas
  for each row execute function public.semasa_set_updated_at();
drop trigger if exists semasa_posts_set_updated_at on public.semasa_posts;
create trigger semasa_posts_set_updated_at before update on public.semasa_posts
  for each row execute function public.semasa_set_updated_at();

-- The approval gate, enforced by the database rather than trusted to the page:
--  * approved_by / approved_at are stamped here from the session, never sent by the page;
--  * an APPROVED post whose words, source, pictures or time change goes back to draft,
--    so what was approved is exactly what gets sent (Studio's Buffer-copy lesson);
--  * the browser can never write scheduled / posted / published / errors: those belong to
--    the publisher (service_role, where auth.uid() is null).
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
        or new.stream is distinct from old.stream) then
    new.status := 'draft'; new.approved_by := null; new.approved_at := null;
  elsif new.status <> 'approved' then
    new.approved_by := null; new.approved_at := null;
  else
    new.approved_by := old.approved_by; new.approved_at := old.approved_at;
  end if;
  return new;
end $$;

drop trigger if exists semasa_posts_gate on public.semasa_posts;
create trigger semasa_posts_gate before insert or update on public.semasa_posts
  for each row execute function public.semasa_posts_gate();

-- New idea → wake the worker at once (the 15-minute poll in media.yml is the net).
create or replace function public.semasa_notify_idea_new() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'media_pending',
                                  'client_payload', jsonb_build_object('idea_id', new.id))
  );
  return new;
end $$;

drop trigger if exists semasa_ideas_notify_new on public.semasa_ideas;
create trigger semasa_ideas_notify_new
  after insert or update of status on public.semasa_ideas
  for each row when (new.status = 'new')
  execute function public.semasa_notify_idea_new();

-- ---------------------------------------------------------------------------
-- Row Level Security: everything here is private to listed uploaders.
-- ---------------------------------------------------------------------------
alter table public.semasa_settings    enable row level security;
alter table public.semasa_prompts     enable row level security;
alter table public.semasa_ideas       enable row level security;
alter table public.semasa_posts       enable row level security;
alter table public.semasa_publish_log enable row level security;

drop policy if exists "semasa settings: uploaders read" on public.semasa_settings;
create policy "semasa settings: uploaders read" on public.semasa_settings
  for select to authenticated using (public.semasa_is_uploader());
-- The publishing switch is deliberately NOT editable from the browser.
drop policy if exists "semasa settings: uploaders edit, not publishing" on public.semasa_settings;
create policy "semasa settings: uploaders edit, not publishing" on public.semasa_settings
  for update to authenticated
  using (public.semasa_is_uploader() and key <> 'publishing')
  with check (public.semasa_is_uploader() and key <> 'publishing');

drop policy if exists "semasa prompts: uploaders all" on public.semasa_prompts;
create policy "semasa prompts: uploaders all" on public.semasa_prompts
  for all to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and created_by = auth.uid());

drop policy if exists "semasa ideas: uploaders read" on public.semasa_ideas;
create policy "semasa ideas: uploaders read" on public.semasa_ideas
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa ideas: uploaders insert" on public.semasa_ideas;
create policy "semasa ideas: uploaders insert" on public.semasa_ideas
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid() and status = 'new');
-- the page may re-queue, reject or edit an idea; `working` and `drafted` are the worker's
drop policy if exists "semasa ideas: uploaders update" on public.semasa_ideas;
create policy "semasa ideas: uploaders update" on public.semasa_ideas
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('new', 'rejected', 'error'));
drop policy if exists "semasa ideas: uploaders delete" on public.semasa_ideas;
create policy "semasa ideas: uploaders delete" on public.semasa_ideas
  for delete to authenticated using (public.semasa_is_uploader());

drop policy if exists "semasa posts: uploaders read" on public.semasa_posts;
create policy "semasa posts: uploaders read" on public.semasa_posts
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa posts: uploaders insert" on public.semasa_posts;
create policy "semasa posts: uploaders insert" on public.semasa_posts
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid());
drop policy if exists "semasa posts: uploaders update" on public.semasa_posts;
create policy "semasa posts: uploaders update" on public.semasa_posts
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('draft', 'approved', 'rejected'));
drop policy if exists "semasa posts: uploaders delete unpublished" on public.semasa_posts;
create policy "semasa posts: uploaders delete unpublished" on public.semasa_posts
  for delete to authenticated
  using (public.semasa_is_uploader() and status in ('draft', 'rejected'));

drop policy if exists "semasa publish log: uploaders read" on public.semasa_publish_log;
create policy "semasa publish log: uploaders read" on public.semasa_publish_log
  for select to authenticated using (public.semasa_is_uploader());
-- writes: service_role only

-- A listed uploader may change the mode/links of their own pending job like any column;
-- the existing insert policy (created_by = auth.uid(), status pending) still applies.

-- Realtime so the Idea and Post tabs update as the worker writes
do $$
declare t text;
begin
  foreach t in array array['semasa_ideas', 'semasa_posts'] loop
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;
