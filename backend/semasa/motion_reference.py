"""A reference video as the STYLE of a Motion film (Wan, 10 Nov 2026: "easy to make motion from reference video, or repo, or
link"; asked what a reference video is for, he chose "copy its style").

The video is watched, never reused: it is fetched (yt-dlp for a YouTube/TikTok/Instagram/Facebook link, a plain download for a
file or a Google Drive link), a few frames are taken at even moments, the cuts are counted for its pace, and the picture reader
describes each frame (palette, type, layout, on-screen devices). What comes back is a block of words handed to the film's writer
as a STYLE REFERENCE, exactly like a motion repo's: none of the video's footage, sound, words or logos goes into the new film.
Everything here fails soft: a video that cannot be fetched or read gives no style and one note, and the film is still made.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from . import video
from .hook_styles import shrink
from .log import get_logger

log = get_logger("semasa.motion_reference")

MAX_SECONDS = 600                 # a reference longer than ten minutes is read for its first ten
FRAMES = 6
VIDEO_HOSTS = ("youtube.com", "youtu.be", "tiktok.com", "instagram.com", "facebook.com", "fb.watch", "vimeo.com",
               "drive.google.com", "docs.google.com")
VIDEO_FILE = re.compile(r"\.(mp4|mov|webm|m4v|mkv)(\?|#|$)", re.I)
REPO = re.compile(r"^https?://(www\.)?github\.com/[\w.-]+/[\w.-]+/?", re.I)

READ_SYSTEM = ("You describe ONE frame of a short social video so a motion designer can make a NEW film in the same visual "
               "style. Describe the look only. Never transcribe names, brands, logos, faces or claims as things to reuse.")
READ_PROMPT = ('Answer with ONE JSON object: {"palette": ["#hex", ...up to 5, background first], "type": "the lettering: '
               'weight, case, size on screen, serif or sans, colour, outline or highlight", "layout": "where the words and the '
               'picture sit, margins, cards or panels", "devices": "captions, stickers, arrows, progress bar, split screen, '
               'cut-outs, emoji, icons, charts", "picture": "photo, screen recording, talking head, illustration, 3D, flat '
               'graphics", "mood": "three words"}')


def kind_of(url: Any) -> str:
    """'repo' (a GitHub repo), 'video' (a video site, a Drive link or a video file), 'page' (any other link), '' (no link)."""
    u = str(url or "").strip()
    if not re.match(r"^https?://\S+$", u):
        return ""
    if REPO.match(u):
        return "repo"
    host = re.sub(r"^https?://(www\.|m\.)?", "", u).split("/")[0].lower()
    if VIDEO_FILE.search(u) or any(host == h or host.endswith("." + h) for h in VIDEO_HOSTS):
        return "video"
    return "page"


def fetch(url: str, folder: Path) -> Path:
    """The reference video as a local file. Raises video.VideoError with a plain reason."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / "reference.mp4"
    if video.is_drive(url) or VIDEO_FILE.search(url):
        return video.download_link(url, dest)
    import yt_dlp
    opts = video._ydl_opts({"outtmpl": str(folder / "reference.%(ext)s"), "format": "mp4[height<=720]/best[height<=720]/best",
                            "noplaylist": True, "max_filesize": 400 * 1024 ** 2})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return Path(ydl.prepare_filename(info))
    except Exception as exc:  # noqa: BLE001 - a private, removed or login-walled video
        raise video.VideoError(f"the reference video could not be fetched ({str(exc)[:160]})") from exc


def frames(path: Path, folder: Path, seconds: float, n: int = FRAMES, runner: Any = subprocess.run) -> list[Path]:
    """`n` frames at even moments (never the very first or last, which are often black or an end card)."""
    out = []
    for i in range(n):
        at = seconds * (i + 0.5) / n
        shot = folder / f"ref-{i + 1}.jpg"
        runner([video.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at:.2f}", "-i", str(path), "-frames:v", "1",
                "-vf", "scale=720:-2", str(shot)], capture_output=True, text=True, timeout=120)
        if shot.exists() and shot.stat().st_size > 0:
            out.append(shot)
    return out


def cuts(path: Path, seconds: float, runner: Any = subprocess.run) -> int | None:
    """How many hard cuts the video has (ffmpeg's scene score over 0.3), or None when it could not be counted."""
    try:
        p = runner([video.ffmpeg(), "-hide_banner", "-t", str(int(seconds)), "-i", str(path), "-vf",
                    "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"], capture_output=True, text=True, timeout=300)
    except Exception:  # noqa: BLE001
        return None
    return len(re.findall(r"pts_time:", p.stderr or "")) if p.returncode == 0 else None


def pace(seconds: float, n_cuts: int | None) -> str:
    if not n_cuts:
        return f"{seconds:.0f} s long; cuts could not be counted" if n_cuts is None else f"{seconds:.0f} s in one continuous shot"
    each = seconds / (n_cuts + 1)
    speed = "very fast" if each < 1.5 else "fast" if each < 3 else "medium" if each < 6 else "slow"
    return f"{seconds:.0f} s long, about {n_cuts} cuts: a new shot every {each:.1f} s ({speed} pace)"


def style_text(seen: list[dict[str, Any]], pace_line: str) -> str:
    """The reader's frame notes as one STYLE block for the writer."""
    def uniq(key: str, most: int) -> list[str]:
        out: list[str] = []
        for s in seen:
            v = " ".join(str(s.get(key) or "").split())[:200]
            if v and v.lower() not in {o.lower() for o in out}:
                out.append(v)
        return out[:most]
    colours: list[str] = []
    for s in seen:
        for c in s.get("palette") or []:
            c = str(c).strip().lower()
            if re.fullmatch(r"#[0-9a-f]{6}", c) and c not in colours:
                colours.append(c)
    lines = [f"PACE: {pace_line}. Match it: scene lengths and how often the picture changes."]
    if colours:
        lines.append("PALETTE (as hex, background first): " + ", ".join(colours[:8]))
    for label, key, most in (("LETTERING", "type", 3), ("LAYOUT", "layout", 3), ("ON-SCREEN DEVICES", "devices", 4),
                             ("KIND OF PICTURE", "picture", 3), ("MOOD", "mood", 3)):
        got = uniq(key, most)
        if got:
            lines.append(f"{label}: " + " | ".join(got))
    return "\n".join(lines)


def style(url: str, folder: Path, llm: Any, *, runner: Any = subprocess.run, fetcher: Any = None) -> tuple[str, str, str]:
    """(name, style text, note) for a reference video. ('', '', why) when it gave no style; never raises."""
    try:
        path = (fetcher or fetch)(url, folder)
        seconds = min(float(video.probe_duration(path) or 0) or 30.0, MAX_SECONDS)
        shots = frames(path, folder, seconds, runner=runner)
        if not shots:
            return "", "", "the reference video gave no frames"
        seen = []
        for shot in shots:
            data, mime = shrink(shot.read_bytes())
            got = llm.describe_image(READ_SYSTEM, READ_PROMPT, data, mime, max_tokens=500) if llm is not None else None
            if isinstance(got, dict):
                seen.append(got)
        if not seen:
            return "", "", "no picture reader could read the reference video's frames (set one in the AI tab)"
        text = style_text(seen, pace(seconds, cuts(path, seconds, runner=runner)))
        return "the reference video", text, f"reference video read: {len(seen)} of {len(shots)} frames"
    except Exception as exc:  # noqa: BLE001 - the film is still made, in the default look
        log.info("reference video not used (%s): %s", url, str(exc)[:160])
        return "", "", f"the reference video was not used: {str(exc)[:200]}"
