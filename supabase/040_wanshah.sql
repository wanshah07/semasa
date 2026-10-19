-- Semasa · 040 · Wanshah, the 3D robot mascot
-- Wan, 20 Oct 2026: "3D robot mascot named Wanshah across the app, replace current poses".
-- The four card poses (wave, point, confused, shocked) can each be replaced by a generated Wanshah picture, approved one at a
-- time in Design → Wanshah. Which picture stands in for which pose lives in one settings row; empty means the original pose
-- is drawn, exactly as before. Safe to run again.

insert into public.semasa_settings (key, value)
values ('wanshah', jsonb_build_object('look', '', 'poses', '{}'::jsonb))
on conflict (key) do nothing;

-- Check (should print 1): the row is there
select count(*) from public.semasa_settings where key = 'wanshah';
