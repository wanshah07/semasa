"""Archive: a post that went out is compacted and archived 24 hours later (Wan, 25 Sep 2026: "for posted post, make
sure it will not recreate as another draft, and will be auto compact and archived after 24 hours posted").

Run by the publisher (publish.yml, three times a day), so a post is archived between 24 and about 32 hours after it
went out. supabase/010_archive.sql adds `posted_at` / `archived_at`; without it this step says so and does nothing.

Compacting keeps what was published and drops what only mattered before it was:
  * text        only the language that was sent, and only the channels it was sent to (every channel of that
                language when no channel is recorded)
  * flags/errors the page's pre-publish scan and send errors are cleared
  * media       picture and slide jobs made FOR this post but never attached to it are deleted, row and files; the
                pictures that went out (media_ids) are kept, since the live posts still point at them
Nothing else is touched: the hook, citation, date, slot, `published` record, slides and the idea stay, so the
archive is still a complete record of what went out, and the idea still cannot be written again (010).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.archive")

AFTER = timedelta(hours=24)


def compact_text(post: dict[str, Any]) -> dict[str, Any]:
    text = post.get("text") if isinstance(post.get("text"), dict) else {}
    lang = post.get("lang") or "bm"
    sent = text.get(lang) if isinstance(text.get(lang), dict) else {}
    channels = [c for c in (post.get("published") or {}) if c in sent]
    return {lang: {c: sent[c] for c in channels} if channels else dict(sent)}


def unused_media(store: Any, post: dict[str, Any]) -> list[dict[str, Any]]:
    """Pictures made for this post that it does not use. A picture another post has attached (the editor offers every
    picture made from the same idea) is in use, whoever made it: deleting it took that post's picture away. A
    Design-tab artwork or a Canva rebuild of one (both carry meta.design, canva_bridge.py copies it forward) is
    excluded too: it may still be sitting unattached waiting for Wan's own Simpan click, same rule purge_rejected
    already keeps for a rejected post's pictures."""
    keep = set(post.get("media_ids") or [])
    rows = store.table(db.MEDIA).select("id,status,meta").eq("post_id", post["id"]).execute().data or []
    dead = [r for r in rows if r["id"] not in keep and r.get("status") in ("done", "error")
            and not (r.get("meta") or {}).get("design")]
    used = set()
    for r in dead:
        try:
            if store.table(db.POSTS).select("id").contains("media_ids", [r["id"]]).limit(1).execute().data:
                used.add(r["id"])
        except Exception:  # noqa: BLE001 - when in doubt, keep the picture
            used.add(r["id"])
    return [r for r in dead if r["id"] not in used]


def files_of(row: dict[str, Any]) -> list[str]:
    meta = row.get("meta") or {}
    paths = [meta.get("generated_path")] + list(meta.get("slide_paths") or [])
    return [p for p in paths if isinstance(p, str) and p]


def run(store: Any, now: datetime | None = None) -> str:
    """Archive every post posted more than 24 hours ago. Never raises; returns a line for the job summary."""
    now = now or datetime.now(UTC)
    try:
        due = db.fetch_all(lambda: store.table(db.POSTS).select("*").eq("status", "posted").is_("archived_at", "null")
                           .lt("posted_at", (now - AFTER).isoformat()).order("id"))
    except Exception as exc:  # noqa: BLE001 - 010 not run yet, or the table is unreachable
        msg = str(exc)
        if "archived_at" in msg or "posted_at" in msg:
            return "archive: skipped (run supabase/010_archive.sql)"
        return f"archive: skipped ({msg[:100]})"
    archived = removed = 0
    for post in due:
        try:
            dead = unused_media(store, post)
            paths = [p for r in dead for p in files_of(r)]
            if paths:
                try:
                    store.storage.from_(db.GENERATED_BUCKET).remove(paths)
                except Exception as exc:  # noqa: BLE001 - a file already gone must not keep the row
                    log.info("post %s: could not remove %d file(s): %s", post["id"], len(paths), str(exc)[:100])
            for r in dead:
                store.table(db.MEDIA).delete().eq("id", r["id"]).execute()
            store.table(db.POSTS).update({"text": compact_text(post), "flags": [], "errors": {},
                                          "archived_at": now.isoformat()}).eq("id", post["id"]) \
                .eq("status", "posted").is_("archived_at", "null").execute()
            archived += 1
            removed += len(dead)
        except Exception as exc:  # noqa: BLE001 - one post must not stop the others
            log.warning("post %s not archived: %s", post["id"], str(exc)[:200])
    if archived:
        db.log_event(store, "info", "post", "post.archived",
                     f"{archived} post diarkibkan (24 jam selepas diterbitkan); {removed} gambar tidak digunakan dibuang",
                     detail={"archived": archived, "media_removed": removed})
    return f"archive: {archived} post(s) archived, {removed} unused media removed"


REJECT_PURGE = timedelta(hours=72)


def purge_rejected(store: Any, now: datetime | None = None) -> str:
    """A rejected post is deleted 72 hours after it was rejected (Studio's purgeRejected, Wan 24 Sep 2026: "for rejected
    post auto permanently delete after 72 hours"). The clock is `rejected_at`, stamped by the database (021), so the
    page's countdown and this step read the same moment. Three guards, as in Studio: a post being rewritten is skipped,
    a post with no `rejected_at` is NEVER deleted (failing safe costs a row; failing open deletes work), and a post
    carrying a `published` record is kept as evidence. Pictures made FOR the post and used by no other post go with it;
    a picture another post uses, a Design-tab design and anything from the library stay."""
    now = now or datetime.now(UTC)
    cutoff = (now - REJECT_PURGE).isoformat()
    try:
        due = db.fetch_all(lambda: store.table(db.POSTS).select("id,published,revise_state,rejected_at,media_ids")
                           .eq("status", "rejected").lt("rejected_at", cutoff).order("id"))
    except Exception as exc:  # noqa: BLE001 - 021 not run yet
        msg = str(exc)
        if "rejected_at" in msg:
            return "purge: skipped (run supabase/021_studio_workflow.sql)"
        return f"purge: skipped ({msg[:100]})"
    purged = removed = kept = 0
    for post in due:
        if not post.get("rejected_at") or post.get("revise_state") == "working" or post.get("published"):
            kept += 1
            continue
        try:
            own = store.table(db.MEDIA).select("id,status,meta").eq("post_id", post["id"]).execute().data or []
            dead = []
            for r in own:
                if (r.get("meta") or {}).get("design"):
                    continue
                try:
                    other = store.table(db.POSTS).select("id").contains("media_ids", [r["id"]]).neq("id", post["id"]) \
                        .limit(1).execute().data
                except Exception:  # noqa: BLE001 - when in doubt, keep the picture
                    other = True
                if not other:
                    dead.append(r)
            gone = store.table(db.POSTS).delete().eq("id", post["id"]).eq("status", "rejected") \
                .lt("rejected_at", cutoff).execute().data or []
            if not gone:
                continue                 # restored (or changed) between the read and the delete
            paths = [p for r in dead for p in files_of(r)]
            if paths:
                try:
                    store.storage.from_(db.GENERATED_BUCKET).remove(paths)
                except Exception as exc:  # noqa: BLE001
                    log.info("post %s: could not remove %d file(s): %s", post["id"], len(paths), str(exc)[:100])
            for r in dead:
                store.table(db.MEDIA).delete().eq("id", r["id"]).execute()
            purged += 1
            removed += len(dead)
        except Exception as exc:  # noqa: BLE001 - one post must not stop the others
            log.warning("rejected post %s not purged: %s", post["id"], str(exc)[:200])
    if purged:
        db.log_event(store, "info", "post", "post.purged",
                     f"{purged} post ditolak dipadam (72 jam selepas ditolak); {removed} gambar miliknya dibuang",
                     detail={"purged": purged, "media_removed": removed, "kept": kept})
    return f"purge: {purged} rejected post(s) deleted after 72h, {removed} of their pictures removed, {kept} kept"


PRUNE_HOURS = 12          # files of a post that went out are deleted this long after it did (Wan, 12 Nov 2026)
_BUCKET_MARK = f"/{db.GENERATED_BUCKET}/"


def path_of(url: Any) -> str:
    """The storage path inside the generated bucket that a public address names, or '' for any other address."""
    text = str(url or "")
    if _BUCKET_MARK not in text:
        return ""
    return text.split(_BUCKET_MARK, 1)[1].split("?", 1)[0].split("#", 1)[0]


def film_files(store: Any, motion: dict[str, Any], media: dict[str, Any]) -> list[str]:
    """Every file a finished Motion film left in storage: the full film, its compressed social copy, the poster, the storyboard's
    scene pictures and contact sheet. A path is listed once."""
    meta = media.get("meta") or {}
    paths = [motion.get("video_path"), path_of(motion.get("video_url")), path_of(motion.get("social_url")),
             path_of(motion.get("poster_url")), path_of(media.get("generated_media_url")), path_of(media.get("reference_url")),
             path_of(meta.get("poster_url")), meta.get("generated_path")]
    if motion.get("id"):
        folder = f"motion/storyboard/{motion['id']}"
        try:
            paths += [f"{folder}/{o['name']}" for o in (store.storage.from_(db.GENERATED_BUCKET).list(folder) or [])
                      if o.get("name")]
        except Exception as exc:  # noqa: BLE001 - no folder is no files
            log.info("film %s: storyboard folder not listed: %s", motion["id"], str(exc)[:100])
    return list(dict.fromkeys(p for p in paths if isinstance(p, str) and p))


def prune_hours(store: Any) -> int:
    """How long a posted post's files are kept: settings `prune.hours` (the page's Settings), else PRUNE_HOURS. Never below
    2: the platforms fetch a picture when they publish, and a few hours of margin is what makes deleting ours safe."""
    try:
        row = store.table(db.SETTINGS).select("value").eq("key", "prune").limit(1).execute().data or []
        value = (row[0].get("value") or {}) if row else {}
        return max(2, min(24 * 30, int(value.get("hours") or PRUNE_HOURS)))
    except Exception:  # noqa: BLE001 - settings unreadable: the default
        return PRUNE_HOURS


def purge_films(store: Any, now: datetime | None = None, hours: int = PRUNE_HOURS) -> str:
    """A Motion film is deleted for good `hours` (12) after its post went out (Wan, 11 Nov 2026: "after 72 hours delete
    them permanently to save space"; 12 Nov: "keep temporarily within 12 hours"). The platforms keep their own copy; ours only
    costs storage. Guards, in the order that matters: only a post whose status is `posted` with a `posted_at` older than the
    window (an unreadable stamp is never purged); a film another post that has NOT gone out still uses is kept; and the files
    go FIRST, the records after, so a failed delete leaves everything as it was and the next run tries again. The rows stay as
    the record (title, script, captions, the post's `published` links): only the files, their addresses and the heavy
    composition are cleared, and `film_purged_at` says when."""
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(hours=hours)).isoformat()
    try:
        posts = db.fetch_all(lambda: store.table(db.POSTS).select("id,media_ids,posted_at").eq("status", "posted")
                             .lt("posted_at", cutoff).order("id"))
    except Exception as exc:  # noqa: BLE001 - 010 not run yet, or the table is unreachable
        return f"films: skipped ({str(exc)[:100]})"
    purged = freed = 0
    for post in posts:
        ids = [i for i in (post.get("media_ids") or []) if i]
        if not ids or not post.get("posted_at"):
            continue
        try:
            rows = store.table(db.MEDIA).select("*").in_("id", ids).eq("type", "video").execute().data or []
            for media in rows:
                meta = dict(media.get("meta") or {})
                if meta.get("flow") != "motion" or meta.get("film_purged_at"):
                    continue
                if _in_use_elsewhere(store, media["id"], post["id"]):
                    continue
                motion = {}
                if meta.get("motion_id"):
                    motion = (store.table("semasa_motions").select("*").eq("id", meta["motion_id"]).limit(1).execute().data
                              or [{}])[0]
                paths = film_files(store, motion, media)
                if paths:
                    # a failure raises here: nothing below runs and the next run tries again
                    store.storage.from_(db.GENERATED_BUCKET).remove(paths)
                stamp = now.isoformat()
                if motion.get("id"):
                    report = dict(motion.get("check_report") or {})
                    report["film_purged_at"] = stamp
                    store.table("semasa_motions").update({"video_url": "", "social_url": "", "poster_url": "", "video_path": "",
                                                          "html": "", "check_report": report}).eq("id", motion["id"]).execute()
                meta.update(film_purged_at=stamp, purge_hours=hours, poster_url="", generated_path=None)
                store.table(db.MEDIA).update({"generated_media_url": None, "reference_url": None, "meta": meta}) \
                    .eq("id", media["id"]).execute()
                purged += 1
                freed += len(paths)
        except Exception as exc:  # noqa: BLE001 - one post must not stop the others
            log.warning("post %s: film not purged: %s", post["id"], str(exc)[:200])
    if purged:
        db.log_event(store, "info", "post", "film.purged",
                     f"{purged} video Motion dipadam kekal ({hours} jam selepas diterbitkan); {freed} fail dibuang",
                     detail={"films": purged, "files": freed})
    return f"films: {purged} Motion film(s) deleted {hours}h after posting, {freed} file(s) removed"


def _in_use_elsewhere(store: Any, media_id: str, post_id: str) -> bool:
    """Is this film attached to another post that has not gone out yet? When unsure, yes: the film is kept."""
    try:
        others = (store.table(db.POSTS).select("id,status").contains("media_ids", [media_id]).neq("id", post_id)
                  .execute().data or [])
        return any(o.get("status") != "posted" for o in others)
    except Exception:  # noqa: BLE001 - when in doubt, keep the film
        return True


def purge_pictures(store: Any, now: datetime | None = None, hours: int = PRUNE_HOURS) -> str:
    """The pictures and slides of a post that went out are deleted `hours` after it did, as films are (Wan, 12 Nov 2026: "after
    post it will delete automatically/or keep temporarily within 12 hours to save space disk"). The platforms keep their own
    copy. Same guards as purge_films: only a post whose status is `posted` with a readable `posted_at` older than the
    window; a picture another post that has NOT gone out still uses is kept; a Design-tab artwork (meta.design) is kept
    (it is Wan's library, not this post's); the files go FIRST and the rows after, so a failed delete changes nothing and the
    next run tries again. The row stays as the record; its addresses are cleared and `files_purged_at` says when."""
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(hours=hours)).isoformat()
    try:
        posts = db.fetch_all(lambda: store.table(db.POSTS).select("id,media_ids,posted_at").eq("status", "posted")
                             .lt("posted_at", cutoff).order("id"))
    except Exception as exc:  # noqa: BLE001
        return f"pictures: skipped ({str(exc)[:100]})"
    purged = freed = 0
    for post in posts:
        ids = [i for i in (post.get("media_ids") or []) if i]
        if not ids or not post.get("posted_at"):
            continue
        try:
            rows = store.table(db.MEDIA).select("*").in_("id", ids).neq("type", "video").execute().data or []
            for media in rows:
                meta = dict(media.get("meta") or {})
                if meta.get("files_purged_at") or meta.get("design") or media.get("status") != "done":
                    continue
                if _in_use_elsewhere(store, media["id"], post["id"]):
                    continue
                paths = list(dict.fromkeys(files_of(media) + [path_of(media.get("generated_media_url")),
                                                              path_of(media.get("reference_url"))]))
                paths = [p for p in paths if p]
                if not paths:
                    continue
                store.storage.from_(db.GENERATED_BUCKET).remove(paths)       # a failure raises: nothing below runs
                meta.update(files_purged_at=now.isoformat(), purge_hours=hours, slide_urls=[], slide_paths=[],
                            generated_path=None)
                store.table(db.MEDIA).update({"generated_media_url": None, "reference_url": None, "meta": meta}) \
                    .eq("id", media["id"]).execute()
                purged += 1
                freed += len(paths)
        except Exception as exc:  # noqa: BLE001 - one post must not stop the others
            log.warning("post %s: pictures not purged: %s", post["id"], str(exc)[:200])
    if purged:
        db.log_event(store, "info", "post", "pictures.purged",
                     f"{purged} gambar/slaid dipadam ({hours} jam selepas diterbitkan); {freed} fail dibuang",
                     detail={"pictures": purged, "files": freed})
    return f"pictures: {purged} picture set(s) deleted {hours}h after posting, {freed} file(s) removed"


ORPHAN_AGE = timedelta(hours=24)
ORPHAN_CAP = 200          # files deleted in one run at most: a bug in the reference scan must not empty the bucket in one go
_NO_SCAN = {db.TRENDS, db.LOG, "semasa_faqs", db.RUNS}


def referenced_text(store: Any) -> str:
    """Everything in the database that could name a stored file, as one string. Read from every table the code knows (a
    table missing from this list can only make a file look USED, never unused: the skip list is the short one)."""
    import json
    tables = sorted({v for k, v in vars(db).items() if k.isupper() and isinstance(v, str) and (v.startswith("semasa_")
                     or v in (db.MEDIA, db.TRENDS, db.RUNS)) and v not in _NO_SCAN} | {"semasa_motions"})
    parts: list[str] = []
    for t in tables:
        rows = db.fetch_all(lambda t=t: store.table(t).select("*").order("id"))      # raises when a table cannot be read
        parts.append(json.dumps(rows, default=str))
    return "\n".join(parts)


def list_bucket(store: Any, folder: str = "") -> list[dict[str, Any]]:
    """Every file in the generated bucket (name relative to the bucket), walking folders."""
    out: list[dict[str, Any]] = []
    bucket = store.storage.from_(db.GENERATED_BUCKET)
    stack = [folder]
    while stack:
        base = stack.pop()
        offset = 0
        while True:
            page = bucket.list(base, {"limit": 1000, "offset": offset}) or []
            for o in page:
                name = f"{base}/{o['name']}" if base else o["name"]
                if o.get("id") is None and not o.get("metadata"):
                    stack.append(name)                                  # a folder
                else:
                    out.append({"name": name, "created_at": o.get("created_at"),
                                "size": int((o.get("metadata") or {}).get("size") or 0)})
            if len(page) < 1000:
                break
            offset += 1000
    return out


def sweep_orphans(store: Any, now: datetime | None = None, mode: str = "report") -> str:
    """Files in the bucket that no database row names, and are at least a day old (a file is written before its row, so a
    young one may be mid-flight). mode "report" (the default) only counts and logs them; "delete" removes up to ORPHAN_CAP
    a run. Any failure reading the bucket or a table means nothing is deleted."""
    now = now or datetime.now(UTC)
    try:
        text = referenced_text(store)
        files = list_bucket(store)
    except Exception as exc:  # noqa: BLE001 - when in doubt, keep everything
        return f"orphans: skipped ({str(exc)[:100]})"
    old = []
    for f in files:
        try:
            made = datetime.fromisoformat(str(f["created_at"]).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue                                                     # an unreadable stamp is never deleted
        if now - made >= ORPHAN_AGE and f["name"] not in text:
            old.append(f)
    mb = sum(f["size"] for f in old) / 1048576
    if mode != "delete" or not old:
        note = "nothing to do" if not old else "report only; settings prune.orphans=delete turns deletion on"
        return f"orphans: {len(old)} unreferenced file(s), {mb:.0f} MB ({note})"
    batch = old[:ORPHAN_CAP]
    try:
        store.storage.from_(db.GENERATED_BUCKET).remove([f["name"] for f in batch])
    except Exception as exc:  # noqa: BLE001
        return f"orphans: not deleted ({str(exc)[:100]})"
    freed = sum(f["size"] for f in batch) / 1048576
    db.log_event(store, "info", "post", "orphans.deleted", f"{len(batch)} fail tanpa rujukan dipadam ({freed:.0f} MB)",
                 detail={"files": len(batch), "mb": round(freed, 1), "left": len(old) - len(batch)})
    return f"orphans: {len(batch)} unreferenced file(s) deleted ({freed:.0f} MB), {len(old) - len(batch)} left"


def prune(store: Any, now: datetime | None = None) -> str:
    """One step for the publisher: films and pictures of posted posts, then the orphan sweep. Never raises."""
    hours = prune_hours(store)
    mode = "report"
    try:
        row = store.table(db.SETTINGS).select("value").eq("key", "prune").limit(1).execute().data or []
        mode = "delete" if row and (row[0].get("value") or {}).get("orphans") == "delete" else "report"
    except Exception:  # noqa: BLE001
        pass
    out = []
    for step in (lambda: purge_films(store, now, hours), lambda: purge_pictures(store, now, hours),
                 lambda: sweep_orphans(store, now, mode)):
        try:
            out.append(step())
        except Exception as exc:  # noqa: BLE001 - one step must not stop the next
            log.warning("prune step failed: %s", str(exc)[:200])
            out.append(f"prune step failed ({str(exc)[:80]})")
    return "; ".join(out)
