-- 069 · Telegram bot: talk to Semasa, approve posts, send it links (Wan, 7 Nov 2026: "for telegram bot, try make I can
-- communicate from telegram, approve post and I can attach link so semasa can read").
--
-- How it fits together:
--   * Telegram calls the Edge Function `semasa-telegram` (a webhook). It checks Telegram's secret header, stores the update
--     here in semasa_telegram_inbox and answers at once ("typing…" / "on it"). Group messages are stored for the FAQ reader
--     (faq_sources.py, which read them with getUpdates before; getUpdates stops working once a webhook is set).
--   * Wan's own private messages and button taps wake the "Telegram" workflow (repository_dispatch 'telegram'), which reads
--     them (backend/semasa/telegram_bot.py): /draf, /status, a link becomes an idea on his tap, other text is a question.
--   * ONE Telegram account may command Semasa: the one Wan links with a one-time code from the page (Tetapan → Telegram).
--     Everyone else gets "this bot is private". The link, the codes and the inbox are readable by the service role only.
--   * APPROVE from Telegram goes through the SAME database gate as the page: semasa_telegram_decide() runs the update as
--     Wan's own login (request.jwt.claims), so semasa_posts_gate stamps approved_by/approved_at and semasa_posts_gate_v3
--     refuses a taken slot or duplicate words exactly as it does for the page. It approves only the version Wan was shown
--     (p_version = the post's updated_at when the preview was sent): a post edited since is refused, never approved blind.
--
-- Safe to re-run.

-- 1 · who may command the bot ---------------------------------------------------------------------------------------------
create table if not exists public.semasa_telegram_link (
  id               int primary key default 1 check (id = 1),           -- one owner
  telegram_user_id bigint not null,
  chat_id          bigint not null,
  username         text,
  user_id          uuid not null references auth.users (id) on delete cascade,
  linked_at        timestamptz not null default now()
);
alter table public.semasa_telegram_link enable row level security;
revoke all on public.semasa_telegram_link from anon, authenticated;

create table if not exists public.semasa_telegram_codes (
  code_hash  text primary key,                                         -- sha256 of the code; the code itself is never stored
  user_id    uuid not null references auth.users (id) on delete cascade,
  expires_at timestamptz not null
);
alter table public.semasa_telegram_codes enable row level security;
revoke all on public.semasa_telegram_codes from anon, authenticated;

-- 2 · everything Telegram sends ---------------------------------------------------------------------------------------------
create table if not exists public.semasa_telegram_inbox (
  id         bigint generated always as identity primary key,
  update_id  bigint unique not null,
  kind       text not null check (kind in ('private', 'callback', 'group', 'other')),
  chat_id    bigint,
  from_id    bigint,
  payload    jsonb not null,
  status     text not null default 'new' check (status in ('new', 'working', 'done', 'error', 'skipped')),
  note       text,
  created_at timestamptz not null default now(),
  done_at    timestamptz
);
create index if not exists semasa_telegram_inbox_todo on public.semasa_telegram_inbox (kind, status, id);
alter table public.semasa_telegram_inbox enable row level security;
revoke all on public.semasa_telegram_inbox from anon, authenticated;

-- which version of a draft Wan was shown, so a tap approves exactly that
create table if not exists public.semasa_telegram_sent (
  post_id    uuid primary key references public.semasa_posts (id) on delete cascade,
  version    timestamptz not null,
  chat_id    bigint not null,
  message_id bigint,
  sent_at    timestamptz not null default now()
);
alter table public.semasa_telegram_sent enable row level security;
revoke all on public.semasa_telegram_sent from anon, authenticated;

-- 3 · the page: make a one-time code, see the link, unlink ------------------------------------------------------------------
create or replace function public.semasa_telegram_link_code() returns text
language plpgsql security definer set search_path = public, extensions as $$
declare
  v_code text;
begin
  if auth.uid() is null or not public.semasa_is_uploader() then
    raise exception 'semasa: sign in first';
  end if;
  delete from public.semasa_telegram_codes where expires_at < now() or user_id = auth.uid();
  v_code := upper(encode(extensions.gen_random_bytes(4), 'hex'));      -- 8 characters, 15 minutes, once
  insert into public.semasa_telegram_codes (code_hash, user_id, expires_at)
    values (encode(extensions.digest(v_code, 'sha256'), 'hex'), auth.uid(), now() + interval '15 minutes');
  return v_code;
end $$;

create or replace function public.semasa_telegram_status() returns jsonb
language plpgsql stable security definer set search_path = public as $$
declare
  l public.semasa_telegram_link;
begin
  if auth.uid() is null or not public.semasa_is_uploader() then
    raise exception 'semasa: sign in first';
  end if;
  select * into l from public.semasa_telegram_link where id = 1;
  return jsonb_build_object(
    'linked', l.telegram_user_id is not null,
    'username', l.username,
    'linked_at', l.linked_at,
    'bot', (select value from public.semasa_settings where key = 'telegram_bot'),
    'waiting', (select count(*) from public.semasa_telegram_inbox where kind in ('private', 'callback') and status in ('new', 'working')),
    'groups', (select count(distinct chat_id) from public.semasa_telegram_inbox where kind = 'group'));
end $$;

create or replace function public.semasa_telegram_unlink() returns void
language plpgsql security definer set search_path = public as $$
begin
  if auth.uid() is null or not public.semasa_is_uploader() then
    raise exception 'semasa: sign in first';
  end if;
  delete from public.semasa_telegram_link where id = 1;
  delete from public.semasa_telegram_codes;
end $$;

revoke execute on function public.semasa_telegram_link_code(), public.semasa_telegram_status(), public.semasa_telegram_unlink()
  from public, anon;
grant execute on function public.semasa_telegram_link_code(), public.semasa_telegram_status(), public.semasa_telegram_unlink()
  to authenticated;

-- 4 · the Edge Function: a code sent to the bot links that Telegram account (service role only) --------------------------
create or replace function public.semasa_telegram_claim(p_code text, p_telegram_user_id bigint, p_chat_id bigint,
                                                        p_username text) returns boolean
language plpgsql security definer set search_path = public, extensions as $$
declare
  v_user uuid;
begin
  delete from public.semasa_telegram_codes
    where code_hash = encode(extensions.digest(upper(btrim(p_code)), 'sha256'), 'hex') and expires_at >= now()
    returning user_id into v_user;
  if v_user is null then
    return false;
  end if;
  insert into public.semasa_telegram_link (id, telegram_user_id, chat_id, username, user_id, linked_at)
    values (1, p_telegram_user_id, p_chat_id, left(p_username, 64), v_user, now())
    on conflict (id) do update set telegram_user_id = excluded.telegram_user_id, chat_id = excluded.chat_id,
      username = excluded.username, user_id = excluded.user_id, linked_at = now();
  return true;
end $$;
revoke execute on function public.semasa_telegram_claim(text, bigint, bigint, text) from public, anon, authenticated;

-- 5 · approve / reject from Telegram, through the page's own gate (service role only) --------------------------------------
drop function if exists public.semasa_telegram_decide(uuid, timestamptz, text, bigint);
create or replace function public.semasa_telegram_decide(p_post uuid, p_version timestamptz, p_action text,
                                                         p_telegram_user_id bigint, p_flags jsonb default '[]'::jsonb,
                                                         p_hard_flags int default 0) returns text
language plpgsql security definer set search_path = public as $$
declare
  l public.semasa_telegram_link;
  p record;
begin
  select * into l from public.semasa_telegram_link where id = 1;
  if l.telegram_user_id is null or l.telegram_user_id <> p_telegram_user_id then
    return 'not_linked';
  end if;
  if p_action not in ('approve', 'reject') then
    return 'bad_action';
  end if;
  select id, status, updated_at into p from public.semasa_posts where id = p_post for update;
  if not found then
    return 'gone';
  end if;
  if p.status <> 'draft' then
    return 'status:' || p.status;
  end if;
  if p_version is null or date_trunc('milliseconds', p.updated_at) <> date_trunc('milliseconds', p_version) then
    return 'changed';
  end if;
  -- act as Wan's own login for this transaction only: the gates (semasa_posts_gate, _v3) then treat this exactly as his click
  perform set_config('request.jwt.claims', jsonb_build_object('sub', l.user_id, 'role', 'authenticated')::text, true);
  -- the worker's fresh compliance scan (the same rules the page and the publisher read) is saved with the decision, so a
  -- stale count from when the draft was written neither blocks a clean post nor lets a flagged one through: an approved
  -- post must have hard_flags = 0 (semasa_posts_approve_clean)
  if p_action = 'approve' then
    update public.semasa_posts set status = 'approved', flags = coalesce(p_flags, '[]'::jsonb), hard_flags = coalesce(p_hard_flags, 0)
      where id = p_post;
  else
    update public.semasa_posts set status = 'rejected' where id = p_post;
  end if;
  perform set_config('request.jwt.claims', '', true);
  return 'ok';
end $$;
revoke execute on function public.semasa_telegram_decide(uuid, timestamptz, text, bigint, jsonb, int) from public, anon, authenticated;

-- 6 · wake the worker for Wan's messages and taps; a scheduled run is the net for a dispatch GitHub dropped -------------
create or replace function public.semasa_notify_telegram() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; Telegram messages are read on the scheduled run only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'telegram', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_telegram() from public, anon, authenticated;

drop trigger if exists semasa_telegram_inbox_notify on public.semasa_telegram_inbox;
create trigger semasa_telegram_inbox_notify after insert on public.semasa_telegram_inbox
  for each row when (new.kind in ('private', 'callback') and new.status = 'new') execute function public.semasa_notify_telegram();

notify pgrst, 'reload schema';
