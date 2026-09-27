"""The link to ws.regulab Studio, until Wan retires it (Wan, 27 Sep 2026: "link ws.regulab studio with the system, so
once the draft posted, deleted automatically in the system, until I instruct to retire the studio").

Studio's drafts came over once (supabase/020, the three import files), each under an id made from its Studio id, so the
same Studio draft always has the same Semasa id. Studio keeps posting them. When it does, the Semasa copy must leave the
drafts queue at once: approving it here as well would post the same story twice the day Semasa publishes.

A Studio post that went out is therefore taken out of the drafts and filed as `posted` in the Arkib, with Studio's
delivery records (Buffer / LinkedIn ids and times) in `published`, compacted exactly as archive.py compacts Semasa's own
posts. It is filed, not deleted, for one reason: the idea it came from is how the bot knows that story was already
written (010, 019). A deleted copy would let the same news be written again as a new draft.

Who calls this: a Routine that reads Studio's store after each Studio release run (ops/STUDIO-LINK-ROUTINE.md) and starts
the `studio-link` workflow with what went out. This module never reads Studio and never sends anything anywhere.
Nothing here writes `approved`; a copy Semasa itself already posted is never touched.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .archive import compact_text
from .log import get_logger

log = get_logger("semasa.studio_link")

# the namespace the import used (the Studio artifact's own address): the same Studio id gives the same Semasa id
STUDIO_NS = uuid.uuid5(uuid.NAMESPACE_URL, "https://claude.ai/code/artifact/531c7408-8042-4ebe-b729-2e8cfad7258a")
CHANNELS = ("instagram", "facebook", "threads", "linkedin")
MOVABLE = ("draft", "approved", "rejected", "scheduled")
MYT = timedelta(hours=8)
MAX_ITEMS = 500


class LinkError(ValueError):
    """The message from the Routine could not be read: nothing is changed."""


def semasa_id(studio_id: str) -> str:
    return str(uuid.uuid5(STUDIO_NS, f"drafts/{studio_id}"))


def when_utc(stamp: Any) -> datetime | None:
    """Studio's delivery stamp is its page's display form, "2026-09-24 19:25 MYT"; a real ISO time is taken as it is."""
    s = str(stamp or "").strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?\s*MYT$", s)
    if m:
        return datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}:{m.group(3)}:00").replace(tzinfo=UTC) - MYT
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else None


def parse(raw: str) -> dict[str, dict[str, dict[str, Any]]]:
    """{"<studio id>": {"<channel>": {"id": …, "at": …, "url": …}}} — only what went out, per channel.
    Anything else is refused whole: a half-read message must not move half the queue."""
    try:
        data = json.loads(raw or "")
    except json.JSONDecodeError as exc:
        raise LinkError(f"not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise LinkError("expected an object keyed by Studio draft id")
    if len(data) > MAX_ITEMS:
        raise LinkError(f"{len(data)} items; at most {MAX_ITEMS} in one message")
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for sid, chans in data.items():
        if not isinstance(sid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", sid):
            raise LinkError(f"not a Studio draft id: {str(sid)[:40]!r}")
        if not isinstance(chans, dict) or not chans:
            raise LinkError(f"{sid}: no channel records")
        kept: dict[str, dict[str, Any]] = {}
        for ch, rec in chans.items():
            if ch not in CHANNELS:
                raise LinkError(f"{sid}: unknown channel {str(ch)[:20]!r}")
            rec = rec if isinstance(rec, dict) else {}
            kept[ch] = {k: str(rec[k])[:300] for k in ("id", "at", "url") if rec.get(k)}
        out[sid] = kept
    return out


def apply(store: Any, posted: dict[str, dict[str, dict[str, Any]]], now: datetime | None = None) -> dict[str, Any]:
    """File every Semasa copy of a Studio post that went out. Returns what happened, for the log and the job summary."""
    now = now or datetime.now(UTC)
    ids = {semasa_id(sid): sid for sid in posted}
    rows = []
    for chunk in (list(ids)[i:i + 100] for i in range(0, len(ids), 100)):
        rows += store.table(db.POSTS).select("*").in_("id", chunk).execute().data or []
    by_id = {r["id"]: r for r in rows}
    moved, already, unknown = [], [], []
    for pid, sid in ids.items():
        row = by_id.get(pid)
        if not row:
            unknown.append(sid)               # a Studio draft made after the import: Semasa never had a copy
            continue
        if row.get("status") not in MOVABLE:
            already.append(sid)               # already history (the import, or an earlier run of this)
            continue
        records = {ch: {**rec, "via": "ws.regulab Studio"} for ch, rec in posted[sid].items()}
        published = {**(row.get("published") or {}), **records}
        times = [t for t in (when_utc(r.get("at")) for r in posted[sid].values()) if t]
        post = {**row, "published": published}
        update = {"status": "posted", "published": published, "text": compact_text(post), "flags": [], "hard_flags": 0,
                  "errors": {}, "posted_at": (max(times) if times else now).isoformat(), "archived_at": now.isoformat()}
        res = (store.table(db.POSTS).update(update).eq("id", pid).in_("status", list(MOVABLE)).execute().data or [])
        if res:
            moved.append((sid, pid, row.get("status"), row.get("hook") or ""))
        else:
            already.append(sid)               # changed between the read and the write: left as it now is
    if moved:
        # the per-row "Post diterbitkan" lines the triggers just wrote would read as if Semasa had published; one honest
        # line replaces them
        try:
            store.table(db.LOG).delete().eq("event", "post.posted").in_("ref_id", [m[1] for m in moved]) \
                .gte("at", (now - timedelta(minutes=5)).isoformat()).execute()
        except Exception as exc:  # noqa: BLE001 - the extra lines are only noise
            log.info("could not tidy the per-post log lines: %s", str(exc)[:120])
        was = {}
        for m in moved:
            was[m[2]] = was.get(m[2], 0) + 1
        db.log_event(store, "info", "post", "studio.posted",
                     f"ws.regulab Studio menerbitkan {len(moved)} post: salinannya di Semasa dipindah ke Arkib",
                     detail={"moved": [{"studio_id": m[0], "post_id": m[1], "was": m[2], "hook": m[3][:120]}
                                       for m in moved], "was": was})
    return {"moved": len(moved), "already": len(already), "unknown": len(unknown),
            "moved_ids": [m[0] for m in moved], "unknown_ids": unknown}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    raw = open(argv[0], encoding="utf-8").read() if argv else os.environ.get("STUDIO_POSTED", "")
    try:
        posted = parse(raw)
    except LinkError as exc:
        log.error("studio link: nothing changed, the message could not be read (%s)", exc)
        return 2
    store = db.client()
    out = apply(store, posted)
    line = (f"studio link: {out['moved']} copy(ies) filed as posted, {out['already']} already history, "
            f"{out['unknown']} not in Semasa")
    log.info(line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"## Studio link\n\n{line}\n\nMoved: {', '.join(out['moved_ids']) or '-'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
