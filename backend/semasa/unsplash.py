"""Unsplash as a picture source (Wan, 26 Sep 2026: "add also unsplashed choice so image can create from there").

A picture job whose provider is "unsplash" is a search first and a pick after, on the same media_generations row:
  1. the page inserts it with the search words as the prompt; the worker asks Unsplash and stores up to 24 results in
     meta.results, the row is `done` with no picture yet (the page shows the results to choose from);
  2. the page writes meta.pick = the chosen photo's id and sets the row `pending` again; the worker tells Unsplash the
     photo was downloaded (their API rule), fetches it at 2160 px, stores it in semasa-generated and records who took
     it (meta.credit). From then on it is a picture like any other: a post's picture, a slide or Design background.

The key (UNSPLASH_ACCESS_KEY) lives on the worker only, never in the page. Unsplash's API guidelines are kept: the
results the page shows are Unsplash's own addresses (hotlinked), the download is reported, and the photographer is
credited with a link wherever the page shows the photo. No credit goes into a caption: ws.regulab captions carry no
URL, and the Unsplash licence does not require one there.
"""

from __future__ import annotations

import io
import os
from datetime import UTC, datetime
from typing import Any

import requests
from PIL import Image

from . import db
from .log import get_logger

log = get_logger("semasa.unsplash")

API = "https://api.unsplash.com"
APP = "semasa"
ORIENTATIONS = ("squarish", "portrait", "landscape")
PER_PAGE = 24
WIDTH = 2160


class UnsplashError(RuntimeError):
    """Final for the row: the message is shown on the page."""


def _key() -> str:
    key = (os.environ.get("UNSPLASH_ACCESS_KEY") or "").strip()
    if not key:
        raise UnsplashError("UNSPLASH_ACCESS_KEY is not set: create a free app at unsplash.com/developers, then add its "
                            "Access Key under GitHub → Settings → Secrets and variables → Actions, and in media.yml")
    return key


def _get(url: str, params: dict[str, Any] | None = None) -> Any:
    r = requests.get(url, params=params, timeout=30,
                     headers={"Authorization": f"Client-ID {_key()}", "Accept-Version": "v1"})
    # a used-up hour comes back as 403 "Rate Limit Exceeded", so it is told apart from a refused key first
    if r.status_code == 429 or (r.status_code >= 400 and (r.headers.get("X-Ratelimit-Remaining") == "0"
                                                          or "rate limit" in (r.text or "").lower())):
        raise UnsplashError("Unsplash's hourly limit is used up (50 an hour for a demo app): try again next hour, "
                            "or apply for production at unsplash.com/developers for 5000")
    if r.status_code in (401, 403):
        raise UnsplashError(f"Unsplash refused the key ({r.status_code}): {r.text[:200]}")
    r.raise_for_status()
    return r.json()


def ref(url: str) -> str:
    """Unsplash asks for its links to carry the app's name."""
    return f"{url}{'&' if '?' in url else '?'}utm_source={APP}&utm_medium=referral" if url else ""


def slim(p: dict[str, Any]) -> dict[str, Any]:
    """What the page needs to show a result and the worker needs to fetch it, nothing else."""
    urls, user, links = p.get("urls") or {}, p.get("user") or {}, p.get("links") or {}
    return {"id": p.get("id"), "w": p.get("width"), "h": p.get("height"), "color": p.get("color"),
            "alt": (p.get("alt_description") or p.get("description") or "")[:200],
            "thumb": urls.get("small"), "raw": urls.get("raw"), "page": ref(links.get("html") or ""),
            "download_location": links.get("download_location"),
            "name": user.get("name") or user.get("username") or "", "profile": ref((user.get("links") or {}).get("html") or "")}


def search(query: str, orientation: str | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"query": query, "per_page": PER_PAGE, "content_filter": "high"}
    if orientation in ORIENTATIONS:
        params["orientation"] = orientation
    data = _get(f"{API}/search/photos", params)
    return [slim(p) for p in (data.get("results") or []) if p.get("id") and (p.get("urls") or {}).get("raw")]


def fetch(photo: dict[str, Any]) -> bytes:
    """Report the download (Unsplash's rule for an app that uses a photo), then fetch it as a 2160 px JPEG."""
    if photo.get("download_location"):
        _get(photo["download_location"])
    raw = photo["raw"]
    r = requests.get(f"{raw}{'&' if '?' in raw else '?'}w={WIDTH}&fm=jpg&q=85", timeout=60)
    r.raise_for_status()
    data = r.content
    Image.open(io.BytesIO(data)).verify()                 # a picture, not an error page
    return data


def process(store: Any, row: dict[str, Any], max_attempts: int) -> bool:
    row_id = row["id"]
    meta = dict(row.get("meta") or {})
    pick = str(meta.get("pick") or "").strip()
    try:
        if not pick:
            query = str(row.get("prompt") or "").strip()
            if not query:
                raise UnsplashError("no search words")
            results = search(query, meta.get("orientation"))
            meta.update(results=results, searched_at=datetime.now(UTC).isoformat(), step="choose")
            db.finish_media(store, row_id, status="done", provider="unsplash", model="search", error=None, meta=meta,
                            generated_media_url=None)
            log.info("%s: Unsplash search %r → %d photos", row_id, query, len(results))
            return True
        photo = next((p for p in meta.get("results") or [] if p.get("id") == pick), None)
        if not photo:
            raise UnsplashError(f"photo {pick} is not among this search's results: search again")
        data = fetch(photo)
        path = f"{datetime.now(UTC).strftime('%Y/%m')}/{row_id}-unsplash-{pick}.jpg"
        url = db.upload_generated(store, path, data, "image/jpeg")
        with Image.open(io.BytesIO(data)) as im:
            size = im.size
        meta.update(step="picked", picked_at=datetime.now(UTC).isoformat(), unsplash_id=pick, bytes=len(data),
                    width=size[0], height=size[1], content_type="image/jpeg", storage_path=path,
                    credit={"name": photo.get("name"), "profile": photo.get("profile"), "page": photo.get("page")},
                    alt=meta.get("alt") or photo.get("alt") or "")
        db.finish_media(store, row_id, status="done", provider="unsplash", model="photo", error=None, meta=meta,
                        generated_media_url=url)
        log.info("%s: Unsplash photo %s by %s stored (%d bytes)", row_id, pick, photo.get("name"), len(data))
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, UnsplashError) or attempts >= max_attempts
        msg = f"{type(exc).__name__}: {str(exc)[:600]}"
        log.error("%s: %s (attempt %d)", row_id, msg, attempts)
        db.finish_media(store, row_id, status="error" if final else "pending", error=msg, provider="unsplash")
        return False
