-- My designs (Wan, 4 Oct 2026): a text-free design saved once and filled by every draft.
-- SAFE IN A SHARED PROJECT (KPI): it adds two rows to semasa_settings and nothing else. The browser can already edit
-- semasa_settings (policy "uploaders edit, not publishing"); it cannot insert, which is why the rows are made here.
--   designs          a list of designs: {id, name, look, cover, middle, closing, single, accent, paper, bg, scrim, mascot, eyebrow}
--   default_design   {"id": "<design id>"} or {}: the design new drafts use when the idea chose no look of its own
-- Run once. Running it again changes nothing.

insert into public.semasa_settings (key, value) values
  ('designs', '[]'::jsonb),
  ('default_design', '{}'::jsonb)
on conflict (key) do nothing;

-- Check (should print: 2):
--   select count(*) from public.semasa_settings where key in ('designs', 'default_design');
