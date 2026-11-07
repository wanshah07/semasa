# Gemini keys (Wan, 6 Nov 2026)

Wan can add any number of Google AI Studio keys on the **API tab → Gemini keys (Wanshah 4)**. Semasa picks the key itself, the way
it picks a ChatGPT login or an AI-team robot. Run `supabase/061_gemini_keys.sql` once first.

## Add a key
1. aistudio.google.com → Get API key → copy it.
2. API tab → **Gemini keys**: type an optional name, paste the key, **Add**. The key is stored in `semasa_gemini_keys`, which no page
   policy can read: the page only shows a hint (`…last4`), a status and the last error, never the key. Up to 10 keys; a repeated key
   is not added twice.
3. Switch a key off, rename it or delete it (two clicks) from the same card.

## How a key is picked (`backend/semasa/gemini_keys.py`)
Usable = switched on, not refused by Google (`bad`), not resting. Tried least recently used first, so the load and the free quota
spread over all keys. A key that answered in the last ten minutes is used without another question; any other gets a five-token
question first. A failure marks the key and the next is tried (up to three in one decision):

| Answer | Mark | Rests |
|---|---|---|
| 429 / quota / rate limit | `limited` | 30 minutes |
| 400, 401, 403 with "API key not valid" etc. | `bad` | until Wan switches it on again |
| anything else (5xx, timeout) | `limited` (retry) | 2 minutes |

## What Gemini does
* **Motion scene pictures**, after ChatGPT (or alone when ChatGPT is not connected), per scene: `gemini_images.Drawer` calls
  `generateContent` on the image model. If ChatGPT is limited or refused part-way, Gemini draws the rest. A scene neither can draw keeps
  its Unsplash photo. Note on the film: "Pictures: N of M scenes drawn (ChatGPT a, Gemini b)".
* **The AI team's fourth robot (W4, Wanshah 4)** for the jobs ticked on the card. **Default: Motion and the idea writer only.** Otak AI,
  receipts, billing, CRM and scrapes (job `reader`) never reach Gemini unless Wan ticks "Every other job", because a free key may let
  Google use what it is sent. Use paid-tier keys if that is ever ticked.

## Not yet proved against Google
The request shapes follow Google's published API (OpenAI-compatible `/v1beta/openai` for text, native `generateContent` with
`x-goog-api-key` for pictures) and were written without a key to try them on. The code steps down on a 400 (no aspect ratio, then
text-and-image) and on a 404 searches the key's own model list for an image model. The first real film is the proof; a failure shows
in the key's last error and the film's pictures note.
