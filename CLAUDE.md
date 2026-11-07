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
