-- Semasa · 039 · The generated bucket accepts PDFs
-- Wan, 17 Oct 2026: a quotation's e-mail failed with
--   StorageApiError: {'statusCode': 415, 'error': 'invalid_mime_type', 'message': 'mime type application/pdf is not supported'}
-- Bil renders each document's A4 PDF and stores it in `semasa-generated` before attaching it to the Gmail send
-- (billing.py ensure_pdf). 003_storage.sql listed only pictures and video for that bucket, so Supabase Storage refused
-- the PDF and no quotation, invoice, receipt or reminder could be e-mailed. Add application/pdf. Nothing else changes.
-- Safe to run again.

update storage.buckets
   set allowed_mime_types = (
         select array_agg(distinct m order by m)
           from unnest(coalesce(allowed_mime_types, array[]::text[]) || array['application/pdf']) as m)
 where id = 'semasa-generated';

-- Check (should print 1 | true): the bucket now lists application/pdf
select count(*) as buckets, bool_and('application/pdf' = any (allowed_mime_types)) as pdf_ok
  from storage.buckets where id = 'semasa-generated';
