# Resit · snap a receipt, Drive files it, the AI reads it (9 Oct 2026)

Wan: *"add feature I can snap and take picture and the picture go to google drive, the AI will read the receipt and outline
the content and automatically organize"*.

## How it flows
```
Phone camera / upload (Resit tab)  ──►  semasa-reference bucket (<uid>/…jpg, shrunk to 1600px)
                                         + semasa_receipts row, status pending
                                               │  (database → repository_dispatch 'receipts_pending')
                                   receipts.yml → python -m semasa.receipts
                                         1. vision model reads it: vendor, date, total, currency, tax, items, payment,
                                            category (9 fixed ones), one-line outline, confidence
                                         2. Composio For You files the picture in Google Drive:
                                            Semasa/Resit/<YYYY>/<MM>/<date vendor RMtotal id>.jpg (folders made as needed)
                                         3. vendor matched to a Langganan subscription by name
                                         4. row: done (read + filed) · pending again (something transient, up to 3 tries)
                                            · error (the reason in words on the card)
                                               │
                                   Resit tab: by month and category, totals in MYR, Correct / Read again / Delete,
                                   "mark the subscription paid" when matched, link to the Drive copy
```

## Set up once
1. Supabase SQL editor (KPI project) → run `supabase/033_receipts.sql` (prints `1 | 4 | 1 | 1`).
2. GitHub → the `Receipts` workflow uses the existing secrets (`SUPABASE_*`, `COMPOSIO_CONSUMER_KEY`, the LLM key) and
   variables (`VISION_MODEL` must be a model that reads pictures: `deepseek-v4.1-flash` on rootsys). Nothing new to add.
3. Settings row `receipts` (`semasa_settings`): `drive_root` (`Semasa/Resit`), `drive_account`
   (`info@kkmhalalconsultant.com`, one of the two Google Drive accounts connected in Composio For You), `per_run` (20).

## Rules
- The date is the one printed on the receipt; when the reader cannot read it, the month it was snapped (Malaysia time)
  is the folder, and the date field is left empty for Wan to fill.
- A total in a foreign currency is shown but never converted; the month's total is ringgit only and says so.
- The reader never guesses: an illegible figure is null, and the card says "unsure" under 0.6 confidence.
- Deleting a receipt in Semasa removes the row and the bucket copy; the Google Drive copy stays (it is the filing).
- Correcting a field never triggers a re-read; "Read again" does, and it re-files only if the Drive copy is missing.

## Not done, said plainly
- No OCR fallback when no vision model answers: the card says "the picture reader gave nothing" and Wan fills it in.
- No Bil expense ledger yet: `billing_doc_id` exists on the row for a later link to a client's invoice.
- One picture per receipt; a multi-page invoice is one photo.
