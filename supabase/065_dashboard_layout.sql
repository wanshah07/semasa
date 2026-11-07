-- 065 · Which widgets the home dashboard shows (Wan, 7 Nov 2026: the dashboard configuration panel). The page reads
-- settings.dashboard = {"hidden": ["chart", "queue", ...]} and saves it from Papan → "Susun papan"
-- (components/ui/dashboard-configuration.tsx). Nothing else reads it. Empty means every widget shows. Safe to re-run.

insert into public.semasa_settings (key, value) values ('dashboard', '{}'::jsonb) on conflict (key) do nothing;
