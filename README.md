# Semasa

**Isu Semasa scraper + AI media lab + the ws.regulab Studio workflow.** Runs entirely on GitHub
(Actions as the backend, Pages as the front end) and Supabase (Postgres + Storage), sharing the **KPI**
project with the KPI system (`wanshah07/kpi-system`). No Vercel, no server.

Semasa is taking over from ws.regulab Studio (`wanshah07/argus`). Studio stays live, and its Routines stay
the only thing that posts, until Semasa has been proven end to end. That is why **publishing is off**:
see *Replacing Studio* below.

Two flows:

- **Flow A** · headline → *Jadikan idea* → the bot READS the article, WRITES a draft in the ws.regulab or
  LinkedIn voice under Studio's rules, and RECREATES a picture (the article's photo is described and drawn
  afresh, never copied) → Wan approves in the **Post** tab → publisher.
- **Flow B** · a prompt alone, or a prompt plus a reference picture of Wan's own, which the bot READS and
  then RECREATES → image or video. Good prompts are kept in the **prompt library**.
- **FAQ** · a question (and its answer, if there is one) is pasted by hand, made from a headline
  (**Jadikan FAQ**), or collected by the scraper as a candidate (JAKIM *Isu-Isu Tular Halal*, Reddit
  r/malaysia). The AI rewrites it in BM and English, anonymises it and picks a category. It appears in the
  **FAQ** tab (search, categories, subcategories), is mirrored to the **Semasa FAQ** Google Sheet, and each
  category exports as **PDF, poster or Excel**.

```
  ┌──────────────┐  every 8 h   ┌────────────────────┐   upsert    ┌──────────────────────┐
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
                                          │ Cloudflare/Replic. │  (+ 15-min poll)
                                          │ / OpenAI           │
                                          │ → `semasa-generated`│
                                          └────────────────────┘
```

| Part | Where | Runs |
|---|---|---|
| Schema, RLS, buckets, dispatch trigger, the log, the clock, the archive | `supabase/001…010.sql` | once, in the SQL editor |
| Scraper | `backend/semasa/scraper.py` | `.github/workflows/scrape.yml`, `17 7,15,23 * * *` (07:17 · 15:17 · 23:17 MYT) |
| Idea writer (Flow A) + media generator (both flows) + slide renderer | `backend/semasa/ideas.py`, `media_generator.py`, `slides.py` | `.github/workflows/media.yml`, dispatch + `*/15` |
| Publisher (**dry run**) | `backend/semasa/publisher.py` | `.github/workflows/publish.yml`, 06:20 · 11:20 · 19:20 MYT |
| Compliance rules (one copy, read by page AND publisher) | `rules/compliance.json`, `rules/cases.json` | tested by both suites |
| Site | `web/` (Vite + React + Tailwind + Framer Motion) | `.github/workflows/pages.yml` on push to `main` |
| FAQ writer + Sheet mirror | `backend/semasa/faq.py` (worker), `faq_sources.py` (candidates, run by the scraper), `apps-script/Code.gs` (the Sheet) | the media worker and the scrape |
| Tests | `backend/tests` (181), `web` (`npm test`: 51 compliance cases) | `.github/workflows/ci.yml` |

## Deploy, in order

### 1 · Supabase: the KPI project

Semasa shares the **KPI** project (`mwaocnbgvbkhovktgods`, the one `wanshah07/kpi-system` uses), and
files 001–004 are **already installed there**: the live site and the scrape runs have used it since
24 Sep. So the GitHub secrets and variables already point at the right project, and only the new files
need running. Everything Semasa creates is named for Semasa (`isu_semasa_trends`, `media_generations`,
`scrape_runs`, `semasa_*`, `semasa-*` buckets and Vault secrets). KPI's own objects are `tasks`,
`settings` and the `attachments` bucket, and nothing of Semasa's shares a name with them.

**Tested:** KPI's `schema.sql` was loaded into a Postgres with a task and a settings value in it, then all
five Semasa files. KPI's tables, their row-level security, columns, data and bucket came out
byte-identical, and the public anon key the Semasa site publishes still reads **0** KPI tasks. KPI keeps
its security by having RLS on with no policies and talking to Supabase with the service key from its
server only; Semasa changes none of that.

**Sign-in.** The KPI app never uses Supabase sign-in (it sits behind its own password), so every
account in that project is Semasa's. You create it by hand. Checked on the live project: only the
**email** provider is enabled, so Semasa offers email + password (and an email link that cannot create
an account), and no Google button.

0. **Pre-check (read-only, change nothing).** In the KPI project's SQL editor run
   `supabase/000_precheck.sql`. Expected today: the 001–004 objects (`isu_semasa_trends`,
   `media_generations`, `scrape_runs`, `semasa_uploaders`, three `semasa_*` functions, two buckets,
   four storage policies) and **no** `semasa_settings`, `semasa_ideas`, `semasa_prompts`, `semasa_posts`.
   Anything else listed means stop and send me the output. It also prints the database size and
   storage use, because both are shared with the KPI system.
1. SQL editor → run `002_rls.sql`, `003_storage.sql`, then `005_studio.sql`. 002 and 003 changed (the
   media gallery is no longer public; the generated bucket's limit is now 50 MB). Re-running is safe.
   NOTICE lines about things that "do not exist, skipping" are normal. If you set up the Vault secrets
   in step 4 later, run `004_webhook.sql` then `005_studio.sql` again.
   **Then `006_slides.sql`** (carousel slides, 25 Sep 2026). A database that ran 005 before that date
   needs it once; re-running is safe, and a fresh install gets the same from 005. It adds two columns
   and one allowed job mode, and makes the gate send an approved post back to draft when its slides
   change. Until it has run, the Post tab says so and nothing about slides is ever written.
   **Then `007_faq.sql`** (FAQ and the Indonesian-word tabung, 25 Sep 2026). It creates `semasa_faqs`
   and two settings rows (`faq` for the categories, `bahasa` for the tabung). It is private to listed
   uploaders like ideas and posts, and safe to run again.
   **Then `008_log.sql`** (the log). It creates `semasa_log` and one AFTER trigger on each Semasa table.
   A trigger that fails only raises a warning and never blocks the change it was describing (tested by
   dropping the log table mid-write).
   **Then `009_clock.sql`** (the clock, see *The clock* below). It schedules three `semasa_*` jobs in
   Supabase's own scheduler (pg_cron) and needs the Vault token from step 4. Without the token each job
   writes one warning to the Log every 6 hours and does nothing else.
   **Then `010_archive.sql`** (a published post is never written again, and is archived 24 hours after it went
   out: see *Published posts* below). Safe to run again.
   **Then `011_video.sql`** (the Video tab, 26 Sep 2026: a long video becomes short clips and draft posts, see
   *Video* below). It creates `semasa_videos`, allows a `clip` media job, and adds videos to 009's clock. Safe to
   run again, and safe in the shared project (only `semasa_*` objects).
   **Then `012_watch.sql`** (the Regulatory and Latest publication segments, 26 Sep 2026, see *Regulatory and
   Latest publication* below). It creates `semasa_watch`, the `watch` settings row and the trigger behind *Sapu
   sekarang*. The page may only hide a row. Safe to run again, and safe in the shared project.
   007 and 008 were changed on 25 Sep 2026 after they were first handed over (bot categories, and a
   settings row the log must never record). Both are safe to run again: run 007, 008 and 009 in that
   order even if you ran an earlier 007 or 008.
2. Authentication → **Users → Add user**: your email and a password, *Auto confirm* ticked.
   Then Authentication → **Sign In / Providers → turn OFF "Allow new users to sign up"**. KPI does not
   use Supabase sign-in, so nothing of KPI's depends on it, and it stops strangers making accounts with
   the public key. (They could not do anything with one, since writes need `semasa_uploaders`, but
   there is no reason to allow it.)
3. Let yourself in:
   ```sql
   insert into public.semasa_uploaders (user_id, note)
   select id, email from auth.users where email = 'info@kkmhalalconsultant.com';
   ```
   `INSERT 0 0` means step 2's user was made with a different email.
4. **Needed** (the clock and the instant start both use it). GitHub's schedules are best effort: on
   24–25 Sep the 15-minute media poll ran 4 times in 6 hours, the scrape went more than 5 hours without
   a run and the 11:20 MYT publisher slot never fired, so an idea waited on "Menunggu bot". Create a
   fine-grained PAT (this repo only, **Contents: read and write**), then
   ```sql
   select vault.create_secret('<the PAT>', 'semasa_github_dispatch_token', 'repository_dispatch for semasa');
   select vault.create_secret('wanshah07/semasa', 'semasa_github_dispatch_repo', 'owner/repo');
   ```
   and run `supabase/004_webhook.sql`, then `005_studio.sql` again, then `009_clock.sql`.
5. Authentication → URL Configuration → add to *Redirect URLs*: `https://socialmedia.kkmhalalconsultant.com/**`
   and `https://wanshah07.github.io/semasa/**`, so an email link lands back on Semasa.

**Space.** The free plan's 500 MB database and 1 GB storage are shared with the KPI system. The scraper
deletes headlines and run rows older than `SCRAPE_KEEP_DAYS` (default 30, roughly 60 MB), drops a headline
nobody made an idea of once it is `SCRAPE_PICK_HOURS` (48) old, and the site
polls only while its tab is visible. Generated videos are what fills storage: delete old jobs from the
gallery when space runs low.

### 2 · GitHub
Settings → Secrets and variables → Actions.

| Secret | Used by |
|---|---|
| `SUPABASE_URL` | all runners — the **KPI** project's URL (already set) |
| `SUPABASE_SERVICE_ROLE_KEY` | all runners (bypasses RLS; never in the browser) |
| `LLM_API_KEY` | scraper summariser, idea writer, the READ step (rootsys key, as now) |
| `REPLICATE_API_TOKEN` | media, when `MEDIA_PROVIDER=replicate` (default) |
| `OPENAI_API_KEY` | media, when `MEDIA_PROVIDER=openai` |
| `LLM_FALLBACK_API_KEY` | optional: the backup writer's key (Mireld). Asked only when rootsys gives no usable answer; needs the variable `LLM_FALLBACK_MODEL` too |
| `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN` | media, when `MEDIA_PROVIDER=cloudflare`: **free pictures** (see *Free pictures: Cloudflare*). With both set and no `REPLICATE_API_TOKEN`, Cloudflare is the default and no Variable is needed |
| `UNSPLASH_ACCESS_KEY` | media: the **Unsplash** picture search (see *Unsplash*). A free app at unsplash.com/developers; the *Access Key*, never the Secret key. Unset: an Unsplash search says where the key goes and stops |
| `YTDLP_COOKIES` | optional, media: only if YouTube keeps refusing GitHub's machine for the Video tab. The text of a `cookies.txt` export from a browser signed in to YouTube. It acts as that account, so use a spare one, never your main account |
| `TELEGRAM_BOT_TOKEN` | optional: the FAQ bot in your Telegram group(s) (see *FAQ from Telegram*). Unset: Telegram is simply not read |
| `SEMASA_SHEET_URL`, `SEMASA_SHEET_TOKEN` | the Semasa Google Sheet (FAQ tabs and the Log tab): the Apps Script `/exec` URL and the `API_TOKEN` its `setup` prints (see *The Semasa Sheet* below). Unset: everything works, and the Sheet is simply not written. `FAQ_SHEET_URL` / `FAQ_SHEET_TOKEN`, their first names, are still read if set |

| Variable | Default | Notes |
|---|---|---|
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` | — | **required** for the site build: the KPI project's URL and anon key (already set; the anon key is public by design) |
| `LLM_PROVIDER` | `openai` | `openai` = any OpenAI-compatible endpoint; `anthropic` = native Messages API |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | only for another OpenAI-compatible gateway: `https://rootsys.cloud/v1` today. **Mireld now answers GitHub runners.** On 19 Sep 2026 `api.mireld.my` went silent after TLS, three ways. Re-probed on 25 Sep 2026 (`kkm-complaints` LLM probe, run 36086853058), it answered in 0.8 s with `401 Invalid API key` for a key that is not Mireld's. That proves it is reachable, not that chat works. Switch only with a Mireld key and a green scrape run: `LLM_BASE_URL=https://api.mireld.my/v1`, `LLM_MODEL` = a Mireld model, and `LLM_API_KEY` = the Mireld key |
| `SCRAPE_KEEP_DAYS` | `30` | headlines and run rows older than this are deleted; `0` keeps everything |
| `SCRAPE_PICK_HOURS` | `48` | a headline nobody makes an idea of leaves the page at this age. The row is deleted once the feed's own date puts it past `SCRAPE_MAX_AGE_HOURS` (48), so it cannot come back as "new". An undated headline stays hidden until `SCRAPE_KEEP_DAYS`, because its row is the only thing stopping it from coming back. `0` never drops. The page's `PICK_HOURS` must match |
| `LLM_MODEL` | `gpt-4o-mini` / `claude-haiku-4-5-20251001` | the writer too; `deepseek-v4.1-flash` on rootsys works |
| `LLM_FALLBACK_MODEL` | — | the backup writer's model (a Mireld model name); with `LLM_FALLBACK_API_KEY` it switches the backup on |
| `LLM_FALLBACK_BASE_URL` | `https://api.mireld.my/v1` | only if the backup lives elsewhere; its host must be in `LLM_FALLBACK_ALLOWED_HOSTS` |
| `VISION_MODEL` | `LLM_MODEL` | the model that **reads** a reference picture: set it to `deepseek-v4.1-flash`, which rootsys lists with the VISION tag. (An earlier version of this line said DeepSeek was text-only; that was wrong.) rootsys can only **read** pictures. Its image, video and embedding endpoints answer 404, so generation is Cloudflare's, Replicate's or OpenAI's job. If no model can see, jobs say "not read": Flow B still recreates from the picture itself, and Flow A draws from the draft's words |
| `REPLICATE_T2I_MODEL` | `black-forest-labs/flux-1.1-pro` | words → image (prompt-only jobs, and Flow A's redraw) |
| `MEDIA_PROVIDER` | `replicate` (`cloudflare` when only its secrets are set) | or `openai`, or `cloudflare` (pictures only) |
| `CLOUDFLARE_T2I_MODEL` | `@cf/black-forest-labs/flux-1-schnell` | words → picture on Cloudflare |
| `CLOUDFLARE_EDIT_MODEL` | `@cf/black-forest-labs/flux-2-klein-4b` | your reference → picture on Cloudflare (a FLUX.2 model: only those take a picture) |
| `CLOUDFLARE_IMAGE_SIZE` | `1024` | width and height for the FLUX.2 models |
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

### 4 · The Semasa Sheet

One Google Sheet for Semasa holds the FAQ and the log. It is the sheet made for the FAQ, in the
info@kkmhalalconsultant.com Drive (rename it from *Semasa FAQ* to **Semasa**; the name does not matter to
the script):
https://docs.google.com/spreadsheets/d/1HKmiGmzIpR1D6oDkmwVeJXr-pIK0M-gy5IjO0MMisMs/edit
Setting it up is the same routine as the KKM complaint sheet:

1. Open it, then **Extensions → Apps Script**. Paste `apps-script/Code.gs` over `Code.gs`. Then Project
   Settings → tick *Show "appsscript.json"*, and paste `apps-script/appsscript.json`.
2. Run **`setup`** once and allow access. The log prints `API_TOKEN=…`.
3. **Deploy → New deployment → Web app**: Execute as *Me*, Who has access *Anyone*. Copy the `/exec` URL.
   "Anyone" is safe: every call must carry the token, and one without it is refused.
4. GitHub secrets: `SEMASA_SHEET_URL` = the `/exec` URL, `SEMASA_SHEET_TOKEN` = the token.

Changing `Code.gs` later: paste it again, then **Deploy → Manage deployments → edit → Version: New
version**. The `/exec` URL stays the same. A deployment left on its old version keeps running the old code
and answers `Unknown action append_log`, which shows in the Log as "Log gagal disalin ke Google Sheet".

The database is the source of truth, and the Sheet is a copy of it:
- **FAQ.** Every worker run that finds the list changed **replaces** the FAQ tabs: *Semua FAQ* plus one
  tab per category, each with a filter row. An edit or delete made in Semasa reaches the Sheet, and **an
  edit made in the Sheet is overwritten**. Edit in Semasa.
- **Log.** Every run (scrape, worker, publisher) **appends** the new log rows to the *Log* tab, in
  Malaysia time, with errors in red and warnings in amber. Each row carries its log id and the script
  remembers the highest one written, so a row sent twice is written once. The database keeps 90 days and
  the tab keeps the newest 50,000 rows, so the Sheet is the long record.

A cell starting with `=`, `+`, `-` or `@` is written as text, so pasted text can never run as a formula.
A category can never take the *Log* or *Semua FAQ* tab: one named that gets "(FAQ)" added.

## Custom domain

The site is built with relative asset paths, so the same build serves at
`https://<owner>.github.io/<repo>/` and at a domain of its own. For
`socialmedia.kkmhalalconsultant.com` (DNS on Cloudflare):

1. Cloudflare → DNS → **Add record**: type `CNAME`, name `socialmedia`, target `wanshah07.github.io`,
   proxy status **DNS only** (grey cloud). An orange-cloud proxy stops GitHub issuing the certificate.
2. Repo → Settings → Pages → **Custom domain**: `socialmedia.kkmhalalconsultant.com` → Save. Wait for the
   DNS check to pass, then tick **Enforce HTTPS** once it is offered (the certificate can take up to an hour).
3. Supabase (KPI project) → Authentication → URL Configuration → add `https://socialmedia.kkmhalalconsultant.com/**`
   to Redirect URLs, or an email sign-in link lands on an error page.

The old `github.io/semasa` address then redirects to the new one. Email on the domain is unaffected:
only the `socialmedia` name is added.

## FAQ

- **Published as rewritten, firm and formal** (Wan, 25 Sep 2026). Answers never hedge: "setahu kami",
  "tak silap", "rasanya", "apa yang saya nampak", "I think" and the like are dropped, and the point is stated
  plainly. The list is `hedges` in `rules/faq_categories.json`. A hedge the writer leaves is caught in three
  steps: the writer is asked once more, then a hedge that opens a sentence is trimmed, and only a hedge
  in mid-sentence (where trimming could break the grammar) is left and flagged.
  - An answer from practical experience is valid with no guideline behind it, so a missing instrument is
    never a reason to flag.
  - The writer may still not add a fact, figure, clause, fee, date or instrument that is not in the input.
  - **perlu semakan** is raised only for an AI-written answer (none was given), a known conflict with a
    regulation, an Indonesian word, or a mid-sentence hedge. It is a warning on the entry, never a gate,
    and it is left out of every export.
- **Anonymised.** The asker's name, company, customers, phone numbers and emails are removed. A brand
  stays only when it is the public subject (an official clarification about that product).
- **Candidates are never rewritten until accepted.** *Terima* or *Abaikan*, one at a time or all at
  once, and a candidate is never offered twice.
  - JAKIM's *Isu-Isu Tular Halal* entries arrive with JAKIM's own answer.
  - Reddit arrives as a question only: its comment feeds answer 429.
  - `forum.lowyat.net` answers 403 to any bot, so it is not a source.
- **Categories** are set in Tetapan. The AI picks one and a subcategory from that list. A category you
  pick by hand (in *Tambah FAQ* or *Sunting*) survives every rewrite and is never moved by the bot. Defaults
  are in `rules/faq_categories.json`.
- **The bot grows and sorts the list itself** (`backend/semasa/faq_sort.py`). Wan asked for it on
  25 Sep 2026.
  - A **subcategory** is added when the writer finds the category right but none of its subs fits.
  - A **category** is added only when at least **2** entries in *Lain-lain* share a topic nothing
    covers. One odd question never opens a category of its own.
  - After every rewrite, and whenever you save the list in Tetapan, the bot looks at *Lain-lain* again
    and moves what now has a better home. Saving the list wakes the worker at once, through the clock.
  - An entry whose category you deleted is re-sorted too.
  - Limits are in `rules/faq_categories.json` → `auto`: at most **12** categories and **10** subs each.
    A name that means the same as an existing one ("Label dan penandaan" = "Label & penandaan") is never
    added twice, and neither is a name with an Indonesian word in it.
  - Anything the bot made is marked **✦ dicipta bot** in Tetapan and on the dashboard. Rename it or
    delete it like any other. A category or sub you delete goes on a `declined` list and is **never
    created again**.
  - Each sort is one line in the Log ("Bot menyusun 3 FAQ: 2 ke Label & penandaan…").
- **The questions live inside their category cards** (Wan, 25 Sep 2026). Each card shows how many questions it
  holds, how many need a check, its top subcategories, and its first four questions. Click a question to open
  its answer and actions, or *Lihat semua* to open the whole card.
  - **A search shows each match twice**, as one list above the cards and inside its own card below. The cards
    keep only the categories with matches.
  - **Jadikan post** on any question sends it to the writer as an idea. The answer is the source the draft is
    written from. An AI-written answer that is not checked yet asks for `[SAHKAN]` on every specific fact.
- **Exports** follow the current category, subcategory and search:
  - **PDF** is the browser's print → *Save as PDF*, on A4, in BM, EN or both.
  - **Poster** is 1080×1350: one PNG, or a ZIP of pages for a long category.
  - **Kad** is one card per question.
  - **Excel** is a real `.xlsx`.
  - Posters keep every word: a card too long for its page says so rather than cutting. Long references
    wrap by character, and the website sits on the footer only.

## Free pictures: Cloudflare

Cloudflare Workers AI gives every account **10,000 neurons a day free**, reset at 00:00 UTC (08:00 MYT)
(developers.cloudflare.com/workers-ai/platform/pricing, updated 17 Sep 2026). On the free Workers plan a call
past the allowance is refused (error 3036) and **never billed**: the job says so and waits for Retry.

| Model | Used for | Neurons per 1024×1024 picture | Free a day |
|---|---|---|---|
| FLUX.1 [schnell] (default words → picture) | prompt-only jobs, Flow A's redraw | 4 tiles × 4.80 + 4 steps × 9.60 = **57.6** | about **173** |
| FLUX.2 [klein] 4B (default reference → picture) | Flow B with your picture | 4 × 26.05 = 104.2, + 5.37 for the reference = **109.6** | about **91** |

Setup: Cloudflare dashboard → the account ID in the sidebar → GitHub secret `CLOUDFLARE_ACCOUNT_ID`; My Profile →
API Tokens → Create Token → template **Workers AI** → secret `CLOUDFLARE_API_TOKEN`. **Pictures only**: Cloudflare's
video models are third-party ones paid from prepaid credits, not from the free neurons, so a video job on
Cloudflare stops before anything is drawn and the page does not offer it. Replicate or OpenAI make videos.

## FAQ from Telegram

A group's questions become FAQ candidates through a **bot you add to the group**. It uses the official Bot
API and is transparent: members see the bot join. The alternative, reading the group through your own
account, logs in as you and reads silently. It is not used here, because the members never agreed to it
(PDPA).

1. In Telegram, message **@BotFather** → `/newbot` → pick a name. Copy the token.
2. Still in @BotFather: `/setprivacy` → choose the bot → **Disable**. A bot with privacy on sees only
   commands, not the questions.
3. Add the bot to the group. A group that only lets admins add bots needs an admin to do it. Tell the
   members what it is for: it collects questions for an FAQ, and never names who asked.
4. GitHub secret `TELEGRAM_BOT_TOKEN` = the token. The next scrape reads the group.

What it does: a message that reads as a question becomes a **candidate**. Replies to it become its
**answer**, while it is still a candidate. Only the text is kept: never a name, username or phone
number, and the writer anonymises the text again on rewrite. Telegram keeps unread messages for **24
hours**, and the scrape reads them every 8. The group's name shows as the source; the link opens the
message when the group is public.

## The log

The **Log** tab reads `semasa_log`, which the **database** writes (`008_log.sql`). Studio's activity log
was free text written by three Routines: two timestamp shapes, fields nested where the page could not
see them, and whatever someone forgot to write was simply missing. Here a trigger on each table
records what changed at the moment it changes, whoever changed it, in one shape:

| field | what it holds |
|---|---|
| `at` | a real timestamp; the page shows Malaysia time |
| `level` | `info`, `warn` or `error` |
| `area` | scrape · idea · post · media · faq · publish · settings · system |
| `event` | a fixed code (`post.approved`, `media.error`, `scrape.finished`…) |
| `title` | one Malay line |
| `ref_table` / `ref_id` | the item, so **Buka** opens it |
| `actor` | you (*Anda*) or the worker (*Bot*) |
| `detail` | the numbers behind the title, shown labelled, never as raw JSON |

The worker adds the few events no table change captures: FAQ candidates gathered, headlines dropped at
48 hours, the bot's sorting, and the Google Sheet written or refused. The page can read the log but
never write it. Rows older than 90 days are pruned by the scrape, and every run copies new rows to the
*Log* tab of the Semasa Sheet first (see *The Semasa Sheet*). A Sheet failure is logged at most once every
6 hours, so a broken Sheet cannot fill the log with copies of itself.

The database writes titles in Malay. In English the page translates each title's fixed opening
("FAQ siap:" → "FAQ ready:") and keeps the rest (a headline, a question) exactly as written. The Sheet
keeps the Malay.

The tab shows:
- tiles for today;
- filters by period (today / 7 / 30 days / all), area, level, who did it, and a search that reaches
  into the details;
- one group per day;
- a CSV export of exactly what is filtered.

## Language: BM or EN

The **BM | EN** switch in the header changes every label, button, message and date on the page (Wan,
25 Sep 2026). Malay is the default, and the choice is remembered in that browser.

Each string is written at its call site in both languages, Malay first: `t("Simpan", "Save")`. So nothing
can go missing from a dictionary, and one line shows both versions for review.

What it does **not** change:
- the words the writers produce: captions and slides keep their own language, and an FAQ keeps its BM and
  EN (the FAQ view follows the switch, and can still be flipped on its own);
- the compliance messages, which are one rulebook shared with the publisher, in English;
- the exports, which have their own language choice.

## Published posts: never written again, archived after 24 hours

Wan, 25 Sep 2026. `supabase/010_archive.sql` and `backend/semasa/archive.py`.

- **Never written again.** An idea whose post is approved, scheduled or published cannot be sent back to the
  writer: the database refuses it, from the page or anywhere else. A *second* idea from the same news for the
  same stream is refused by the writer too, before any AI call is spent. The one way through is deliberate: add a
  note to that idea saying what the follow-up post should say. The other stream (ws.regulab vs LinkedIn) is not
  blocked, because it is a different post for a different audience.
- **Archived after 24 hours.** `posted_at` is stamped the moment a post becomes published. The publisher run
  (06:20 · 11:20 · 19:20 MYT) archives every post published more than 24 hours earlier, so between 24 and about
  32 hours after it went out. Archiving compacts the row:
  - only the captions that were sent are kept (that language, those channels);
  - the page's old scan and send errors are cleared;
  - picture and slide jobs made for the post but never used are deleted, with their files.
  The pictures that went out are kept, because the live posts still point at them. The hook, citation, date,
  slot, publish record and slides stay, so the archive is still a full record.
- The Posts page has an **Arkib** tab, and an archived post says when it was archived.

## Design: posters, cards and carousels

The **Reka bentuk** tab (Wan, 25 Sep 2026) makes three kinds of picture:

| Kind | Default size | Words |
|---|---|---|
| Poster | 4:5 · 1080×1350 | one headline and up to five points |
| Single card | 1:1 · 1080×1080 | one headline and up to three points |
| Carousel | the stream's own (1:1 ws.regulab, 4:5 LinkedIn) | 5 to 7 slides from an idea, or up to 10 by hand |

Any of them can be made at 1:1, 4:5 or 9:16 (1080×1920, a story).

- **Words:** write them yourself, or give an idea or a prompt and the writer (rootsys) turns it into words. The
  words are saved on the job before drawing, so a retry never writes new ones. *Daripada post* fills the form from
  an existing post: its slides for a carousel, otherwise its hook and caption as the idea.
- **Background:** brand paper; your own picture (uploaded, drawn under a dark scrim); or an AI picture. The AI
  picture is made first by the image provider (Cloudflare: free) and the drawing waits for it, up to 2 hours.
- **Rules:** every word is judged by the post rules (no CTA, no URL, no social source, `[SAHKAN]`). The form shows
  the flags as you type. A finished design shows them too. A design attached to a post blocks that post's
  approval while a hard flag stands.
- **Attach to a post** adds the design to that draft post's pictures. It never replaces the post's own carousel.
- **Drawing:** done by `backend/semasa/slides.py` with no AI and no cost, the same as the post carousels.

## ws.regulab Studio's designs for carousels

Wan, 26 Sep 2026: *"for post and idea carousel, copy the code design that already in ws.regulab studio, so we can
choose the design"*. Every carousel (a post's slides, an idea's slides, and the Design tab) now offers four looks:

| Look | What it is |
|---|---|
| Semasa | Semasa's own drawing (`backend/semasa/slides.py`, Pillow): cream paper, serif headline, slide numbers |
| Grid | Studio: cream graph paper, ultra-bold headline, one word in orange |
| Info ERA | Studio: kraft paper, marker highlights, red blocks |
| Photo | Studio: the picture behind the words on every slide. **Needs a background** (the post's picture, an upload, an AI picture or Unsplash) |

- **The code is Studio's own**, copied verbatim from `wanshah07/argus` `studio/part2.html` into
  `web/src/lib/cards/studio.js`, with four marked edits (card size, CORS for pictures, the logo set at run time, and
  nothing of Studio's store). Its fonts (Poppins, Instrument Sans, JetBrains Mono, Caveat; SIL Open Font License) and
  the ws.regulab logo are in `web/public/cards/`.
- **What you pick is what you get.** The picker previews every slide in your browser with that same file, and the
  worker draws the real slides with it too, in headless Chrome (`backend/semasa/studio_cards.py`; the runner's own
  Google Chrome, so nothing is downloaded).
- **Every word is kept.** Studio's templates show at most 3 or 4 points; a slide with more gets the layout that
  draws them all as lines. A slide Studio calls fuller than the card is shown in red in the preview, blocks
  *Generate*, and fails the render with its number. It is never cut.
- LinkedIn slides carry no ws.regulab logo, as in Studio.
- An idea remembers its look (in its `brief`) until the bot writes its slides.

## Try Mireld for one run

Settings → **Cuba Mireld untuk satu larian**. The next scrape and the bot's next job that asks the writer anything
ask Mireld **first**: the news summaries, the drafts, the design words, and the read of a reference picture. rootsys
answers whatever Mireld cannot, so no work is lost. After three misses in a row, rootsys leads for the rest of that
run, so a silent Mireld cannot stall a scrape. Each half then writes its result on the card and switches itself off:
how many answers came from Mireld and from rootsys, whether Mireld could read a picture, and the models Mireld's own
`/models` list names (the card marks any that look like image models). The result also goes to the Log.
The switch (`semasa_settings.llm_trial`) is created by the worker on its first run after this update; the browser
may edit settings but not add a key. It uses the secrets already set (`LLM_FALLBACK_API_KEY`, `LLM_FALLBACK_MODEL`).

## Unsplash

A picture source beside Cloudflare, in the Media lab, the post editor (*Gambar*) and the Design tab (*Latar →
Unsplash*). Search, click a photo, and it becomes an ordinary picture: a post picture, a slide background or a
design background.

- **The key stays on the worker** (`UNSPLASH_ACCESS_KEY`). A search is a media row the worker answers in about a
  minute; the pick is the same row sent back. Nothing about the key reaches the page.
- **Unsplash's API rules are kept:** the results shown are Unsplash's own addresses, the download is reported to
  Unsplash when you pick, and the photographer is credited with a link wherever the page shows the photo. No credit
  goes into a caption (ws.regulab captions carry no URL, and the licence does not ask for one there).
- A demo app gets 50 requests an hour (a search is one, a pick is one). For more, apply for production on the
  Unsplash developer page.

## Video: a long talk becomes short clips

The **Video** tab (Wan, 26 Sep 2026: *"cut, edit video for short video such as youtube video (ceramah agama) …
paste youtube page … once approve can cut edit and create into short video"*).

1. **Paste a link:** a YouTube video, or a link to a video file (Google Drive shared with *anyone with the link*,
   or a direct `.mp4`). Pick the stream and domain, and say what you want from it.
2. **The bot reads it:** the transcript you pasted comes first; then the video's own subtitles; then YouTube's
   automatic captions; for a video file with none of those, Cloudflare Whisper hears it (the same free allowance
   as the pictures). The writer proposes 3 to 6 clips of 15 to 90 seconds, each a complete thought, with a hook, a
   caption crediting the speaker, and a warning on any clip that states a ruling (hukum), so you check its context.
3. **You confirm the rights once per video:** your own video, the owner's permission (with a note of the proof), or
   Creative Commons. Cutting and republishing someone else's talk without permission can infringe the **Copyright
   Act 1987** and YouTube's terms. Nothing is cut before this is recorded, and the worker checks it again.
4. **Edit and approve a clip:** watch it in place, change the start and end, the hook and the caption (checked by
   the post rules as you type), choose *whole + blurred sides* or *crop to fill*, captions on or off, then **Luluskan
   & potong**.
5. **The bot cuts it** (`backend/semasa/video.py`, the static ffmpeg from the `imageio-ffmpeg` wheel): 1080×1920,
   captions burnt in, the hook in a box at the top, the ws.regulab mark on ws.regulab clips (none on LinkedIn), H.264
   kept under 50 MB. It writes a **draft post** with the clip and the caption at the next free slot. The post goes
   through the Posts tab like any other; nothing is published here. *Potong semula* on the same clip replaces the
   clip in its own draft.

**When YouTube refuses GitHub's machine** ("Sign in to confirm you're not a bot", which happens to cloud servers):
paste the transcript yourself (YouTube → description → *Show transcript* → select all → copy) and *Baca semula*,
which is enough to propose clips; to cut, add the video again as a Google Drive link. `YTDLP_COOKIES` is the last
resort, with a spare account.

## Regulatory and Latest publication

Two segments beside *Isu semasa* in the first tab (Wan, 26 Sep 2026: *"add segment like current issue for regulatory
and latest publication … run every 24 hours … regulatory/current issue/latest publication > idea/ppt/poster > render
the carousel/card > post"*).

- **Regulatori** reads the regulators' own list pages: NPRA (Kenyataan Media KKM, safety alerts, directives,
  circulars, announcements), Portal Halal Malaysia, HSA Singapore, EU SCCS opinions, UK OPSS and China NMPA. Items
  older than 45 days are skipped. Portal Halal's newest item was April 2025 when this was built, so that source is
  often empty. That is the portal's own state, not a fault.
- **Penerbitan terkini** reads PubMed (the official E-utilities API, no key): papers added in the last 14 days on
  cosmetic science, consumer dermatology, halal science and cosmetic contaminants, with the journal, authors, DOI and
  abstract.
- **Once a day.** The sweep rides on the 8-hourly scrape and runs when 23 hours have passed, so in practice it is the
  same run every day. *Sapu sekarang* wakes the worker to sweep straight away.
- **The writer's notes.** For every new item the writer adds a Malay summary, the domain, *why it matters* to a
  Malaysian business, and whether it is relevant at all. A foreign ministry's diplomatic news is marked *kurang
  berkaitan* and hidden by default; tick the box to see it. *Sembunyi* hides an item for everyone. Items are kept
  45 days.
- **Jadikan idea** opens the same idea box as a headline:
  - A notice goes to ws.regulab in its domain.
  - A paper goes to LinkedIn, angle F (cosmetic science) or G (medicine and dermatology).
  - Both start as a **carousel**. Pick **Post**, **Carousel (slaid/PPT)** or **Poster**, and the design (Semasa's own
    or Studio's Grid, Info ERA or Photo).
  - The worker writes the draft, draws the slides or the 4:5 poster, and the draft goes through the Posts tab like any
    other.
  - Unlike a news portal, the regulator or the journal **is** the source, so the writer is told to cite it by name
    with its reference, or the paper's authors, journal, year and DOI.

EU Safety Gate is not in the list: its alert pages are drawn by JavaScript and a plain fetch gets an empty shell.

## Card or table

Current issues, Ideas and Posts each switch between cards and a table. The switch is remembered in this browser.
On a phone the table stacks each row into a block with the column names beside the values, so nothing is cut off.
Long titles and references wrap and never push the page sideways.

## One writer: rootsys, with Mireld as its backup

Wan, 25 Sep 2026: from drafting to the Buffer queue, the AI is rootsys and nothing else. Every text AI call
(headline summaries, drafts, slides, FAQ, sorting, reading pictures) goes through one place, and it may only call a
host in `LLM_ALLOWED_HOSTS` (default `rootsys.cloud`). If `LLM_BASE_URL` points anywhere else, or is missing
(which used to mean OpenAI), the writer switches **off**: nothing falls back to another AI, ideas and FAQs say
why, and the scrape run turns red. Allowing another host is a deliberate GitHub variable, never a default. The
Buffer step itself uses no AI: it moves the approved caption exactly as written.

**The backup** (Wan, 25 Sep 2026: "can we add mireld as open api backup"):
- **When it is asked:** only when rootsys gives no usable answer: it times out, errors, or answers with something
  that is not JSON. Mireld is asked once, with its own key. The rootsys key never goes to Mireld, nor Mireld's to
  rootsys.
- **Where it is allowed:** only on its own list (`LLM_FALLBACK_ALLOWED_HOSTS`, default `api.mireld.my`). Mireld
  can never become the main writer by accident.
- **Pictures:** the backup never reads pictures, because nothing says its model can see.
- **Showing that it answered:** the scrape run shows a yellow warning and records `+ backup <model> ×n` as its
  writer. A draft records the model that wrote it.
- **Switching it on:**
  - secret `LLM_FALLBACK_API_KEY`: the Mireld key.
  - variable `LLM_FALLBACK_MODEL`: the Mireld model name, from its dashboard.
  - `LLM_FALLBACK_BASE_URL` is only needed for a different address than `https://api.mireld.my/v1`.
  - A key without a model leaves the backup off and says why.

## The clock

GitHub runs scheduled workflows "best effort", and on 24–25 Sep 2026 that meant hours of nothing.
`009_clock.sql` puts the timing in Supabase's own scheduler (pg_cron), which wakes the workflows through
`repository_dispatch` with the Vault token from step 4:

| job | when (MYT) | wakes |
|---|---|---|
| `semasa_scrape` | 07:17 · 15:17 · 23:17 | *Scrape isu semasa* |
| `semasa_worker` | every 10 minutes, **only when something is waiting** (a new idea, FAQ or media job, or one stuck) | *Generate media* |
| `semasa_publish` | 06:20 · 11:20 · 19:20 | *Publish (dry run)* |

An idle day costs no Actions minutes. GitHub's own schedules stay in the workflows as a second, slower net.
Each workflow's `concurrency` group runs a double start one after the other. Neither start can double a
result: the scrape upserts, the worker claims each row once, and the publisher skips a channel already done.

Check it:
```sql
select jobname, schedule, active from cron.job where jobname like 'semasa_%' order by jobname;
select start_time, status, return_message from cron.job_run_details d join cron.job j using (jobid)
 where j.jobname like 'semasa_%' order by start_time desc limit 20;
```
Stop it: `select cron.unschedule(jobname) from cron.job where jobname like 'semasa_%';`

## Tabung perkataan Indonesia

Tetapan → **Tabung perkataan Indonesia** is Wan's own list of Indonesian words and phrases that still
slip through, each with the Malaysian word to use instead. It sits on top of the built-in list in
`rules/compliance.json`, and it is applied everywhere:
- every writer's prompt tells the AI to avoid them (drafts, slides and FAQ);
- the compliance scan blocks them in captions and slides, in the page and in the publisher alike. The
  message names the word to write instead, and the other language variant only warns;
- an FAQ whose BM text still contains one is marked **perlu semakan**, with the words named.

A one-word entry matches whole words only: *pakai* never matches *pemakaian*. An entry of several
words matches as a phrase.

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
- Editing an approved post's words, slides, source, pictures or time sends it back to draft.
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
| Carousel slides: written by the writer or by hand, drawn by the worker (`slides.py`, Pillow, no AI, no key), 1080×1080 / 1080×1350, `*emphasis*`, long references split instead of clipped, never a word cut (too long fails the job and names the slide), the website on the ws.regulab footer only, source on the closing slide, optional photo ground under a scrim, compliance on every slide, and a block when the drawn slides carry older words | ✅ 25 Sep 2026 |
| Studio's other card families (grid / ERA / photo), logo, mascots | ⏳ phase 2 |
| Regulator sweep (NPRA, halal.gov.my, EUR-Lex, PubMed…) as ideas | ⏳ phase 2 (Semasa reads news only today) |
| Moving Studio's store (drafts, media, settings, log) | ⏳ last, then Studio is retired |

## Behaviour worth knowing

- **Slides are drawn from a snapshot.** *Jana slaid* saves the post, then queues one `slides` job carrying
  the words. The pictures are exactly those words. If the slides are edited afterwards, the page and
  the publisher both block the post until it is drawn again. A new set replaces the post's old set in
  the same position. Like every worker write, it lands only on a draft.
- **A headline has 48 hours.** The Isu tab shows the last `PICK_HOURS`, and a card counts down its last
  12. A headline made into an idea is kept, and the idea keeps its own copy anyway.

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
