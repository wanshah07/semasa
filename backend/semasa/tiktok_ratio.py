"""TikTok takes an upright 9:16 film (Wan, 20 Nov 2026: "fix ratio tiktok for film come from hermes nous").

A film that arrives from outside Semasa (Hermes / Nous through the import route, or `zernio_publish`) is whatever shape its
maker gave it, usually 16:9 (Nexabot's web route makes 1280x720). TikTok shows that as a small strip in the middle of the
screen. This makes an upright copy for TikTok only: the whole picture across the width over a blurred, darkened copy of itself
(the same fit the reference clips use, video.filter_graph), 1080x1920. The other platforms keep the film as it came. A film that
is already 9:16 is left alone and nothing is copied.

The copy lives in the public bucket semasa-generated under tiktok/<hash of the film's address>.mp4, so a second send of the same
film (a retry, a re-send) reuses it and never converts twice.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from . import db, senders, video
from .log import get_logger

log = get_logger("semasa.tiktok_ratio")

W, H = 1080, 1920
TARGET = 9 / 16
TOLERANCE = 0.03            # 9:16 within three per cent counts as 9:16 (1080x1920, 720x1280, 1080x1918)
MAX_IN_BYTES = 120 * 1024 ** 2
MAX_OUT_BYTES = 48 * 1024 * 1024      # the semasa-generated bucket takes 50 MB a file

GRAPH = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},gblur=sigma=28,"
         f"eq=brightness=-0.12[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
         "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")


def is_nine_sixteen(width: int, height: int) -> bool:
    return width > 0 and height > 0 and abs(width / height - TARGET) <= TARGET * TOLERANCE


def size_of(path: Path) -> tuple[int, int] | None:
    """(width, height) of the first video stream, read from ffmpeg's own banner; None when it cannot be read."""
    p = subprocess.run([video.ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True, timeout=120)
    for line in (p.stderr or "").splitlines():
        if "Video:" in line:
            m = re.search(r"[ ,](\d{2,5})x(\d{2,5})[ ,\[]", line + " ")
            if m:
                return int(m.group(1)), int(m.group(2))
    return None


def vertical_copy(src: Path, out: Path) -> Path:
    """The upright copy: the picture fitted over a blurred copy of itself, sound kept, no larger than the bucket takes."""
    cmd = [video.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-filter_complex", GRAPH, "-map", "[v]",
           "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", "128k", "-movflags", "+faststart", "-fs", str(MAX_OUT_BYTES), str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if p.returncode != 0 or not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError(f"ffmpeg could not make the upright copy ({(p.stderr or '')[-200:].strip()})")
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


def for_tiktok(store: Any, film: dict[str, Any]) -> dict[str, Any]:
    """The film as TikTok should receive it: the same dict when it is already 9:16, else one pointing at the upright copy.
    Raises senders.SendError("transient", ...) when the copy cannot be made, so a landscape film is never sent to TikTok."""
    url = str(film.get("url") or "")
    if not url:
        raise senders.SendError("refused", "tiktok: the film has no address")
    name = f"tiktok/{hashlib.sha1(url.encode()).hexdigest()[:20]}.mp4"
    public = str(store.storage.from_(db.GENERATED_BUCKET).get_public_url(name))
    if _exists(public):
        return {**film, "url": public, "vertical": True}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            src = _download(url, Path(tmp) / "in.mp4")
            size = size_of(src)
            if size and is_nine_sixteen(*size):
                return {**film, "vertical": True}
            made = vertical_copy(src, Path(tmp) / "out.mp4")
            got = db.upload_generated(store, name, made.read_bytes(), "video/mp4")
        log.info("tiktok ratio: %s (%s) -> %s", url[:80], f"{size[0]}x{size[1]}" if size else "size unknown", got)
        return {**film, "url": got, "vertical": True}
    except senders.SendError:
        raise
    except Exception as exc:  # noqa: BLE001 - nothing wrong-shaped goes to TikTok
        why = str(exc)[:200]
        raise senders.SendError("transient", f"tiktok: the upright copy of the film could not be made ({why})") from exc
