"""Redraw what is already approved, in place, keeping its approval (Wan, 11 Nov 2026).

Wan: "Re-render the carousels and films", answering the question "the worker refuses to redraw approved artwork, how?" with
"in place, keep approvals". So, for every ws.regulab post that is approved or scheduled but not yet sent, and not due within the
next two hours:

  1. its pictures are marked `processing` first, which holds the post back from the publisher (a post whose pictures are not
     done is never sent) while this runs;
  2. its Zernio copy is DELETED, and the channel records are cleared, because the old picture files are removed once the new
     ones exist and Zernio fetches them when the post goes out; the status goes back to `approved` (the publisher only queues
     an approved post, and the post keeps its date, slot and every word);
  3. a carousel is drawn again from its stored words (`semasa.media_generator.process_slides`, called directly: the guard that
     refuses to touch approved artwork sits in `process_row` and is the thing this one-off steps around, on Wan's word);
     a film gets the branded cover added to the finished file (ffmpeg only: no AI, no new storyboard, no cost);
  4. a failed redraw puts the old artwork back exactly as it was, so the post is queued again with what it had.

The publisher queues the posts again at its next run (dispatch it right after). Nothing here writes `approved` on a post that was
not approved, sets `posted`, or touches a post any of whose channels has already gone out.

    python -m semasa.rerender --dry          # list what would be redrawn, change nothing
    python -m semasa.rerender                # do it
    python -m semasa.rerender --only <post id>[,<post id>...]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from . import archive, db, publisher
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.rerender")
MARGIN = timedelta(hours=2)          # a post due sooner than this is left alone: there is no time to queue it again


def _sent(post: dict[str, Any]) -> bool:
    return any(isinstance(r, dict) and r.get("status") in ("sent", "error") for r in (post.get("published") or {}).values())


def candidates(store: Any, now: datetime, only: set[str] | None = None) -> list[dict[str, Any]]:
    """[{post, kind: 'carousel' | 'film', media}] for ws.regulab posts that are approved or scheduled and not yet sent."""
    posts = db.fetch_all(lambda: store.table(db.POSTS).select("*").eq("stream", "regulab")
                         .in_("status", ["approved", "scheduled"]).order("date"))
    out = []
    for post in posts:
        if only and post["id"] not in only:
            continue
        if not post.get("date") or not post.get("slot") or _sent(post):
            continue
        if publisher.due_utc(post["date"], post["slot"]) < now + MARGIN:
            continue
        ids = [i for i in (post.get("media_ids") or []) if i]
        if not ids:
            continue
        for media in store.table(db.MEDIA).select("*").in_("id", ids).eq("status", "done").execute().data or []:
            meta = media.get("meta") or {}
            if media.get("mode") == "slides" and not meta.get("design") and not meta.get("cover"):
                out.append({"post": post, "kind": "carousel", "media": media})
            elif media.get("type") == "video" and meta.get("flow") == "motion" and not meta.get("film_purged_at") \
                    and not meta.get("cover_added_at") and meta.get("motion_id"):
                out.append({"post": post, "kind": "film", "media": media})
    return out


def _hold(store: Any, zernio: Any, post: dict[str, Any], media: dict[str, Any]) -> None:
    """Hold the post back from the publisher, then take its Zernio copy out and clear its records. Raises when a copy cannot be
    deleted: the copies already deleted are cleared from the post (it is queued again for those channels), the rest stay as
    they were, and the caller lifts the hold."""
    store.table(db.MEDIA).update({"status": "processing"}).eq("id", media["id"]).execute()
    published = dict(post.get("published") or {})
    deleted: list[str] = []
    try:
        for channel, rec in published.items():
            if not isinstance(rec, dict):
                continue
            if not str(rec.get("route") or "").startswith("zernio"):
                raise RuntimeError(f"{channel} is held by {rec.get('route') or 'another sender'}, not Zernio: left alone")
            if zernio is None:
                raise RuntimeError("no Zernio sender is set up here")
            zernio.delete(rec["id"], rec.get("account") or "")
            deleted.append(channel)
    except Exception:
        if deleted:
            left = {k: v for k, v in published.items() if k not in deleted}
            store.table(db.POSTS).update({"published": left, "status": "approved"}).eq("id", post["id"]).execute()
        raise
    if published or post.get("errors"):
        store.table(db.POSTS).update({"published": {}, "errors": {}, "status": "approved"}).eq("id", post["id"]).execute()
    elif post.get("status") != "approved":
        store.table(db.POSTS).update({"status": "approved"}).eq("id", post["id"]).execute()


def _restore(store: Any, before: dict[str, Any]) -> None:
    store.table(db.MEDIA).update({"status": "done", "error": before.get("error"),
                                  "generated_media_url": before.get("generated_media_url"),
                                  "reference_url": before.get("reference_url"), "meta": before.get("meta") or {}}) \
        .eq("id", before["id"]).execute()


def redraw_carousel(store: Any, media: dict[str, Any], settings: Any) -> str:
    """Draw the set again from its stored words. 'done' on success; on any failure the old row is put back, reason returned."""
    from . import media_generator
    row = {**media, "status": "processing", "attempts": 1}
    try:
        media_generator.process_slides(store, row, settings, None)
    except Exception as exc:  # noqa: BLE001 - the old artwork goes back
        _restore(store, media)
        return f"redraw failed: {str(exc)[:160]}"
    now = (store.table(db.MEDIA).select("*").eq("id", media["id"]).limit(1).execute().data or [{}])[0]
    if now.get("status") != "done" or not (now.get("meta") or {}).get("slide_urls"):
        _restore(store, media)
        return f"redraw did not finish (status {now.get('status')}): the old artwork is back"
    return "done"


def _download(url: str, to: Path) -> Path:
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    to.write_bytes(r.content)
    return to


def add_cover_to_film(store: Any, media: dict[str, Any], runner: Any = subprocess.run) -> str:
    """The branded cover added to the finished film (and its social copy and poster), with the files uploaded under new names
    and the old ones removed after the records point at the new ones. 'done', or the reason it could not be."""
    from . import motion
    meta = dict(media.get("meta") or {})
    film = (store.table("semasa_motions").select("*").eq("id", meta["motion_id"]).limit(1).execute().data or [{}])[0]
    if not film.get("video_url"):
        return "the film's file is gone"
    first = (film.get("script") or [{}])[0] if film.get("script") else {}
    title = str(first.get("heading") or film.get("title") or film.get("brief") or "")[:200]
    with tempfile.TemporaryDirectory() as tmp:
        src = _download(film["video_url"], Path(tmp) / "film.mp4")
        covered = motion.with_cover(src, title, eyebrow=str(first.get("kicker") or "")[:60], runner=runner)
        if covered == src:
            return "the cover could not be added"
        info = motion.probe(covered, runner)
        full = covered.read_bytes()
        small = motion.social_copy(covered, runner)
        jpg = motion.poster(covered, runner)
        base = f"motion/{film['id']}-c{datetime.now(UTC):%d%H%M%S}"
        video_url = db.upload_generated(store, f"{base}.mp4", full, "video/mp4")
        social_url = db.upload_generated(store, f"{base}-social.mp4", small.read_bytes(), "video/mp4") if small else ""
        poster_url = db.upload_generated(store, f"{base}.jpg", jpg, "image/jpeg") if jpg else ""
        social_bytes = small.stat().st_size if small else 0
    old = [film.get("video_path"), archive.path_of(film.get("social_url")), archive.path_of(film.get("poster_url"))]
    report = dict(film.get("check_report") or {})
    report["cover"] = {"seconds": 1.1, "added_by": "rerender"}
    store.table("semasa_motions").update({
        "video_path": f"{base}.mp4", "video_url": video_url, "social_url": social_url, "poster_url": poster_url,
        "bytes": len(full), "social_bytes": social_bytes, "duration_s": info["duration_s"], "check_report": report,
    }).eq("id", film["id"]).execute()
    meta.update(poster_url=poster_url, seconds=info["duration_s"], bytes=social_bytes or len(full),
                compressed=bool(social_url), cover_added_at=datetime.now(UTC).isoformat())
    store.table(db.MEDIA).update({"status": "done", "generated_media_url": social_url or video_url, "reference_url": video_url,
                                  "meta": meta}).eq("id", media["id"]).execute()
    gone = [p for p in old if p]
    if gone:
        try:
            store.storage.from_(db.GENERATED_BUCKET).remove(gone)
        except Exception as exc:  # noqa: BLE001 - housekeeping: a file left behind is not a failure
            log.info("film %s: old files not removed: %s", film["id"], str(exc)[:100])
    return "done"


def run(store: Any, now: datetime | None = None, *, dry: bool = False, only: set[str] | None = None,
        clients: dict[str, Any] | None = None, settings: Any = None, runner: Any = subprocess.run) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    todo = candidates(store, now, only)
    result: dict[str, Any] = {"candidates": len(todo), "done": 0, "failed": 0, "lines": []}
    if dry:
        result["lines"] = [f"{c['kind']:8} {c['post']['date']} {c['post']['slot']} {c['post']['id']}" for c in todo]
        return result
    clients = clients if clients is not None else publisher.make_clients(publisher.load_settings(store))
    zernio = clients.get("zernio")
    if settings is None:
        from .media_generator import MediaSettings
        settings = MediaSettings.load()
    for c in todo:
        post, media = c["post"], c["media"]
        label = f"{c['kind']} {post['date']} {post['slot']} {post['id'][:8]}"
        try:
            _hold(store, zernio, post, media)
        except Exception as exc:  # noqa: BLE001 - nothing was changed beyond the hold: lift it and leave the post as it was
            store.table(db.MEDIA).update({"status": "done"}).eq("id", media["id"]).execute()
            result["failed"] += 1
            result["lines"].append(f"{label}: NOT touched ({str(exc)[:140]})")
            continue
        try:
            if c["kind"] == "carousel":
                outcome = redraw_carousel(store, media, settings)
            else:
                outcome = add_cover_to_film(store, media, runner)
        except Exception as exc:  # noqa: BLE001 - the old artwork goes back
            outcome = f"failed: {str(exc)[:160]}"
        if outcome != "done":
            _restore(store, media)
            result["failed"] += 1
            result["lines"].append(f"{label}: kept its old artwork ({outcome})")
        else:
            result["done"] += 1
            result["lines"].append(f"{label}: redrawn")
    if result["done"] or result["failed"]:
        db.log_event(store, "info", "post", "post.rerendered",
                     f"{result['done']} post dilukis semula di tempat (kelulusan kekal), {result['failed']} dibiarkan",
                     detail={"done": result["done"], "failed": result["failed"], "lines": result["lines"][:40]})
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    store = db.client(SupabaseSettings.load())
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    res = run(store, dry=args.dry, only=only)
    print(f"candidates {res['candidates']}, redrawn {res['done']}, kept {res['failed']}")
    for line in res["lines"]:
        print(" ", line)
    return 1 if res["failed"] and not args.dry else 0

if __name__ == "__main__":
    sys.exit(main())
