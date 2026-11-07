-- 066 · Businesses (Wan, 11 Oct 2026: "business separate to WS REGULAB and VALORITH, I able to add the business / CRM can
-- combine for all business but I can choose for which company / Fragrance under Valorith segment / valorith perlu bil dan
-- asingkan"). One row per business; everything that belongs to one now says which.
--
-- What changes:
--   * semasa_businesses: id (a short slug), name, and `billing`, the same shape settings.billing has had since 028 (company,
--     bank, prefix, days, tax_rate, terms, email). WS REGULAB is seeded with a copy of settings.billing as it is today, so its
--     letterhead, bank, prefixes and terms carry on unchanged. VALORITH starts with its own name, no bank (Wan fills it in),
--     its own prefixes (VAL-QT, VAL-INV, VAL-RPT) and WS REGULAB's terms to edit. More businesses are added from the page.
--   * business_id on clients, projects, billing documents, CRM contacts and CRM campaigns: NOT NULL, default 'wsregulab'.
--     Every existing row (2 clients, 1 invoice INV-2026-015, 1 quotation QT-2026-010 on 7 Nov 2026) is therefore WS REGULAB's.
--   * business_id on receipts and subscriptions: NULLABLE. Null means personal or not yet assigned; nothing is guessed.
--   * counters are kept per business: the primary key becomes (business_id, prefix, year). WS REGULAB's three counters
--     (QT 10, INV 15, RPT 16 for 2026) carry on, so the next numbers are exactly what they would have been.
--   * semasa_billing_issue reads the document's business (prefix, days) and its counter; a number another business already
--     holds is refused with a plain message (document numbers stay unique across all businesses).
--   * semasa_billing_public shows the document's own business letterhead and bank, and says which business it is (the page
--     draws WS REGULAB's logo only on WS REGULAB's papers; another business shows its company.logo_url, else its name).
--   * an issued document cannot move to another business (its number belongs to the one that issued it).
--   * a CRM campaign is queued only to contacts of its own business (semasa_crm_queue, also used by the welcome sweep).
-- settings.billing stays as it is and is only a fallback for a business whose own `billing` is empty. Safe to re-run.

-- 1 · the businesses -------------------------------------------------------------------------------------------------------
create table if not exists public.semasa_businesses (
  id          text primary key,
  name        text        not null,
  billing     jsonb       not null default '{}'::jsonb,
  sort        int         not null default 0,
  active      boolean     not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_businesses_id_check check (id ~ '^[a-z0-9][a-z0-9-]{1,30}$'),
  constraint semasa_businesses_name_check check (length(btrim(name)) > 0)
);
drop trigger if exists semasa_businesses_set_updated_at on public.semasa_businesses;
create trigger semasa_businesses_set_updated_at before update on public.semasa_businesses
  for each row execute function public.semasa_set_updated_at();

insert into public.semasa_businesses (id, name, billing, sort)
select 'wsregulab', 'WS REGULAB', coalesce((select value from public.semasa_settings where key = 'billing'), '{}'::jsonb), 1
on conflict (id) do nothing;

insert into public.semasa_businesses (id, name, billing, sort)
select 'valorith', 'VALORITH', jsonb_build_object(
  'company', jsonb_build_object('name', 'Valorith', 'reg_no', '', 'tagline', '', 'footer', '', 'website', '', 'email', '',
                                'phone', '', 'address', '', 'sst_no', '', 'tin', '', 'signatory', ''),
  'bank', jsonb_build_object('name', '', 'account_name', '', 'account_no', ''),
  'prefix', jsonb_build_object('quotation', 'VAL-QT', 'invoice', 'VAL-INV', 'receipt', 'VAL-RPT'),
  'days', coalesce(b.value->'days', jsonb_build_object('quotation_valid', 30, 'invoice_due', 30)),
  'tax_rate', 0,
  'terms', coalesce(b.value->'terms', '{}'::jsonb),
  'email', coalesce(b.value->'email', '{}'::jsonb) || jsonb_build_object('auto_send', false)
), 2
from (select (select value from public.semasa_settings where key = 'billing') as value) b
on conflict (id) do nothing;

-- 2 · who each row belongs to ----------------------------------------------------------------------------------------------
alter table public.semasa_clients       add column if not exists business_id text not null default 'wsregulab' references public.semasa_businesses (id) on update cascade;
alter table public.semasa_projects      add column if not exists business_id text not null default 'wsregulab' references public.semasa_businesses (id) on update cascade;
alter table public.semasa_billing_docs  add column if not exists business_id text not null default 'wsregulab' references public.semasa_businesses (id) on update cascade;
alter table public.semasa_crm_contacts  add column if not exists business_id text not null default 'wsregulab' references public.semasa_businesses (id) on update cascade;
alter table public.semasa_crm_campaigns add column if not exists business_id text not null default 'wsregulab' references public.semasa_businesses (id) on update cascade;
alter table public.semasa_receipts      add column if not exists business_id text references public.semasa_businesses (id) on update cascade on delete set null;
alter table public.semasa_subscriptions add column if not exists business_id text references public.semasa_businesses (id) on update cascade on delete set null;
create index if not exists semasa_billing_docs_business_idx on public.semasa_billing_docs (business_id, kind, status);
create index if not exists semasa_clients_business_idx on public.semasa_clients (business_id);
create index if not exists semasa_crm_contacts_business_idx on public.semasa_crm_contacts (business_id);

-- 3 · one number sequence per business, prefix and year --------------------------------------------------------------------
alter table public.semasa_billing_counters add column if not exists business_id text not null default 'wsregulab' references public.semasa_businesses (id) on update cascade;
do $$
begin
  if exists (select 1 from pg_constraint where conname = 'semasa_billing_counters_pkey'
             and conrelid = 'public.semasa_billing_counters'::regclass
             and array_length(conkey, 1) = 2) then
    alter table public.semasa_billing_counters drop constraint semasa_billing_counters_pkey;
    alter table public.semasa_billing_counters add constraint semasa_billing_counters_pkey primary key (business_id, prefix, year);
  end if;
end $$;

-- 4 · the settings a document is issued, shown and sent under: its business's own, else the old shared settings ----------
create or replace function public.semasa_billing_settings_for(p_business text) returns jsonb
language sql stable security definer set search_path = public as $$
  select coalesce(
    (select nullif(billing, '{}'::jsonb) from public.semasa_businesses where id = coalesce(p_business, 'wsregulab')),
    (select value from public.semasa_settings where key = 'billing'),
    '{}'::jsonb);
$$;
revoke all on function public.semasa_billing_settings_for(text) from public, anon;
grant execute on function public.semasa_billing_settings_for(text) to authenticated;

-- 5 · an issued document keeps its business ----------------------------------------------------------------------------
create or replace function public.semasa_billing_guard() returns trigger
language plpgsql as $$
begin
  if old.status <> 'draft' and current_setting('role', true) <> 'service_role' then
    if new.number is distinct from old.number or new.kind <> old.kind or new.issue_date is distinct from old.issue_date then
      raise exception 'semasa billing: % is issued; its number, kind and issue date cannot change', old.number;
    end if;
    if new.business_id is distinct from old.business_id then
      raise exception 'semasa billing: % is issued by one business; it cannot move to another', old.number;
    end if;
    if old.status in ('paid', 'void', 'converted', 'sent', 'viewed', 'accepted', 'declined', 'expired', 'issued')
       and (new.items <> old.items or new.total <> old.total or new.client <> old.client) then
      raise exception 'semasa billing: % is issued; put the correction on a new document (void this one if it is wrong)', old.number;
    end if;
  end if;
  return new;
end $$;

-- 6 · ISSUE: the next number for the document's business, kind and year -------------------------------------------------
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
  v_set  := public.semasa_billing_settings_for(d.business_id);
  v_pfx  := coalesce(nullif(v_set->'prefix'->>d.kind, ''), case d.kind when 'quotation' then 'QT' when 'invoice' then 'INV' else 'RPT' end);
  v_year := extract(year from coalesce(d.issue_date, current_date))::int;
  insert into public.semasa_billing_counters (business_id, prefix, year, last) values (d.business_id, v_pfx, v_year, 1)
    on conflict (business_id, prefix, year) do update set last = public.semasa_billing_counters.last + 1
    returning last into v_last;
  v_num := v_pfx || '-' || v_year || '-' || lpad(v_last::text, 3, '0');
  if exists (select 1 from public.semasa_billing_docs where number = v_num) then
    raise exception 'semasa billing: % is already used by another business; give this business its own prefix in Billing settings', v_num;
  end if;
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

-- 7 · the public view shows the document's own business ----------------------------------------------------------------
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
  v_set := public.semasa_billing_settings_for(d.business_id);
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
    'business', d.business_id,
    'bank', case when d.kind = 'invoice' then coalesce(v_set->'bank', '{}'::jsonb) else '{}'::jsonb end);
end $$;
revoke all on function public.semasa_billing_public(text) from public;
grant execute on function public.semasa_billing_public(text) to anon, authenticated;

-- 8 · a campaign reaches its own business's contacts only (032's queue, one line added; the welcome sweep calls the same) --
create or replace function public.semasa_crm_queue(p_campaign uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  c         public.semasa_crm_campaigns%rowtype;
  r         record;
  v_stages  text[];
  v_tags    text[];
  v_lang    text;
  v_phone   text;
  n_q       int := 0;
  n_nc      int := 0;
  n_ne      int := 0;
  n_al      int := 0;
  v_subject text;
  v_body    text;
begin
  if not public.semasa_is_uploader() then raise exception 'semasa: not an uploader'; end if;
  select * into c from public.semasa_crm_campaigns where id = p_campaign;
  if not found then raise exception 'semasa: campaign not found'; end if;
  if c.status = 'deleting' then raise exception 'semasa: this campaign is being deleted'; end if;
  if length(btrim(c.body)) = 0 then raise exception 'semasa: the campaign needs a body'; end if;
  if c.channel = 'email' and length(btrim(c.subject)) = 0 then raise exception 'semasa: an e-mail campaign needs a subject'; end if;
  v_stages := array(select jsonb_array_elements_text(coalesce(c.audience -> 'stages', '[]'::jsonb)));
  v_tags   := array(select jsonb_array_elements_text(coalesce(c.audience -> 'tags', '[]'::jsonb)));
  v_lang   := coalesce(c.audience ->> 'lang', '');
  for r in select * from public.semasa_crm_contacts k
           where k.business_id = c.business_id                        -- 066: a campaign reaches its own business's contacts only
             and (cardinality(v_stages) = 0 or k.stage = any (v_stages))
             and (cardinality(v_tags) = 0 or k.tags && v_tags)
             and (v_lang = '' or k.lang = v_lang)
  loop
    v_phone := public.semasa_crm_phone_digits(r.phone);
    if (c.channel = 'email' and r.email = '') or (c.channel = 'whatsapp' and v_phone = '') then n_ne := n_ne + 1; continue; end if;
    if not r.consent or r.unsubscribed_at is not null then n_nc := n_nc + 1; continue; end if;
    if exists (select 1 from public.semasa_crm_outbox o where o.campaign_id = c.id and o.contact_id = r.id and not o.is_test) then
      n_al := n_al + 1; continue;
    end if;
    v_subject := replace(replace(c.subject, '{{name}}', r.name), '{{company}}', r.company);
    v_body    := replace(replace(c.body, '{{name}}', r.name), '{{company}}', r.company);
    insert into public.semasa_crm_outbox (campaign_id, contact_id, channel, to_email, to_phone, subject, body)
      values (c.id, r.id, c.channel, r.email, case when c.channel = 'whatsapp' then v_phone else '' end,
              case when c.channel = 'whatsapp' then c.name else v_subject end, v_body);
    n_q := n_q + 1;
  end loop;
  update public.semasa_crm_campaigns
     set status = case when c.kind = 'welcome' then 'scheduled'
                       when c.send_at is null or c.send_at <= now() then 'sending' else 'scheduled' end,
         send_at = coalesce(c.send_at, now()),
         skipped_count = skipped_count + n_nc + n_ne
   where id = c.id;
  return jsonb_build_object('queued', n_q, 'skipped_no_consent', n_nc, 'skipped_no_contact', n_ne, 'skipped_no_email', n_ne, 'already', n_al);
end $$;

revoke all on function public.semasa_crm_queue(uuid) from public, anon;
grant execute on function public.semasa_crm_queue(uuid) to authenticated;

-- 9 · row-level security: Semasa's uploaders, as every other Semasa table ------------------------------------------------
alter table public.semasa_businesses enable row level security;
drop policy if exists "semasa businesses: uploaders read" on public.semasa_businesses;
create policy "semasa businesses: uploaders read" on public.semasa_businesses for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa businesses: uploaders insert" on public.semasa_businesses;
create policy "semasa businesses: uploaders insert" on public.semasa_businesses for insert to authenticated with check (public.semasa_is_uploader());
drop policy if exists "semasa businesses: uploaders update" on public.semasa_businesses;
create policy "semasa businesses: uploaders update" on public.semasa_businesses for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
-- no delete policy: a business that has papers keeps them; one no longer used is switched off (active = false)
revoke all on public.semasa_businesses from anon;
grant select, insert, update on public.semasa_businesses to authenticated;

notify pgrst, 'reload schema';
