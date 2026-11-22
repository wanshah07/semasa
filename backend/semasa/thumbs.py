"""Small copies of stored pictures for the page's library tiles (Wan, 22 Nov 2026: "Fix what you recommend", after an egress
audit). The Image and Poster libraries drew every tile from the full picture: an OpenAI PNG is often 2 MB, the average stored
picture 0.9 MB (323 of them on 22 Nov 2026, 289 MB), and a tile is about 150 px wide.

Each picture stored in `semasa-generated` gets a JPEG at THUMB_PATH, short side THUMB_PX, written by db.upload_generated from the
bytes it already holds (no download, no extra egress). The address is DERIVED from the picture's own, so no row has to carry it:
    <path>              2026/11/abc.png
    thumbs/<path>.jpg   thumbs/2026/11/abc.png.jpg
The page builds the same address (web/src/lib/thumbs.js) and falls back to the full picture when the small one does not load,
so a picture with no thumbnail yet (or a failed one) shows exactly as before.

Supabase's own image transformations (/storage/v1/render/image/...) also work on this project (Pro plan, checked 22 Nov 2026:
197 KB -> 55 KB at width 400), but they are metered: 100 origin images a month are included, then a charge per 1,000. A file of
our own costs nothing but ~30 KB of storage, so that is the route; the render endpoint is not used.

No delete has to know about thumbnails: the orphan sweep (archive.sweep_orphans) keeps one exactly as long as its picture is
named somewhere, so when a post's pictures are purged or a row is deleted, the small copy goes with the next sweep a day later.
`backfill` makes the missing ones for pictures stored before this existed; housekeeping runs it daily, BACKFILL_CAP a run (each
is one download of the full picture, once)."""

from __future__ import annotations

import io
from typing import Any

from .log import get_logger

log = get_logger("semasa.thumbs")

THUMB_PX = 400            # the short side: a tile is square and object-cover, at most ~160 CSS px on a 2-3x screen
LONG_MAX = 1200           # a very wide or tall picture is not kept wider than this
QUALITY = 72
PREFIX = "thumbs/"
BACKFILL_CAP = 80         # pictures a run at most: each one is a download of the full picture (about 0.9 MB on average)
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")
_SKIP = ("motion/", "imports/", PREFIX)   # film scene pictures and video posters are never library tiles; a thumbnail has none


def thumb_path(path: str | None) -> str:
    """The thumbnail's path for a stored picture's path, or '' when the file is not a picture that gets one."""
    p = str(path or "").split("?", 1)[0].split("#", 1)[0]
    if not p or p.startswith(_SKIP) or not p.lower().endswith(_IMAGE_EXT):
        return ""
    return f"{PREFIX}{p}.jpg"


def original_of(name: str) -> str:
    """The picture a thumbnail path was made from, or '' when `name` is not a thumbnail."""
    if not name.startswith(PREFIX) or not name.endswith(".jpg"):
        return ""
    return name[len(PREFIX):-len(".jpg")]


def make_thumb(data: bytes) -> bytes | None:
    """A JPEG with its short side THUMB_PX (never enlarged), or None when the bytes are not a picture Pillow can read."""
    try:
        from PIL import Image, ImageOps
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            flat = Image.new("RGB", im.size, (255, 255, 255))
            flat.paste(im, mask=im.split()[-1])
            im = flat
        else:
            im = im.convert("RGB")
        w, h = im.size
        scale = min(1.0, THUMB_PX / max(1, min(w, h)), LONG_MAX / max(1, max(w, h)))
        if scale < 1.0:
            im = im.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=QUALITY, optimize=True, progressive=True)
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 - not a picture, or one Pillow cannot read: no thumbnail, the tile shows the full one
        log.info("no thumbnail: %s", str(exc)[:120])
        return None


def store_thumb(bucket: Any, path: str, data: bytes) -> str:
    """Write the thumbnail of a picture being stored at `path`. Returns its path, or '' when there is none. Never raises: a
    picture is never refused because its small copy could not be made."""
    tp = thumb_path(path)
    if not tp:
        return ""
    small = make_thumb(data)
    if not small:
        return ""
    try:
        bucket.upload(tp, small, {"content-type": "image/jpeg", "upsert": "true", "cache-control": "86400"})
        return tp
    except Exception as exc:  # noqa: BLE001
        log.info("thumbnail %s not stored: %s", tp, str(exc)[:120])
        return ""


def missing(rows: list[dict[str, Any]], names: set[str]) -> list[tuple[str, str]]:
    """(url, path) of each stored picture in `rows` whose thumbnail is not among `names` (the bucket's file names), once each.
    Only the picture a tile draws: the result, else the first slide."""
    from .archive import path_of
    out: dict[str, str] = {}
    for r in rows:
        if r.get("status") != "done" or r.get("type") == "video":
            continue
        meta = r.get("meta") or {}
        url = r.get("generated_media_url") or next(iter(meta.get("slide_urls") or []), "")
        p = path_of(url)
        tp = thumb_path(p)
        if tp and p in names and tp not in names:
            out.setdefault(p, url)
    return [(u, p) for p, u in out.items()]


def backfill(store: Any, names: set[str], dry: bool, cap: int = BACKFILL_CAP, fetch: Any = None) -> dict[str, Any]:
    """Make the thumbnails pictures stored before this existed are missing, newest first, `cap` a run. `names` is the bucket's
    listing (housekeeping reads it once a run). dry: count only. Raises nothing; a picture that fails is tried next run."""
    from . import db
    try:
        rows = db.fetch_all(lambda: store.table(db.MEDIA).select("id,type,status,meta,generated_media_url,created_at")
                            .eq("status", "done").order("created_at", desc=True))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160]}
    todo = missing(rows, names)
    out: dict[str, Any] = {"found": len(todo), "made": 0, "bytes": 0}
    if dry or not todo:
        return out
    get = fetch or _fetch
    bucket = store.storage.from_(db.GENERATED_BUCKET)
    for url, path in todo[:cap]:
        try:
            data = get(url)
        except Exception as exc:  # noqa: BLE001 - one picture must not stop the others
            log.info("picture %s not read: %s", path, str(exc)[:120])
            continue
        tp = store_thumb(bucket, path, data)
        if tp:
            out["made"] += 1
            out["bytes"] += len(data)
    return out


def _fetch(url: str) -> bytes:
    import requests
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.content


def main(argv: list[str] | None = None) -> int:
    import argparse

    from . import archive, db
    ap = argparse.ArgumentParser(description="Make the library thumbnails stored pictures are missing")
    ap.add_argument("--dry-run", action="store_true", help="count only")
    ap.add_argument("--cap", type=int, default=BACKFILL_CAP)
    args = ap.parse_args(argv)
    store = db.client()
    names = {f["name"] for f in archive.list_bucket(store)}
    out = backfill(store, names, args.dry_run, args.cap)
    print(out)
    return 1 if out.get("error") else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
