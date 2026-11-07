-- 070 · Memori & Arahan: Wan's instructions for the AI chat and the two memory switches (Wan, 7 Nov 2026: "should I add obsidian
-- or memory base so telegram and AI chat can improve auto and remember", with Claude's own settings as the picture).
--
-- Two rows in semasa_settings, because the browser may UPDATE a setting but never INSERT one (005_studio.sql, policy "uploaders
-- edit, not publishing"), so the page cannot make them itself:
--   ai_instructions  {text, updated_at}           free text the chat follows after its own rules (supabase/functions/semasa-chat)
--   ai_memory        {search_chats, auto_memory}  "Search and reference chats" and "Generate memory from chats", both on
--
-- Nothing else needs SQL. The notes the page lists, adds, edits and deletes are semasa_chat_memory, whose policy "chat memory: own"
-- (025_chat_memory.sql) already lets a signed-in uploader do all four to their own rows and nobody else's. The nightly job
-- (backend/semasa/memory_auto.py) writes with the service key and keeps its bookmark in a third row, memory_auto, which it makes
-- itself. A person's change of either row is logged by the existing settings trigger (017_review_fixes.sql), as every setting is.
--
-- Safe to re-run: an existing row (and whatever Wan saved in it) is never touched.

insert into public.semasa_settings (key, value)
values ('ai_instructions', '{"text": "", "updated_at": null}'::jsonb)
on conflict (key) do nothing;

insert into public.semasa_settings (key, value)
values ('ai_memory', '{"search_chats": true, "auto_memory": true}'::jsonb)
on conflict (key) do nothing;

-- Check (should print 2):
select count(*) as ai_memory_rows from public.semasa_settings where key in ('ai_instructions', 'ai_memory');
