-- 032 · CRM, second pass (Wan, 9 Oct 2026: "make sure the CRM include whatsapp blast, for email make sure I can edit,
-- delete from the system and it will delete in the email").
--
-- Three things, on the 031 tables:
--   1. a campaign has a CHANNEL: email (as before) or whatsapp. A WhatsApp campaign queues one row per consenting
--      contact with a phone number (digits only, Malaysian 01x → 601x); the worker sends it through the WhatsApp Business
--      Cloud API when a phone_number_id is set in settings.crm, and the page offers a click-through "blast board"
--      (wa.me links with the words filled in) when it is not — the same consent gate either way;
--   2. EDIT reaches the queue: semasa_crm_refill(campaign) rewrites the words on every row still pending, so a campaign
--      corrected after "Send" goes out corrected. A row already sent is history and is never rewritten;
--   3. DELETE reaches Gmail: semasa_crm_delete(campaign, trash) marks the campaign 'deleting' and, when asked, flags
--      every sent e-mail row for the worker to move to Gmail's Trash (GMAIL_MOVE_TO_TRASH on the message id Gmail gave
--      back); the worker deletes the rows as each mail is trashed and the campaign when none is left. A single sent row
--      can be flagged the same way from the contact's record. A WhatsApp message cannot be unsent by any API, so a
--      WhatsApp row is only deleted from the system, and the page says so.
--
-- SAFE IN A SHARED PROJECT (KPI): columns and functions on semasa_ tables only. Run once; re-running changes nothing.

alter table public.semasa_crm_campaigns add column if not exists channel text not null default 'email';
alter table public.semasa_crm_campaigns drop constraint if exists semasa_crm_campaigns_channel_check;
alter table public.semasa_crm_campaigns add constraint semasa_crm_campaigns_channel_check check (channel in ('email', 'whatsapp'));
alter table public.semasa_crm_campaigns drop constraint if exists semasa_crm_campaigns_status_check;
alter table public.semasa_crm_campaigns add constraint semasa_crm_campaigns_status_check
  check (status in ('draft', 'scheduled', 'sending', 'sent', 'paused', 'deleting'));

alter table public.semasa_crm_outbox add column if not exists channel  text    not null default 'email';
alter table public.semasa_crm_outbox add column if not exists to_phone text    not null default '';
alter table public.semasa_crm_outbox add column if not exists trash_requested boolean not null default false;
alter table public.semasa_crm_outbox drop constraint if exists semasa_crm_outbox_channel_check;
alter table public.semasa_crm_outbox add constraint semasa_crm_outbox_channel_check check (channel in ('email', 'whatsapp'));
alter table public.semasa_crm_outbox drop constraint if exists semasa_crm_outbox_to_check;
alter table public.semasa_crm_outbox add constraint semasa_crm_outbox_to_check
  check ((channel = 'email' and position('@' in to_email) > 1) or (channel = 'whatsapp' and to_phone ~ '^[0-9]{8,15}$'));
-- an e-mail row carries '' in to_phone and a WhatsApp row carries the contact's e-mail only for the record
alter table public.semasa_crm_outbox alter column to_email set default '';
create index if not exists semasa_crm_outbox_trash_idx on public.semasa_crm_outbox (trash_requested) where trash_requested;

-- the phone as WhatsApp wants it: digits only; a Malaysian number written 01x-xxx xxxx becomes 601xxxxxxxx; a number
-- that is not 8 to 15 digits after that is '' (unsendable, counted as "no phone")
create or replace function public.semasa_crm_phone_digits(p text) returns text
language sql immutable as $$
  select case
    when d ~ '^0[0-9]{8,10}$' then '6' || d
    when d ~ '^[0-9]{8,15}$' then d
    else '' end
  from (select regexp_replace(coalesce(p, ''), '[^0-9]', '', 'g') as d) x;
$$;

-- 1 · queue, now by channel ----------------------------------------------------------------------------------------------
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
           where (cardinality(v_stages) = 0 or k.stage = any (v_stages))
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

-- 2 · edit reaches the queue: the words on every row still pending are rewritten from the campaign as it is now ------------
create or replace function public.semasa_crm_refill(p_campaign uuid) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  c public.semasa_crm_campaigns%rowtype;
  n int := 0;
begin
  if not public.semasa_is_uploader() then raise exception 'semasa: not an uploader'; end if;
  select * into c from public.semasa_crm_campaigns where id = p_campaign;
  if not found then raise exception 'semasa: campaign not found'; end if;
  update public.semasa_crm_outbox o
     set subject = case when c.channel = 'whatsapp' then c.name else replace(replace(c.subject, '{{name}}', k.name), '{{company}}', k.company) end,
         body    = replace(replace(c.body, '{{name}}', k.name), '{{company}}', k.company)
    from public.semasa_crm_contacts k
   where o.contact_id = k.id and o.campaign_id = c.id and o.status = 'pending';
  get diagnostics n = row_count;
  return jsonb_build_object('refilled', n);
end $$;
revoke all on function public.semasa_crm_refill(uuid) from public;
grant execute on function public.semasa_crm_refill(uuid) to authenticated;

-- 3 · delete reaches Gmail -------------------------------------------------------------------------------------------------
--     p_trash true: every SENT e-mail row with a Gmail message id is flagged for the worker, which moves the mail to Trash
--     and deletes the row; the campaign is deleted by the worker once no flagged row is left. p_trash false, or nothing
--     sent by e-mail: the campaign and all its rows go now. Returns {trashing: n, deleted: bool}.
create or replace function public.semasa_crm_delete(p_campaign uuid, p_trash boolean default false) returns jsonb
language plpgsql security definer set search_path = public as $$
declare
  n int := 0;
begin
  if not public.semasa_is_uploader() then raise exception 'semasa: not an uploader'; end if;
  if p_trash then
    update public.semasa_crm_outbox set trash_requested = true
     where campaign_id = p_campaign and channel = 'email' and status = 'sent' and coalesce(result ->> 'id', '') <> '';
    get diagnostics n = row_count;
  end if;
  -- whatever is not waiting for Gmail goes now (pending rows, errors, WhatsApp rows, tests)
  delete from public.semasa_crm_outbox where campaign_id = p_campaign and not trash_requested;
  if n = 0 then
    delete from public.semasa_crm_campaigns where id = p_campaign;
    return jsonb_build_object('trashing', 0, 'deleted', true);
  end if;
  update public.semasa_crm_campaigns set status = 'deleting' where id = p_campaign;
  return jsonb_build_object('trashing', n, 'deleted', false);
end $$;
revoke all on function public.semasa_crm_delete(uuid, boolean) from public;
grant execute on function public.semasa_crm_delete(uuid, boolean) to authenticated;

-- one sent row from a contact's record: flag it (e-mail) or delete it outright (WhatsApp, which no API can unsend)
create or replace function public.semasa_crm_delete_row(p_row uuid, p_trash boolean default true) returns jsonb
language plpgsql security definer set search_path = public as $$
declare o public.semasa_crm_outbox%rowtype;
begin
  if not public.semasa_is_uploader() then raise exception 'semasa: not an uploader'; end if;
  select * into o from public.semasa_crm_outbox where id = p_row;
  if not found then return jsonb_build_object('deleted', false); end if;
  if p_trash and o.channel = 'email' and o.status = 'sent' and coalesce(o.result ->> 'id', '') <> '' then
    update public.semasa_crm_outbox set trash_requested = true where id = p_row;
    return jsonb_build_object('trashing', true, 'deleted', false);
  end if;
  delete from public.semasa_crm_outbox where id = p_row;
  return jsonb_build_object('trashing', false, 'deleted', true);
end $$;
revoke all on function public.semasa_crm_delete_row(uuid, boolean) from public;
grant execute on function public.semasa_crm_delete_row(uuid, boolean) to authenticated;

-- a trash request wakes the worker too (same dispatch function as 031)
drop trigger if exists semasa_crm_outbox_trash_notify on public.semasa_crm_outbox;
create trigger semasa_crm_outbox_trash_notify after update of trash_requested on public.semasa_crm_outbox
  for each row when (new.trash_requested and not old.trash_requested) execute function public.semasa_notify_crm_pending();

-- settings: the WhatsApp sender (blank = the page's click-through blast board, nothing sent by the worker)
update public.semasa_settings
   set value = value || jsonb_build_object('whatsapp_phone_number_id', coalesce(value ->> 'whatsapp_phone_number_id', ''),
                                           'whatsapp_footer_bm', coalesce(value ->> 'whatsapp_footer_bm', 'Balas STOP untuk berhenti menerima mesej ini.'),
                                           'whatsapp_footer_en', coalesce(value ->> 'whatsapp_footer_en', 'Reply STOP to stop receiving these messages.'))
 where key = 'crm';

-- proof: 1 | 1 | 3
select (select count(*) from information_schema.columns where table_name = 'semasa_crm_campaigns' and column_name = 'channel') as channel_ok,
       (select count(*) from information_schema.columns where table_name = 'semasa_crm_outbox' and column_name = 'trash_requested') as trash_ok,
       (select count(*) from pg_proc where proname in ('semasa_crm_refill', 'semasa_crm_delete', 'semasa_crm_delete_row')) as functions;
