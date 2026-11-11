"""Pull a scheduled post back to draft so Wan can edit it (supabase/076; Wan, 10 Nov 2026: "make sure aku boleh ubah post untuk
ws.regulab atau linkedin").

The page asks by inserting a row in semasa_post_pullbacks. This worker (pullback.yml, woken by the database) does what the
browser cannot, because the keys live here:

  * a post with ANY channel already published is refused, with the reason on the row: nothing can unpublish a sent post;
  * a channel held by Buffer is refused too (Buffer is the idle backup now: delete it there first);
  * otherwise every Zernio post of it is deleted (already gone counts as deleted), and the post goes back to DRAFT with its
    date and slot kept and every channel record cleared. It must be approved again: an edited post is never sent on the strength
    of an approval for different words.

Nothing else on the post is touched. A failure part-way leaves the post as it was and says why: the next ask tries again.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from . import db, publisher, senders
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.pullback")
TABLE = "semasa_post_pullbacks"


def _finish(store: Any, row: dict[str, Any], state: str, note: str, now: datetime) -> None:
    store.table(TABLE).update({"state": state, "note": note[:500], "done_at": now.isoformat()}).eq("id", row["id"]).execute()


def pull_back(store: Any, row: dict[str, Any], clients: dict[str, Any], now: datetime) -> str:
    """One request: 'done' or 'refused'. Never raises: the reason is written on the row."""
    posts = store.table(db.POSTS).select("id,status,published").eq("id", row["post_id"]).limit(1).execute().data or []
    if not posts:
        _finish(store, row, "refused", "the post no longer exists", now)
        return "refused"
    post = posts[0]
    if post.get("status") != "scheduled":
        why = ("it has been published and cannot be taken back" if post.get("status") == "posted"
               else f"it is {post.get('status')}, not scheduled: it can already be edited")
        _finish(store, row, "refused", why, now)
        return "refused"
    records = {ch: rec for ch, rec in (post.get("published") or {}).items() if isinstance(rec, dict)}
    sent = sorted(ch for ch, rec in records.items() if rec.get("status") == "sent")
    if sent:
        _finish(store, row, "refused", f"already published on {', '.join(sent)}: a published post cannot be taken back", now)
        return "refused"
    for ch, rec in records.items():
        if not str(rec.get("route") or "").startswith("zernio"):
            _finish(store, row, "refused", f"{ch} is held by {rec.get('route') or 'another service'}: delete it there first, "
                    "then ask again", now)
            return "refused"
    hub = clients.get("zernio")
    if records and hub is None:
        _finish(store, row, "refused", "no Zernio sender is set up on this worker (its key is missing)", now)
        return "refused"
    for ch, rec in records.items():
        try:
            hub.delete(rec["id"], rec.get("account") or "")
        except (senders.SendError, KeyError) as exc:
            _finish(store, row, "refused", f"{ch}: Zernio would not take it out of the queue ({str(exc)[:160]}); the channels "
                    "after it were not touched", now)
            return "refused"
        # the app's log, not semasa_publish_log: that table's CHECK has no 'pulled_back' action, so the insert failed AFTER Zernio had
        # deleted the post and the request was refused with the post still "scheduled" (11 Nov 2026, eb328516)
        db.log_event(store, "info", "publish", "publish.pulled_back", f"{ch}: ditarik balik untuk disunting",
                     ref_table=db.POSTS, ref_id=post["id"], detail={"channel": ch, "zernio_id": rec.get("id")})
    store.table(db.POSTS).update({"status": "draft", "published": {}, "errors": {}, "approved_by": None, "approved_at": None}) \
        .eq("id", post["id"]).eq("status", "scheduled").execute()
    queued = ", ".join(records) or "no channel was queued"
    _finish(store, row, "done", f"back to draft: {queued}; approve it again after the edit", now)
    return "done"


def run(store: Any, now: datetime | None = None, clients: dict[str, Any] | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    rows = store.table(TABLE).select("*").eq("state", "pending").order("requested_at").limit(20).execute().data or []
    counts = {"done": 0, "refused": 0, "failed": 0}
    if not rows:
        return counts
    if clients is None:
        clients = publisher.make_clients(publisher.load_settings(store))
    for row in rows:
        try:
            counts[pull_back(store, row, clients, now)] += 1
        except Exception as exc:  # noqa: BLE001 - one bad request must not stop the others
            counts["failed"] += 1
            log.exception("pull-back of %s failed", row.get("post_id"))
            try:
                _finish(store, row, "refused", f"the worker failed: {str(exc)[:200]}", now)
            except Exception:  # noqa: BLE001
                pass
    return counts


def main() -> int:
    store = db.client(SupabaseSettings.load())
    log.info("pull-back: %s", run(store))
    return 0


if __name__ == "__main__":
    sys.exit(main())
