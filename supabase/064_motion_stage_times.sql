-- 064 · When each stage of a Motion film began (Wan, 7 Nov 2026: a tracker "idea > storyboard > motion", with times).
--
-- 063 added `stage` (what a working film is doing now). This adds `stage_times`, a map of stage -> when it began, written by
-- backend/semasa/motion.py set_stage at each boundary: {"storyboard": "...", "pictures": "...", "film": "...", "done": "..."}.
-- A new run starts at the storyboard and clears the old stamps. The page (components/MotionLab.jsx) draws the tracker from it:
-- Idea (the row's created_at) -> Storyboard -> Pictures -> Film. Until this is applied the worker still writes the stage,
-- only without the times, and the tracker shows the steps with no clock. Safe to re-run.

alter table public.semasa_motions add column if not exists stage_times jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';
