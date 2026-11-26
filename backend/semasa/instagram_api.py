"""Instagram posts from Apify's apidojo actor: the LAST resort after the saved Playwright login (see apify_budget.py).

`fetch` asks apify_budget.check FIRST and makes no run when it refuses, so a spent month, a missing token or an unreadable
account is a plain note and never an HTTP run. It asks the actor for a handful of posts of one or two watched accounts (or
a hashtag when no account is watched) and maps each answer to the post shape every other reader in social_web.py returns.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from . import apify_budget
from .log import get_logger

log = get_logger("semasa.instagram_api")

IG_BASE = "https://www.instagram.com"
RUN_SECONDS = 120
Post = Callable[[str, str, dict[str, Any]], tuple[int, Any]]


class ApiError(RuntimeError):
    pass


def http_post(path: str, tok: str, body: dict[str, Any]) -> tuple[int, Any]:
    req = urllib.request.Request(apify_budget.API + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json",
                                          "User-Agent": "semasa-apify"})
    try:
        with urllib.request.urlopen(req, timeout=RUN_SECONDS + 40) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except Exception:  # noqa: BLE001
            return exc.code, {}
    except Exception as exc:  # noqa: BLE001
        raise ApiError(f"{type(exc).__name__}: {str(exc)[:100]}") from exc


def post_row(item: dict[str, Any], cap: int = 500) -> dict[str, Any] | None:
    """One answer of the actor as a post: {id, username, text, permalink, timestamp, counts, shown}. None for an item that is
    not a post with a code, a date and words (a reel without a caption is not an argument)."""
    code = str(item.get("code") or "").strip()
    when = apify_budget._when(item.get("createdAt"))
    text = " ".join(str(item.get("caption") or "").split())
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    if not code or not when or len(text) < 15:
        return None
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    counts = {"likes": item.get("likeCount"), "comments": item.get("commentCount")}
    if video.get("playCount") is not None:
        counts["plays"] = video["playCount"]
    shown = {k: f"{v:,}" for k, v in counts.items() if isinstance(v, int) and k in ("likes", "comments")}
    return {"id": code, "username": str(owner.get("username") or ""), "text": text[:cap], "permalink": f"{IG_BASE}/p/{code}/",
            "timestamp": when.isoformat(), "counts": {k: v for k, v in counts.items() if isinstance(v, int)} or {"likes": None},
            "shown": shown}


def fetch(urls: list[str], now: datetime | None = None, get: apify_budget.Get | None = None,
          post: Post | None = None, items: int | None = None) -> tuple[list[dict[str, Any]], str]:
    """(posts, note). The note says why nothing was asked, or what was. Never raises."""
    now = now or datetime.now(UTC)
    ok, why, info = apify_budget.check(items, now, get)
    if not ok:
        return [], f"not run: {why}"
    if not urls:
        return [], "not run: no account or hashtag to read"
    n = info["items"]
    tok = apify_budget.token()
    path = (f"/v2/acts/{quote(apify_budget.ACTOR, safe='~')}/run-sync-get-dataset-items"
            f"?timeout={RUN_SECONDS}&maxTotalChargeUsd={round(info['cost_usd'] * 2, 4)}")
    try:
        code, body = (post or http_post)(path, tok, {"startUrls": urls, "resultsLimit": n, "maxItems": n})
    except ApiError as exc:
        return [], f"the run failed ({exc})"
    if code not in (200, 201) or not isinstance(body, list):
        msg = str(((body or {}).get("error") or {}).get("message") or "") if isinstance(body, dict) else ""
        return [], f"the run answered HTTP {code}" + (f": {msg[:120]}" if msg else "")
    rows = [r for r in (post_row(i) for i in body if isinstance(i, dict)) if r]
    cap = info["limits"]["cap_usd"]
    return rows, f"{len(body)} item(s) from Apify, {len(rows)} usable, about ${info['cost_usd']} of ${cap:.2f}"
