"""A post whose date and slot have gone by moves to the next free slot of its stream (Wan, 22 Nov 2026: "kalau terlepas tarikh
dan masa, auto cari next slot").

Three callers, one rule:
  * the publisher (publisher.run): an APPROVED post nothing has been handed over for, whose slot the publisher would refuse as
    late (ws.regulab more than 45 minutes gone; LinkedIn past the day it may still go, li_send_day), is moved forward and stays
    approved. It is never sent late, and a post Buffer, Zernio or LinkedIn already holds anything for is never touched.
  * Telegram's Approve (telegram_bot.decide): a draft with no position, a slot gone by, or a slot another post holds is moved to
    the next free slot first and then approved through the database gate, as for the page.
  * the page's Approve (web/src/lib/slots.js approvePosition) does the same in the browser.

"Free" is the same everywhere: no other post of the stream that is not rejected holds that date and slot (supabase/026 and
guard.py: one post to a slot), no Motion film was booked for it (autofill.film_positions), the stream posts that day, and for
ws.regulab the rota gives the post's domain that day (ideas.next_free_position). The new slot is never one due within LEAD, so a
post is never moved onto a moment the publisher cannot reach (web/src/lib/slots.js nextFreeSlot leadMin).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.rollforward")

MYT = timedelta(hours=8)
LATE_GRACE = timedelta(minutes=45)     # publisher.LATE_GRACE, web/src/lib/slots.js LATE_GRACE_MIN
LEAD = timedelta(minutes=30)           # web/src/lib/slots.js nextFreeSlot leadMin
HORIZON_DAYS = 60                      # web/src/lib/slots.js nextFreeSlot horizon
WHY_WORDS = {"none": "tiada tarikh atau slot", "past": "slotnya sudah lepas", "taken": "slotnya sudah dipegang post lain"}
WHY_EN = {"none": "it had no date or slot", "past": "its slot had passed", "taken": "its slot was held by another post"}


def due_utc(date: Any, slot: Any) -> datetime | None:
    """The slot as a UTC moment (date and slot are Malaysia time), or None when either is missing or unreadable."""
    try:
        y, m, d = (int(x) for x in str(date or "")[:10].split("-"))
        hh, mm = (int(x) for x in str(slot or "").split(":")[:2])
        return datetime(y, m, d, hh, mm, tzinfo=UTC) - MYT
    except (TypeError, ValueError):
        return None


def slot_gone(stream: str, date: Any, slot: Any, now: datetime, linkedin_queued: bool = False) -> bool:
    """Would the publisher refuse this position as late? ws.regulab (and LinkedIn through Zernio, `linkedin_queued`): more than
    45 minutes past its slot. LinkedIn through Composio: past the day it may still be sent on (publisher.li_send_day).
    web/src/lib/slots.js slotGone says the same for the page."""
    due = due_utc(date, slot)
    if due is None:
        return False
    if (stream or "regulab") == "linkedin" and not linkedin_queued:
        from .publisher import li_send_day, myt_date
        return myt_date(now) > li_send_day(due)
    return due < now - LATE_GRACE


def holders(store: Any, post: dict[str, Any]) -> list[dict[str, Any]]:
    """Other posts of the stream, not rejected, on this post's date and slot."""
    if not post.get("date") or not post.get("slot"):
        return []
    stream = post.get("stream") or "regulab"
    rows = (store.table(db.POSTS).select("id,stream,status,date,slot,hook").eq("stream", stream).eq("date", post["date"])
            .eq("slot", post["slot"]).neq("status", "rejected").execute().data or [])
    return [r for r in rows if r.get("id") != post.get("id")]


def why_move(store: Any, post: dict[str, Any], now: datetime, linkedin_queued: bool = False) -> str:
    """"" when the post may stay where it is; else why it must move: "none", "past" or "taken"."""
    if due_utc(post.get("date"), post.get("slot")) is None:
        return "none"
    if slot_gone(post.get("stream") or "regulab", post.get("date"), post.get("slot"), now, linkedin_queued):
        return "past"
    if holders(store, post):
        return "taken"
    return ""


def taken_now(store: Any, stream: str, now: datetime) -> set[tuple[str, str]]:
    """Every position of the stream a post (not rejected) or a booked Motion film holds, from today (Malaysia time) on."""
    from . import autofill, ideas
    return set(ideas.taken_positions(store, stream, now)) | set(autofill.film_positions(store, stream))


def next_position(post: dict[str, Any], brand: dict[str, Any], taken: set[tuple[str, str]], now: datetime,
                  lead: timedelta = LEAD) -> tuple[str, str] | None:
    """The first free position for the post's stream from TODAY (Malaysia time), never one due within `lead`: the worker's own
    rule (ideas.next_free_position, which starts tomorrow, is asked from yesterday with today's too-soon slots marked taken)."""
    from . import ideas
    stream = post.get("stream") or "regulab"
    domain = post.get("domain") if stream == "regulab" else None
    cfg = brand.get(stream) or {}
    slots = cfg.get("slots") or (["08:00", "13:00", "21:00"] if stream == "regulab" else ["06:00"])
    today = (now + MYT).date().isoformat()
    soon = {(today, s) for s in slots if (due_utc(today, s) or now) <= now + lead}
    date, slot = ideas.next_free_position(stream, domain, brand, set(taken) | soon, now - timedelta(days=1),
                                          horizon_days=HORIZON_DAYS)
    return (date, slot) if date and slot else None


def decision(by: str, why: str, old: dict[str, Any], date: str, slot: str, now: datetime) -> dict[str, Any]:
    was = f"{old.get('date') or '-'} {old.get('slot') or ''}".strip()
    return {"at": now.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "by": by, "action": "moved",
            "note": f"from {was} to {date} {slot}: {WHY_EN.get(why, why)}"}


def move(store: Any, post: dict[str, Any], date: str, slot: str, why: str, by: str, now: datetime,
         status: str) -> dict[str, Any] | None:
    """Write the new position, pinned to the post still having `status` and the updated_at it was read with, and carrying no
    hand-over record. The row as written, or None when the pin missed (someone changed the post meanwhile)."""
    patch: dict[str, Any] = {"date": date, "slot": slot}
    if "decisions" in post:
        patch["decisions"] = [*(post.get("decisions") or []), decision(by, why, post, date, slot, now)][-50:]
    q = store.table(db.POSTS).update(patch).eq("id", post["id"]).eq("status", status)
    if post.get("updated_at"):
        q = q.eq("updated_at", post["updated_at"])
    rows = q.execute().data or []
    if not rows:
        return None
    got = rows[0]
    return {**post, **patch, **({"updated_at": got["updated_at"]} if got.get("updated_at") else {})}


def describe(post: dict[str, Any], old: dict[str, Any], why: str) -> str:
    who = {"regulab": "ws.regulab", "linkedin": "LinkedIn"}.get(post.get("stream") or "regulab", post.get("stream") or "")
    name = str(post.get("hook") or post.get("id"))[:70]
    was = f"{old.get('date') or '-'} {old.get('slot') or ''}".strip()
    return f"• {who}: {name}\n  {was} → {post['date']} {post['slot']} MYT ({WHY_WORDS.get(why, why)})"


def roll_missed(store: Any, posts: list[dict[str, Any]], settings: dict[str, Any], now: datetime,
                linkedin_queued: bool = False, notify: Any = None) -> list[dict[str, Any]]:
    """The publisher's roll-forward. Every APPROVED post in `posts` with nothing handed over yet (no `published` record) whose
    slot the publisher would refuse as late moves to the next free slot of its stream, oldest slot first, still approved.
    `posts` is changed in place (the moved posts carry their new date, slot and updated_at) and the moves are returned. Wan
    is told on Telegram, once for the run. A post with no free slot ahead stays where it is (the publisher calls it overdue)."""
    brand = settings.get("brand") or {}
    taken: dict[str, set[tuple[str, str]]] = {}
    moved: list[dict[str, Any]] = []
    stuck: list[str] = []
    for i, post in enumerate(posts):
        stream = post.get("stream") or "regulab"
        if post.get("status") != "approved" or post.get("published"):
            continue
        if not slot_gone(stream, post.get("date"), post.get("slot"), now, linkedin_queued and stream == "linkedin"):
            continue
        if stream not in taken:
            taken[stream] = taken_now(store, stream, now)
        pos = next_position(post, brand, taken[stream], now)
        if pos is None:
            stuck.append(str(post.get("hook") or post.get("id"))[:70])
            continue
        try:
            new = move(store, post, pos[0], pos[1], "past", "publisher", now, "approved")
        except Exception as exc:  # noqa: BLE001 - one post never stops the run
            log.warning("post %s not moved: %s", post.get("id"), str(exc)[:200])
            continue
        if new is None:
            continue                                  # changed meanwhile: the next run reads it again
        taken[stream].add(pos)
        posts[i] = new
        moved.append({"id": post["id"], "from": [post.get("date"), post.get("slot")], "to": list(pos),
                      "line": describe(new, post, "past")})
        db.log_event(store, "info", "publish", "publish.moved",
                     f"Slot terlepas: {str(post.get('hook') or post['id'])[:80]} dipindah dari {post.get('date')} "
                     f"{post.get('slot')} ke {pos[0]} {pos[1]}",
                     ref_table=db.POSTS, ref_id=post["id"],
                     detail={"from": {"date": post.get("date"), "slot": post.get("slot")}, "to": {"date": pos[0], "slot": pos[1]},
                             "stream": stream, "why": "past"})
    if moved or stuck:
        lines = []
        if moved:
            lines.append(f"⏰ {len(moved)} post diluluskan terlepas slotnya, jadi dipindah ke slot kosong seterusnya "
                         "(masih diluluskan, penerbit hantar pada slot baharu):")
            lines += [m["line"] for m in moved[:10]]
        if stuck:
            lines.append(f"⚠️ Tiada slot kosong dalam {HORIZON_DAYS} hari untuk {len(stuck)} post: " + "; ".join(stuck[:5]))
        tell(store, "\n".join(lines), notify)
    return moved


def tell(store: Any, text: str, notify: Any = None) -> bool:
    """A Telegram message to Wan when the bot is linked. Never raises."""
    try:
        if notify is not None:
            return bool(notify(store, text))
        from . import telegram_bot
        return bool(telegram_bot.notify(store, text))
    except Exception as exc:  # noqa: BLE001
        log.info("move not told on Telegram (%s)", str(exc)[:120])
        return False
