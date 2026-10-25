-- Optional private Motion attachments. Apply separately; committing does not provision storage.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('semasa-motion-assets', 'semasa-motion-assets', false, 20971520,
        array['image/png','image/jpeg','image/webp','video/mp4','audio/mpeg','audio/wav','application/pdf','text/plain'])
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

-- Same authenticated allowlist as existing reference uploads, but never publicly readable.
drop policy if exists "motion assets: owner insert" on storage.objects;
create policy "motion assets: owner insert" on storage.objects for insert to authenticated
with check (bucket_id = 'semasa-motion-assets' and (storage.foldername(name))[1] = auth.uid()::text
            and public.semasa_is_uploader());
drop policy if exists "motion assets: owner read" on storage.objects;
create policy "motion assets: owner read" on storage.objects for select to authenticated
using (bucket_id = 'semasa-motion-assets' and (storage.foldername(name))[1] = auth.uid()::text
       and public.semasa_is_uploader());
drop policy if exists "motion assets: owner delete" on storage.objects;
create policy "motion assets: owner delete" on storage.objects for delete to authenticated
using (bucket_id = 'semasa-motion-assets' and (storage.foldername(name))[1] = auth.uid()::text
       and public.semasa_is_uploader());
-- Worker service-role downloads bypass RLS. Browser receives only creator-owned paths, no signed/public URLs.
