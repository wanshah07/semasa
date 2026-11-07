# Motion pipeline (Wan, 7 Nov 2026)

`Scrape > Idea > Motion (storyboard) > Motion (Picture) > Motion`

| Stage (`semasa_motions.stage`, 063) | What happens | Who does it |
|---|---|---|
| `storyboard` | the script (4 scenes, hook built on one of the 25 shapes) and, when a picture maker is ready, a SHOT for every scene | the film's writer (AI team) writes the script; **ChatGPT, then Gemini, then the film's writer** writes the shots (`motion_storyboard.py`) |
| `pictures` | one picture per scene from its shot | **ChatGPT, then Gemini, then Cloudflare Workers AI** per scene; a maker whose allowance is used up or login refused is skipped for the rest of the film |
| `film` | voice, layout, check, render, upload | the worker |
| `done` | finished | |

The **status** (waiting / pending / working / done / error) is unchanged: the trigger, the queue and the page read it. `stage` only
says what a working film is doing, and the Motion tab shows it as three steps beside the status, with the planned shots under
"Storyboard". A film waiting to run again after a failure is in no stage.

## Pictures
* **ChatGPT**: Wan's login (Motion tab). **Gemini**: his key pool (API tab), model Auto. **Cloudflare**: the FLUX models on Workers AI
  with the same credentials the post images use (GitHub secrets `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, or the page's image
  slot): nothing new to set up. It draws a square picture; a scene crops it to the frame. The free 10,000 neurons a day reset at 08:00 MYT.
* The report line reads `Pictures: 4 of 6 scenes drawn (ChatGPT 2, Gemini 1, Cloudflare 1)`.

## Storyboard
Every writer gets the same rules: the picture illustrates and is never evidence (no words, logos, packaging, faces, before-and-after,
cure or warning imagery). A shot that breaks them is dropped, and a scene without a shot keeps the template request. The shots are
kept on the scenes and on the row's `script`. ChatGPT's text goes through the same login that draws (`Login.write`): not verified
against OpenAI until the first real film.
