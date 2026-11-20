# Import video: sending Semasa a finished MP4

For Nous Hermes, Nexabot, huashu-motion or any agent that makes a video outside Semasa. Semasa checks the file and the caption and
makes a **draft** post on the next free slot. It never approves, schedules or posts: Wan's Approve click (page or Telegram) is the
only gate. After he approves, the publisher posts it as it posts any film.

## Get a key

Wan makes it in Semasa: **Video → Motion → Import video from outside → Make a key**. The key (`smi_…`) is shown once. Only its
sha256 is stored, so a lost key is replaced, never recovered. A key can be revoked at any time. The address is shown on the same card:
`https://<project>.supabase.co/functions/v1/semasa-import-video`.

## Request

`POST`, header `Authorization: Bearer smi_…`. Three ways to send the file:

| Way | Body | Limit |
| --- | --- | --- |
| multipart (preferred) | form field `file` (the MP4) plus option fields | 50 MB |
| raw | `Content-Type: video/mp4`, the bytes; options in the query string, key in an `Idempotency-Key` header | 50 MB |
| JSON | `{"video_url": "https://…"}` (public https, fetched by the worker) or `{"video_base64": "…"}` | link: 50 MB; base64: 15 MiB |

50 MB is the bucket's own ceiling (`semasa-generated`, supabase/003). The Edge runtime has 256 MB of memory and a 150 s wall clock on
the free plan, which a 50 MB upload sits inside. Larger files: send `video_url`, or shorten the film.

Options (all optional):

| Field | Meaning |
| --- | --- |
| `title` | up to 160 characters; the post's hook and the picture's alt text. Default: the caption's first line |
| `caption` | text for every channel, or an object `{"instagram": "…", "facebook": "…", "threads": "…"}` (in a multipart form, which carries text only, send that object as a JSON string: the worker reads it). Never altered or shortened. A caption that breaks a rule still makes the draft, with the blocking flags on it for Wan to fix in the page. **None at all and a `title`: Semasa writes one, see "No caption sent"** |
| `lang` | `bm` (default for `regulab`) or `en` (the only choice for `linkedin`) |
| `stream` | `regulab` (default: Instagram, Facebook, Threads) or `linkedin` |
| `channels` | a subset of the stream's channels. Default: all of them |
| `date` + `slot` | `YYYY-MM-DD` and `HH:MM` (Malaysia time), together, one of the stream's slots, free and ahead. Default: the next free slot |
| `source` | free text, e.g. `hermes`; kept on the film and shown on the card |
| `idempotency_key` | up to 128 characters of `A-Z a-z 0-9 . _ : -`. The same key from the same token returns the first import and never makes a second |

## Answer

`202 {"ok": true, "import_id": "…", "status": "received"}`. The same `idempotency_key` again: `200` with the first import and
`"duplicate": true`.

| Status | `error` | Meaning |
| --- | --- | --- |
| 401 | `bad_token` | missing, wrong or revoked key |
| 409 | `idempotency_conflict` | the key was used for a different video or caption |
| 413 | `too_big` | over 50 MB (JSON base64: 15 MiB) |
| 415 | `not_mp4` | no `ftyp` header, or a link that is a web page |
| 422 | `bad_stream`, `bad_lang`, `bad_channels`, `bad_slot`, `bad_url`, `bad_source`, … | a field is wrong; `message` says which |
| 429 | `rate_limited` | more than 20 imports an hour from this key (`settings.video_import.max_per_hour`) |

`received` means stored, not yet checked. The Motion worker checks it within minutes (it is woken by the new row; the hourly run is the
net). It ends as `done` (a draft post exists) or `error` with a sentence saying why; only a bad **file** ends as `error`. The card in
Semasa shows both. A refused file is deleted from storage. To try again after a refusal, fix the video and send it with a **new**
`idempotency_key`.

## What the worker checks

- A bad **file** (not an MP4, no picture, too long or too big, a bad link) is the only thing that ends the import as `error`.
- ffprobe reads it as a video with a picture track and a length; MP4/MOV container.
- Length at most **90 s** (`video.MAX_CLIP`) and posted size at most **48 MB** (`video.MAX_OUT_BYTES`), the repo's own limits for
  every channel. A file that is not already H.264 + AAC (or silent) in yuv420p, or is over 48 MB, gets the same platform copy a
  Motion film gets (`motion.social_copy`); if it is still too big it is refused.
- The caption and title go through the compliance scan of the chosen stream: no CTA, no ws.regulab website in a ws.regulab
  caption, no promise of approval, no vague wording, no Bahasa Indonesia, LinkedIn in English, Threads at most 500 characters a post. A blocking
  flag does **not** refuse the import (Wan, 17 Nov 2026): the draft is made anyway with `hard_flags` > 0, the flags listed, and the
  import's note says "N blocking flag(s) to fix". Wan fixes the caption in the page; Approve stays blocked while a hard flag remains.
  A warning (for example a plain link) goes on the draft too. The draft is never approved.
- A landscape film on ws.regulab only warns: it will not show as a Reel.
- **Decision of Wan's (17 Nov 2026): the branded-cover rule for Instagram films is OFF for imports.** The rule
  (`publisher.instagram_cover_gap`) applies to films with `meta.flow == "motion"`; an import's media row has `flow == "import"`, so an
  imported film can go to Instagram without Semasa's cover. The film was not made by Semasa and a cover cannot be added to someone
  else's film. Wan still sees the film before he approves.

## No caption sent: Semasa writes one from the title (17 Nov 2026)

When a `title` came and no `caption` (string or object), the worker writes a caption for each channel with the Motion caption writer
(`motion_captions.write`, the one that writes a film's captions), so the draft is not left with blocking "no caption" flags.

- **The brief is only what the sender gave**: the title (the prompt, for a Nexabot film) and the `source`, which the writer is told
  not to name. No scene, no script, no idea, no search. The writer is told to describe what the picture shows in two or three
  warm, plain sentences, and never to bring in a number, name, place, date, regulation, source or claim the title does not already
  contain. Language and voice follow the draft: Malaysian Malay, casual brand voice, for `regulab`; English for `linkedin`;
  each platform's own length and hashtag count (`rules/compliance.json`); no call to action, no ws.regulab URL, no "follow for more".
- **It is checked, never trusted.** A written caption is refused (that channel gets the plain caption) when it asks people to follow,
  sends the reader away to look something up, states a number the title does not have, or names a rule, body or guarantee
  (NPRA, JAKIM, halal, "dijamin", "safe", "clinical" and the like) that the title does not. Then the whole set goes through the
  same compliance scan as a sent caption; if a blocking flag is still there, every channel gets the **plain caption**: the title as
  one sentence, fitted to the platform, nothing added. The same plain caption stands in when no writer is available or it fails. Wan
  is flagged only for what still blocks.
- **The draft says so**: a warning flag ("Semasa wrote this caption from the title only: read it before approving"), a `decisions`
  line, the import's `note` and the Telegram message. It is a DRAFT like any import; nothing is approved. Wan reads the caption,
  edits it if he likes, then approves.
- **A caption the sender gave is never touched**, and the writer is not asked. No title and no caption is the old draft with the
  "no caption" blocking flag.

## An import whose draft is gone

`video_import.recover_missing_drafts`, called from the same Motion step as the import itself, looks at imports that are `done`, younger
than 7 days, and whose draft post no longer exists (deleted in the page: the import's `post_id` and the film's `queued_post_id` were set
to null, and no post carries the film's media). It makes the draft again from the stored film (no new file, no probe), with the film's
captions, or written from the title as above when it has none, on the next free slot, tells Wan on Telegram, and marks the import row's
`note` with `[draft made again YYYY-MM-DD]` **before** it writes the draft: an import is recovered once, never again, even if the
recovery fails half way. Up to two a run. No column is needed. A draft Wan deletes on purpose within 7 days of the import is
made again once; delete it a second time and it stays gone.

## Examples

```bash
curl -X POST "https://<project>.supabase.co/functions/v1/semasa-import-video" \
  -H "Authorization: Bearer $SEMASA_IMPORT_TOKEN" \
  -F "file=@film.mp4;type=video/mp4" \
  -F "title=Notifikasi kosmetik" \
  -F "caption=Satu ayat tentang apa yang filem ini jelaskan." \
  -F "source=hermes" \
  -F "idempotency_key=hermes-2026-11-18-01"
```

```python
import os, requests

URL = "https://<project>.supabase.co/functions/v1/semasa-import-video"
TOKEN = os.environ["SEMASA_IMPORT_TOKEN"]            # never put the key in a repo or a prompt

with open("film.mp4", "rb") as f:
    r = requests.post(
        URL,
        headers={"Authorization": f"Bearer {TOKEN}"},
        files={"file": ("film.mp4", f, "video/mp4")},
        data={"title": "Notifikasi kosmetik", "caption": "…", "stream": "regulab",
              "channels": "instagram,facebook", "source": "hermes", "idempotency_key": "hermes-2026-11-18-01"},
        timeout=300,
    )
print(r.status_code, r.json())      # 202 {'ok': True, 'import_id': '…', 'status': 'received'}
```

A link instead of a file:

```bash
curl -X POST "$URL" -H "Authorization: Bearer $SEMASA_IMPORT_TOKEN" -H "Content-Type: application/json" \
  -d '{"video_url": "https://cdn.example.com/film.mp4", "caption": "…", "idempotency_key": "hermes-2026-11-18-02"}'
```

### From the Nexabot generate job

`.github/workflows/nexabot-generate.yml` (Actions, "Run workflow"): `prompt`, `dry` and `import` as before, plus optional `title`,
`caption` (one text for every channel), `captions_json` (`{"instagram": "…", "facebook": "…", "threads": "…"}`), `channels`
(`instagram,facebook,threads`) and `lang` (`bm` or `en`). They only count with `import` on and `dry` off. Every input reaches the script as
an environment variable (`NB_TITLE`, `NB_CAPTION`, `NB_CAPTIONS_JSON`, `NB_CHANNELS`, `NB_LANG`), never pasted into shell text, so a
caption with quotes or `$` is safe. With none of them, the film goes with its prompt as the title and Semasa writes the caption.
`python -m semasa.nexabot_generate OUT --prompt … --import [--title … --caption … --captions-json … --channels … --lang … --source …]`
does the same by hand; a `--captions-json` that is not a JSON object of channel texts is refused before anything is generated.

Code: `supabase/functions/semasa-import-video/` (the intake), `supabase/087_video_import.sql` (tables, keys), `backend/semasa/video_import.py`
(the worker, called from `motion.run`), `web/src/components/VideoImportCard.jsx` (the card).

## TikTok (Wan, 20 Nov 2026)

- **TikTok takes upright 9:16.** A film from Hermes / Nous is usually 16:9 (Nexabot's web route makes 1280x720). For TikTok only,
  Semasa sends an upright 1080x1920 copy: the whole picture across the width over a blurred, darkened copy of itself
  (`backend/semasa/tiktok_ratio.py`). Both routes use it: the publisher (an imported or Motion film that goes to TikTok) and
  `semasa.zernio_publish` (Hermes handing a finished film to Zernio). The copy is kept in the public bucket under `tiktok/<hash>.mp4`
  and reused on a re-send; a film already 9:16 is left alone; when the copy cannot be made TikTok gets nothing (the other platforms
  still go) and the publisher tries again next run. Facebook, Instagram and Threads get the film as it came.
- **TikTok is on request, not automatic.** An approved film no longer goes to TikTok by itself (it used to ride with every ws.regulab
  film that went to Instagram). It goes when Wan asks: Hermes names `tiktok` in `zernio_publish --channels ...`, which sends the
  upright copy. A post that already holds a TikTok record keeps it (a failed hand-over is retried; a sent one stays counted).
  `settings.channels.zernio.tiktok_with_film = true` brings the old ride-along back.
- **A per-post TikTok tick (Wan, 20 Nov 2026: "ask me every time").** In Motion's **Post / queue** panel, a ws.regulab film that goes
  to Instagram shows **Send to TikTok too**, off every time. Ticked, the queued post lists `tiktok` in its own `channels`
  (`supabase/088_tiktok_channel.sql` lets the column hold it) and the publisher sends the upright copy with Instagram's caption.
  A picture post, a LinkedIn post, or a post without Instagram never goes, whatever the column says.

