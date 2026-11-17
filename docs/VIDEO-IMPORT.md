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
| `caption` | text for every channel, or an object `{"instagram": "…", "facebook": "…", "threads": "…"}`. Never altered or shortened. A caption that breaks a rule, or none at all, still makes the draft, with the blocking flags on it for Wan to fix in the page |
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

Code: `supabase/functions/semasa-import-video/` (the intake), `supabase/087_video_import.sql` (tables, keys), `backend/semasa/video_import.py`
(the worker, called from `motion.run`), `web/src/components/VideoImportCard.jsx` (the card).
