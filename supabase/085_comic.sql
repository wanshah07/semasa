-- Semasa · Comic as a Design choice: Wan's own cartoon styles and cartoon series (Wan, 16 to 17 Nov 2026: "remember the comic
-- style so other model can use and render same based on topics / for comic style create multiples cartoon or comic style, and
-- make it series like cartoon series / add comic as choice").
-- Run ONCE in the SQL editor, after 083. Idempotent: safe to run again.
--
-- What it does
--   One row in semasa_settings, `comic`: {styles: [...], series: [...]}. The built-in styles and series are a file in the repo
--   (rules/comic.json), read by the page and the worker alike; this row holds only what Wan adds or edits, merged over the
--   file by id (web/src/lib/comic.js comicLibrary, backend/semasa/comic_library.py library). The browser may UPDATE a setting
--   but never INSERT one (005_studio.sql, policy "uploaders edit, not publishing"), so the page cannot make the row itself.
--
-- What it does NOT need
--   No table and no constraint changes. A comic is a `slides` job in media_generations whose meta carries design "comic" and
--   its own block meta.comic (series, style, script, episode, how the words were checked): `slides` is already an allowed
--   mode, and meta is free-form. Until this file is run, comics are made as usual with the built-in styles and series; only
--   saving one of his own is refused, and the page says to run this file.
-- Nothing here posts, approves or drafts: one settings row only. An existing row (and whatever Wan saved in it) is never touched.

insert into public.semasa_settings (key, value)
values ('comic', '{"styles": [], "series": []}'::jsonb)
on conflict (key) do nothing;

-- Check (should print 1):
select count(*) as comic_row from public.semasa_settings where key = 'comic';
