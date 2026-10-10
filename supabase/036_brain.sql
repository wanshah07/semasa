-- 036 · Otak AI: drop anything in (text, a photo, a file, a link, a page to scrape) and the AI reads it and files it as notes,
-- FAQs, skills, prompts and references, each with a category and tags (Wan, 10 Oct 2026: "create 1 segment for AI, I will
-- upload text, photo, link social media, scrape etc ... the model will auto read and be like note, faq and will be
-- categorize like skills, prompt etc").
--
-- Two tables, because one thing dropped in can become several things filed:
--   semasa_brain_inbox    what Wan dropped in, and where the reading stands (pending | working | done | needs_text | error)
--   semasa_brain_entries  what the AI filed from it: kind (note | faq | skill | prompt | reference | checklist), category,
--                         title, summary, a markdown body, tags, and the kind's own fields in `data`
-- The page inserts an inbox row (a picture goes to the semasa-reference bucket first, a file's words are read in the browser
-- or, for a PDF, by the worker); the database wakes the worker (repository_dispatch 'brain_pending'); the worker
-- (backend/semasa/brain.py) reads the link / picture / text with the AI gateway (Afiq's rootsys, Mireld as the backup,
-- the model chosen by the gateway settings in the AI tab) and writes the entries. Nothing here posts anything.
--
-- SAFE IN A SHARED PROJECT (KPI): two semasa_ tables, uploader-only RLS, the same vault secrets for the dispatch. Run once;
-- re-running changes nothing.

create table if not exists public.semasa_brain_inbox (
  id           uuid primary key default gen_random_uuid(),
  status       text        not null default 'pending',            -- pending | working | done | needs_text | error
  source_kind  text        not null default 'text',               -- text | image | file | link | scrape
  title        text        not null default '',                   -- optional, what Wan calls it
  url          text        not null default '',                   -- a link or a page to scrape
  body         text        not null default '',                   -- pasted text, or the words read from a file in the browser
  image_path   text        not null default '',                   -- storage path in semasa-reference (a picture, or a PDF for the worker)
  image_url    text        not null default '',
  file_name    text        not null default '',
  file_mime    text        not null default '',
  hint         text        not null default '',                   -- optional: "faq" | "skill" | "prompt" | "note": make it this kind
  note         text        not null default '',                   -- Wan's own words about it, given to the AI as context
  read_chars   int         not null default 0,                    -- how much the worker actually read (0 until read)
  entries      int         not null default 0,                    -- how many entries it became
  model        text        not null default '',                   -- which model answered
  error        text        not null default '',                   -- the reason in words when not done
  attempts     int         not null default 0,
  created_by   uuid        references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint semasa_brain_inbox_status_check check (status in ('pending', 'working', 'done', 'needs_text', 'error')),
  constraint semasa_brain_inbox_kind_check   check (source_kind in ('text', 'image', 'file', 'link', 'scrape')),
  constraint semasa_brain_inbox_hint_check   check (hint in ('', 'note', 'faq', 'skill', 'prompt', 'reference', 'checklist'))
);
create index if not exists semasa_brain_inbox_status_idx on public.semasa_brain_inbox (status, created_at);
drop trigger if exists semasa_brain_inbox_set_updated_at on public.semasa_brain_inbox;
create trigger semasa_brain_inbox_set_updated_at before update on public.semasa_brain_inbox
  for each row execute function public.semasa_set_updated_at();

create table if not exists public.semasa_brain_entries (
  id           uuid primary key default gen_random_uuid(),
  inbox_id     uuid        references public.semasa_brain_inbox (id) on delete set null,
  kind         text        not null default 'note',
  category     text        not null default 'lain',               -- one of settings.brain.categories
  title        text        not null default '',
  summary      text        not null default '',                   -- one or two lines
  body         text        not null default '',                   -- markdown; for a prompt, the prompt itself
  question     text        not null default '',                   -- faq
  answer       text        not null default '',                   -- faq
  tags         text[]      not null default '{}',
  data         jsonb       not null default '{}'::jsonb,          -- skill {when, steps[]} · prompt {use, variables[]} · checklist {items[]}
  source_url   text        not null default '',
  confidence   numeric(3,2),                                      -- 0..1 as the reader rated itself
  pinned       boolean     not null default false,
  edited       boolean     not null default false,                -- Wan changed it: a re-read never replaces it
  created_by   uuid        references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint semasa_brain_entries_kind_check check (kind in ('note', 'faq', 'skill', 'prompt', 'reference', 'checklist'))
);
create index if not exists semasa_brain_entries_kind_idx  on public.semasa_brain_entries (kind, category);
create index if not exists semasa_brain_entries_inbox_idx on public.semasa_brain_entries (inbox_id);
create index if not exists semasa_brain_entries_tags_idx  on public.semasa_brain_entries using gin (tags);
drop trigger if exists semasa_brain_entries_set_updated_at on public.semasa_brain_entries;
create trigger semasa_brain_entries_set_updated_at before update on public.semasa_brain_entries
  for each row execute function public.semasa_set_updated_at();

-- uploader-only, as every semasa_ table
do $$
declare t text;
begin
  foreach t in array array['semasa_brain_inbox', 'semasa_brain_entries'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists %I on public.%I', t || ': uploaders read', t);
    execute format('create policy %I on public.%I for select to authenticated using (public.semasa_is_uploader())', t || ': uploaders read', t);
    execute format('drop policy if exists %I on public.%I', t || ': uploaders insert', t);
    execute format('create policy %I on public.%I for insert to authenticated with check (public.semasa_is_uploader())', t || ': uploaders insert', t);
    execute format('drop policy if exists %I on public.%I', t || ': uploaders update', t);
    execute format('create policy %I on public.%I for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader())', t || ': uploaders update', t);
    execute format('drop policy if exists %I on public.%I', t || ': uploaders delete', t);
    execute format('create policy %I on public.%I for delete to authenticated using (public.semasa_is_uploader())', t || ': uploaders delete', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

-- the database wakes the worker on a new pending row (and on "Baca semula", which sets pending again)
create or replace function public.semasa_notify_brain_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the brain worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'brain_pending', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_brain_inbox_notify on public.semasa_brain_inbox;
create trigger semasa_brain_inbox_notify after insert or update of status on public.semasa_brain_inbox
  for each row when (new.status = 'pending') execute function public.semasa_notify_brain_pending();

-- the log may say 'brain'; the settings row the worker and the page read
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing', 'subscription', 'crm', 'receipt', 'metrics', 'repos', 'api', 'brain'));
insert into public.semasa_settings (key, value) values ('brain', jsonb_build_object(
  'categories', jsonb_build_array('regulatori', 'kosmetik', 'halal', 'makanan', 'farmaseutikal', 'pemasaran', 'kandungan', 'teknologi', 'kewangan', 'operasi', 'klien', 'lain'),
  'per_run', 15,                                       -- inbox items one worker run reads before stopping
  'max_entries', 10,                                   -- entries one inbox item may become
  'language', 'ms'                                     -- the language entries are written in: ms (Bahasa Malaysia) or en; a source in the other language is kept in its own
)) on conflict (key) do nothing;

-- proof: 2 | 8 | 1 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename in ('semasa_brain_inbox', 'semasa_brain_entries')) as tables_ok,
       (select count(*) from pg_policies where tablename in ('semasa_brain_inbox', 'semasa_brain_entries')) as policies,
       (select count(*) from pg_trigger where tgname = 'semasa_brain_inbox_notify') as trigger_ok,
       (select count(*) from public.semasa_settings where key = 'brain') as settings;
