-- Bil: English is the default language of a client, a paper and an e-mail (Wan, 7 Oct 2026: "make the receipt, invoice
-- and quotation in english"). The page writes `lang` explicitly on every row, so this only changes what a row written
-- without one gets; each client and paper can still be switched to Bahasa Malaysia. Run once, after 028.
alter table public.semasa_clients        alter column lang set default 'en';
alter table public.semasa_billing_docs   alter column lang set default 'en';
alter table public.semasa_billing_outbox alter column lang set default 'en';

-- Check (should print 3): the three defaults now read 'en'
--   select count(*) from information_schema.columns where column_name = 'lang'
--     and table_name in ('semasa_clients','semasa_billing_docs','semasa_billing_outbox') and column_default like '%en%';
