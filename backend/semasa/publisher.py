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
    rows = db.read_with_retry(store.table(db.SETTINGS).select("key,value")).data or []
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


def video_of(m: dict[str, Any]) -> dict[str, Any] | None:
    """A video media row as the senders take it: its address, its poster and whether it stands upright (a Reel)."""
    if m.get("type") != "video" or not m.get("generated_media_url"):
        return None
    meta = m.get("meta") or {}
    return {"url": m["generated_media_url"], "thumbnail": meta.get("poster_url") or "",
            "vertical": int(meta.get("height") or 0) > int(meta.get("width") or 0) > 0}


def pictures_of(m: dict[str, Any]) -> list[str]:
    """The addresses a media row sends: every slide of a carousel, in order, else its one file. A video is not a picture."""
    if m.get("type") == "video":
        return []
    if m.get("mode") == "slides":
        return [u for u in ((m.get("meta") or {}).get("slide_urls") or []) if u]
    return [m["generated_media_url"]] if m.get("generated_media_url") else []


SHARE_NOW_WITHIN = timedelta(minutes=2)
ADOPT_WITHIN = timedelta(minutes=2)    # a Buffer post is this post's channel only if it is due within this of the slot
TRANSIENT_GIVE_UP = 5                  # runs in a row a transient failure is tried again before it is final
PUBLISH_RUNS_MYT = ("06:20", "11:20", "19:20")   # publish.yml cron and supabase/009 semasa_publish (22:20 03:20 11:20 UTC)
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
        return when_utc(str(ts))            # Studio's own display stamps ("2026-09-28 06:43 MYT" and friends)
    return dt if dt.tzinfo else None


def linkedin_sent_on(store: Any, day) -> int:
    """LinkedIn posts sent on this MYT day (the daily cap). A post can only have been sent on `day` if it was written to
    since that day began (sending writes `published`, which moves updated_at), so only that window is read: reading every
    LinkedIn post ever stops counting once PostgREST's 1000-row cap is reached, and the cap would then let posts burst."""
    since = datetime(day.year, day.month, day.day, tzinfo=UTC) - MYT - timedelta(hours=1)   # an hour of slack for clocks
    rows = (db.read_with_retry(store.table(db.POSTS).select("stream,published,updated_at").eq("stream", "linkedin")
                               .gte("updated_at", since.isoformat())).data or [])
    n = 0
    for r in rows:
        at = _parse(((r.get("published") or {}).get("linkedin") or {}).get("at"))
        if at and myt_date(at) == day:
            n += 1
    return n


def li_send_day(due: datetime):
    """The MYT day a LinkedIn post may still be sent on. LinkedIn has no queue: a post goes at the first publish run at or
    after its slot (PUBLISH_RUNS_MYT). For a slot later than the day's last run (after 19:20 MYT) that first run is 06:20
    the NEXT day, so such a post is sent on the next day instead of being called overdue. On any later day it is overdue
    and is never sent by itself. web/src/lib/slots.js liSendDay says the same for the page."""
    local = due + MYT
    hh, mm = (int(x) for x in max(PUBLISH_RUNS_MYT).split(":"))
    return local.date() + timedelta(days=1) if (local.hour, local.minute) > (hh, mm) else local.date()


class _BufferView:
    """What Buffer already holds, read once per channel per run: the no-double-post check."""

    def __init__(self, client: Any, now: datetime, claimed: dict[str, str] | None = None):
        self.client, self.now, self.cache = client, now, {}
        self.claimed: dict[str, str] = dict(claimed or {})       # Buffer post id -> the Semasa post that records it

    def find(self, channel_id: str, text: str, due: datetime, post_id: Any = None) -> dict[str, Any] | None:
        """The Buffer post that IS this channel of this post: the same words in full (whitespace squeezed), due at the same
        moment (within ADOPT_WITHIN; a share-now made this run is due when it was made, so up to now), and not already
        recorded by another post. A different post that only opens with the same hundred letters is never taken for it."""
        if channel_id not in self.cache:
            self.cache[channel_id] = self.client.posts(
                [channel_id], (self.now - timedelta(days=3)).isoformat(), (self.now + LOOKAHEAD + timedelta(days=2)).isoformat())
        key = senders.text_key(text)
        lo = due - ADOPT_WITHIN
        hi = (max(due, self.now) if due <= self.now + SHARE_NOW_WITHIN else due) + ADOPT_WITHIN
        for p in self.cache[channel_id]:
            owner = self.claimed.get(str(p.get("id") or ""))
            if owner is not None and owner != str(post_id):
                continue
            at = _parse(p.get("dueAt") or p.get("sentAt"))
            if (p.get("status") not in ("error", "draft") and senders.text_key(p.get("text", "")) == key
                    and at and lo <= at <= hi):
                return p
        return None

    def add(self, channel_id: str, post: dict[str, Any], post_id: Any = None) -> None:
        self.cache.setdefault(channel_id, []).append(post)
        self.claim(post, post_id)

    def claim(self, bp: dict[str, Any], post_id: Any) -> None:
        if bp.get("id") and post_id is not None:
            self.claimed[str(bp["id"])] = str(post_id)


def _claimed(live: list[dict[str, Any]]) -> dict[str, str]:
    """Every Buffer id some post already records in `published`: never adopted by a different post."""
    out: dict[str, str] = {}
    for o in live:
        for rec in (o.get("published") or {}).values():
            if isinstance(rec, dict) and rec.get("id"):
                out[str(rec["id"])] = str(o.get("id"))
    return out


def _record(bp: dict[str, Any], mode: str, route: str, now: datetime) -> dict[str, Any]:
    return {"id": bp.get("id"), "status": bp.get("status"), "dueAt": bp.get("dueAt"), "mode": mode,
            "route": route, "at": now.isoformat(), **({"url": bp["externalLink"]} if bp.get("externalLink") else {}),
            **({"unconfirmed": True} if bp.get("unconfirmed") else {})}


def _send_buffer(client: Any, view: _BufferView, channel_id: str, channel: str, text: str, pictures: list[str],
                 alt: str, due: datetime, now: datetime, video: dict[str, Any] | None = None,
                 post_id: Any = None) -> dict[str, Any]:
    """One channel of one post into Buffer. Returns the record for `published`; raises SendError."""
    share_now = due <= now + SHARE_NOW_WITHIN
    due_iso = None if share_now else due.isoformat()
    mode = "shareNow" if share_now else "customScheduled"
    for attempt in (1, 2):
        try:
            bp = (client.create_video(channel_id, channel, text, video, due_iso) if video
                  else client.create(channel_id, channel, text, pictures, alt, due_iso))
        except senders.SendError as exc:
            if exc.kind != "transient" or attempt == 2:
                raise
            view.cache.pop(channel_id, None)        # the pre-attempt cache cannot show a post made just now:
            found = view.find(channel_id, text, due, post_id)  # force a fresh read before deciding to retry
            if found is not None:                   # the first try did land after all
                view.claim(found, post_id)
                return _record(found, mode, "buffer-adopted", now)
            continue
        if share_now:
            try:
                fin = client.confirm(bp["id"])
            except Exception as exc:  # noqa: BLE001 - Buffer HAS the post; only reading it back failed
                # Recording this as an error with no `published` record would make a later run create it a second time.
                # Record what Buffer gave us, marked unconfirmed: the tally reads it back and settles it (sent or error).
                log.warning("publisher: %s %s was created but could not be read back: %s", channel, bp.get("id"), exc)
                fin = {"unconfirmed": True}
            err = (fin.get("error") or {}).get("message") or ""
            if fin.get("status") == "error":
                kind = senders.classify(err)
                if kind == "transient" and attempt == 1:
                    continue                                    # Studio's TRANSIENT_SEND: one identical retry
                raise senders.SendError(kind, f"{channel}: {err or 'Buffer reported an error'}")
            bp = {**bp, **fin}
        view.add(channel_id, bp, post_id)
        return _record(bp, mode, "buffer", now)
    raise senders.SendError("refused", "unreachable")


def moved_since_handed_over(published: dict[str, Any], due: datetime) -> list[str]:
    """Channels Buffer holds for a different moment than the post's slot now: the post was moved after they were handed
    over (the page and supabase/072 refuse that from a browser; the worker and the importer write with the service key).
    Sending the rest at the new slot would split one post across two slots and leave the old one taken in Buffer."""
    out = []
    for ch, rec in sorted(published.items()):
        if not isinstance(rec, dict) or rec.get("mode") == "shareNow" or not str(rec.get("route") or "").startswith("buffer"):
            continue
        at = _parse(rec.get("dueAt"))
        if at and abs(at - due) > ADOPT_WITHIN:
            out.append(f"{ch} {(at + MYT):%Y-%m-%d %H:%M}")
    return out


def _final(rec: Any) -> bool:
    """Is this stored channel error one that stops the channel until the post is edited? A refusal is; a transient failure
    is not, until it has been tried in TRANSIENT_GIVE_UP runs. A record with no kind (unconfirmed LinkedIn, Instagram
    with no picture) always is."""
    return isinstance(rec, dict) and (rec.get("kind") != "transient" or bool(rec.get("gave_up")))


def _fail(ctx: _Run, post_id: Any, errors: dict[str, Any], channel: str, fp: str, exc: senders.SendError,
          **detail: Any) -> None:
    """Write down one failed channel. A refusal is final for these words (an edit sends again). A transient failure (an
    outage, a 429, a timeout, a failed listing) is tried again next run, counted in `attempts`; after TRANSIENT_GIVE_UP
    runs in a row it is recorded as final, so Wan sees it and nothing hammers a dead route for ever."""
    prior = errors.get(channel)
    tries = 1
    if isinstance(prior, dict) and prior.get("fingerprint") == fp and prior.get("kind") == "transient":
        tries = int(prior.get("attempts") or 1) + 1
    transient = exc.kind == "transient"
    gave_up = transient and tries >= TRANSIENT_GIVE_UP
    msg = exc.message + (f" (failed in {tries} runs in a row: no more tries until the post is edited and approved again)"
                         if gave_up else "")
    errors[channel] = {"fingerprint": fp, "message": msg, "kind": exc.kind, "attempts": tries, "at": ctx.now.isoformat(),
                       **({"retry": True} if transient and not gave_up else {}), **({"gave_up": True} if gave_up else {})}
    ctx.counts["retry" if transient and not gave_up else "error"] += 1
    write_log(ctx.store, post_id, channel, "error",
              {"fingerprint": fp, "why": msg, "kind": exc.kind, "attempts": tries, **detail})


def _unanswered(store: Any, post_id: Any, channel: str, fp: str) -> bool:
    """Did an earlier run start sending these words to LinkedIn and never hear back? Every attempt writes one "sending"
    line, and every attempt that is answered closes it with "sent", or with an "error" marked before_post (a transient
    failure before the post call, when nothing can be on LinkedIn). More openings than closings: one is unanswered."""
    rows = (store.table(db.PUBLISH_LOG).select("action,detail").eq("post_id", post_id).eq("channel", channel)
            .in_("action", ["sending", "sent", "error"]).order("at", desc=True).limit(200).execute().data or [])
    mine = [r for r in rows if (r.get("detail") or {}).get("fingerprint") == fp]
    opened = sum(1 for r in mine if r.get("action") == "sending")
    closed = sum(1 for r in mine if r.get("action") == "sent"
                 or (r.get("action") == "error" and (r.get("detail") or {}).get("before_post")))
    return opened > closed


class _Run:
    """One publisher run: what every post shares (settings, clients, counts, Buffer's view, LinkedIn's count today)."""

    def __init__(self, store: Any, now: datetime, settings: dict[str, Any], enabled: bool, clients: dict[str, Any]):
        self.store, self.now, self.settings, self.enabled, self.clients = store, now, settings, enabled, clients
        brand = settings.get("brand") or {}
        self.brand, self.reg = brand, brand.get("regulab") or {}
        self.bufcfg = (settings.get("channels") or {}).get("buffer") or {}
        self.counts = {"considered": 0, "dry_run": 0, "blocked": 0, "error": 0, "overdue": 0, "scheduled": 0, "sent": 0,
                       "adopted": 0, "waiting": 0, "not_yet": 0, "retry": 0, "changed": 0, "failed": 0}
        self.li_cap = max(1, len((brand.get("linkedin") or {}).get("slots") or ["06:00"]))
        self.li_today: int | None = None
        self.live: list[dict[str, Any]] = []
        self.view: _BufferView | None = None


class _Pin:
    """The version of one post this run decided to send: its updated_at as read. Before each send the row is read again,
    and a post someone changed meanwhile (moved, edited, sent back to draft, rejected) is left alone; the run's own writes
    move updated_at too, so the pin follows them."""

    def __init__(self, store: Any, post: dict[str, Any]):
        self.store, self.id, self.updated_at = store, post["id"], post.get("updated_at")

    def still_ours(self) -> bool:
        rows = db.read_with_retry(self.store.table(db.POSTS).select("id,status,updated_at").eq("id", self.id)).data or []
        return bool(rows) and rows[0].get("status") == "approved" and rows[0].get("updated_at") == self.updated_at

    def follow(self, res: Any) -> None:
        rows = getattr(res, "data", None) or []
        if rows and rows[0].get("updated_at"):
            self.updated_at = rows[0]["updated_at"]

    def save_published(self, published: dict[str, Any]) -> None:
        """What Buffer or LinkedIn now holds is written UNCONDITIONALLY: it is the truth whatever happened to the post
        meanwhile, and losing it would send that channel a second time."""
        self.follow(self.store.table(db.POSTS).update({"published": published}).eq("id", self.id).execute())

    def save_final(self, patch: dict[str, Any], published: dict[str, Any]) -> bool:
        """The end-of-post write (errors, status), pinned to the post still being approved and unchanged since it was
        read. When the pin misses, the per-channel records are written anyway (save_published) and nothing else."""
        q = self.store.table(db.POSTS).update(patch).eq("id", self.id).eq("status", "approved")
        if self.updated_at:
            q = q.eq("updated_at", self.updated_at)
        res = q.execute()
        if getattr(res, "data", None):
            self.follow(res)
            return True
        if "published" in patch:
            self.save_published(published)
        return False


def _publish_post(ctx: _Run, post: dict[str, Any]) -> None:
    store, now, counts, settings, clients = ctx.store, ctx.now, ctx.counts, ctx.settings, ctx.clients
    due = due_utc(post["date"], post["slot"])
    if due > now + LOOKAHEAD:
        return
    counts["considered"] += 1
    stream = post.get("stream") or "regulab"
    media = media_for(store, list(post.get("media_ids") or []))
    scan_post = {**post, "media": [scan_entry(m) for m in media if m.get("status") == "done"]}
    flags = compliance.scan(scan_post, brand=ctx.reg, schedule=ctx.reg.get("schedule"),
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
    hard += guard.blockers(post, ctx.live)
    lang = compliance.lang_of(post)
    published = dict(post.get("published") or {})
    elsewhere = moved_since_handed_over(published, due)
    if elsewhere:
        hard.append(f"moved after it was handed to Buffer, which still holds {', '.join(elsewhere)} MYT: move it back "
                    "to that slot, or delete those posts in Buffer and have their records cleared")
    errors = {k: v for k, v in (post.get("errors") or {}).items() if k != "scan"}
    changed = False
    pin = _Pin(store, post)
    pictures = [u for m in media for u in pictures_of(m)]
    video = next((v for v in (video_of(m) for m in media) if v), None)      # a post's video stands alone (no pictures)
    alt = " ".join(str((m.get("meta") or {}).get("alt") or "") for m in media).strip()
    channels = post_channels(settings, post)

    def moved_on(channel: str) -> bool:
        """Re-read the post just before a send: one changed since this run read it is not sent (race with the page)."""
        if pin.still_ours():
            return False
        counts["changed"] += 1
        log.info("publisher: post %s changed while this run was on it; %s not sent, the next run reads it again",
                 post["id"], channel)
        return True

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
        late = (myt_date(now) > li_send_day(due)) if stream == "linkedin" else (due < now - LATE_GRACE)
        if late:
            counts["overdue"] += 1
            if not logged(store, post["id"], channel, "blocked", fp):
                write_log(store, post["id"], channel, "blocked",
                          {"fingerprint": fp, "why": [f"overdue: its slot was {post['date']} {post['slot']} MYT; "
                                                      "move it to a new slot"]})
            continue
        if not ctx.enabled:
            counts["dry_run"] += 1
            if not logged(store, post["id"], channel, "dry_run", fp):
                write_log(store, post["id"], channel, "dry_run",
                          {"fingerprint": fp, "would_send": payload, "chars": len(payload["text"])})
            continue
        prior = errors.get(channel)
        if _final(prior) and prior.get("fingerprint") == fp:
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
            if ctx.li_today is None:
                ctx.li_today = linkedin_sent_on(store, myt_date(now))
            if ctx.li_today >= ctx.li_cap:
                counts["waiting"] += 1
                if not logged(store, post["id"], channel, "wait", fp):
                    write_log(store, post["id"], channel, "wait", {"fingerprint": fp, "why": (
                        f"LinkedIn's daily cap ({ctx.li_cap}) is used; a post whose day has passed is not sent")})
                continue
            if _unanswered(store, post["id"], channel, fp):
                # an earlier run began this send and never recorded the answer: it may be on LinkedIn already
                msg = ("An earlier run started sending this and never heard back. Check LinkedIn; if it is not "
                       "there, edit the post and approve it again to send it.")
                errors[channel] = {"fingerprint": fp, "message": msg, "unconfirmed": True, "at": now.isoformat()}
                changed = True
                counts["error"] += 1
                write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": msg})
                continue
            if moved_on(channel):
                return
            write_log(store, post["id"], channel, "sending",
                      {"fingerprint": fp, "pictures": len(pictures), **({"video": video["url"]} if video else {})})
            try:
                # No retry here. By the senders' contract (senders.py LinkedIn/LinkedInMCP .post/.post_video) anything
                # that goes wrong once the post call has gone out is a refusal, because a timeout or 5xx does not prove
                # the post never landed and there is no idempotency key: it is recorded and never sent again by itself.
                # A TRANSIENT failure can only come from before the post call (account lookup, picture fetch/upload,
                # video hand-over), when nothing can be on LinkedIn: it closes its "sending" line (before_post) and the
                # next run tries again.
                res = client.post_video(text, video["url"]) if video else client.post(text, pictures)
            except senders.SendError as exc:
                _fail(ctx, post["id"], errors, channel, fp, exc, before_post=exc.kind == "transient")
                changed = True
                continue
            published[channel] = {"id": res.urn, "url": res.url, "status": "sent", "at": now.isoformat(),
                                  "route": "composio+video" if video else "composio+image" if pictures else "composio"}
            errors.pop(channel, None)
            changed = True
            ctx.li_today += 1
            counts["sent"] += 1
            # persist 'published' BEFORE the log line: a crash/failure between the two must never leave a
            # "sent" log with no matching published record, or the next run sends this channel again
            pin.save_published(published)
            write_log(store, post["id"], channel, "sent", {"fingerprint": fp, "urn": res.urn})
            continue

        channel_id = ctx.bufcfg.get(channel)
        if not channel_id:
            counts["error"] += 1
            if not logged(store, post["id"], channel, "error", fp):
                write_log(store, post["id"], channel, "error",
                          {"fingerprint": fp, "why": f"no Buffer channel id for {channel} in settings"})
            continue
        if channel == "instagram" and not pictures and not video:
            errors[channel] = {"fingerprint": fp, "message": "Instagram needs a picture and this post has none",
                               "at": now.isoformat()}
            changed = True
            counts["error"] += 1
            write_log(store, post["id"], channel, "error", {"fingerprint": fp, "why": errors[channel]["message"]})
            continue
        if moved_on(channel):
            return
        view = ctx.view
        try:
            found = view.find(channel_id, text, due, post["id"])
            if found:
                view.claim(found, post["id"])
                published[channel] = _record(found, "customScheduled", "buffer-adopted", now)
                counts["adopted"] += 1
                pin.save_published(published)
                write_log(store, post["id"], channel, "adopted", {"fingerprint": fp, "buffer_id": found.get("id")})
            else:
                rec = _send_buffer(client, view, channel_id, channel, text, pictures, alt, due, now, video, post["id"])
                published[channel] = rec
                action = "sent" if rec.get("status") == "sent" else "scheduled"
                counts[action] += 1
                # persist 'published' BEFORE the log line (same reasoning as the LinkedIn branch above): if the
                # save below this loop never runs, the next run must still see this channel as already handled
                pin.save_published(published)
                write_log(store, post["id"], channel, action,
                          {"fingerprint": fp, "buffer_id": rec.get("id"), "due_at": due.isoformat(),
                           **({"unconfirmed": True} if rec.get("unconfirmed") else {})})
            errors.pop(channel, None)
            changed = True
        except senders.SendError as exc:
            if exc.kind == "full":
                counts["waiting"] += 1               # Buffer's plan cap: a wait, never an error
                if not logged(store, post["id"], channel, "wait", fp):
                    write_log(store, post["id"], channel, "wait", {"fingerprint": fp, "why": exc.message})
                continue
            _fail(ctx, post["id"], errors, channel, fp, exc)
            changed = True

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
    # judged on every run, not only when this run sent something: a post whose last channel went in a run whose final
    # write missed its pin is promoted by the next one
    if channels and all(published.get(c) for c in channels):
        patch["status"] = "posted" if all(published[c].get("status") == "sent" for c in channels) else "scheduled"
    if patch:
        pin.save_final(patch, published)


def run(store: Any, now: datetime | None = None, clients: dict[str, Any] | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    enabled = publishing_on(settings, now)
    if clients is None:
        clients = make_clients(settings) if enabled else {}
    r = _Run(store, now, settings, enabled, clients)
    posts = (db.read_with_retry(store.table(db.POSTS).select("*").eq("status", "approved").not_.is_("date", "null")
             .not_.is_("slot", "null").order("date").order("slot")).data or [])
    r.live = guard.load_live(store, db.POSTS, myt_date(now)) if posts else []
    r.view = _BufferView(clients["buffer"], now, _claimed(r.live)) if clients.get("buffer") else None
    for post in posts:
        try:
            _publish_post(r, post)
        except Exception:  # noqa: BLE001 - one bad post must never stop the others, the tally or the archive
            r.counts["failed"] += 1
            log.exception("publisher: post %s failed; the run goes on with the next one", post.get("id"))

    if enabled and clients.get("buffer"):
        try:
            tally(store, clients["buffer"], now, r.counts, settings)
        except Exception:  # noqa: BLE001
            r.counts["failed"] += 1
            log.exception("publisher: the Buffer tally failed")
    return r.counts


def tally(store: Any, client: Any, now: datetime, counts: dict[str, int], settings: dict[str, Any]) -> None:
    """Read back every Buffer post whose moment has passed and write down what the network actually did (Studio's
    reconcileBuffer): `sent` or `error`, and a post whose every channel is sent becomes `posted`."""
    counts.setdefault("confirmed", 0)
    rows = (store.table(db.POSTS).select("id,status,stream,channels,published,errors").in_("status", ["approved", "scheduled"])
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
        channels = post_channels(settings, post)
        # `all([])` is True: a post whose every channel was since switched off in settings must not read as posted
        if channels and all((published.get(c) or {}).get("status") == "sent" for c in channels):
            patch["status"] = "posted"
        store.table(db.POSTS).update(patch).eq("id", post["id"]).execute()


def main() -> int:
    store = db.client(SupabaseSettings.load())
    try:
        counts = run(store)
    except Exception:  # noqa: BLE001 - settings unreadable, the posts read failed: the archive below still runs
        log.exception("publisher: the run failed before it could finish")
        counts = {"failed": 1}
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
    # a post that crashed was skipped so the others, the tally and the archive could run; the job still goes red so it is seen
    return 1 if counts.get("failed") else 0


if __name__ == "__main__":
    sys.exit(main())
