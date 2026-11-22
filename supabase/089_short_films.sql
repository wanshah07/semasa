-- Semasa · Short-film categories (Wan, 22 Nov 2026: "Untuk short film ada kan dua kategori - kisah keluarga halal dan cats, dan
-- kategori ini boleh ditambah").
-- Run ONCE in the SQL editor, after 088. Idempotent: safe to run again.
--
-- What it does
--   One row in semasa_settings, `short_films`: {categories: [...], hidden: [...]}. The built-in categories (kisah-keluarga-halal and
--   cats) are a file in the repo (rules/short_films.json), read by the page and the film scripts alike; this row holds only the
--   categories Wan adds in the Motion tab and the built-in ones he hides from its list, merged over the file by id
--   (web/src/lib/shortFilms.js shortFilmLibrary, backend/semasa/short_films.py library). The browser may UPDATE a setting but
--   never INSERT one (005_studio.sql, policy "uploaders edit, not publishing"), so the page cannot make the row itself.
--
-- What it does NOT need
--   No table and no constraint changes. Until this file is run, the two built-in categories are filmed as usual; only saving one
--   of his own is refused, and the page says to run this file.
-- Nothing here posts, approves or drafts: one settings row only. An existing row (and whatever Wan saved in it) is never touched.

insert into public.semasa_settings (key, value)
values ('short_films', '{"categories": [], "hidden": []}'::jsonb)
on conflict (key) do nothing;

-- Check (should print 1):
select count(*) as short_films_row from public.semasa_settings where key = 'short_films';
