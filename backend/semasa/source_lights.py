"""The watchdog light for every scrape source (Wan, 14 Nov 2026: "make sure watchdog report if status threads, fb, ig and all
scrape, and also add light watchdog in semasa (green live, orange standby, red unlive)").

One light per tab of Isu semasa: regulatory, publication, reddit, youtube, threads, facebook, instagram, folder (OneDrive), myra.

  green   live     the last sweep ran, the source answered, and it has something to show
  orange  standby  not broken, but not working yet: waiting for its first sweep, waiting for a saved login, a quota used up for
                   today, or a source that answered with nothing. Switched off in Settings is also orange, with that reason.
  red     unlive   an error, a login the platform refused, a sweep that has not run for hours, or a source that read nothing in
                   several sweeps in a row.

The lights are worked out here, once, and saved as settings.source_lights, so the page's dot and the watchdog e-mail (health.py)
say the same thing and cannot drift. intake.run refreshes them after every sweep; health.run refreshes them every six hours, which
is what turns a sweep that stopped running red. Nothing here reads a platform or posts anything.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import db, intake
from .log import get_logger

log = get_logger("semasa.source_lights")

KEY = "source_lights"
SECTIONS = ("regulatory", "publication", "reddit", "youtube", "threads", "facebook", "instagram", "folder", "myra")
COMMUNITY = ("reddit", "youtube", "threads", "facebook", "instagram")
NAMES = {"regulatory": "Regulatory", "publication": "Latest publications", "reddit": "Reddit", "youtube": "YouTube",
         "threads": "Threads", "facebook": "Facebook", "instagram": "Instagram", "folder": "OneDrive", "myra": "MYRA"}
SWEEP_STALE = timedelta(hours=14)        # the own-sources sweep runs about three times a day
WATCH_STALE = timedelta(hours=30)        # regulatory and publication are swept once a day
ZERO_RED = 3                             # sweeps in a row that read nothing before orange turns red
GREEN, ORANGE, RED = "green", "orange", "red"


def _parse(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _ago(then: datetime | None, now: datetime) -> str:
    if not then:
        return "never"
    hours = int((now - then).total_seconds() // 3600)
    return f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago"


def _light(color: str, why: str, **extra: Any) -> dict[str, Any]:
    return {"light": color, "why": why[:220], **extra}


def _community(section: str, cfg: dict[str, Any], stored: dict[str, Any], latest: datetime | None, streak: int,
               now: datetime) -> dict[str, Any]:
    com = cfg.get("community") or {}
    sub = com.get(section) if isinstance(com.get(section), dict) else {}
    if cfg.get("enabled") is False or com.get("enabled") is False or (section != "reddit" and sub.get("enabled") is False):
        return _light(ORANGE, "switched off in settings", off=True)
    last = _parse(stored.get("last_run"))
    rep = (stored.get("report") or {}).get("community")
    if not isinstance(rep, dict):
        return _light(ORANGE, "waiting for its first sweep")
    if rep.get("ok") is False:
        return _light(RED, f"the sweep failed: {rep.get('error') or 'no reason given'}")
    if last and now - last > SWEEP_STALE:
        return _light(RED, f"no sweep for {_ago(last, now)}")
    err = str(rep.get(f"{section}_error") or "")
    if err:
        low = err.lower()
        if section == "instagram" and "saved login" in low:
            return _light(ORANGE, "waiting for a saved login (the secret PW_STORAGE_STATE_B64; see ops/SOCIAL-LOGIN.md)",
                          act=True)
        if "quota" in low:
            return _light(ORANGE, "search quota used up for today; it tries again tomorrow")
        if "asked for a login" in low:
            return _light(RED, f"the login was refused or has expired: {err}")
        return _light(RED, err)
    read = int((rep.get("read") or {}).get(section) or 0)
    hours = int(sub.get("hours") or com.get("hours") or 72)
    fresh = bool(latest and now - latest <= timedelta(hours=hours))
    if read > 0 or fresh:
        return _light(GREEN, f"live: {read} read in the last sweep ({_ago(last, now)})")
    if streak >= ZERO_RED:
        return _light(RED, f"read nothing in {streak} sweeps in a row")
    return _light(ORANGE, "answered, but read nothing in the last sweep", act=True)


def _part(section: str, cfg: dict[str, Any], stored: dict[str, Any], now: datetime) -> dict[str, Any]:
    name = "folders" if section == "folder" else "myra"
    if cfg.get("enabled") is False or (cfg.get(name) or {}).get("enabled") is False:
        return _light(ORANGE, "switched off in settings", off=True)
    last = _parse(stored.get("last_run"))
    rep = (stored.get("report") or {}).get(name)
    if not isinstance(rep, dict):
        return _light(ORANGE, "waiting for its first sweep")
    if rep.get("ok") is False:
        return _light(RED, str(rep.get("error") or "the sweep failed"))
    if last and now - last > SWEEP_STALE:
        return _light(RED, f"no sweep for {_ago(last, now)}")
    return _light(GREEN, f"live ({_ago(last, now)})")


def _watch(watch: dict[str, Any], now: datetime) -> dict[str, Any]:
    last = _parse(watch.get("last_run"))
    res = watch.get("result") or {}
    if not last:
        return _light(ORANGE, "waiting for its first sweep")
    if now - last > WATCH_STALE:
        return _light(RED, f"no sweep for {_ago(last, now)}")
    if res.get("error"):
        return _light(RED, f"the sweep failed: {res['error']}")
    srcs = [s for s in (res.get("sources") or []) if isinstance(s, dict)]
    bad = [s for s in srcs if not s.get("ok")]
    if srcs and len(bad) == len(srcs):
        return _light(RED, "every source failed: " + "; ".join(f"{s.get('name')}: {s.get('error')}" for s in bad[:3]))
    if bad:
        names = ", ".join(str(s.get("name")) for s in bad[:4])
        return _light(ORANGE, f"{len(bad)} of {len(srcs)} sources failed: {names}", act=True)
    return _light(GREEN, f"live ({_ago(last, now)})")


def evaluate(cfg: dict[str, Any], stored: dict[str, Any], watch: dict[str, Any], latest: dict[str, datetime | None],
             prev: dict[str, Any], now: datetime, from_sweep: bool = False) -> dict[str, Any]:
    """The nine lights. `prev` is the last saved set: the zero-read streak is carried from it, and added to only when this call
    follows a sweep (from_sweep), so the six-hourly health run never counts the same sweep twice."""
    rep = ((stored.get("report") or {}).get("community")) if isinstance(stored.get("report"), dict) else None
    out: dict[str, Any] = {}
    for s in SECTIONS:
        if s in COMMUNITY:
            before = int(((prev.get(s) or {}).get("zero_streak")) or 0)
            read = int(((rep or {}).get("read") or {}).get(s) or 0) if isinstance(rep, dict) else 0
            streak = (0 if read > 0 else before + 1) if (from_sweep and isinstance(rep, dict)) else before
            res = _community(s, cfg, stored, latest.get(s), streak, now)
            res["zero_streak"] = streak
        elif s in ("folder", "myra"):
            res = _part(s, cfg, stored, now)
        else:
            res = _watch(watch, now)
        out[s] = res
    return out


def _value(store: Any, key: str) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("value").eq("key", key).execute().data or []
    return dict((rows[0].get("value") if rows else None) or {})


def _latest(store: Any, section: str) -> datetime | None:
    q = store.table(intake.WATCH).select("created_at").eq("section", section).order("created_at", desc=True)
    rows = q.limit(1).execute().data
    return _parse((rows or [{}])[0].get("created_at"))


def update(store: Any, now: datetime | None = None, from_sweep: bool = False) -> dict[str, Any]:
    """Work the lights out and save them (settings.source_lights). Never raises: a watchdog that crashes the sweep it watches is
    worse than no light."""
    now = now or datetime.now(UTC)
    try:
        cfg, stored = intake.load_config(store)
        prev = _value(store, KEY).get("lights") or {}
        latest = {s: _latest(store, s) for s in SECTIONS}
        lights = evaluate(cfg, stored, _value(store, "watch"), latest, prev, now, from_sweep)
        store.table(db.SETTINGS).upsert({"key": KEY, "value": {"at": now.isoformat(), "lights": lights},
                                         "updated_at": now.isoformat()}, on_conflict="key").execute()
        return lights
    except Exception as exc:  # noqa: BLE001
        log.warning("source lights not updated: %s", str(exc)[:160])
        return {}


def problems(lights: dict[str, Any]) -> list[dict[str, str]]:
    """The watchdog lines (health.py): every red, and every orange that needs someone (a login to save, a source that reads
    nothing). An orange that mends itself (waiting for a first sweep, a quota that resets tomorrow) or that Wan switched off is
    only a light on the page, never an e-mail."""
    out = []
    for s in SECTIONS:
        v = lights.get(s) or {}
        if v.get("light") == RED or (v.get("light") == ORANGE and v.get("act")):
            state = "UNLIVE" if v["light"] == RED else "STANDBY"
            out.append({"area": f"Scrape · {NAMES[s]}", "what": f"{state}: {v.get('why')}",
                        "todo": "Open Isu semasa and the tab's light; run Sources (only=community) once the cause is fixed."})
    return out
