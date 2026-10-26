-- 052 · Anti slop in levels (Wan, 26 Oct 2026: "can buat berperingkat so we know if anti slop better or not").
--
-- settings.antislop.level is off | clean | full (default full): off writes and edits nothing for slop (the control), clean makes the
-- machine edits only, full also hands the rules to every writer. The worker scores every post and film it writes, before and after its
-- own edits, and keeps one row per output here, so Tetapan can show the three levels side by side on real output.
-- Safe to re-run. Run it BEFORE the worker that writes the log is deployed (without it the worker simply keeps no score).

insert into public.semasa_settings (key, value) values ('antislop', jsonb_build_object('level', 'full'))
  on conflict (key) do nothing;

create table if not exists public.semasa_antislop_log (
  id         bigint generated always as identity primary key,
  at         timestamptz not null default now(),
  kind       text        not null check (kind in ('post', 'film')),
  ref        text        not null default '',
  level      text        not null check (level in ('off', 'clean', 'full')),
  chars      int         not null default 0,
  raw_hits   int         not null default 0,   -- slop in what the writer produced (edits clean() would make + tells)
  final_hits int         not null default 0    -- slop left after the machine edits (the tells that need a person)
);
create index if not exists semasa_antislop_log_at_idx on public.semasa_antislop_log (at desc);

alter table public.semasa_antislop_log enable row level security;
drop policy if exists "semasa antislop log: uploaders read" on public.semasa_antislop_log;
create policy "semasa antislop log: uploaders read" on public.semasa_antislop_log
  for select to authenticated using (public.semasa_is_uploader());
-- no insert policy: only the worker (service role) writes it
