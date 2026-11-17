# Standing rules for Semasa

## Anti slop
`antislop active: during (project instruction, Wan, 26 Oct 2026)`. The skills are in `.claude/skills/antislop*` (github.com/miqdadbadjuber/anti-slop
v3.2.23, MIT). Before UI, copy or comment work, load the core `antislop` skill and the one that matches the work: `antislop-ui`,
`antislop-layoutmobile`, `antislop-copywriting`, `antislop-code` (comments), `antislop-human`. The skill's mode question is already answered:
do not ask it again here.

- Text this system writes for the public goes through `backend/semasa/antislop.py` (`PROMPT` for the writer, `clean()` on what comes back).
  A new writer of public text gets both. `ops/ANTISLOP.md` says what is applied and lists the open findings.
- Wan's own voice outranks the filter (R-37): the film hooks, the connecting sentences between scenes and the closing line stay.
- Malaysian Malay only, never Indonesian (`motion.malaysian`, `compliance.json` `indo`).
- No em dash in anything a person reads. No fabricated number, name, quote or claim.

## Hooks and captions

`.claude/skills/hook-bank/SKILL.md` holds 25 fill-in-the-blank hook shapes in five groups
(CURIOSITY, TRANSFORM, VULNERABLE, BOLD, RELATABLE). `backend/semasa/hook_bank.py` carries the
same 25 (re-exported by `ideas.py` as `HOOK_FAMILIES`) and **every post's first line must be built
on one of them** (Wan, 6 Nov 2026: "25 hook tu wajib dalam ayat"). The writer is always given the
shapes its stream may use, numbered 1 to 25 in series order, and must say which in `"hook_shape"`.
An answer without a usable number (or with blanks left in the hook) is asked for once more; a second
miss fails the idea with a reason, so no post leaves without a shape. The same holds for "revise
with a note". The number and whether the caption opens with the hook are kept on the idea's `brief`
(`hook_shape`, `hook_in_caption`). If the bank changes, both copies change: the markdown is the
reference, the constant is what the writer actually sees.

The shapes are Malaysian Malay. A Malay post uses a shape as written; an English post (LinkedIn)
translates it faithfully. The rules above still outrank the shapes, and when no shape can be filled
without inventing a fact the writer takes a RELATABLE or CURIOSITY shape, which assert nothing.
VULNERABLE is withheld on the company stream by `OFF_BRAND`: first-person confession belongs to
Wan, never to ws.regulab. `hook_family` on an idea narrows the shapes to one family; it no longer
decides whether a shape is used.

A **hook style** made from screenshots (`ops/HOOK-STYLES.md`, `hook_styles.py`, `semasa_hook_styles`) replaces the built-in 25 and
their default guidance while it is selected (the default in `settings.hook_style`, or `brief.hook_style` on one idea): the same
requirement applies to ITS numbered shapes, and its instruction can never lift a rule (`hook_styles.LIFT` drops the sentences that try).

**Motion's hook scene uses the shapes too** (Wan, 7 Nov 2026: "do 1,2,3"): it no longer opens with Tahukah anda / Amaran / Berita
terkini. The film's script prompt carries `hook_bank.film_block` (the stream's shapes, or the selected hook style via
`hook_bank.pick_for_idea`) and asks for `hook_shape` + `hook`; a script without a usable shape is asked again once, and a second miss
fails the film with a reason (Redo). Scene 1's heading is made equal to the hook (up to 14 words), the shape is kept on scene 1, the
plan, `check_report.hook` and the style note, and `hook_first_said` records whether the narrator's first words are the hook. A film
built on a shape draws no TAHUKAH ANDA / AMARAN / BERITA TERKINI chip (`motion_auto.choose` sets `hook` to ""); a film with no shape
(an older one) still does.

**Hooks learn from results** (Wan, 7 Nov 2026, `ops/HOOK-LEARNING.md`): `hook_learning.py` (daily, `hook-learning.yml`) ranks the shapes on the
last 60 days of views and interaction (post metrics joined to `brief.hook_shape` or a film's `check_report.hook.shape`) and every writer
(post, revise, film) gets the top three as a HINT in the required-hook block, after the rules, never a rule: a shape needs 3 results, unranked
shapes keep being tried, no hook text is quoted, and `settings.hook_learning_on` turns it off. The cover slide and the poster headline wear the
hook too (`hook_bank.cover`).

Pick the group by how much the post asserts: CURIOSITY and RELATABLE assert nothing,
BOLD asserts an opinion, TRANSFORM asserts a result, VULNERABLE asserts something about the
author. The higher the assertion, the higher the evidence bar, and rule 4 above already
forbids any invented fact.

Two hard limits that come from this repo's own rules, not from the format:

- A hook may not promise a figure, a duration, an approval or a cure. Blanks stay abstract
  until the source in `rules/` supports a specific.
- A VULNERABLE hook is first person about a named human. Never render one under a company
  identity; Semasa's public voice is the company.


## Navigation (Phase 1, 11 Oct 2026)

- The sidebar lists **segments**, not pages (`web/src/lib/tabs.js`: `tabsOf` is the one list of pages, each with a `segment`; `segmentsOf` / `segmentOf` group them). A segment opens its first page and a tab row (`components/SegmentBar.jsx`) shows the others. A page keeps its own hash (`#post`, `#office`…), so old links work. `tabs.test.mjs` fails if a page is in two segments or none.
- **Kanvas is removed** (page, `canvasSeed.js`, `leaveGuard.js`, every "Edit in Kanvas" button). Design's rebuild/inspire flow now ends in **Download PNG** (`renderSeedPreview` at full size). `kanvasBuild.js` stays only because that preview uses it.
- **Office repos** (`pages/OfficeTab.jsx`, the health board) and **Repo library** (`pages/RepoTab.jsx`, pasted links) are two pages in Technology.
- Pages fill the width: `--page-max` is `min(100%, 1920px)`.

## Create, split in three (Phase 2, 11 Oct 2026)

- Three segments, each with a **generate** page and a **library** page: Image (`media`, `media-lib`), Video (`video`, `video-lib`, `motion-skills`), Poster (`design`, `design-lib`). Libraries are `components/TileGrid.jsx`: square tiles, 8 across from 1280 px, click opens the page's own full card in a dialog (retry, delete, post, download all kept).
- Image and video generation are apart: `MediaUploader` takes `only="image" | "video"`. Generate video is one page with three ways (Motion, AI video, YouTube clips; the choice is remembered). `MotionLab` and `DesignTab` take `view` (`make` / `library` / `skills`) so one component holds the state and each page draws its share.
- The motion skill box moved from Tetapan to **Motion skills** (`components/MotionSkill.jsx`), beside the motion repos, and takes a `.md` / `.txt` upload (fills the box, saved only on Save). The effect library and per-film pictures stay in the Motion form: they are choices for one film.

## Pasted components, 7 Nov 2026

- **OrderTracking** (`components/ui/order-tracking.tsx`): the Motion card's process tracker, Idea → Storyboard → Pictures → Film (`lib/motion.js motionTrack`). Times come from `semasa_motions.stage_times` (supabase/064, written by `motion.set_stage`; a new run clears them at the storyboard; before 064 the stage is still written without times).
- **AnimatedTabs** (`components/ui/animated-tabs.tsx`): the sliding pill in every segment's tab bar (`SegmentBar`). Theme colours, controlled `value`/`onChange`, `hideContent`.
- **GlassWorkspace** (`components/ui/adjustable-glass-dashboard.tsx`) is **Ringkasan wang** (`#wang`, Business). `lib/money.js`: money in = invoices marked paid (a receipt document is never counted twice), money out = read purchase receipts + a subscription's last payment only when no receipt covers that month; open invoices and the next 30 days of bills are pending and never summed; ringgit only. No savings goals exist, so that view hides. The glass setting is per browser.
- **Bento** (`components/ui/interactive-tech-stack-bento-grid-with-hover-effects.tsx`) is the **Technology overview** (`#tech`) with real rows only (api_status, repos). Its default export is the pasted demo with random numbers and is never rendered. `PYTHON` in `TechOverviewTab.jsx` is checked against the workflows by `techOverview.test.mjs`.
- **DashboardLayoutConfigurator** (`components/ui/dashboard-configuration.tsx`): Papan → "Susun papan"; `settings.dashboard.hidden` (supabase/065). The headline tiles are permanent.
- `components/ui` holds both Semasa's `Button.jsx`/`Card.jsx` and shadcn's `button.tsx`: on a case-insensitive disk `@/components/ui/button` finds `Button.jsx` first, so a pasted component imports `@/components/ui/button.tsx` explicitly and takes Card from `@/components/ui/app-1-utils/card`.
- Never spread a variants object onto an element (`<motion.div {...fadeUp}>`): it passes `hidden={…}` and the browser hides the element. Nine page headers were invisible this way; `tabs.test.mjs` now fails on it.

## Businesses (Phase 3, 7 Nov 2026)

- `semasa_businesses` (supabase/066): one row per business, `billing` in the shape `settings.billing` has always had. **WS REGULAB** (`wsregulab`, seeded from `settings.billing`) and **VALORITH** (`valorith`, prefixes VAL-QT / VAL-INV / VAL-RPT, no bank, auto-send off). More are added in Perniagaan → **Syarikat**; a business is never deleted, only switched off, and WS REGULAB cannot be switched off.
- `business_id` is NOT NULL (default `wsregulab`) on clients, projects, billing documents, CRM contacts and campaigns, so every row from before 066 is WS REGULAB's. On receipts and subscriptions it is NULLABLE: null = personal.
- Numbering is per business: `semasa_billing_counters` key `(business_id, prefix, year)`; `semasa_billing_issue` reads `semasa_billing_settings_for(business)` (own billing, else `settings.billing`) and refuses a number another business already holds. An issued document cannot change business (guard trigger).
- **Bil & Resit** shows one business at a time (picker remembered as `semasa.view.billing.business`; Syarikat's "Bil & tetapan" sets it). **Bil Valorith** (`#bil-valorith`, Valorith segment beside Wangian) is the same page with `lockBusiness="valorith"`. Settings save to the business row; a prefix another business uses is refused.
- The paper's logo: WS REGULAB's logo only on WS REGULAB's papers; another business uses its own `company.logo_url` (https) or prints its name (`lib/businesses.js logoFor`, the same rule in `backend/semasa/billing.py logo_for`).
- E-mail: one Gmail connection sends for every business. `billing.py` claims the business's address as From only when it is the connected account; otherwise the mail goes from the account and the signature names the business.
- **CRM** combines every business with a picker (all / one); a contact and a campaign each belong to one business, and `semasa_crm_queue` sends a campaign only to its own business's contacts. **Ringkasan wang** picks all / a business / personal.
- Before 066 is applied every page still works as one business (WS REGULAB, `settings.billing`), with no pickers.

## Hooks bank and writing styles (Phase 4, 7 Nov 2026)

- **Bank hook** (`#hooks`, Content) holds everything that decides a post's first line; the hook-style and hook-learning cards moved here from Tetapan. The built-in 25 are shown (`web/src/lib/hookBank.js`, a copy of `backend/semasa/hook_bank.py FAMILIES`; `hookBank.test.mjs` fails if the two differ) and are never edited in place: they stay the worker's fallback.
- A hook set can be made three ways, all rows of `semasa_hook_styles`: by the bot from screenshots (`source = 'screenshots'`, 060), written by hand, or **Salin untuk diubah** (a copy of the 25). The last two are `source = 'manual'` (067): ready at once, at least 3 shapes, never sent to the bot (the policy keeps them `ready`). Every ready set is edited, added to (the one-line box or the textarea) and applied as the default (`settings.hook_style`) or on one idea (`brief.hook_style`). Shapes are numbered in line order, so editing a set renumbers it for hook learning.
- **Gaya penulisan** (`#gaya`, Content): `semasa_writing_styles` (067), apart from the hook: how the whole caption reads. Made from viral posts (links, pasted text, screenshots; `backend/semasa/writing_styles.py`, the "Writing styles" workflow, repository_dispatch `writing_style`) or written by hand (`source = 'manual'`). The worker describes HOW the posts are written: a sentence or trait that repeats 8 words in a row from a source, carries a link or handle, or tries to lift a rule is dropped. LinkedIn, Instagram, TikTok and X usually hide a post from a plain fetch; the card says so and pasted text or a screenshot fills the gap.
- The chosen writing style (`settings.writing_style`, or `brief.writing_style` on an idea; `none` = no style) is added to the caption writer's prompt after the house style and before the required-hook block (`ideas.build_request style_block`), to a revision, and to a Motion film's script (`writing_styles.pick_for_idea`). It says it changes the voice only, never a fact, the citation, the stream's language, the hook requirement or any rule.
- **Senarai teknologi** (`#stack`, Technology): ONE list of every API (with its models), SDK, CLI, repo and service. Read from what is true: `web/src/lib/stack.js` `CODE_APIS` (every outside service, by the secret each workflow reads; `stack.test.mjs` fails when a workflow reads a secret no entry names, or an entry names one nothing reads), `CLIS` (each checked against a workflow), `PY_PACKAGES` (checked line by line against `backend/requirements.txt`), `web/package.json`, the probe's gateways and models (`semasa_api_status`; Gemini's models sit on its own entry), the office repos and the repo library. What Wan adds by hand is `semasa_tech_items` (068): a secret's NAME only (the column refuses anything but `UPPER_CASE`), never its value. A new secret in a workflow means a new or updated `CODE_APIS` entry, or CI goes red.
- Repo registration (Repo pejabat → Senarai repo) takes `owner/name` or any GitHub address of the repo (`www.`, `/tree/main`, `.git`); only `owner/name` is kept.

## Sidebar, overview and the health report (7 Nov 2026)

- The sidebar lists each segment's pages under it (`AppSidebar` → `dashboard-sidebar.tsx` children); the group holding the page in view opens by itself, a one-page segment stays one row. "Pin menu / Auto-sembunyi menu" sits in the sidebar's foot as well as beside the header (`semasa.sidebar.v2`).
- Moved out of Tetapan: the house style card (`WriterSettings`, now titled "Gaya rumah") to Gaya penulisan; Tetapan AI and the Mireld trial to Technology → API. They are still defined in `SettingsTab.jsx` and exported.
- Ringkasan wang fills its frame (`.gw-workspace` 100%); with no savings goals the lower grid is one column.
- Papan has a "Carta ringkas" widget (`components/HomeCharts.jsx`, sums in `lib/dashboard.js`): ideas by status, posts by channel (30 days), AI tokens a day (14 days), posts by topic. It sits under the main chart (`App1`'s `below`).
- The design library under Pustaka poster uses `TileGrid` (8 a row) for the grounds and the mascot poses.
- Fixed from the 7 Nov audit: the probe's `model_listed` ignored Google's `models/` prefix; the probe asks Gemini with `reasoning_effort: low` (asked again plainly if refused); with Gemini on Auto a 503/hang on one model hands the job to a stable 2.5 Flash on the same key (`gemini_keys.backup_model`), a pinned model is never swapped; a ChatGPT storyboard call now records `last_ok_at`/`last_error`; Buffer refuses a video asset with `thumbnailUrl`, so it is no longer sent; Motion's `apt-get` is time-limited.
- **Health report** (`backend/semasa/health.py`, `health.yml`, every 6 h): clears publisher errors whose cause is fixed in code (`KNOWN_FIXED`; the publisher still never sends early or late), requeues ideas the writer did not answer (transient only, ≤10 a run, <3 attempts, last 3 days), and reports failed workflows, gateways, Gemini, the ChatGPT login, LinkedIn restrictions, publisher and billing errors and the Gmail connection. It e-mails Wan (WS REGULAB's company e-mail, or `vars.HEALTH_EMAIL`) from info@ in a plain watchdog form (Wan, 7 Nov 2026, after the Halal Practitioners Hub's): "Semasa watchdog: needs attention" with one `PROBLEM:` line a new problem; "Semasa watchdog: all working again" (or "fixed, N still need attention") with `FIXED: <area> is working again (problem started <UTC>)` and `FIXED BY SEMASA:` for its own fixes; a "daily check" at the 09:17 MYT run. Each open problem keeps its first-seen moment in `health_state.open`, written only once the e-mail went (a failed send says it again). State in `settings.health_state`; one `semasa_log` line a run (area `system`). A new fixed-bug pattern goes in `KNOWN_FIXED` with its cause gone from the code first.
- **Semasa on Telegram** (Wan, 7 Nov 2026: "communicate from telegram, approve post and I can attach link so semasa can read", then "add all relevant features"). `supabase/069_telegram_bot.sql`, Edge Function `semasa-telegram`, `backend/semasa/telegram_bot.py`, `telegram.yml`.
  - Telegram POSTs to the Edge Function (deployed `--no-verify-jwt`; the gate is the `X-Telegram-Bot-Api-Secret-Token` header, `TELEGRAM_WEBHOOK_SECRET` = HMAC-SHA256(bot token, "semasa-telegram-webhook"), set by functions.yml, so there is no second secret). It stores the update in `semasa_telegram_inbox` and answers in the response body (never holds the bot token). The database wakes `telegram.yml` (repository_dispatch `telegram`) for Wan's messages and taps; a 2-hourly schedule (08:05–22:05 MYT) is the net and pushes new drafts.
  - ONE Telegram account is obeyed: the one that sent `/start CODE`, a one-time code from Tetapan → Telegram (8 hex characters, 15 minutes, once, only its sha256 stored). Link, codes, inbox and `semasa_telegram_sent` are service-role only.
  - Commands: /draf (picture + ✅ Lulus / ❌ Tolak), /jadual, /status, /ralat (🔁 Cuba lagi on a failed idea), /kesihatan, /bil, /idea or a bare link (ws.regulab / LinkedIn / Batal buttons; the idea is written only on the tap), any other text is a question answered by the AI team with a snapshot and the last turns (it cannot change anything).
  - **Approve keeps the gate**: `semasa_telegram_decide` runs the update as Wan's own login (`request.jwt.claims`, transaction-local), so `semasa_posts_gate` stamps approved_by/at and `_v3` refuses a taken slot or duplicate words as for the page; only the version Wan was shown (`semasa_telegram_sent.version`) is approved; the publisher's own hard checks run first and the fresh flags are saved with it (`semasa_posts_approve_clean` needs hard_flags = 0). Proved on 7 Nov 2026 in a rolled-back run against the live gate.
  - Group messages for the FAQ come from the inbox now (getUpdates answers 409 once a webhook is set; faq_sources still reads it before then). The watchdog's alerts also go to Telegram, and `check_telegram` reports a broken webhook or Wan's messages unanswered for 30 minutes.
- **Each business sends from its own Gmail** (Wan, 7 Nov 2026: "for valorith change to muhammad.ridzuan22222@gmail.com"). `billing.make_senders` gives WS REGULAB's sender and `sender_for(email)`: a business whose company e-mail is connected in Composio sends from that inbox with its own From; until it is, its mail goes from WS REGULAB's inbox with no From claimed, and the health report says so (`check_business_gmail`). `GmailMCP.account()` takes one inbox connected twice (a reconnect leaves the old link active: info@ was on `gmail_smock-upgang` and `gmail_prissy-stingo`) as one inbox, Composio's default first, else the lowest id. Before this, that duplicate refused every WS REGULAB send and CRM mail ("expected exactly 1"). CRM still sends from WS REGULAB's inbox only.

## Motion film templates (7 Nov 2026)

- Wan: "buatkan motion boleh buat macam ni, storyboard dari gemini, picture from chatgpt or cloudflare". Motion's form has a **Film template**: Explainer (as before), **Product showcase**, **Photo story** (`web/src/lib/motionTemplates.js`, `components/MotionProducts.jsx`; worker `backend/semasa/motion_templates.py`, run by `motion.template_film` from `process`). The choice is `options.template` on `semasa_motions` (with `options.products`, `options.brand`): no migration.
- Storyboard: one strict JSON object, Gemini first, then ChatGPT (login), then the film's writer; code validates every field and the hook shape, and a refused answer is asked once more with the reason. Pictures: ChatGPT, Cloudflare, Gemini (`draw_scenes(order=...)`), then Unsplash. A showcase's product pictures are always the user's own (a library id read back from the database, or a private upload); only its background is AI, and the "generated with AI" line is drawn only when that is true.
- The pages are laid out by code (1080x1920, about 20 s, silent with the approved piano). The references belonged to another brand: never put its name, logo or copy anywhere; the brand is the business picked (`semasa_businesses`), and LinkedIn never wears WS REGULAB's identity.
- **Telegram, round two** (Wan, 7 Nov 2026: "telegram always improve ... robot button ... identify which model run now and I can choose ... develop report or poster or motion or video"; `backend/semasa/telegram_tools.py`).
  - `/robot` lists the AI team from `semasa_api_status` and `ai_team_state` (who writes now, each robot's state and speed) with a button per healthy text robot and Auto. A tap writes `settings.ai_team.pins.reader`, the API page's own pin (other pins kept); a robot that failed its last check, and ChatGPT (Motion's pictures and storyboard, not a router writer yet), cannot be pinned.
  - Every answer ends `— <robot> · <model>`, read off the call's own usage record (`llm._record_usage`), so a failover is reported as it happened; the model is told who it is, so "which model are you" is answered truthfully (it once claimed to be another product).
  - It improves itself: Wan's standing notes are `semasa_chat_memory` (the AI chat page's own notes) and go into every answer; `/ingat` adds, `/memori` lists and deletes; 👎 under an answer makes his next message a standing note ("Pembetulan Wan: …"); 👍 is counted. Each exchange is kept in the AI chat page's `Telegram` thread (`semasa_chat_threads/messages`), which is also where the earlier turns come from.
  - `/poster` and `/karusel` write an idea (`brief.format` poster / `make_slides`), `/motion` and `/video` queue a `waiting` film (`options.via = telegram`) with a ▶️ button that sets it `pending` (the existing trigger wakes Motion) and send the finished film back; `/laporan` writes a Markdown report and sends it as a file.
  - The command menu (`setMyCommands`) is re-sent whenever `COMMANDS` changes (`settings.telegram_bot.commands`).
- **Telegram, round three** (Wan, 7 Nov 2026: "make sure telegram answer more fast", "add button like this in telegram as per segment").
  - `/start` and `/menu` show a button menu by segment (Kandungan, Cipta, Sistem, Bisnes & memori, Buka Semasa; `telegram_tools.MENU`). A button that needs a topic (idea, poster, karusel, motion, laporan, ingat) asks for it and the next plain message becomes `/<action> <text>` (`telegram_chat.pending`); the rest run at once.
  - **Fast answers:** a plain question from the linked account is answered inside the webhook (`semasa-telegram`, `fastAnswer`) with the AI chat's own gateway secrets (`gatewayConfig` from `semasa-chat/logic.js`), in seconds, instead of waking the GitHub worker. Only when nothing else must happen first (`fastEligible`: no command, no link, no pending topic, no 👎 correction waiting, and the /robot pin is Auto or this same gateway); a gateway error or anything past 22 s goes to the worker as before. The answer carries the same footer and 👍/👎 buttons, and the turn is kept in the Telegram thread.
- **Telegram, the menu of every feature** (Wan, 16 Nov 2026: "make sure all features appear in telegram semasa button"; `rules/telegram_menu.json`, `backend/semasa/telegram_menu.py`, `supabase/functions/semasa-telegram/menu.js`). This replaces the five-button home of 9 Nov and the webhook's older four rows.
  - ONE catalogue holds every button: the page's own segments and pages in the sidebar's order, plus `system` (Settings and the bot's own reports). `/menu` and `/start` open home (two quick buttons, a button a segment, the language switch, Open Semasa); a segment lists its pages; a page with something to do in the chat has its own short menu, and a page with nothing is a link straight to that page.
  - **A new tab needs an entry.** `web/telegramMenu.test.mjs` and `backend/tests/test_telegram_menu.py` fail when a tab in `web/src/lib/tabs.js` has no entry in the catalogue, when an entry names a tab that is gone, or when the segment, the order or either name differs. After any change to the JSON run `python ops/telegram_menu_copy.py`: it rewrites the webhook's copy (`menu_data.js`) and `rules/telegram_menu_cases.json`, which is what both renderers must draw.
  - A button is `m:<node>` (another menu, drawn where the tapped one was; `n:<node>` under an answer sends it as a new message so the answer stays), `a:<act>` (the worker does it: `telegram_menu.ACTIONS`, every name in the catalogue and only those) or a URL. An action is only what the bot could already do: a read, the drafts with their own Approve / Reject through `semasa_telegram_decide`, or a question whose answer becomes a row a worker reads (an idea for ws.regulab or LinkedIn, a poster or a carousel in a look Wan picks: `brief.look`, a repo, a writing style). Two reads are new: the vague-wording check on pasted text (`compliance.vague_hits`) and an ayat by surah:ayat (`quran.fetch`; the tick that a verse was checked stays on the page). No button approves, publishes, deletes or spends.
  - Malay unless Wan picks English (🌐 on the home menu; `settings.telegram_chat.lang`), like the page. The webhook redraws a menu tap in place at once (`ops/TELEGRAM-SPEED.md`); the worker draws the same menu when the webhook leaves a tap to it.
  - A link can name a choice inside a page: `#design/comic` (`web/src/lib/deepLink.js`; App.jsx reads the page, the page reads the rest with `useSubLink` and ignores a choice it does not offer). The bot's links to a post used `#posts`, which is not a page and opened the dashboard: they are `#post` / `#li-post` now (`telegram_menu.page_url`).
- **ChatGPT on the API page as Wanshah 5** (Wan, 7 Nov 2026: "check chatgpt and move to api"). The login card moved from Motion to Technology → API. A model the account refuses ("The 'gpt-5' model is not supported when using Codex with a ChatGPT account", `model_not_found`) is replaced in `Login._with_model`: the account's own list (`/backend-api/codex/models`) first, then `FALLBACK_MODELS`, at most `MODEL_TRIES`; the first that answers is saved as the row's model. The 6-hourly API check writes a `semasa_api_status` row `chatgpt` (`probe_row`: login refreshed, models listed, one real "OK" answer). Repo library cards show the original link as text.
- **AI chat: every model of all five robots** (Wan, 7 Nov 2026: "for AI Chat, allow me to choose all model accross all 5 bots"). The picker groups each robot's chat models with its live state (`semasa_api_status`) plus Auto; `semasa-chat` reads each key where it already lives (function secrets, the page's AI slots by `key_host`, `semasa_gemini_keys`, `semasa_chatgpt_auth`) with the service role, sends it only to that robot's host and never back to the page. A robot whose key is only a GitHub secret is listed unavailable with that reason. Auto never picks Gemini (free-key privacy) and puts ChatGPT (no tools in the chat) after the robots with tools. See `supabase/functions/semasa-chat/README.md`.
## Dokumen and Memori & Arahan (7 Nov 2026)

- **Dokumen** (`#dokumen`, Rujukan): the repo's own Markdown (CLAUDE.md, every README, `rules/`, `ops/`, `docs/`, `.claude/skills/`,
  `supabase/**`), bundled at build time (`web/src/lib/repoDocsFiles.js`, `import.meta.glob` with `?raw`, one lazy chunk per file) and
  drawn with the chat's Markdown reader (no HTML passes through). `backup/`, `node_modules`, `dist` and files over 400 KB are never
  shown. `pages.yml` now rebuilds on any `**/*.md` push with the full history, so a merged change appears by itself and each file
  carries its last-commit date (`web/vite.repoDocs.js`). `repoDocs.test.mjs` fails when a .md file the rules accept is missed by the glob.
- **Memori & Arahan** (`#memori`, Dashboard, beside Sembang AI): `settings.ai_instructions` {text, updated_at} (max 4,000) and
  `settings.ai_memory` {search_chats, auto_memory} (both on by default; rows made by `supabase/070_ai_memory.sql`, since the browser
  can update a setting but never add one), plus list / add / edit / delete of the signed-in user's `semasa_chat_memory` notes
  (policy from 025). The chat sends the instructions after its own rules, never above them; `search_chats` adds the read-only
  `search_chats` tool (other threads, Telegram's included); off, the chat sees only the current thread and is told so.
- **Memory from chats**: `backend/semasa/memory_auto.py` (`memory.yml`, 00:35 MYT) reads only Wan's own messages of the last day,
  asks the AI team for at most 5 lasting facts or preferences, drops secrets, e-mail addresses and long numbers, skips near-repeats
  and the 40-note ceiling, and saves them with source `chat` (shown as "auto"). Its bookmark is `settings.memory_auto`.
- **Every Motion storyboard is approved before anything else is made** (Wan, 7 Nov 2026: "make sure all storyboard appear and approve before proceed for motion creation"; `supabase/071_motion_storyboard_review.sql`, `backend/semasa/motion_review.py`).
  - The worker writes the storyboard (an explainer's plan with each scene's shot; a template film's whole storyboard object), saves it in `semasa_motions.storyboard` (`{kind, plan | sb, note, written_at}`) and sets the film to **`review`**. Nothing past that point runs: no AI background, no picture, no voice, no render.
  - Wan sees every scene in the Motion tab (`MotionStoryboardReview.jsx`) and on Telegram (`✅ Luluskan` / `🔁 Tulis semula`; sent by the motion worker itself, with the Telegram run as the net, never twice: its own settings row `telegram_storyboards`, bug sweep 7 Nov 2026). Approve, approve with edits, or ask for a new one, all through `semasa_motion_storyboard_decide` (Telegram: `semasa_telegram_motion_decide`, as his own login), which stamps `storyboard_approved_at/_by` and sets `pending`.
  - After the approval the film is made from EXACTLY the saved storyboard, checked again with the same rules (`motion.approved_plan`, `motion_templates.validate_*`). An edit that breaks one goes back to `review` with the reason, never into a film. The outro is never editable.
  - The database holds the line too: 071's guard refuses any change INTO `done` without an approval, and clears an approval when the storyboard itself changes. An automatic retry keeps the approved storyboard; "Buat semula" asks for a new one; "Cuba lagi (storyboard sama)" carries a failed approved film on.
  - Before 071 is applied the film goes back to `waiting` with a note naming 071: never made without an approval. Tests: `tests/test_motion_review.py` (marked `storyboard_gate`); every other motion test runs through `conftest.storyboard_approved`, which plays Wan's Approve.

## Comic as a Design choice (17 Nov 2026)

- Wan, 16 to 17 Nov 2026: "remember the comic style so other model can use and render same based on topics / for comic style create
  multiples cartoon or comic style, and make it series like cartoon series / add comic as choice". Jana poster has a fourth kind,
  **Komik** (`components/ComicMaker.jsx`, `lib/comic.js`); the worker is `backend/semasa/comic_job.py` with `comic.py` (prompts,
  lettering, trim, frame), `comic_library.py` (styles and series) and `comic_writer.py` (the script and its checks).
- **A style is remembered as words.** `rules/comic.json` holds the built-in cartoon styles and series, read by the page and the
  worker alike. A style's `prompt` goes into every prompt verbatim, and its `lettering` when the picture maker writes the words; a
  character's `look` is repeated word for word in every episode. Wan's own are the settings row `comic` ({styles, series},
  supabase/085), merged over the file by id: the same id replaces a built-in one, a new id is added, and an entry that is not whole
  is left out. A cast is two people inside a comic, never a brand mascot.
- **A comic is a `slides` job** with `meta.design = "comic"` and its own block `meta.comic`, so the library, attach to a post, the
  publisher and the post's compliance scan treat it as any design (`meta.slides` holds the title and each panel's bubbles). No
  constraint changed.
- **The script** is four panels, one or two bubbles a panel, each person once a panel, a bubble at most `comic.MAX_CHARS`. Written
  from an idea under `design.COMMON` and the stream's voice, or typed. It is refused with the reason, before any picture is paid
  for, on a hard compliance flag over the title or a bubble, vague wording nothing pins down, Malay on LinkedIn, or (a written one
  only) a figure the brief never gave. A written script waits for Wan first unless he unticks it (`meta.comic.review`, stage
  `script`: a `done` row with no picture).
- **The words**: the picture maker draws the comic with its words, the picture reader Semasa already has (`llm.describe_image`,
  the reader pinned on the API page first) reads every bubble back, and they are compared after case, spaces and the spacing
  around punctuation are evened out. A difference is drawn once more; a second one, or no reader, falls back to wordless art and
  Semasa's own lettering, which is exact. `meta.comic.words` records the path and whether the words were checked, and the card
  shows it. Makers are tried in `comic_job.MAKERS` order (the two the 16 Nov sample proved first), not `IMAGE_PRIORITY`.
- **The frame** is Semasa's: the series and episode ("Siri <name> · Episod N"; the series' finished comics + 1, kept through a
  redraw), the title, the comic trimmed of the picture maker's stray border, the source. ws.regulab carries the logo and the
  website; LinkedIn carries no brand identity. Every line is fitted to its own area or the job is refused by name.
- An idea can ask for a comic as its post's one picture (`brief.format = "comic"`, `ideas.comic_job`): the script is written from
  the post's own words and no other picture is made.
## Sending failed channels again (16 Nov 2026)

- Wan: "move to new slot", after two films lost channels when their slot came (Instagram went out, TikTok / Threads / Facebook failed). A post can be **half sent**: `published.<channel>.status` is `sent` on some channels and `error` on others. Nothing is ever sent again by itself. **A person moving the post to a new slot is the instruction.**
- The rules (`backend/semasa/publisher.py`, tests `tests/test_resend.py`):
  - a record the network has **settled** (`sent`, `error`) holds nothing in the scheduler's queue, so it never blocks a move (`moved_since_handed_over`); a record still pending (scheduled, sending, unconfirmed) does;
  - `stale_failures`: a channel whose record is `error` for a moment **other than the slot the post has now** is handed over again for the new slot. The failed record stays until its replacement is in hand (the new record carries `replaces`), so a blocked, late or interrupted run changes nothing;
  - an `error` for the slot the post **still has** is never retried, and a `sent` channel is never looked at: no channel goes out twice;
  - the loop reads an approved post, and a `scheduled` one **only** when it has a stale failure. Such a post ranks below posts already scheduled on the new slot (`guard.rank(p, resend)`), so one post to a slot still holds; it ends `posted` once every channel is sent;
  - a record Zernio answers **404 "Post not found"** for, 20 minutes past its moment and in **every** login (`ZernioHub.gone`), is settled as an `error` with `lost: true` ("Zernio no longer holds this post and it was not sent"). A timeout, a 5xx or one unreadable login is never proof.
- The page: `web/src/lib/slots.js` (`canResend`, `resendChannels`, `moveCheck` → `resend`), `lib/resend.js` and `components/PostResend.jsx` (the box in the post editor: which channels failed, in the platform's words, and "Move and send again", which writes the date and slot only). The schedule map lets such a post be dragged. A scheduled post is never moved to a slot the publisher's next run (06:20, 11:20, 19:20) comes too late for.
- The database: `supabase/084_resend_failed_channels.sql`. The move is accepted when every record is settled and at least one failed; it is the ONE write a browser may make to a scheduled post (date, slot and the decision note), to a free slot still ahead; an approved post that moves goes back to draft and is approved again. Before 084 is run the page's move is refused and the box says to run it.
- The slot check tells a re-send that missed its new slot and a second failure at a new slot (an alert is per post, channel, kind **and slot**). The health report's advice is per case (`health.publish_advice`).
- MYRA's sheet read (`myra.fetch`) reads again after 20 s and 65 s when Google answers with its per-minute read quota or a rate limit; every other error is final at once.
