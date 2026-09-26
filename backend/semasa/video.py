"""Video: a long video becomes short clips and draft posts (Wan, 26 Sep 2026: "add segment that can cut, edit video for
short video such as youtube video (ceramah agama) to able act idea and post, allow me to paste youtube page to you
scrape, once approve can cut edit and create into short video").

Two halves, both run by the media worker:

READ (a semasa_videos row, status new → ready). The link's details and its words: a transcript Wan pasted comes first
(YouTube's own "Show transcript" copy, timestamps and all); then the video's subtitles, then YouTube's automatic
captions; for a link to a video file with none of those, Cloudflare's Whisper (the same free allowance the pictures
use). The writer then proposes 3 to 6 clips of 15 to 90 seconds, each a complete thought.

CUT (a media job, mode "clip"). Only after Wan has said he may use the video (rights: his own, the owner's permission,
or a Creative Commons licence). The worker fetches just that stretch, makes a 1080x1920 short (the picture fitted over
a blurred copy of itself, or cropped to fill), burns in the captions and the clip's opening line, stores it, and writes
a DRAFT post carrying it. Nothing is published here: the post goes through the same gate as every other.

Rules the writer is held to: a clip never changes what the speaker meant, carries the conditions of any ruling it
states, and is credited to the speaker; the caption carries no call to action, no URL, and never names YouTube.

Tools: yt-dlp for YouTube (pip), a static ffmpeg with libass (imageio-ffmpeg, pip), so the runner installs nothing.
GitHub's machines are sometimes refused by YouTube ("Sign in to confirm you're not a bot"): the error says so, and the
way round it is a pasted transcript for the reading and a link to the video file for the cutting.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from . import compliance, db
from .log import get_logger

log = get_logger("semasa.video")

VIDEOS = "semasa_videos"
MIN_CLIP, MAX_CLIP = 15, 90
MAX_SOURCE_S = 4 * 3600
MAX_OUT_BYTES = 48 * 1024 * 1024          # the semasa-generated bucket takes 50 MB a file
W, H = 1080, 1920
FONTS = Path(__file__).resolve().parent / "fonts"
LOGO = Path(__file__).resolve().parents[2] / "web" / "public" / "cards" / "logo.png"
STALE = timedelta(minutes=30)
YOUTUBE_ID = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|live/|embed/)|youtu\.be/)([\w-]{11})")


class VideoError(RuntimeError):
    """Final: the message is shown on the page."""


# --- small helpers ---------------------------------------------------------------------------------------

def youtube_id(url: str) -> str | None:
    m = YOUTUBE_ID.search(url or "")
    return m.group(1) if m else None


def fmt_ts(sec: float) -> str:
    sec = max(0, int(round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_ts(v: Any) -> float | None:
    """'1:02:03', '12:34', '75', 75 -> seconds; None when it is not a time."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip().strip("[]()")
    if not re.fullmatch(r"\d{1,2}(:\d{1,2}){0,2}(\.\d+)?", s):
        return None
    parts = [float(p) for p in s.split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def ffmpeg() -> str:
    """The static ffmpeg that comes with the imageio-ffmpeg wheel: libass, freetype and x264 included."""
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


# --- transcripts ------------------------------------------------------------------------------------------

_TAG = re.compile(r"<[^>]+>")
_CUE_TIME = re.compile(r"(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}\s*-->\s*(\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}")


def _vtt_time(t: str) -> float:
    t = t.strip().replace(",", ".")
    parts = [float(p) for p in t.split(":")]
    return parts[0] * 3600 + parts[1] * 60 + parts[2] if len(parts) == 3 else parts[0] * 60 + parts[1]


def parse_vtt(text: str) -> list[dict[str, Any]]:
    """WebVTT (or SRT) to [{s, e, t}]. YouTube's automatic captions repeat the previous line at the top of each cue
    (rolling captions) and carry word-timing tags; both are removed, so every word appears once."""
    out: list[dict[str, Any]] = []
    prev: list[str] = []
    for block in re.split(r"\n\s*\n", (text or "").replace("\r", "")):
        lines = [x for x in block.split("\n") if x.strip()]
        idx = next((i for i, x in enumerate(lines) if _CUE_TIME.search(x)), None)
        if idx is None:
            continue
        a, b = lines[idx].split("-->")[:2]
        start, end = _vtt_time(a), _vtt_time(b.split()[0])
        words = [re.sub(r"\s+", " ", _TAG.sub("", x)).strip() for x in lines[idx + 1:]]
        words = [x for x in words if x]
        fresh = [x for x in words if x not in prev]
        prev = words or prev
        if not fresh:
            continue
        t = " ".join(fresh).replace("&nbsp;", " ").replace("&amp;", "&").replace("&gt;", ">").replace("&lt;", "<")
        if out and out[-1]["t"] == t:
            out[-1]["e"] = end
            continue
        out.append({"s": round(start, 2), "e": round(end, 2), "t": t})
    return out


_PASTE_TS = re.compile(r"^\s*\[?((?:\d{1,2}:)?\d{1,2}:\d{2})\]?\s*(.*)$")


def parse_pasted(text: str) -> list[dict[str, Any]]:
    """What YouTube's "Show transcript" panel copies: a timestamp line then the words, or both on one line.
    Lines with no timestamp join the segment above them. A segment ends where the next begins."""
    segs: list[dict[str, Any]] = []
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        m = _PASTE_TS.match(line)
        if m and parse_ts(m.group(1)) is not None:
            segs.append({"s": parse_ts(m.group(1)), "e": None, "t": m.group(2).strip()})
        elif segs:
            segs[-1]["t"] = (segs[-1]["t"] + " " + line).strip()
    segs = [x for x in segs if x["t"]]
    for i, x in enumerate(segs):
        nxt = segs[i + 1]["s"] if i + 1 < len(segs) else x["s"] + max(3.0, len(x["t"]) / 15)
        x["e"] = round(max(x["s"] + 0.5, nxt), 2)
    return segs


def windows(segs: list[dict[str, Any]], seconds: float = 10, chars: int = 220) -> list[dict[str, Any]]:
    """Consecutive segments joined into ~10-second lines, so a long talk reaches the writer compactly."""
    out: list[dict[str, Any]] = []
    for x in segs:
        if out and x["s"] - out[-1]["s"] < seconds and len(out[-1]["t"]) + len(x["t"]) < chars:
            out[-1]["t"] += " " + x["t"]
            out[-1]["e"] = x["e"]
        else:
            out.append(dict(x))
    return out


def transcript_text(segs: list[dict[str, Any]], limit: int = 110_000) -> tuple[str, bool]:
    lines, total = [], 0
    for x in windows(segs):
        line = f"[{fmt_ts(x['s'])}] {x['t']}"
        total += len(line) + 1
        if total > limit:
            return "\n".join(lines), True
        lines.append(line)
    return "\n".join(lines), False


# --- reading a link ------------------------------------------------------------------------------------------

def _ydl_opts(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {"quiet": True, "no_warnings": True, "noplaylist": True,
                            "js_runtimes": {"deno": {}, "node": {}}, "socket_timeout": 30}
    cookies = os.environ.get("YTDLP_COOKIES")
    if cookies:
        path = Path(tempfile.gettempdir()) / "semasa-yt-cookies.txt"
        path.write_text(cookies)
        opts["cookiefile"] = str(path)
    return {**opts, **(extra or {})}


def _youtube_refusal(exc: Exception) -> VideoError:
    msg = str(exc)
    if "confirm you" in msg.lower() or "sign in" in msg.lower() or "bot" in msg.lower():
        return VideoError("YouTube refused GitHub's machine (\"confirm you're not a bot\"). Paste the transcript "
                          "yourself (YouTube → … → Show transcript → copy) and read again; to CUT, give a link to the "
                          "video file instead (Google Drive, anyone with the link), or set the YTDLP_COOKIES secret.")
    if "private" in msg.lower() or "unavailable" in msg.lower():
        return VideoError(f"YouTube says this video is not available: {msg[:300]}")
    return VideoError(f"could not read the video: {msg[:400]}")


def pick_captions(info: dict[str, Any]) -> tuple[str, str, str] | None:
    """(url, kind, language) of the best captions: the video's own subtitles first, then the automatic captions in
    the language the video is spoken in ('-orig'), then Malay, Indonesian, English."""
    spoken = str(info.get("language") or "").split("-")[0]
    prefer = [x for x in (spoken, "ms", "id", "en") if x]

    def best(tracks: dict[str, Any], kind: str, orig_first: bool) -> tuple[str, str, str] | None:
        keys = list(tracks or {})
        order: list[str] = []
        if orig_first:
            order += [k for k in keys if k.endswith("-orig")]
        for lang in prefer:
            order += [k for k in keys if k == lang or k.startswith(lang + "-")]
        for k in order:
            for f in tracks.get(k) or []:
                if f.get("ext") == "vtt" and f.get("url"):
                    return f["url"], kind, k
        return None

    return (best(info.get("subtitles") or {}, "subtitles", False)
            or best(info.get("automatic_captions") or {}, "auto-captions", True))


def read_youtube(url: str) -> tuple[dict[str, Any], list[dict[str, Any]], str]:
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL(_ydl_opts({"skip_download": True})) as ydl:
            info = ydl.extract_info(url, download=False)
            meta = {"title": info.get("title"), "channel": info.get("channel") or info.get("uploader"),
                    "channel_url": info.get("channel_url") or info.get("uploader_url"),
                    "duration_s": int(info.get("duration") or 0) or None, "thumbnail_url": info.get("thumbnail"),
                    "upload_date": info.get("upload_date"), "license": info.get("license"),
                    "description": (info.get("description") or "")[:3000]}
            track = pick_captions(info)
            segs: list[dict[str, Any]] = []
            source = "none"
            if track:
                body = ydl.urlopen(track[0]).read().decode("utf-8", "replace")
                segs, source = parse_vtt(body), track[1]
            return meta, segs, source
    except VideoError:
        raise
    except Exception as exc:  # noqa: BLE001 - yt-dlp raises many kinds
        raise _youtube_refusal(exc) from exc


def is_drive(url: str) -> bool:
    return "drive.google.com" in (url or "") or "docs.google.com" in (url or "")


def download_link(url: str, dest: Path) -> Path:
    """A direct link to a video file, or a Google Drive file shared with anyone who has the link."""
    if is_drive(url):
        import gdown
        out = gdown.download(url=url, output=str(dest), quiet=True, fuzzy=True)
        if not out or not Path(out).exists():
            raise VideoError("Google Drive did not hand the file over: share it as 'Anyone with the link' and try again")
        return Path(out)
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        kind = r.headers.get("content-type", "")
        if "text/html" in kind:
            raise VideoError("that link opens a web page, not a video file: give the file's own address, or Google Drive")
        size = 0
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                size += len(chunk)
                if size > 3 * 1024 ** 3:
                    raise VideoError("the video file is larger than 3 GB")
                fh.write(chunk)
    return dest


def probe_duration(path: Path) -> float | None:
    """Read the duration from ffmpeg's own report (the static build has no ffprobe)."""
    p = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


def whisper(path: Path, account: str | None, token: str | None, model: str = "@cf/openai/whisper-large-v3-turbo",
            chunk_s: int = 600) -> list[dict[str, Any]]:
    """Words from the sound, by Cloudflare's Whisper, ten minutes at a time (16 kHz mono MP3)."""
    if not (account and token):
        raise VideoError("this video has no transcript and Cloudflare is not set up to hear it: paste the transcript, "
                         "or set CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN")
    total = probe_duration(path) or 0
    segs: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory() as tmp:
        start = 0.0
        while start < max(total, 1):
            part = Path(tmp) / f"a{int(start)}.mp3"
            subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", str(start), "-t", str(chunk_s),
                            "-i", str(path), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", str(part)], check=True)
            if not part.exists() or part.stat().st_size < 1000:
                break
            r = requests.post(f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}",
                              headers={"Authorization": f"Bearer {token}"}, timeout=300,
                              json={"audio": base64.b64encode(part.read_bytes()).decode("ascii")})
            if r.status_code >= 400:
                raise VideoError(f"Cloudflare Whisper refused the sound ({r.status_code}): {r.text[:300]}")
            res = (r.json() or {}).get("result") or {}
            for x in res.get("segments") or []:
                t = str(x.get("text") or "").strip()
                if t:
                    segs.append({"s": round(start + float(x.get("start") or 0), 2),
                                 "e": round(start + float(x.get("end") or 0), 2), "t": t})
            start += chunk_s
    return segs


# --- the writer's proposals ------------------------------------------------------------------------------------

VOICE = {
    "regulab": "Captions in Malaysian Malay (never Bahasa Indonesia: boleh, ubat, syarikat, kualiti, pembungkusan), "
               "natural and warm, for ws.regulab's audience of Malaysian SME owners and Muslim consumers.",
    "linkedin": "Captions in English for regulatory and formulation peers, under a named chemist's own byline. No "
                "company identity at all.",
}

PROPOSE = """You choose short clips from a long talk for social media (Reels, Shorts, Threads, LinkedIn video).

Pick 3 to 6 clips. Each is {min} to {max} seconds and is ONE complete thought: it starts where a sentence starts and
ends where a sentence ends, and it makes sense to someone who has not heard the rest.

Rules. Breaking any of them makes the clip unusable:
1. Never change what the speaker meant. A clip must not make the speaker say something he did not mean once cut
   from its context. If a ruling (hukum, fatwa, halal/haram, wajib, sunat) is stated, the clip carries its conditions
   and exceptions, or it is not chosen. Set "sensitive": true on any clip that states a ruling, so a person checks it.
2. The caption credits the speaker by name (from the details below; if unknown, "penceramah" / "the speaker") and
   presents the point as HIS, never as ws.regulab's own ruling.
3. No call to action of any kind, no URL, no hashtags list longer than 3, and never the words YouTube, TikTok or
   Facebook. No emoji walls.
4. No fact that is not in the transcript. Quote him only with words he actually said.
5. "hook" is the first line shown on the video: at most 8 words, faithful to the clip.

{voice}

Answer with ONE JSON object only:
{{"clips": [{{"start": "m:ss", "end": "m:ss", "title": "a short name for the clip",
  "hook": "on-screen first line", "why": "one line: why this works as a short",
  "caption": "the post caption, 2 to 5 short paragraphs", "sensitive": false}}],
  "speaker": "the speaker's name if the details or the talk give it, else empty"}}"""


def propose(llm: Any, video: dict[str, Any], segs: list[dict[str, Any]], duration: float | None) -> tuple[list[dict], str]:
    if not llm or not llm.configured:
        raise VideoError("the writer is off, so no clips can be proposed: " + (llm.why_off() if llm else "no writer"))
    body, cut = transcript_text(segs)
    stream = video.get("stream") or "regulab"
    system = PROPOSE.format(min=MIN_CLIP, max=MAX_CLIP, voice=VOICE.get(stream, VOICE["regulab"]))
    details = (f"TITLE: {video.get('title') or ''}\nCHANNEL: {video.get('channel') or ''}\n"
               f"DURATION: {fmt_ts(duration or 0)}\nWAN'S NOTE: {video.get('note') or '(none)'}\n"
               + ("NOTE: the transcript below is cut short; choose from what is there.\n" if cut else ""))
    out = llm.chat_json(system, f"{details}\nTRANSCRIPT:\n{body}", max_tokens=4000)
    if not isinstance(out, dict):
        raise VideoError("the writer did not answer (see the run log): press Read again")
    clips = validate_clips(out.get("clips"), segs, duration)
    if not clips:
        raise VideoError("the writer proposed no usable clip (each must be 15 to 90 seconds inside the video)")
    return clips, str(out.get("speaker") or "").strip()[:120]


def snap(t: float, segs: list[dict[str, Any]], edge: str) -> float:
    """Move a cut to the nearest segment boundary within 2 s, so no word is cut in half."""
    keys = [x["s"] for x in segs] if edge == "start" else [x["e"] for x in segs]
    near = [k for k in keys if abs(k - t) <= 2]
    return min(near, key=lambda k: abs(k - t)) if near else t


def validate_clips(raw: Any, segs: list[dict[str, Any]], duration: float | None) -> list[dict[str, Any]]:
    out = []
    for i, c in enumerate(raw if isinstance(raw, list) else []):
        if not isinstance(c, dict):
            continue
        s, e = parse_ts(c.get("start")), parse_ts(c.get("end"))
        if s is None or e is None:
            continue
        s, e = snap(s, segs, "start"), snap(e, segs, "end")
        if duration:
            e = min(e, duration)
        if not (MIN_CLIP <= e - s <= MAX_CLIP) or s < 0:
            continue
        out.append({"id": hashlib.sha1(f"{s}-{e}-{i}".encode()).hexdigest()[:10], "start": round(s, 2), "end": round(e, 2),
                    "title": str(c.get("title") or "")[:120], "hook": str(c.get("hook") or "")[:90],
                    "why": str(c.get("why") or "")[:300], "caption": str(c.get("caption") or "")[:2200],
                    "sensitive": bool(c.get("sensitive"))})
    return out[:6]


# --- the READ half --------------------------------------------------------------------------------------------------

def read(store: Any, llm: Any, video: dict[str, Any]) -> None:
    url = str(video.get("source_url") or "").strip()
    kind = video.get("source_kind") or ("youtube" if youtube_id(url) else "link")
    meta: dict[str, Any] = {}
    segs: list[dict[str, Any]] = []
    source = "none"
    if kind == "youtube":
        if not youtube_id(url):
            raise VideoError("that is not a YouTube video link (watch, youtu.be, shorts or live)")
        pasted = parse_pasted(video.get("transcript_paste") or "")
        try:
            meta, segs, source = read_youtube(url)
        except VideoError:
            if not pasted:
                raise
            log.warning("%s: YouTube could not be read; using the pasted transcript", video["id"])
        if pasted:
            segs, source = pasted, "pasted"
    else:
        pasted = parse_pasted(video.get("transcript_paste") or "")
        with tempfile.TemporaryDirectory() as tmp:
            path = download_link(url, Path(tmp) / "source")
            meta["duration_s"] = int(probe_duration(path) or 0) or None
            if pasted:
                segs, source = pasted, "pasted"
            else:
                segs = whisper(path, os.environ.get("CLOUDFLARE_ACCOUNT_ID"), os.environ.get("CLOUDFLARE_API_TOKEN"))
                source = "whisper"
        meta.setdefault("title", url.rsplit("/", 1)[-1][:120])
    if meta.get("duration_s") and meta["duration_s"] > MAX_SOURCE_S:
        raise VideoError(f"the video is {fmt_ts(meta['duration_s'])} long; the limit is {fmt_ts(MAX_SOURCE_S)}")
    if not segs:
        raise VideoError("this video has no transcript YouTube will give. Paste it yourself: on YouTube, open the "
                         "description → Show transcript, select all of it, copy, and paste it here, then Read again")
    duration = meta.get("duration_s") or (segs[-1]["e"] if segs else None)
    clips, speaker = propose(llm, {**video, **meta}, segs, duration)
    update = {k: v for k, v in meta.items() if k != "description"}
    update.update(status="ready", transcript=segs, transcript_source=source, clips=clips, error=None,
                  duration_s=int(duration or 0) or None)
    if speaker and not update.get("channel"):
        update["channel"] = speaker
    for c in clips:
        c["speaker"] = speaker
    store.table(VIDEOS).update(update).eq("id", video["id"]).execute()
    log.info("%s: %d segments (%s), %d clips proposed", video["id"], len(segs), source, len(clips))


def run(store: Any, llm: Any, limit: int = 2, max_attempts: int = 3) -> str:
    """Read the videos waiting. Never raises: a missing table (011 not run yet) is a line in the summary."""
    try:
        cutoff = (datetime.now(UTC) - STALE).isoformat()
        store.table(VIDEOS).update({"status": "new"}).eq("status", "working").lt("updated_at", cutoff).execute()
        rows = store.table(VIDEOS).select("*").eq("status", "new").order("created_at").limit(limit).execute().data or []
    except Exception as exc:  # noqa: BLE001
        return f"Video: not set up ({str(exc)[:120]}); run supabase/011_video.sql"
    done = 0
    for v in rows:
        claimed = (store.table(VIDEOS).update({"status": "working", "attempts": int(v.get("attempts") or 0) + 1, "error": None})
                   .eq("id", v["id"]).eq("status", "new").execute().data)
        if not claimed:
            continue
        try:
            read(store, llm, v)
            done += 1
            db.log_event(store, "info", "media", "video.ready", f"Video dibaca: {(v.get('title') or v['source_url'])[:80]}",
                         ref_table=VIDEOS, ref_id=v["id"])
        except Exception as exc:  # noqa: BLE001 - the row records it
            attempts = int(v.get("attempts") or 0) + 1
            final = isinstance(exc, VideoError) or attempts >= max_attempts
            msg = str(exc)[:900] if isinstance(exc, VideoError) else f"{type(exc).__name__}: {str(exc)[:800]}"
            log.error("video %s: %s", v["id"], msg)
            store.table(VIDEOS).update({"status": "error" if final else "new", "error": msg}).eq("id", v["id"]).execute()
    return f"Video: {done}/{len(rows)} read" if rows else "Video: nothing waiting"


# --- the CUT half -------------------------------------------------------------------------------------------------

def _ass_text(t: str) -> str:
    return str(t or "").replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def _ass_time(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


STYLE_FORMAT = ("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
                "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
                "MarginR, MarginV, Encoding")


def build_ass(segs: list[dict[str, Any]], start: float, end: float, hook: str, captions: bool = True) -> str:
    """The clip's words as subtitles (lower third, white on a black outline) and its opening line in a box at the top
    for the whole clip. Times are relative to the clip."""
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
{STYLE_FORMAT}
Style: Cap,Inter,62,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,5,0,2,90,90,300,1
Style: Hook,Inter,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&HB4101418,0,0,0,0,100,100,0,0,3,22,0,8,90,90,230,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dur = end - start
    events = []
    if hook.strip():
        events.append(f"Dialogue: 1,{_ass_time(0)},{_ass_time(dur)},Hook,,0,0,0,,{_ass_text(hook)}")
    if captions:
        for x in segs:
            s, e = max(x["s"], start) - start, min(x["e"], end) - start
            if e - s < 0.2:
                continue
            events.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Cap,,0,0,0,,{_ass_text(x['t'])}")
    return head + "\n".join(events) + "\n"


def _escape_filter_path(p: Path) -> str:
    return str(p).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


def caption_fonts(work: Path) -> Path:
    """A fonts folder holding ONLY Inter SemiBold. Both Inter files in semasa/fonts name themselves "Inter Regular"
    inside, so libass handed a folder with both picks the Regular one (measured: fontselect -> Inter-Regular)."""
    d = work / "fonts"
    d.mkdir(exist_ok=True)
    (d / "Inter-SemiBold.ttf").write_bytes((FONTS / "Inter-SemiBold.ttf").read_bytes())
    return d


def filter_graph(frame: str, ass: Path, logo: Path | None, fonts: Path = FONTS) -> str:
    """fit: the whole picture across the width over a blurred, darkened copy of itself (a talk filmed wide keeps the
    speaker AND the room); fill: cropped to 9:16 from the centre (a speaker filmed close)."""
    if frame == "fill":
        base = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[base]"
    else:
        base = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                f"gblur=sigma=28,eq=brightness=-0.12[bg];[b]scale={W}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    subs = f"[base]subtitles=filename='{_escape_filter_path(ass)}':fontsdir='{_escape_filter_path(fonts)}'[sub]"
    if logo:
        return f"{base};{subs};[1:v]scale=300:-1[lg];[sub][lg]overlay=70:80[v]"
    return f"{base};{subs.replace('[sub]', '[v]')}"


def trimmed_logo(dest: Path) -> Path | None:
    """The ws.regulab mark without the file's transparent padding (the same trim Studio's cards make)."""
    try:
        from PIL import Image
        with Image.open(LOGO) as im:
            im = im.convert("RGBA")
            box = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
            (im.crop(box) if box else im).save(dest)
        return dest
    except Exception as exc:  # noqa: BLE001 - a clip without the mark is still a clip
        log.info("no logo on the clip: %s", exc)
        return None


def render(src: Path, out: Path, *, start_in_file: float, dur: float, ass_text: str, frame: str, stream: str,
           crf: int = 23, maxrate: str = "3M") -> None:
    work = out.parent
    ass = work / "clip.ass"
    ass.write_text(ass_text, "utf-8")
    logo = trimmed_logo(work / "logo.png") if stream != "linkedin" else None     # LinkedIn carries no ws.regulab mark
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start_in_file:.2f}", "-t", f"{dur:.2f}",
           "-i", str(src)]
    if logo:
        cmd += ["-i", str(logo)]
    cmd += ["-filter_complex", filter_graph(frame, ass, logo, caption_fonts(work)), "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-maxrate", maxrate, "-bufsize", "6M",
            "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-movflags", "+faststart", str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0 or not out.exists():
        raise RuntimeError(f"ffmpeg failed: {p.stderr[-800:]}")


def fetch_section(video: dict[str, Any], start: float, end: float, work: Path) -> tuple[Path, float]:
    """The stretch to cut, on disk, and where the clip starts inside that file."""
    url = video["source_url"]
    if (video.get("source_kind") or "youtube") == "youtube":
        import yt_dlp
        from yt_dlp.utils import download_range_func
        pad = 1.0
        a, b = max(0.0, start - pad), end + pad
        opts = _ydl_opts({"format": "bv*[height<=1080]+ba/b[height<=1080]/b", "outtmpl": str(work / "src.%(ext)s"),
                          "download_ranges": download_range_func(None, [(a, b)]), "force_keyframes_at_cuts": True,
                          "ffmpeg_location": ffmpeg(), "merge_output_format": "mp4"})
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
        except Exception as exc:  # noqa: BLE001
            raise _youtube_refusal(exc) from exc
        files = [f for f in work.glob("src.*") if f.suffix not in (".part", ".ytdl")]
        if not files:
            raise VideoError("YouTube gave no video file for this stretch")
        return files[0], start - a
    path = download_link(url, work / "source")
    return path, start


def process_clip(store: Any, row: dict[str, Any], max_attempts: int) -> bool:
    row_id = row["id"]
    meta = dict(row.get("meta") or {})
    try:
        vids = store.table(VIDEOS).select("*").eq("id", meta.get("video_id")).execute().data or []
        if not vids:
            raise VideoError("the video this clip comes from was deleted")
        video = vids[0]
        if not video.get("rights"):
            raise VideoError("no rights recorded for this video: confirm on the Video tab that it is your own, that the "
                             "owner allows it, or that it is Creative Commons, then cut again")
        start, end = parse_ts(meta.get("start")), parse_ts(meta.get("end"))
        if start is None or end is None or not (3 <= end - start <= MAX_CLIP):
            raise VideoError(f"a clip is 3 to {MAX_CLIP} seconds; this one is {fmt_ts(start or 0)} to {fmt_ts(end or 0)}")
        segs = video.get("transcript") or []
        ass = build_ass(segs, start, end, str(meta.get("hook") or ""), bool(meta.get("captions", True)))
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            src, offset = fetch_section(video, start, end, work)
            out = work / "clip.mp4"
            stream = video.get("stream") or "regulab"
            render(src, out, start_in_file=offset, dur=end - start, ass_text=ass, frame=str(meta.get("frame") or "fit"),
                   stream=stream)
            if out.stat().st_size > MAX_OUT_BYTES:
                render(src, out, start_in_file=offset, dur=end - start, ass_text=ass, frame=str(meta.get("frame") or "fit"),
                       stream=stream, crf=28, maxrate="1.6M")
            if out.stat().st_size > MAX_OUT_BYTES:
                raise VideoError("the clip is still larger than 50 MB after shrinking: make it shorter")
            poster = work / "poster.jpg"
            subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", "1", "-i", str(out),
                            "-frames:v", "1", "-q:v", "3", str(poster)], check=False)
            day = datetime.now(UTC).strftime("%Y/%m")
            data = out.read_bytes()
            url = db.upload_generated(store, f"{day}/{row_id}-clip.mp4", data, "video/mp4")
            poster_url = db.upload_generated(store, f"{day}/{row_id}-clip.jpg", poster.read_bytes(), "image/jpeg") \
                if poster.exists() else None
        meta.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), poster_url=poster_url, width=W, height=H,
                    seconds=round(end - start, 2), content_type="video/mp4", finished_at=datetime.now(UTC).isoformat())
        db.finish_media(store, row_id, status="done", generated_media_url=url, provider="semasa", model="clip-v1",
                        error=None, meta=meta)
        post_id = row.get("post_id") or write_post(store, row, video, meta)
        if row.get("post_id"):
            replace_clip_in_draft(store, row["post_id"], row_id)
        log.info("%s: clip %s-%s cut (%d bytes), post %s", row_id, fmt_ts(start), fmt_ts(end), len(data), post_id)
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, VideoError) or attempts >= max_attempts
        msg = str(exc)[:900] if isinstance(exc, VideoError) else f"{type(exc).__name__}: {str(exc)[:800]}"
        log.error("%s: %s (attempt %d)", row_id, msg, attempts)
        db.finish_media(store, row_id, status="error" if final else "pending", error=msg, provider="semasa")
        return False


def replace_clip_in_draft(store: Any, post_id: str, media_id: str) -> None:
    """A clip cut again for its own draft takes the old clip's place (one short per post), and only while the post is a
    DRAFT, the same gate db.attach_media_to_draft keeps."""
    try:
        rows = store.table(db.POSTS).select("id,status,media_ids").eq("id", post_id).limit(1).execute().data or []
        if not rows or rows[0]["status"] != "draft":
            return
        ids = [i for i in (rows[0].get("media_ids") or []) if i != media_id]
        clips = {r["id"] for r in (store.table(db.MEDIA).select("id,mode").in_("id", ids).execute().data or [])
                 if r.get("mode") == "clip"} if ids else set()
        at = next((n for n, i in enumerate(ids) if i in clips), len(ids))
        kept = [i for i in ids if i not in clips]
        kept.insert(min(at, len(kept)), media_id)
        store.table(db.POSTS).update({"media_ids": kept}).eq("id", post_id).eq("status", "draft").execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not put clip %s on post %s: %s", media_id, post_id, exc)


def write_post(store: Any, row: dict[str, Any], video: dict[str, Any], meta: dict[str, Any]) -> str | None:
    """The clip's DRAFT post: its caption for each of the stream's platforms, the speaker as the source, the clip as
    its only media, the next free position. Judged by the same scan as every post; nothing is approved here."""
    from . import ideas
    stream = video.get("stream") or "regulab"
    lang = "en" if stream == "linkedin" else "bm"
    caption = str(meta.get("caption") or "").strip()
    if not caption:
        return None
    text = ideas.normalise_text({lang: {p: caption for p in compliance.platforms_for(stream)}}, stream, lang)
    settings = ideas.load_settings(store)
    brand = settings.get("brand") or {}
    domain = video.get("domain") if stream == "regulab" else None
    date, slot = ideas.next_free_position(stream, domain, brand, ideas.taken_positions(store, stream))
    speaker = str(meta.get("speaker") or video.get("channel") or "").strip()
    post = {"stream": stream, "domain": domain, "angle": video.get("angle") if stream == "linkedin" else None,
            "lang": lang, "hook": str(meta.get("hook") or meta.get("title") or "")[:300], "text": text,
            "citation": (f"{speaker}, {video.get('title') or ''}".strip(", "))[:1000], "media_ids": [row["id"]],
            "date": date, "slot": slot, "status": "draft", "created_by": row.get("created_by")}
    reg = brand.get("regulab") or {}
    flags = compliance.scan({**post, "media": [{"type": "video", "url": "clip"}]}, brand=reg, schedule=reg.get("schedule"),
                            indo_extra=(settings.get("bahasa") or {}).get("indo"))
    post["flags"], post["hard_flags"] = flags, compliance.hard_count(flags)
    post_id = store.table(db.POSTS).insert(post).execute().data[0]["id"]
    store.table(db.MEDIA).update({"post_id": post_id}).eq("id", row["id"]).execute()
    db.log_event(store, "info", "media", "video.clip", f"Klip video siap dan draf ditulis: {post['hook'][:80]}",
                 ref_table="semasa_posts", ref_id=post_id)
    return post_id

