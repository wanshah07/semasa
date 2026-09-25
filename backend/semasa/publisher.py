"""Publisher. Entry point: `python -m semasa.publisher` (publish.yml, 06:20 · 11:20 · 19:20 MYT).

Studio's gate, kept: only a post a person APPROVED is ever considered, and it is re-checked
here with the same rules the page used (rules/compliance.json) before anything leaves.

PUBLISHING IS OFF. `semasa_settings.publishing.enabled` is false and the browser cannot change
it (only the SQL editor can). While it is off this module is a DRY RUN: for every approved post
coming up it writes to `semasa_publish_log` exactly what it WOULD send — channel, time, caption,
pictures — and sends nothing. That log is how Semasa is proven before it replaces Studio.

Turning it on before the Buffer and LinkedIn senders exist does not send either: it records an
`error` saying so. And never turn it on while ws.regulab Studio's Routines still run: two
publishers on one Buffer account post everything twice (argus CLAUDE.md rule 1: one schedule
per job, in the repo that owns the job).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import compliance, db
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.publisher")

MYT = timedelta(hours=8)
LATE_GRACE = timedelta(minutes=45)    # Studio's LATE_GRACE_MS: a slot long past is never fired automatically
LOOKAHEAD = timedelta(days=14)
SENDERS: dict[str, Any] = {}          # channel -> sender; empty until the Buffer/LinkedIn senders are ported


def due_utc(date: str, slot: str) -> datetime:
    y, m, d = (int(x) for x in str(date)[:10].split("-"))
    hh, mm = (int(x) for x in slot.split(":"))
    return datetime(y, m, d, hh, mm, tzinfo=UTC) - MYT


def fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def load_settings(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").execute().data or []
    return {r["key"]: r["value"] for r in rows}


def logged(store: Any, post_id: str, channel: str, action: str, fp: str) -> bool:
    rows = (store.table(db.PUBLISH_LOG).select("detail").eq("post_id", post_id).eq("channel", channel)
            .eq("action", action).order("at", desc=True).limit(20).execute().data or [])
    return any((r.get("detail") or {}).get("fingerprint") == fp for r in rows)


def write_log(store: Any, post_id: str, channel: str, action: str, detail: dict[str, Any]) -> None:
    store.table(db.PUBLISH_LOG).insert({"post_id": post_id, "channel": channel, "action": action,
                                        "detail": detail}).execute()


def media_for(store: Any, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    rows = store.table(db.MEDIA).select("id,status,generated_media_url,type,meta").in_("id", ids).execute().data or []
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def run(store: Any, now: datetime | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    enabled = bool((settings.get("publishing") or {}).get("enabled"))
    brand = settings.get("brand") or {}
    reg = brand.get("regulab") or {}
    counts = {"considered": 0, "dry_run": 0, "blocked": 0, "error": 0, "overdue": 0}

    posts = (store.table(db.POSTS).select("*").eq("status", "approved").not_.is_("date", "null")
             .not_.is_("slot", "null").order("date").order("slot").execute().data or [])
    for post in posts:
        due = due_utc(post["date"], post["slot"])
        if due > now + LOOKAHEAD:
            continue
        counts["considered"] += 1
        media = media_for(store, list(post.get("media_ids") or []))
        scan_post = {**post, "media": [{"alt": (m.get("meta") or {}).get("alt") or ""} for m in media
                                       if m.get("status") == "done"]}
        flags = compliance.scan(scan_post, brand=reg, schedule=reg.get("schedule"))
        hard = [f"{f['where']}: {f['msg']}" for f in flags if f["hard"]]
        not_ready = [m["id"] for m in media if m.get("status") != "done" or not m.get("generated_media_url")]
        if not_ready:
            hard.append(f"{len(not_ready)} picture(s) not generated yet")
        lang = compliance.lang_of(post)
        for channel in compliance.platforms_for(post.get("stream") or "regulab"):
            if (post.get("published") or {}).get(channel):
                continue
            payload = {"channel": channel, "due_at": due.isoformat(),
                       "text": compliance.text_of(post, channel, lang),
                       "media": [m.get("generated_media_url") for m in media]}
            fp = fingerprint(payload)
            if hard:
                counts["blocked"] += 1
                if not logged(store, post["id"], channel, "blocked", fp):
                    write_log(store, post["id"], channel, "blocked", {"fingerprint": fp, "why": hard})
                continue
            if due < now - LATE_GRACE:
                counts["overdue"] += 1
                if not logged(store, post["id"], channel, "blocked", fp):
                    write_log(store, post["id"], channel, "blocked",
                              {"fingerprint": fp, "why": [f"overdue: its slot was {post['date']} {post['slot']} MYT; "
                                                          "move it to a new slot"]})
                continue
            if not enabled:
                counts["dry_run"] += 1
                if not logged(store, post["id"], channel, "dry_run", fp):
                    write_log(store, post["id"], channel, "dry_run",
                              {"fingerprint": fp, "would_send": payload, "chars": len(payload["text"])})
                continue
            sender = SENDERS.get(channel)
            counts["error"] += 1
            if sender is None and not logged(store, post["id"], channel, "error", fp):
                write_log(store, post["id"], channel, "error",
                          {"fingerprint": fp, "why": f"publishing is on, but no {channel} sender exists in this "
                                                     "version of Semasa; nothing was sent"})
        if hard:
            store.table(db.POSTS).update({"errors": {"scan": hard, "at": now.isoformat()}}).eq("id", post["id"]).execute()
    return counts


def main() -> int:
    store = db.client(SupabaseSettings.load())
    counts = run(store)
    log.info("publisher: %s", counts)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## Semasa publisher\n\n" + ", ".join(f"{k} {v}" for k, v in counts.items()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
