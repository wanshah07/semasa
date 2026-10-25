-- 046 · A talking mascot and a voice on every motion video (Wan, 24 Oct 2026: "all video can you add mascot looks like
-- talking, and make sure got voice or audio").
--
--   voice    male | female | off.   Microsoft Edge neural voices on the runner (backend/semasa/voice.py): Malay Osman /
--            Yasmin, English Andrew / Ava, picked by the film's language. 'off' makes a silent film as before.
--   mascot   the pose from rules/cards.json (wave | point | confused | shocked), or '' for no mascot. The worker puts the
--            character in the lower part of the frame and moves the mouth on the words of the narration.
--   script   what the writer planned and the voice read: [{kicker, heading, lines, narration, start, duration}], so Wan
--            can read what was said without opening the film.
--
-- SAFE IN A SHARED PROJECT (KPI): semasa_motions only. Run once after 045; re-running changes nothing.

alter table public.semasa_motions add column if not exists voice  text  not null default 'male';
alter table public.semasa_motions add column if not exists mascot text  not null default 'wave';
alter table public.semasa_motions add column if not exists script jsonb not null default '[]'::jsonb;
alter table public.semasa_motions drop constraint if exists semasa_motions_voice_check;
alter table public.semasa_motions add constraint semasa_motions_voice_check check (voice in ('male', 'female', 'off', 'kitten'));   -- 'kitten' is 047's; kept here so re-running 046 never resets it
