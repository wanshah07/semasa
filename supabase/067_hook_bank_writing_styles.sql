-- 067 · Hook bank you can edit, and a writing style bank (Wan, 11 Oct 2026, Phase 4: "hooks bank boleh edit, add, apply" and
-- "writing style bank, asing dan boleh pilih; aku upload link post viral, AI analyse dan terjemah jadi gaya penulisan").
--
-- 1 · Hook sets made by hand. semasa_hook_styles (060) held only styles the bot made from screenshots. A style can now also be
--     made by hand on the Bank hook page (`source = 'manual'`): a name, an instruction and at least 3 fill-in-the-blank shapes,
--     ready at once, no screenshots and no bot. "Salin 25 terbina" is a manual style holding a copy of the built-in 25 to edit.
--     A manual style is never sent to the bot: it can only be 'ready' (the worker only takes 'new').
--
-- 2 · semasa_writing_styles: how a whole caption is written (voice, rhythm, length, structure, language mix), apart from the
--     hook. Wan adds viral posts as links, pasted text and/or screenshots; the database wakes the "Writing styles" workflow
--     (repository_dispatch 'writing_style'), which reads them and writes an INSTRUCTION and a few TRAITS. Or he writes one by hand
--     (`source = 'manual'`, ready at once). The style chosen as the default (settings.writing_style) or on one idea
--     (brief.writing_style) is added to the caption writer's prompt after every rule, the house style and the hook requirement's
--     guardrails, and is told it never lifts one. Nothing a source post said word for word is kept.
--
-- status: new (waiting for the worker) · working · ready · error (the reason is on the row; "Try again" sets it back to new).
-- Safe to re-run.

-- 1 · hook styles: a source column and the manual path ---------------------------------------------------------------------
alter table public.semasa_hook_styles add column if not exists source text not null default 'screenshots';
do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'semasa_hook_styles_source_check') then
    alter table public.semasa_hook_styles add constraint semasa_hook_styles_source_check check (source in ('screenshots', 'manual'));
  end if;
end $$;

drop policy if exists "semasa hook styles: uploaders add" on public.semasa_hook_styles;
create policy "semasa hook styles: uploaders add" on public.semasa_hook_styles
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid() and attempts = 0 and (
    (source = 'screenshots' and status = 'new' and coalesce(array_length(images, 1), 0) between 1 and 8)
    or (source = 'manual' and status = 'ready' and coalesce(array_length(images, 1), 0) = 0
        and jsonb_typeof(shapes) = 'array' and jsonb_array_length(shapes) between 3 and 30)));

-- a manual style stays ready (setting it back to 'new' would send the bot a style with nothing to read)
drop policy if exists "semasa hook styles: uploaders edit" on public.semasa_hook_styles;
create policy "semasa hook styles: uploaders edit" on public.semasa_hook_styles
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('new', 'ready', 'error') and (source = 'screenshots' or status = 'ready'));

-- 2 · writing styles -------------------------------------------------------------------------------------------------------
create table if not exists public.semasa_writing_styles (
  id          uuid primary key default gen_random_uuid(),
  name        text not null default '',
  source      text not null default 'analyse' check (source in ('analyse', 'manual')),
  status      text not null default 'new' check (status in ('new', 'working', 'ready', 'error')),
  links       text[] not null default '{}',          -- viral posts, one link each (http/https)
  sample      text not null default '',              -- pasted post text, for a site the worker cannot read
  images      text[] not null default '{}',          -- screenshots in semasa-reference, each under the creator's own uid/
  summary     text,
  instruction text,                                  -- added to the caption writer's prompt while the style is chosen
  traits      jsonb not null default '[]'::jsonb,    -- ["short line", ...]: what marks the style
  error       text,
  attempts    integer not null default 0,
  created_by  uuid references auth.users (id) on delete set null default auth.uid(),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now(),
  constraint semasa_writing_styles_sizes check (coalesce(array_length(links, 1), 0) <= 8 and coalesce(array_length(images, 1), 0) <= 8
                                               and length(sample) <= 12000 and length(coalesce(instruction, '')) <= 2000)
);

alter table public.semasa_writing_styles enable row level security;

drop policy if exists "semasa writing styles: uploaders read" on public.semasa_writing_styles;
create policy "semasa writing styles: uploaders read" on public.semasa_writing_styles
  for select to authenticated using (public.semasa_is_uploader());

drop policy if exists "semasa writing styles: uploaders add" on public.semasa_writing_styles;
create policy "semasa writing styles: uploaders add" on public.semasa_writing_styles
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid() and attempts = 0 and (
    (source = 'analyse' and status = 'new'
       and (coalesce(array_length(links, 1), 0) + coalesce(array_length(images, 1), 0) > 0 or length(btrim(sample)) >= 80))
    or (source = 'manual' and status = 'ready' and length(btrim(coalesce(instruction, ''))) >= 20)));

-- Wan edits the name, the instruction and the traits of a ready style, and sets an errored one back to 'new' (Try again). Only
-- the worker marks a style 'working'; a manual style stays ready.
drop policy if exists "semasa writing styles: uploaders edit" on public.semasa_writing_styles;
create policy "semasa writing styles: uploaders edit" on public.semasa_writing_styles
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('new', 'ready', 'error') and (source = 'analyse' or status = 'ready'));

drop policy if exists "semasa writing styles: uploaders delete" on public.semasa_writing_styles;
create policy "semasa writing styles: uploaders delete" on public.semasa_writing_styles
  for delete to authenticated using (public.semasa_is_uploader());

revoke all on public.semasa_writing_styles from anon;
grant select, insert, update, delete on public.semasa_writing_styles to authenticated;

drop trigger if exists semasa_writing_styles_set_updated_at on public.semasa_writing_styles;
create trigger semasa_writing_styles_set_updated_at before update on public.semasa_writing_styles
  for each row execute function public.semasa_set_updated_at();

-- the default style: the page edits this row ({"id": ""} = no writing style, the house style alone)
insert into public.semasa_settings (key, value) values ('writing_style', '{}'::jsonb) on conflict (key) do nothing;

-- a new style (or one set back to 'new') wakes the worker; a daily run is the net for a dispatch GitHub dropped
create or replace function public.semasa_notify_writing_style() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; writing styles are read on the daily run only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'writing_style', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_writing_style() from public, anon, authenticated;

drop trigger if exists semasa_writing_styles_notify on public.semasa_writing_styles;
create trigger semasa_writing_styles_notify after insert or update of status on public.semasa_writing_styles
  for each row when (new.status = 'new') execute function public.semasa_notify_writing_style();

notify pgrst, 'reload schema';
