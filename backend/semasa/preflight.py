"""A dry run of every queued post, on every platform, before a platform refuses it (Wan, 11 Nov 2026).

Threads refused the first Zernio chain ("The parameter text is required": the tag line under the words had been sent as a post
of its own) and the refusal only showed at the slot. This builds the EXACT request the sender would make for each
approved or scheduled post and each of its channels, with nothing sent (`senders.Zernio` over a recording session), and
checks it against what each platform takes. `--live` also reads Zernio back for every post already handed over and reports
any that Zernio itself shows as failed, moved or different from what Semasa holds.

    python -m semasa.preflight             # offline: the requests, checked
    python -m semasa.preflight --live      # + what Zernio holds for the posts already handed over

It writes nothing to a post. Exit code 1 when any post has a blocker.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from . import compliance, db, publisher, senders
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.preflight")

# What each platform takes. `text` is characters of the caption (per post for a Threads chain). Where a number is not one
# Zernio documents it is marked "soft": a warning, never a blocker.
LIMITS: dict[str, dict[str, Any]] = {
    # from docs.zernio.com (read 11 Nov 2026): Threads 500 and 10 images; Instagram 2,200 and 20 images, no text-only; Facebook
    # 10 images; LinkedIn 3,000 and 20 images, one media type; TikTok 2,200, video, no text-only. `day` is the account's posts
    # per rolling 24 hours (Threads 250, Instagram 100, TikTok 15 videos on the Business app lane).
    "threads": {"text": 500, "items": senders.THREAD_LEVELS, "images": 10, "videos": 1, "day": 250},
    "instagram": {"text": 2200, "images": 20, "videos": 1, "needs_media": True, "day": 100},
    "facebook": {"text": 63206, "images": 10, "videos": 1},
    "linkedin": {"text": 3000, "images": 20, "videos": 1},
    "tiktok": {"text": 2200, "videos": 1, "needs_media": True, "video_only": True, "day": 15},
}
SOFT_TAGS = {"instagram": 30}           # Instagram's own cap, which Zernio does not document: a warning only
_TAGS_ONLY = re.compile(r"^(?:\s*#[^\s#]+)+\s*$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f​-‍﻿]")


class _Recorder:
    """A session that records the request and answers like Zernio, so no network is touched."""

    def __init__(self) -> None:
        self.body: dict[str, Any] = {}

    def request(self, method: str, url: str, json: Any = None, **kw: Any) -> Any:
        self.body = json or {}
        return SimpleNamespace(status_code=201, json=lambda: {"post": {"_id": "dry", "status": "scheduled", "platforms": []}})


def request_for(channel: str, text: str, pictures: list[str], video: dict[str, Any] | None, due_iso: str) -> dict[str, Any]:
    """The exact body the Zernio sender would POST for this channel."""
    rec = _Recorder()
    z = senders.Zernio("dry", session=rec)
    if video:
        z.create_video("acct", channel, text, video, due_iso)
    else:
        z.create("acct", channel, text, pictures, "", due_iso)
    return rec.body


def _items(body: dict[str, Any]) -> list[dict[str, Any]]:
    plat = (body.get("platforms") or [{}])[0]
    chain = (plat.get("platformSpecificData") or {}).get("threadItems")
    if chain:
        return [{"content": str(i.get("content") or ""), "media": i.get("mediaItems") or []} for i in chain]
    return [{"content": str(body.get("content") or ""), "media": body.get("mediaItems") or []}]


def check_request(channel: str, body: dict[str, Any]) -> list[tuple[str, str]]:
    """[(level, message)] for one request: level is 'block' (the platform will refuse it) or 'warn'."""
    lim = LIMITS.get(channel, {})
    out: list[tuple[str, str]] = []
    items = _items(body)
    media = [m for i in items for m in i["media"]]
    images = [m for m in media if m.get("type") == "image"]
    videos = [m for m in media if m.get("type") == "video"]
    if channel == "threads":
        if len(items) > lim["items"]:
            out.append(("block", f"{len(items)} posts in the chain (most {lim['items']})"))
        for n, it in enumerate(items, 1):
            text = it["content"].strip()
            if not text and not it["media"]:
                out.append(("block", f"post {n} of the chain has no text and no picture"))
            elif text and _TAGS_ONLY.match(text):
                out.append(("block", f"post {n} of the chain is hashtags alone (Threads: 'The parameter text is required')"))
            if len(it["content"]) > lim["text"]:
                out.append(("block", f"post {n} of the chain is {len(it['content'])} characters (most {lim['text']})"))
    else:
        text = items[0]["content"]
        if len(text) > lim.get("text", 10**9):
            out.append(("block", f"caption is {len(text)} characters (most {lim['text']})"))
        if not text.strip() and not media:
            out.append(("block", "no caption and no picture"))
        if SOFT_TAGS.get(channel) and len(re.findall(r"#\w+", text)) > SOFT_TAGS[channel]:
            out.append(("warn", f"more than {SOFT_TAGS[channel]} hashtags"))
    for n, it in enumerate(items, 1):
        if _CONTROL.search(it["content"]):
            out.append(("warn", f"post {n} holds an invisible or control character"))
    if lim.get("needs_media") and not media:
        out.append(("block", f"{channel} needs a picture or a film"))
    if lim.get("video_only") and (images or not videos):
        out.append(("block", f"{channel} takes a film only"))
    if lim.get("images") and len(images) > lim["images"]:
        out.append(("block", f"{len(images)} pictures (most {lim['images']})"))
    if lim.get("videos") is not None and len(videos) > lim["videos"]:
        out.append(("block", f"{len(videos)} films (most {lim['videos']})"))
    if images and videos:
        out.append(("block", "pictures and a film in one post"))
    if channel == "instagram" and len(images) == 1 and not videos:
        out.append(("warn", "a single picture: Instagram shows it as a plain post, not a carousel"))
    for m in media:
        if not str(m.get("url") or "").startswith("https://"):
            out.append(("block", f"a {m.get('type')} address is not https: {str(m.get('url'))[:60]}"))
    return out


def check_post(post: dict[str, Any], media: list[dict[str, Any]], settings: dict[str, Any],
               sink: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
    """Every finding for one post: [{channel, level, message}]. `sink` collects what the queue-wide checks need."""
    findings: list[dict[str, str]] = []
    due = publisher.due_utc(post["date"], post["slot"])
    pictures = [u for m in media for u in publisher.pictures_of(m)]
    video = next((v for v in (publisher.video_of(m) for m in media) if v), None)
    not_ready = [m["id"] for m in media if m.get("status") != "done" or not m.get("generated_media_url")]
    if not_ready:
        findings.append({"channel": "*", "level": "block", "message": f"{len(not_ready)} picture(s) not generated yet"})
    lang = compliance.lang_of(post)
    for channel in publisher.post_channels(settings, post, has_video=bool(video)):
        text = compliance.text_of(post, channel, lang) or (
            compliance.text_of(post, "instagram", lang) if channel == "tiktok" else "")
        fmt = publisher.format_of(pictures, video)
        if fmt not in publisher.ZERNIO_FORMATS.get(channel, ()) and channel in publisher.ZERNIO_FORMATS:
            takes = " or ".join(publisher.FORMAT_NAMES[f] for f in publisher.ZERNIO_FORMATS[channel])
            findings.append({"channel": channel, "level": "block",
                             "message": f"{channel} takes {takes}; this post is {publisher.FORMAT_NAMES[fmt]}"})
            continue
        try:
            body = request_for(channel, text, pictures, video, due.isoformat())
        except senders.SendError as exc:
            findings.append({"channel": channel, "level": "block", "message": str(exc)[:200]})
            continue
        findings += [{"channel": channel, "level": lv, "message": msg} for lv, msg in check_request(channel, body)]
        if sink is not None:
            sink.append({"label": f"{post['date']} {post['slot']} {str(post['id'])[:8]}", "channel": channel, "due": due,
                         "text": text})
    return findings


def queue_findings(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Across the queue: the same words twice on one channel (Zernio refuses a duplicate within 24 hours, LinkedIn for good),
    and an account's posts in one rolling 24 hours against what the platform allows. rows: [{label, channel, due, text}]."""
    out: list[dict[str, str]] = []
    seen: dict[tuple[str, str], str] = {}
    for r in sorted(rows, key=lambda r: r["due"]):
        key = (r["channel"], senders.text_key(r["text"]))
        if key in seen and r["text"].strip():
            out.append({"label": r["label"], "channel": r["channel"], "level": "block",
                        "message": f"the same words as {seen[key]} on {r['channel']}: Zernio refuses a duplicate"})
        seen.setdefault(key, r["label"])
    for channel, lim in LIMITS.items():
        times = sorted((r["due"], r["label"]) for r in rows if r["channel"] == channel)
        for i, (t, label) in enumerate(times):
            n = sum(1 for u, _ in times[i:] if (u - t).total_seconds() < 86400)
            if lim.get("day") and n > lim["day"]:
                out.append({"label": label, "channel": channel, "level": "warn",
                            "message": f"{n} posts in 24 hours from here (the platform allows {lim['day']})"})
                break
    return out


def read_back(zernio: Any, post: dict[str, Any]) -> list[dict[str, str]]:
    """What Zernio holds for the channels already handed over: a failed post, a moved time, a different caption."""
    out: list[dict[str, str]] = []
    due = publisher.due_utc(post["date"], post["slot"])
    for channel, rec in (post.get("published") or {}).items():
        if not isinstance(rec, dict) or not str(rec.get("route") or "").startswith("zernio") or rec.get("status") == "sent":
            continue
        try:
            got = zernio.get(rec["id"], rec.get("account") or "")
        except Exception as exc:  # noqa: BLE001 - a post Zernio cannot find is a finding
            out.append({"channel": channel, "level": "block", "message": f"Zernio cannot read it back: {str(exc)[:140]}"})
            continue
        if got.get("status") == "error":
            out.append({"channel": channel, "level": "block",
                        "message": f"Zernio shows it FAILED: {((got.get('error') or {}).get('message') or '')[:220]}"})
        z_due = publisher._parse(got.get("dueAt"))
        if z_due and abs((z_due - due).total_seconds()) > 60 and got.get("status") != "sent":
            out.append({"channel": channel, "level": "block",
                        "message": f"Zernio holds it for {z_due.isoformat()} but the slot is {due.isoformat()}"})
    return out


def run(store: Any, zernio: Any = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    settings = publisher.load_settings(store)
    posts = db.fetch_all(lambda: store.table(db.POSTS).select("*").in_("status", ["approved", "scheduled"])
                         .not_.is_("date", "null").order("date"))
    report: dict[str, Any] = {"posts": 0, "blocked": 0, "warned": 0, "lines": []}
    sink: list[dict[str, Any]] = []
    for post in posts:
        if not post.get("slot") or publisher.due_utc(post["date"], post["slot"]) < now:
            continue
        report["posts"] += 1
        media = publisher.media_for(store, list(post.get("media_ids") or []))
        findings = check_post(post, media, settings, sink) + (read_back(zernio, post) if zernio is not None else [])
        label = f"{post['date']} {post['slot']} {post.get('stream', '')[:4]:4} {str(post['id'])[:8]}"
        for f in findings:
            report["lines"].append(f"{'BLOCK' if f['level'] == 'block' else 'warn '} {label} {f['channel']:9} {f['message']}")
        report["blocked"] += any(f["level"] == "block" for f in findings)
        report["warned"] += any(f["level"] == "warn" for f in findings) and not any(f["level"] == "block" for f in findings)
    for f in queue_findings(sink):
        report["lines"].append(f"{'BLOCK' if f['level'] == 'block' else 'warn '} {f['label']} {f['channel']:9} {f['message']}")
        report["blocked" if f["level"] == "block" else "warned"] += 1
    return report


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also read Zernio back for the posts already handed over")
    args = ap.parse_args()
    store = db.client(SupabaseSettings.load())
    zernio = publisher.make_clients(publisher.load_settings(store)).get("zernio") if args.live else None
    rep = run(store, zernio)
    print(f"{rep['posts']} upcoming posts checked: {rep['blocked']} with a blocker, {rep['warned']} with a warning only")
    for line in rep["lines"]:
        print(" ", line)
    return 1 if rep["blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
