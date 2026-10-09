-- 035 · Repo tracker + API gateway status (Wan, 9 Oct 2026: "add all repo office environment in 6D in the system so i can
-- track the repos progress and status" and "track status of token from mireld and afiq API including their models").
--
-- Three tables, all written by workers on the GitHub runner (service role) and read by the page (uploaders only):
--   semasa_repos       one row per repository: the six office repositories by default (settings.repos), with the six
--                      dimensions the page draws: code, pull requests, CI, issues, schedules, deploy (backend/semasa/repos.py,
--                      .github/workflows/repos.yml, every 6 hours).
--   semasa_api_status  one row per AI gateway (rootsys = Afiq's, Mireld): reachable, the key accepted, latency, the models
--                      it lists, whether the configured model is among them, balance if the gateway says
--                      (backend/semasa/api_status.py, .github/workflows/api.yml, every 6 hours).
--   semasa_api_usage   one row per AI call the workers make: gateway, model, tokens, time, ok. Written through
--                      llm.set_usage_sink by every runner that asks a writer anything; the page sums it by day.
--
-- SAFE IN A SHARED PROJECT (KPI): semasa_ tables only, uploader-only read, no browser write. Run once; re-running changes nothing.

create table if not exists public.semasa_repos (
  id            uuid primary key default gen_random_uuid(),
  full_name     text        not null unique,                        -- owner/name
  name          text        not null default '',
  description   text        not null default '',
  private       boolean     not null default false,
  default_branch text       not null default 'main',
  html_url      text        not null default '',
  pushed_at     timestamptz,
  last_commit   jsonb       not null default '{}'::jsonb,           -- {sha, message, at, author}
  commits_7d    int         not null default 0,
  commits_30d   int         not null default 0,
  commit_days   jsonb       not null default '[]'::jsonb,           -- [{date, n}] last 14 days, the sparkline
  open_prs      jsonb       not null default '[]'::jsonb,           -- [{number, title, draft, updated_at, url, ci}]
  merged_30d    int         not null default 0,
  open_issues   int         not null default 0,                     -- issues only (GitHub's count includes PRs)
  issues        jsonb       not null default '[]'::jsonb,           -- [{number, title, updated_at, url}] the newest few
  workflows     jsonb       not null default '[]'::jsonb,           -- [{name, path, cron, last: {status, conclusion, at, url}}]
  ci            text        not null default 'none',                -- green | red | running | none
  pages         jsonb       not null default '{}'::jsonb,           -- {url, status, at}
  health        int         not null default 0,                     -- 0..100
  progress      int         not null default 0,                     -- merged ÷ (merged + open) over 30 days, percent
  dims          jsonb       not null default '{}'::jsonb,           -- the six dimensions, each {state, label, detail}
  error         text        not null default '',
  fetched_at    timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
drop trigger if exists semasa_repos_set_updated_at on public.semasa_repos;
create trigger semasa_repos_set_updated_at before update on public.semasa_repos
  for each row execute function public.semasa_set_updated_at();
alter table public.semasa_repos enable row level security;
drop policy if exists "semasa repos: uploaders read" on public.semasa_repos;
create policy "semasa repos: uploaders read" on public.semasa_repos for select to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_repos from anon;
grant select on public.semasa_repos to authenticated;

create table if not exists public.semasa_api_status (
  id            uuid primary key default gen_random_uuid(),
  slug          text        not null unique,                        -- rootsys | mireld | <host>
  name          text        not null default '',
  role          text        not null default '',                    -- primary | backup | chat | reader
  base_url      text        not null default '',
  key_set       boolean     not null default false,
  key_last4     text        not null default '',
  key_ok        boolean,                                            -- null = not asked; false = 401/403
  model         text        not null default '',                    -- the model configured for it
  model_listed  boolean,                                            -- the configured model is in its /models list
  reachable     boolean     not null default false,
  http          int,
  latency_ms    int,
  chat_ok       boolean,                                            -- a 5-token question answered
  chat_ms       int,
  models        jsonb       not null default '[]'::jsonb,
  balance       jsonb       not null default '{}'::jsonb,           -- whatever the gateway's balance endpoint said, or {}
  error         text        not null default '',
  checked_at    timestamptz not null default now(),
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
drop trigger if exists semasa_api_status_set_updated_at on public.semasa_api_status;
create trigger semasa_api_status_set_updated_at before update on public.semasa_api_status
  for each row execute function public.semasa_set_updated_at();
alter table public.semasa_api_status enable row level security;
drop policy if exists "semasa api status: uploaders read" on public.semasa_api_status;
create policy "semasa api status: uploaders read" on public.semasa_api_status for select to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_api_status from anon;
grant select on public.semasa_api_status to authenticated;

create table if not exists public.semasa_api_usage (
  id            uuid primary key default gen_random_uuid(),
  gateway       text        not null,                               -- the slug above
  model         text        not null default '',
  area          text        not null default '',                    -- scrape | media | faq | receipt | chat | probe
  prompt_tokens int         not null default 0,
  completion_tokens int     not null default 0,
  total_tokens  int         not null default 0,
  ms            int         not null default 0,
  ok            boolean     not null default true,
  error         text        not null default '',
  created_at    timestamptz not null default now()
);
create index if not exists semasa_api_usage_at_idx on public.semasa_api_usage (created_at desc);
alter table public.semasa_api_usage enable row level security;
drop policy if exists "semasa api usage: uploaders read" on public.semasa_api_usage;
create policy "semasa api usage: uploaders read" on public.semasa_api_usage for select to authenticated using (public.semasa_is_uploader());
revoke all on public.semasa_api_usage from anon;
grant select on public.semasa_api_usage to authenticated;

-- the log may say 'repos' and 'api'
alter table public.semasa_log drop constraint if exists semasa_log_area_check;
alter table public.semasa_log add constraint semasa_log_area_check
  check (area in ('scrape', 'idea', 'post', 'media', 'faq', 'publish', 'settings', 'system', 'billing', 'subscription', 'crm', 'receipt', 'metrics', 'repos', 'api'));

-- the six office repositories; the page edits the list under Settings (uploaders may edit settings, not insert them)
insert into public.semasa_settings (key, value) values ('repos', jsonb_build_object(
  'list', jsonb_build_array('wanshah07/semasa', 'wanshah07/argus', 'wanshah07/argus-cards', 'wanshah07/kkm-complaints',
                            'wanshah07/kpi-system', 'wanshah07/malaysian-regulatory-affairs'),
  'days', 30
)) on conflict (key) do nothing;
insert into public.semasa_settings (key, value) values ('api_probe', jsonb_build_object(
  'keep_days', 90                                     -- how long usage rows are kept
)) on conflict (key) do nothing;

-- proof: 3 | 3 | 2
select (select count(*) from pg_tables where schemaname = 'public' and tablename in ('semasa_repos', 'semasa_api_status', 'semasa_api_usage')) as tables,
       (select count(*) from pg_policies where tablename in ('semasa_repos', 'semasa_api_status', 'semasa_api_usage')) as policies,
       (select count(*) from public.semasa_settings where key in ('repos', 'api_probe')) as settings;
