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

## Documents (11 Oct 2026)
The bot also **issues documents** from what the brain and the FAQ hold, in Bahasa Malaysia, English or both, as Word files.
```
Otak tab: tick entries, "Buat dokumen" ┐
FAQ tab: "Dokumen" (the questions shown) ┴► semasa_brain_docs row, status pending ──(database → 'brain_doc_pending')──►
brain-docs.yml → python -m semasa.brain_docs → result {ms, en} → the page builds the .docx (web/src/lib/docxWrite.js)
```
- **Types** (`rules/documents.json`, the one file the worker and the page read): FAQ document, work instruction, SOP gap review,
  SOP draft, fact extraction, reference comparison A/B, gaps + follow-up e-mail, NCR draft + corrective action, risk register,
  meeting minutes, manual amendment list, AI use-case map, reusable prompt, and *your own structure* (one section per line, a
  `|` makes a table). A type is its sections, their headings and columns in both languages; add one there and in the SQL check list
  (`test_the_sql_check_list_is_the_rules_file_list` and `documents.test.mjs` fail if the lists drift).
- **What the AI may not do, and where that is enforced** (not only asked for in the prompt):
  - The status line is always *DRAF UNTUK SEMAKAN / DRAFT FOR REVIEW*, the document number, version, reviewer, approver and
    signature are the marker, and the header, footer and disclaimer are written by the renderer, never by the AI.
  - A table has exactly its columns; numbering and fixed cells (a gap's status *Belum disahkan*) are the renderer's; an empty or
    "n/a" cell becomes the marker; a missing section is the marker and is listed under *to confirm*.
  - A cell that must come from the material (an owner, a target date, a version, a name) is kept **only if the material contains it
    as a whole word or phrase**, otherwise it becomes the marker.
  - Every figure, date and clause reference in the draft that the material does not contain is listed under *Source check*.
  - Wording that reads as a halal / compliance / approval decision is listed under *Check: status or approval wording*, for a person.
  - The material is data, never instructions (`test_an_instruction_inside_the_material_is_not_followed…`).
- **Material**: the entries or FAQs ticked, facts pasted, and Word / Excel / CSV / text files read in the browser, numbered
  *Bahan 1, 2, …* so the draft can cite where a statement came from. The AI reads the first 40,000 characters; the page warns when
  there is more, and a draft made from cut material says so. A PDF or a picture is dropped in the brain first, then its entries are
  ticked (the page reads words only).
- **Both languages** = two files written from the same material, each by its own AI call; a retry asks only for the language still
  missing. **Draft again** clears the result and asks afresh.
- **Not done, said plainly**: the Word file is built fresh from the type's structure; it does **not** fill in a company's own
  template file in place, so its fonts, header and footer are not carried over (give your own structure instead, or paste the
  result into your template). Dates the AI writes in another form than the material's (05/10/2026 for 5 Oktober 2026) are listed
  under *Source check* or, in a must-come-from-the-material column, replaced by the marker: safe, a little strict.
- Set up once: run `supabase/037_brain_docs.sql` (prints `1 | 4 | 1 | 1`), then `supabase/038_doc_templates.sql` (prints `1 | 4 | 1 | 1 | 2 | 1`); the `Dokumen AI` workflow uses the same secrets and
  variables as the Otak AI one and needs no Chromium.

Files: `supabase/037_brain_docs.sql` · `rules/documents.json` · `backend/semasa/brain_docs.py` (+ `tests/test_brain_docs.py`, 27)
· `.github/workflows/brain-docs.yml` · `web/src/lib/documents.js` · `web/src/lib/docxWrite.js` (+ `web/documents.test.mjs`, 16)
· `web/src/components/DocumentModal.jsx` · `web/src/components/DocumentsPanel.jsx`.

### Your own templates (11 Oct 2026)
```
Otak tab → Templat dokumen → "Tambah rujukan": a Word / Excel / CSV / text file, read in the browser (web/src/lib/templateOutline.js)
  → semasa_doc_templates row, status pending ──(database → 'brain_doc_pending')──► brain-docs.yml → process_templates
  → structure (sections, kinds, table columns, BM + EN titles) + warnings → Edit / Guna → a document request carrying a copy of it
```
- **Reading**: a Word form keeps its shape for the AI: a paragraph in a heading style, or short and all bold, or short and all
  capitals, is `# Heading`; a table is `TABLE:` and `| a | b |` rows (first row the header); other paragraphs, such as the form's own
  instruction text, stay as lines. Excel: each sheet is a heading and a table. CSV: a table. Text and Markdown as they are. The marks
  are a hint, never a rule. PDF, pictures and old .doc/.xls are refused by name with what to do.
- **The AI makes the template, and the code checks it** (`clean_sections`, `unmatched`): the reference's own titles word for word, the
  translation beside each; a kind outside paragraphs / bullets / table becomes text; a table needs two columns; a first column called
  No. or Bil. is numbered by the renderer; a column that names an owner, date, version, signature or approver is kept only if the
  material has it (the same rule as the built-in types); every title the reference does not contain is listed under *Not found in the
  reference*, for you to check or edit. The document-control block (number, version, dates, prepared, reviewed, approved,
  signature), headers and footers are left out because the renderer writes them.
- **A request keeps a copy of the template** (`template_snapshot`), so *Draft again* works after the template is edited or deleted.
  Editing a template changes only documents made afterwards.
- **Not done, said plainly**: the reference file is not stored (only its words) and the Word file is built from the structure, so the
  template's fonts, header, footer and logo are not carried over. Doing that means keeping the file and building the output inside it:
  a separate change, with a private bucket for the file.
- Files: `supabase/038_doc_templates.sql` · `web/src/lib/templateOutline.js` · `web/src/components/TemplateModal.jsx` ·
  `web/src/components/TemplatePanel.jsx` · `web/test-fixtures/template.docx` (made with python-docx).
