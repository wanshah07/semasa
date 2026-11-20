"""A film is posted in the shape its platform takes (Wan, 20 Nov 2026: "fix all import film especially from hermes nous, so before
post make sure follow platform ratio which is already set in semasa").

The shape is the one Semasa already sets per stream (motion.PLATFORM_SIZE): ws.regulab posts upright 9:16 (Instagram and Facebook
Reels, Threads, TikTok), LinkedIn square 1:1. A film that arrives from outside Semasa (Hermes / Nous through the import route,
or `zernio_publish`) is whatever shape its maker gave it, usually 16:9 (Nexabot's web route makes 1280x720), which a platform
shows as a small strip. This makes a copy in the right shape: the whole picture across the width over a blurred, darkened copy of
itself (the same fit the reference clips use, video.filter_graph). A film already in the shape is left alone, nothing copied.

Three places call it: the import worker (the draft's film is already right when Wan sees it), the publisher (before any send, for
a film imported before this existed or one that skipped the worker) and `zernio_publish` (Hermes handing a finished film over).
A copy lives in the public bucket semasa-generated under ratio/<WxH>/<hash of the film's address>.mp4, so a second send of the
same film (a retry, a re-send) reuses it and never converts twice.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import db, motion, senders, video
from .log import get_logger

log = get_logger("semasa.film_ratio")

TOLERANCE = 0.03            # within three per cent of the shape counts as the shape (1080x1920, 720x1280, 1080x1918)
MAX_IN_BYTES = 120 * 1024 ** 2
MAX_OUT_BYTES = 48 * 1024 * 1024      # the semasa-generated bucket takes 50 MB a file


def size_for(stream: str | None) -> tuple[int, int]:
    """The frame the stream's platforms take, from the table the rest of Semasa uses (motion.PLATFORM_SIZE)."""
    return motion.SIZES[motion.PLATFORM_SIZE.get(stream or "regulab", "portrait")]


def fits(width: int, height: int, size: tuple[int, int]) -> bool:
    w, h = size
    return width > 0 and height > 0 and abs(width / height - w / h) <= (w / h) * TOLERANCE


def graph(size: tuple[int, int]) -> str:
    w, h = size
    return (f"[0:v]split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},gblur=sigma=28,"
            f"eq=brightness=-0.12[bg];[b]scale={w}:{h}:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")


def size_of(path: Path) -> tuple[int, int] | None:
    """(width, height) of the first video stream, read from ffmpeg's own banner; None when it cannot be read."""
    p = subprocess.run([video.ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=120)
    for line in (p.stderr or "").splitlines():
        if "Video:" in line:
            m = re.search(r"[ ,](\d{2,5})x(\d{2,5})[ ,\[]", line + " ")
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


def fit_copy(src: Path, out: Path, size: tuple[int, int]) -> Path:
    """The copy in the platform's shape: the picture fitted over a blurred copy of itself, H.264 + AAC (so it is also the platform
    copy), sound kept, the bitrate capped so a 90 s film stays inside the bucket."""
    cmd = [video.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
           "-filter_complex", graph(size), "-map", "[v]", "-map", "0:a?",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "4500k", "-bufsize", "9000k",
           "-profile:v", "high", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
           "-movflags", "+faststart", "-fs", str(MAX_OUT_BYTES), str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0 or not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError(f"ffmpeg could not fit the film to {size[0]}x{size[1]} ({(p.stderr or '')[-200:].strip()})")
    return out


def _download(url: str, dest: Path) -> Path:
    import requests
    got = 0
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                got += len(chunk)
                if got > MAX_IN_BYTES:
                    raise RuntimeError("the film is over 120 MB")
                fh.write(chunk)
    return dest


def _exists(url: str) -> bool:
    import requests
    try:
        return requests.head(url, timeout=30, allow_redirects=True).status_code == 200
    except Exception:  # noqa: BLE001
        return False


def for_stream(store: Any, film: dict[str, Any], stream: str | None) -> dict[str, Any]:
    """The film as the stream's platforms should receive it: the same dict when it is already in their shape, else one pointing
    at the fitted copy. Raises senders.SendError("transient", ...) when the copy cannot be made, so a film of the wrong shape
    is never sent. A film whose own size is known (`width` and `height`, from the media row) is judged without a download."""
    size = size_for(stream)
    url = str(film.get("url") or "")
    if not url:
        raise senders.SendError("refused", "the film has no address")
    known = (int(film.get("width") or 0), int(film.get("height") or 0))
    if known[0] and known[1] and fits(*known, size):
        return {**film, "vertical": size[1] > size[0]}
    name = f"ratio/{size[0]}x{size[1]}/{hashlib.sha1(url.encode()).hexdigest()[:20]}.mp4"
    public = str(store.storage.from_(db.GENERATED_BUCKET).get_public_url(name))
    if _exists(public):
        return {**film, "url": public, "width": size[0], "height": size[1], "vertical": size[1] > size[0]}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = _download(url, Path(tmp) / "in.mp4")
            seen = size_of(src)
            if seen and fits(*seen, size):
                return {**film, "width": seen[0], "height": seen[1], "vertical": size[1] > size[0]}
            made = fit_copy(src, Path(tmp) / "out.mp4", size)
            got = db.upload_generated(store, name, made.read_bytes(), "video/mp4")
        was = f"{seen[0]}x{seen[1]}" if seen else "size unknown"
        log.info("film ratio: %s (%s) -> %sx%s %s", url[:80], was, size[0], size[1], got)
        return {**film, "url": got, "width": size[0], "height": size[1], "vertical": size[1] > size[0]}
    except senders.SendError:
        raise
    except Exception as exc:  # noqa: BLE001 - nothing wrong-shaped goes to a platform
        why = str(exc)[:200]
        raise senders.SendError("transient", f"the film could not be fitted to {size[0]}x{size[1]} ({why})") from exc
