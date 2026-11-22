"""Import video (Wan, 17 Nov 2026): an MP4 made OUTSIDE Semasa (Nous Hermes, Nexabot, huashu-motion) is sent in through the Edge
Function `semasa-import-video`, which stores it and writes a `semasa_video_imports` row as `received` (supabase/087). This is the
worker half, run from the Motion step (`motion.run`, beside the daily comic): it checks the file and the caption and, when both
pass, makes a Motion film row (already `done`) and a DRAFT post on the next free slot, exactly as `comic_daily.queue_post` does.

THE GATE: nothing here approves, schedules or posts. The post is a draft carrying the page's own scan; Wan's Approve click
(page or Telegram) is the only gate and the database enforces it. A FILE that fails (not a real MP4, no picture, too long or
too big for the channels, a bad link) ends the import as `error` with a sentence a person can act on, and the stored file is
deleted. A CAPTION that fails the compliance scan, or none at all, is not a failure (Wan, 17 Nov 2026): the draft is made anyway
with the blocking flags on it, so he fixes the caption in the page; the page (and Telegram's Approve) refuse while a hard
flag remains.

NO CAPTION SENT (Wan, 17 Nov 2026: "betulkan untuk imported video"): when the sender gave a title but no caption, Semasa
writes one per channel with the Motion caption writer (`motion_captions.write`) from the title alone, checks it with the same
compliance scan, and falls back to a plain caption built from the title when the writer fails or its text breaks a rule. The
draft says so (a decision, a warning flag, the note) and is never approved. A caption the sender gave is never touched.

Limits are the repo's own, none invented: a stored file is at most 50 MB (the bucket, supabase/003), the posted copy at most
`video.MAX_OUT_BYTES` (48 MB) and `video.MAX_CLIP` (90 s), the longest short film Semasa itself makes. The compressed copy is
`motion.social_copy`, the same one a Motion film gets. Never raises: the import step must never stop a film."""

from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from . import autofill, compliance, db, film_ratio, ideas, motion, motion_captions, video
from .log import get_logger

log = get_logger("semasa.video_import")

TABLE = "semasa_video_imports"
MOTIONS = "semasa_motions"
MAX_PER_RUN = 3  # imports checked in one Motion run: each may be compressed
MAX_ATTEMPTS = 3  # a transient failure (the database, the network) is tried this many times
STALE_AFTER = timedelta(minutes=30)
MAX_FILE_BYTES = 52_428_800  # the bucket's ceiling (supabase/003)
MAX_SECONDS = video.MAX_CLIP
MAX_POSTED_BYTES = video.MAX_OUT_BYTES
MYT = timedelta(hours=8)
FETCH_TIMEOUT = (10, 60)
MAX_REDIRECTS = 3
LIMITS = {c: {"seconds": MAX_SECONDS, "bytes": MAX_POSTED_BYTES} for c in ("instagram", "facebook", "tiktok")}
CHANNEL_NAMES = {"instagram": "Instagram", "facebook": "Facebook", "threads": "Threads", "linkedin": "LinkedIn",
                 "tiktok": "TikTok"}
MP4_FORMATS = ("mov", "mp4")  # what ffprobe calls every MP4 / MOV: "mov,mp4,m4a,3gp,3g2,mj2"
H264, AAC = "h264", "aac"


class Reject(Exception):
    """The import cannot become a post. The message is a sentence Wan, or the agent that sent it, can act on."""


# --- where the bytes live -----------------------------------------------------------------------------------------------------


class Storage:
    """The public bucket semasa-generated, as the worker uses it (db.upload_generated). Tests pass a stand-in with the same four
    methods."""

    def __init__(self, store: Any):
        self.store = store

    def download(self, path: str) -> bytes:
        return bytes(self.store.storage.from_(db.GENERATED_BUCKET).download(path))

    def upload(self, path: str, data: bytes, content_type: str) -> str:
        return db.upload_generated(self.store, path, data, content_type)

    def url(self, path: str) -> str:
        return str(self.store.storage.from_(db.GENERATED_BUCKET).get_public_url(path))

    def remove(self, paths: list[str]) -> None:
        self.store.storage.from_(db.GENERATED_BUCKET).remove(paths)


# --- fetching a link safely ---------------------------------------------------------------------------------------------------


def _private(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    return a.is_private or a.is_loopback or a.is_link_local or a.is_reserved or a.is_multicast or a.is_unspecified


def check_host(url: str, resolve: Any = socket.getaddrinfo) -> None:
    """A public https address: no credentials, port 443 only, and every address the name resolves to is public (a name can
    point inward). Raises Reject."""
    u = urlparse(url)
    if u.scheme != "https" or not u.hostname or u.username or u.password or (u.port not in (None, 443)):
        raise Reject("video_url must be a public https address")
    try:
        ips = {str(info[4][0]) for info in resolve(u.hostname, 443, proto=socket.IPPROTO_TCP)}
    except OSError as exc:
        raise Reject(f"video_url could not be reached: {u.hostname} did not resolve") from exc
    if not ips or any(_private(ip) for ip in ips):
        raise Reject("video_url points inside a private network; send a public https address")


def fetch_url(url: str, *, get: Any = requests.get, resolve: Any = socket.getaddrinfo, limit: int = MAX_FILE_BYTES) -> bytes:
    """The bytes behind a public https address, redirects followed by hand (each hop is checked again), never more than
    `limit`. Raises Reject with what a person needs to know."""
    here = url
    for _ in range(MAX_REDIRECTS + 1):
        check_host(here, resolve)
        try:
            r = get(
                here, stream=True, timeout=FETCH_TIMEOUT, allow_redirects=False, headers={"User-Agent": "semasa-video-import"}
            )
        except requests.RequestException as exc:
            raise Reject(f"video_url could not be fetched ({type(exc).__name__})") from exc
        try:
            if 300 <= r.status_code < 400 and r.headers.get("location"):
                here = urljoin(here, r.headers["location"])
                continue
            if r.status_code != 200:
                raise Reject(f"video_url answered {r.status_code}; it must open without a login")
            kind = str(r.headers.get("content-type") or "").lower().split(";")[0]
            if kind.startswith(("text/", "image/")) or kind == "application/json":
                raise Reject(f"video_url is a {kind or 'page'}, not a video")
            if int(r.headers.get("content-length") or 0) > limit:
                raise Reject(f"the file at video_url is over {limit // 1_048_576} MB, the most Semasa stores")
            out = bytearray()
            for chunk in r.iter_content(chunk_size=1 << 20):
                out += chunk
                if len(out) > limit:
                    raise Reject(f"the file at video_url is over {limit // 1_048_576} MB, the most Semasa stores")
            return bytes(out)
        finally:
            close = getattr(r, "close", None)
            if close:
                close()
    raise Reject("video_url redirects too many times")


# --- the checks ---------------------------------------------------------------------------------------------------------------


def probe(path: Path, runner: Any = subprocess.run) -> dict[str, Any]:
    """What ffprobe says of the file: container, video and audio codecs, size in pixels, length. Raises Reject when it cannot
    read it as a video at all."""
    try:
        p = runner(
            ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        j = json.loads(p.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        raise Reject("the file could not be read as a video") from exc
    streams = j.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = j.get("format") or {}
    if not v:
        raise Reject("the file has no picture track: it is not a video")
    try:
        duration = float(fmt.get("duration") or v.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "format": str(fmt.get("format_name") or ""),
        "vcodec": str(v.get("codec_name") or ""),
        "pix_fmt": str(v.get("pix_fmt") or ""),
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "duration_s": round(duration, 2),
        "acodec": str((a or {}).get("codec_name") or ""),
        "has_audio": a is not None,
        "bytes": int(fmt.get("size") or 0) or int(path.stat().st_size),
    }


def channel_limits(channels: list[str]) -> tuple[int, int]:
    """(the shortest length, the smallest size) the chosen channels take. The repo carries one figure for every channel."""
    rows = [LIMITS[c] for c in channels if c in LIMITS] or list(LIMITS.values())
    return min(r["seconds"] for r in rows), min(r["bytes"] for r in rows)


def check_file(info: dict[str, Any], channels: list[str]) -> None:
    """Raises Reject with the reason for a file that cannot be posted to these channels."""
    if not any(f in info["format"] for f in MP4_FORMATS):
        raise Reject(f"the file is not an MP4 (its container is {info['format'] or 'unknown'})")
    if info["width"] <= 0 or info["height"] <= 0:
        raise Reject("the video has no picture size")
    if info["duration_s"] <= 0:
        raise Reject("the video has no length (0 seconds)")
    seconds, _ = channel_limits(channels)
    if info["duration_s"] > seconds:
        names = ", ".join(CHANNEL_NAMES.get(c, c) for c in channels)
        raise Reject(
            f"the video is {info['duration_s']:g} s, over the {seconds} s Semasa posts to {names} "
            f"(the longest short film it makes). Cut it to {seconds} s or less and send it again"
        )


def needs_copy(info: dict[str, Any], size: int) -> bool:
    """A platform-friendly copy is made unless the file already is one: H.264 in yuv420p, AAC or no sound, and within the
    posted size ceiling. (motion.social_copy also caps the bitrate; a file inside the ceiling needs no more.)"""
    return not (
        info["vcodec"] == H264
        and info["pix_fmt"] == "yuv420p"
        and (not info["has_audio"] or info["acodec"] == AAC)
        and size <= MAX_POSTED_BYTES
    )


# --- the caption ---------------------------------------------------------------------------------------------------------------


def texts_of(params: dict[str, Any], channels: list[str]) -> dict[str, str]:
    """{channel: caption} from the request: one text for every channel, or the object the sender gave (also as a JSON object in a
    string). Never altered."""
    cap = params.get("caption")
    if isinstance(cap, str) and cap.lstrip().startswith("{"):
        # a multipart form field is text, so a sender with a caption per channel sends the object as JSON in `caption`
        try:
            obj = json.loads(cap)
        except ValueError:
            obj = None
        if isinstance(obj, dict) and obj and all(k in CHANNEL_NAMES and isinstance(v, str) for k, v in obj.items()):
            cap = obj
    if isinstance(cap, dict):
        return {c: str(cap[c]).strip() for c in channels if str(cap.get(c) or "").strip()}
    text = str(cap or "").strip()
    return {c: text for c in channels} if text else {}


def draft_flags(
    stream: str,
    lang: str,
    texts: dict[str, str],
    channels: list[str],
    title: str,
    settings: dict[str, Any],
    info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """The page's own compliance scan over the caption, the title (read as the picture's alt text) and the language, for the
    stream's rules, plus what only an import knows."""
    reg = (settings.get("brand") or {}).get("regulab") or {}
    post = {
        "stream": stream,
        "lang": lang,
        "text": {lang: texts},
        "citation": "",
        "channels": channels,
        "media": [{"alt": title}],
        "hook": title,
    }
    flags = compliance.scan(post, brand=reg, schedule=reg.get("schedule"), indo_extra=(settings.get("bahasa") or {}).get("indo"))
    if not texts:
        flags.insert(
            0, {"hard": True, "where": "Caption", "msg": "no caption was sent with the video. Write it before approving"}
        )
    if info and stream == "regulab" and info["width"] >= info["height"]:
        flags.append(
            {
                "hard": False,
                "where": "Video",
                "msg": f"the film is {info['width']}x{info['height']}, not upright 9:16: no Reel on Instagram or Facebook",
            }
        )
    return flags


# --- a caption when none was sent -----------------------------------------------------------------------------------------------

IMPORT_NOTE = """THIS FILM WAS MADE OUTSIDE SEMASA. The TITLE line above is all anyone told us about it: the prompt or title its
sender used. It overrides the rules above that ask for a script, a source or a rule that decides it.
- Write a short, warm, plain caption about what the picture shows, from the TITLE and nothing else. Two or three sentences at most
  (Threads: one).
- Never invent anything: no number, name, brand, place, date, regulation, source, claim, health or safety statement that the TITLE
  does not already contain. If the TITLE is only a scene, describe the scene.
- No call to action, no "follow for more", no link, no website, no question that tells people to do something.
- The film's maker or tool ({made_by}) is not named in the caption.
- Hashtags: only the number given for the platform, plain words from the TITLE."""

# words that put a rule, a body or a guarantee in a caption: only allowed when the sender's own title already has them
CLAIM_WORDS = re.compile(
    r"\b(?:npra|jakim|kkm|moh|fda|sccs|hsa|akta|peraturan|regulation|regulations|directive|direktif|garis panduan|guideline|"
    r"guidelines|halal|sijil|certified|bersijil|dijamin|guaranteed|terbukti|proven|klinikal|clinical|selamat|safe)\b",
    re.I,
)
NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def invented(text: str, title: str) -> str:
    """Why a written caption is refused ('' when it is fine): it asks for something, sends the reader away, or brings in a
    number or a rule/claim word the sender's title does not contain. What an author could not know from a picture is the risk."""
    body = "\n".join(ln for ln in text.split("\n") if not ln.strip().startswith("#"))
    if motion_captions.follow_ask(text):
        return "it asks people to follow"
    if motion_captions.hand_off(text):
        return "it sends the reader away"
    have = title.lower()
    nums = {n for n in NUMBER.findall(body) if n not in title}
    if nums:
        return f"it states a number the title does not have ({sorted(nums)[0]})"
    for m in CLAIM_WORDS.finditer(body):
        if m.group(0).lower() not in have:
            return f"it states '{m.group(0)}', which the title does not"
    return ""


def plain_caption(title: str, stream: str, platform: str) -> str:
    """The safe caption: the sender's own title as a sentence, fitted to the platform. Nothing added."""
    t = " ".join(str(title or "").split())
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    if t[-1] not in ".!?":
        t += "."
    return motion_captions.fit(t, stream, platform)


def auto_captions(
    llm: Any,
    stream: str,
    lang: str,
    channels: list[str],
    title: str,
    source: str,
    settings: dict[str, Any],
) -> tuple[dict[str, str], str]:
    """({channel: caption}, who) for an import that came with no caption. `who` is 'semasa' when the Motion caption writer
    wrote at least one (from the title only), 'plain' when the plain caption from the title stands in, '' when there is no title.
    The writer's text is judged by the same compliance scan as any caption; one that breaks a rule is replaced by the plain
    caption. Never raises."""
    plain = {c: plain_caption(title, stream, c) for c in channels}
    plain = {c: t for c, t in plain.items() if t}
    if not plain:
        return {}, ""
    texts, written = dict(plain), 0
    if llm is not None:
        try:
            mark = motion_captions.from_script(title, [], stream)  # what write() answers when it could not write
            got = motion_captions.write(
                llm,
                {"stream": stream},
                [],
                title,
                lang=lang,
                voice=motion.voice_line(stream, lang),
                speak_as=motion.speaker(lang),
                note=IMPORT_NOTE.format(made_by=source or "an outside agent"),
            )
            for c in channels:
                t = str(got.get(c) or "").strip()
                if not t or t == mark.get(c):
                    continue
                why = invented(t, title)
                if why:
                    log.info("written caption for %s refused: %s", c, why)
                    continue
                texts[c], written = t, written + 1
        except Exception as exc:  # noqa: BLE001 - the plain caption stands in
            log.warning("import caption writer failed (%s)", str(exc)[:160])
            texts, written = dict(plain), 0
    if written and compliance.hard_count(draft_flags(stream, lang, texts, channels, title, settings)):
        texts, written = dict(plain), 0  # a rule is still broken: the plain caption, and Wan is flagged for what still blocks
    return texts, ("semasa" if written else "plain")


AUTHORED_FLAG = {
    "hard": False,
    "where": "Caption",
    "msg": "Semasa wrote this caption from the title only: read it before approving",
}
AUTHORED_ACTION = "caption written by Semasa from the title only (nothing else was sent); read it before approving"


# --- the slot ------------------------------------------------------------------------------------------------------------------


def slot_for(store: Any, stream: str, params: dict[str, Any], settings: dict[str, Any], now: datetime) -> tuple[str, str]:
    """The sender's date and slot when both were given and free and ahead, else the next free position (what comic_daily does)."""
    brand = settings.get("brand") or {}
    taken = ideas.taken_positions(store, stream, now) | autofill.film_positions(store, stream)
    date, slot = str(params.get("date") or ""), str(params.get("slot") or "")
    if date and slot:
        slots = sorted((brand.get(stream) or {}).get("slots") or [])
        if slots and slot not in slots:
            raise Reject(f"{slot} is not one of the {stream} slots ({', '.join(slots)})")
        try:
            at = datetime.fromisoformat(f"{date}T{slot}:00").replace(tzinfo=UTC) - MYT
        except ValueError as exc:
            raise Reject("date and slot are not a real moment") from exc
        if at <= now:
            raise Reject(f"{date} {slot} (Malaysia time) is already past")
        if (date, slot) in taken:
            raise Reject(f"the slot {date} {slot} already holds a post. Send another slot, or none for the next free one")
        return date, slot
    date, slot = ideas.next_free_position(stream, None, brand, taken, now)
    if not date or not slot:
        raise Reject("no free slot in the next 28 days")
    return date, slot


# --- one import ----------------------------------------------------------------------------------------------------------------


def _resolution(w: int, h: int) -> str:
    return "portrait" if h > w else "landscape" if w > h else "square"


def _title_of(params: dict[str, Any], row: dict[str, Any], texts: dict[str, str]) -> str:
    t = str(params.get("title") or "").strip()
    if t:
        return t[:160]
    first = next(iter(texts.values()), "")
    first = first.strip().split("\n", 1)[0].strip() if first else ""
    return (first[:80] or f"Video import ({str(row.get('source') or 'luar')[:40]})").strip()


def _shape(params: dict[str, Any]) -> tuple[str, str, list[str]]:
    """(stream, language, channels) an import asked for, with the defaults the intake applies."""
    stream = "linkedin" if params.get("stream") == "linkedin" else "regulab"
    lang = "en" if stream == "linkedin" else ("en" if params.get("lang") == "en" else "bm")
    # a film goes to Instagram (a Reel) and Facebook only, plus TikTok when asked (Wan, 22 Nov 2026); never Threads or LinkedIn
    plats = compliance.film_platforms_for(stream)
    asked = [c for c in (params.get("channels") or []) if c in plats]
    chosen = asked or list(plats)
    if "tiktok" in (params.get("channels") or []) and "instagram" in chosen:
        chosen.append("tiktok")
    return stream, lang, chosen


def process(
    store: Any,
    row: dict[str, Any],
    settings: dict[str, Any],
    *,
    storage: Storage | None = None,
    runner: Any = subprocess.run,
    get: Any = requests.get,
    resolve: Any = socket.getaddrinfo,
    notify: Any = None,
    now: datetime | None = None,
    llm: Any = None,
) -> str:
    """One import to its end: 'done' (a draft post waits for Wan) or 'error' (with the reason). Raises only for a failure worth
    trying again (the caller counts attempts); a Reject is final and is written here."""
    storage = storage or Storage(store)
    now = now or datetime.now(UTC)
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    stream, lang, channels = _shape(params)
    made: list[str] = []  # every file this import wrote: all of them go if it is rejected
    stored = str(row.get("stored_path") or "")
    try:
        if stored:
            made.append(stored)
        if not channels:
            raise Reject("a film goes only to Instagram (Reel), Facebook and TikTok, and the LinkedIn stream has none of them: "
                         "send it with stream regulab")
        try:
            data = storage.download(stored) if stored else fetch_url(str(row.get("source_url") or ""), get=get, resolve=resolve)
        except Reject:
            raise
        except Exception as exc:  # noqa: BLE001 - the file the function stored could not be read back
            if stored:
                raise RuntimeError(f"stored file not readable: {str(exc)[:120]}") from exc
            raise
        if not data or len(data) > MAX_FILE_BYTES:
            raise Reject(
                "the file is empty" if not data else f"the file is over {MAX_FILE_BYTES // 1_048_576} MB, the most Semasa stores"
            )
        if data[4:8] != b"ftyp":
            raise Reject("the file is not an MP4 (it has no ftyp header). Send H.264/AAC in an .mp4 container")
        texts = texts_of(params, channels)
        title = _title_of(params, row, texts)
        authored = ""
        if not texts and str(params.get("title") or "").strip():  # no caption sent: Semasa writes one, from that title alone
            texts, authored = auto_captions(llm, stream, lang, channels, title, str(row.get("source") or ""), settings)
        with tempfile.TemporaryDirectory(prefix="semasa-import-") as tmp:
            src = Path(tmp) / "import.mp4"
            src.write_bytes(data)
            info = probe(src, runner)
            check_file(info, channels)
            date, slot = slot_for(store, stream, params, settings, now)
            note: list[str] = []
            if not stored:  # a link: the file is kept in Semasa's own bucket from here on
                stored = f"imports/{row['id']}.mp4"
                video_url = storage.upload(stored, data, "video/mp4")
                made.append(stored)
            else:
                video_url = storage.url(stored)
            social_url, social_bytes = "", 0
            # the film goes in the shape its stream's platforms take (Wan, 20 Nov 2026): a 16:9 film from Hermes / Nous is fitted
            # over a blurred copy of itself now, so the draft Wan approves already is the film that is posted
            target = film_ratio.size_for(stream)
            fitting = not film_ratio.fits(info["width"], info["height"], target)
            if fitting:
                try:
                    small = film_ratio.fit_copy(src, Path(tmp) / "fitted.mp4", target)
                except Exception as exc:  # noqa: BLE001 - a film that cannot be put in the right shape is not posted
                    raise Reject(
                        f"the video is {info['width']}x{info['height']} and could not be fitted to {target[0]}x{target[1]} "
                        f"for the platforms ({str(exc)[:120]}). Send it in that shape and try again"
                    ) from exc
                social_bytes = small.stat().st_size
                _, ceiling = channel_limits(channels)
                if social_bytes > ceiling:
                    raise Reject(
                        f"the video is {social_bytes / 1_048_576:.0f} MB even after fitting, over the "
                        f"{ceiling // 1_048_576} MB limit. Make it shorter or smaller and send it again"
                    )
                path = f"imports/{row['id']}-social.mp4"
                social_url = storage.upload(path, small.read_bytes(), "video/mp4")
                made.append(path)
                note.append(
                    f"fitted from {info['width']}x{info['height']} to {target[0]}x{target[1]} for the platforms "
                    f"({social_bytes / 1_048_576:.1f} MB)"
                )
                info = {**info, "width": target[0], "height": target[1]}      # what is posted, from here on
            elif needs_copy(info, len(data)):
                small = motion.social_copy(src, runner)
                if small is None:
                    raise Reject(
                        "the video could not be converted to H.264/AAC for the platforms. Re-encode it and send it again"
                    )
                social_bytes = small.stat().st_size
                _, ceiling = channel_limits(channels)
                if social_bytes > ceiling:
                    raise Reject(
                        f"the video is {social_bytes / 1_048_576:.0f} MB even after compressing, over the "
                        f"{ceiling // 1_048_576} MB limit. Make it shorter or smaller and send it again"
                    )
                path = f"imports/{row['id']}-social.mp4"
                social_url = storage.upload(path, small.read_bytes(), "video/mp4")
                made.append(path)
                note.append(f"a platform copy was made ({social_bytes / 1_048_576:.1f} MB)")
            flags = draft_flags(stream, lang, texts, channels, title, settings, info)     # info is what is posted
            if authored:
                flags.append(dict(AUTHORED_FLAG))
            jpg = motion.poster(src, runner)
            poster_url = ""
            if jpg:
                made.append(f"imports/{row['id']}.jpg")
                poster_url = storage.upload(f"imports/{row['id']}.jpg", jpg, "image/jpeg")
        post_id = _make_draft(
            store,
            row,
            params,
            stream,
            lang,
            channels,
            texts,
            title,
            flags,
            date,
            slot,
            info,
            stored,
            video_url,
            social_url,
            social_bytes,
            poster_url,
            now,
            authored=authored,
        )
        blocking = compliance.hard_count(flags)
        if blocking:  # a caption that breaks a rule is the draft's to fix (Wan, 17 Nov 2026), never a reason to refuse the import
            note.append(f"the draft was made with {blocking} blocking flag(s) to fix before Wan can approve it")
        if not texts:
            note.append("no caption: write it before approving")
        if authored:
            note.append(
                "no caption was sent: Semasa wrote it from the title only"
                + (" (the writer was not used: a plain caption from the title)" if authored == "plain" else "")
                + "; read it before approving"
            )
        soft = [f"{f['where']}: {f['msg']}" for f in flags if not f["hard"]]
        if soft:
            note.append(f"{len(soft)} warning(s) on the draft")
        store.table(TABLE).update({"status": "done", "post_id": post_id, "error": "", "note": "; ".join(note)[:500]}).eq(
            "id", row["id"]
        ).execute()
        db.log_event(
            store,
            "info",
            "import",
            "import.drafted",
            f"Video import siap: {title[:80]} ({date} {slot}); menunggu Lulus anda",
            ref_table=db.POSTS,
            ref_id=post_id,
            detail={"import_id": row["id"], "source": row.get("source"), "date": date, "slot": slot},
        )
        told = f"Video import siap, menunggu lulus: {title[:100]} ({date} {slot}, {', '.join(channels)})"
        if blocking:
            told += f". {blocking} perkara menghalang Lulus: betulkan kapsyen di Semasa"
        elif authored:
            told += ". Kapsyen ditulis oleh Semasa daripada tajuk sahaja: baca dahulu sebelum Lulus"
        _tell(store, told, notify)
        return "done"
    except Reject as no:
        _reject(store, row, str(no), storage, made)
        return "error"


def _make_draft(
    store: Any,
    row: dict[str, Any],
    params: dict[str, Any],
    stream: str,
    lang: str,
    channels: list[str],
    texts: dict[str, str],
    title: str,
    flags: list[dict[str, Any]],
    date: str,
    slot: str,
    info: dict[str, Any],
    stored: str,
    video_url: str,
    social_url: str,
    social_bytes: int,
    poster_url: str,
    now: datetime,
    authored: str = "",
    recovered: bool = False,
) -> str:
    """The film row (already done), its media row and the DRAFT post, written in the order comic_daily.queue_post uses. A retry
    after a half-finished try reuses the film row the first try made."""
    src = {
        "source": row.get("source") or "",
        "idempotency_key": row.get("idempotency_key"),
        "token_label": row.get("token_label") or "",
        "import_id": row["id"],
    }
    stamp = now.isoformat()
    motion_id = row.get("motion_id")
    if not motion_id:
        film = (
            store.table(MOTIONS)
            .insert(
                {
                    "status": "done",
                    "brief": title,
                    "stream": stream,
                    "language": lang,
                    "resolution": _resolution(info["width"], info["height"]),
                    "seconds": max(3, min(60, round(info["duration_s"]))),
                    "title": title,
                    "video_path": stored,
                    "video_url": video_url,
                    "poster_url": poster_url,
                    "width": info["width"],
                    "height": info["height"],
                    "duration_s": info["duration_s"],
                    "bytes": int(info["bytes"]),
                    "social_url": social_url,
                    "social_bytes": social_bytes,
                    "model": "import",
                    "style_note": f"Imported video ({src['source'] or 'outside agent'}); made outside Semasa",
                    "captions": texts,
                    "options": {"template": "import", "via": "import", "import": src},
                    "stage": "done",
                }
            )
            .execute()
            .data[0]
        )
        motion_id = film["id"]
        store.table(TABLE).update({"motion_id": motion_id}).eq("id", row["id"]).execute()
    media = (
        store.table(db.MEDIA)
        .insert(
            {
                "reference_url": video_url,
                "generated_media_url": social_url or video_url,
                "type": "video",
                "status": "done",
                "mode": "clip",
                "prompt": title,
                "provider": "import",
                "model": "import",
                "meta": {
                    "flow": "import",
                    "import_id": row["id"],
                    "motion_id": motion_id,
                    "poster_url": poster_url,
                    "width": info["width"],
                    "height": info["height"],
                    "seconds": info["duration_s"],
                    "bytes": social_bytes if social_url else int(info["bytes"]),
                    "compressed": bool(social_url),
                    "alt": title,
                    "source": src["source"],
                },
            }
        )
        .execute()
        .data[0]
    )
    post = {
        "stream": stream,
        "lang": lang,
        "hook": title[:300],
        "text": {lang: texts},
        "citation": "",
        "media_ids": [media["id"]],
        "date": date,
        "slot": slot,
        "status": "draft",
        "channels": channels,
        "created_by": None,
        "decisions": [
            {
                "at": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "by": "worker",
                "action": f"imported video ({src['source'] or 'outside agent'}); a draft, waiting for Wan's Approve",
            },
            *([{"at": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "by": "worker", "action": RECOVERED_ACTION}] if recovered else []),
            *([{"at": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "by": "worker", "action": AUTHORED_ACTION}] if authored else []),
        ],
    }
    post["flags"], post["hard_flags"] = flags, compliance.hard_count(flags)
    try:
        made = store.table(db.POSTS).insert(post).execute().data[0]
    except Exception:
        store.table(db.MEDIA).delete().eq("id", media["id"]).execute()  # no orphan picture row behind a refused post
        raise
    store.table(db.MEDIA).update({"post_id": made["id"]}).eq("id", media["id"]).execute()
    store.table(MOTIONS).update({"queued_post_id": made["id"], "queued_at": stamp}).eq("id", motion_id).execute()
    return str(made["id"])


def _reject(store: Any, row: dict[str, Any], reason: str, storage: Storage, made: list[str]) -> None:
    """The import ends as `error` with its reason, and every file it wrote is deleted (a rejected file is not left public)."""
    try:
        if made:
            storage.remove(sorted(set(made)))
    except Exception as exc:  # noqa: BLE001
        log.info("rejected files not removed (%s)", str(exc)[:120])
    store.table(TABLE).update({"status": "error", "error": reason[:600], "stored_path": ""}).eq("id", row["id"]).execute()
    db.log_event(
        store,
        "warn",
        "import",
        "import.rejected",
        f"Video import ditolak: {reason[:160]}",
        ref_table=TABLE,
        ref_id=row["id"],
        detail={"source": row.get("source"), "token": row.get("token_label")},
    )


def _tell(store: Any, text: str, notify: Any = None) -> None:
    """A Telegram message to Wan, only when the bot is linked. Never raises."""
    try:
        if notify is not None:
            notify(store, text)
        else:
            from . import telegram_bot

            telegram_bot.notify(store, text)
    except Exception as exc:  # noqa: BLE001
        log.info("import not announced on Telegram (%s)", str(exc)[:120])


# --- an import whose draft is gone ----------------------------------------------------------------------------------------------

RECOVER_WITHIN = timedelta(days=7)
MAX_RECOVER = 2  # drafts made again in one run
RECOVERED_TAG = "[draft made again"  # at the front of the import row's `note`: the one recovery an import gets
RECOVERED_ACTION = "draft made again from the stored film (the first draft was removed); a draft, waiting for Wan's Approve"


def _post_exists(store: Any, post_id: Any) -> bool:
    if not post_id:
        return False
    return bool(store.table(db.POSTS).select("id").eq("id", post_id).limit(1).execute().data)


def fitted_for_recovery(store: Any, video_url: str, info: dict[str, Any], stream: str, social_url: str,
                        social_bytes: int) -> tuple[dict[str, Any], str, int]:
    """A draft made again from an older import carries the film in the shape the stream's platforms take (Wan, 21 Nov 2026:
    "make sure the ratio of the film sent by Hermes Nous follows each platform before it posts"). An import made before the
    fitting existed is stored in its maker's shape (usually 16:9), so it is fitted now, from the original. A film already in
    shape is left alone, and one that cannot be fitted here keeps its stored address: the publisher fits it again before any
    send."""
    target = film_ratio.size_for(stream)
    if not (info.get("width") and info.get("height")) or film_ratio.fits(info["width"], info["height"], target):
        return info, social_url, social_bytes
    try:
        got = film_ratio.for_stream(store, {"url": video_url, "width": info["width"], "height": info["height"]}, stream)
    except Exception as exc:  # noqa: BLE001 - the draft is still made; the publisher fits the film before it sends
        log.warning("import recovery: film not fitted (%s); the publisher fits it before any send", str(exc)[:120])
        return info, social_url, social_bytes
    if got.get("url") == video_url:
        return info, social_url, social_bytes
    return {**info, "width": target[0], "height": target[1]}, str(got["url"]), 0


def _recover_one(store: Any, row: dict[str, Any], settings: dict[str, Any], now: datetime, notify: Any, llm: Any) -> bool:
    """One `done` import whose draft post is gone gets its draft again, once. False when there was nothing to do."""
    if RECOVERED_TAG in str(row.get("note") or "") or not row.get("motion_id") or _post_exists(store, row.get("post_id")):
        return False
    film = (store.table(MOTIONS).select("*").eq("id", row["motion_id"]).limit(1).execute().data or [None])[0]
    if not film or film.get("status") != "done" or not film.get("video_url") or _post_exists(store, film.get("queued_post_id")):
        return False
    for m in store.table(db.MEDIA).select("id,post_id").eq("meta->>import_id", row["id"]).execute().data or []:
        if _post_exists(store, m.get("post_id")):
            return False  # a post still carries this film
    params = row.get("params") if isinstance(row.get("params"), dict) else {}
    stream, lang, channels = _shape(params)
    if not channels:
        return False  # a LinkedIn film has no platform a film may go to (Wan, 22 Nov 2026)
    title = str(film.get("title") or film.get("brief") or params.get("title") or "").strip()[:160]
    kept = film.get("captions") if isinstance(film.get("captions"), dict) else {}
    texts, authored = {c: str(kept[c]).strip() for c in channels if str(kept.get(c) or "").strip()}, ""
    if not texts and title:
        texts, authored = auto_captions(llm, stream, lang, channels, title, str(row.get("source") or ""), settings)
    info = {
        "width": int(film.get("width") or 0),
        "height": int(film.get("height") or 0),
        "duration_s": float(film.get("duration_s") or 0),
        "bytes": int(film.get("bytes") or 0),
    }
    social_url, social_bytes = str(film.get("social_url") or ""), int(film.get("social_bytes") or 0)
    info, social_url, social_bytes = fitted_for_recovery(
        store, str(film.get("video_url")), info, stream, social_url, social_bytes)
    flags = draft_flags(stream, lang, texts, channels, title, settings, info)
    if authored:
        flags.append(dict(AUTHORED_FLAG))
    date, slot = slot_for(store, stream, {}, settings, now)
    note = f"{RECOVERED_TAG} {now.strftime('%Y-%m-%d')}] {str(row.get('note') or '')}"[:500]
    # the marker is written BEFORE the draft: whatever happens next, this import is never recovered a second time
    store.table(TABLE).update({"note": note}).eq("id", row["id"]).eq("status", "done").execute()
    post_id = _make_draft(
        store,
        {**row, "note": note},
        params,
        stream,
        lang,
        channels,
        texts,
        title,
        flags,
        date,
        slot,
        info,
        str(film.get("video_path") or row.get("stored_path") or ""),
        str(film.get("video_url")),
        social_url,
        social_bytes,
        str(film.get("poster_url") or ""),
        now,
        authored=authored,
        recovered=True,
    )
    store.table(TABLE).update({"post_id": post_id}).eq("id", row["id"]).execute()
    if authored:
        store.table(MOTIONS).update({"captions": texts}).eq("id", film["id"]).execute()
    db.log_event(
        store,
        "info",
        "import",
        "import.recovered",
        f"Video import dibuat semula sebagai draf: {title[:80]} ({date} {slot}); menunggu Lulus anda",
        ref_table=db.POSTS,
        ref_id=post_id,
        detail={"import_id": row["id"], "source": row.get("source"), "date": date, "slot": slot},
    )
    blocking = compliance.hard_count(flags)
    told = f"Video import dibuat semula sebagai draf, menunggu lulus: {title[:100]} ({date} {slot}, {', '.join(channels)})"
    if blocking:
        told += f". {blocking} perkara menghalang Lulus: betulkan kapsyen di Semasa"
    elif authored:
        told += ". Kapsyen ditulis oleh Semasa daripada tajuk sahaja: baca dahulu sebelum Lulus"
    _tell(store, told, notify)
    return True


def recover_missing_drafts(
    store: Any, settings: dict[str, Any] | None = None, now: datetime | None = None, *, notify: Any = None, llm: Any = None
) -> int:
    """Imports that finished (`done`) in the last 7 days whose draft post was removed get their draft again from the stored film,
    with the written captions, on the next free slot and a Telegram message: once per import (the import row's `note` carries
    the mark). Idempotent; never raises. Returns the number of drafts made."""
    now = now or datetime.now(UTC)
    made = 0
    try:
        settings = settings if settings is not None else ideas.load_settings(store)
        rows = (
            store.table(TABLE)
            .select("*")
            .eq("status", "done")
            .gte("created_at", (now - RECOVER_WITHIN).isoformat())
            .order("created_at", desc=True)  # newest first: the oldest 50 would hide a newer import whose draft is missing
            .limit(50)
            .execute()
            .data
            or []
        )
        for r in rows:
            if made >= MAX_RECOVER:
                break
            try:
                made += _recover_one(store, r, settings, now, notify, llm)
            except Exception as exc:  # noqa: BLE001 - one import's trouble never stops the others
                log.warning("import %s draft not recovered (%s)", r.get("id"), str(exc)[:200])
    except Exception as exc:  # noqa: BLE001
        log.warning("import recovery step failed (%s)", str(exc)[:200])
    return made


# --- the step ------------------------------------------------------------------------------------------------------------------


def claim(store: Any, limit: int = MAX_PER_RUN) -> list[dict[str, Any]]:
    rows = store.table(TABLE).select("*").eq("status", "received").order("created_at").limit(limit).execute().data or []
    got = []
    for r in rows:
        res = (
            store.table(TABLE)
            .update({"status": "working", "attempts": int(r.get("attempts") or 0) + 1})
            .eq("id", r["id"])
            .eq("status", "received")
            .execute()
        )
        if res.data:
            got.append(res.data[0])
    return got


def run(store: Any, settings: dict[str, Any] | None = None, now: datetime | None = None, **kw: Any) -> str:
    """Motion's hook: put back what a dead runner left, then check up to MAX_PER_RUN received imports. One log line, "" when there
    was nothing. Never raises."""
    now = now or datetime.now(UTC)
    out: list[str] = []
    try:
        settings = settings if settings is not None else ideas.load_settings(store)
        db.requeue_stale(
            store,
            TABLE,
            working="working",
            back="received",
            cutoff=(now - STALE_AFTER).isoformat(),
            max_attempts=MAX_ATTEMPTS,
            what="import",
        )
        done = failed = 0
        for row in claim(store):
            try:
                verdict = process(store, row, settings, now=now, **kw)
            except Exception as exc:  # noqa: BLE001 - worth trying again, up to MAX_ATTEMPTS
                log.warning("import %s not finished (%s)", row["id"], str(exc)[:200])
                if int(row.get("attempts") or 1) >= MAX_ATTEMPTS:
                    store.table(TABLE).update(
                        {"status": "error", "error": f"could not be finished after {MAX_ATTEMPTS} tries: {str(exc)[:200]}"}
                    ).eq("id", row["id"]).execute()
                    failed += 1
                else:
                    store.table(TABLE).update({"status": "received", "error": f"will try again: {str(exc)[:200]}"}).eq(
                        "id", row["id"]
                    ).execute()
                continue
            done += verdict == "done"
            failed += verdict == "error"
        if done:
            out.append(f"{done} import(s) drafted")
        if failed:
            out.append(f"{failed} import(s) refused")
        again = recover_missing_drafts(store, settings, now, notify=kw.get("notify"), llm=kw.get("llm"))
        if again:
            out.append(f"{again} draft(s) made again")
    except Exception as exc:  # noqa: BLE001
        log.warning("video import step failed (%s)", str(exc)[:200])
        out.append("error")
    return "; ".join(out)
