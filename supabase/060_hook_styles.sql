-- 060 · Hook styles made from screenshots (Wan, 6 Nov 2026: "add style hook bank, I can add screenshot and bot can analyze and
-- create the hook and instruction to replace current instruction when select").
--
-- Wan adds a style on the Tetapan tab: a name and up to 8 screenshots of hooks he likes (uploaded under his own folder in
-- semasa-reference). The database wakes the "Hook styles" workflow (repository_dispatch 'hook_style'), which reads the screenshots
-- with the picture reader and writes the style back: an INSTRUCTION (how a hook of this style is written, which replaces the
-- default guidance while the style is selected) and fill-in-the-blank SHAPES the writer must build every post's first line on
-- (the same requirement as the built-in 25). A style is picked as the default for every post (settings.hook_style) or per idea
-- (the idea's brief.hook_style); "builtin" or no choice means the built-in 25.
--
-- status: new (waiting for the worker) · working · ready · error (the reason is on the row; "Try again" sets it back to new).
-- Safe to re-run.

create table if not exists public.semasa_hook_styles (
  id          uuid primary key default gen_random_uuid(),
  name        text not null default '',
  status      text not null default 'new' check (status in ('new', 'working', 'ready', 'error')),
  images      text[] not null default '{}',          -- paths in semasa-reference, each under the creator's own uid/
  summary     text,
  instruction text,                                  -- replaces the default guidance in the writer's required-hook block
  shapes      jsonb not null default '[]'::jsonb,    -- [{"family": "...", "text": "... ___ ..."}]
  error       text,
  attempts    integer not null default 0,
  created_by  uuid references auth.users (id) on delete set null default auth.uid(),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

alter table public.semasa_hook_styles enable row level security;

drop policy if exists "semasa hook styles: uploaders read" on public.semasa_hook_styles;
create policy "semasa hook styles: uploaders read" on public.semasa_hook_styles
  for select to authenticated using (public.semasa_is_uploader());

drop policy if exists "semasa hook styles: uploaders add" on public.semasa_hook_styles;
create policy "semasa hook styles: uploaders add" on public.semasa_hook_styles
  for insert to authenticated
  with check (public.semasa_is_uploader() and created_by = auth.uid() and status = 'new' and attempts = 0
              and coalesce(array_length(images, 1), 0) between 1 and 8);

-- Wan edits the name, the instruction and the shapes of a ready style, and sets an errored one back to 'new' (Try again).
-- He can never mark a style 'working' himself: only the worker does.
drop policy if exists "semasa hook styles: uploaders edit" on public.semasa_hook_styles;
create policy "semasa hook styles: uploaders edit" on public.semasa_hook_styles
  for update to authenticated
  using (public.semasa_is_uploader())
  with check (public.semasa_is_uploader() and status in ('new', 'ready', 'error'));

drop policy if exists "semasa hook styles: uploaders delete" on public.semasa_hook_styles;
create policy "semasa hook styles: uploaders delete" on public.semasa_hook_styles
  for delete to authenticated using (public.semasa_is_uploader());

-- the default style: the page edits this row (the settings policy lets an uploader update any key but 'publishing')
insert into public.semasa_settings (key, value) values ('hook_style', '{}'::jsonb) on conflict (key) do nothing;

-- a new style (or one set back to 'new') wakes the worker; a daily run is the net for a dispatch GitHub dropped
create or replace function public.semasa_notify_hook_style() returns trigger
language plpgsql security definer set search_path = public, vault, net as $$
declare
  v_token text;
  v_repo  text;
begin
  select decrypted_secret into v_token from vault.decrypted_secrets where name = 'semasa_github_dispatch_token';
  select decrypted_secret into v_repo  from vault.decrypted_secrets where name = 'semasa_github_dispatch_repo';
  if v_token is null or v_repo is null then
    raise warning 'semasa: dispatch token missing from vault; hook styles are read on the daily run only';
    return new;
  end if;
  perform net.http_post(
    url     := 'https://api.github.com/repos/' || v_repo || '/dispatches',
    headers := jsonb_build_object('Authorization', 'Bearer ' || v_token, 'Accept', 'application/vnd.github+json',
                                  'Content-Type', 'application/json', 'User-Agent', 'semasa-supabase-webhook'),
    body    := jsonb_build_object('event_type', 'hook_style', 'client_payload', jsonb_build_object('id', new.id))
  );
  return new;
end $$;
revoke execute on function public.semasa_notify_hook_style() from public, anon, authenticated;

drop trigger if exists semasa_hook_styles_notify on public.semasa_hook_styles;
create trigger semasa_hook_styles_notify after insert or update of status on public.semasa_hook_styles
  for each row when (new.status = 'new') execute function public.semasa_notify_hook_style();

notify pgrst, 'reload schema';
