-- 033 · Resit: snap a receipt, the picture goes to Google Drive, the AI reads it and files it (Wan, 9 Oct 2026: "add
-- feature I can snap and take picture and the picture go to google drive, the AI will read the receipt and outline the
-- content and automatically organize").
--
-- One table. The page puts the photo in the semasa-reference bucket (under the uploader's own folder, as every upload)
-- and inserts a `pending` row; the database wakes the worker (repository_dispatch 'receipts_pending'); the worker
-- (backend/semasa/receipts.py) reads the picture with the vision model, uploads it to Google Drive under
-- Semasa/Resit/<YYYY>/<MM>/<date vendor total>.jpg through Composio For You, matches the vendor to a subscription, and
-- writes everything back. The page shows the receipts by month and category and lets Wan correct any field.
--
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, uploader-only RLS, the same vault secrets for the dispatch. Run
-- once; re-running changes nothing.

create table if not exists public.semasa_receipts (
  id              uuid primary key default gen_random_uuid(),
  status          text        not null default 'pending',          -- pending | working | done | error
  image_path      text        not null,                            -- storage path in semasa-reference
  image_url       text        not null,                            -- its public address (the worker and the page read it)
  taken_at        timestamptz not null default now(),
  -- what the AI read, every one correctable in the page
  vendor          text        not null default '',
  doc_date        date,
  total           numeric(12,2),
  currency        text        not null default 'MYR',
  tax             numeric(12,2),
  items           jsonb       not null default '[]'::jsonb,        -- [{name, qty, price}]
  payment_method  text        not null default '',
  category        text        not null default 'other',            -- makan | pengangkutan | bekalan | langganan | utiliti | perjalanan | pejabat | klien | lain
  summary         text        not null default '',                 -- one line, the AI's outline
  confidence      numeric(3,2),                                    -- 0..1 as the reader rated itself
  ai              jsonb       not null default '{}'::jsonb,        -- the raw answer, for the record
  -- where it was filed
  drive_file_id   text        not null default '',
  drive_url       text        not null default '',
  drive_path      text        not null default '',                 -- Semasa/Resit/2026/10
  subscription_id uuid        references public.semasa_subscriptions (id) on delete set null,
  billing_doc_id  uuid        references public.semasa_billing_docs (id) on delete set null,
  notes           text        not null default '',
  error           text        not null default '',
  attempts        int         not null default 0,
  created_by      uuid        references auth.users (id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint semasa_receipts_status_check   check (status in ('pending', 'working', 'done', 'error')),
  constraint semasa_receipts_category_check check (category in ('makan', 'pengangkutan', 'bekalan', 'langganan', 'utiliti', 'perjalanan', 'pejabat', 'klien', 'lain', 'other'))
);
create index if not exists semasa_receipts_status_idx on public.semasa_receipts (status, created_at);
create index if not exists semasa_receipts_date_idx on public.semasa_receipts (doc_date desc);
drop trigger if exists semasa_receipts_set_updated_at on public.semasa_receipts;
create trigger semasa_receipts_set_updated_at before update on public.semasa_receipts
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_receipts enable row level security;
drop policy if exists "semasa receipts: uploaders read" on public.semasa_receipts;
create policy "semasa receipts: uploaders read" on public.semasa_receipts for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa receipts: uploaders insert" on public.semasa_receipts;
create policy "semasa receipts: uploaders insert" on public.semasa_receipts for insert to authenticated with check (public.semasa_is_uploader());
drop policy if exists "semasa receipts: uploaders update" on public.semasa_receipts;
create policy "semasa receipts: uploaders update" on public.semasa_receipts for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa receipts: uploaders delete" on public.semasa_receipts;
create policy "semasa receipts: uploaders delete" on public.semasa_receipts for delete to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_receipts from anon;
grant select, insert, update, delete on public.semasa_receipts to authenticated;
do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = 'semasa_receipts') then
    execute 'alter publication supabase_realtime add table public.semasa_receipts';
  end if;
end $$;

-- the database wakes the worker on a new pending row (and on "Baca semula", which sets pending again)
create or replace function public.semasa_notify_receipts_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the receipts worker runs on its daily schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'receipts_pending', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_receipts_notify on public.semasa_receipts;
create trigger semasa_receipts_notify after insert or update of status on public.semasa_receipts
  for each row when (new.status = 'pending') execute function public.semasa_notify_receipts_pending();

-- the log may say 'receipt'; the settings row the worker reads
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing', 'subscription', 'crm', 'receipt'));
insert into public.semasa_settings (key, value) values ('receipts', jsonb_build_object(
  'drive_root', 'Semasa/Resit',                       -- the folder tree under My Drive: Semasa/Resit/<YYYY>/<MM>
  'drive_account', 'info@kkmhalalconsultant.com',     -- which of the connected Google Drive accounts files them
  'per_run', 20                                       -- receipts one worker run reads before stopping
)) on conflict (key) do nothing;

-- proof: 1 | 4 | 1 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename = 'semasa_receipts') as table_ok,
       (select count(*) from pg_policies where tablename = 'semasa_receipts') as policies,
       (select count(*) from pg_trigger where tgname = 'semasa_receipts_notify') as trigger_ok,
       (select count(*) from public.semasa_settings where key = 'receipts') as settings;
