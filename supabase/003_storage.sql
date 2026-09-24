-- Semasa · Module A · Storage buckets and policies
-- Bucket and policy names are prefixed semasa so this file cannot touch a bucket
-- or policy that belongs to another app in the same project. (`on conflict ... do
-- update` below would otherwise have made an existing private bucket public.)
--   semasa-reference  — what Wan uploads. Public READ (the generation API must be able
--                to fetch the address with no credentials), signed-in WRITE
--                into the uploader's own folder <uid>/…
--   semasa-generated  — what the runner writes back. Public READ, service_role WRITE.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('semasa-reference', 'semasa-reference', true, 52428800,
    array['image/png','image/jpeg','image/webp','image/gif','text/plain','text/markdown','application/pdf']),
  ('semasa-generated', 'semasa-generated', true, 524288000,
    array['image/png','image/jpeg','image/webp','video/mp4','video/webm'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- semasa-reference: anyone reads; a listed uploader writes only under their own uid/
drop policy if exists "semasa reference: public read" on storage.objects;
create policy "semasa reference: public read"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'semasa-reference');

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

-- semasa-generated: anyone reads; nothing but service_role writes (no insert policy)
drop policy if exists "semasa generated: public read" on storage.objects;
create policy "semasa generated: public read"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'semasa-generated');
