-- The voice alternates from one film to the next in the queue (Wan, 26 Oct 2026: "bukan suara laki perempuan dalam satu video,
-- maksudnya selang seli untuk video queue"): 'auto' is resolved by the worker to the opposite of the previous film's voice.
alter table semasa_motions drop constraint if exists semasa_motions_voice_check;
alter table semasa_motions add constraint semasa_motions_voice_check
  check (voice = any (array['male'::text, 'female'::text, 'off'::text, 'kitten'::text, 'auto'::text]));
notify pgrst, 'reload schema';
