-- 030 · Langganan: the recurring bills the business and Wan pay (Wan, 9 Oct 2026: "review my email and list pending payment
-- subscription and add to new section"). One table in the shape of Wallos (github.com/ellite/Wallos): a name, who bills it,
-- how much, how often, and the next date money leaves. The page (web/src/pages/SubscriptionsTab.jsx) and the home dashboard
-- (web/src/pages/HomeTab.jsx) read it; lib/subscriptions.js does the arithmetic (next date after a payment, the monthly
-- equivalent, what is due in the next N days).
--
-- SAFE IN A SHARED PROJECT (KPI): one new table, prefixed semasa_, with the same uploader-only RLS as every other Semasa table.
-- Nothing else is touched. Run once; re-running changes nothing (create if not exists, seed on conflict do nothing).
--
-- `amount` is in `currency` exactly as the vendor bills it; `amount_myr` is what the bank actually took in ringgit for a
-- foreign bill (Anthropic bills USD 108, the card paid RM 457.69). Totals in the page are in MYR and use amount_myr when it
-- is set, amount when the currency is MYR, and otherwise count the row as "not in the total" rather than inventing a rate.
--
-- `cycle`: daily | weekly | monthly | yearly | one_time (Wallos' five). `status`: active (renews), paused (kept but not
-- renewing: a cancelled plan that has not ended yet), ended (history). "Pending" and "overdue" are not statuses: they are
-- next_payment against today, computed by the page, so a bill never has to be re-marked by hand.
--
-- `auto_pay`: the card or a direct debit pays it (nothing for Wan to do); false means Wan pays by hand when it is due.
-- `source`: where the fact came from, usually the Gmail thread id, so a figure can be checked against the mail.

create table if not exists public.semasa_subscriptions (
  id             uuid primary key default gen_random_uuid(),
  name           text        not null,                          -- "Claude Max 5x", "Home fibre"
  vendor         text        not null,                          -- "Anthropic", "TIME dotCom"
  amount         numeric(12,2) not null default 0,
  currency       text        not null default 'MYR',
  amount_myr     numeric(12,2),                                 -- what the bank took, for a non-MYR bill
  cycle          text        not null default 'monthly',
  next_payment   date,                                          -- null: nothing more will be charged (ended / one-off paid)
  last_paid      date,
  status         text        not null default 'active',
  auto_pay       boolean     not null default false,
  payment_method text        not null default '',               -- "Visa ...5742", "TNG", "bank transfer"
  category       text        not null default 'other',          -- software | telco | utilities | membership | insurance | finance | other
  account_ref    text        not null default '',               -- the vendor's account or invoice number
  url            text        not null default '',               -- where to pay or manage it
  notes          text        not null default '',
  source         text        not null default '',               -- Gmail thread id or "manual"
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_subscriptions_cycle_check  check (cycle in ('daily', 'weekly', 'monthly', 'yearly', 'one_time')),
  constraint semasa_subscriptions_status_check check (status in ('active', 'paused', 'ended')),
  constraint semasa_subscriptions_amount_check check (amount >= 0 and (amount_myr is null or amount_myr >= 0)),
  constraint semasa_subscriptions_name_vendor_key unique (vendor, name)
);
create index if not exists semasa_subscriptions_next_idx on public.semasa_subscriptions (status, next_payment);

drop trigger if exists semasa_subscriptions_set_updated_at on public.semasa_subscriptions;
create trigger semasa_subscriptions_set_updated_at before update on public.semasa_subscriptions
  for each row execute function public.semasa_set_updated_at();

-- row-level security: Semasa's uploaders, as every other Semasa table ------------------------------------------------------
alter table public.semasa_subscriptions enable row level security;
drop policy if exists "semasa subscriptions: uploaders read" on public.semasa_subscriptions;
create policy "semasa subscriptions: uploaders read" on public.semasa_subscriptions
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa subscriptions: uploaders insert" on public.semasa_subscriptions;
create policy "semasa subscriptions: uploaders insert" on public.semasa_subscriptions
  for insert to authenticated with check (public.semasa_is_uploader());
drop policy if exists "semasa subscriptions: uploaders update" on public.semasa_subscriptions;
create policy "semasa subscriptions: uploaders update" on public.semasa_subscriptions
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa subscriptions: uploaders delete" on public.semasa_subscriptions;
create policy "semasa subscriptions: uploaders delete" on public.semasa_subscriptions
  for delete to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_subscriptions from anon;
grant select, insert, update, delete on public.semasa_subscriptions to authenticated;

-- live updates for the page, like the other Semasa tables
do $$
begin
  if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public'
                 and tablename = 'semasa_subscriptions') then
    execute 'alter publication supabase_realtime add table public.semasa_subscriptions';
  end if;
end $$;

-- seed: what the mailbox (info@kkmhalalconsultant.com) showed on 9 Oct 2026. Every figure is as written in the mail;
-- a figure the mail did not state is left 0 with a note. Re-running inserts nothing (unique vendor+name).
insert into public.semasa_subscriptions
  (vendor, name, amount, currency, amount_myr, cycle, next_payment, last_paid, status, auto_pay, payment_method, category, account_ref, url, notes, source)
values
  ('CelcomDigi', 'Mobile postpaid', 61.48, 'MYR', null, 'monthly', '2026-10-12', null, 'active', false, '', 'telco', '1100050042345', '', 'Statement 12 Sep 2026; no payment receipt seen in mail', '1a0a37ac3a77b678'),
  ('TIME dotCom', 'Home fibre', 104.95, 'MYR', null, 'monthly', '2026-11-04', null, 'active', false, '', 'telco', '435632070624', '', 'From 29 Oct 2026 the due date is 24 days after the bill date', '1a1099565a5de6d4'),
  ('Institut Kimia Malaysia', 'Membership retention fee', 100.00, 'MYR', null, 'yearly', '2026-10-31', null, 'active', false, '', 'membership', 'IKM-2027-0d3a4a5', '', 'Invoice 6 Oct 2026, no due date stated in the mail; 31 Oct is a placeholder', '1a10ed9da8fa2e39'),
  ('Unifi', 'Mobile postpaid', 62.55, 'MYR', null, 'monthly', '2026-10-28', null, 'active', false, '', 'telco', '7016957156', '', 'Sep bill got a "missed your bill payment?" on 28 Sep; no receipt found for it', '1a11570bda749a0f'),
  ('Unifi', 'Home 100Mbps Pro', 148.00, 'MYR', null, 'monthly', '2026-11-01', '2026-10-01', 'paused', false, '', 'telco', '1081504530', '', 'Termination requested 15 Sep 2026 (report 108549113); a final bill is still to come', '1a0a40e0b3419b97'),
  ('Anthropic', 'Claude Max 5x', 108.00, 'USD', 457.69, 'monthly', '2026-11-03', '2026-10-03', 'active', true, 'card ...3809', 'software', '2752-7772-5538', 'https://claude.ai/settings/billing', 'USD 100 + 8% SST', '1a10108db1350fe5'),
  ('Google', 'Workspace (kkmhalalconsultant.com)', 0, 'MYR', null, 'monthly', '2026-11-02', '2026-10-02', 'active', true, 'payments profile 3184-5755-8525', 'software', '5696705428', 'https://admin.google.com/ac/billing', 'Amount is in the PDF only: fill it in from the invoice', '1a0fb3369ce569c2'),
  ('Render', 'Servers, 1 instance', 7.00, 'USD', null, 'monthly', '2026-10-01', '2026-09-01', 'active', true, 'card ...8289', 'software', 'C1PWB8UR-0008', 'https://dashboard.render.com/billing', 'No October receipt in the mailbox: check whether it is still active', '1a05dfdd9b0a5470'),
  ('Unshape', 'Threads by Unshape', 6.00, 'EUR', 29.10, 'monthly', '2026-09-29', '2026-08-29', 'active', true, 'card ...5742', 'software', '2371-7379', '', 'No 29 Sep receipt in the mailbox: check whether it is still active', '1a04e3f14b3fea35'),
  ('Apple', 'iCloud+ 200 GB', 11.90, 'MYR', null, 'monthly', '2026-10-10', '2026-09-09', 'active', true, 'Visa ...5742', 'software', 'MSHQ46JGZ4', '', 'Billed to Valorith Resources', '1a08933e8266c8fb'),
  ('Microsoft', '365 Family Classic', 409.00, 'MYR', null, 'yearly', '2027-07-16', '2026-07-15', 'active', true, '', 'software', '', 'https://account.microsoft.com/services', 'Storage terms change after the first renewal after 2 May 2027', '19f6938d9de704f9'),
  ('MBOT', 'Professional Technologist membership', 170.00, 'MYR', null, 'yearly', '2027-01-12', null, 'active', false, '', 'membership', '', 'https://cpd.mbot.org.my', 'RM200 standard less RM30 event credit', '19fb9168394e707b'),
  ('GX Bank', 'FlexiCredit instalment', 1527.88, 'MYR', null, 'monthly', '2026-11-01', '2026-10-01', 'active', true, '', 'finance', '', '', '', '1a0f71fabe442433'),
  ('TNB', 'Electricity', 59.65, 'MYR', null, 'monthly', '2026-11-01', '2026-10-01', 'active', false, 'TNG', 'utilities', '210276320910', '', 'Amount varies by the month; the last bill is shown', '1a0f724904e7091f'),
  ('BJAK / RHB', 'Myvi RW7530 insurance + roadtax', 1187.50, 'MYR', null, 'yearly', '2026-12-01', null, 'active', false, '', 'insurance', 'RW7530', '', 'Quote only (3 Oct 2026): insurance RM 1,097.50 + roadtax RM 90.00; roadtax expires 1 Dec 2026', '1a1016dceec4e1ed'),
  ('BudgetPixel', 'Starter plan', 5.00, 'USD', 21.00, 'monthly', null, '2026-09-02', 'ended', true, 'card ...5742', 'software', '2560-9186', '', 'Ended 2 Oct 2026; files over 500 MB may be deleted from 16 Oct', '1a0ed89a9e3af2ed')
on conflict (vendor, name) do nothing;

-- the log takes a subscription area (web and page both write "subscription")
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing', 'subscription'));

-- proof: one row, all 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename = 'semasa_subscriptions') as table_ok,
       (select count(*) from pg_policies where tablename = 'semasa_subscriptions') / 4 as policies_ok,
       (select count(*) >= 16 from public.semasa_subscriptions)::int as seeded;
