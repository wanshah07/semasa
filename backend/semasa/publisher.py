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
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import compliance, db, guard, senders
from .config import SupabaseSettings
from .log import get_logger
from .studio_link import when_utc

log = get_logger("semasa.publisher")

MYT = timedelta(hours=8)
LATE_GRACE = timedelta(minutes=45)    # Studio's LATE_GRACE_MS: a slot long past is never fired automatically
LOOKAHEAD = timedelta(days=14)


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
    rows = store.table(db.MEDIA).select("id,status,generated_media_url,type,mode,meta").in_("id", ids).execute().data or []
    by_id = {r["id"]: r for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def scan_entry(m: dict[str, Any]) -> dict[str, Any]:
    """What the compliance scan needs of one attached media: its alt text and, for a slide set,
    the words it was drawn from (so a set drawn from older words blocks the send)."""
    meta = m.get("meta") or {}
    entry: dict[str, Any] = {"alt": meta.get("alt") or ""}
    if m.get("mode") == "slides":
        # a Design-tab artwork carries its own words; a post's carousel is a drawing of the post's slides
        entry["artwork" if meta.get("design") else "slides"] = meta.get("slides") or []
    return entry


def pictures_of(m: dict[str, Any]) -> list[str]:
    """The addresses a media row sends: every slide of a carousel, in order, else its one file."""
    if m.get("mode") == "slides":
        return [u for u in ((m.get("meta") or {}).get("slide_urls") or []) if u]
    return [m["generated_media_url"]] if m.get("generated_media_url") else []


SHARE_NOW_WITHIN = timedelta(minutes=2)
BUFFER_ID = re.compile(r"^[a-f0-9]{24}$")


def publishing_on(settings: dict[str, Any], now: datetime) -> bool:
    """On when `enabled` is true, or once `enabled_from` (an ISO moment with its zone) has passed; `paused` wins over
    both. `enabled_from` is how the switch opens by itself on the night Studio is retired (supabase/023), with nobody
    at a keyboard."""
    pub = settings.get("publishing") or {}
    if pub.get("paused") is True:
        return False
    if pub.get("enabled") is True:
        return True
    since = pub.get("enabled_from")
    if not since:
        return False
    try:
        at = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
    except ValueError:
        return False
    return at.tzinfo is not None and now >= at


def myt_date(dt: datetime):
    return (dt + MYT).date()


def make_clients(settings: dict[str, Any]) -> dict[str, Any]:
    """The senders this run can use: each exists only when its secret AND its settings are there."""
    cfg = settings.get("channels") or {}
    out: dict[str, Any] = {}
    buf, li = cfg.get("buffer") or {}, cfg.get("linkedin") or {}
    if os.environ.get("BUFFER_API_KEY") and buf.get("organizationId"):
        out["buffer"] = senders.Buffer(os.environ["BUFFER_API_KEY"], buf["organizationId"])
    if os.environ.get("COMPOSIO_CONSUMER_KEY") and li.get("author"):
        # For You (the workspace that holds Wan's LinkedIn connection): wins over a Platform key if both are set
        out["linkedin"] = senders.LinkedInMCP(os.environ["COMPOSIO_CONSUMER_KEY"], li["author"],
                                              account_id=li.get("foryou_account_id") or None)
    elif os.environ.get("COMPOSIO_API_KEY") and li.get("author"):
        out["linkedin"] = senders.LinkedIn(os.environ["COMPOSIO_API_KEY"], li["author"],
                                           account_id=li.get("account_id") or None)
    return out


def buffer_channels(settings: dict[str, Any], stream: str) -> list[str]:
    """The platforms a post goes to: the stream's list, less any Buffer channel switched off in settings."""
    plats = compliance.platforms_for(stream)
    if stream == "linkedin":
        return plats
    enabled = ((settings.get("channels") or {}).get("buffer") or {}).get("enabled") or {}
    return [p for p in plats if enabled.get(p, True) is not False]


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return when_utc(str(ts))            # Studio's own display stamps ("2026-09-28 06:43 MYT" and friends)
    return dt if dt.tzinfo else None


def linkedin_sent_on(store: Any, day) -> int:
    rows = store.table(db.POSTS).select("stream,published").eq("stream", "linkedin").execute().data or []
    n = 0
    for r in rows:
        at = _parse(((r.get("published") or {}).get("linkedin") or {}).get("at"))
        if at and myt_date(at) == day:
            n += 1
    return n


class _BufferView:
    """What Buffer already holds, read once per channel per run: the no-double-post check."""

    def __init__(self, client: Any, now: datetime):
        self.client, self.now, self.cache = client, now, {}

    def find(self, channel_id: str, text: str, due: datetime) -> dict[str, Any] | None:
        if channel_id not in self.cache:
            self.cache[channel_id] = self.client.posts(
                [channel_id], (self.now - timedelta(days=3)).isoformat(), (self.now + LOOKAHEAD + timedelta(days=2)).isoformat())
        key = senders.text_key(text)
        for p in self.cache[channel_id]:
            at = _parse(p.get("dueAt"))
            if (p.get("status") not in ("error", "draft") and senders.text_key(p.get("text", "")) == key
                    and at and abs(at - due) <= timedelta(hours=36)):
                return p
        return None

    def add(self, channel_id: str, post: dict[str, Any]) -> None:
        self.cache.setdefault(channel_id, []).append(post)


def _record(bp: dict[str, Any], mode: str, route: str, now: datetime) -> dict[str, Any]:
    return {"id": bp.get("id"), "status": bp.get("status"), "dueAt": bp.get("dueAt"), "mode": mode,
            "route": route, "at": now.isoformat(), **({"url": bp["externalLink"]} if bp.get("externalLink") else {}),
            **({"unconfirmed": True} if bp.get("unconfirmed") else {})}


def _send_buffer(client: Any, view: _BufferView, channel_id: str, channel: str, text: str, pictures: list[str],
                 alt: str, due: datetime, now: datetime) -> dict[str, Any]:
    """One channel of one post into Buffer. Returns the record for `published`; raises SendError."""
    share_now = due <= now + SHARE_NOW_WITHIN
    due_iso = None if share_now else due.isoformat()
    mode = "shareNow" if share_now else "customScheduled"
    for attempt in (1, 2):
        try:
            bp = client.create(channel_id, channel, text, pictures, alt, due_iso)
        except senders.SendError as exc:
            if exc.kind != "transient" or attempt == 2:
                raise
            if view.find(channel_id, text, due) is not None:   # the first try did land after all
                view.cache.pop(channel_id, None)
                return _record(view.find(channel_id, text, due), mode, "buffer-adopted", now)
            continue
        if share_now:
            fin = client.confirm(bp["id"])
            err = (fin.get("error") or {}).get("message") or ""
            if fin.get("status") == "error":
                kind = senders.classify(err)
                if kind == "transient" and attempt == 1:
                    continue                                    # Studio's TRANSIENT_SEND: one identical retry
                raise senders.SendError(kind, f"{channel}: {err or 'Buffer reported an error'}")
            bp = {**bp, **fin}
        view.add(channel_id, bp)
        return _record(bp, mode, "buffer", now)
    raise senders.SendError("refused", "unreachable")


def run(store: Any, now: datetime | None = None, clients: dict[str, Any] | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    enabled = publishing_on(settings, now)
    brand = settings.get("brand") or {}
    reg = brand.get("regulab") or {}
    bufcfg = (settings.get("channels") or {}).get("buffer") or {}
    if clients is None:
        clients = make_clients(settings) if enabled else {}
    counts = {"considered": 0, "dry_run": 0, "blocked": 0, "error": 0, "overdue": 0,
              "scheduled": 0, "sent": 0, "adopted": 0, "waiting": 0, "not_yet": 0}
    view = _BufferView(clients["buffer"], now) if clients.get("buffer") else None
    li_cap = max(1, len((brand.get("linkedin") or {}).get("slots") or ["06:00"]))
    li_today: int | None = None

    posts = (store.table(db.POSTS).select("*").eq("status", "approved").not_.is_("date", "null")
             .not_.is_("slot", "null").order("date").order("slot").execute().data or [])
    live = guard.load_live(store, db.POSTS, myt_date(now)) if posts else []
    for post in posts:
        due = due_utc(post["date"], post["slot"])
        if due > now + LOOKAHEAD:
            continue
        counts["considered"] += 1
        stream = post.get("stream") or "regulab"
        media = media_for(store, list(post.get("media_ids") or []))
        scan_post = {**post, "media": [scan_entry(m) for m in media if m.get("status") == "done"]}
        flags = compliance.scan(scan_post, brand=reg, schedule=reg.get("schedule"),
                                indo_extra=(settings.get("bahasa") or {}).get("indo"))
        hard = [f"{f['where']}: {f['msg']}" for f in flags if f["hard"]]
        not_ready = [m["id"] for m in media if m.get("status") != "done" or not m.get("generated_media_url")]
        if not_ready:
            hard.append(f"{len(not_ready)} picture(s) not generated yet")
        gone = [i for i in (post.get("media_ids") or []) if i not in {m["id"] for m in media}]
        if gone:
            # a picture approved with the post has since been deleted: sending without it is not what Wan approved
            hard.append(f"{len(gone)} picture(s) approved with this post no longer exist; attach them again and approve")
        # one post to a slot and the same words never twice: only the post that outranks the others goes (guard.py)
        hard += guard.blockers(post, live)
        lang = compliance.lang_of(post)
        published = dict(post.get("published") or {})
        errors = {k: v for k, v in (post.get("errors") or {}).items() if k != "scan"}
        changed = False
        pictures = [u for m in media for u in pictures_of(m)]
        alt = " ".join(str((m.get("meta") or {}).get("alt") or "") for m in media).strip()
        channels = buffer_channels(settings, stream)
        for channel in channels:
            if published.get(channel):
                continue
            text = compliance.text_of(post, channel, lang)
            payload = {"channel": channel, "due_at": due.isoformat(), "text": text, "media": pictures}
            fp = fingerprint(payload)
            if hard:
                counts["blocked"] += 1
                if not logged(store, post["id"], channel, "blocked", fp):
                    write_log(store, post["id"], channel, "blocked", {"fingerprint": fp, "why": hard})
                continue
            late = (myt_date(due) < myt_date(now)) if stream == "linkedin" else (due < now - LATE_GRACE)
            if late:
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
            prior = errors.get(channel)
            if isinstance(prior, dict) and prior.get("fingerprint") == fp:
                continue                                   # refused before with these exact words; an edit sends again
            client = clients.get("linkedin" if stream == "linkedin" else "buffer")
            if client is None:
                counts["error"] += 1
                if not logged(store, post["id"], channel, "error", fp):
                    write_log(store, post["id"], channel, "error",
                              {"fingerprint": fp, "why": f"publishing is on, but no {channel} sender is set up (its "
                                                         "secret or its settings are missing); nothing was sent"})
                continue

            if stream == "linkedin":
                if due > now:
                    counts["not_yet"] += 1                 # LinkedIn has no queue: it goes at its slot, never before
                    continue
                if li_today is None:
                    li_today = linkedin_sent_on(store, myt_date(now))
                if li_today >= li_cap:
                    counts["waiting"] += 1
                    if not logged(store, post["id"], channel, "wait", fp):
                        write_log(store, post["id"], channel, "wait", {"fingerprint": fp, "why": (
                            f"LinkedIn's daily cap ({li_cap}) is used; a post whose day has passed is not sent")})
                    continue
                if logged(store, post["id"], channel, "sending", fp) and not logged(store, post["id"], channel, "sent", fp):
                    # an earlier run began this send and never recorded the answer: it may be on LinkedIn already
                    msg = ("An earlier run started sending this and never heard back. Check LinkedIn; if it is not "
                           "there, edit the post and approve it again to send it.")
                    errors[channel] = {"fingerprint": fp, "message": msg, "unconfirmed": True, "at": now.isoformat()}
                    changed = True
                    counts["error"] += 1
                    write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": msg})
                    continue
                write_log(store, post["id"], channel, "sending", {"fingerprint": fp, "pictures": len(pictures)})
                try:
                    try:
                        res = client.post(text, pictures)
                    except senders.SendError as exc:
                        if exc.kind != "transient" or "LinkedIn" in exc.message:
                            raise                          # a refusal FROM LinkedIn may still have posted: no retry
                        res = client.post(text, pictures)  # the upload/connection hiccuped before the post was made
                except senders.SendError as exc:
                    errors[channel] = {"fingerprint": fp, "message": exc.message, "kind": exc.kind,
                                       "at": now.isoformat()}
                    changed = True
                    counts["error"] += 1
                    write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": exc.message})
                    continue
                published[channel] = {"id": res.urn, "url": res.url, "status": "sent", "at": now.isoformat(),
                                      "route": "composio+image" if pictures else "composio"}
                errors.pop(channel, None)
                changed = True
                li_today += 1
                counts["sent"] += 1
                write_log(store, post["id"], channel, "sent", {"fingerprint": fp, "urn": res.urn})
                continue

            channel_id = bufcfg.get(channel)
            if not channel_id:
                counts["error"] += 1
                if not logged(store, post["id"], channel, "error", fp):
                    write_log(store, post["id"], channel, "error",
                              {"fingerprint": fp, "why": f"no Buffer channel id for {channel} in settings"})
                continue
            if channel == "instagram" and not pictures:
                errors[channel] = {"fingerprint": fp, "message": "Instagram needs a picture and this post has none",
                                   "at": now.isoformat()}
                changed = True
                counts["error"] += 1
                write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": errors[channel]["message"]})
                continue
            try:
                found = view.find(channel_id, text, due)
                if found:
                    published[channel] = _record(found, "customScheduled", "buffer-adopted", now)
                    counts["adopted"] += 1
                    write_log(store, post["id"], channel, "adopted", {"fingerprint": fp, "buffer_id": found.get("id")})
                else:
                    rec = _send_buffer(client, view, channel_id, channel, text, pictures, alt, due, now)
                    published[channel] = rec
                    action = "sent" if rec.get("status") == "sent" else "scheduled"
                    counts[action] += 1
                    write_log(store, post["id"], channel, action,
                              {"fingerprint": fp, "buffer_id": rec.get("id"), "due_at": due.isoformat()})
                errors.pop(channel, None)
                changed = True
            except senders.SendError as exc:
                if exc.kind == "full":
                    counts["waiting"] += 1               # Buffer's plan cap: a wait, never an error
                    if not logged(store, post["id"], channel, "wait", fp):
                        write_log(store, post["id"], channel, "wait", {"fingerprint": fp, "why": exc.message})
                    continue
                errors[channel] = {"fingerprint": fp, "message": exc.message, "kind": exc.kind, "at": now.isoformat()}
                changed = True
                counts["error"] += 1
                write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": exc.message})

        patch: dict[str, Any] = {}
        if hard:
            errors["scan"] = hard
            errors["at"] = now.isoformat()
        elif "at" in errors and not any(k in errors for k in channels):
            errors.pop("at")
        if changed or hard or (post.get("errors") or {}) != errors:
            patch["errors"] = errors
        if changed:
            patch["published"] = published
            if channels and all(published.get(c) for c in channels):
                patch["status"] = "posted" if all(published[c].get("status") == "sent" for c in channels) else "scheduled"
        if patch:
            store.table(db.POSTS).update(patch).eq("id", post["id"]).execute()

    if enabled and clients.get("buffer"):
        tally(store, clients["buffer"], now, counts, settings)
    return counts


def tally(store: Any, client: Any, now: datetime, counts: dict[str, int], settings: dict[str, Any]) -> None:
    """Read back every Buffer post whose moment has passed and write down what the network actually did (Studio's
    reconcileBuffer): `sent` or `error`, and a post whose every channel is sent becomes `posted`."""
    counts.setdefault("confirmed", 0)
    rows = (store.table(db.POSTS).select("id,status,stream,published,errors").in_("status", ["approved", "scheduled"])
            .execute().data or [])
    for post in rows:
        published = dict(post.get("published") or {})
        errors = dict(post.get("errors") or {})
        changed = False
        for ch, rec in list(published.items()):
            if not isinstance(rec, dict) or not BUFFER_ID.match(str(rec.get("id") or "")):
                continue
            if rec.get("status") in ("sent", "error"):
                continue
            due = _parse(rec.get("dueAt"))
            if due and due > now - timedelta(minutes=5):
                continue
            try:
                got = client.get(rec["id"])
            except senders.SendError:
                continue
            status = got.get("status")
            if status not in ("sent", "error"):
                continue
            published[ch] = {**rec, "status": status, **({"url": got["externalLink"]} if got.get("externalLink") else {}),
                             "confirmed_at": now.isoformat()}
            if status == "error":
                msg = (got.get("error") or {}).get("message") or "Buffer reported an error"
                errors[ch] = {"message": f"{ch}: {msg}", "at": now.isoformat()}
                write_log(store, post["id"], ch, "error", {"buffer_id": rec["id"], "why": msg})
            else:
                write_log(store, post["id"], ch, "confirmed", {"buffer_id": rec["id"]})
            counts["confirmed"] += 1
            changed = True
        if not changed:
            continue
        patch: dict[str, Any] = {"published": published, "errors": errors}
        channels = buffer_channels(settings, post.get("stream") or "regulab")
        if all((published.get(c) or {}).get("status") == "sent" for c in channels):
            patch["status"] = "posted"
        store.table(db.POSTS).update(patch).eq("id", post["id"]).execute()


def main() -> int:
    store = db.client(SupabaseSettings.load())
    counts = run(store)
    log.info("publisher: %s", counts)
    from . import archive, sheet
    archived = archive.run(store)                     # before the sheet, so today's archive rows go with it
    archived += "; " + archive.purge_rejected(store)   # rejected 72 hours ago (021)
    log.info(archived)
    log.info(sheet.sync_log(store))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## Semasa publisher\n\n" + ", ".join(f"{k} {v}" for k, v in counts.items()) + f"\n\n{archived}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
