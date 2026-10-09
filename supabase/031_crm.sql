-- 031 · CRM (Wan, 9 Oct 2026: "add CRM system as one new segment and we allow to send email automatically to send
-- marketing material", with EspoCRM as the reference). Four tables in EspoCRM's shape, cut down to what one consultancy
-- runs: a CONTACT (EspoCRM's Lead + Contact in one row, with a stage instead of a conversion), a CAMPAIGN (Campaign +
-- MassEmail: the words, the audience, when it goes), an OUTBOX row per contact per campaign (EmailQueueItem) that the worker
-- sends from Wan's own Gmail, and an ACTIVITY line per contact (CampaignLogRecord + notes/calls/meetings).
--
-- SAFE IN A SHARED PROJECT (KPI): four new semasa_ tables, one public function, one dispatch trigger on the same vault
-- secrets 028 uses. Nothing else is touched. Run once; re-running changes nothing.
--
-- Rules the database itself keeps:
--   * a marketing e-mail goes ONLY to a contact with consent = true and unsubscribed_at null (PDPA 2010 s.43: direct
--     marketing needs consent and a way out). The queue function skips everyone else and says how many it skipped;
--   * one contact gets one campaign once (unique campaign_id + contact_id), so a re-run or a second click never doubles;
--   * every contact carries an unsubscribe token; the public function semasa_crm_unsubscribe(token) needs no sign-in and
--     is the link in every marketing mail's footer. Unsubscribing writes the moment and is never undone by a page click
--     (a new consent must be a new, dated, sourced consent);
--   * a campaign's words are frozen on each outbox row when it is queued (subject/body copied), so editing the campaign
--     after "Send" never changes what a person already received or is about to.

create extension if not exists pgcrypto;

-- 1 · contacts: leads and clients in one list, with a stage --------------------------------------------------------------
create table if not exists public.semasa_crm_contacts (
  id              uuid primary key default gen_random_uuid(),
  name            text        not null,                              -- the person
  company         text        not null default '',
  email           text        not null default '',
  phone           text        not null default '',
  stage           text        not null default 'lead',               -- lead | prospect | client | dormant | lost
  source          text        not null default '',                   -- referral | website | linkedin | event | walk-in | ...
  tags            text[]      not null default '{}',
  lang            text        not null default 'bm',
  consent         boolean     not null default false,                -- marketing e-mail allowed (PDPA)
  consent_at      timestamptz,
  consent_source  text        not null default '',                   -- "form on 9 Oct", "WhatsApp 3 Oct", "existing client"
  unsubscribed_at timestamptz,
  unsub_token     text        not null default encode(gen_random_bytes(16), 'hex'),
  client_id       uuid        references public.semasa_clients (id) on delete set null,   -- the Bil client once they are one
  notes           text        not null default '',
  last_contact_at timestamptz,
  next_action     text        not null default '',
  next_action_at  date,
  created_by      uuid        references auth.users (id) on delete set null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint semasa_crm_contacts_name_check  check (length(btrim(name)) > 0),
  constraint semasa_crm_contacts_stage_check check (stage in ('lead', 'prospect', 'client', 'dormant', 'lost')),
  constraint semasa_crm_contacts_lang_check  check (lang in ('bm', 'en')),
  constraint semasa_crm_contacts_email_check check (email = '' or position('@' in email) > 1),
  constraint semasa_crm_contacts_token_key   unique (unsub_token)
);
create unique index if not exists semasa_crm_contacts_email_key on public.semasa_crm_contacts (lower(email)) where email <> '';
create index if not exists semasa_crm_contacts_stage_idx on public.semasa_crm_contacts (stage, updated_at desc);
drop trigger if exists semasa_crm_contacts_set_updated_at on public.semasa_crm_contacts;
create trigger semasa_crm_contacts_set_updated_at before update on public.semasa_crm_contacts
  for each row execute function public.semasa_set_updated_at();

-- 2 · campaigns: one piece of marketing material and who it goes to ------------------------------------------------------
create table if not exists public.semasa_crm_campaigns (
  id            uuid primary key default gen_random_uuid(),
  name          text        not null,
  kind          text        not null default 'broadcast',           -- broadcast (once, at send_at) | welcome (automatic, to every new consenting contact)
  subject       text        not null default '',
  body          text        not null default '',                     -- HTML or plain text; {{name}} {{company}} are filled per contact
  lang          text        not null default 'bm',
  audience      jsonb       not null default '{}'::jsonb,            -- {stages: [...], tags: [...], lang: "bm"|"en"|""}; empty = everyone consenting
  attachments   jsonb       not null default '[]'::jsonb,            -- [{name, url}] public addresses (semasa-generated or a Drive link)
  status        text        not null default 'draft',                -- draft | scheduled | sending | sent | paused
  send_at       timestamptz,                                         -- broadcast: when the worker may start
  sent_count    int         not null default 0,
  error_count   int         not null default 0,
  skipped_count int         not null default 0,
  created_by    uuid        references auth.users (id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint semasa_crm_campaigns_name_check   check (length(btrim(name)) > 0),
  constraint semasa_crm_campaigns_kind_check   check (kind in ('broadcast', 'welcome')),
  constraint semasa_crm_campaigns_status_check check (status in ('draft', 'scheduled', 'sending', 'sent', 'paused')),
  constraint semasa_crm_campaigns_lang_check   check (lang in ('bm', 'en'))
);
drop trigger if exists semasa_crm_campaigns_set_updated_at on public.semasa_crm_campaigns;
create trigger semasa_crm_campaigns_set_updated_at before update on public.semasa_crm_campaigns
  for each row execute function public.semasa_set_updated_at();

-- 3 · outbox: one row per contact per campaign; the worker sends it once ------------------------------------------------
create table if not exists public.semasa_crm_outbox (
  id           uuid primary key default gen_random_uuid(),
  campaign_id  uuid        not null references public.semasa_crm_campaigns (id) on delete cascade,
  contact_id   uuid        not null references public.semasa_crm_contacts (id) on delete cascade,
  to_email     text        not null,
  subject      text        not null,                                 -- the campaign's words, filled, frozen at queue time
  body         text        not null,
  status       text        not null default 'pending',               -- pending | working | sent | error | skipped
  attempts     int         not null default 0,
  error        text        not null default '',
  result       jsonb       not null default '{}'::jsonb,             -- {id, threadId} from Gmail
  is_test      boolean     not null default false,                   -- a test send to Wan himself: never counted, never gated on consent
  created_at   timestamptz not null default now(),
  sent_at      timestamptz,
  constraint semasa_crm_outbox_status_check check (status in ('pending', 'working', 'sent', 'error', 'skipped')),
  constraint semasa_crm_outbox_to_check     check (position('@' in to_email) > 1),
  constraint semasa_crm_outbox_once_key     unique (campaign_id, contact_id, is_test)
);
create index if not exists semasa_crm_outbox_status_idx on public.semasa_crm_outbox (status, created_at);

-- 4 · activities: what happened with a contact (a note, a call, a meeting, an e-mail sent, an unsubscribe) ----------------
create table if not exists public.semasa_crm_activities (
  id          bigint generated always as identity primary key,
  contact_id  uuid        not null references public.semasa_crm_contacts (id) on delete cascade,
  kind        text        not null default 'note',                   -- note | call | meeting | email | whatsapp | campaign | unsubscribe | stage
  at          timestamptz not null default now(),
  title       text        not null default '',
  detail      jsonb       not null default '{}'::jsonb,
  created_by  uuid        references auth.users (id) on delete set null,
  constraint semasa_crm_activities_kind_check check (kind in ('note', 'call', 'meeting', 'email', 'whatsapp', 'campaign', 'unsubscribe', 'stage'))
);
create index if not exists semasa_crm_activities_contact_idx on public.semasa_crm_activities (contact_id, at desc);

-- 5 · row-level security: Semasa's uploaders, as every other Semasa table --------------------------------------------------
do $$
declare t text;
begin
  foreach t in array array['semasa_crm_contacts', 'semasa_crm_campaigns', 'semasa_crm_outbox', 'semasa_crm_activities']
  loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "semasa crm: uploaders read" on public.%I', t);
    execute format('create policy "semasa crm: uploaders read" on public.%I for select to authenticated using (public.semasa_is_uploader())', t);
    execute format('drop policy if exists "semasa crm: uploaders insert" on public.%I', t);
    execute format('create policy "semasa crm: uploaders insert" on public.%I for insert to authenticated with check (public.semasa_is_uploader())', t);
    execute format('drop policy if exists "semasa crm: uploaders update" on public.%I', t);
    execute format('create policy "semasa crm: uploaders update" on public.%I for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader())', t);
    execute format('drop policy if exists "semasa crm: uploaders delete" on public.%I', t);
    execute format('create policy "semasa crm: uploaders delete" on public.%I for delete to authenticated using (public.semasa_is_uploader())', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('grant select, insert, update, delete on public.%I to authenticated', t);
    if not exists (select 1 from pg_publication_tables where pubname = 'supabase_realtime' and schemaname = 'public' and tablename = t) then
      execute format('alter publication supabase_realtime add table public.%I', t);
    end if;
  end loop;
end $$;

-- 6 · queue a campaign: one outbox row per consenting contact in the audience, words filled and frozen ---------------------
--     Returns {queued, skipped_no_consent, skipped_no_email, already}. Called by the page's "Send" / "Schedule" and by the
--     worker for a welcome campaign. The campaign is set to 'scheduled' (or 'sending' when send_at is now or past).
create or replace function public.semasa_crm_queue(p_campaign uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  c         public.semasa_crm_campaigns%rowtype;
  r         record;
  v_stages  text[];
  v_tags    text[];
  v_lang    text;
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
  if length(btrim(c.subject)) = 0 or length(btrim(c.body)) = 0 then raise exception 'semasa: the campaign needs a subject and a body'; end if;
  v_stages := array(select jsonb_array_elements_text(coalesce(c.audience -> 'stages', '[]'::jsonb)));
  v_tags   := array(select jsonb_array_elements_text(coalesce(c.audience -> 'tags', '[]'::jsonb)));
  v_lang   := coalesce(c.audience ->> 'lang', '');
  for r in select * from public.semasa_crm_contacts k
           where (cardinality(v_stages) = 0 or k.stage = any (v_stages))
             and (cardinality(v_tags) = 0 or k.tags && v_tags)
             and (v_lang = '' or k.lang = v_lang)
  loop
    if r.email = '' then n_ne := n_ne + 1; continue; end if;
    if not r.consent or r.unsubscribed_at is not null then n_nc := n_nc + 1; continue; end if;
    if exists (select 1 from public.semasa_crm_outbox o where o.campaign_id = c.id and o.contact_id = r.id and not o.is_test) then
      n_al := n_al + 1; continue;
    end if;
    v_subject := replace(replace(c.subject, '{{name}}', r.name), '{{company}}', r.company);
    v_body    := replace(replace(c.body, '{{name}}', r.name), '{{company}}', r.company);
    insert into public.semasa_crm_outbox (campaign_id, contact_id, to_email, subject, body)
      values (c.id, r.id, r.email, v_subject, v_body);
    n_q := n_q + 1;
  end loop;
  update public.semasa_crm_campaigns
     set status = case when c.kind = 'welcome' then 'scheduled'
                       when c.send_at is null or c.send_at <= now() then 'sending' else 'scheduled' end,
         send_at = coalesce(c.send_at, now()),
         skipped_count = skipped_count + n_nc + n_ne
   where id = c.id;
  return jsonb_build_object('queued', n_q, 'skipped_no_consent', n_nc, 'skipped_no_email', n_ne, 'already', n_al);
end $$;
revoke all on function public.semasa_crm_queue(uuid) from public;
grant execute on function public.semasa_crm_queue(uuid) to authenticated;

-- 7 · the public way out: the footer link; no sign-in, answers the contact's first name and nothing else ------------------
create or replace function public.semasa_crm_unsubscribe(p_token text) returns jsonb
language plpgsql security definer set search_path = public as $$
declare k public.semasa_crm_contacts%rowtype;
begin
  if p_token is null or length(p_token) < 16 then return null; end if;
  select * into k from public.semasa_crm_contacts where unsub_token = p_token;
  if not found then return null; end if;
  if k.unsubscribed_at is null then
    update public.semasa_crm_contacts set unsubscribed_at = now() where id = k.id;
    insert into public.semasa_crm_activities (contact_id, kind, title) values (k.id, 'unsubscribe', 'Berhenti melanggan melalui pautan e-mel');
    update public.semasa_crm_outbox set status = 'skipped', error = 'unsubscribed' where contact_id = k.id and status = 'pending' and not is_test;
  end if;
  return jsonb_build_object('name', split_part(k.name, ' ', 1), 'lang', k.lang, 'already', k.unsubscribed_at is not null);
end $$;
revoke all on function public.semasa_crm_unsubscribe(text) from public;
grant execute on function public.semasa_crm_unsubscribe(text) to anon, authenticated;

-- 8 · the database wakes the worker when a mail is queued (same vault token and repo as 004 / 028) -----------------------
create or replace function public.semasa_notify_crm_pending() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the CRM worker runs on its hourly schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'crm_pending', 'client_payload', jsonb_build_object('campaign', new.campaign_id))
  );
  return new;
end $$;
drop trigger if exists semasa_crm_outbox_notify on public.semasa_crm_outbox;
create trigger semasa_crm_outbox_notify after insert on public.semasa_crm_outbox
  for each row when (new.status = 'pending') execute function public.semasa_notify_crm_pending();

-- 9 · the log may say 'crm'; the settings row the page and worker read ---------------------------------------------------
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing', 'subscription', 'crm'));
insert into public.semasa_settings (key, value) values ('crm', jsonb_build_object(
  'daily_cap', 200,                       -- marketing mails a day from the mailbox (Workspace allows 2,000; keep the sender's reputation)
  'per_run', 60,                          -- mails one worker run sends before stopping (15-minute runner)
  'from_name', 'WS Regulab Solutions',
  'reply_to', '',
  'footer_bm', 'Anda menerima e-mel ini kerana anda bersetuju menerima makluman daripada WS Regulab Solutions.',
  'footer_en', 'You receive this e-mail because you agreed to hear from WS Regulab Solutions.',
  'test_to', ''                           -- where a test send goes (blank = the company e-mail in the billing settings)
)) on conflict (key) do nothing;

-- proof: 4 | 16 | 2 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename like 'semasa_crm_%') as tables,
       (select count(*) from pg_policies where tablename like 'semasa_crm_%') as policies,
       (select count(*) from pg_proc where proname in ('semasa_crm_queue', 'semasa_crm_unsubscribe')) as functions,
       (select count(*) from public.semasa_settings where key = 'crm') as settings;
