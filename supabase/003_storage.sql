-- Semasa · Module A · Storage buckets and policies
-- Bucket and policy names are prefixed semasa so this file cannot touch a bucket
-- or policy that belongs to another app in the same project. (`on conflict ... do
-- update` below would otherwise have made an existing private bucket public.)
--   semasa-reference  — what Wan uploads. A public BUCKET, so a file opens by its public link
--                with no credentials (the generation API must fetch it); signed-in WRITE
--                into the uploader's own folder <uid>/…, and no one lists another's files
--   semasa-generated  — what the runner writes back. Opens by its public link, service_role WRITE.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('semasa-reference', 'semasa-reference', true, 52428800,
    array['image/png','image/jpeg','image/webp','image/gif','text/plain','text/markdown','application/pdf']),
  ('semasa-generated', 'semasa-generated', true, 52428800,   -- 50 MB: the free plan's per-file ceiling
    array['image/png','image/jpeg','image/webp','video/mp4','video/webm'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- semasa-reference: anyone OPENS a file by its public link (a public bucket serves /object/public/ with no policy);
-- only its uploader may list or read it through the API, and a listed uploader writes only under their own uid/.
-- There is deliberately no "public read" policy: it let the published anon key LIST every upload (017, 27 Sep 2026).
drop policy if exists "semasa reference: public read" on storage.objects;
drop policy if exists "semasa reference: owner read" on storage.objects;
create policy "semasa reference: owner read"
  on storage.objects for select
  to authenticated
  using (bucket_id = 'semasa-reference' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "semasa reference: owner upload" on storage.objects;
create policy "semasa reference: owner upload"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'semasa-reference' and (storage.foldername(name))[1] = auth.uid()::text
              and public.semasa_is_uploader());

drop policy if exists "semasa reference: owner delete" on storage.objects;
create policy "semasa reference: owner delete"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'semasa-reference' and (storage.foldername(name))[1] = auth.uid()::text);

-- semasa-generated: anyone opens a file by its public link; nothing but service_role writes or lists (no policy at
-- all: the old "public read" let the anon key list every picture, unapproved artwork included; 017)
drop policy if exists "semasa generated: public read" on storage.objects;
