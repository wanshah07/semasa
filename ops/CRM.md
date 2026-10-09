# CRM · contacts, stages and marketing e-mail that goes out by itself (9 Oct 2026)

Wan: *"add CRM system as one new segment and we allow to send email automatically to send marketing material"*, with
EspoCRM (github.com/espocrm/espocrm) as the reference.

## What was taken from EspoCRM, and what was not
EspoCRM's shape is Lead → Contact → Account, Campaign + MassEmail + TargetList, EmailQueueItem, CampaignLogRecord. One
consultancy does not need the Lead/Contact split, Accounts, Opportunities, or a tracking server, so Semasa has:
- **a contact** (`semasa_crm_contacts`): one row per person with a **stage** (lead → prospect → client / dormant / lost)
  instead of a conversion, tags, the e-mail language, a **consent** flag with its **source and date** (PDPA 2010 s.43), an
  unsubscribe token, an optional link to the Bil client, a next action and its date;
- **a campaign** (`semasa_crm_campaigns`): the words (`{{name}}` and `{{company}}` are filled per contact), an audience
  (stages / tags / language; empty = everyone who consented), a kind — **broadcast** (once, at `send_at`) or **welcome**
  (automatic, to every new consenting contact, once each) — and the counts;
- **an outbox row per contact per campaign** (`semasa_crm_outbox`), the words frozen when queued, sent once;
- **an activity line** per contact (`semasa_crm_activities`): note, call, meeting, e-mail, WhatsApp, campaign sent, stage
  change, unsubscribe.
Not built, said plainly: open/click tracking (needs a pixel/link host and is of doubtful value at this list size), A/B,
bounce handling (a bounce lands in Wan's inbox as a normal reply), attachments (the `attachments` column exists; the worker
does not attach yet — link to a public PDF in the body instead), WhatsApp sending.

## Set up once
1. Supabase SQL editor (KPI project) → run `supabase/031_crm.sql` (prints `4 | 16 | 2 | 1`). Applied on 9 Oct 2026.
2. GitHub → the `CRM` workflow uses the Billing secrets (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `COMPOSIO_CONSUMER_KEY`)
   and the variable `SEMASA_SITE_URL` (the unsubscribe link's host). Nothing new to add.
3. The vault secrets from 004/028 (`semasa_github_dispatch_token`, `semasa_github_dispatch_repo`) wake the run within
   seconds of a Send; without them it runs on its hourly schedule only.
4. Settings row `crm` (`semasa_settings`): `daily_cap` 200, `per_run` 60, the PDPA footer line in both languages, `test_to`
   (blank = the company e-mail under Bil settings).

## How it flows
```
Contact (consent + source)  ──►  Campaign (words, audience, when)  ──►  Send / Schedule / Activate
                                        │
                              semasa_crm_queue(campaign): one outbox row per CONSENTING contact in the audience,
                              words filled and frozen; skips no-consent / unsubscribed / no e-mail and says how many
                                        │  (database → repository_dispatch 'crm_pending')
                              crm.yml → python -m semasa.crm: sends pending rows of DUE campaigns from Wan's Gmail
                              (Composio For You, the Bil sender), footer + unsubscribe link under each, checks consent
                              AGAIN at send time, stops at per_run / daily_cap, tallies, marks a broadcast 'sent'
                                        │
                              footer link #crm/unsub/<token> → semasa_crm_unsubscribe: dated, never undone by a click
```
- **Test send**: the composer's "Send a test to me" queues one `is_test` row to `test_to`; it goes through the same worker
  and footer, is never counted, and never needs consent (the test contact row "Wan (ujian)" is made once).
- **Pause**: a scheduled/sending campaign set to `paused` sends nothing until resumed; rows already sent stay sent.
- **Caps**: Google Workspace allows 2,000 a day; the cap is 200 to protect the mailbox's reputation (the same address
  sends invoices). The worker says `left: N` when it stops short, and the hourly run carries on.
- **Why a withdrawn consent is checked twice**: the queue function skips at click time, the worker skips again at send
  time, because a person can unsubscribe between the two (and the unsubscribe function also flips their pending rows to
  `skipped`).

## Files
`supabase/031_crm.sql` · `backend/semasa/crm.py` (+ `tests/test_crm.py`) · `.github/workflows/crm.yml` ·
`web/src/lib/crm.js` (+ `crm.test.mjs`) · `web/src/pages/CrmTab.jsx` · `web/src/pages/CrmUnsubscribe.jsx`.

## Second pass, 9 Oct 2026: WhatsApp, and edit / delete that reach the mailbox (`supabase/032_crm_channels.sql`)
Wan: *"make sure the CRM include whatsapp blast, for email make sure I can edit, delete from the system and it will delete
in the email"*.

- **Channel.** A campaign is e-mail or WhatsApp. A WhatsApp campaign queues one row per consenting contact with a usable
  phone (digits only; `012-345 6789` → `60123456789`), the same PDPA gate as e-mail, with a "Reply STOP" line and the
  unsubscribe link under every message.
- **Two ways a WhatsApp campaign goes out.** With a WhatsApp Business **phone number id** saved in the CRM tab (Composio's
  `whatsapp` toolkit connected to the Meta Business account), the worker sends it itself (`WHATSAPP_SEND_MESSAGE`). With
  none, the campaign becomes a **blast board**: one `wa.me` link per contact with the words filled in, Open → send in
  WhatsApp → press Sent; the row is then counted like any other. Meta's rule applies to the API only: free text is allowed
  within 24 hours of the person's last message, otherwise only an approved template goes through and the worker records
  the refusal word for word. The board has no such limit because it is Wan's own phone sending.
- **Edit reaches the queue.** Saving a campaign that is already scheduled / sending / paused rewrites the words on every
  row still pending (`semasa_crm_refill`). Rows already sent are history and never change.
- **Delete reaches Gmail.** Deleting a campaign asks whether the e-mails already sent should also go to Gmail's Trash; yes
  flags them, the worker calls `GMAIL_MOVE_TO_TRASH` on each (recoverable in Trash for 30 days), deletes the rows one by
  one, and deletes the campaign when none is left (status `deleting` meanwhile). A single sent e-mail can be deleted from
  the contact's record the same way. A WhatsApp message cannot be unsent by any API; it is deleted from the system only
  and the page says so.
- Not done, said plainly: reading a STOP reply (needs a Meta webhook; the unsubscribe link does the job today), template
  messages for cold WhatsApp outreach (create them in Meta Business Suite; the worker sends free text only).
