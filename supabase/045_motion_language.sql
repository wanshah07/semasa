-- 045 · The words of a motion video in Malay, English, or both (Wan, 24 Oct 2026: "choice for english, malay, or english +
-- malay version"). Until now the language followed the stream (ws.regulab = BM, LinkedIn = EN) with no way to change it.
--
--   language   bm | en | both.  'both' puts the Malay line and the English line on screen together, Malay first.
--              The page defaults it from the stream; an idea's motion keeps the stream's own language.
--
-- SAFE IN A SHARED PROJECT (KPI): semasa_motions only. Run once after 044; re-running changes nothing.

alter table public.semasa_motions add column if not exists language text not null default 'bm';
alter table public.semasa_motions drop constraint if exists semasa_motions_language_check;
alter table public.semasa_motions add constraint semasa_motions_language_check check (language in ('bm', 'en', 'both'));
-- rows made before this column: LinkedIn ones were written in English
update public.semasa_motions set language = 'en' where stream = 'linkedin' and language = 'bm';
