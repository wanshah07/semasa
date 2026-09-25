# Semasa

**Isu Semasa scraper + AI media lab + the ws.regulab Studio workflow.** Runs entirely on GitHub
(Actions as the backend, Pages as the front end) and Supabase (Postgres + Storage), sharing the **KKM**
project with the KKM website. No Vercel, no server.

Semasa is taking over from ws.regulab Studio (`wanshah07/argus`). Studio stays live, and its Routines stay
the only thing that posts, until Semasa has been proven end to end. That is why **publishing is off**:
see *Replacing Studio* below.

Two flows:

- **Flow A** · headline → *Jadikan idea* → the bot READS the article, WRITES a draft in the ws.regulab or
  LinkedIn voice under Studio's rules, and RECREATES a picture (the article's photo is described and drawn
  afresh, never copied) → Wan approves in the **Post** tab → publisher.
- **Flow B** · a prompt alone, or a prompt plus a reference picture of Wan's own, which the bot READS and
  then RECREATES → image or video. Good prompts are kept in the **prompt library**.

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
| Schema, RLS, buckets, dispatch trigger | `supabase/001…005.sql` | once, in the SQL editor |
| Scraper | `backend/semasa/scraper.py` | `.github/workflows/scrape.yml`, `17 */2 * * *` |
| Idea writer (Flow A) + media generator (both flows) | `backend/semasa/ideas.py`, `media_generator.py` | `.github/workflows/media.yml`, dispatch + `*/15` |
| Publisher (**dry run**) | `backend/semasa/publisher.py` | `.github/workflows/publish.yml`, 06:20 · 11:20 · 19:20 MYT |
| Compliance rules (one copy, read by page AND publisher) | `rules/compliance.json`, `rules/cases.json` | tested by both suites |
| Site | `web/` (Vite + React + Tailwind + Framer Motion) | `.github/workflows/pages.yml` on push to `main` |
| Tests | `backend/tests` (118), `web` (`npm test`: 32 compliance cases) | `.github/workflows/ci.yml` |

## Deploy, in order

### 1 · Supabase: the KKM project

Semasa shares the **KKM** project (the one the KKM website, `wanshah07/KKM3`, uses). Everything it creates
is named for Semasa (`isu_semasa_trends`, `media_generations`, `scrape_runs`, `semasa_*`, `semasa-*`
buckets and Vault secrets). **Tested:** the KKM website's 13 migrations were loaded into a Postgres
first, then Semasa's five files. All 53 KKM policies, KKM's functions, triggers and its `images` bucket
came out byte-identical.

Sign-in is the KKM website's own: the same accounts, email + password or Google. Semasa adds no
sign-up, and its email link cannot create an account. An account still has to be on
`semasa_uploaders` to see anything but the headlines.

0. **Pre-check (read-only, change nothing).** In the KKM project's SQL editor run
   `supabase/000_precheck.sql`. On a project that has never had Semasa it lists **no** `semasa`/`media_generations`/
   `scrape_runs`/`isu_semasa_trends` objects. Anything listed there means stop and send me the output.
   It also prints the database size and storage use, because both are shared with the KKM website.
1. SQL editor → run `001_schema.sql`, `002_rls.sql`, `003_storage.sql`, `005_studio.sql`, in that order.
   Re-running is safe. NOTICE lines about things that "do not exist, skipping" are normal.
2. Authentication → URL Configuration → **add to Redirect URLs** (do not touch *Site URL*: it belongs to the
   KKM website): `https://socialmedia.kkmhalalconsultant.com/**` and `https://wanshah07.github.io/semasa/**`.
   Without these, Google sign-in returns you to the KKM website instead of Semasa.
3. Let yourself in (use the email of your KKM website account):
   ```sql
   insert into public.semasa_uploaders (user_id, note)
   select id, email from auth.users where email = 'info@kkmhalalconsultant.com';
   ```
   `INSERT 0 0` means that email has no account in this project yet: add one under Authentication →
   Users → Add user (it will also appear as an ordinary `user` on the KKM website, with no admin rights).
4. For jobs to start within seconds instead of on the 15-minute poll: create a fine-grained PAT (this repo
   only, **Contents: read and write**), then
   ```sql
   select vault.create_secret('<the PAT>', 'semasa_github_dispatch_token', 'repository_dispatch for semasa');
   select vault.create_secret('wanshah07/semasa', 'semasa_github_dispatch_repo', 'owner/repo');
   ```
   and run `supabase/004_webhook.sql`. (Run 005 again after 004 if you do this later; both are idempotent.)
5. Project Settings → API Keys: copy the **Project URL**, the **anon** (or publishable) key and the
   **service_role** (or secret) key into GitHub (next section), replacing the old project's values.

**Space.** The free plan's 500 MB database and 1 GB storage are shared with the KKM website. The scraper
deletes headlines and run rows older than `SCRAPE_KEEP_DAYS` (default 30, roughly 60 MB), and the site
polls only while its tab is visible. Generated videos are what fills storage: delete old jobs from the
gallery when space runs low.

### 2 · GitHub
Settings → Secrets and variables → Actions.

| Secret | Used by |
|---|---|
| `SUPABASE_URL` | all runners — the **KKM** project's URL |
| `SUPABASE_SERVICE_ROLE_KEY` | all runners (bypasses RLS; never in the browser) |
| `LLM_API_KEY` | scraper summariser, idea writer, the READ step (rootsys key, as now) |
| `REPLICATE_API_TOKEN` | media, when `MEDIA_PROVIDER=replicate` (default) |
| `OPENAI_API_KEY` | media, when `MEDIA_PROVIDER=openai` |

| Variable | Default | Notes |
|---|---|---|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | — | **required** for the site build: the KKM project's URL and anon key (public by design) |
| `LLM_PROVIDER` | `openai` | `openai` = any OpenAI-compatible endpoint; `anthropic` = native Messages API |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | only for another OpenAI-compatible gateway. **Not Mireld:** `api.mireld.my` completes TLS and then never answers GitHub runners (measured on two runs, 19 Sep 2026), so the scraper would wait out every timeout and write rules-only rows |
| `SCRAPE_KEEP_DAYS` | `30` | headlines and run rows older than this are deleted; `0` keeps everything |
| `LLM_MODEL` | `gpt-4o-mini` / `claude-haiku-4-5-20251001` | the writer too; `deepseek-v4.1-flash` on rootsys works |
| `VISION_MODEL` | `LLM_MODEL` | the model that **reads** a reference picture. DeepSeek is text-only, so set this to a rootsys model that sees pictures (the one `kkm-complaints` uses for screenshots). Unset or text-only: jobs say "not read", Flow B still recreates from the picture itself, Flow A draws from the draft's words |
| `REPLICATE_T2I_MODEL` | `black-forest-labs/flux-1.1-pro` | words → image (prompt-only jobs, and Flow A's redraw) |
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
3. Supabase (KKM project) → Authentication → URL Configuration → add `https://socialmedia.kkmhalalconsultant.com/**`
   to Redirect URLs, or Google sign-in lands on the KKM website instead.

The old `github.io/semasa` address then redirects to the new one. Email on the domain is unaffected:
only the `socialmedia` name is added.

## Replacing Studio

**The switch.** `semasa_settings.publishing.enabled` is `false`. The browser cannot change it: the
database's own policy refuses that row. While it is off, `publish.yml` is a **dry run**. For every
approved post in the next 14 days it writes to `semasa_publish_log` exactly what it *would* send:
channel, time, caption and pictures. Each post shows that log. Turning it on today still sends nothing,
because the senders are not ported yet; the log records that instead. **Never turn it on while Studio's
Routines still run.** Two publishers on one Buffer account post everything twice, and argus's rule 1
allows one schedule per job.

**The gate, as in Studio, enforced by the database rather than trusted to the page.**
- Only a person can approve, and only with zero blocking flags.
- `approved_by` and `approved_at` are stamped from the session.
- Editing an approved post's words, source, pictures or time sends it back to draft.
- The page can never write `scheduled`, `posted`, `published` or `errors`.
- The publisher re-runs the same checks before it would send.

| Studio feature | In Semasa |
|---|---|
| Compliance: CTA, website in caption, `[SAHKAN]` (incl. empty), social source, BM-not-Indonesian, limits, hashtags, LinkedIn aggregator + brand mark, fatwa gazette, Instagram needs a picture, off-rota warning, other-language warnings | ✅ same rules, one file, page and publisher agree exactly (tested) |
| One approval gate, two voices, slots, weekly rota, LinkedIn days | ✅ |
| Ideas → drafts | ✅ from headlines (Flow A) |
| Release clock 06:20 · 11:20 · 19:20, 45-minute late grace | ✅ dry run |
| Picture hosting that never expires | ✅ `semasa-generated` is public and permanent |
| Buffer sender (FB · IG · Threads): confirm, tally, queue-full wait, one transient retry | ⏳ phase 2 |
| LinkedIn sender (Composio, text or images) | ⏳ phase 2 |
| Card and carousel artwork (grid / ERA / photo families, logo, grounds, mascots) | ⏳ phase 2 |
| Regulator sweep (NPRA, halal.gov.my, EUR-Lex, PubMed…) as ideas | ⏳ phase 2 (Semasa reads news only today) |
| Moving Studio's store (drafts, media, settings, log) | ⏳ last, then Studio is retired |

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
- **A job whose runner died is not stuck for ever.** A row still `processing` after `MEDIA_STALE_MINUTES`
  (60) goes back to `pending`, its lost attempt counted; an idea left `working` for 30 minutes goes back to `new`.
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
