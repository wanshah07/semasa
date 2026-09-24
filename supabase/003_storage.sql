-- Semasa · Module A · Storage buckets and policies
--   reference  — what Wan uploads. Public READ (the generation API must be able
--                to fetch the address with no credentials), signed-in WRITE
--                into the uploader's own folder <uid>/…
--   generated  — what the runner writes back. Public READ, service_role WRITE.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('reference', 'reference', true, 52428800,
    array['image/png','image/jpeg','image/webp','image/gif','text/plain','text/markdown','application/pdf']),
  ('generated', 'generated', true, 524288000,
    array['image/png','image/jpeg','image/webp','video/mp4','video/webm'])
on conflict (id) do update
  set public = excluded.public,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- reference: anyone reads, a signed-in user writes only under their own uid/
drop policy if exists "reference: public read" on storage.objects;
create policy "reference: public read"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'reference');

drop policy if exists "reference: owner upload" on storage.objects;
create policy "reference: owner upload"
  on storage.objects for insert
  to authenticated
  with check (bucket_id = 'reference' and (storage.foldername(name))[1] = auth.uid()::text);

drop policy if exists "reference: owner delete" on storage.objects;
create policy "reference: owner delete"
  on storage.objects for delete
  to authenticated
  using (bucket_id = 'reference' and (storage.foldername(name))[1] = auth.uid()::text);

-- generated: anyone reads; nothing but service_role writes (no insert policy)
drop policy if exists "generated: public read" on storage.objects;
create policy "generated: public read"
  on storage.objects for select
  to anon, authenticated
  using (bucket_id = 'generated');
