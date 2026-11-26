"""A rest between browser reads of Instagram and Threads (Wan, 26 Nov 2026: "add limit" so the saved login lasts longer).

Instagram flagged the saved login within about 14 hours of a working read on 25 Nov (green 13:41 UTC, "asked for a login" again
by 03:29 UTC) and Threads reads 70 posts a sweep: a login that opens many pages in a short time is the thing a platform
challenges. Three limits, all on the browser reads (the Reddit, YouTube and regulator reads are not touched):

  1. fewer pages per sweep (social_web.PER_TAG_IG, PER_ACCOUNT_IG, MAX_TAGS, MAX_ACCOUNTS);
  2. a random pause between page loads (`social_web.pace`), never the same beat twice;
  3. a MINIMUM GAP between sweeps of one platform: Instagram `DEFAULT_HOURS["instagram"]` hours, Threads
     `DEFAULT_HOURS["threads"]` (`settings.sources.community.pace` = {"instagram": 11, "threads": 5}, 0 = no limit).
     "Sweep now" on the page overrides the gap, because Wan asked for it.

A paused platform keeps its last read count in the report, so its light does not turn orange for a rest it was told to take.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.social_pace")

KEY = "social_pace"                    # semasa_settings row: {"instagram": "<when it last read>", "threads": "..."}
DEFAULT_HOURS = {"instagram": 11, "threads": 5}


def hours_of(cfg: dict[str, Any], platform: str) -> float:
    """The minimum hours between two sweeps of `platform`: the settings' own number (0 = none), else the default."""
    raw = (cfg.get("pace") or {}).get(platform) if isinstance(cfg.get("pace"), dict) else None
    if raw is None:
        return float(DEFAULT_HOURS.get(platform, 0))
    try:
        return max(0.0, min(72.0, float(raw)))
    except (TypeError, ValueError):
        return float(DEFAULT_HOURS.get(platform, 0))


def last_read(store: Any, platform: str) -> datetime | None:
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", KEY).execute().data or []
        raw = ((rows[0].get("value") if rows else None) or {}).get(platform)
        at = datetime.fromisoformat(str(raw).replace("Z", "+00:00")) if raw else None
        return at if at and at.tzinfo else None
    except Exception as exc:  # noqa: BLE001 - no row, no table or a bad stamp is "never read": the read goes ahead
        log.info("pace not read (%s)", str(exc)[:100])
        return None


def next_read(store: Any, cfg: dict[str, Any], platform: str, now: datetime, forced: bool = False) -> datetime | None:
    """None when `platform` may be read now; else the moment its rest ends."""
    gap = hours_of(cfg, platform)
    last = last_read(store, platform)
    if forced or gap <= 0 or last is None:
        return None
    ready = last + timedelta(hours=gap)
    return ready if ready > now else None


def mark(store: Any, platform: str, now: datetime) -> None:
    """Record that `platform` was read now (an attempt counts: a refused login must not be hammered either)."""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", KEY).execute().data or []
        value = dict((rows[0].get("value") if rows else None) or {})
        value[platform] = now.isoformat()
        store.table(db.SETTINGS).upsert({"key": KEY, "value": value, "updated_at": now.isoformat()}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - a missing table never stops a sweep
        log.info("pace not saved (%s)", str(exc)[:100])


def rest_note(platform: str, until: datetime) -> str:
    """The line the report and the light show for a platform that is resting."""
    return f"resting to keep the saved login alive: next {platform.title()} read after {until.astimezone(UTC):%d %b %H:%M} UTC"


def carried_read(store: Any, platform: str) -> int:
    """What the platform's last real sweep read, from the stored report: a resting platform keeps its green light."""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", "sources").execute().data or []
        rep = (((rows[0].get("value") if rows else None) or {}).get("report") or {}).get("community") or {}
        return int((rep.get("read") or {}).get(platform) or 0)
    except Exception:  # noqa: BLE001
        return 0
