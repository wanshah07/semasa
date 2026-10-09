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

## Use another gateway: Afiq's rootsys (9 Oct 2026)

The function talks to any OpenAI-compatible gateway. To move the chat, the Design reader and the FAQ bar to rootsys, set these
secrets (type the key into the dashboard or your own terminal, never into a chat) and deploy again:

```
supabase secrets set AI_API_KEY=<the rootsys key> AI_BASE_URL=https://rootsys.cloud/v1 AI_MODEL=kimi-k3 --project-ref mwaocnbgvbkhovktgods
```

- With `AI_API_KEY` set, `AI_*` win and `MIRELD_*` are ignored. `AI_BASE_URL` is then required, so the key can never be sent to
  Mireld's address; `MIRELD_MODEL` is ignored too, because a model id belongs to one gateway. To go back, `supabase secrets unset
  AI_API_KEY AI_BASE_URL AI_MODEL`.
- rootsys drops the system message, so for that host the instructions are also repeated at the top of the first user turn (the same
  fix the worker has had since 28 Sep). `AI_REPEAT_SYSTEM=1` or `0` forces it on or off for any gateway.
- Models that read a picture are what the Design reader and the FAQ bar need. rootsys marks `kimi-k3`, `glm-5.3-flashx`,
  `glm-5.3-flash`, `deepseek-v4.1-flash`, `minimax-m3` and `kimi-k2.7` as vision; with no `AI_MODEL` the function picks the first
  of those it lists (`kimi-k3`). That order is a guess from the names, not a measurement: press **Check the model** in the AI chat
  tab, which sends a red square and a test tool call, and pin the winner with `AI_MODEL`.
- The page names the gateway it is really using (`rootsys`, `Mireld`, or the host) in its notes and in the "reader did not answer" text.

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

## Streaming, answering again, attachments (`chat`, 1 Oct 2026, "almost similar with claude")

- `{action:"chat", stream:true}` answers as **Server-Sent Events**: `data: {"type":"start"}` then `{"type":"status","tool","detail"}` as
  a tool runs, `{"type":"delta","text"}` for every piece of the answer as the model writes it, and `{"type":"done", ...}` carrying the
  same fields as the one-piece answer (`text`, `thread_id`, `model`, `tools`, `memory_saved`). An error after the headers went out
  comes as `{"type":"error"}`. The page reads this with `fetch` and the person's own login token (`web/src/lib/chat.js streamChat`),
  can stop it (the answer that arrived stays on screen, marked *stopped*; the function still finishes and saves the whole answer, so a
  reload shows it in full), and falls back to the one-piece call when the function does not stream. Mireld's own stream dialect
  (OpenAI SSE, `delta.content` and `delta.tool_calls` pieces) is folded by `logic.js foldDelta`, tested in Node.
- `{action:"chat", regenerate:true, thread_id}` drops the thread's last answer and answers its last question again (attachments are
  not re-sent). The page's **Again** button.
- The system prompt is Wan's own brief: answer first, Markdown, Malaysian Malay or English as asked, never "consult a professional",
  no invented numbers, cite the instrument and entry. Answers are drawn as Markdown by `web/src/components/Markdown.jsx` from a
  reader that never passes HTML through (`web/src/lib/markdown.js`, tested), so a model cannot put markup into the page.
- Attachments: pictures, PDF (text pages as text, scanned pages as pictures), Word, Excel, CSV and text, read in the browser by the
  FAQ bar's readers and folded one attachment per file (`web/src/lib/chatFiles.js`). Limits: 6 pictures, 6 documents, 60,000
  characters each.
- Conversations are listed, renamed and deleted from the page's history panel straight through row-level security; the function
  is not involved.

## Slow first output (`faq_extract`, `design_clone`, `design_refine`, 2 Oct 2026)

Wan's screenshot of the Design tab: *"the reader did not answer (HTTP 500: Member first-output deadline)"*. Mireld gives each model a
deadline to START answering; a non-streamed call produces nothing until the whole answer is written, so a long layout (thousands of
tokens) can miss it. These three actions now **stream** the reader's answer (the first token arrives at once, and the pieces are
folded back into one text), and when the call still fails in a way another try could fix (a deadline, a timeout, any 5xx, a 429, an
empty answer), they ask **once more on the best other chat model Mireld lists** (70 s, then 50 s, inside the function's own limit).
A 400, 401, 403 or 404 is not retried. The error names the models tried and says what to do. `logic.js retryable` and `pickFallback`
decide this and are tested; the streaming itself is the same SSE fold the chat uses.

## What keeps it safe (1 Oct 2026, "check the security and the flow")

- **Who may call it**: a signed-in Semasa user, proved twice (the login token through `auth/v1/user`, then `semasa_is_uploader()`);
  the public anon key alone is refused. The gateway's JWT verification stays on.
- **How much**: a body over 40 MB is refused (413); per user, a window of 40 chat calls, 12 design reads, 20 FAQ reads and 10 checks
  in 10 minutes, then 429 with `retry-after` (`logic.js RATE`, `allow`). Attachments: 6 pictures of 4 MB, 6 documents of 60,000
  characters and 150,000 characters together.
- **What the model can reach**: `fetch_url` is https only, no logins, no odd ports, no IP literals, no internal names, no supabase
  host and never this project's own host, every resolved address checked and every redirect re-checked; `query_semasa` reads an
  allow-list of tables through the caller's own login with secret-looking columns dropped; `remember` writes only when Wan's own
  message asked. Everything a page, a search or a table returns is marked as untrusted data. One limit is honest to state: the
  address check and the fetch are two steps, so a name that changes its address between them (DNS rebinding) is not caught; the
  private-address refusal and the https-only rule are the defence in depth.
- **What reaches the page**: answers are Markdown drawn as React elements, never HTML; links only http(s)/mailto, opened with
  `noopener noreferrer`. The key never leaves the function.

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

## Rebuild a design from a reference (`design_clone`, 1 Oct 2026)

Wan: *"allow upload design, then ai render similarly, only context is different"*. He chose to **rebuild the reference as editable layers**
(not to have an image AI repaint it), and to **drop logos from other people's designs**. In the Design tab, once a reference is uploaded,
the switch **Rebuild it the same** sends it here with the target size, the stream and, if the bot is to write the words, the idea.

- The reader returns a **layout**, never a picture: background (colour or gradient), shapes, picture areas, and every text block with its
  place, size, colour, type class, weight, alignment and spacing, roles `eyebrow | headline | point | source | deco`. With an idea it also
  writes the new words for each block, under the same rules as a post (no CTA, no URL, no social source, no invented figure).
- `design.js` `cleanLayout` holds the answer to the rules: known kinds only, numbers clamped to the canvas, colours as `#rrggbb`, at most 40
  elements. **A logo, a brand mark, a person's face, a web address or a handle never becomes a layer**; they are listed in `removed` and shown.
- The page (`web/src/lib/designCloneSeed.js`) lays the layout out as Kanvas layers with the words: the reference's own place, size, colour and
  font for each block, shapes in its stacking order, gradients, picture areas (empty boxes, or the picture chosen in the form). No word of the
  reference is ever drawn; a block with no new words is left out. Extra points are spread evenly through the room the points had, never onto
  another block.
- Before it opens in Kanvas the words are checked against the post rules in a review step; a hard flag (a call to action, a URL) stops it opening.
- Poster and single card only (one picture). The AI reads the layout once; everything after is drawn in the browser without AI.
- What it cannot do in **Rebuilt layers** mode: copy a photograph or an illustration (the area stays an empty box for your own picture),
  reproduce a font it does not have (the nearest of Playfair Display, Poppins, Instrument Sans, Anton, JetBrains Mono and Caveat is used).

### Second pass (same day): "make sure almost 100% serupa", and "inspired ... generate"

- **On the reference picture (closest)**, the default under *Rebuild it the same*: the reference picture itself becomes the background
  layer (the canvas takes the reference's own shape, shorter side 1080), so every shape, gradient, texture and photograph is the
  original's own pixels. The old words, and the logo and face boxes the reader listed, go under **patches** in the colour found behind
  them, read off the picture in the browser (`web/src/lib/designPatch.js`: the median of a thin ring above and below the box, drawn as a
  top-to-bottom gradient so it blends on a gradient or a scrim); only the new words are drawn on top. A patch on a photograph is said on
  screen, and is a layer, so it can be moved or deleted in Kanvas. Nothing leaves the browser for this step.
- **A preview, then a refine pass.** The review step now draws the rebuild (`web/src/lib/kanvasBuild.js` `renderSeedPreview`, the same
  builder Kanvas uses, so what is shown is what opens) and sends the reference and the drawing side by side to `design_refine`; the
  reader answers with the layout corrected (places, sizes, colours, fonts, alignment), the words untouched (`design.js keepWords` copies
  them back whatever the reader did). One pass runs by itself; **Refine again** runs more, up to four.
- **Make it in Kanvas (now)** under *Inspired*: `design_clone` with `mode: "inspire"` asks for an ORIGINAL composition in the reference's
  visual language (palette, type, rhythm, mood), never its arrangement, and opens it in Kanvas at once with no worker queue. The worker
  route (*Make the design*) is unchanged beside it.
- The reader's contract also grew `behind` (the colour behind each block), `lines`, `palette` and the boxes of logos and faces
  (`layout.covers`), and asks for TIGHT boxes measured against the edges.

## Choosing the model (1 Oct 2026)

Wan: *"we allow to choose AI model and you will suggest default AI that is the best"*. The chat page has a **Model AI** picker.

- `{action:"models"}` returns the chat models Mireld lists (embedding, speech and image models are left out), best default first, each
  with a one-line note from its name alone (never a price or a speed). Mireld's list is read once and kept five minutes.
- **The default is Auto**: `MIRELD_MODEL` if you set it, else the first of `claude-sonnet-5.5`, `claude-opus-5.5`, `claude-sonnet-5`,
  `claude-fable-5.1`, `claude-haiku-4.5` that Mireld lists (`MODEL_PREFERENCE` in `logic.js`). **Sonnet 5.5** is the recommended default:
  it is the model the chat was proven on (reads pictures, calls tools, writes Malay), and it answers quickly. **Opus** is the one to pick
  for a hard clause or a long document: more thorough, slower, dearer. Haiku is the lightest.
- The choice is kept in the browser (`semasa.chat.model`); Auto sends no model, so the default can improve without anyone changing a setting.
- `chat` and `check` take `{model}`. It is used only if Mireld lists it (or the list cannot be read and it is a plain id); otherwise the
  default answers and the page says so. **Test** is the existing check button, now run on the model picked: it proves that model reads a
  picture and calls tools, which is how an unfamiliar model earns a place.
- The picker needs this function deployed; an older function simply hides it.

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
