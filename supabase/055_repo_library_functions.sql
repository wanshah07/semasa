-- 055 · Pustaka repo for EVERY function, not only motion (Wan, 26 Oct 2026: "the repo library only for style motion video,
-- I want put all function repo"). The library already took any GitHub link; what leaned to video was the category list
-- (motion first, nothing for agents, documents, APIs, security ...) and the AI's brief. Three changes:
--   1. semasa_repo_library.functions: what the repo can DO, one line each, written from its README (the card shows it)
--   2. the stored category list (settings.repo_library) is widened; the stored list beats the code's default, so it is set here
--      and a category Wan already used keeps its place (the list only ever grows: nothing a row uses is removed)
--   3. the three repos already filed are read again so they get their functions list; their summary and safety are rewritten
--      from the same reading, and a category Wan chose by hand is kept (category_by = 'wan')
-- Safe to re-run.

alter table public.semasa_repo_library add column if not exists functions text[] not null default '{}';

insert into public.semasa_settings (key, value)
values ('repo_library', jsonb_build_object('categories', to_jsonb(array[
  'motion','video','suara','muzik','imej','3d','kemahiran-ai','agen-ai','mcp','scraper','pelayar','regulatori','dokumen','web',
  'frontend','api','data','analitik','automasi','pemasaran','keselamatan','devops','terjemahan','alatan','lain'])))
on conflict (key) do update
  set value = jsonb_set(coalesce(public.semasa_settings.value, '{}'::jsonb), '{categories}', to_jsonb(array[
  'motion','video','suara','muzik','imej','3d','kemahiran-ai','agen-ai','mcp','scraper','pelayar','regulatori','dokumen','web',
  'frontend','api','data','analitik','automasi','pemasaran','keselamatan','devops','terjemahan','alatan','lain']));

update public.semasa_repo_library set status = 'pending', attempts = 0 where status = 'done' and functions = '{}';
notify pgrst, 'reload schema';
