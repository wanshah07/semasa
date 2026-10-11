-- 038 · Templates for documents: add a reference document (a blank form, a SOP template, a filled example) and the AI turns it
-- into a template, which you then choose when you ask for a document (Wan, 11 Oct 2026: "allow me to add document reference and
-- you will create it as template, and I can choose the template"). RUN 037 FIRST: this adds to semasa_brain_docs.
--
--   semasa_doc_templates   one row per reference: the words read from it in the browser (`source_text`), the sections and table
--                          columns the AI found in the reference's own words with the other language beside them (`structure`),
--                          what it could not find in the reference (`warnings`), and where the reading stands
--   semasa_brain_docs      gains `template_id` and `template_snapshot`: a request that chose a template carries a copy of its
--                          structure, so a document can be drafted again after the template is edited or deleted
-- The page inserts a pending template; the database wakes the same worker as the documents (repository_dispatch
-- 'brain_doc_pending', function from 037); backend/semasa/brain_docs.py reads the reference and writes `structure`. The reference
-- FILE itself is not stored, only the words read from it; the Word file a document is built into follows the template's
-- structure, not its fonts, header or footer. Nothing here posts or sends anything.
--
-- SAFE IN A SHARED PROJECT (KPI): one new semasa_ table, uploader-only RLS. Run once; re-running changes nothing.

create table if not exists public.semasa_doc_templates (
  id           uuid primary key default gen_random_uuid(),
  status       text        not null default 'pending',            -- pending | working | done | error
  name         text        not null default '',
  description  text        not null default '',
  source_file  text        not null default '',                   -- the file name it was read from
  source_lang  text        not null default '',                   -- ms | en: the language the reference is written in ('' until read)
  note         text        not null default '',                   -- what the document is for, in the requester's words
  source_text  text        not null default '',                   -- the words of the reference, read in the browser
  structure    jsonb       not null default '[]'::jsonb,          -- [{key, kind, heading{ms,en}, hint{ms,en}, optional, columns[{ms,en,auto_no,verbatim}]}]
  warnings     jsonb       not null default '[]'::jsonb,          -- titles the AI wrote that the reference does not contain
  model        text        not null default '',
  error        text        not null default '',
  attempts     int         not null default 0,
  created_by   uuid        references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now(),
  constraint semasa_doc_templates_status_check check (status in ('pending', 'working', 'done', 'error')),
  constraint semasa_doc_templates_lang_check   check (source_lang in ('', 'ms', 'en')),
  constraint semasa_doc_templates_source_size  check (char_length(source_text) <= 120000)
);
create index if not exists semasa_doc_templates_status_idx on public.semasa_doc_templates (status, created_at);
drop trigger if exists semasa_doc_templates_set_updated_at on public.semasa_doc_templates;
create trigger semasa_doc_templates_set_updated_at before update on public.semasa_doc_templates
  for each row execute function public.semasa_set_updated_at();

-- uploader-only, as every semasa_ table
do $$
declare t text := 'semasa_doc_templates';
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

-- a new pending reference (and "Baca semula") wakes the worker through the function 037 made
drop trigger if exists semasa_doc_templates_notify on public.semasa_doc_templates;
create trigger semasa_doc_templates_notify after insert or update of status on public.semasa_doc_templates
  for each row when (new.status = 'pending') execute function public.semasa_notify_brain_doc_pending();

-- a request may choose a template, and keeps a copy of its structure
alter table public.semasa_brain_docs add column if not exists template_id uuid references public.semasa_doc_templates (id) on delete set null;
alter table public.semasa_brain_docs add column if not exists template_snapshot jsonb not null default '{}'::jsonb;
alter table public.semasa_brain_docs drop constraint if exists semasa_brain_docs_type_check;
alter table public.semasa_brain_docs add constraint semasa_brain_docs_type_check check (doc_type in ('faq_pack', 'work_instruction', 'sop_gap',
  'sop_draft', 'fact_extract', 'ref_compare', 'gap_followup', 'ncr_capa', 'risk_register', 'minutes', 'manual_update', 'use_case_map',
  'reusable_prompt', 'custom', 'template'));

-- proof: 1 | 4 | 1 | 1 | 2 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename = 'semasa_doc_templates') as table_ok,
       (select count(*) from pg_policies where tablename = 'semasa_doc_templates') as policies,
       (select count(*) from pg_trigger where tgname = 'semasa_doc_templates_notify') as trigger_ok,
       (select count(*) from pg_publication_tables where pubname = 'supabase_realtime' and tablename = 'semasa_doc_templates') as realtime,
       (select count(*) from information_schema.columns where table_name = 'semasa_brain_docs' and column_name in ('template_id', 'template_snapshot')) as columns_ok,
       (select count(*) from pg_constraint where conname = 'semasa_brain_docs_type_check' and pg_get_constraintdef(oid) like '%''template''%') as type_ok;
