-- 078 · Tanya Otak: answer a question from the Otak AI brain, cited (Wan, 11 Nov 2026: "Apply second brain ni dan simpan
-- dekat semasa dan apply sana jugak" — GBrain's synthesis layer, built on the entries Otak AI already files).
--
-- One table, one row per question:
--   semasa_brain_asks   the question, the language (ms | en), an optional note, and the answer that came back: the answer
--                       text with [n] citations, the sources it cited (ref → entry), the gaps (what the brain does not
--                       cover) and the conflicts (where two entries disagree). status: pending | working | done |
--                       empty | error.
-- The page inserts a pending row; the database wakes the worker (repository_dispatch 'brain_ask_pending'); the worker
-- (backend/semasa/brain_ask.py) retrieves the most on-topic entries, asks the AI gateway for one cited answer and writes
-- `result`. The answer is what the brain holds, cited, never a compliance decision. Nothing here posts or sends anything.
--
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, uploader-only RLS, the same vault secrets for the dispatch. Run once;
-- re-running changes nothing.

create table if not exists public.semasa_brain_asks (
  id           uuid primary key default gen_random_uuid(),
  status       text        not null default 'pending',        -- pending | working | done | empty | error
  question     text        not null default '',
  lang         text        not null default 'ms',             -- ms | en
  note         text        not null default '',               -- optional: what is wanted, in the requester's words
  result       jsonb       not null default '{}'::jsonb,      -- {answer, sources[], gaps[], conflicts[], cited[], uncited_sources[], question}
  model        text        not null default '',
  error        text        not null default '',
  attempts     int         not null default 0,
  created_by   uuid        references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint semasa_brain_asks_status_check check (status in ('pending', 'working', 'done', 'empty', 'error')),
  constraint semasa_brain_asks_lang_check   check (lang in ('ms', 'en')),
  constraint semasa_brain_asks_question_size check (char_length(question) <= 2000)
);
create index if not exists semasa_brain_asks_status_idx on public.semasa_brain_asks (status, created_at);
drop trigger if exists semasa_brain_asks_set_updated_at on public.semasa_brain_asks;
create trigger semasa_brain_asks_set_updated_at before update on public.semasa_brain_asks
  for each row execute function public.semasa_set_updated_at();

-- uploader-only, as every semasa_ table
do $$
declare t text := 'semasa_brain_asks';
begin
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
end $$;

-- the database wakes the worker on a new pending question (and on "Tanya semula", which sets pending again)
create or replace function public.semasa_notify_brain_ask_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the brain-ask worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'brain_ask_pending', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_brain_asks_notify on public.semasa_brain_asks;
create trigger semasa_brain_asks_notify after insert or update of status on public.semasa_brain_asks
  for each row when (new.status = 'pending') execute function public.semasa_notify_brain_ask_pending();

-- the log may say 'brain'; the ask rows live beside the other brain tables
-- proof: 1 | 4 | 1 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename = 'semasa_brain_asks') as table_ok,
       (select count(*) from pg_policies where tablename = 'semasa_brain_asks') as policies,
       (select count(*) from pg_trigger where tgname = 'semasa_brain_asks_notify') as trigger_ok,
       (select count(*) from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'semasa_brain_asks') as realtime;
