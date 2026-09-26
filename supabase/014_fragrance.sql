-- Semasa · Wangian (fragrance): a list of our perfumes, and ad designs made for them with OUR bottle in the picture.
-- Run ONCE in the SQL editor, after 001–013. Idempotent: safe to run again.
--
-- Wan, 26 Sep 2026: "add one more segment for fragrance, design is separate or can try to redesign via canva" and
-- "you will run to find new design and will replace the bottle in the design with our by render or via canva".
--
-- SAFE IN A SHARED PROJECT (KPI): it creates one table (semasa_fragrances) with its own policies and trigger, and widens
-- one check on media_generations (mode 'fragrance'). No other app's table, policy or function is read or changed.
--
-- The flow:
--   1. Wan adds a perfume (name, notes, the claims he has evidence for) and uploads a photo of the bottle;
--   2. the page queues a media job (mode 'fragrance', meta.step 'concepts'): the worker writes three designs;
--   3. Wan picks one (meta.step 'render'): the worker draws it twice, the real bottle cut out and set into the scene,
--      and an AI edit with the bottle as its reference; every word is typeset on top, never drawn by the AI;
--   4. Wan keeps one (meta.step 'save'): the other is deleted. A design never kept is cleared after 7 days.
-- Nothing is published by this: Valorith is scheduled from Semasa only once its publishing is switched on.

create table if not exists public.semasa_fragrances (
  id             uuid primary key default gen_random_uuid(),
  brand          text        not null default 'Valorith',
  name           text        not null,                       -- Noir Rush
  concentration  text        not null default 'Extrait de Parfum',
  size           text        not null default '',            -- 30ml
  notes          text        not null default '',            -- top, heart, base: the concepts are drawn from these
  mood           text        not null default '',            -- how it should feel (dark, warm, playful …)
  claims         text[]      not null default '{}',          -- ONLY claims with evidence in the PIF: the only badges
  footnote       text        not null default '',            -- what an asterisked claim means (*Based on …)
  bottle_url     text,                                       -- the bottle photo (semasa-reference, public read)
  bottle_path    text,
  logo_url       text,                                       -- optional: the brand's logo as a transparent PNG
  logo_path      text,
  created_by     uuid        references auth.users (id) on delete set null,
  created_at     timestamptz not null default now(),
  updated_at     timestamptz not null default now(),
  constraint semasa_fragrances_name_check check (length(btrim(name)) > 0)
);

drop trigger if exists semasa_fragrances_set_updated_at on public.semasa_fragrances;
create trigger semasa_fragrances_set_updated_at before update on public.semasa_fragrances
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_fragrances enable row level security;
drop policy if exists "semasa fragrances: uploaders read" on public.semasa_fragrances;
create policy "semasa fragrances: uploaders read" on public.semasa_fragrances
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa fragrances: uploaders insert" on public.semasa_fragrances;
create policy "semasa fragrances: uploaders insert" on public.semasa_fragrances
  for insert to authenticated with check (public.semasa_is_uploader() and created_by = auth.uid());
drop policy if exists "semasa fragrances: uploaders update" on public.semasa_fragrances;
create policy "semasa fragrances: uploaders update" on public.semasa_fragrances
  for update to authenticated using (public.semasa_is_uploader()) with check (public.semasa_is_uploader());
drop policy if exists "semasa fragrances: uploaders delete" on public.semasa_fragrances;
create policy "semasa fragrances: uploaders delete" on public.semasa_fragrances
  for delete to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_fragrances from anon;
grant select, insert, update, delete on public.semasa_fragrances to authenticated;

-- a fragrance design is a media job like any other, of its own mode (every earlier mode kept exactly as 011 wrote it)
alter table public.media_generations drop constraint if exists media_generations_mode_check;
alter table public.media_generations add constraint media_generations_mode_check
  check (mode in ('recreate', 'prompt', 'slides', 'clip', 'fragrance')
         and (mode <> 'recreate' or reference_url is not null));

-- Check (should print 1 | 1 | 1):
--   select (select count(*) from information_schema.tables where table_name = 'semasa_fragrances'),
--          (select count(*) from pg_constraint where conname = 'media_generations_mode_check'
--             and pg_get_constraintdef(oid) like '%fragrance%'),
--          (select (count(*) = 4)::int from pg_policies where tablename = 'semasa_fragrances');
