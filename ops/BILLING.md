# Bil · quotations, invoices and receipts (7 Oct 2026)

Wan: *"create feature for quotation, invoice and receipt, can auto send email, view, download, send reminder, status …
create the dashboard to overview … register client > Project name > details"*.

## Set up once
1. Supabase SQL editor (KPI project) → run `supabase/028_billing.sql`. It prints `6 | 1 | 1 | 3`.
   It creates `semasa_clients`, `semasa_projects`, `semasa_billing_docs`, `semasa_billing_events`, `semasa_billing_outbox`,
   `semasa_billing_counters`, the settings row `billing`, two functions (`semasa_billing_issue`, `semasa_billing_public`) and the
   outbox trigger that wakes the worker. The counters start at the numbers Wan used by hand (QT 009, INV 014, RPT 016), so the
   next papers are QT-2026-010, INV-2026-015, RPT-2026-017. Nothing else in the project is touched.
2. GitHub → the `Billing` workflow needs the secrets the publisher already has (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
   `COMPOSIO_CONSUMER_KEY`). Optional repository variable `SEMASA_SITE_URL` (default `https://socialmedia.kkmhalalconsultant.com`).
3. Composio For You: the Gmail connection `info@kkmhalalconsultant.com` is already active (checked 7 Oct 2026). E-mail leaves from
   that mailbox, so replies land in Wan's inbox and every mail is in Sent.
4. Semasa → Bil & Resit → Tetapan: check the company block, bank, terms, reminder days. Logo = `web/public/cards/logo.png`.

## How it flows
```
Client (semasa_clients) ──► Project (semasa_projects: name, details, status, dates, budget)
                                   │
   + Sebut harga ─► DRAFT ─ Issue ─► QT-2026-010 ─ Send ─► e-mail + PDF ─► client opens link ─► VIEWED ─► Accepted
                                                                                                   └─► Convert ─► invoice DRAFT
   + Invois ──────► DRAFT ─ Issue ─► INV-2026-015 ─ Send ─► … ─► due date passes ─► OVERDUE (derived) ─► reminders (worker)
                                                                        └─► Mark paid ─► PAID + receipt RPT-2026-017 (issued, e-mailed)
```
* **Draft → Issue.** The page validates, the database allocates the number (`semasa_billing_issue`, atomic per prefix and year)
  and locks the paper: after that the trigger `semasa_billing_guard` refuses any change to its number, items, total or client.
  A mistake is **voided** and a new paper issued; the void number stays in the sequence (an auditor can see it).
* **Send.** A row in `semasa_billing_outbox`. The database fires `repository_dispatch billing_pending`; the `Billing` workflow
  renders the A4 PDF in Chrome (`backend/semasa/billing.py render_pdf`, the SAME template the page shows), keeps it in
  `semasa-generated/billing/<token>/<number>-<client>.pdf`, uploads it inside the Composio workbench for an s3key and calls
  `GMAIL_SEND_EMAIL` **once**. Outcome: outbox `sent` (with Gmail ids) or `error` (with the reason, and a *Try again* button in the
  viewer). A transient failure before the send call retries up to 3 times; the send itself is never retried.
* **View online.** `#bil/<token>` (32 hex chars). `semasa_billing_public` returns the paper and marks it VIEWED on first open.
  The QR on the paper is this link. The page shows status, total, Print / Save as PDF and the worker's PDF.
* **Status.** Stored: draft, issued, sent, viewed, accepted, declined, expired, converted, paid, void. **Derived** (never stored):
  `overdue` (invoice past due, unpaid), `expired` (quotation past validity) — `web/src/lib/billing.js effectiveStatus`. The worker's
  daily sweep stamps `expired` on quotations so the table agrees even when nobody opens the page.
* **Reminders.** `settings.billing.email.reminder_days` (default `-3, 1, 7, 14` days relative to due). The daily run (09:15 MYT)
  queues ONE reminder per due invoice for the latest offset reached and records all earlier ones (`reminders.sent`), so a week of
  downtime is one e-mail, not four. Only invoices that were e-mailed (`sent`/`viewed`) are reminded. *Send reminder* in the page or
  the table's bulk bar queues one by hand.
* **Mark paid.** Writes `paid` + payment (method, date, reference) on the invoice, creates and issues the receipt with the same
  lines, and (tick) e-mails it. Bulk: several invoices, one payment date and method.
* **Download.** The worker's PDF when it is fresh (newer than the document's last change); otherwise the browser's print dialog on
  the same HTML (Save as PDF). Bulk download prints every selected paper as one file, one A4 page each.
* **Projects.** `Pelanggan → Projek`: a client's piece of work (name, details, status lead/active/on_hold/done/cancelled, dates,
  budget, client reference). A document may belong to a project; the project card shows quoted / invoiced / paid / outstanding
  from its documents (`projectSummary`), and each project carries its four stages across (`components/ui/timeline.tsx`,
  the 21st.dev Timeline adapted to Tailwind 3 with no Base UI): opened → quotation → invoice → paid in full / done, with the
  date and the paper's number and status under each, read from the papers rather than kept as a field. The same component
  drawn down is a paper's history in the viewer.
* **Language.** English by default (`settings billing.lang`, `supabase/029`), for the paper and the e-mail alike; a client
  record carries its own language and a paper can be switched in the editor. Bahasa Malaysia stays a full second set of words.

## What the hand-made papers got wrong, and what the template does instead
| Found on QT-2026-009 / INV-2026-014 / RPT-2026-016 | Now |
|---|---|
| Two page sizes (US Letter twice, A4 once); two generators (Print to PDF, jsPDF) | One A4 template, in the page and in the worker |
| Quotation said **Due date** and **Amount due** | **Valid until**, **Quotation total**, acceptance signature block |
| **TAX INVOICE** with 0 % tax and no SST number | **INVOICE**; becomes TAX INVOICE only when `company.sst_no` is set (shown with the number) |
| Receipt named no invoice, no method, no reference | *Payment received* card: for invoice, date, method, reference |
| Recipient address differed between the quotation and its invoice | One client record, copied onto the paper at issue |
| No contact, e-mail or phone on the recipient | Attention, e-mail, phone printed |
| Half-page gap between the items and the totals | The table takes the height it needs; totals follow it |
| Nothing said whether an invoice was paid | PAID stamp + paid-on line; VOID and DRAFT stamps |
| QR code of unknown target | The QR opens the live "view online" page of that paper |

## Files
`supabase/028_billing.sql` · `backend/semasa/billing.py` (+ `tests/test_billing.py`) · `.github/workflows/billing.yml` ·
`web/src/lib/billing.js` (rules, Node-tested in `billing.test.mjs`) · `web/src/lib/billingDoc.js` (the paper) · `web/src/lib/qr.js` ·
`web/src/pages/BillingTab.jsx` (dashboard, table, editor, viewer, clients, projects, settings) · `web/src/pages/BillingPublic.jsx` ·
`web/src/components/ui/table-2.tsx` (+ `table-2-utils/`): the pasted 21st.dev invoices table, adapted to Radix/lucide and fed by props.

## Not done, said plainly
* **e-Invois (LHDN MyInvois)** is not submitted from here. The paper carries a TIN field for the day it is needed; the
  submission itself is a separate integration and needs Wan's decision on phase and scope.
* The Gantt component Wan pasted on 7 Oct (`reui-gantt.tsx`) could not render without its sibling files; the Timeline
  component he pasted the same day replaced it (see Projects above), so no Gantt is pending.
* e-Invois (MyInvois) submission: not built, by Wan's decision on 7 Oct 2026 ("ignore e-vois"). The TIN field stays.
