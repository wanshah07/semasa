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
    picture made from the same idea) is in use, whoever made it: deleting it took that post's picture away."""
    keep = set(post.get("media_ids") or [])
    rows = store.table(db.MEDIA).select("id,status,meta").eq("post_id", post["id"]).execute().data or []
    dead = [r for r in rows if r["id"] not in keep and r.get("status") in ("done", "error")]
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
