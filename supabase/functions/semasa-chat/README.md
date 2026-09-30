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

## What it enforces

- Caller must be signed in **and** pass `public.semasa_is_uploader()`. The project's public anon key is itself a valid
  JWT and the project is shared with another app, so a JWT check alone would let any of their users spend the key.
- Sends only user/assistant turns (last 30, 8,000 characters each). Pictures: up to 4 PNG/JPEG/WEBP/GIF, 3 MB each.
  Plain-text files: up to 3. PDFs and Word files are named in the message as "not read", never silently dropped.
- Errors carry the model's HTTP status and first 200 characters, never the key.

## Not proven yet

Whether `api.mireld.my` answers a Supabase Edge Function. It does not answer GitHub runners (19 Sep 2026) and does
answer the Composio sandbox. The **check** button is the test; if it says the model list could not be read and the
picture test failed with HTTP 0, Mireld is refusing this caller and the chat needs another route.
