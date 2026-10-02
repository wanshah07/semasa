"""Two things must never reach Buffer or LinkedIn: two posts in one slot, and the same words twice.

Wan, 3 Oct 2026: "make blocker to avoid duplicate post to be posted, and more than 1 post in 1 slot". Three layers say
the same thing in the same terms: the page (web/src/lib/slots.js moveCheck / duplicatesOf), the database for a browser's
writes (supabase/026_slot_and_duplicate_guard.sql) and this module for what the publisher sends. The publisher's layer is
the one that cannot be bypassed, because the importer and the worker write with the service key, which the database
guard deliberately leaves alone (an import must be able to bring a clash over so a person can see and fix it).

A post is blocked only by a post that OUTRANKS it, so exactly one of a clashing pair goes and the other waits for a person:
  1. a post already scheduled or posted outranks everything (Buffer or LinkedIn already holds it);
  2. then an approved post that has already sent a channel (half done is not undone by a newcomer);
  3. then whichever was approved first (approved_at, else created_at), the id breaking a tie.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from . import compliance

KEY_LEN = 120                 # letters of a caption that must match (web/src/lib/slots.js DUP_KEY_LEN)
MIN_LEN = 20                  # a shorter caption carries too little to call a copy
WINDOW_DAYS = 90              # the same words months later are not what this stops
LIVE = ("approved", "scheduled", "posted")
_STRIP = re.compile(r"[\W_]+")


def caption_key(text: Any) -> str:
    """First 120 letters and digits of a caption, lower-cased, everything else squeezed out; "" when too short."""
    k = _STRIP.sub("", str(text or "").lower())[:KEY_LEN]
    return k if len(k) >= MIN_LEN else ""


def caption_keys(post: dict[str, Any]) -> set[str]:
    """The keys of every caption the post would send: its sent language, each platform."""
    by_plat = (post.get("text") or {}).get(compliance.lang_of(post)) or {}
    return {k for k in (caption_key(v) for v in by_plat.values()) if k}


def rank(p: dict[str, Any]) -> tuple[int, str, str]:
    """Lower outranks higher (see the module docstring)."""
    if p.get("status") in ("scheduled", "posted"):
        tier = 0
    elif p.get("published"):
        tier = 1
    else:
        tier = 2
    return tier, str(p.get("approved_at") or p.get("created_at") or ""), str(p.get("id"))


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def blockers(post: dict[str, Any], live: list[dict[str, Any]]) -> list[str]:
    """Why this approved post must not be sent: [] when nothing outranks it. `live` is every approved, scheduled or
    posted post nearby (this one included; it is skipped by id)."""
    stream = post.get("stream") or "regulab"
    mine = rank(post)
    out: list[str] = []
    keys = caption_keys(post)
    day = _day(post.get("date"))
    for o in live:
        if o.get("id") == post.get("id") or (o.get("stream") or "regulab") != stream or o.get("status") not in LIVE:
            continue
        if rank(o) >= mine:
            continue
        name = str(o.get("hook") or o.get("id"))[:60]
        who = f'"{name}" ({o.get("status")}, {o.get("date") or "no date"} {o.get("slot") or ""})'.strip()
        if post.get("date") and post.get("slot") and o.get("date") == post["date"] and o.get("slot") == post["slot"]:
            out.append(f"slot clash: {who} already holds {post['date']} {post['slot']}; move one of the two posts")
        od = _day(o.get("date"))
        if keys and (day is None or od is None or abs((od - day).days) <= WINDOW_DAYS) and keys & caption_keys(o):
            out.append(f"duplicate: {who} already carries these words; change the wording or reject one of them")
    return out


def load_live(store: Any, table: str, today: date) -> list[dict[str, Any]]:
    """Every approved, scheduled or posted post within the duplicate window of today (and the future)."""
    since = (today - timedelta(days=WINDOW_DAYS + 1)).isoformat()
    return (store.table(table).select("id,stream,status,date,slot,hook,lang,text,published,approved_at,created_at")
            .in_("status", list(LIVE)).gte("date", since).execute().data or [])
