-- 093 · The Redraw buttons (Wan, 24 Nov 2026: "how many need to redraw, and add redraw in semasa and telegram button").
--
-- A ws.regulab carousel (or film) that is draft, approved or scheduled can be drawn again IN PLACE: its words, slot and approval
-- stay exactly as they are, the Zernio copy is taken out and the publisher queues it again with the new pictures
-- (backend/semasa/rerender.py). The browser and the bot cannot do that (the picture makers and the sender keys live in GitHub),
-- so they ask: they insert a row here, the database wakes the worker (repository_dispatch 'post_redraw', the same Vault token
-- 043 and 076 use), and rerender.yml does it. The hourly schedule in that workflow is the net for a dispatch GitHub dropped.
--
-- Nothing here approves, schedules or publishes: the approval gate is untouched. Refused, with the reason on the row, when the
-- post is gone, is not ws.regulab, was already sent, is due within two hours or has no carousel.
--
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, one trigger function. Run once; re-running changes nothing.

create table if not exists public.semasa_post_redraws (
  id           uuid primary key default gen_random_uuid(),
  post_id      uuid not null references public.semasa_posts(id) on delete cascade,
  requested_by uuid default auth.uid(),
  requested_at timestamptz not null default now(),
  state        text not null default 'pending' check (state in ('pending', 'done', 'refused')),
  note         text not null default '',
  done_at      timestamptz
);
create unique index if not exists semasa_post_redraws_one_pending on public.semasa_post_redraws (post_id) where state = 'pending';
create index if not exists semasa_post_redraws_post on public.semasa_post_redraws (post_id, requested_at desc);

alter table public.semasa_post_redraws enable row level security;
drop policy if exists "semasa redraws: uploaders read" on public.semasa_post_redraws;
create policy "semasa redraws: uploaders read" on public.semasa_post_redraws
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa redraws: uploaders ask" on public.semasa_post_redraws;
create policy "semasa redraws: uploaders ask" on public.semasa_post_redraws
  for insert to authenticated with check (public.semasa_is_uploader() and state = 'pending');
revoke all on public.semasa_post_redraws from anon;
grant select, insert on public.semasa_post_redraws to authenticated;

create or replace function public.semasa_notify_post_redraw() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the redraw worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'post_redraw', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_post_redraws_notify on public.semasa_post_redraws;
create trigger semasa_post_redraws_notify after insert on public.semasa_post_redraws
  for each row execute function public.semasa_notify_post_redraw();

-- Check (should print 1 | 1 | 1):
select (select count(*) from information_schema.tables where table_name = 'semasa_post_redraws') as tbl,
       (select count(*) from pg_proc where proname = 'semasa_notify_post_redraw') as fn,
       (select count(*) from pg_trigger where tgname = 'semasa_post_redraws_notify') as trg;
