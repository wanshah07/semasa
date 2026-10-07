-- Semasa · Bil (Wan, 7 Oct 2026): quotations, invoices and receipts for WS Regulab Solutions, with clients, numbering,
-- e-mail sending through the worker (Gmail via Composio), reminders, statuses and a public "view online" link.
-- Run ONCE in the SQL editor, after 001–027. Idempotent: safe to run again.
--
-- SAFE IN A SHARED PROJECT (KPI): everything here is prefixed semasa_ (five tables, three functions, one trigger, one
-- settings row) and one check on semasa_log is widened by one word ('billing'). No other app's object is touched.
--
-- The three PDFs Wan made by hand (QT-2026-009, INV-2026-014, RPT-2026-016) were printed from a browser page: two in US
-- Letter, one in A4, the recipient's address differing between the quotation and its invoice, "Due date" on a quotation
-- that was really its validity, "TAX INVOICE" with 0% tax and no SST number, a receipt naming no invoice and no payment
-- method. This module is the one source for all of that: one client record, one numbering sequence, one A4 template.
--
-- The flow:
--   1. a document starts as a DRAFT (no number); Wan edits items, dates, terms; the page computes and stores the totals;
--   2. ISSUE allocates the next number for its kind and year (semasa_billing_issue, atomic) and locks the words;
--   3. SEND puts a row in semasa_billing_outbox; the database wakes the worker (repository_dispatch 'billing_pending');
--      the worker renders the A4 PDF in Chrome, attaches it, and sends from Wan's own Gmail (Composio For You);
--   4. the client opens the "view online" link: semasa_billing_public marks the document VIEWED;
--   5. a quotation becomes an invoice; an invoice paid becomes a receipt; reminders go out for invoices past due.
-- Statuses (stored): quotation draft|issued|sent|viewed|accepted|declined|expired|converted;
--                    invoice   draft|issued|sent|viewed|paid|void;   receipt issued|sent|viewed.
-- "Overdue" is never stored: it is an invoice past its due date that is not paid or void (web/src/lib/billing.js).

create extension if not exists pgcrypto;

-- 1 · clients -----------------------------------------------------------------------------------------------------------
create table if not exists public.semasa_clients (
  id          uuid primary key default gen_random_uuid(),
  name        text        not null,
  reg_no      text        not null default '',          -- SSM / company number
  attention   text        not null default '',          -- contact person
  email       text        not null default '',
  phone       text        not null default '',
  address     text        not null default '',          -- street lines
  postcode    text        not null default '',
  city        text        not null default '',
  state       text        not null default '',
  country     text        not null default 'Malaysia',
  lang        text        not null default 'bm',        -- the language their documents and e-mails are written in
  notes       text        not null default '',
  created_by  uuid        references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_clients_name_check check (length(btrim(name)) > 0),
  constraint semasa_clients_lang_check check (lang in ('bm', 'en'))
);
drop trigger if exists semasa_clients_set_updated_at on public.semasa_clients;
create trigger semasa_clients_set_updated_at before update on public.semasa_clients
  for each row execute function public.semasa_set_updated_at();

-- 1b · projects (Wan, 7 Oct 2026: "register client > Project name > details"): a client's piece of work, which its
--      quotations, invoices and receipts hang off, so one project's money can be read in one place -----------------------
create table if not exists public.semasa_projects (
  id          uuid primary key default gen_random_uuid(),
  client_id   uuid        not null references public.semasa_clients (id) on delete cascade,
  name        text        not null,
  details     text        not null default '',          -- scope, products, what was agreed
  status      text        not null default 'active',    -- lead | active | on_hold | done | cancelled
  start_date  date,
  end_date    date,
  budget      numeric(12,2),                            -- the agreed fee, if one was agreed up front
  reference   text        not null default '',          -- the client's own PO / file reference
  notes       text        not null default '',          -- internal
  created_by  uuid        references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_projects_name_check check (length(btrim(name)) > 0),
  constraint semasa_projects_status_check check (status in ('lead', 'active', 'on_hold', 'done', 'cancelled')),
  constraint semasa_projects_dates_check check (end_date is null or start_date is null or end_date >= start_date)
);
create index if not exists semasa_projects_client_idx on public.semasa_projects (client_id);
drop trigger if exists semasa_projects_set_updated_at on public.semasa_projects;
create trigger semasa_projects_set_updated_at before update on public.semasa_projects
  for each row execute function public.semasa_set_updated_at();

-- 2 · documents ---------------------------------------------------------------------------------------------------------
create table if not exists public.semasa_billing_docs (
  id          uuid primary key default gen_random_uuid(),
  kind        text        not null,
  number      text,                                       -- QT-2026-010; null while a draft
  status      text        not null default 'draft',
  token       text        not null default encode(gen_random_bytes(16), 'hex'),   -- the public view link
  client_id   uuid        references public.semasa_clients (id) on delete set null,
  project_id  uuid        references public.semasa_projects (id) on delete set null,
  client      jsonb       not null default '{}'::jsonb,   -- the client's details as they were when issued
  items       jsonb       not null default '[]'::jsonb,   -- [{description, qty, rate}]
  currency    text        not null default 'MYR',
  tax_rate    numeric(5,2)  not null default 0,
  discount    numeric(12,2) not null default 0,
  subtotal    numeric(12,2) not null default 0,
  tax         numeric(12,2) not null default 0,
  total       numeric(12,2) not null default 0,
  issue_date  date,
  due_date    date,                                       -- invoice: payment due; quotation: valid until
  terms       text        not null default '',
  notes       text        not null default '',
  reference   text        not null default '',            -- the client's PO / project reference, if any
  payment     jsonb       not null default '{}'::jsonb,   -- receipt: {method, date, reference}; invoice when paid: the same
  parent_id   uuid        references public.semasa_billing_docs (id) on delete set null,   -- invoice ← quotation, receipt ← invoice
  lang        text        not null default 'bm',
  sent_at     timestamptz,
  viewed_at   timestamptz,
  paid_at     timestamptz,
  reminders   jsonb       not null default '{"sent": []}'::jsonb,   -- {"sent": [offset days already reminded]}
  pdf_path    text,                                       -- the worker's rendering in semasa-generated
  pdf_url     text,
  pdf_at      timestamptz,
  created_by  uuid        references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_billing_docs_kind_check check (kind in ('quotation', 'invoice', 'receipt')),
  constraint semasa_billing_docs_status_check check (status in
    ('draft', 'issued', 'sent', 'viewed', 'accepted', 'declined', 'expired', 'converted', 'paid', 'void')),
  constraint semasa_billing_docs_lang_check check (lang in ('bm', 'en')),
  constraint semasa_billing_docs_number_key unique (number),
  constraint semasa_billing_docs_token_key unique (token)
);
create index if not exists semasa_billing_docs_kind_status_idx on public.semasa_billing_docs (kind, status);
create index if not exists semasa_billing_docs_client_idx on public.semasa_billing_docs (client_id);
create index if not exists semasa_billing_docs_project_idx on public.semasa_billing_docs (project_id);
-- a table made by an earlier run of this file, before projects existed, gets the column too
alter table public.semasa_billing_docs add column if not exists project_id uuid references public.semasa_projects (id) on delete set null;
drop trigger if exists semasa_billing_docs_set_updated_at on public.semasa_billing_docs;
create trigger semasa_billing_docs_set_updated_at before update on public.semasa_billing_docs
  for each row execute function public.semasa_set_updated_at();

-- 3 · events (what happened to a document: issued, sent, reminder, viewed, paid, error) ----------------------------------
create table if not exists public.semasa_billing_events (
  id        bigint generated always as identity primary key,
  doc_id    uuid        not null references public.semasa_billing_docs (id) on delete cascade,
  at        timestamptz not null default now(),
  kind      text        not null,
  detail    jsonb       not null default '{}'::jsonb,
  actor     uuid        references auth.users (id) on delete set null
);
create index if not exists semasa_billing_events_doc_idx on public.semasa_billing_events (doc_id, at desc);

-- 4 · outbox (an e-mail the worker must send) ---------------------------------------------------------------------------
create table if not exists public.semasa_billing_outbox (
  id          uuid primary key default gen_random_uuid(),
  doc_id      uuid        not null references public.semasa_billing_docs (id) on delete cascade,
  action      text        not null,                       -- send | reminder
  to_email    text        not null,
  cc          text[]      not null default '{}',
  subject     text        not null default '',            -- '' = the worker writes it from the settings template
  body        text        not null default '',
  lang        text        not null default 'bm',
  status      text        not null default 'pending',     -- pending | working | sent | error
  attempts    int         not null default 0,
  error       text        not null default '',
  result      jsonb       not null default '{}'::jsonb,   -- {id, threadId} from Gmail
  meta        jsonb       not null default '{}'::jsonb,   -- reminder: {offset}
  created_by  uuid        references auth.users (id) on delete set null,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_billing_outbox_action_check check (action in ('send', 'reminder')),
  constraint semasa_billing_outbox_status_check check (status in ('pending', 'working', 'sent', 'error')),
  constraint semasa_billing_outbox_to_check check (position('@' in to_email) > 1)
);
create index if not exists semasa_billing_outbox_status_idx on public.semasa_billing_outbox (status, created_at);
drop trigger if exists semasa_billing_outbox_set_updated_at on public.semasa_billing_outbox;
create trigger semasa_billing_outbox_set_updated_at before update on public.semasa_billing_outbox
  for each row execute function public.semasa_set_updated_at();

-- 5 · counters: one sequence per prefix and year, taken atomically -----------------------------------------------------
create table if not exists public.semasa_billing_counters (
  prefix  text not null,
  year    int  not null,
  last    int  not null default 0,
  primary key (prefix, year)
);
-- the numbers Wan has already used by hand (7 Oct 2026): the next ones are QT-2026-010, INV-2026-015, RPT-2026-017
insert into public.semasa_billing_counters (prefix, year, last) values ('QT', 2026, 9), ('INV', 2026, 14), ('RPT', 2026, 16)
on conflict (prefix, year) do nothing;

-- 6 · settings row (the page edits it; the worker reads it) -----------------------------------------------------------
insert into public.semasa_settings (key, value) values ('billing', jsonb_build_object(
  'company', jsonb_build_object(
    'name', 'WS Regulab Solutions', 'reg_no', '202603005218 (MA0341349-M)', 'tagline', 'Trusted . Proven . Clarity',
    'footer', 'Malaysia Regulatory Specialist • Professional Consultancy & Compliance Services',
    'website', 'www.kkmhalalconsultant.com', 'email', 'info@kkmhalalconsultant.com', 'phone', '', 'address', '',
    'sst_no', '', 'tin', '', 'signatory', 'Ts. ChM Muhammad Ridzuan'),
  'bank', jsonb_build_object('name', 'Public Bank Berhad', 'account_name', 'WS Regulab Solutions', 'account_no', '3246551604'),
  'prefix', jsonb_build_object('quotation', 'QT', 'invoice', 'INV', 'receipt', 'RPT'),
  'days', jsonb_build_object('quotation_valid', 30, 'invoice_due', 30),
  'tax_rate', 0,
  'terms', jsonb_build_object(
    'quotation', E'Valid for 30 days from the issue date.\nScope as stated; additional work is charged separately.\nFees are non-refundable once services commence.\nQuoted fees exclude any government, statutory or regulatory fees, which are borne by the client.',
    'invoice',   E'Payment is due within 30 days by bank or instant transfer, quoting the invoice number.\nDisputes must be raised within 7 days of the invoice date, failing which the invoice is deemed accepted.\nFees are non-refundable once services commence.\nProfessional fees exclude government, statutory or regulatory fees; any such fees are charged separately at actual cost.',
    'receipt',   'This receipt is issued as an acknowledgement of payment received. Thank you.'),
  'email', jsonb_build_object(
    'auto_send', false,              -- true: issuing a document also e-mails it
    'auto_reminders', true,          -- the worker reminds for invoices past due
    'reminder_days', jsonb_build_array(-3, 1, 7, 14),   -- days relative to the due date (negative = before)
    'cc_self', true,                 -- copy info@ on every e-mail sent
    'reply_to', '')
)) on conflict (key) do nothing;

-- 7 · the log may say 'billing' (008 listed the areas; the worker and the page write under this one) --------------------
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing'));

-- 8 · row-level security: Semasa's uploaders, as every other Semasa table --------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['semasa_clients', 'semasa_projects', 'semasa_billing_docs', 'semasa_billing_events', 'semasa_billing_outbox',
                           'semasa_billing_counters']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "semasa billing: uploaders read" on public.%I', t);
    execute format('create policy "semasa billing: uploaders read" on public.%I for select to authenticated using (public.semasa_is_uploader())', t);
    execute format('drop policy if exists "semasa billing: uploaders insert" on public.%I', t);
    execute format('create policy "semasa billing: uploaders insert" on public.%I for insert to authenticated with check (public.semasa_is_uploader())', t);
    execute format('drop policy if exists "semasa billing: uploaders update" on public.%I', t);
    execute format('create policy "semasa billing: uploaders update" on public.%I for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader())', t);
    execute format('drop policy if exists "semasa billing: uploaders delete" on public.%I', t);
    execute format('create policy "semasa billing: uploaders delete" on public.%I for delete to authenticated using (public.semasa_is_uploader())', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
  end loop;
end $$;
-- a receipt or an invoice that has been issued is a record: its number and the words on it never change again
create or replace function public.semasa_billing_guard() returns trigger
language plpgsql as $$
begin
  if old.status <> 'draft' and current_setting('role', true) <> 'service_role' then
    if new.number is distinct from old.number or new.kind <> old.kind or new.issue_date is distinct from old.issue_date then
      raise exception 'semasa billing: % is issued; its number, kind and issue date cannot change', old.number;
    end if;
    if old.status in ('paid', 'void', 'converted', 'sent', 'viewed', 'accepted', 'declined', 'expired', 'issued')
       and (new.items <> old.items or new.total <> old.total or new.client <> old.client) then
      raise exception 'semasa billing: % is issued; put the correction on a new document (void this one if it is wrong)', old.number;
    end if;
  end if;
  return new;
end $$;
drop trigger if exists semasa_billing_docs_guard on public.semasa_billing_docs;
create trigger semasa_billing_docs_guard before update on public.semasa_billing_docs
  for each row execute function public.semasa_billing_guard();

-- 9 · ISSUE: the next number for the kind and year, taken atomically, never reused -------------------------------------
create or replace function public.semasa_billing_issue(p_id uuid) returns text
language plpgsql security definer set search_path = public as $$
declare
  d      public.semasa_billing_docs%rowtype;
  v_pfx  text;
  v_year int;
  v_last int;
  v_num  text;
  v_set  jsonb;
begin
  if not public.semasa_is_uploader() then
    raise exception 'semasa billing: not allowed';
  end if;
  select * into d from public.semasa_billing_docs where id = p_id for update;
  if not found then raise exception 'semasa billing: document not found'; end if;
  if d.status <> 'draft' then raise exception 'semasa billing: % is already issued', d.number; end if;
  if jsonb_array_length(d.items) = 0 then raise exception 'semasa billing: nothing to issue (no items)'; end if;
  if coalesce(d.client->>'name', '') = '' then raise exception 'semasa billing: choose the client first'; end if;
  select value into v_set from public.semasa_settings where key = 'billing';
  v_pfx  := coalesce(v_set->'prefix'->>d.kind, case d.kind when 'quotation' then 'QT' when 'invoice' then 'INV' else 'RPT' end);
  v_year := extract(year from coalesce(d.issue_date, current_date))::int;
  insert into public.semasa_billing_counters (prefix, year, last) values (v_pfx, v_year, 1)
    on conflict (prefix, year) do update set last = public.semasa_billing_counters.last + 1
    returning last into v_last;
  v_num := v_pfx || '-' || v_year || '-' || lpad(v_last::text, 3, '0');
  update public.semasa_billing_docs
     set number = v_num, status = 'issued', issue_date = coalesce(issue_date, current_date),
         due_date = case when kind = 'receipt' then null else coalesce(due_date, coalesce(issue_date, current_date)
                      + coalesce((v_set->'days'->>(case when kind = 'quotation' then 'quotation_valid' else 'invoice_due' end))::int, 30)) end
   where id = p_id;
  insert into public.semasa_billing_events (doc_id, kind, detail, actor) values (p_id, 'issued', jsonb_build_object('number', v_num), auth.uid());
  return v_num;
end $$;
revoke all on function public.semasa_billing_issue(uuid) from public, anon;
grant execute on function public.semasa_billing_issue(uuid) to authenticated;

-- 10 · the public view: anyone holding the link reads the document and the company's details; nothing else ------------
create or replace function public.semasa_billing_public(p_token text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  d     public.semasa_billing_docs%rowtype;
  v_set jsonb;
  first boolean;
begin
  if p_token is null or length(p_token) < 16 then return null; end if;
  select * into d from public.semasa_billing_docs where token = p_token and status <> 'draft';
  if not found then return null; end if;
  select value into v_set from public.semasa_settings where key = 'billing';
  first := d.viewed_at is null;
  update public.semasa_billing_docs
     set viewed_at = coalesce(viewed_at, now()),
         status = case when status = 'sent' then 'viewed' else status end
   where id = d.id;
  if first then
    insert into public.semasa_billing_events (doc_id, kind, detail) values (d.id, 'viewed', jsonb_build_object('via', 'link'));
  end if;
  return jsonb_build_object(
    'doc', jsonb_build_object('kind', d.kind, 'number', d.number, 'status', case when d.status = 'sent' then 'viewed' else d.status end,
      'client', d.client, 'items', d.items, 'currency', d.currency, 'tax_rate', d.tax_rate, 'discount', d.discount,
      'subtotal', d.subtotal, 'tax', d.tax, 'total', d.total, 'issue_date', d.issue_date, 'due_date', d.due_date,
      'terms', d.terms, 'notes', d.notes, 'reference', d.reference, 'payment', d.payment, 'lang', d.lang, 'paid_at', d.paid_at,
      'pdf_url', d.pdf_url, 'token', d.token,
      'project', (select name from public.semasa_projects where id = d.project_id),
      'parent_number', (select number from public.semasa_billing_docs where id = d.parent_id)),
    'company', coalesce(v_set->'company', '{}'::jsonb),
    'bank', case when d.kind = 'invoice' then coalesce(v_set->'bank', '{}'::jsonb) else '{}'::jsonb end);
end $$;
revoke all on function public.semasa_billing_public(text) from public;
grant execute on function public.semasa_billing_public(text) to anon, authenticated;

-- 11 · the database wakes the worker when an e-mail is queued (same Vault token and repo as 004) ------------------------
create or replace function public.semasa_notify_billing_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the billing worker runs on its daily schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'billing_pending', 'client_payload', jsonb_build_object('id', new.id, 'action', new.action))
  );
  return new;
end $$;
drop trigger if exists semasa_billing_outbox_notify on public.semasa_billing_outbox;
create trigger semasa_billing_outbox_notify after insert on public.semasa_billing_outbox
  for each row when (new.status = 'pending') execute function public.semasa_notify_billing_pending();

-- Check (should print 6 | 1 | 1 | 3):
--   select (select count(*) from information_schema.tables where table_name in
--             ('semasa_clients','semasa_projects','semasa_billing_docs','semasa_billing_events','semasa_billing_outbox','semasa_billing_counters')),
--          (select count(*) from public.semasa_settings where key = 'billing'),
--          (select count(*) from pg_constraint where conname = 'semasa_log_area_check' and pg_get_constraintdef(oid) like '%billing%'),
--          (select count(*) from public.semasa_billing_counters);
