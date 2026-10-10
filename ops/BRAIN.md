# Otak AI · drop anything in, the AI files it (10 Oct 2026)

Wan: *"create 1 segment for AI, I will upload text, photo, link social media, scrape etc … the model will auto read and be
like note, faq and will be categorize like skills, prompt etc"*.

## How it flows
```
Otak tab (Create group)   text · screenshot (paste or drop) · picture · PDF · Word / Excel / CSV / text file
                          · a link · a page to scrape        (+ optional "make it a FAQ/skill/…" and a note for the AI)
        │  picture/PDF → semasa-reference bucket (<uid>/…) ; Word/Excel/CSV/text → the words are read in the browser
        ▼
semasa_brain_inbox row, status pending ──(database → repository_dispatch 'brain_pending')──► brain.yml → python -m semasa.brain
        1. GATHER   text as it is · picture → vision model · PDF → its text layer (pypdf) · link → browser-identity GET,
                    a JavaScript page or a "scrape" row through Playwright, the links on a scraped page collected too
        2. FILE     the AI gateway (Afiq's rootsys, Mireld as the backup, the model from the AI tab) returns entries:
                    note · faq · skill · prompt · reference · checklist, each with category + 2–6 tags + a confidence
        3. WRITE    semasa_brain_entries, a title already held is skipped; the inbox row says done (n entries, which model)
                    · needs_text (what to do instead) · pending again (transient, up to 3 tries) · error (the reason)
        ▼
Otak tab: search · kind chips · category · tag cloud · pin · copy · edit · delete · .md per entry
          · Export = one zip, skills as <slug>/SKILL.md (loadable by another assistant), the rest by kind
```

## What it will not do, said plainly
- **A social post behind a login is not read.** Instagram, Facebook, Threads, TikTok, LinkedIn and X show a post to a signed-in
  browser only. The worker reads whatever the link's public preview carries; when that is too thin the row becomes
  `needs_text` and says *paste the caption or upload a screenshot*. Nothing is invented from a link it could not read, and
  nothing here logs in as Wan. A screenshot dropped on the box is read by the vision model and works for any post.
- **A scanned PDF has no text layer**: the row says so; upload its pages as pictures.
- **Old Word/Excel/PowerPoint formats** (.doc, .xls, .ppt) are refused by name with how to convert them.
- **What was dropped in is data, never instructions.** The prompt says so; a page that tells the AI to ignore its rules is
  filed as a page that says so (`test_the_material_is_marked_as_data…`).
- **A re-read never overwrites what Wan edited** (`edited = true`); it replaces only what the AI filed from that source last time.
- **Nothing here posts, publishes or deletes anything outside the brain.** Not a Studio idea, not a post.

## Set up once
1. Supabase SQL editor (KPI project) → run `supabase/036_brain.sql` (prints `2 | 8 | 1 | 1`; run twice is harmless).
2. GitHub → the `Otak AI` workflow uses the secrets and variables the other workers already use (`SUPABASE_*`, `LLM_*`;
   `VISION_MODEL` must be a model that reads pictures). Nothing new to add. It installs Chromium for scrape pages.
3. Settings row `brain` (`semasa_settings`): `categories` (editable on the tab with the **Kategori** button; `lain` is always
   kept), `per_run` (15 inbox items a run), `max_entries` (10 entries an item), `language` (`ms` or `en`).

## Files
`supabase/036_brain.sql` · `backend/semasa/brain.py` (+ `tests/test_brain.py`, 18) · `.github/workflows/brain.yml`
· `web/src/pages/BrainTab.jsx` · `web/src/lib/brain.js` (+ `web/brain.test.mjs`, 16) · `web/src/lib/brainFiles.js`
