# ChatGPT pictures for Motion (Wan, 5 Nov 2026)

Motion draws one picture per scene of a film's storyboard through Wan's ChatGPT login, in the film's own style. A scene whose
picture cannot be drawn keeps its Unsplash photo (or none): the film is always made.

## Connect (once): a link and a one-time code (059)
1. Motion tab, **ChatGPT pictures for every scene**, press **Log in with ChatGPT**.
2. About a minute later the card shows a code and the link `auth.openai.com/codex/device`. Open the link, sign in with ChatGPT and
   type the code. The card copies it for you.
3. The card links itself when you approve; nothing to paste. The code lives 15 minutes; **New code** replaces it, **Cancel**
   stops. After 15 minutes the card says it expired and offers a new one.

How: the page calls `semasa_chatgpt_device_start()`, the database wakes the **ChatGPT login** workflow (repository_dispatch
`chatgpt_login`, the same Vault token as 042 and 057), `semasa.chatgpt_device` gets the code from OpenAI (the Codex CLI's own
`codex login --device-auth` endpoints), writes it on the row, polls every 5 s and, on approval, saves the tokens in the row 058
keeps. A browser page cannot call auth.openai.com, which is why a run does it. The page never sees a token or the private device
id. The first minute is the workflow starting; a request nobody picks up for 2.5 minutes shows "The worker has not started".

### Or paste auth.json (058)
1. On your own computer run `codex login` and choose **Sign in with ChatGPT**.
2. Open `~/.codex/auth.json` and copy all of it.
3. Same card, **Or paste auth.json**, paste it, **Connect ChatGPT**.

`supabase/058_chatgpt_login.sql` must have been run once. The tokens are kept in `semasa_chatgpt_auth`, which no page policy can
read; the page only ever sees a status. Only the worker (service role) reads them. An API key sitting beside the tokens in the
file is dropped in the browser and never sent.

## What happens in a film
`motion.process` calls `motion_gpt_images.draw_scenes` right after the Unsplash photos are assigned:

* every scene except the closing card, at most **Most pictures a film** (default 6, up to 8) within an 8-minute budget;
* the prompt per scene = its heading, lines and narration, the film's topic, the design look (Bright Editorial or Continuous
  Line), the palette and ambient colour, the platform's tone (ws.regulab or LinkedIn) and the chosen style repo's name;
* every prompt forbids words, logos, packaging, recognisable people, before-and-after and cure imagery: the picture is
  illustration, never evidence;
* the frame follows the film (9:16, 1:1, 16:9);
* the picture becomes that scene's own `photo` (it replaces the Unsplash photo and the pair partner), so the style chooser frames
  it like any photograph. The report and credits list only the photos some scene still shows.

The film's report says `ChatGPT pictures: N of M scenes drawn` and why any scene was skipped. A used-up allowance or a refused
login stops the remaining scenes of that film at once.

## Keeping the login alive
`semasa.chatgpt_login.Login` refreshes the access token when it has less than 5 minutes left and saves the new pair at once (the
refresh token is single-use). Two runs refreshing together: the loser reloads the row and uses what the winner saved. The
6-hourly API check (and one run when a new login is saved) refreshes it for real: ChatGPT accepting that refresh shows as
*Login accepted, no picture yet* (`checked_at`); a picture actually drawn in a film shows as *Working* (`last_ok_at`); a refusal
or a failed picture shows the error. If ChatGPT refuses the login, log in again and paste a new `auth.json`.

## What this is not
It is OpenAI's own first-party Codex login (public client `app_EMoamEEZ73f0CkXaXp7hrann`, endpoint
`chatgpt.com/backend-api/codex/responses` with the hosted `image_generation` tool), not an app registered by Semasa and not an
API. OpenAI can change or limit it without notice, and pictures count against Wan's ChatGPT plan. The first real film is the
proof: this was built and tested against fake ChatGPT replies, not against the live service.

Switch it off, change the model (default `gpt-5`) or the picture count from the card; **Disconnect** deletes the tokens.
