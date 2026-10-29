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

import requests

from . import compliance, db, guard, postiz, publishing, senders
from .config import SupabaseSettings
from .log import get_logger
from .studio_link import when_utc

log = get_logger("semasa.publisher")

MYT = timedelta(hours=8)
LATE_GRACE = timedelta(minutes=45)  # Studio's LATE_GRACE_MS: a slot long past is never fired automatically
LOOKAHEAD = timedelta(days=14)


def due_utc(date: str, slot: str) -> datetime:
    y, m, d = (int(x) for x in str(date)[:10].split("-"))
    hh, mm = (int(x) for x in slot.split(":"))
    return datetime(y, m, d, hh, mm, tzinfo=UTC) - MYT


def fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def load_settings(store: Any) -> dict[str, Any]:
    rows = db.read_with_retry(store.table(db.SETTINGS).select("key,value")).data or []
    return {r["key"]: r["value"] for r in rows}


def logged(store: Any, post_id: str, channel: str, action: str, fp: str) -> bool:
    rows = (
        store.table(db.PUBLISH_LOG)
        .select("detail")
        .eq("post_id", post_id)
        .eq("channel", channel)
        .eq("action", action)
        .order("at", desc=True)
        .limit(20)
        .execute()
        .data
        or []
    )
    return any((r.get("detail") or {}).get("fingerprint") == fp for r in rows)


def write_log(store: Any, post_id: str, channel: str, action: str, detail: dict[str, Any]) -> None:
    store.table(db.PUBLISH_LOG).insert({"post_id": post_id, "channel": channel, "action": action, "detail": detail}).execute()


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


def video_of(m: dict[str, Any]) -> dict[str, Any] | None:
    """A video media row as the senders take it: its address, its poster and whether it stands upright (a Reel)."""
    if m.get("type") != "video" or not m.get("generated_media_url"):
        return None
    meta = m.get("meta") or {}
    return {
        "url": m["generated_media_url"],
        "thumbnail": meta.get("poster_url") or "",
        "vertical": int(meta.get("height") or 0) > int(meta.get("width") or 0) > 0,
    }


def pictures_of(m: dict[str, Any]) -> list[str]:
    """The addresses a media row sends: every slide of a carousel, in order, else its one file. A video is not a picture."""
    if m.get("type") == "video":
        return []
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
    pz = cfg.get("postiz") or {}
    if os.environ.get("POSTIZ_API_KEY") and os.environ.get("POSTIZ_BASE_URL") and pz.get("enabled") is True:
        out["postiz"] = postiz.Postiz(os.environ["POSTIZ_API_KEY"], os.environ["POSTIZ_BASE_URL"])
    if os.environ.get("BUFFER_API_KEY") and buf.get("organizationId"):
        out["buffer"] = senders.Buffer(os.environ["BUFFER_API_KEY"], buf["organizationId"])
    if os.environ.get("COMPOSIO_CONSUMER_KEY") and li.get("author"):
        # For You (the workspace that holds Wan's LinkedIn connection): wins over a Platform key if both are set
        out["linkedin"] = senders.LinkedInMCP(
            os.environ["COMPOSIO_CONSUMER_KEY"], li["author"], account_id=li.get("foryou_account_id") or None
        )
    elif os.environ.get("COMPOSIO_API_KEY") and li.get("author"):
        out["linkedin"] = senders.LinkedIn(os.environ["COMPOSIO_API_KEY"], li["author"], account_id=li.get("account_id") or None)
    return out


def buffer_channels(settings: dict[str, Any], stream: str) -> list[str]:
    """The platforms a post goes to: the stream's list, less any Buffer channel switched off in settings."""
    plats = compliance.platforms_for(stream)
    if stream == "linkedin":
        return plats
    enabled = ((settings.get("channels") or {}).get("buffer") or {}).get("enabled") or {}
    return [p for p in plats if enabled.get(p, True) is not False]


def post_channels(settings: dict[str, Any], post: dict[str, Any]) -> list[str]:
    """The platforms this post goes to: its stream's switched-on channels, narrowed to the ones Wan chose for it when it
    was queued to some of them (a Motion film), never widened."""
    return [p for p in buffer_channels(settings, post.get("stream") or "regulab") if p in compliance.platforms_of(post)]


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return when_utc(str(ts))  # Studio's own display stamps ("2026-09-28 06:43 MYT" and friends)
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
                [channel_id], (self.now - timedelta(days=3)).isoformat(), (self.now + LOOKAHEAD + timedelta(days=2)).isoformat()
            )
        key = senders.text_key(text)
        for p in self.cache[channel_id]:
            at = _parse(p.get("dueAt"))
            if (
                p.get("status") not in ("error", "draft")
                and senders.text_key(p.get("text", "")) == key
                and at
                and abs(at - due) <= timedelta(hours=36)
            ):
                return p
        return None

    def add(self, channel_id: str, post: dict[str, Any]) -> None:
        self.cache.setdefault(channel_id, []).append(post)


def _record(bp: dict[str, Any], mode: str, route: str, now: datetime) -> dict[str, Any]:
    return {
        "id": bp.get("id"),
        "status": bp.get("status"),
        "dueAt": bp.get("dueAt"),
        "mode": mode,
        "route": route,
        "at": now.isoformat(),
        **({"url": bp["externalLink"]} if bp.get("externalLink") else {}),
        **({"unconfirmed": True} if bp.get("unconfirmed") else {}),
    }


def _send_buffer(
    client: Any,
    view: _BufferView,
    channel_id: str,
    channel: str,
    text: str,
    pictures: list[str],
    alt: str,
    due: datetime,
    now: datetime,
    video: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One channel of one post into Buffer. Returns the record for `published`; raises SendError."""
    share_now = due <= now + SHARE_NOW_WITHIN
    due_iso = None if share_now else due.isoformat()
    mode = "shareNow" if share_now else "customScheduled"
    for attempt in (1, 2):
        try:
            bp = (
                client.create_video(channel_id, channel, text, video, due_iso)
                if video
                else client.create(channel_id, channel, text, pictures, alt, due_iso)
            )
        except senders.SendError as exc:
            if exc.kind != "transient" or attempt == 2:
                raise
            view.cache.pop(channel_id, None)  # the pre-attempt cache cannot show a post made just now:
            found = view.find(channel_id, text, due)  # force a fresh read before deciding to retry
            if found is not None:  # the first try did land after all
                return _record(found, mode, "buffer-adopted", now)
            continue
        if share_now:
            fin = client.confirm(bp["id"])
            err = (fin.get("error") or {}).get("message") or ""
            if fin.get("status") == "error":
                kind = senders.classify(err)
                if kind == "transient" and attempt == 1:
                    continue  # Studio's TRANSIENT_SEND: one identical retry
                raise senders.SendError(kind, f"{channel}: {err or 'Buffer reported an error'}")
            bp = {**bp, **fin}
        view.add(channel_id, bp)
        return _record(bp, mode, "buffer", now)
    raise senders.SendError("refused", "unreachable")


def _postiz_package(
    post: dict[str, Any], channel: str, text: str, integration_id: str, due: datetime, media: list[dict[str, Any]], fetch: Any
) -> publishing.ContentPackage:
    assets = []
    for row in media:
        urls = pictures_of(row) if row.get("type") != "video" else [row["generated_media_url"]]
        sums = (row.get("meta") or {}).get("sha256")
        for i, url in enumerate(urls):
            try:
                response = fetch(url, timeout=60)
                response.raise_for_status()
            except requests.RequestException as exc:
                raise postiz.PostizError(f"could not fetch approved media {row['id']}: {exc}") from exc
            data = response.content
            actual = hashlib.sha256(data).hexdigest()
            expected = sums[i] if isinstance(sums, list) and i < len(sums) else sums
            if expected and expected != actual:
                raise postiz.MediaValidationError(f"media {row['id']} changed after approval")
            mime = (row.get("meta") or {}).get("content_type") or ("video/mp4" if row.get("type") == "video" else "image/jpeg")
            assets.append(
                publishing.MediaAsset(
                    f"{row['id']}:{i}", url, mime, data, actual, len(data), (row.get("meta") or {}).get("seconds")
                )
            )
    key = f"{post['id']}:{channel}:{publishing.approval_token(post, media, {channel: integration_id})}"
    return publishing.ContentPackage(
        post["id"],
        text,
        channel,
        integration_id,
        due.isoformat(),
        "Asia/Kuala_Lumpur",
        key,
        tuple(assets),
        tuple(a.asset_id for a in assets),
    )


def _send_postiz(client: Any, package: publishing.ContentPackage, now: datetime) -> dict[str, Any]:
    found = client.find_by_key(package.idempotency_key, package.scheduled_at)
    result = found or client.publish(package)
    return {
        "id": result.post_id,
        "status": result.status,
        "dueAt": result.due_at,
        "route": "postiz",
        "at": now.isoformat(),
        **({"url": result.url} if result.url else {}),
        **({"confirmed_at": now.isoformat()} if result.status in ("sent", "error") else {}),
    }


def run(store: Any, now: datetime | None = None, clients: dict[str, Any] | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    enabled = publishing_on(settings, now)
    brand = settings.get("brand") or {}
    reg = brand.get("regulab") or {}
    bufcfg = (settings.get("channels") or {}).get("buffer") or {}
    if clients is None:
        clients = make_clients(settings) if enabled else {}
    counts = {
        "considered": 0,
        "dry_run": 0,
        "blocked": 0,
        "error": 0,
        "overdue": 0,
        "scheduled": 0,
        "sent": 0,
        "adopted": 0,
        "waiting": 0,
        "not_yet": 0,
    }
    view = _BufferView(clients["buffer"], now) if clients.get("buffer") else None
    li_cap = max(1, len((brand.get("linkedin") or {}).get("slots") or ["06:00"]))
    li_today: int | None = None

    posts = (
        db.read_with_retry(
            store.table(db.POSTS)
            .select("*")
            .eq("status", "approved")
            .not_.is_("date", "null")
            .not_.is_("slot", "null")
            .order("date")
            .order("slot")
        ).data
        or []
    )
    live = guard.load_live(store, db.POSTS, myt_date(now)) if posts else []
    for post in posts:
        due = due_utc(post["date"], post["slot"])
        if due > now + LOOKAHEAD:
            continue
        counts["considered"] += 1
        stream = post.get("stream") or "regulab"
        media = media_for(store, list(post.get("media_ids") or []))
        scan_post = {**post, "media": [scan_entry(m) for m in media if m.get("status") == "done"]}
        flags = compliance.scan(
            scan_post, brand=reg, schedule=reg.get("schedule"), indo_extra=(settings.get("bahasa") or {}).get("indo")
        )
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
        video = next((v for v in (video_of(m) for m in media) if v), None)  # a post's video stands alone (no pictures)
        alt = " ".join(str((m.get("meta") or {}).get("alt") or "") for m in media).strip()
        channels = post_channels(settings, post)
        route = publishing.provider_for(post, settings)
        account_ids = (
            {c: ((settings.get("channels") or {}).get("postiz") or {}).get(c) for c in channels} if route == "postiz" else {}
        )
        if enabled and route == "postiz" and not publishing.approval_valid(post, media, account_ids):
            hard.append("approval is missing or stale for this exact provider, content, media, accounts and schedule")
        for channel in channels:
            if published.get(channel):
                continue
            text = compliance.text_of(post, channel, lang)
            payload = {"channel": channel, "due_at": due.isoformat(), "text": text, "media": pictures}
            if video:
                payload["video"] = video["url"]
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
                    write_log(
                        store,
                        post["id"],
                        channel,
                        "blocked",
                        {
                            "fingerprint": fp,
                            "why": [f"overdue: its slot was {post['date']} {post['slot']} MYT; move it to a new slot"],
                        },
                    )
                continue
            if not enabled:
                counts["dry_run"] += 1
                if not logged(store, post["id"], channel, "dry_run", fp):
                    write_log(
                        store,
                        post["id"],
                        channel,
                        "dry_run",
                        {"fingerprint": fp, "would_send": payload, "chars": len(payload["text"])},
                    )
                continue
            prior = errors.get(channel)
            if route != "postiz" and isinstance(prior, dict) and (prior.get("outcome") == "unknown" or prior.get("unconfirmed")):
                continue  # legacy providers have no reliable readback: never retry ambiguous sends
            if isinstance(prior, dict) and prior.get("fingerprint") == fp:
                continue  # refused before with these exact words; an edit sends again
            if route == "postiz":
                client = clients.get("postiz")
                if client is None:
                    counts["error"] += 1
                    write_log(
                        store,
                        post["id"],
                        channel,
                        "error",
                        {
                            "fingerprint": fp,
                            "why": (
                                "Postiz is selected but its API key, base URL or enabled setting is missing; "
                                "no backup was selected"
                            ),
                        },
                    )
                    continue
                integration_id = account_ids.get(channel)
                if not integration_id:
                    counts["error"] += 1
                    write_log(
                        store, post["id"], channel, "error", {"fingerprint": fp, "why": f"no Postiz integration id for {channel}"}
                    )
                    continue
                try:
                    package = _postiz_package(post, channel, text, integration_id, due, media, requests.get)
                    rec = _send_postiz(client, package, now)
                    published[channel] = rec
                    errors.pop(channel, None)
                    changed = True
                    counts["sent" if rec["status"] == "sent" else "scheduled"] += 1
                    store.table(db.POSTS).update({"published": published}).eq("id", post["id"]).execute()
                    write_log(
                        store,
                        post["id"],
                        channel,
                        "sent" if rec["status"] == "sent" else "scheduled",
                        {"fingerprint": fp, "postiz_id": rec["id"], "readback": True},
                    )
                except postiz.UnknownOutcome as exc:
                    errors[channel] = {
                        "fingerprint": fp,
                        "message": str(exc),
                        "outcome": "unknown",
                        "unconfirmed": True,
                        "at": now.isoformat(),
                    }
                    changed = True
                    counts["error"] += 1
                    write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": str(exc), "outcome": "unknown"})
                except (postiz.PostizError, ValueError) as exc:
                    errors[channel] = {
                        "fingerprint": fp,
                        "message": str(exc),
                        "outcome": "refused",
                        "remote_accepted": False,
                        "at": now.isoformat(),
                    }
                    changed = True
                    counts["error"] += 1
                    write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": str(exc), "outcome": "refused"})
                continue
            client = clients.get("linkedin" if stream == "linkedin" else "buffer")
            if client is None:
                counts["error"] += 1
                if not logged(store, post["id"], channel, "error", fp):
                    write_log(
                        store,
                        post["id"],
                        channel,
                        "error",
                        {
                            "fingerprint": fp,
                            "why": f"publishing is on, but no {channel} sender is set up (its "
                            "secret or its settings are missing); nothing was sent",
                        },
                    )
                continue

            if stream == "linkedin":
                if due > now:
                    counts["not_yet"] += 1  # LinkedIn has no queue: it goes at its slot, never before
                    continue
                if li_today is None:
                    li_today = linkedin_sent_on(store, myt_date(now))
                if li_today >= li_cap:
                    counts["waiting"] += 1
                    if not logged(store, post["id"], channel, "wait", fp):
                        write_log(
                            store,
                            post["id"],
                            channel,
                            "wait",
                            {
                                "fingerprint": fp,
                                "why": (f"LinkedIn's daily cap ({li_cap}) is used; a post whose day has passed is not sent"),
                            },
                        )
                    continue
                if logged(store, post["id"], channel, "sending", fp) and not logged(store, post["id"], channel, "sent", fp):
                    # an earlier run began this send and never recorded the answer: it may be on LinkedIn already
                    msg = (
                        "An earlier run started sending this and never heard back. Check LinkedIn; if it is not "
                        "there, edit the post and approve it again to send it."
                    )
                    errors[channel] = {"fingerprint": fp, "message": msg, "unconfirmed": True, "at": now.isoformat()}
                    changed = True
                    counts["error"] += 1
                    write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": msg})
                    continue
                write_log(
                    store,
                    post["id"],
                    channel,
                    "sending",
                    {"fingerprint": fp, "pictures": len(pictures), **({"video": video["url"]} if video else {})},
                )
                try:
                    # No automatic retry here: a timeout or 5xx from Composio does not prove the post never landed,
                    # and LinkedIn/Composio give us no safe way to check or an idempotency key. Resending blindly
                    # risked a duplicate LinkedIn post. The "sending" log line just above, with no matching "sent"
                    # line, is exactly what the guard at the top of this branch checks on the NEXT run: it stops and
                    # asks a human to check LinkedIn rather than silently sending again.
                    res = client.post_video(text, video["url"]) if video else client.post(text, pictures)
                except senders.SendError as exc:
                    errors[channel] = {"fingerprint": fp, "message": exc.message, "kind": exc.kind, "at": now.isoformat()}
                    changed = True
                    counts["error"] += 1
                    write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": exc.message})
                    continue
                published[channel] = {
                    "id": res.urn,
                    "url": res.url,
                    "status": "sent",
                    "at": now.isoformat(),
                    "route": "composio+video" if video else "composio+image" if pictures else "composio",
                }
                errors.pop(channel, None)
                changed = True
                li_today += 1
                counts["sent"] += 1
                # persist 'published' BEFORE the log line: a crash/failure between the two must never leave a
                # "sent" log with no matching published record, or the next run sends this channel again
                store.table(db.POSTS).update({"published": published}).eq("id", post["id"]).execute()
                write_log(store, post["id"], channel, "sent", {"fingerprint": fp, "urn": res.urn})
                continue

            channel_id = bufcfg.get(channel)
            if not channel_id:
                counts["error"] += 1
                if not logged(store, post["id"], channel, "error", fp):
                    write_log(
                        store,
                        post["id"],
                        channel,
                        "error",
                        {"fingerprint": fp, "why": f"no Buffer channel id for {channel} in settings"},
                    )
                continue
            if channel == "instagram" and not pictures and not video:
                errors[channel] = {
                    "fingerprint": fp,
                    "message": "Instagram needs a picture and this post has none",
                    "at": now.isoformat(),
                }
                changed = True
                counts["error"] += 1
                write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": errors[channel]["message"]})
                continue
            try:
                found = view.find(channel_id, text, due)
                if found:
                    published[channel] = _record(found, "customScheduled", "buffer-adopted", now)
                    counts["adopted"] += 1
                    store.table(db.POSTS).update({"published": published}).eq("id", post["id"]).execute()
                    write_log(store, post["id"], channel, "adopted", {"fingerprint": fp, "buffer_id": found.get("id")})
                else:
                    rec = _send_buffer(client, view, channel_id, channel, text, pictures, alt, due, now, video)
                    published[channel] = rec
                    action = "sent" if rec.get("status") == "sent" else "scheduled"
                    counts[action] += 1
                    # persist 'published' BEFORE the log line (same reasoning as the LinkedIn branch above): if the
                    # save below this loop never runs, the next run must still see this channel as already handled
                    store.table(db.POSTS).update({"published": published}).eq("id", post["id"]).execute()
                    write_log(
                        store,
                        post["id"],
                        channel,
                        action,
                        {"fingerprint": fp, "buffer_id": rec.get("id"), "due_at": due.isoformat()},
                    )
                errors.pop(channel, None)
                changed = True
            except senders.SendError as exc:
                if exc.kind == "full":
                    counts["waiting"] += 1  # Buffer's plan cap: a wait, never an error
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
    if enabled and clients.get("postiz"):
        tally_postiz(store, clients["postiz"], now, counts, settings)
    return counts


def tally_postiz(store: Any, client: Any, now: datetime, counts: dict[str, int], settings: dict[str, Any]) -> None:
    counts.setdefault("confirmed", 0)
    rows = store.table(db.POSTS).select("*").in_("status", ["approved", "scheduled"]).execute().data or []
    for post in rows:
        if publishing.provider_for(post, settings) != "postiz":
            continue
        published = dict(post.get("published") or {})
        errors = dict(post.get("errors") or {})
        changed = False
        for channel, rec in list(published.items()):
            if not isinstance(rec, dict) or rec.get("route") != "postiz" or rec.get("status") in ("sent", "error"):
                continue
            due = _parse(rec.get("dueAt"))
            if due and due > now - timedelta(minutes=5):
                continue
            try:
                result = client.readback(
                    postiz.Result(str(rec["id"]), rec.get("status", "scheduled"), rec["dueAt"]), rec["dueAt"]
                )
            except postiz.PostizError:
                continue
            published[channel] = {
                **rec,
                "status": result.status,
                "confirmed_at": now.isoformat(),
                **({"url": result.url} if result.url else {}),
            }
            if result.status == "error":
                errors[channel] = {"message": "Postiz readback reported a publishing error", "at": now.isoformat()}
            else:
                errors.pop(channel, None)
            write_log(store, post["id"], channel, "confirmed", {"postiz_id": rec["id"], "status": result.status})
            counts["confirmed"] += 1
            changed = True
        if changed:
            patch: dict[str, Any] = {"published": published, "errors": errors}
            channels = post_channels(settings, post)
            if all((published.get(c) or {}).get("status") == "sent" for c in channels):
                patch["status"] = "posted"
            store.table(db.POSTS).update(patch).eq("id", post["id"]).execute()


def tally(store: Any, client: Any, now: datetime, counts: dict[str, int], settings: dict[str, Any]) -> None:
    """Read back every Buffer post whose moment has passed and write down what the network actually did (Studio's
    reconcileBuffer): `sent` or `error`, and a post whose every channel is sent becomes `posted`."""
    counts.setdefault("confirmed", 0)
    rows = (
        store.table(db.POSTS)
        .select("id,status,stream,channels,published,errors")
        .in_("status", ["approved", "scheduled"])
        .execute()
        .data
        or []
    )
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
            published[ch] = {
                **rec,
                "status": status,
                **({"url": got["externalLink"]} if got.get("externalLink") else {}),
                "confirmed_at": now.isoformat(),
            }
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
        channels = post_channels(settings, post)
        if all((published.get(c) or {}).get("status") == "sent" for c in channels):
            patch["status"] = "posted"
        store.table(db.POSTS).update(patch).eq("id", post["id"]).execute()


def main() -> int:
    store = db.client(SupabaseSettings.load())
    counts = run(store)
    log.info("publisher: %s", counts)
    from . import archive, sheet

    archived = archive.run(store)  # before the sheet, so today's archive rows go with it
    archived += "; " + archive.purge_rejected(store)  # rejected 72 hours ago (021)
    log.info(archived)
    log.info(sheet.sync_log(store))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write("## Semasa publisher\n\n" + ", ".join(f"{k} {v}" for k, v in counts.items()) + f"\n\n{archived}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
