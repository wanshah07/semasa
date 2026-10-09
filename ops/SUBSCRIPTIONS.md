# Langganan · subscriptions and recurring bills (9 Oct 2026)

Wan: *"can review my email and list pending payment subscription and add to new section"* (with Wallos as the reference).

## What it is
One table, `semasa_subscriptions` (`supabase/030_subscriptions.sql`, applied to the KPI project on 9 Oct 2026), in the shape of
Wallos: vendor, name, amount in the vendor's currency (+ the ringgit the bank actually took for a foreign bill), cycle
(daily / weekly / monthly / yearly / one-time), next payment, last paid, status (active / paused / ended), auto-pay, category,
account reference, link, notes, and the Gmail thread id the fact came from.

- **Langganan tab** (`web/src/pages/SubscriptionsTab.jsx`): tiles (per month estimate in MYR, due in 30 days, overdue, this week),
  the table, add / edit / delete, and **Paid**, which steps `next_payment` one cycle on from the date that was due
  (`lib/subscriptions.js markPaid`: a bill paid late keeps its billing day; two months behind lands on the first date ahead).
- **Papan** (the home dashboard, `pages/HomeTab.jsx`) shows the next 30 days beside the chart.
- Overdue and due-soon are computed from the date every time; nothing has to be re-marked by hand.
- A foreign bill with no `amount_myr` is **not** in the monthly total and the tile says how many were left out; the page never
  invents an exchange rate.

## What the mailbox showed on 9 Oct 2026 (seeded)
16 rows. Pending or worth a look right now: CelcomDigi RM 61.48 due 12 Oct · Unifi Mobile RM 62.55 due 28 Oct (the September bill
had a "missed your bill payment?" on 28 Sep and no receipt in the mailbox) · TIME fibre RM 104.95 due 4 Nov · IKM retention fee
RM 100 (invoice 6 Oct, no due date stated) · Apple iCloud+ RM 11.90 renews 10 Oct · Render USD 7 and Unshape EUR 6 have no
October / late-September receipt, so check whether they are still live · BJAK Myvi quote RM 1,187.50 (roadtax expires 1 Dec) ·
MBOT RM 170 due 12 Jan 2027. Google Workspace's amount is in its PDF only and is seeded as 0: fill it in from the invoice.
Not bills but dated: the Anthropic API key "s" expires 16 Oct; BudgetPixel may delete files over 500 MB from 16 Oct; Dropbox
deletes files if still over quota on 17 Nov.

## Not done, said plainly
- Nothing reads the mailbox automatically: the seed was a one-off review. A new bill is added by hand (or by a later sweep).
- No exchange rate: a USD/EUR bill shows its MYR only when the bank's figure is typed in.
