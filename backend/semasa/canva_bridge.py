"""The Canva bridge (Wan, 4 Oct 2026: "Rebuild the next carousel post in Canva ... Carousel Studio > Create Design > send
to semasa ... bot will design not me in canva").

Semasa draws a carousel itself, free and in seconds. The second choice is to have the bot build the same carousel in Canva
(a Claude session with the Canva connector, in the "Carousel Studio" folder) and send the finished pages back. This module
is Semasa's half of that, and the only half that can touch the database; Canva is called from the session, never from here.

  queue    what the bot should build next: the next carousel posts that are still drafts or approved (never scheduled or
           posted: Buffer already holds those pictures), with the words of the first one in full.
  import   the pages the bot exported from Canva, as one carousel for that post (or, for a reference design Wan uploaded in
           the Design tab, as a design waiting for his Simpan): fetched from Canva's export address,
           checked (host, size, picture type), drawn to the post's own size, stored in `semasa-generated`, and attached
           to the post as its slide set. A DRAFT takes them at once (like any new render); an APPROVED post does not get
           its pictures changed behind Wan's back: the pages are stored and the report says so (the gate stands).

Entry point: `python -m semasa.canva_bridge` (canva-bridge.yml), with CANVA_ACTION = queue | import.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests
from PIL import Image

from . import db
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.canva_bridge")

MYT = timedelta(hours=8)
OPEN = ("draft", "approved")
SIZES = {"regulab": (1080, 1080), "linkedin": (1080, 1350)}
MAX_PAGES = 10
MAX_BYTES = 15 * 1024 * 1024
# Canva serves an export from its own download host; anything else is refused before a byte is fetched.
HOSTS = ("canva.com",)


class BridgeError(Exception):
    """A refusal Wan can act on: said plainly, never a stack trace."""


def _words(slide: dict[str, Any]) -> dict[str, Any]:
    keep = ("title", "lead", "points", "eyebrow", "note", "chip", "footnote", "template")
    return {k: slide[k] for k in keep if slide.get(k)}


def has_canva(store: Any, post: dict[str, Any]) -> bool:
    ids = list(post.get("media_ids") or [])
    if not ids:
        return False
    rows = store.table(db.MEDIA).select("id,meta").in_("id", ids).execute().data or []
    return any((r.get("meta") or {}).get("look") == "canva" for r in rows)


def next_carousels(store: Any, today: str, limit: int = 3) -> list[dict[str, Any]]:
    """The next carousel posts still open to a new set of pictures, soonest slot first. A carousel is a post with at
    least two slides written; one that already has a Canva set is not offered twice."""
    rows = (store.table(db.POSTS).select("id,status,stream,date,slot,hook,lang,slides,media_ids,citation,domain,angle")
            .in_("status", list(OPEN)).gte("date", today).order("date").limit(200).execute().data or [])
    rows.sort(key=lambda r: (str(r.get("date") or ""), str(r.get("slot") or ""), str(r.get("id"))))
    out = []
    for r in rows:
        slides = [s for s in (r.get("slides") or []) if isinstance(s, dict)]
        if len(slides) < 2 or has_canva(store, r):
            continue
        out.append({**r, "slides": slides})
        if len(out) >= limit:
            break
    return out


def render_queue(posts: list[dict[str, Any]]) -> dict[str, Any]:
    """The first post in full (the bot builds it now); the rest as a line each."""
    def head(p: dict[str, Any]) -> dict[str, Any]:
        stream = p.get("stream") or "regulab"
        return {"id": p["id"], "status": p["status"], "stream": stream, "date": p.get("date"), "slot": p.get("slot"),
                "lang": p.get("lang"), "pages": len(p["slides"]), "size": list(SIZES.get(stream, SIZES["regulab"]))}
    if not posts:
        return {"next": None, "after": []}
    first = posts[0]
    return {"next": {**head(first), "domain": first.get("domain"), "angle": first.get("angle"),
                     "citation": first.get("citation") or "", "slides": [_words(s) for s in first["slides"]]},
            "after": [head(p) for p in posts[1:]]}


def _check_url(url: str) -> None:
    u = urlparse(str(url))
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host == h or host.endswith("." + h) for h in HOSTS):
        raise BridgeError(f"not a Canva export address (https and a canva.com host only): {host or url[:40]}")


def fetch_page(url: str, get: Any = requests.get) -> bytes:
    _check_url(url)
    resp = get(url, timeout=60, stream=True)
    resp.raise_for_status()
    data = b""
    for chunk in resp.iter_content(1 << 16):
        data += chunk
        if len(data) > MAX_BYTES:
            raise BridgeError("a page is over 15 MB; export it as JPG or PNG at the card's size")
    return data


def to_card(data: bytes, size: tuple[int, int] | None) -> bytes:
    """A Canva page as the card's JPEG. The same shape at another scale (a 2x export) is brought to the card's size;
    a different shape is refused rather than stretched or cropped, because that is a design problem, not a file one."""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:  # noqa: BLE001
        raise BridgeError("a page is not a picture Semasa can read (export PNG or JPG)") from exc
    w, h = im.size
    size = size or (w, h)                                        # a reference design of no recorded shape: as exported
    if abs(w / h - size[0] / size[1]) > 0.01:
        raise BridgeError(f"a page is {w}×{h} and this post's card is {size[0]}×{size[1]}: build the Canva design at "
                          f"{size[0]}×{size[1]} px")
    if im.mode in ("RGBA", "LA", "P"):
        flat = Image.new("RGB", im.size, (255, 255, 255))
        flat.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[3])
        im = flat
    im = im.convert("RGB")
    if im.size != size:
        im = im.resize(size, Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90, optimize=True)
    return out.getvalue()


def import_design(store: Any, post_id: str, urls: list[str], design_url: str = "", *, get: Any = requests.get,
                  now: datetime | None = None) -> dict[str, Any]:
    if not urls or len(urls) > MAX_PAGES:
        raise BridgeError(f"send 1 to {MAX_PAGES} page addresses, in page order")
    rows = (store.table(db.POSTS).select("id,status,stream,slides,media_ids,created_by").eq("id", post_id).limit(1)
            .execute().data or [])
    if not rows:
        raise BridgeError("no such post")
    post = rows[0]
    stream = post.get("stream") or "regulab"
    size = SIZES.get(stream, SIZES["regulab"])
    slides = [s for s in (post.get("slides") or []) if isinstance(s, dict)]
    if slides and len(slides) != len(urls):
        raise BridgeError(f"the post has {len(slides)} slides and {len(urls)} pages came: the carousel and the design "
                          "must have the same number of pages")
    cards = [to_card(fetch_page(u, get), size) for u in urls]          # everything checked before anything is written
    when = now or datetime.now(UTC)
    day, stamp = when.strftime("%Y/%m"), when.strftime("%d%H%M%S")
    row = store.table(db.MEDIA).insert({
        "mode": "slides", "type": "image", "status": "done", "prompt": "", "post_id": post_id,
        "created_by": post.get("created_by"), "provider": "canva", "model": "canva-carousel-studio",
        "meta": {"flow": "canva"}}).execute().data[0]
    paths, public, sums = [], [], []
    for i, data in enumerate(cards, 1):
        path = f"{day}/{row['id']}-{stamp}-canva{i:02d}.jpg"
        public.append(db.upload_generated(store, path, data, "image/jpeg"))
        paths.append(path)
        sums.append(hashlib.sha256(data).hexdigest())
    meta = {"flow": "canva", "look": "canva", "slides": slides, "stream": stream, "size": list(size), "count": len(public),
            "slide_urls": public, "slide_paths": paths, "sha256": sums, "content_type": "image/jpeg",
            "bytes": sum(len(c) for c in cards), "design_url": design_url, "finished_at": when.isoformat()}
    db.finish_media(store, row["id"], status="done", generated_media_url=public[0], provider="canva",
                    model="canva-carousel-studio", error=None, meta=meta)
    attached = post.get("status") == "draft"
    if attached:
        db.attach_slides_to_draft(store, post_id, row["id"])
    return {"media_id": row["id"], "pages": len(public), "attached": attached, "status": post.get("status")}


def next_references(store: Any, limit: int = 3) -> list[dict[str, Any]]:
    """Reference designs Wan uploaded in the Design tab and the bot has not yet rebuilt in Canva, newest first: a done
    Design job with a reference picture (style_ref), that is not itself a Canva rebuild and has no Canva twin."""
    rows = (store.table(db.MEDIA).select("id,status,post_id,created_by,meta,created_at").eq("mode", "slides")
            .eq("status", "done").order("created_at", desc=True).limit(100).execute().data or [])
    twins = {(r.get("meta") or {}).get("canva_for") for r in rows}
    out = []
    for r in rows:
        m = r.get("meta") or {}
        ref = m.get("style_ref") if isinstance(m.get("style_ref"), dict) else {}
        if not ref.get("url") or m.get("flow") == "canva" or r["id"] in twins:
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


def render_references(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def one(r: dict[str, Any], full: bool) -> dict[str, Any]:
        m = r["meta"]
        stream = m.get("stream") or "regulab"
        known = isinstance(m.get("size"), list) and len(m["size"]) == 2
        size = m["size"] if known else list(SIZES.get(stream, SIZES["regulab"]))
        head = {"job": r["id"], "design": m.get("design"), "stream": stream, "size": size, "post_id": r.get("post_id"),
                "reference": m["style_ref"]["url"]}
        if not full:
            return head
        rv = m.get("review") if isinstance(m.get("review"), dict) else {}
        return {**head, "citation": m.get("citation") or "", "eyebrow": m.get("eyebrow") or "", "brief": m.get("brief") or "",
                "slides": [_words(s) for s in (m.get("slides") or []) if isinstance(s, dict)],
                "reading": {"summary": rv.get("summary"), "keep": rv.get("keep"), "change": rv.get("change"),
                            "brands_not_to_copy": rv.get("brands")}}
    if not rows:
        return {"next": None, "after": []}
    return {"next": one(rows[0], True), "after": [one(r, False) for r in rows[1:]]}


def import_reference(store: Any, job_id: str, urls: list[str], design_url: str = "", *, get: Any = requests.get,
                     now: datetime | None = None) -> dict[str, Any]:
    """The Canva rebuild of a reference design, as a NEW Design result beside the Semasa one: waiting for Wan's Simpan
    (like any reference design), never attached to a post before it. The Semasa drawing is left as it is."""
    if not urls or len(urls) > MAX_PAGES:
        raise BridgeError(f"send 1 to {MAX_PAGES} page addresses, in page order")
    rows = (store.table(db.MEDIA).select("id,post_id,created_by,reference_url,reference_path,meta").eq("id", job_id).limit(1)
            .execute().data or [])
    if not rows or not isinstance((rows[0].get("meta") or {}).get("style_ref"), dict):
        raise BridgeError("no such reference design")
    src = rows[0]
    m = dict(src["meta"])
    stream = m.get("stream") or "regulab"
    size = tuple(m["size"]) if isinstance(m.get("size"), list) and len(m["size"]) == 2 else None
    cards = [to_card(fetch_page(u, get), size) for u in urls]
    when = now or datetime.now(UTC)
    day, stamp = when.strftime("%Y/%m"), when.strftime("%d%H%M%S")
    row = store.table(db.MEDIA).insert({
        "mode": "slides", "type": "image", "status": "done", "prompt": "", "post_id": src.get("post_id"),
        "created_by": src.get("created_by"), "reference_url": src.get("reference_url"),
        "reference_path": src.get("reference_path"), "provider": "canva", "model": "canva-carousel-studio",
        "meta": {"flow": "canva"}}).execute().data[0]
    paths, public, sums = [], [], []
    for i, data in enumerate(cards, 1):
        path = f"{day}/{row['id']}-{stamp}-canva{i:02d}.jpg"
        public.append(db.upload_generated(store, path, data, "image/jpeg"))
        paths.append(path)
        sums.append(hashlib.sha256(data).hexdigest())
    keep = {k: m[k] for k in ("design", "format", "size", "size_name", "stream", "citation", "eyebrow", "slides", "brief",
                              "style_ref", "review", "from_post") if k in m}
    meta = {**keep, "flow": "canva", "look": "canva", "canva_for": job_id, "slide_urls": public, "slide_paths": paths,
            "sha256": sums, "count": len(public), "content_type": "image/jpeg", "bytes": sum(len(c) for c in cards),
            "design_url": design_url, "awaiting_confirm": True, "stream": stream, "finished_at": when.isoformat()}
    db.finish_media(store, row["id"], status="done", generated_media_url=public[0], provider="canva",
                    model="canva-carousel-studio", error=None, meta=meta)
    return {"media_id": row["id"], "pages": len(public)}


def _summary(text: str) -> None:
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    action = os.environ.get("CANVA_ACTION", "queue")
    store = db.client(SupabaseSettings.load())
    try:
        if action == "queue":
            today = (datetime.now(UTC) + MYT).date().isoformat()
            queue = {"carousel": render_queue(next_carousels(store, today)),
                     "reference": render_references(next_references(store))}
            _summary("## Canva queue\n\n```json\n" + json.dumps(queue, ensure_ascii=False, indent=1) + "\n```")
            return 0
        if action == "import":
            urls = json.loads(os.environ.get("CANVA_URLS", "[]"))
            if os.environ.get("CANVA_JOB_ID"):
                got = import_reference(store, os.environ["CANVA_JOB_ID"], [str(u) for u in urls],
                                       os.environ.get("CANVA_DESIGN_URL", ""))
                _summary(f"## Canva import\n\n{got['pages']} pages of the reference design stored (media {got['media_id']}). "
                         "They wait in the Design tab for Wan's Save; nothing is attached to a post before that.")
                return 0
            got = import_design(store, os.environ.get("CANVA_POST_ID", ""), [str(u) for u in urls],
                                os.environ.get("CANVA_DESIGN_URL", ""))
            done = (f"{got['pages']} pages stored and attached to the draft post (media {got['media_id']})." if got["attached"]
                    else f"{got['pages']} pages stored (media {got['media_id']}), NOT attached: the post is {got['status']}. "
                    "Move it back to draft in Semasa and press Use this set, so Wan sees the pictures before they go out.")
            _summary("## Canva import\n\n" + done)
            return 0
        raise BridgeError(f"unknown action {action!r}")
    except (BridgeError, ValueError, requests.RequestException) as exc:
        _summary(f"## Canva bridge refused\n\n{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
