"""Filling empty slots (Studio's nightly drafter, brought over 27 Sep 2026), OFF until Wan switches it on in Settings.

Semasa's rule so far is that no idea is written without Wan's click. This step keeps that rule while it is off, which is
how it ships (supabase/022 seeds settings "autofill" with enabled false). Switched on, each worker run looks at the next
`days_ahead` days, finds positions no post holds and no waiting idea is already written for, and writes an idea FOR that
position from the Regulatory and Latest publication feed (semasa_watch): an item the writer judged relevant, that Wan
did not hide, that no idea has used, and, for ws.regulab, whose domain the rota gives that day. The ideas step then
writes the draft in the same run. Everything stays a DRAFT: nothing here approves, schedules or posts, and the publisher
is still a dry run. A gap with no fitting item is left a gap and said so, never filled with something off-rota.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .ideas import ANY_DAY_DOMAINS, MYT
from .log import get_logger

log = get_logger("semasa.autofill")

WATCH = "semasa_watch"
FRESH_DAYS = 21                 # an item older than this is not news any more
MAX_DAYS, MAX_PER_RUN = 7, 5


def config(settings: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    raw = settings.get("autofill") if isinstance(settings.get("autofill"), dict) else {}
    on = raw.get("enabled") is True
    if not on and raw.get("enabled_from"):
        # the same self-opening switch as publishing (supabase/023): autofill starts the night Studio's drafter stops
        try:
            at = datetime.fromisoformat(str(raw["enabled_from"]).replace("Z", "+00:00"))
            on = at.tzinfo is not None and (now or datetime.now(UTC)) >= at
        except ValueError:
            on = False
    days = max(1, min(MAX_DAYS, int(raw.get("days_ahead") or 3)))
    per = max(1, min(MAX_PER_RUN, int(raw.get("per_run") or 2)))
    streams = [s for s in (raw.get("streams") or ["regulab", "linkedin"]) if s in ("regulab", "linkedin")]
    return {"enabled": on, "days_ahead": days, "per_run": per, "streams": streams}


def gaps(stream: str, brand: dict[str, Any], taken: set[tuple[str, str]], days: int,
         now: datetime | None = None) -> list[tuple[str, str, list[str] | None]]:
    """(date, slot, the rota's domains that day) for every free position from tomorrow, Malaysia time. Today is left
    alone: a draft written now still needs Wan to read and approve it before its slot."""
    cfg = brand.get(stream) or {}
    slots = sorted(cfg.get("slots") or (["08:00", "13:00", "21:00"] if stream == "regulab" else ["06:00"]))
    today = ((now or datetime.now(UTC)) + MYT).date()
    out = []
    for i in range(1, days + 1):
        d = today + timedelta(days=i)
        dow = (d.weekday() + 1) % 7
        allow = None
        if stream == "regulab":
            allow = (cfg.get("schedule") or {}).get(str(dow))
            if isinstance(allow, str):
                allow = [allow]
            if allow is not None and not allow:
                continue                                       # a no-posting day
        else:
            ds = cfg.get("days")
            if ds and dow not in ds:
                continue
        out += [(d.isoformat(), s, allow) for s in slots if (d.isoformat(), s) not in taken]
    return out


def held(store: Any, stream: str, now: datetime | None = None) -> set[tuple[str, str]]:
    """Positions a post already holds (a rejected one holds nothing), read on the same clock as the gaps."""
    today = ((now or datetime.now(UTC)) + MYT).date().isoformat()
    rows = (store.table(db.POSTS).select("date,slot,status").eq("stream", stream).gte("date", today)
            .neq("status", "rejected").execute().data or [])
    return {(str(r["date"]), r["slot"]) for r in rows if r.get("date") and r.get("slot")}


def asked_for(store: Any, stream: str) -> set[tuple[str, str]]:
    """Positions a waiting idea is already being written for: never two ideas for one slot."""
    rows = (store.table(db.IDEAS).select("stream,status,brief").in_("status", ["new", "working"]).execute().data or [])
    out = set()
    for r in rows:
        pos = (r.get("brief") or {}).get("position") if isinstance(r.get("brief"), dict) else None
        if (r.get("stream") or "regulab") == stream and isinstance(pos, dict) and pos.get("date") and pos.get("slot"):
            out.add((str(pos["date"]), str(pos["slot"])))
    return out


SELECT = "id,section,source,kind,title,url,summary,why,domain,raw,published_at,created_at"


def candidates(store: Any, now: datetime | None = None) -> list[dict[str, Any]]:
    """Feed items an idea has not used yet. News is fresh for FRESH_DAYS; the OneDrive angle bank is not news and has no
    age limit (its rows are written once, when a file is first read, and wait until they are used)."""
    since = ((now or datetime.now(UTC)) - timedelta(days=FRESH_DAYS)).isoformat()
    rows = (store.table(WATCH).select(SELECT).eq("relevant", True).eq("dismissed", False).gte("created_at", since)
            .neq("section", "folder").order("created_at", desc=True).limit(200).execute().data or [])
    bank = (store.table(WATCH).select(SELECT).eq("section", "folder").eq("relevant", True).eq("dismissed", False)
            .order("created_at", desc=True).limit(300).execute().data or [])
    rows = rows + bank
    if not rows:
        return []
    urls = [r["url"] for r in rows]
    spent: set[str] = set()
    for chunk in db._in_filter_chunks(urls):
        spent |= {r.get("source_url") for r in (store.table(db.IDEAS).select("source_url").in_("source_url", chunk)
                                                .execute().data or [])}
    return [r for r in rows if r["url"] not in spent]


def pick(pool: list[dict[str, Any]], stream: str, allow: list[str] | None, day: str) -> dict[str, Any] | None:
    """An urgent file for THIS date first (Studio's `urgent post/DDMMYY` override), then the first item that fits."""
    for x in pool:
        if (x.get("raw") or {}).get("urgent_for") == day:
            return x
    return next((x for x in pool if fits(x, stream, allow)), None)


def fits(item: dict[str, Any], stream: str, allow: list[str] | None) -> bool:
    if stream == "linkedin":
        return True                                            # every section reads as a chemist's post
    dom = item.get("domain")
    if not allow:
        return True
    return dom in allow or dom in ANY_DAY_DOMAINS


def run(store: Any, settings: dict[str, Any], now: datetime | None = None) -> str:
    cfg = config(settings, now)
    if not cfg["enabled"]:
        return "Autofill: off (switch it on in Settings)"
    try:
        pool = candidates(store, now)
        brand = settings.get("brand") or {}
        made, empty = 0, 0
        for stream in cfg["streams"]:
            busy = held(store, stream, now) | asked_for(store, stream)
            for date, slot, allow in gaps(stream, brand, busy, cfg["days_ahead"], now):
                if made >= cfg["per_run"]:
                    break
                item = pick(pool, stream, allow, date)
                if not item:
                    empty += 1
                    continue
                pool.remove(item)
                domain = None
                urgent = (item.get("raw") or {}).get("urgent_for") == date
                if stream == "regulab":
                    domain = item.get("domain") if item.get("domain") and (urgent or fits(item, stream, allow)) else None
                    if allow and domain not in allow and domain not in ANY_DAY_DOMAINS and not urgent:
                        domain = allow[0]
                store.table(db.IDEAS).insert({
                    "source_title": str(item.get("title") or "")[:500], "source_url": item["url"],
                    "source_name": item.get("source") or None,
                    "source_summary": (str(item.get("summary") or item.get("why") or "")
                                       + (f" (Rujukan dalam dokumen: {(item.get('raw') or {}).get('cite')})"
                                          if (item.get("raw") or {}).get("cite") else ""))[:4000] or None,
                    "stream": stream, "domain": domain,
                    "angle": ("F" if item.get("section") == "publication" else "A") if stream == "linkedin" else None,
                    "make_media": "image", "status": "new", "created_by": None,
                    # no note: the writer reads a note as Wan's words, and a note also lifts the already-published
                    # guard (ideas.process_idea). What this idea is for rides in the brief, shown as a pill.
                    "note": "",
                    "brief": {"position": {"date": date, "slot": slot}, "auto": True, "watch_id": item["id"]},
                }).execute()
                made += 1
        if made:
            db.log_event(store, "info", "idea", "idea.autofill",
                         f"{made} idea ditulis untuk slot kosong (auto-isi); draf menunggu kelulusan",
                         detail={"made": made, "no_fitting_item": empty})
        return f"Autofill: {made} idea(s) written for empty slots" + (f"; {empty} gap(s) had no fitting item" if empty else "")
    except Exception as exc:  # noqa: BLE001 - a missing table or setting must not stop the worker
        log.warning("autofill skipped: %s", exc)
        return f"Autofill: skipped ({str(exc)[:120]})"
