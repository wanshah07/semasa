-- 053 · The caption of each platform, written with the film (Wan, 26 Oct 2026: "make sure terus setkan caption ikut platform").
--
-- The worker writes one caption per platform of the film's stream when it finishes the film (backend/semasa/motion_captions.py), in the
-- film's language and its stream's voice, fitted to the platform's limits: {"instagram": "...", "facebook": "...", "threads": "..."}
-- for ws.regulab, {"linkedin": "..."} for the LinkedIn stream. The Post this film panel starts from them. Empty on films made before.
-- Safe to re-run. Run it BEFORE the worker that writes it is deployed.

alter table public.semasa_motions add column if not exists captions jsonb not null default '{}'::jsonb;
