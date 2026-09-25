-- Semasa · Module A · Row Level Security
-- Anonymous READS of headlines and runs; everything else, and every WRITE, only from a signed-in user who is listed in
-- public.semasa_uploaders (see 001). Being signed in is not enough: in a shared
-- project the other app's users can sign in too. The GitHub runner uses the
-- service_role key, which bypasses RLS by design.

alter table public.isu_semasa_trends enable row level security;
alter table public.media_generations enable row level security;
alter table public.scrape_runs       enable row level security;
alter table public.semasa_uploaders  enable row level security;

-- isu_semasa_trends ----------------------------------------------------------
drop policy if exists "trends: anyone can read" on public.isu_semasa_trends;
create policy "trends: anyone can read"
  on public.isu_semasa_trends for select
  to anon, authenticated
  using (true);

drop policy if exists "trends: signed-in can insert" on public.isu_semasa_trends;
create policy "trends: signed-in can insert"
  on public.isu_semasa_trends for insert
  to authenticated
  with check (public.semasa_is_uploader());
-- no update/delete policy: only service_role (the scraper) may change a row

-- media_generations ----------------------------------------------------------
-- Not public: it carries unapproved Flow A artwork (Studio's rule: only an approved
-- post's artwork is public). 005 enforces the same; either file may be re-run.
drop policy if exists "media: anyone can read" on public.media_generations;
drop policy if exists "media: uploaders can read" on public.media_generations;
create policy "media: uploaders can read"
  on public.media_generations for select
  to authenticated
  using (public.semasa_is_uploader());

drop policy if exists "media: signed-in can insert own" on public.media_generations;
create policy "media: signed-in can insert own"
  on public.media_generations for insert
  to authenticated
  with check (created_by = auth.uid() and status = 'pending' and public.semasa_is_uploader());

-- The owner may re-queue a failed job (error → pending) or delete it.
-- Everything else about the row is the runner's.
drop policy if exists "media: owner can requeue" on public.media_generations;
create policy "media: owner can requeue"
  on public.media_generations for update
  to authenticated
  using (created_by = auth.uid() and public.semasa_is_uploader())
  with check (created_by = auth.uid() and status in ('pending','error'));

drop policy if exists "media: owner can delete" on public.media_generations;
create policy "media: owner can delete"
  on public.media_generations for delete
  to authenticated
  using (created_by = auth.uid() and public.semasa_is_uploader());

-- scrape_runs ----------------------------------------------------------------
drop policy if exists "runs: anyone can read" on public.scrape_runs;
create policy "runs: anyone can read"
  on public.scrape_runs for select
  to anon, authenticated
  using (true);
-- writes: service_role only

-- semasa_uploaders -----------------------------------------------------------
-- A signed-in user may see only whether THEY are on the list (the page uses it
-- to say "this account cannot upload" instead of failing on insert). Nobody
-- edits the list from the browser; add rows in the SQL editor.
drop policy if exists "uploaders: see own row" on public.semasa_uploaders;
create policy "uploaders: see own row"
  on public.semasa_uploaders for select
  to authenticated
  using (user_id = auth.uid());
