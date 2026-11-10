-- 076 · Pull a scheduled post back to draft so it can be edited (Wan, 10 Nov 2026: "make sure aku boleh ubah post untuk
-- ws.regulab atau linkedin").
--
-- Why a request and not an edit: once the publisher has handed a post to Zernio (or Buffer), that service holds its words, its
-- pictures and its slot, so the page refuses to edit it (072). The only way to change what is scheduled is to take it out of the
-- queue first. The browser cannot do that (the keys live in GitHub), so it asks: it inserts a row here, the database wakes
-- the worker (repository_dispatch 'post_pull_back', the same Vault token 043 uses), and backend/semasa/pullback.py removes the post
-- from Zernio and puts it back to DRAFT with its date and slot kept. It then has to be approved again: the approval gate is
-- untouched, and an edited post is never sent on the strength of an approval for different words.
--
-- Refused, with the reason written on the row, when any channel has already published (nothing can unpublish a sent post) or
-- when a channel is held by Buffer (delete it in Buffer first). The post stays scheduled as it was.
--
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, one trigger function. Run once; re-running changes nothing.

create table if not exists public.semasa_post_pullbacks (
  id           uuid primary key default gen_random_uuid(),
  post_id      uuid not null references public.semasa_posts(id) on delete cascade,
  requested_by uuid default auth.uid(),
  requested_at timestamptz not null default now(),
  state        text not null default 'pending' check (state in ('pending', 'done', 'refused')),
  note         text not null default '',
  done_at      timestamptz
);
create unique index if not exists semasa_post_pullbacks_one_pending on public.semasa_post_pullbacks (post_id) where state = 'pending';
create index if not exists semasa_post_pullbacks_post on public.semasa_post_pullbacks (post_id, requested_at desc);

alter table public.semasa_post_pullbacks enable row level security;
drop policy if exists "semasa pullbacks: uploaders read" on public.semasa_post_pullbacks;
create policy "semasa pullbacks: uploaders read" on public.semasa_post_pullbacks
  for select to authenticated using (public.semasa_is_uploader());
drop policy if exists "semasa pullbacks: uploaders ask" on public.semasa_post_pullbacks;
create policy "semasa pullbacks: uploaders ask" on public.semasa_post_pullbacks
  for insert to authenticated with check (public.semasa_is_uploader() and state = 'pending');
revoke all on public.semasa_post_pullbacks from anon;
grant select, insert on public.semasa_post_pullbacks to authenticated;

create or replace function public.semasa_notify_post_pull_back() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; the pull-back worker runs on its schedule only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'post_pull_back', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
drop trigger if exists semasa_post_pullbacks_notify on public.semasa_post_pullbacks;
create trigger semasa_post_pullbacks_notify after insert on public.semasa_post_pullbacks
  for each row execute function public.semasa_notify_post_pull_back();

-- Check (should print 1 | 1 | 1):
select (select count(*) from information_schema.tables where table_name = 'semasa_post_pullbacks') as tbl,
       (select count(*) from pg_proc where proname = 'semasa_notify_post_pull_back') as fn,
       (select count(*) from pg_trigger where tgname = 'semasa_post_pullbacks_notify') as trg;
