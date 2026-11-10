"""What Buffer's queue already holds, for the step that writes ideas (Wan, 9 Nov 2026: "make sure add the posts that are already
queued in Buffer; if the queue is full, pause new ideas; when the queue moves, put them back").

Two things come out of one read of Buffer:
  * POSITIONS: every post Buffer holds as scheduled (Semasa's, Studio's brought-over ones, ones made by hand in Buffer) is a
    taken date+slot, so auto-fill never plans an idea for a slot Buffer already has a post on. Before this only Semasa's own
    posts table counted.
  * FULL: Buffer caps scheduled posts PER CHANNEL (organizations[].limits.scheduledPosts, 10 on the free plan). When any
    switched-on ws.regulab channel is at the cap, a new idea would only become a draft that Buffer refuses ("Limit reached"),
    so auto-fill waits. It resumes by itself on the first run that finds room again (a post went out, or one was deleted).

Zernio too (Wan, 10 Nov 2026: "this one apply for zernio too"): while Zernio carries ws.regulab and Buffer is the idle backup, the
same pause reads ZERNIO's queue (`snapshot_zernio`, settings row `zernio_queue`). Zernio's plan sets no cap on scheduled posts
(usage-based, `/usage-stats` limits -1), so the cap is Wan's own: `channels.zernio.queue_limit`, 10 unless he sets another,
0 for none.

It only READS Buffer. It writes one settings row, `buffer_queue`, that the page shows. Unknown is never "full": with no Buffer
key or an unreachable Buffer the answer is None and auto-fill carries on exactly as before.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import db, senders
from .log import get_logger

log = get_logger("semasa.buffer_queue")

KEY = "buffer_queue"
ZKEY = "zernio_queue"
ZERNIO_CAP = 10                                             # per channel, the same rhythm the Buffer plan gave
HOLDING = ("scheduled", "sending", "needs_approval")       # Buffer statuses that occupy a place in the queue
LOOKAHEAD = timedelta(days=21)
MARGIN = 0                                                  # full = at the cap; raise to keep room for a hand-made post
SLOT_TOLERANCE = timedelta(minutes=45)                      # a Buffer post within this of a slot holds that slot
MYT = timedelta(hours=8)


def _parse(ts: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def channel_ids(settings: dict[str, Any]) -> dict[str, str]:
    """{platform: Buffer channel id} for the ws.regulab channels that are switched on (Threads, Facebook, Instagram)."""
    cfg = (settings.get("channels") or {}).get("buffer") or {}
    enabled = cfg.get("enabled") or {}
    return {p: str(cfg[p]) for p in ("facebook", "instagram", "threads") if cfg.get(p) and enabled.get(p, True) is not False}


def slot_of(due: datetime, slots: list[str]) -> tuple[str, str] | None:
    """(Malaysia date, slot) a Buffer post is on: the slot within SLOT_TOLERANCE of its Malaysian clock time, else None
    (a post at an odd hour holds no slot of ours, though it still counts toward the cap)."""
    local = due.astimezone(UTC) + MYT
    best: tuple[timedelta, str] | None = None
    for s in slots:
        try:
            hh, mm = (int(x) for x in s.split(":"))
        except ValueError:
            continue
        at = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
        gap = abs(local - at)
        if gap <= SLOT_TOLERANCE and (best is None or gap < best[0]):
            best = (gap, s)
    return (local.date().isoformat(), best[1]) if best else None


def read(client: Any, ids: dict[str, str], now: datetime, limit: Any = "plan") -> dict[str, Any]:
    """One look at a queue: per channel the posts it holds, and the cap per channel. `limit` "plan" reads Buffer's own plan cap;
    a number (or None for no cap) is the cap given, which is how Zernio's is set."""
    if limit == "plan":
        limit = None
        try:
            acct = client._gql("query { account { organizations { id limits { scheduledPosts } } } }")
            for org in (acct.get("account") or {}).get("organizations") or []:
                if str(org.get("id")) == str(client.org):
                    limit = int(((org.get("limits") or {}).get("scheduledPosts")) or 0) or None
        except (senders.SendError, TypeError, ValueError) as exc:
            log.info("Buffer plan cap not read (%s)", str(exc)[:100])
    per: dict[str, list[dict[str, Any]]] = {}
    for platform, cid in ids.items():
        posts = client.posts([cid], now.isoformat(), (now + LOOKAHEAD).isoformat())
        per[platform] = [p for p in posts
                         if p.get("status") in HOLDING and (_parse(p.get("dueAt")) or now) >= now - SLOT_TOLERANCE]
    return {"limit": limit, "channels": per}


def summarise(got: dict[str, Any], slots: list[str]) -> dict[str, Any]:
    """The facts auto-fill and the page need, from one read: counts per channel, whether any is full, and taken positions."""
    limit = got.get("limit")
    counts = {p: len(v) for p, v in (got.get("channels") or {}).items()}
    full = [p for p, n in counts.items() if limit and n >= limit - MARGIN]
    taken: set[tuple[str, str]] = set()
    for posts in (got.get("channels") or {}).values():
        for post in posts:
            due = _parse(post.get("dueAt"))
            pos = slot_of(due, slots) if due else None
            if pos:
                taken.add(pos)
    return {"limit": limit, "counts": counts, "full": full, "is_full": bool(full), "taken": sorted(taken)}


def snapshot(store: Any, settings: dict[str, Any], now: datetime | None = None, client: Any = None) -> dict[str, Any] | None:
    """summarise(read(...)) for the ws.regulab stream, remembered in settings.buffer_queue; None when Buffer cannot be read
    (no key, no channels, unreachable): the caller then behaves exactly as it did before this existed."""
    now = now or datetime.now(UTC)
    if client is None:
        from . import publisher  # the same one-key-one-organization client the publisher builds
        client = publisher.make_clients(settings).get("buffer")
    ids = channel_ids(settings)
    if client is None or not ids:
        return None
    slots = sorted(((settings.get("brand") or {}).get("regulab") or {}).get("slots") or ["08:00", "13:00", "21:00"])
    try:
        out = summarise(read(client, ids, now), slots)
    except senders.SendError as exc:
        log.warning("Buffer queue not read: %s", str(exc)[:160])
        return None
    out["name"] = "Buffer"
    remember(store, out, now, (settings.get(KEY) or {}) if isinstance(settings.get(KEY), dict) else {})
    return out


def zernio_ids(settings: dict[str, Any]) -> dict[str, str]:
    """{platform: Zernio account id} for the ws.regulab platforms Zernio carries (Facebook, Instagram, Threads)."""
    from . import publisher
    acc = publisher.zernio_accounts((settings.get("channels") or {}).get("zernio") or {})
    return {p: acc[p]["id"] for p in ("facebook", "instagram", "threads") if p in acc}


def zernio_cap(settings: dict[str, Any]) -> int | None:
    """Wan's own cap per Zernio channel (its plan sets none): `channels.zernio.queue_limit`, 10 when unset, None for 0."""
    raw = ((settings.get("channels") or {}).get("zernio") or {}).get("queue_limit")
    if raw is None:
        return ZERNIO_CAP
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return ZERNIO_CAP
    return n if n > 0 else None


def snapshot_zernio(store: Any, settings: dict[str, Any], now: datetime | None = None,
                    client: Any = None) -> dict[str, Any] | None:
    """The same read for Zernio's queue: counts per channel against Wan's cap, and the slots its posts hold. Remembered in
    settings.zernio_queue. None when Zernio cannot be read (no key, no channels, unreachable): auto-fill then carries on."""
    now = now or datetime.now(UTC)
    if client is None:
        from . import publisher
        client = publisher.make_clients(settings).get("zernio")
    ids = zernio_ids(settings)
    if client is None or not ids:
        return None
    slots = sorted(((settings.get("brand") or {}).get("regulab") or {}).get("slots") or ["08:00", "13:00", "21:00"])
    try:
        out = summarise(read(client, ids, now, limit=zernio_cap(settings)), slots)
    except senders.SendError as exc:
        log.warning("Zernio queue not read: %s", str(exc)[:160])
        return None
    out["name"] = "Zernio"
    remember(store, out, now, (settings.get(ZKEY) or {}) if isinstance(settings.get(ZKEY), dict) else {}, key=ZKEY, name="Zernio")
    return out


def rest(store: Any, settings: dict[str, Any], now: datetime | None = None) -> None:
    """Buffer is the idle backup, so a pause it wrote while it was the route no longer holds anything back: the banner and the
    log say so instead of showing a stale 'full'. Never raises."""
    before = settings.get(KEY) if isinstance(settings.get(KEY), dict) else {}
    if not before.get("paused"):
        return
    now = now or datetime.now(UTC)
    try:
        store.table(db.SETTINGS).upsert({"key": KEY, "value": {**before, "at": now.isoformat(), "paused": False, "since": None,
                                                              "backup": True}}, on_conflict="key").execute()
        db.log_event(store, "info", "idea", "idea.autofill_resumed",
                     "Auto-isi bersambung: Buffer kini sandaran, queue Zernio yang menentukan")
    except Exception as exc:  # noqa: BLE001
        log.info("buffer_queue not cleared (%s)", str(exc)[:100])


def remember(store: Any, out: dict[str, Any], now: datetime, before: dict[str, Any], key: str = KEY,
             name: str = "Buffer") -> None:
    """Write the queue's settings row (buffer_queue, zernio_queue) for the page, and one log line each time the queue goes full
    or has room again."""
    since = None
    if out["is_full"]:
        since = before.get("since") if before.get("paused") else now.isoformat()
    value = {"at": now.isoformat(), "limit": out["limit"], "counts": out["counts"], "full": out["full"],
             "paused": out["is_full"], "since": since}
    try:
        store.table(db.SETTINGS).upsert({"key": key, "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - a missing table must not stop the worker
        log.info("%s not saved (%s)", key, str(exc)[:100])
    was = bool(before.get("paused"))
    if out["is_full"] and not was:
        top = max(out["counts"].values(), default=0)
        db.log_event(store, "warn", "idea", "idea.autofill_paused",
                     f"Auto-isi dijeda: queue {name} penuh ({', '.join(out['full'])}: {top}/{out['limit']})", detail=value)
    elif was and not out["is_full"]:
        db.log_event(store, "info", "idea", "idea.autofill_resumed",
                     f"Auto-isi bersambung: queue {name} ada ruang semula", detail=value)
