"""Wan's own picture, used as it is (Studio: "upload a card or a photo into the post", brought over 27 Sep 2026).

The page puts the file in the reference bucket and queues a `mode: "upload"` job on the post (supabase/022). This step
checks it is really a picture, turns it the right way up, makes it a clean JPEG no longer than MAX_EDGE on its long
side (every network takes that; a 50 MB phone photo is not a post picture), hosts it in `semasa-generated`, where an
address never expires, attaches it to the draft and removes the temporary copy. Studio held such a picture until a
release run had hosted it; here it is hosted for good the moment it arrives. No AI is involved and nothing is paid for.
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime
from typing import Any

from PIL import Image

from . import db
from .fetch import get
from .images import open_upright
from .log import get_logger
from .providers import Generated

log = get_logger("semasa.own_picture")

MAX_EDGE = 2160
MAX_BYTES = 50 * 1024 * 1024
REFERENCE_BUCKET = "semasa-reference"


class NotAPicture(ValueError):
    pass


def normalise(data: bytes) -> tuple[bytes, dict[str, Any]]:
    """Any picture Pillow can open → an upright RGB JPEG, long edge at most MAX_EDGE. Transparency is laid on white,
    which is what every network would do to it anyway, but here Wan sees the result before it is posted."""
    if not data:
        raise NotAPicture("the file is empty")
    if len(data) > MAX_BYTES:
        raise NotAPicture("the file is over 50 MB")
    try:
        img = open_upright(data)
        img.load()
    except Exception as exc:  # noqa: BLE001 - whatever Pillow cannot open is not a picture here
        raise NotAPicture(f"this file is not a picture Semasa can read ({type(exc).__name__})") from exc
    w0, h0 = img.size
    if getattr(img, "n_frames", 1) > 1:
        img.seek(0)                      # an animated GIF posts as its first frame
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, (255, 255, 255))
        base.paste(rgba, mask=rgba.split()[-1])
        img = base
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "JPEG", quality=90, optimize=True, progressive=True)
    return out.getvalue(), {"width": img.size[0], "height": img.size[1], "original_size": [w0, h0]}


def process(store: Any, row: dict[str, Any], max_attempts: int = 3) -> bool:
    row_id = row["id"]
    meta = dict(row.get("meta") or {})
    try:
        url = row.get("reference_url")
        if not url:
            raise NotAPicture("no file came with this job")
        data, info = normalise(get(url, timeout=60).content)
        day = datetime.now(UTC).strftime("%Y/%m")
        gen = Generated(data=data, content_type="image/jpeg", model="own")
        path = f"{day}/{row_id}.{gen.extension}"
        public = db.upload_generated(store, path, data, gen.content_type)
        meta.update(info, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), content_type="image/jpeg",
                    generated_path=path, own=True, finished_at=datetime.now(UTC).isoformat())
        ref = row.get("reference_path")
        db.finish_media(store, row_id, status="done", generated_media_url=public, provider="own", model="own",
                        error=None, meta=meta, reference_path=None)
        if ref:
            try:
                store.storage.from_(REFERENCE_BUCKET).remove([ref])      # the hosted copy is the one that stays
            except Exception as exc:  # noqa: BLE001 - a leftover temporary file harms nothing
                log.info("%s: temporary copy not removed: %s", row_id, str(exc)[:120])
        if row.get("post_id"):
            db.attach_media_to_draft(store, row["post_id"], row_id)
        log.info("%s: own picture hosted → %s (%dx%d)", row_id, public, info["width"], info["height"])
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, NotAPicture) or attempts >= max_attempts
        msg = f"{type(exc).__name__}: {str(exc)[:600]}"
        log.error("%s: %s (attempt %d)", row_id, msg, attempts)
        db.finish_media(store, row_id, status="error" if final else "pending", error=msg, provider="own")
        return False
