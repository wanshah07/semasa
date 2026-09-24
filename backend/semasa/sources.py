"""The source registry and the three parsers (RSS, Google Trends, rendered HTML).

Every address here was fetched and answered on 23 Sep 2026 from an open-internet
caller (the Composio sandbox; a GitHub runner has the same egress). `kind` says how
it is read:

  rss     feedparser over a real feed — the cheap, stable path
  trends  Google Trends' daily RSS, whose items are nested `ht:news_item` blocks
  html    the front page rendered in Chromium, headlines pulled by a generic rule

Addresses that did NOT answer and are deliberately absent: thestar.com.my/rss/*
(404), bernama.com/*/rss.php (404), astroawani.com/rss/* (404), theedgemalaysia
(404), harakahdaily (403). Re-probe before assuming; egress and sites both move.

Studio's own sweep (argus) already reads NPRA, JAKIM, halal.gov.my, EU/UK law, PubMed,
Reddit and the cosmetic-science blogs. This registry is deliberately the OTHER half:
general Malaysian news and what Malaysians are searching for right now.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

import feedparser
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Source:
    name: str
    kind: str                 # rss | trends | html
    url: str
    lang: str = "ms"          # default language of the outlet; overridden per item when detectable
    tags: tuple[str, ...] = ()
    # html only: paths that are never a story
    skip_paths: tuple[str, ...] = ("/video", "/tag/", "/tags/", "/topik/", "/category/", "/author/", "/login",
                                   "/search", "/galeri", "/gallery", "/podcast", "/live", "/foto")


@dataclass
class Item:
    title: str
    url: str
    source: str
    lang: str
    published_at: datetime | None = None
    snippet: str | None = None
    tags: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


SOURCES: tuple[Source, ...] = (
    # What is loud right now — aggregated across every Malaysian outlet
    Source("Google News MY (BM)", "rss", "https://news.google.com/rss?hl=ms-MY&gl=MY&ceid=MY:ms", "ms", ("aggregator",)),
    Source("Google News MY (EN)", "rss", "https://news.google.com/rss?hl=en-MY&gl=MY&ceid=MY:en", "en", ("aggregator",)),
    Source("Google Trends MY", "trends", "https://trends.google.com/trending/rss?geo=MY", "ms", ("trending",)),
    # Topic searches Wan actually cares about, phrased the way the outlets write them
    Source("Google News: kosmetik/NPRA", "rss",
           "https://news.google.com/rss/search?q=kosmetik+OR+NPRA+OR+%22produk+kecantikan%22&hl=ms-MY&gl=MY&ceid=MY:ms",
           "ms", ("aggregator", "kosmetik")),
    Source("Google News: halal", "rss",
           "https://news.google.com/rss/search?q=halal+JAKIM+OR+%22sijil+halal%22+OR+%22logo+halal%22&hl=ms-MY&gl=MY&ceid=MY:ms",
           "ms", ("aggregator", "halal")),
    Source("Google News: KKM/ubat", "rss",
           "https://news.google.com/rss/search?q=KKM+ubat+OR+farmasi+OR+%22produk+tidak+berdaftar%22&hl=ms-MY&gl=MY&ceid=MY:ms",
           "ms", ("aggregator", "farmaseutikal")),
    Source("Google News: makanan/BKKM", "rss",
           "https://news.google.com/rss/search?q=%22keracunan+makanan%22+OR+BKKM+OR+%22label+makanan%22&hl=ms-MY&gl=MY&ceid=MY:ms",
           "ms", ("aggregator", "makanan")),
    # Outlets with real feeds
    Source("Berita Harian", "rss", "https://www.bharian.com.my/feed", "ms"),
    Source("Harian Metro", "rss", "https://www.hmetro.com.my/feed", "ms"),
    Source("Utusan Malaysia", "rss", "https://www.utusan.com.my/feed/", "ms"),
    Source("Kosmo!", "rss", "https://www.kosmo.com.my/feed/", "ms"),
    Source("Malaysiakini (BM)", "rss", "https://www.malaysiakini.com/my/rss/news.rss", "ms"),
    Source("Malaysiakini (EN)", "rss", "https://www.malaysiakini.com/en/rss/news.rss", "en"),
    Source("Malay Mail", "rss", "https://www.malaymail.com/feed/rss/malaysia", "en"),
    Source("Free Malaysia Today", "rss", "https://www.freemalaysiatoday.com/category/nation/feed/", "en"),
    Source("New Straits Times", "rss", "https://www.nst.com.my/feed", "en"),
    # Front pages that only render in a browser
    Source("Astro Awani", "html", "https://www.astroawani.com/home", "ms"),
    Source("Sinar Harian", "html", "https://www.sinarharian.com.my/", "ms"),
    Source("Bernama (BM)", "html", "https://www.bernama.com/bm/", "ms"),
)


# --- helpers -------------------------------------------------------------------

_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref$|source$)", re.I)
_WS = re.compile(r"\s+")


def clean_title(text: str | None) -> str:
    return _WS.sub(" ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()


def clean_url(url: str) -> str:
    """Drop tracking parameters and fragments; keep everything that identifies the story."""
    p = urlparse(url.strip())
    if not p.scheme or not p.netloc:
        return url.strip()
    kept = [kv for kv in p.query.split("&") if kv and not _TRACKING.match(kv.split("=")[0])]
    return p._replace(query="&".join(kept), fragment="").geturl()


def parse_date(value: Any) -> datetime | None:
    """feedparser gives a struct_time; Trends gives RFC 2822 text."""
    import calendar
    import email.utils
    import time as _time

    if value is None:
        return None
    if isinstance(value, _time.struct_time):
        return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
    if isinstance(value, str):
        try:
            dt = email.utils.parsedate_to_datetime(value)
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            return None
    return None


def strip_gnews_suffix(title: str, publisher: str | None) -> str:
    """Google News writes 'Headline - Publisher'; the publisher lives in `source` already."""
    if publisher and title.endswith(f" - {publisher}"):
        return title[: -len(publisher) - 3].rstrip()
    return re.sub(r"\s+-\s+[^-]{2,40}$", "", title) if title.count(" - ") == 1 else title


# --- parsers -------------------------------------------------------------------

def parse_rss(source: Source, text: str) -> list[Item]:
    feed = feedparser.parse(text)
    items: list[Item] = []
    for e in feed.entries:
        link = clean_url(e.get("link") or "")
        title = clean_title(e.get("title"))
        if not link or not title:
            continue
        publisher = None
        src = e.get("source")
        if isinstance(src, dict):
            publisher = clean_title(src.get("title"))
        if "aggregator" in source.tags:
            title = strip_gnews_suffix(title, publisher)
        snippet = clean_title(e.get("summary") or e.get("description"))
        if "aggregator" in source.tags:
            snippet = None  # Google's description is a list of related links, not a summary
        tags = [t.get("term") for t in e.get("tags", []) if isinstance(t, dict) and t.get("term")]
        items.append(Item(
            title=title,
            url=link,
            source=publisher or source.name,
            lang=source.lang,
            published_at=parse_date(e.get("published_parsed") or e.get("updated_parsed")),
            snippet=snippet[:600] if snippet else None,
            tags=[*source.tags, *tags][:12],
            raw={"feed": source.name},
        ))
    return items


_HT = "{https://trends.google.com/trending/rss}"


def parse_trends(source: Source, text: str) -> list[Item]:
    """Each trending query carries up to three news items; each news item is a row,
    tagged with the query and its approximate traffic so the page can rank it."""
    root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    items: list[Item] = []
    for it in root.iter("item"):
        query = (it.findtext("title") or "").strip()
        traffic = (it.findtext(f"{_HT}approx_traffic") or "").strip()
        when = parse_date(it.findtext("pubDate"))
        for news in it.findall(f"{_HT}news_item"):
            url = clean_url(news.findtext(f"{_HT}news_item_url") or "")
            title = clean_title(news.findtext(f"{_HT}news_item_title"))
            if not url or not title:
                continue
            publisher = clean_title(news.findtext(f"{_HT}news_item_source")) or source.name
            items.append(Item(
                title=title,
                url=url,
                source=publisher,
                lang=source.lang,
                published_at=when,
                snippet=clean_title(news.findtext(f"{_HT}news_item_snippet")) or None,
                tags=[*source.tags, f"carian:{query}", f"trafik:{traffic}"] if query else list(source.tags),
                raw={"feed": source.name, "query": query, "approx_traffic": traffic},
            ))
    return items


def parse_html(source: Source, html: str, *, min_len: int = 35, max_items: int = 60) -> list[Item]:
    """Generic front-page headline rule, deliberately not per-site selectors:
    an anchor on the same host, with a path at least two segments deep, whose
    visible text is long enough to be a headline. Site redesigns change class
    names weekly; they rarely change what a headline link looks like."""
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(source.url).netloc.removeprefix("www.")
    seen: set[str] = set()
    items: list[Item] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        url = clean_url(urljoin(source.url, href))
        p = urlparse(url)
        if p.netloc.removeprefix("www.") != host:
            continue
        path = p.path.rstrip("/")
        if path.count("/") < 2 or any(s in path.lower() for s in source.skip_paths):
            continue
        text = clean_title(a.get_text(" "))
        if len(text) < min_len or url in seen:
            continue
        seen.add(url)
        items.append(Item(title=text, url=url, source=source.name, lang=source.lang,
                          tags=list(source.tags), raw={"feed": source.name}))
        if len(items) >= max_items:
            break
    return items
