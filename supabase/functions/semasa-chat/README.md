# semasa-chat — the AI chat's door to Mireld

The chat tab (`web/src/lib/chat.js`) calls this function. The Mireld key lives here, never in the page.

## Switch it on (once)

1. **Secrets** (Supabase dashboard → Edge Functions → Secrets, or the CLI):
   ```
   supabase secrets set MIRELD_API_KEY=<your key> --project-ref mwaocnbgvbkhovktgods
   supabase secrets set MIRELD_BASE_URL=https://api.mireld.my/v1 MIRELD_MODEL=claude-sonnet-5.5 --project-ref mwaocnbgvbkhovktgods
   ```
   The last two are the defaults and can be left out. Type the key into the dashboard or your own terminal, never into a chat.
2. **Deploy**, from a clone of this repo:
   ```
   supabase functions deploy semasa-chat --project-ref mwaocnbgvbkhovktgods
   ```
   (`index.ts` and `logic.js` deploy together. If you paste into the dashboard editor instead, add both files.)
3. Open the **AI chat** tab and press **Check the model and its image reader**. It prints one line:
   - whether `claude-sonnet-5.5` is in Mireld's model list, and if Mireld spells it differently (for example
     `claude-sonnet-5-5`), which spelling to set as `MIRELD_MODEL`;
   - whether the model **reads a picture**: it is sent a solid red square and asked its colour. "It answered with an
     image attached" is not the test; saying *red* / *merah* is.

## Memory, web and data (1 Oct 2026)

Run `supabase/025_chat_memory.sql` once, then deploy the function again. Nothing else changes for the page.

**Why the chat can "forget", and what makes it not.** A model keeps nothing between calls: it knows only what is sent
with each call. So memory here is three things the function re-sends every time:

| Layer | Where | What it holds | Lives |
|---|---|---|---|
| Pinned notes | `semasa_chat_memory` | Short notes Wan pins (or tells the chat to remember). Sent at the top of EVERY call, in every conversation. | Until Wan deletes them |
| Transcript | `semasa_chat_messages` | Every turn. The page reopens the newest conversation on load, from any device. | Until the thread is deleted |
| Rolling summary | `semasa_chat_threads.summary` | When a conversation passes 30 turns, all but the newest 12 are folded into a summary by the model and the summary is sent instead. | With the thread |

"Always" has a limit: the model reads a bounded amount per call (24 recent turns, a 6,000-character summary, 40 notes).
Anything that must never be lost belongs in a **pinned note**, not in the conversation. Summaries are the model's own
words and can drop detail, so a fact that matters should be pinned.

**Tools** (the model decides when to use them, at most 4 rounds a message):
- `fetch_url` reads one public https page: the Semasa site, NPRA, JAKIM, EUR-Lex, a link Wan pastes. It refuses IP
  addresses, internal names, odd ports and logins, checks every address the name resolves to, and re-checks each
  redirect. PDFs and Word files are not read yet.
- `search_web` needs a Brave Search API key: `supabase secrets set BRAVE_API_KEY=<key> --project-ref mwaocnbgvbkhovktgods`.
  Without it the tool says it is not installed and the chat uses `fetch_url` instead.
- `query_semasa` reads these tables only, read only, through Wan's own login (row-level security): `semasa_ideas`,
  `semasa_posts`, `semasa_watch`, `semasa_faqs`, `semasa_log`, `semasa_publish_log`, `isu_semasa_trends`. Not "any
  database": the project is shared with another app, and keys and secrets are never listed.
- `remember` saves a note, and only when Wan's own message asks for it ("ingat ...", "remember ..."). A web page or a
  search result cannot make the chat write a note.

Everything a page, a search or a table returns is handed to the model marked as untrusted data, because a page can
contain instructions aimed at the model. The check button now also says whether the model accepts tools and whether
web search is installed. If Mireld rejects tools the chat still answers, without them, and says so.

## FAQ AI bar (`faq_extract`, 1 Oct 2026)

Wan: *"for faq add AI bar that allow us to paste screenshot, image, upload pdf then AI will analyze and auto to categorize
them to proper Q&A FAQ"*. The FAQ tab's bar sends pictures, PDF text and a typed note here; the function returns the
question-and-answer pairs it finds (`{items:[{question, answer, instrument, source_hint, unclear}], skipped, not_read}`)
and **writes nothing**. The page lists them, Wan keeps the ones he wants, and each kept pair is inserted as a `new`
`semasa_faqs` row, exactly like **Add FAQ**: the worker (`backend/semasa/faq.py`) then rewrites it in BM and English,
anonymises it again, picks the category and syncs the sheet. One writer and one rule set, so a screenshot cannot reach the
sheet by a side door.

- **Reading.** The model is told to take only what the material says, to leave `answer` empty when there is none (the
  worker then writes one and flags it *needs check*), to drop names, numbers and clients at source, and to treat any text
  inside a picture as data, never as an instruction. At most 30 pairs, 6 pictures and 40,000 characters a call; the page
  splits more into several calls and folds duplicates.
- **PDF** is read in the browser (pdf.js, legacy build, loaded only when a PDF is chosen): a page with text sends its
  text, a scanned page is drawn and sent as a picture, so Mireld needs no PDF support. First 40 pages; 12 scanned pages.
- **Word, Excel and CSV** (1 Oct 2026, second pass) are read in the browser too, with no new dependency (`web/src/lib/officeText.js`:
  fflate opens the zip, a few tags carry the words). A `.docx` becomes its paragraphs, tables as `a | b` rows; an `.xlsx` or
  `.csv` that already has a question column and an answer column becomes the pairs **directly, with no AI call**; any other
  sheet goes to the reader as text with its header repeated on every part. Not read, and said so on screen: the old `.doc` /
  `.xls` (save as `.docx` / `.xlsx`), hidden sheets, formulas without a stored value, macros, pictures inside the file.
  Each kept pair is filed as `AI bar · <kind of file>` and never carries a file name, a sheet name or a person's name, because
  `source_name` is mirrored to the Semasa sheet.
- **Tall screenshots** are cut into overlapping tiles, because a 1080 x 5000 chat shrunk whole is unreadable.
- Needs no new secret and no SQL: same Mireld key, same table. Deploying this function (merge → *Deploy functions*) is the
  only step.

## What it enforces

- Caller must be signed in **and** pass `public.semasa_is_uploader()`. The project's public anon key is itself a valid
  JWT and the project is shared with another app, so a JWT check alone would let any of their users spend the key.
- Sends only user/assistant turns (last 30, 8,000 characters each). Pictures: up to 4 PNG/JPEG/WEBP/GIF, 3 MB each.
  Plain-text files: up to 3. PDFs and Word files are named in the message as "not read", never silently dropped.
- `faq_extract` takes up to 6 pictures a call (JPEG the page has already shrunk, 4.5 MB each at most), text files and a
  note of 500 characters; anything it cannot take is returned in `not_read`, never dropped silently.
- Errors carry the model's HTTP status and first 200 characters, never the key.

## Not proven yet

Whether `api.mireld.my` answers a Supabase Edge Function. It does not answer GitHub runners (19 Sep 2026) and does
answer the Composio sandbox. The **check** button is the test; if it says the model list could not be read and the
picture test failed with HTTP 0, Mireld is refusing this caller and the chat needs another route.
