-- Semasa · Kanvas: a Canva-like editor in the page (Fabric.js, MIT). Every design Wan makes or edits is kept here.
-- Run ONCE in the SQL editor, after 001–014. Idempotent: safe to run again.
--
-- Wan, 26 Sep 2026: "add ratio layout option as attachment / add any repo that the design can similar like canva".
--
-- SAFE IN A SHARED PROJECT (KPI): it creates one table (semasa_canvas) with its own policies and trigger. No other
-- app's table, policy or function is read or changed. No worker reads it: the page draws and saves by itself.
--
-- What is stored, kept small on purpose:
--   doc        the design as Fabric.js JSON. Pictures inside it are ADDRESSES (the uploads bucket), never the
--              pictures themselves, so a design is a few kilobytes; a hard cap stops a pasted picture bloating it.
--   preview    one PNG of the finished design, in semasa-reference under the owner's folder (replaced on each save).
--   assets     the pictures uploaded INTO this design, so deleting the design deletes them too.

create table if not exists public.semasa_canvas (
  id            uuid primary key default gen_random_uuid(),
  name          text        not null default 'Reka bentuk',
  width         int         not null,
  height        int         not null,
  size_id       text,                                       -- the preset (web/src/lib/sizes.js), or null for custom
  doc           jsonb       not null default '{}'::jsonb,
  preview_url   text,
  preview_path  text,
  assets        text[]      not null default '{}',
  source        text,                                       -- 'fragrance' when opened from a Wangian design
  source_id     uuid,                                       -- that design's media job
  created_by    uuid        references auth.users (id) on delete set null,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint semasa_canvas_size_check check (width between 200 and 4096 and height between 200 and 4096),
  constraint semasa_canvas_doc_check  check (pg_column_size(doc) < 1500000)
);
create index if not exists semasa_canvas_owner_idx on public.semasa_canvas (created_by, updated_at desc);

drop trigger if exists semasa_canvas_set_updated_at on public.semasa_canvas;
create trigger semasa_canvas_set_updated_at before update on public.semasa_canvas
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_canvas enable row level security;
drop policy if exists "semasa canvas: uploaders read" on public.semasa_canvas;
create policy "semasa canvas: uploaders read" on public.semasa_canvas
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa canvas: uploaders insert" on public.semasa_canvas;
create policy "semasa canvas: uploaders insert" on public.semasa_canvas
  for insert to authenticated with check (public.semasa_is_uploader() and created_by = auth.uid());
drop policy if exists "semasa canvas: uploaders update" on public.semasa_canvas;
create policy "semasa canvas: uploaders update" on public.semasa_canvas
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa canvas: uploaders delete" on public.semasa_canvas;
create policy "semasa canvas: uploaders delete" on public.semasa_canvas
  for delete to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_canvas from anon;
grant select, insert, update, delete on public.semasa_canvas to authenticated;

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from information_schema.tables where table_name = 'semasa_canvas'),
--          (select (count(*) = 4)::int from pg_policies where tablename = 'semasa_canvas'),
--          (select count(*) from pg_trigger where tgname = 'semasa_canvas_set_updated_at');
