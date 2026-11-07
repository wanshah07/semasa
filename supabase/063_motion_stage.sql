-- 063 · The stage a Motion film is in (Wan, 7 Nov 2026: Scrape > Idea > Motion (storyboard) > Motion (Picture) > Motion).
--
-- The status stays exactly as it was (waiting / pending / working / done / error: the trigger, the queue and the page read it).
-- `stage` says what a WORKING film is doing right now, written by the worker at each boundary:
--   storyboard  the script and, when a picture maker is ready, the AI-written shot of every scene
--   pictures    each scene's picture, drawn by ChatGPT, Gemini or Cloudflare
--   film        the layout, the check, the render and the upload
--   done        finished
-- Empty means not started, or waiting to run again after a failure. Safe to re-run.

alter table public.semasa_motions add column if not exists stage text not null default '';

notify pgrst, 'reload schema';
