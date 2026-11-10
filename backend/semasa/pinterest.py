"""A Pinterest pin as a poster reference (Wan, 10 Nov 2026: "make sure the poster can be render based on pinterest").

A pin link (pinterest.com/pin/<id>, a country domain, or a pin.it short link) is a web page, not a picture, so the picture
generators refused it as "not an image". The page carries its picture as og:image; this reads it and hands back the picture's
own address, so the poster job draws from it exactly as it does from any other reference picture: the reference is READ for its
mood and layout and the poster is drawn afresh (media_generator "recreate"), never copied. A board or a profile holds many
pictures and has no single one to read, so it is refused with that reason rather than guessed at."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .fetch import HEADERS

PIN_PATH = re.compile(r"/pin/\d+", re.I)


def _host(url: str) -> str:
    return (urlparse(url if "//" in url else "https://" + url).hostname or "").lower()


def is_pinterest(url: str) -> bool:
    host = _host(url)
    return host == "pin.it" or bool(re.search(r"(^|\.)pinterest\.[a-z.]+$", host))


def is_pin_link(url: str) -> bool:
    """One pin: a /pin/<id> page, or a pin.it short link (which is always one pin)."""
    if not is_pinterest(url):
        return False
    return _host(url) == "pin.it" or bool(PIN_PATH.search(urlparse(url).path))


def _original(url: str, get: Any) -> str:
    """Pinterest serves the same picture at /236x/, /474x/, /736x/ and /originals/: the largest that answers is used."""
    big = re.sub(r"/(?:\d+x(?:\d+)?|[^/]+)/(?=[0-9a-f]{2}/[0-9a-f]{2}/)", "/originals/", url, count=1)
    if big != url:
        try:
            r = get(big, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=20, stream=True)
            ok = r.status_code == 200 and str(r.headers.get("content-type", "")).startswith("image/")
            r.close()
            if ok:
                return big
        except requests.RequestException:
            pass
    return url


def resolve(url: str, get: Any = requests.get) -> dict[str, Any]:
    """{"image": address, "title": ..., "pin": the pin's own page} for one pin link. Raises ValueError, with a reason Wan can
    read, for a board, a login wall or a page with no picture."""
    if not is_pin_link(url):
        raise ValueError("that Pinterest link is a board or a profile, which holds many pictures: open one pin and send its link")
    try:
        r = get(url, headers={"User-Agent": HEADERS["User-Agent"], "Accept-Language": "en"}, timeout=25, allow_redirects=True)
    except requests.RequestException as exc:
        raise ValueError(f"Pinterest could not be reached ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise ValueError(f"Pinterest answered {r.status_code} for that pin: it may be private or removed")
    soup = BeautifulSoup(r.text, "lxml")

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    image = meta("og:image", "og:image:url", "twitter:image")
    if not image.startswith("http"):
        raise ValueError("that pin page carried no picture (a login wall or a removed pin)")
    return {"image": _original(image, get), "title": meta("og:title", "twitter:title")[:200], "pin": str(getattr(r, "url", url))}
