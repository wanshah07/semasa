# Semasa

**Isu Semasa scraper + AI media lab.** Runs entirely on GitHub (Actions as the backend, Pages as the
front end) and Supabase (Postgres + Storage). No Vercel, no server.

Sibling of ws.regulab Studio (`wanshah07/argus`), never part of it: Studio's sweep reads regulators,
law, PubMed and Reddit; **Semasa reads everything else** — the Malaysian news portals, Google News MY
and Google Trends MY — and adds a reference-in, media-out generation queue.

```
  ┌──────────────┐  every 2 h   ┌────────────────────┐   upsert    ┌──────────────────────┐
  │ news portals │ ───────────▶ │ scraper.py         │ ──────────▶ │ isu_semasa_trends    │
  │ Google News  │  (Actions)   │ RSS · Trends ·     │             │ scrape_runs          │
  │ Google Trends│              │ Chromium · LLM     │             └──────────┬───────────┘
  └──────────────┘              └────────────────────┘                        │ anon read
                                                                              ▼
  ┌──────────────┐  upload      ┌────────────────────┐  insert     ┌──────────────────────┐
  │  Wan (UI on  │ ───────────▶ │ Supabase Storage   │ ──────────▶ │ media_generations    │
  │  GH Pages)   │              │ `semasa-reference` │  pending    │ (pg_net trigger ───────┐
  └──────────────┘              └────────────────────┘             └──────────────────────┘│
        ▲                                                                                  │
        │ realtime status                 ┌────────────────────┐  repository_dispatch      │
        └──────────────────────────────── │ media_generator.py │ ◀─────────────────────────┘
                                          │ Replicate / OpenAI │  (+ 15-min poll)
                                          │ → `semasa-generated`│
                                          └────────────────────┘
```

| Part | Where | Runs |
|---|---|---|
| Schema, RLS, buckets, dispatch trigger | `supabase/001…004.sql` | once, in the SQL editor |
| Scraper | `backend/semasa/scraper.py` | `.github/workflows/scrape.yml`, `17 */2 * * *` |
| Media generator | `backend/semasa/media_generator.py` | `.github/workflows/media.yml`, dispatch + `*/15` |
| Site | `web/` (Vite + React + Tailwind + Framer Motion) | `.github/workflows/pages.yml` on push to `main` |
| Tests | `backend/tests` (33), `web` build | `.github/workflows/ci.yml` |

## Deploy, in order

### 1 · Supabase (a new project, or one you already have)

Semasa is built to **share** a Supabase project with another app: every table, function, bucket,
policy and Vault secret it creates is named for Semasa (`isu_semasa_trends`, `media_generations`,
`scrape_runs`, `semasa_*`, `semasa-*`), so running its SQL cannot replace or open up anything that
belongs to the other app. This was tested by running the files on top of a stand-in app that already
had a `set_updated_at()` function, a private `reference` bucket and its own storage policy — all three
came through untouched.

**Before sharing a project, check one thing about the other app:** Semasa's site publishes that
project's anon key. Open **Advisors → Security Advisor** and confirm there is no *RLS disabled in
public* finding. If there is, anyone holding the anon key can read or write that table, and the fix
belongs to the other app before its key goes on a public page.

1. SQL editor → run `supabase/001_schema.sql`, `002_rls.sql`, `003_storage.sql` in that order. Re-running
   is safe. NOTICE lines about things that "do not exist, skipping" are normal.
2. Authentication → URL Configuration → **add** `https://<owner>.github.io/<repo>/**` to *Redirect URLs*.
   In a shared project, leave *Site URL* and the sign-up setting alone — they belong to the other app.
3. Sign in once on the Semasa site (Makmal media tab), then allow yourself to upload. Being signed in is
   not enough on its own, because the other app's users can sign in too:
   ```sql
   insert into public.semasa_uploaders (user_id, note)
   select id, email from auth.users where email = 'you@example.com';
   ```
4. Optional, for a job to start within seconds instead of on the 15-minute poll: create a fine-grained
   PAT (this repo only, **Contents: read and write**), then
   ```sql
   select vault.create_secret('<the PAT>', 'semasa_github_dispatch_token', 'repository_dispatch for semasa');
   select vault.create_secret('<owner>/<repo>', 'semasa_github_dispatch_repo', 'owner/repo');
   ```
   and run `supabase/004_webhook.sql`.
5. Project Settings → API Keys: copy the **Project URL**, the **anon** (or publishable) key and the
   **service_role** (or secret) key.

**Space.** The free plan's 500 MB database and 1 GB storage are shared with the other app. The scraper
deletes headlines and run rows older than `SCRAPE_KEEP_DAYS` (default 30, roughly 60 MB), and the site
polls only while its tab is visible. Generated videos are the thing that fills storage; delete old jobs
from the gallery when space runs low.

### 2 · GitHub
Settings → Secrets and variables → Actions.

| Secret | Used by |
|---|---|
| `SUPABASE_URL` | both runners |
| `SUPABASE_SERVICE_ROLE_KEY` | both runners (bypasses RLS; never in the browser) |
| `LLM_API_KEY` | scraper summariser — an Anthropic or OpenAI key |
| `REPLICATE_API_TOKEN` | media, when `MEDIA_PROVIDER=replicate` (default) |
| `OPENAI_API_KEY` | media, when `MEDIA_PROVIDER=openai` |

| Variable | Default | Notes |
|---|---|---|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | — | **required** for the site build; the anon key is public by design |
| `LLM_PROVIDER` | `openai` | `openai` = any OpenAI-compatible endpoint; `anthropic` = native Messages API |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | only for another OpenAI-compatible gateway. **Not Mireld:** `api.mireld.my` completes TLS and then never answers GitHub runners (measured on two runs, 19 Sep 2026), so the scraper would wait out every timeout and write rules-only rows |
| `SCRAPE_KEEP_DAYS` | `30` | headlines and run rows older than this are deleted; `0` keeps everything |
| `LLM_MODEL` | `gpt-4o-mini` / `claude-haiku-4-5-20251001` | |
| `MEDIA_PROVIDER` | `replicate` | or `openai` |
| `REPLICATE_IMAGE_MODEL` | `black-forest-labs/flux-kontext-pro` | image → image; input field `input_image` |
| `REPLICATE_VIDEO_MODEL` | `kwaivgi/kling-v2.1` | image → video; input field `start_image` |
| `REPLICATE_IMAGE_INPUT_KEY` / `REPLICATE_VIDEO_INPUT_KEY` | as above | change when you change model — each model names its picture field differently |
| `OPENAI_IMAGE_MODEL` / `OPENAI_VIDEO_MODEL` | `gpt-image-1` / `sora-2` | |

Then: Settings → Pages → Source: **GitHub Actions**. Actions → *Deploy site* → Run workflow. The site
is at `https://<owner>.github.io/<repo>/`.

### 3 · First run
Actions → *Scrape isu semasa* → Run workflow. The job summary prints a per-source table; a source that
answers nothing shows ❌ with the reason, and the run row (`scrape_runs`) carries the same table, which
the site's hero reads. **Exit 2** means the LLM key is set but not answering — rows were still written,
rules-only, and the run is red on purpose so it cannot go unnoticed.

## Custom domain

The site is built with relative asset paths, so the same build serves at
`https://<owner>.github.io/<repo>/` and at a domain of its own. For
`socialmedia.kkmhalalconsultant.com` (DNS on Cloudflare):

1. Cloudflare → DNS → **Add record**: type `CNAME`, name `socialmedia`, target `wanshah07.github.io`,
   proxy status **DNS only** (grey cloud). An orange-cloud proxy stops GitHub issuing the certificate.
2. Repo → Settings → Pages → **Custom domain**: `socialmedia.kkmhalalconsultant.com` → Save. Wait for the
   DNS check to pass, then tick **Enforce HTTPS** once it is offered (the certificate can take up to an hour).
3. Supabase → Authentication → URL Configuration → add `https://socialmedia.kkmhalalconsultant.com/**`
   to Redirect URLs, or magic-link sign-in lands on an error page.

The old `github.io/semasa` address then redirects to the new one. Email on the domain is unaffected:
only the `socialmedia` name is added.

## Behaviour worth knowing

- **A row says which brain summarised it.** `summary_source` is `llm`, `rules` or `none`. A dead LLM
  endpoint never fills the table with verdicts that read like reviewed ones.
- **Existing rows are never overwritten.** Upsert on `url` with `ignore_duplicates`, so a later
  rules-only run cannot replace an LLM summary.
- **Sources were measured, not remembered.** Every feed in `sources.py` answered on 23 Sep 2026 from an
  open-internet caller. The Star's RSS paths, Bernama's, Astro Awani's and The Edge's all 404 and are
  absent; those outlets are read from their front pages in Chromium or arrive through Google News.
- **A generation job records its own failure.** `error` on the row, `attempts` counted, back to
  `pending` until `MEDIA_MAX_ATTEMPTS`, then `error` with a *Cuba lagi* button in the page. A provider
  refusal (bad input, 4xx) is final on the first try — retrying the same request gets the same answer.
- **The runner claims a job conditionally** (`update … where status = 'pending'`), so a dispatch and a
  poll arriving together cannot both take it.
- **Generated files carry a sha256 and byte count** in `meta`, so what is in the bucket can be proved
  against what the provider returned.

## Design system

`web/src/design/tokens.css` is the only place a colour, radius, font or shadow is decided. Tailwind
maps every utility to those variables (`bg-surface`, `text-accent`, `rounded-card`), so a component
never sees a hex code. A theme is one CSS file under `web/src/design/themes/` that overrides the
variables under `[data-theme="…"]`; three ship (`facerinna` — the my.facerinna.com palette: Fraunces +
Inter, `#3FA6EE` on `#FBFDFF`, pill radii, 14px glass — plus `noir` and `regulab`). Add a theme: write
the file, import it in `ThemeProvider.jsx`, add its name to `THEMES`. Nothing else changes. Motion
presets live in `design/motion.js` so the whole app moves with one hand.

Components are one job each (`TrendCard`, `MasonryGrid`, `FilterBar`, `MediaUploader`,
`GenerationGallery`, `AuthPanel`, `ui/*`); data access is in `lib/hooks.js` and never inside a component.

## Local

```bash
# backend
cd backend && python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt && python -m playwright install chromium
ruff check . && pytest
SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… LLM_API_KEY=… python -m semasa.scraper

# web
cd web && cp .env.example .env.local   # fill in
npm install && npm run dev
```
