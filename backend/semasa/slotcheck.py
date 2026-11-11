"""The post-slot checker (Wan, 11 Nov 2026: "build the post-slot checker").

A platform can refuse a post only when its slot arrives (Threads did, 11 Nov 10:30, and the refusal sat unread until the next
publish run, hours later). This runs shortly after each slot, reads Zernio back for every record that is now due, writes what the
network did (`publisher.tally`: sent, or error with the platform's own message), and tells Wan on Telegram, once per problem:

  * a channel Zernio shows as FAILED, with the platform's message;
  * a channel still not sent 20 minutes after its slot ("stuck");
  * an approved post whose slot has passed with a channel never handed over (the publisher leaves a late post alone).

It never re-sends anything by itself: a refusal is read, recorded and reported, because sending again can post twice. It writes a
log row every run (`slotcheck.ok` or `slotcheck.alert`), so a quiet run still shows that it ran.

    python -m semasa.slotcheck
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db, publisher, senders, telegram_bot
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.slotcheck")
STUCK_AFTER = timedelta(minutes=20)        # a channel not sent this long after its slot is stuck
WINDOW = timedelta(hours=26)               # slots older than this are the archive's business, not this check's


def _hook(post: dict[str, Any]) -> str:
    return str(post.get("hook") or "post")[:60]


def _seen(store: Any, post_id: str, title: str) -> bool:
    """Already told Wan about exactly this (post, channel, kind)?"""
    rows = (store.table(db.LOG).select("id").eq("event", "slotcheck.alert").eq("ref_id", post_id).eq("title", title)
            .limit(1).execute().data or [])
    return bool(rows)


def problems(store: Any, zernio: Any, now: datetime, settings: dict[str, Any]) -> list[dict[str, str]]:
    """[{post_id, channel, kind, title, message}] for everything that is wrong right now (not yet de-duplicated)."""
    out: list[dict[str, str]] = []
    posts = db.fetch_all(lambda: store.table(db.POSTS).select("*").in_("status", ["approved", "scheduled", "posted"])
                         .not_.is_("date", "null"))
    for post in posts:
        if not post.get("slot"):
            continue
        due = publisher.due_utc(post["date"], post["slot"])
        if due > now or due < now - WINDOW:
            continue
        pid = str(post["id"])
        published = post.get("published") or {}
        for ch, rec in published.items():
            if not isinstance(rec, dict):
                continue
            if rec.get("status") == "error":
                msg = ((post.get("errors") or {}).get(ch) or {}).get("message") or f"{ch}: the platform refused it"
                out.append({"post_id": pid, "channel": ch, "kind": "failed", "message": str(msg)[:300],
                            "title": f"Gagal di {ch}: {_hook(post)}", "due": due.isoformat()})
            elif rec.get("status") in ("scheduled", "sending") and due < now - STUCK_AFTER:
                raw = ""
                if str(rec.get("route") or "").startswith("zernio") and zernio is not None:
                    try:
                        raw = zernio.get(rec["id"], rec.get("account") or "").get("status") or ""
                    except senders.SendError as exc:
                        raw = f"cannot read it back: {str(exc)[:120]}"
                out.append({"post_id": pid, "channel": ch, "kind": "stuck",
                            "message": f"{ch} still not sent {int((now - due).total_seconds() // 60)} minutes after its slot"
                                       + (f" (Zernio: {raw})" if raw else ""),
                            "title": f"Belum keluar di {ch}: {_hook(post)}", "due": due.isoformat()})
        if post.get("status") == "approved" and due < now - publisher.LATE_GRACE:
            for ch in publisher.post_channels(settings, post):
                if not published.get(ch):
                    out.append({"post_id": pid, "channel": ch, "kind": "missed",
                                "message": f"{ch} was never handed over and its slot has passed; the publisher leaves a late "
                                           "post alone (send it now, or move it)",
                                "title": f"Terlepas slot di {ch}: {_hook(post)}", "due": due.isoformat()})
    return out


def run(store: Any, zernio: Any = None, now: datetime | None = None, notify: Any = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    settings = publisher.load_settings(store)
    counts: dict[str, int] = {}
    if zernio is not None:
        publisher.tally(store, None, now, counts, settings, zernio)         # sent / error, written from what Zernio says
    found = problems(store, zernio, now, settings)
    fresh = [p for p in found if not _seen(store, p["post_id"], p["title"])]
    for p in fresh:
        db.log_event(store, "error", "publish", "slotcheck.alert", p["title"], ref_table=db.POSTS, ref_id=p["post_id"],
                     detail={"channel": p["channel"], "kind": p["kind"], "why": p["message"], "due_at": p["due"]})
    if fresh:
        lines = [f"⚠️ Semakan selepas slot: {len(fresh)} masalah"] + [f"• {p['title']}\n  {p['message']}" for p in fresh[:8]]
        (notify or telegram_bot.notify)(store, "\n".join(lines))
    else:
        db.log_event(store, "info", "publish", "slotcheck.ok",
                     f"Semakan slot: tiada masalah baharu ({counts.get('confirmed', 0)} disahkan, {len(found)} masih dikenali)",
                     detail={"confirmed": counts.get("confirmed", 0), "known": len(found)})
    return {"confirmed": counts.get("confirmed", 0), "problems": len(found), "new": len(fresh), "lines": [
        f"{p['kind']:7} {p['title']}: {p['message']}" for p in found]}


def main() -> int:
    store = db.client(SupabaseSettings.load())
    settings = publisher.load_settings(store)
    zernio = publisher.make_clients(settings).get("zernio")
    res = run(store, zernio)
    print(f"{res['confirmed']} confirmed, {res['problems']} problems ({res['new']} new)")
    for line in res["lines"]:
        print(" ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
