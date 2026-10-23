-- 041 · The AI team (Wan, 23 Oct 2026: "for all segments, make sure can have each robot, AI providers and its model, and the
-- model automatically switch to use the fastest rate or if the current use models got any issue ... for API segment, I can
-- see whole progress, can change the model if needed (the system still automatically switch)").
--
-- Two settings rows (backend/semasa/ai_team.py):
--   ai_team        what the page saves: a pinned robot+model per job (reader, image_gen, image_reader), or null for auto.
--                  A pin is a preference: the router still switches away from a pinned robot that is down.
--   ai_team_state  what the router decided on its last run and why (the order, the ones skipped, the pin), for the API tab.
--                  Written by every worker run and by the API status probe; the page only reads it.
-- The image slot's provider check in 016 already takes an OpenAI-dialect painter such as KiosAPI (provider 'openai',
-- base_url https://kiosapi.com/v1); nothing there changes.
--
-- SAFE IN A SHARED PROJECT (KPI): two rows in semasa_settings. Run once; re-running changes nothing.

insert into public.semasa_settings (key, value)
values ('ai_team', '{"pins": {"reader": null, "image_gen": null, "image_reader": null}}'::jsonb)
on conflict (key) do nothing;

insert into public.semasa_settings (key, value)
values ('ai_team_state', '{}'::jsonb)
on conflict (key) do nothing;
