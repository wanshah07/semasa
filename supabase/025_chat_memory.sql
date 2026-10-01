-- Semasa · AI chat memory: saved conversations, a rolling summary, and notes the chat must always remember.
-- Run ONCE in the SQL editor, after 001–024. Idempotent: safe to run again.
--
-- Wan, 1 Oct 2026: "how to ensure the AI Chat memory is stable and always remember".
--
-- A model remembers nothing between calls. What it "remembers" is whatever is sent with each call, so memory is three
-- things kept here and re-sent by supabase/functions/semasa-chat:
--   semasa_chat_messages  every turn, in order (the transcript; survives reload and works from any device)
--   semasa_chat_threads   one row per conversation, with a rolling SUMMARY of the old turns that no longer fit
--   semasa_chat_memory    short notes Wan pins ("remember this"), sent at the top of EVERY call, in every conversation
--
-- Each row belongs to one user and is visible only to that user, and only while they are on semasa_uploaders
-- (the project is shared with another app, so being signed in is not enough). The function reads and writes with the
-- caller's own login, never a service key, so these policies are the only gate.

create table if not exists public.semasa_chat_threads (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users (id) on delete cascade,
  title           text not null default '',
  summary         text not null default '',          -- what the older turns said, written by the model
  summarized_upto bigint not null default 0,         -- id of the last message already folded into `summary`
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint semasa_chat_threads_summary_len check (length(summary) <= 12000)
);

create table if not exists public.semasa_chat_messages (
  id         bigint generated always as identity primary key,
  thread_id  uuid not null references public.semasa_chat_threads (id) on delete cascade,
  user_id    uuid not null references auth.users (id) on delete cascade,
  role       text not null check (role in ('user', 'assistant')),
  content    text not null check (length(content) <= 40000),
  tools      jsonb,                                  -- which tools an answer used, e.g. ["fetch_url","query_semasa"]
  created_at timestamptz not null default now()
);
create index if not exists semasa_chat_messages_thread_idx on public.semasa_chat_messages (thread_id, id);
create index if not exists semasa_chat_threads_user_idx on public.semasa_chat_threads (user_id, updated_at desc);

create table if not exists public.semasa_chat_memory (
  id         uuid primary key default gen_random_uuid(),
  user_id    uuid not null references auth.users (id) on delete cascade,
  note       text not null check (length(note) between 3 and 500),
  source     text not null default 'user' check (source in ('user', 'chat')),   -- typed by Wan, or saved when he asked the chat to remember
  created_at timestamptz not null default now()
);
create index if not exists semasa_chat_memory_user_idx on public.semasa_chat_memory (user_id, created_at);

alter table public.semasa_chat_threads  enable row level security;
alter table public.semasa_chat_messages enable row level security;
alter table public.semasa_chat_memory   enable row level security;

drop policy if exists "chat threads: own" on public.semasa_chat_threads;
create policy "chat threads: own" on public.semasa_chat_threads for all to authenticated
  using (user_id = auth.uid() and public.semasa_is_uploader())
  with check (user_id = auth.uid() and public.semasa_is_uploader());

drop policy if exists "chat messages: own" on public.semasa_chat_messages;
create policy "chat messages: own" on public.semasa_chat_messages for all to authenticated
  using (user_id = auth.uid() and public.semasa_is_uploader())
  with check (user_id = auth.uid() and public.semasa_is_uploader()
              and exists (select 1 from public.semasa_chat_threads t where t.id = thread_id and t.user_id = auth.uid()));

drop policy if exists "chat memory: own" on public.semasa_chat_memory;
create policy "chat memory: own" on public.semasa_chat_memory for all to authenticated
  using (user_id = auth.uid() and public.semasa_is_uploader())
  with check (user_id = auth.uid() and public.semasa_is_uploader());

-- keep a thread's updated_at honest, so the newest conversation is the one that opens
create or replace function public.semasa_chat_touch() returns trigger
language plpgsql as $$
begin
  update public.semasa_chat_threads set updated_at = now() where id = new.thread_id;
  return new;
end $$;
drop trigger if exists semasa_chat_messages_touch on public.semasa_chat_messages;
create trigger semasa_chat_messages_touch after insert on public.semasa_chat_messages
  for each row execute function public.semasa_chat_touch();

-- Check (should print 3 | 3 | 1): the tables, their policies, the touch trigger.
select (select count(*) from pg_tables where schemaname = 'public' and tablename in
          ('semasa_chat_threads', 'semasa_chat_messages', 'semasa_chat_memory')) as tables,
       (select count(*) from pg_policies where schemaname = 'public' and policyname in
          ('chat threads: own', 'chat messages: own', 'chat memory: own')) as policies,
       (select count(*) from pg_trigger where tgname = 'semasa_chat_messages_touch') as touch_trigger;
