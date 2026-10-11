-- 037 · Documents from the brain and the FAQ: the AI drafts a SOP, an NCR, a comparison, an FAQ document and more as a Word
-- file, in Bahasa Malaysia, English or both (Wan, 11 Oct 2026: "ensure the bot can issue document for FAQ, Otak AI like this
-- when needed (in malay and english)", with the halal-documentation prompt workbook as the pattern).
--
-- One table, one row per request:
--   semasa_brain_docs   what was asked (a type from rules/documents.json, a language, the material put together in the browser)
--                       and the draft that came back (`result`: one document per language, each with its checks)
-- The page inserts a pending row; the database wakes the worker (repository_dispatch 'brain_doc_pending'); the worker
-- (backend/semasa/brain_docs.py) asks the AI gateway for the sections, conforms the answer to the type's structure, checks
-- it against the material and writes `result`; the page turns it into a .docx. Every document is a DRAFT FOR REVIEW: the AI
-- never decides halal status, compliance, approval or closure, and invents no name, date, number, version, signature or owner.
-- Nothing here posts or sends anything.
--
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, uploader-only RLS, the same vault secrets for the dispatch. Run once;
-- re-running changes nothing.

create table if not exists public.semasa_brain_docs (
  id               uuid primary key default gen_random_uuid(),
  status           text        not null default 'pending',        -- pending | working | done | error
  doc_type         text        not null default 'faq_pack',       -- an id in rules/documents.json
  lang             text        not null default 'ms',             -- ms | en | both
  title            text        not null default '',               -- optional working title
  note             text        not null default '',               -- what is wanted, in the requester's words
  custom_structure text        not null default '',               -- doc_type 'custom': one section per line, "Heading | col | col" for a table
  source_text      text        not null default '',               -- the material, assembled in the browser (entries, FAQs, pasted facts, files read there)
  source_refs      jsonb       not null default '[]'::jsonb,      -- [{kind, id, title}] what the material came from
  result           jsonb       not null default '{}'::jsonb,      -- {ms: document, en: document}
  model            text        not null default '',
  error            text        not null default '',
  attempts         int         not null default 0,
  created_by       uuid        references auth.users (id) on delete set null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  constraint semasa_brain_docs_status_check check (status in ('pending', 'working', 'done', 'error')),
  constraint semasa_brain_docs_lang_check   check (lang in ('ms', 'en', 'both')),
  constraint semasa_brain_docs_type_check   check (doc_type in ('faq_pack', 'work_instruction', 'sop_gap', 'sop_draft', 'fact_extract', 'ref_compare',
    'gap_followup', 'ncr_capa', 'risk_register', 'minutes', 'manual_update', 'use_case_map', 'reusable_prompt', 'custom')),
  constraint semasa_brain_docs_source_size  check (char_length(source_text) <= 120000)
);
create index if not exists semasa_brain_docs_status_idx on public.semasa_brain_docs (status, created_at);
drop trigger if exists semasa_brain_docs_set_updated_at on public.semasa_brain_docs;
create trigger semasa_brain_docs_set_updated_at before update on public.semasa_brain_docs
  for each row execute function public.semasa_set_updated_at();

-- uploader-only, as every semasa_ table
do $$
declare t text := 'semasa_brain_docs';
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

-- the database wakes the worker on a new pending request (and on "Jana semula", which sets pending again)
create or replace function public.semasa_notify_brain_doc_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the document worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'brain_doc_pending', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_brain_docs_notify on public.semasa_brain_docs;
create trigger semasa_brain_docs_notify after insert or update of status on public.semasa_brain_docs
  for each row when (new.status = 'pending') execute function public.semasa_notify_brain_doc_pending();

-- proof: 1 | 4 | 1 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename = 'semasa_brain_docs') as table_ok,
       (select count(*) from pg_policies where tablename = 'semasa_brain_docs') as policies,
       (select count(*) from pg_trigger where tgname = 'semasa_brain_docs_notify') as trigger_ok,
       (select count(*) from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'semasa_brain_docs') as realtime;
