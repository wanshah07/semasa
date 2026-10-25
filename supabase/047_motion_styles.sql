-- 047 · Attachment-derived motion options. Apply manually AFTER 046, before deploying this UI.
-- No deployment/migration is performed by the PR. Existing rows retain their explicit values.
-- options is independent of style_repo_id; missing/invalid styles fall back in the worker.
alter table public.semasa_motions add column if not exists options jsonb not null default '{}'::jsonb;
alter table public.semasa_motions alter column seconds set default 30;
alter table public.semasa_motions alter column mascot set default '';
alter table public.semasa_motions drop constraint if exists semasa_motions_voice_check;
alter table public.semasa_motions add constraint semasa_motions_voice_check check (voice in ('male', 'female', 'off', 'kitten'));
