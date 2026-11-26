"""What happens to an idea the writer could not turn into a draft (Wan, 26 Nov 2026).

Three failures used to sit in the Ideas tab as an error card, each asking Wan to press "Cuba lagi" or add a note:

  * the writer did not build the hook on one of the 25 hook shapes (asked twice)  -> the writer is pushed again by itself, up to
    HOOK_RETRIES more times, each time with a firmer ask and, from the second, on the built-in 25 shapes whatever style was set;
  * the same event is already written up for this stream                          -> an idea the AUTOFILL wrote is deleted;
  * the writer judged this headline no fit for the stream (a cookie notice, a bare title, a number)  -> the same.

Only an idea autofill wrote (`brief.auto`) is deleted: an idea Wan typed himself keeps its card, because he is the one who can
add the note it asks for. A deleted idea leaves a tombstone (`settings.autofill_skip`, the newest SKIP_KEEP source keys) so the
next run does not pick the same row again and fail the same way. Never raises: a failure of this step leaves the error card as
it was.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.idea_failures")

HOOK_RETRIES = 3
SKIP_KEY = "autofill_skip"
SKIP_KEEP = 1500
HOOK_MARK = "did not build the hook on one of"
TWIN_MARK = "the same event is already written up for this stream"
PUBLISHED_MARK = "already has a"                      # "this news already has a posted post for this stream"
NOFIT_MARK = "the writer judged this headline no fit"


def kind_of(message: str) -> str | None:
    """"hook", "twin", "nofit" or None for the failure the message names."""
    if HOOK_MARK in message and "asked twice" in message:
        return "hook"
    if TWIN_MARK in message or (PUBLISHED_MARK in message and "not written again" in message):
        return "twin"
    if NOFIT_MARK in message:
        return "nofit"
    return None


def skip_key(idea: dict[str, Any]) -> str:
    """The key a tombstone is kept under: the idea's source address, or faq://<id> for an FAQ answer."""
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    if idea.get("source_url"):
        return str(idea["source_url"])
    return f"faq://{brief['faq_id']}" if brief.get("faq_id") else ""


def skipped(store: Any) -> set[str]:
    """The source keys autofill must not pick again."""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", SKIP_KEY).execute().data or []
        return {str(k) for k in ((rows[0].get("value") if rows else None) or {}).get("keys") or []}
    except Exception as exc:  # noqa: BLE001 - no row or no table is "nothing skipped"
        log.info("skip list not read (%s)", str(exc)[:100])
        return set()


def _remember(store: Any, key: str, now: datetime) -> None:
    keys = [k for k in skipped(store) if k != key]
    keys = [*keys, key][-SKIP_KEEP:]
    store.table(db.SETTINGS).upsert({"key": SKIP_KEY, "value": {"keys": keys}, "updated_at": now.isoformat()},
                                    on_conflict="key").execute()


def settle(store: Any, idea: dict[str, Any], message: str, now: datetime | None = None) -> str:
    """Deal with a failed idea: "retry" (back in the queue), "deleted" (an autofill idea removed) or "" (the error card stays)."""
    now = now or datetime.now(UTC)
    kind = kind_of(message)
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    try:
        if kind == "hook":
            tries = int(brief.get("hook_retry") or 0) + 1
            if tries > HOOK_RETRIES:
                return ""                                           # the card stays: Wan sees what the writer could not do
            nxt = {**brief, "hook_retry": tries}
            if tries >= 2:
                nxt.pop("hook_style", None)                         # a custom style may be what confuses it: the built-in 25
            store.table(db.IDEAS).update({"status": "new", "error": None, "brief": nxt}).eq("id", idea["id"]).execute()
            db.log_event(store, "info", "idea", "idea.hook_retry",
                         f"Penulis tidak membina hook: dicuba semula sendiri ({tries}/{HOOK_RETRIES}): "
                         f"{str(idea.get('source_title') or '')[:70]}", ref_table=db.IDEAS, ref_id=idea.get("id"))
            return "retry"
        if kind in ("twin", "nofit") and brief.get("auto"):
            key = skip_key(idea)
            if key:
                _remember(store, key, now)
            store.table(db.IDEAS).delete().eq("id", idea["id"]).execute()
            db.log_event(store, "info", "idea", "idea.auto_deleted",
                         f"Idea auto dipadam ({'peristiwa sama sudah ditulis' if kind == 'twin' else 'penulis: tidak sesuai'}): "
                         f"{str(idea.get('source_title') or '')[:70]}", detail={"why": message[:300], "key": key})
            return "deleted"
    except Exception as exc:  # noqa: BLE001 - the error card stays as it was
        log.warning("idea %s failure not settled: %s", str(idea.get("id"))[:8], str(exc)[:120])
    return ""
