-- 034 · Prestasi: what each published post did on its channel (Wan, 9 Oct 2026: "add feature that can track post same as
-- attached" — Threads' own analytics: reach, average views, engagement, replies, the peak post, the best publishing window
-- and a day × 3-hour heatmap).
--
-- One table, one row per channel-post. The worker (backend/semasa/metrics.py, .github/workflows/metrics.yml, once a day
-- after Buffer refreshes its figures) reads every SENT post on the ws.regulab Buffer channels (Facebook, Instagram, Threads)
-- with Buffer's per-post metrics and upserts it here, joined to the Semasa post whose `published.<channel>.id` names it. The
-- page (web/src/pages/PrestasiTab.jsx, lib/analytics.js) computes everything from these rows in Malaysia time; it writes
-- nothing. LinkedIn has no row: the Composio connection holds w_member_social only, so LinkedIn's figures cannot be read.
--
-- SAFE IN A SHARED PROJECT (KPI): one semasa_ table, uploader-only read, the worker writes with the service role. Run
-- once; re-running changes nothing.

create table if not exists public.semasa_post_metrics (
  id            uuid primary key default gen_random_uuid(),
  source        text        not null default 'buffer',               -- where the figures came from
  external_id   text        not null,                                -- Buffer's post id (unique per source)
  channel       text        not null,                                -- facebook | instagram | threads | linkedin
  channel_id    text        not null default '',
  post_id       uuid,                                                -- the Semasa post, re-linked on every run (no FK: a removed post simply unlinks)
  sent_at       timestamptz,                                         -- when the network published it (UTC)
  url           text        not null default '',
  text_head     text        not null default '',                     -- the first 200 characters, so the page can name it
  -- the figures, normalised: a network that has no such figure leaves null
  views         int,
  reach         int,
  impressions   int,
  reactions     int,
  comments      int,
  shares        int,
  saves         int,
  reposts       int,
  quotes        int,
  clicks        int,
  follows       int,
  engagement    numeric(6,2),                                        -- the network's own engagement rate, percent
  metrics       jsonb       not null default '[]'::jsonb,            -- the raw list, for the record
  metrics_at    timestamptz,                                         -- when Buffer last refreshed them
  fetched_at    timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  constraint semasa_post_metrics_source_check check (source in ('buffer', 'instagram', 'manual')),
  constraint semasa_post_metrics_unique unique (source, external_id)
);
create index if not exists semasa_post_metrics_sent_idx on public.semasa_post_metrics (sent_at desc);
create index if not exists semasa_post_metrics_post_idx on public.semasa_post_metrics (post_id);
drop trigger if exists semasa_post_metrics_set_updated_at on public.semasa_post_metrics;
create trigger semasa_post_metrics_set_updated_at before update on public.semasa_post_metrics
  for each row execute function public.semasa_set_updated_at();

alter table public.semasa_post_metrics enable row level security;
drop policy if exists "semasa post metrics: uploaders read" on public.semasa_post_metrics;
create policy "semasa post metrics: uploaders read" on public.semasa_post_metrics for select to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_post_metrics from anon;
grant select on public.semasa_post_metrics to authenticated;

-- the log may say 'metrics'; the settings row the worker reads
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing', 'subscription', 'crm', 'receipt', 'metrics', 'repos'));
insert into public.semasa_settings (key, value) values ('metrics', jsonb_build_object(
  'days_back', 120                                   -- how far back the worker re-reads sent posts each run
)) on conflict (key) do nothing;

-- proof: 1 | 1 | 1
select (select count(*) from pg_tables where schemaname = 'public' and tablename = 'semasa_post_metrics') as table_ok,
       (select count(*) from pg_policies where tablename = 'semasa_post_metrics') as policies,
       (select count(*) from public.semasa_settings where key = 'metrics') as settings;
