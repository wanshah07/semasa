"""Regulatory notices and new publications: two segments beside Isu Semasa, swept once every 24 hours (Wan, 26 Sep 2026:
"add segment like current issue for regulatory and latest publication - do the same mechanism like current issue but
for these segments run every 24 hours - can add as post and idea"). The flow is the one current issues already has:
item → idea (a post, a carousel or a poster) → drawn → post.

REGULATORY reads the regulators' own list pages, so an item names the notice itself, not a news story about it:
  NPRA (Malaysia)           announcements, Kenyataan Media KKM, safety alerts, directives and cosmetic circulars
  Portal Halal Malaysia     JAKIM's announcements and news (recalls, withdrawn recognitions of foreign bodies)
  HSA (Singapore)           ASEAN neighbour: announcements, product alerts
  EU SCCS                   the scientific opinions behind EU cosmetic restrictions
  UK OPSS                   product safety and cosmetics notices (Atom feed)
  China NMPA                the regulator's English news
LATEST PUBLICATION reads PubMed's own API (E-utilities, no key): papers from the last 14 days on cosmetic science,
dermatology for consumers, halal authentication and cosmetic contaminants, each with its journal, DOI and abstract.
The paper is the citable thing; a blog never is.

Every source was fetched and parsed from its live page on 26 Sep 2026. Each item gets a Malay summary, the domain it
belongs to, one line on why it matters, and a "relevant" verdict from the writer; the page hides what is not relevant
rather than deleting it, so tomorrow's sweep does not ask again. The sweep runs inside the scrape (three times a day,
on the Supabase clock) and does its work only when 23 hours have passed since the last one, or when the page asks
for it now. Items stay 45 days.

Scope note: until 26 Sep 2026 Semasa read only the "other half of the world" and left the regulators to ws.regulab
Studio's sweep (argus CLAUDE.md, rule 1). Wan asked for them here. Reading twice publishes nothing twice: Semasa's
publisher is a dry run, and only one publisher is ever switched on.
"""

from __future__ import annotations

import io
import json
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import db, fetch
from .log import get_logger
from .sources import Source, clean_title, parse_rss

log = get_logger("semasa.watch")

WATCH = "semasa_watch"
KEY = "watch"                       # semasa_settings row: last run, the page's "sweep now", the last report
EVERY = timedelta(hours=23)         # the scrape runs every 8 h; the first run after 23 h does the daily sweep
MAX_AGE = timedelta(days=45)        # a notice older than this on its own page is not "latest"
# Kept compact (Wan, 26 Sep 2026: "make the data compact to save the storage"). Each window is at least as long as the
# window the source is read over, so nothing pruned can come back as "new" on the next sweep.
KEEP = timedelta(days=45)           # regulatory notices (read over MAX_AGE)
KEEP_PAPERS = timedelta(days=31)    # papers (PubMed is read over 14 days, competitors over 30)
KEEP_PASTED = timedelta(days=90)    # links Wan pasted himself
TOMBSTONE_AFTER = timedelta(days=3)  # a hidden or not-relevant item keeps only its link and title after this
ABSTRACT_KEEP, SUMMARY_KEEP, WHY_KEEP = 800, 400, 240
PER_SOURCE = 25
DOMAINS = ("kosmetik", "makanan", "halal_my", "farmaseutikal", "fatwa", "sains_kosmetik", "kajian_kes", "lain")

MONTHS = {m: i for i, ms in enumerate(
    [("jan", "januari", "january"), ("feb", "februari", "february"), ("mar", "mac", "march"), ("apr", "april"),
     ("may", "mei"), ("jun", "june"), ("jul", "julai", "july"), ("aug", "ogos", "august", "ogo"),
     ("sep", "sept", "september"), ("oct", "okt", "oktober", "october"), ("nov", "november"),
     ("dec", "dis", "disember", "december")], start=1) for m in ms}


@dataclass(frozen=True)
class WatchSource:
    name: str
    section: str                    # regulatory | publication
    url: str
    parse: Callable[[str, str, date], list[dict[str, Any]]]
    lang: str = "en"
    country: str = ""


def _month(word: str) -> int | None:
    return MONTHS.get(word.strip(".").lower()[:9]) or MONTHS.get(word.strip(".").lower()[:3])


def date_in_words(text: str) -> date | None:
    """'24 Ogos 2026', '25 September 2026', '30 April 2026' → a date."""
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,10})\.?\s+(20\d{2})\b", text or "")
    if not m or not _month(m.group(2)):
        return None
    try:
        return date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _item(title: str, url: str, when: date | None, **extra: Any) -> dict[str, Any]:
    return {"title": clean_title(title)[:500], "url": url, "published_at": when, **extra}


# --- the regulators' pages --------------------------------------------------------------------------------------

NPRA_KIND = (("press-release", "Kenyataan Media KKM"), ("safety-alerts", "Safety alert"), ("announcement", "Announcement"),
             ("directives-cosmetic", "Cosmetic circular"), ("directive", "Directive"), ("industry-news", "Industry news"),
             ("circular", "Circular"))


def parse_npra(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """NPRA's front page lists its notices in two shapes: an article block with a day and a month (the year is in the
    link, or it is this year) and a table row 'published on YYYY-MM-DD'. Only numbered articles are taken, never menus."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"/\d{6,8}-[\w-]+", href):
            continue
        url = urljoin(base, href.split("?")[0])
        title = a.get_text(" ", strip=True)
        if url in seen or len(title) < 12:
            continue
        kind = next((label for key, label in NPRA_KIND if key in href), "Notice")
        when = date_in_words(title)
        box = a.find_parent("p")
        if not when and box:
            m = re.search(r"published on (\d{4})-(\d{2})-(\d{2})", box.get_text(" ", strip=True))
            if m:
                when = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        art = a.find_parent(class_="sppb-addon-article")
        if not when and art:
            d = art.find(class_="sppb-meta-date")
            mo = art.find(class_="sppb-meta-month")
            if d and mo and _month(mo.get_text(strip=True)):
                y = re.search(r"-(20\d{2})/", href)
                year = int(y.group(1)) if y else today.year
                try:
                    when = date(year, _month(mo.get_text(strip=True)), int(d.get_text(strip=True)))
                except ValueError:
                    when = None
                if when and not y and when > today + timedelta(days=1):
                    when = when.replace(year=year - 1)
        if not when:
            continue
        seen.add(url)
        out.append(_item(title, url, when, kind=kind))
    return out


def parse_halal_portal(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """Portal Halal Malaysia: 'TITLE dd/mm/yyyy chevron_right' links, Announcement and News. The portal gives several
    news items the SAME address, so a duplicate address is told apart by its title."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if "page_title=" not in a["href"]:
            continue
        text = a.get_text(" ", strip=True).replace("chevron_right", "").strip()
        m = re.search(r"(\d{2})/(\d{2})/(20\d{2})\s*$", text)
        if not m:
            continue
        title = text[: m.start()].strip()
        url = urljoin(base, a["href"])
        key = (title.lower(), m.group(0))
        if key in seen or len(title) < 12:
            continue
        seen.add(key)
        if any(o["url"] == url for o in out):
            url += "#" + re.sub(r"[^a-z0-9]+", "-", title.lower())[:60]
        kind = "Announcement" if "page_title=Announcement" in a["href"] else "News"
        try:
            when = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            continue
        out.append(_item(title, url, when, kind=kind))
    return out


def parse_hsa(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """HSA's announcements: each link reads '25 September 2026 25 September 2026 <title> Audiences …'."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if not a["href"].startswith("/announcements/") or a["href"].rstrip("/") == "/announcements":
            continue
        text = a.get_text(" ", strip=True)
        m = re.match(r"(\d{1,2} [A-Za-z]+ 20\d{2})\s+(?:\1\s+)?(.+?)(?:\s+Audiences\b.*)?$", text)
        if not m:
            continue
        url = urljoin(base, a["href"])
        if url in seen:
            continue
        seen.add(url)
        out.append(_item(m.group(2), url, date_in_words(m.group(1)), kind="Announcement"))
    return out


def parse_sccs(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """The EU Scientific Committee on Consumer Safety's opinions: '<title> SCCS/1689/26 - 30 April 2026'."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if "/publications/" not in a["href"]:
            continue
        box = a.find_parent(["li", "div", "article"])
        ctx = box.get_text(" ", strip=True) if box else ""
        m = re.search(r"(SCCS/\d{3,4}/\d{2})\s*-\s*(\d{1,2} [A-Za-z]+ 20\d{2})", ctx)
        url = urljoin(base, a["href"])
        if not m or url in seen:
            continue
        seen.add(url)
        out.append(_item(a.get_text(" ", strip=True), url, date_in_words(m.group(2)), kind="SCCS opinion", ref=m.group(1)))
    return out


def parse_nmpa(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """China NMPA's English news: the date is in the address (2026-09/23/c_1215574.htm)."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"(20\d{2})-(\d{2})/(\d{2})/c_\d+\.htm", a["href"])
        title = a.get_text(" ", strip=True)
        url = urljoin(base, a["href"])
        if not m or url in seen or len(title) < 12:
            continue
        seen.add(url)
        out.append(_item(title, url, date(int(m.group(1)), int(m.group(2)), int(m.group(3))), kind="News"))
    return out


def parse_feed(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """An RSS or Atom feed (UK OPSS), through the scraper's own feed parser."""
    out = []
    for it in parse_rss(Source("feed", "rss", base, "en"), html):
        out.append(_item(it.title, it.url, it.published_at.date() if it.published_at else None, snippet=it.snippet,
                         kind="Notice"))
    return out


# --- beyond cosmetics and medicines (Wan, 26 Sep 2026: "make sure the scope run not limit to pharma and cosmetic only")
# Food and halal regulators whose own list pages a GitHub runner can read, measured from an open-internet sandbox on
# 26 Sep 2026. Not reachable from there, so not here: e-Fatwa (e-fatwa.gov.my), FSQD (fsq.moh.gov.my) and moh.gov.my
# (403). JAKIM's "Isu-Isu Tular Halal" pages carry no dates, so they are reference, not news: paste one when needed.

def dated_links(html: str, base: str, pattern: str, kind: str, levels: int = 4) -> list[dict[str, Any]]:
    """Links whose href matches `pattern`, each dated from the nearest enclosing block that states a date in words
    ('26 September 2026', '21 Julai 2026'). A link with no date near it is a menu, not an item, and is skipped."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(pattern, href):
            continue
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        url = urljoin(base, href.split("#")[0])
        if len(title) < 15 or url in seen:
            continue
        node, when = a, None
        for _ in range(levels):
            node = node.parent
            if node is None:
                break
            when = date_in_words(node.get_text(" ", strip=True))
            if when:
                break
        if when:
            seen.add(url)
            out.append(_item(title, url, when, kind=kind))
    return out


def parse_farmasi(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """KKM Bahagian Farmasi: every news link carries its date, /ms/berita/27-ogo-2026/<slug>."""
    soup = BeautifulSoup(html, "lxml")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        m = re.search(r"/berita/(\d{1,2})-([a-z]{3})-(20\d{2})/", a["href"])
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        url = urljoin(base, a["href"])
        if not m or url in seen or len(title) < 15 or title.lower().startswith("bacaan penuh"):
            continue
        try:
            when = date(int(m.group(3)), _month(m.group(2)) or 0, int(m.group(1)))
        except ValueError:
            continue
        seen.add(url)
        out.append(_item(title.removesuffix("...").strip(), url, when, kind="Berita KKM Farmasi"))
    return out


def parse_jakim(html: str, base: str, today: date) -> list[dict[str, Any]]:
    return dated_links(html, base, r"/ms/kenyataan-media/\d+", "Kenyataan Media JAKIM")


def parse_fsanz_recalls(html: str, base: str, today: date) -> list[dict[str, Any]]:
    return dated_links(html, base, r"/food-recalls/recall-alert/", "Food recall")


def parse_fsanz_news(html: str, base: str, today: date) -> list[dict[str, Any]]:
    return dated_links(html, base, r"foodstandards\.gov\.au/news/|^/news/.+|/circulars/notification-circular", "Notice")


def parse_eu_food(html: str, base: str, today: date) -> list[dict[str, Any]]:
    """The date in the words can be an event's ("SAVE THE DATE: … 3 December"); the link ends in the day it was
    published (…-2026-08-31_en), so that one wins when it is there."""
    out = dated_links(html, base, r"/food-safety-news/", "EU food safety news")
    for it in out:
        m = re.search(r"-(20\d{2})-(\d{2})-(\d{2})_[a-z]{2}$", it["url"])
        if m:
            it["published_at"] = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return out


def parse_fsa_alerts(text: str, base: str, today: date) -> list[dict[str, Any]]:
    """The UK Food Standards Agency's alert API (JSON): product recalls and allergy alerts."""
    out = []
    for it in (json.loads(text) or {}).get("items") or []:
        title = str(it.get("title") or "").strip()
        notation = str(it.get("notation") or "")
        url = it.get("alertURL") or (f"https://www.food.gov.uk/news-alerts/alert/{notation.lower()}" if notation else "")
        when = _any_date(str(it.get("created") or ""))
        types = " ".join(it.get("type") or [])
        kind = "Allergy alert" if "AA" in types.rsplit("/", 1)[-1] else "Food recall"
        if title and url:
            out.append(_item(title, url, when, kind=kind))
    return out


def parse_efsa(text: str, base: str, today: date) -> list[dict[str, Any]]:
    return [{**it, "kind": "EFSA opinion"} for it in parse_feed(text, base, today)]


SOURCES: tuple[WatchSource, ...] = (
    WatchSource("NPRA", "regulatory", "https://www.npra.gov.my/index.php/en/", parse_npra, "en", "MY"),
    WatchSource("Portal Halal Malaysia", "regulatory", "https://www.halal.gov.my/", parse_halal_portal, "en", "MY"),
    WatchSource("HSA Singapore", "regulatory", "https://www.hsa.gov.sg/announcements", parse_hsa, "en", "SG"),
    WatchSource("EU SCCS", "regulatory",
                "https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs/sccs-opinions_en",
                parse_sccs, "en", "EU"),
    WatchSource("UK OPSS", "regulatory",
                "https://www.gov.uk/search/news-and-communications.atom?organisations%5B%5D=office-for-product-safety-and-standards",
                parse_feed, "en", "UK"),
    WatchSource("China NMPA", "regulatory", "https://english.nmpa.gov.cn/news.html", parse_nmpa, "en", "CN"),
    WatchSource("KKM · Bahagian Farmasi", "regulatory", "https://pharmacy.moh.gov.my/ms", parse_farmasi, "ms", "MY"),
    WatchSource("JAKIM", "regulatory", "https://www.islam.gov.my/ms/kenyataan-media", parse_jakim, "ms", "MY"),
    WatchSource("FSANZ recalls", "regulatory", "https://www.foodstandards.gov.au/food-recalls/recalls", parse_fsanz_recalls,
                "en", "AU"),
    WatchSource("FSANZ", "regulatory", "https://www.foodstandards.gov.au/news", parse_fsanz_news, "en", "AU"),
    WatchSource("UK FSA", "regulatory", "https://data.food.gov.uk/food-alerts/id?_limit=30&_sort=-created",
                parse_fsa_alerts, "en", "UK"),
    WatchSource("EFSA", "regulatory", "https://www.efsa.europa.eu/en/all/rss", parse_efsa, "en", "EU"),
    WatchSource("EU food safety", "regulatory", "https://food.ec.europa.eu/food-safety-news_en", parse_eu_food, "en", "EU"),
)


# --- PubMed ----------------------------------------------------------------------------------------------------------

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
# (label, search, days back, how many) — sized on 26 Sep 2026 against PubMed's real counts: about 55, 62, 26, 71, 4 and
# 5 papers in 14 days, i.e. under 15 a day each, so a daily sweep of the newest 25 misses nothing
PUBMED_QUERIES: tuple[tuple[str, str, int, int], ...] = (
    # "all cosmetic science" (Wan, 26 Sep 2026): the key words in the TITLE (in an abstract "cosmetic" is mostly surgery),
    # plus every paper in the journals that are cosmetic science by definition
    ("Cosmetic science", '((cosmetic*[ti] OR cosmeceutical*[ti] OR sunscreen*[ti] OR "skin care"[ti] OR skincare[ti] OR '
                         '"personal care"[ti] OR "hair care"[ti] OR emollient*[ti] OR "skin microbiome"[ti]) NOT (surg*[ti] '
                         'OR surgical[tiab] OR implant*[ti])) OR "Int J Cosmet Sci"[ta] OR "J Cosmet Dermatol"[ta] OR '
                         '"J Cosmet Sci"[ta] OR "Cosmetics"[ta] OR "Skin Pharmacol Physiol"[ta] OR "Skin Res Technol"[ta]',
     14, 25),
    ("Cosmetic safety", '(cosmetic*[tiab] OR "personal care"[tiab] OR sunscreen*[tiab] OR "hair dye*"[tiab] OR '
                        'fragrance*[tiab] OR preservative*[ti] OR "skin lightening"[tiab] OR "skin whitening"[tiab]) AND '
                        '(safety[ti] OR toxicity[tiab] OR "contact dermatitis"[tiab] OR allergen*[tiab] OR sensiti*[ti] OR '
                        '"risk assessment"[tiab] OR "margin of safety"[tiab] OR mercury[tiab] OR hydroquinone[tiab] OR '
                        '"heavy metal*"[tiab] OR PFAS[tiab] OR benzene[tiab] OR steroid*[tiab]) '
                        'NOT (surg*[ti] OR surgical[tiab])', 14, 25),
    ("Dermatology for consumers", '(topical[ti] OR moisturi*[ti] OR emollient*[ti] OR "skin barrier"[ti]) AND '
                                  '(atopic OR acne OR rosacea OR hyperpigmentation OR melasma OR photoaging OR "skin barrier")',
     14, 15),
    # the main dermatology journals, on the conditions a skincare business meets (not cancer or surgery)
    ("Dermatology", '("J Am Acad Dermatol"[ta] OR "JAMA Dermatol"[ta] OR "Br J Dermatol"[ta] OR "J Eur Acad Dermatol '
                    'Venereol"[ta] OR "J Invest Dermatol"[ta] OR "Clin Exp Dermatol"[ta] OR "Acta Derm Venereol"[ta] OR '
                    '"Contact Dermatitis"[ta] OR "Exp Dermatol"[ta] OR "Photodermatol Photoimmunol Photomed"[ta] OR '
                    '"J Dermatolog Treat"[ta] OR "Am J Clin Dermatol"[ta]) AND (acne[tiab] OR atopic[tiab] OR eczema[tiab] OR '
                    'rosacea[tiab] OR pigment*[tiab] OR melasma[tiab] OR psoriasis[tiab] OR photoaging[tiab] OR '
                    '"skin aging"[tiab] OR "skin barrier"[tiab] OR alopecia[tiab] OR "hair loss"[tiab] OR "sensitive skin"[tiab] '
                    'OR sunscreen*[tiab] OR moisturi*[tiab] OR topical[ti]) NOT (melanoma[ti] OR carcinoma[ti] OR surg*[ti] OR '
                    'lymphoma[ti])', 14, 25),
    ("Halal science", '(halal[tiab] OR "pork adulteration"[tiab] OR (porcine[ti] AND (gelatin* OR adulterat* OR '
                      'authenticat* OR "species identification")) OR (gelatin*[ti] AND (source OR species OR authenticat*)))',
     14, 10),
)
# Derma brands' own research (Wan: "publication from our derma brands competitors"), found by the company in the
# authors' affiliations. Editable in the page (settings 'watch' → competitors); "A|B" lists two names for one brand.
COMPETITORS: tuple[tuple[str, str], ...] = (
    ("La Roche-Posay · CeraVe · Vichy (L'Oréal)", "L'Oreal"), ("Eucerin · Nivea (Beiersdorf)", "Beiersdorf"),
    ("Cetaphil (Galderma)", "Galderma"), ("Avène (Pierre Fabre)", "Pierre Fabre"), ("Bioderma (NAOS)", "NAOS|Bioderma"),
    ("Neutrogena · Aveeno (Kenvue)", "Kenvue"), ("Uriage", "Uriage"), ("ISDIN", "ISDIN"), ("Shiseido", "Shiseido"),
    ("Amorepacific", "Amorepacific"), ("Hada Labo (Rohto)", "Rohto"), ("Kao", "Kao Corporation"),
)
COMPETITOR_DAYS, COMPETITOR_MAX = 30, 30                # a company publishes a few papers a month, not a day


def _get(url: str, timeout: int) -> str:
    return fetch.get(url, timeout=timeout).text           # fetch.get carries a browser identity itself


EUTILS_GAP = 0.4                    # NCBI allows 3 calls a second without a key; the 26 Sep sweep lost a topic to 429
_last_eutils = [0.0]


def _eutils(url: str, timeout: int) -> str:
    """One E-utilities call, spaced out, with one patient retry on 429 (fetch.get never retries a 4xx)."""
    import requests
    for attempt in range(2):
        wait = _last_eutils[0] + EUTILS_GAP - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_eutils[0] = time.monotonic()
        try:
            return _get(url, timeout)
        except requests.HTTPError as exc:
            if attempt or exc.response is None or exc.response.status_code != 429:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def competitors_of(value: Any) -> list[tuple[str, list[str]]]:
    """The page's list ([{"label", "company"}] or ["Label = Company|Alias"]) or the default, as (label, [names])."""
    rows = []
    for it in value if isinstance(value, list) and value else [{"label": a, "company": b} for a, b in COMPETITORS]:
        if isinstance(it, dict):
            label, company = str(it.get("label") or "").strip(), str(it.get("company") or "").strip()
        else:
            label, _, company = str(it).partition("=")
            label, company = label.strip(), company.strip()
        names = [n.strip().replace('"', "") for n in (company or label).split("|") if n.strip()]
        if label and names:
            rows.append((label[:80], names[:4]))
    return rows[:25]


def _plain(text: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).lower()


def competitor_query(rows: list[tuple[str, list[str]]]) -> str:
    names = " OR ".join(f'"{n}"[ad]' for _, ns in rows for n in ns)
    return f"({names}) AND (skin[tiab] OR derm*[tiab] OR cosmetic*[tiab] OR hair[tiab] OR sunscreen*[tiab])"


def pubmed(timeout: int = 30, competitors: Any = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(items, report) — the newest papers per topic, plus the derma competitors' own, with abstracts."""
    ids: dict[str, str] = {}
    report = []
    rivals = competitors_of(competitors)
    queries = list(PUBMED_QUERIES)
    if rivals:
        queries.append(("Competitors", competitor_query(rivals), COMPETITOR_DAYS, COMPETITOR_MAX))
    for label, term, days, retmax in queries:
        try:
            q = json.loads(_eutils(f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&sort=date&datetype=edat&reldate={days}"
                                   f"&retmax={retmax}&tool=semasa&term={_quote(term)}", timeout))
            got = (q.get("esearchresult") or {}).get("idlist") or []
            for i in got:
                ids.setdefault(i, label)
            report.append({"name": f"PubMed · {label}", "ok": True, "items": len(got), "error": None})
        except Exception as exc:  # noqa: BLE001 - one topic failing must not end the sweep
            report.append({"name": f"PubMed · {label}", "ok": False, "items": 0,
                           "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    if not ids:
        return [], report
    return papers(ids, timeout, rivals), report


def papers(ids: dict[str, str], timeout: int = 30, rivals: list[tuple[str, list[str]]] | None = None) -> list[dict[str, Any]]:
    """PubMed records for these PMIDs ({pmid: topic}), each with its journal, authors, DOI and abstract. A competitor's
    paper is labelled with the brand whose company is in its authors' affiliations."""
    idlist = ",".join(ids)
    summ = json.loads(_eutils(f"{EUTILS}/esummary.fcgi?db=pubmed&retmode=json&tool=semasa&id={idlist}", timeout))
    summ = summ.get("result") or {}
    xml = _eutils(f"{EUTILS}/efetch.fcgi?db=pubmed&retmode=xml&tool=semasa&id={idlist}", timeout)
    abstracts = parse_abstracts(xml)
    affils = parse_affiliations(xml) if rivals else {}
    for pmid, label in list(ids.items()):
        if label == "Competitors":
            where = _plain(affils.get(pmid, ""))
            brand = next((lab for lab, names in rivals or [] if any(_plain(n) in where for n in names)), None)
            ids[pmid] = f"Competitor · {brand}" if brand else "Competitors"
    items = []
    for pmid, label in ids.items():
        s = summ.get(pmid) or {}
        title = s.get("title") or ""
        if not title:
            continue
        doi = next((x.get("value") for x in s.get("articleids") or [] if x.get("idtype") == "doi"), "")
        authors = [a.get("name") for a in s.get("authors") or [] if a.get("name")]
        journal = s.get("fulljournalname") or s.get("source") or ""
        when = _pub_date(s.get("sortpubdate") or s.get("epubdate") or s.get("pubdate") or "")
        items.append(_item(title, f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", when, kind="Paper",
                           snippet=abstracts.get(pmid, "")[:ABSTRACT_KEEP], source=f"PubMed · {journal}"[:120],
                           raw={"pmid": pmid, "doi": doi, "journal": journal, "authors": authors[:3],
                                "n_authors": len(authors), "topic": label}))
    return items


def _quote(term: str) -> str:
    from urllib.parse import quote
    return quote(term, safe="")


def _pub_date(s: str) -> date | None:
    m = re.match(r"(20\d{2})/(\d{2})/(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"(20\d{2}) ([A-Za-z]{3})(?: (\d{1,2}))?", s)
    if m and _month(m.group(2)):
        return date(int(m.group(1)), _month(m.group(2)), int(m.group(3) or 1))
    return None


def parse_affiliations(xml: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext(".//PMID") or ""
        if pmid:
            out[pmid] = " | ".join((a.text or "") for a in art.iter("Affiliation"))
    return out


def parse_abstracts(xml: str) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return out
    for art in root.iter("PubmedArticle"):
        pmid = art.findtext(".//PMID") or ""
        parts = []
        for ab in art.iter("AbstractText"):
            label = ab.get("Label")
            text = "".join(ab.itertext()).strip()
            if text:
                parts.append(f"{label}: {text}" if label else text)
        if pmid:
            out[pmid] = " ".join(parts)
    return out


# --- the writer's reading --------------------------------------------------------------------------------------------

SYSTEM = """You screen regulatory notices and new scientific papers for ws.regulab, a Malaysian regulatory consultancy
(cosmetics, halal, food, pharmaceuticals; clients are Malaysian SMEs; Malaysia and ASEAN first, then the EU/UK and
China). For each item decide:
- "relevant": true when it matters to a Malaysian cosmetics, halal, food or pharmaceutical business or to the people
  who advise them. That includes food recalls and allergen alerts abroad (they show what an importer or exporter
  faces), JAKIM statements on halal, products or viral claims, and papers on cosmetic science, cosmetic safety,
  dermatology or a derma brand's own research. False for ceremonies, staff news, courtesy visits, vaccines-only or
  medical-device-only matters, and JAKIM's purely religious-administration notices (marriage courses, mosque or Quran
  administration, staff training).
- "domain": one of kosmetik, makanan, halal_my, farmaseutikal, fatwa, sains_kosmetik (a cosmetic-science paper),
  kajian_kes (an enforcement case on a cosmetic product), lain.
- "summary": two sentences in Malaysian Malay (never Bahasa Indonesia) saying what it is, using ONLY the title and
  snippet given. No fact that is not there.
- "why": one sentence in Malaysian Malay: what a Malaysian business should know or do because of it.
Answer with ONE JSON object: {"items": [{"i": 0, "relevant": true, "domain": "...", "summary": "...", "why": "..."}]}"""


def annotate(llm: Any, rows: list[dict[str, Any]], batch: int = 10) -> None:
    """Fill summary, why, domain and relevant in place. A row the writer does not answer keeps its own snippet and is
    shown, marked as not read."""
    if not llm or not getattr(llm, "configured", False):
        return
    for start in range(0, len(rows), batch):
        chunk = rows[start:start + batch]
        user = "Items:\n" + "\n".join(json.dumps({"i": start + k, "source": r["source"], "title": r["title"],
                                                   "snippet": (r.get("summary") or "")[:700]}, ensure_ascii=False)
                                        for k, r in enumerate(chunk))
        out = llm.chat_json(SYSTEM, user, max_tokens=260 * len(chunk) + 120)
        for ans in (out or {}).get("items") or []:
            try:
                i = int(ans.get("i"))
            except (TypeError, ValueError, AttributeError):
                continue
            if not start <= i < start + len(chunk) or not str(ans.get("summary") or "").strip():
                continue
            r = rows[i]
            r["summary"] = str(ans["summary"]).strip()[:SUMMARY_KEEP]
            r["why"] = str(ans.get("why") or "").strip()[:WHY_KEEP] or None
            dom = str(ans.get("domain") or "").strip().lower()
            r["domain"] = dom if dom in DOMAINS else r.get("domain")
            r["relevant"] = bool(ans.get("relevant", True))
            r["summary_source"] = "llm"


# --- one sweep --------------------------------------------------------------------------------------------------------

def collect(timeout: int = 30, today: date | None = None,
            competitors: Any = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    today = today or datetime.now(UTC).date()
    rows, report = [], []
    for src in SOURCES:
        try:
            got = src.parse(_get(src.url, timeout), src.url, today)
            fresh = [g for g in got if g["published_at"] and today - g["published_at"] <= MAX_AGE
                     and g["published_at"] <= today + timedelta(days=1)][:PER_SOURCE]
            for g in fresh:
                rows.append({"section": src.section, "source": src.name, "country": src.country, "lang": src.lang, **g})
            report.append({"name": src.name, "ok": True, "items": len(fresh), "error": None})
        except Exception as exc:  # noqa: BLE001 - one dead page must not end the sweep
            report.append({"name": src.name, "ok": False, "items": 0, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    found, rep = pubmed(timeout, competitors)
    rows += [{"section": "publication", "country": "", "lang": "en", "domain": "sains_kosmetik", **p} for p in found]
    report += rep
    return rows, report


def to_row(r: dict[str, Any]) -> dict[str, Any]:
    when = r.get("published_at")
    raw = {k: v for k, v in (r.get("raw") or {}).items() if v not in (None, "", [])}
    if r["section"] == "publication" and r.get("snippet"):
        raw.setdefault("abstract", r["snippet"])          # the Malay summary replaces it; an idea needs the paper's words
    if raw.get("abstract"):
        raw["abstract"] = str(raw["abstract"])[:ABSTRACT_KEEP]
    if raw.get("final_url") == r.get("url"):
        raw.pop("final_url")
    return {"section": r["section"], "source": r.get("source") or "", "title": r["title"], "url": r["url"],
            "summary": (r.get("summary") or r.get("snippet") or "")[:SUMMARY_KEEP] or None, "why": r.get("why"),
            "domain": r.get("domain"),
            "relevant": r.get("relevant", True), "kind": r.get("kind"), "country": r.get("country") or None,
            "lang": r.get("lang") or "en",
            "summary_source": r.get("summary_source") or ("source" if r.get("snippet") else "none"),
            "published_at": when.isoformat() if isinstance(when, date) else when, "raw": raw}


def compact(store: Any, now: datetime | None = None) -> None:
    """Prune by age (each kind after its own window) and shrink hidden or not-relevant items to a marker: the link and
    title stay, so tomorrow's sweep still knows it has seen them and does not add them again."""
    now = now or datetime.now(UTC)
    iso = lambda d: (now - d).isoformat()  # noqa: E731
    t = store.table
    t(WATCH).delete().eq("section", "regulatory").eq("pasted", False).lt("created_at", iso(KEEP)).execute()
    t(WATCH).delete().eq("section", "publication").eq("pasted", False).lt("created_at", iso(KEEP_PAPERS)).execute()
    t(WATCH).delete().eq("pasted", True).lt("created_at", iso(KEEP_PASTED)).execute()
    blank = {"summary": None, "why": None, "raw": {}}
    # a window of four days rather than "everything older": each row is shrunk on a run or two, not rewritten daily
    for flag, value in (("dismissed", True), ("relevant", False)):
        t(WATCH).update(blank).eq(flag, value).eq("pasted", False) \
            .lt("created_at", iso(TOMBSTONE_AFTER)).gt("created_at", iso(TOMBSTONE_AFTER + timedelta(days=4))).execute()


def sweep(store: Any, llm: Any, timeout: int = 30, competitors: Any = None) -> dict[str, Any]:
    rows, report = collect(timeout, competitors=competitors)
    urls = [r["url"] for r in rows]
    have: set[str] = set()
    for i in range(0, len(urls), 100):
        have |= {x["url"] for x in (store.table(WATCH).select("url").in_("url", urls[i:i + 100]).execute().data or [])}
    new = [r for r in rows if r["url"] not in have]
    for r in new:
        r.setdefault("summary", r.get("snippet"))
    annotate(llm, new)
    written = 0
    for i in range(0, len(new), 100):
        res = store.table(WATCH).upsert([to_row(r) for r in new[i:i + 100]], on_conflict="url", ignore_duplicates=True).execute()
        written += len(res.data or [])
    try:
        compact(store)
    except Exception as exc:  # noqa: BLE001 - retention never fails the sweep
        log.warning("could not compact %s: %s", WATCH, exc)
    by = {s: sum(1 for r in new if r["section"] == s) for s in ("regulatory", "publication")}
    log.info("watch: %d read, %d new (regulatory %d, publication %d), %d written", len(rows), len(new),
             by["regulatory"], by["publication"], written)
    return {"read": len(rows), "new": len(new), "written": written, "by_section": by, "sources": report}


def run_if_due(store: Any, llm: Any, *, timeout: int = 30, now: datetime | None = None, only_forced: bool = False) -> str:
    """Sweep when 23 hours have passed since the last sweep, or the page asked for one now. The media worker passes
    only_forced (it runs often and answers the page's "sweep now"); the scrape keeps the daily clock. Never raises: a
    missing table (012 not run yet) is a line in the run's summary."""
    now = now or datetime.now(UTC)
    try:
        rows = store.table(db.SETTINGS).select("key,value,updated_at").eq("key", KEY).execute().data or []
        if not rows:
            store.table(db.SETTINGS).insert({"key": KEY, "value": {}}).execute()
            rows = store.table(db.SETTINGS).select("key,value,updated_at").eq("key", KEY).execute().data or []
        row = rows[0]
        value = dict(row.get("value") or {})
        last = _parse_iso(value.get("last_run"))
        if only_forced and not value.get("force"):
            return ""
        if not value.get("force") and last and now - last < EVERY:
            return f"Regulatory/publication: next sweep after {(last + EVERY).strftime('%Y-%m-%d %H:%M')} UTC"
        claim = store.table(db.SETTINGS).update({"value": {**value, "running_at": now.isoformat()}}).eq("key", KEY)
        if row.get("updated_at"):
            claim = claim.eq("updated_at", row["updated_at"])
        if not (claim.execute().data or []):
            return "Regulatory/publication: another run is sweeping"
    except Exception as exc:  # noqa: BLE001
        return f"Regulatory/publication: not set up ({str(exc)[:120]}); run supabase/012_watch.sql"
    try:
        result = sweep(store, llm, timeout, competitors=value.get("competitors"))
        note = (f"Regulatory/publication: {result['new']} new "
                f"(regulatory {result['by_section']['regulatory']}, publication {result['by_section']['publication']})")
        failed = [s for s in result["sources"] if not s["ok"]]
        if failed:
            note += "; failed: " + ", ".join(f"{s['name']} ({s['error']})" for s in failed)
    except Exception as exc:  # noqa: BLE001
        result, note = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}, f"Regulatory/publication: sweep failed: {exc}"
    fresh = dict((store.table(db.SETTINGS).select("value").eq("key", KEY).execute().data or [{}])[0].get("value") or {})
    fresh.update(last_run=now.isoformat(), force=False, running_at=None, result={**result, "at": now.isoformat()})
    store.table(db.SETTINGS).update({"value": fresh}).eq("key", KEY).execute()
    try:
        db.log_event(store, "info", "scrape", "watch.sweep", note[:200], detail={"new": result.get("new")})
    except Exception:  # noqa: BLE001
        pass
    log.info(note)
    return note


def _parse_iso(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


# --- a link Wan pastes ---------------------------------------------------------------------------------------------
# Wan, 26 Sep 2026: "for regulatory and latest publication, allow us to paste the link as well". The page inserts a
# row with status 'pending' (supabase/013_watch_paste.sql); the worker reads the link, fills the row like a swept one
# and marks it 'ready'. A pasted item is always shown: Wan chose it, so the writer's "relevant" verdict does not hide it.

PASTE_ATTEMPTS = 3
PASTE_STALE = timedelta(minutes=30)
# who issued a pasted page, by its host (most specific first): named and cited like the swept regulators
HOSTS: tuple[tuple[str, str, str], ...] = (
    ("npra.gov.my", "NPRA", "MY"), ("pharmacy.moh.gov.my", "KKM · Bahagian Farmasi", "MY"),
    ("fsq.moh.gov.my", "KKM · BKKM", "MY"), ("moh.gov.my", "KKM", "MY"), ("halal.gov.my", "Portal Halal Malaysia", "MY"),
    ("islam.gov.my", "JAKIM", "MY"), ("jakim.gov.my", "JAKIM", "MY"), ("e-fatwa.gov.my", "e-Fatwa", "MY"),
    ("hsa.gov.sg", "HSA Singapore", "SG"), ("sfa.gov.sg", "SFA Singapore", "SG"), ("asean.org", "ASEAN", ""),
    ("eur-lex.europa.eu", "EUR-Lex", "EU"), ("echa.europa.eu", "ECHA", "EU"), ("efsa.europa.eu", "EFSA", "EU"),
    ("ec.europa.eu", "European Commission", "EU"), ("legislation.gov.uk", "legislation.gov.uk", "UK"),
    ("gov.uk", "UK Government", "UK"), ("nmpa.gov.cn", "China NMPA", "CN"), ("fda.gov", "US FDA", "US"),
    ("tga.gov.au", "TGA Australia", "AU"), ("mfds.go.kr", "MFDS Korea", "KR"), ("mhlw.go.jp", "MHLW Japan", "JP"),
    ("epingalert.org", "WTO ePing", ""), ("who.int", "WHO", ""),
)
PMID_RE = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|ncbi\.nlm\.nih\.gov/pubmed/)(\d{1,9})\b")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s?#\"'<>]+)")


class PasteError(RuntimeError):
    """Final for the row: the message is shown on the page."""


def issuer_of(url: str) -> tuple[str, str] | None:
    u = urlparse(url)
    host = u.netloc.lower().split(":")[0]
    if host == "sites.google.com" and u.path.lower().startswith("/islam.gov.my"):
        return "JAKIM", "MY"                             # JAKIM's own Isu-Isu Tular Halal pages live on Google Sites
    for suffix, name, country in HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return name, country
    return None


def pdf_text(data: bytes, limit: int = 6000) -> tuple[str, str]:
    """(title, text) of a PDF: its own title if it has one, else the first line that reads like one."""
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:8]:
        parts.append(page.extract_text() or "")
        if sum(map(len, parts)) > limit:
            break
    text = re.sub(r"[ \t]+", " ", "\n".join(parts)).strip()
    title = str((reader.metadata or {}).get("/Title") or "").strip()
    if not title or len(title) < 8 or title.lower().startswith(("microsoft", "untitled")):
        title = next((ln.strip() for ln in text.splitlines() if len(ln.strip()) > 15), "")
    return title[:500], text[:limit]


def read_page(url: str, timeout: int = 30) -> dict[str, Any]:
    """Any other link: a regulator's page or PDF, or a journal's page (its citation_* tags name the paper)."""
    import requests
    try:
        r = fetch.get(url, timeout=timeout, retries=1)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        raise PasteError(f"the site refused GitHub's machine ({code}). For a paper, paste its PubMed link or DOI instead; "
                         "for a notice, paste the PDF link, or make the idea by hand in the Idea tab") from exc
    except requests.RequestException as exc:
        raise PasteError(f"could not open the link: {type(exc).__name__}: {str(exc)[:200]}") from exc
    final = r.url or url
    ctype = (r.headers.get("content-type") or "").lower()
    if "pdf" in ctype or r.content[:5] == b"%PDF-" or final.lower().split("?")[0].endswith(".pdf"):
        try:
            title, text = pdf_text(r.content)
        except Exception as exc:  # noqa: BLE001
            raise PasteError(f"the PDF could not be read: {type(exc).__name__}: {str(exc)[:160]}") from exc
        if not text:
            raise PasteError("the PDF has no text layer (a scan): make the idea by hand in the Idea tab")
        return {"title": title or final.rsplit("/", 1)[-1], "snippet": text[:1500], "published_at": date_in_words(text[:3000]),
                "kind": "PDF", "raw": {"final_url": final}}
    soup = BeautifulSoup(r.text, "lxml")

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"name": n}) or soup.find("meta", attrs={"property": n})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    authors = [str(t["content"]).strip() for t in soup.find_all("meta", attrs={"name": "citation_author"}) if t.get("content")]
    title = meta("citation_title", "og:title", "twitter:title", "dc.title") \
        or (soup.title.get_text(strip=True) if soup.title else "")
    when_raw = meta("citation_publication_date", "citation_online_date", "citation_date", "article:published_time",
                    "dc.date", "date")
    when = _any_date(when_raw)
    for bad in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        bad.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in root.find_all(["p", "li", "td"])]
    text = "\n".join(p for p in paras if len(p) > 50)
    abstract = meta("citation_abstract", "dc.description", "description", "og:description")
    snippet = (abstract + "\n" + text).strip() if abstract else text
    if not title and not snippet:
        raise PasteError("the page had no title and no readable text (it may need a browser)")
    item: dict[str, Any] = {"title": title or final, "snippet": snippet[:1500],
                            "published_at": when or date_in_words(text[:3000]),
                            "kind": "Paper" if meta("citation_journal_title", "citation_doi") else "Notice",
                            "raw": {"final_url": final}}
    if meta("citation_journal_title", "citation_doi"):
        item["raw"].update(journal=meta("citation_journal_title"), doi=meta("citation_doi"), authors=authors[:3],
                           n_authors=len(authors), abstract=abstract[:ABSTRACT_KEEP] if abstract else "")
    return item


def _any_date(s: str) -> date | None:
    m = re.match(r"(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", s or "")
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3) or 1))
        except ValueError:
            return None
    return date_in_words(s or "")


def pmid_for_doi(doi: str, timeout: int = 30) -> str | None:
    q = json.loads(_eutils(f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&tool=semasa&term={_quote(doi + '[doi]')}", timeout))
    ids = (q.get("esearchresult") or {}).get("idlist") or []
    return ids[0] if len(ids) == 1 else None


def resolve(row: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    """A pasted row → the fields a swept row carries (title, source, kind, date, snippet, raw)."""
    url = str(row.get("url") or "").strip()
    if not re.match(r"https?://", url):
        raise PasteError("not a web link (it must start with http:// or https://)")
    m = PMID_RE.search(url)
    doi = None if m else (DOI_RE.search(url) or [None, None])[1]
    pmid = m.group(1) if m else (pmid_for_doi(doi.rstrip(".,;)"), timeout) if doi else None)
    if pmid:
        got = papers({pmid: "pasted"}, timeout)
        if not got:
            raise PasteError(f"PubMed has no record {pmid}")
        p = got[0]
        return {**p, "raw": {**p["raw"], "abstract": p.get("snippet") or ""}, "country": "", "lang": "en"}
    page = read_page(url, timeout)
    who = issuer_of(page["raw"].get("final_url") or url) or issuer_of(url)
    raw = page["raw"]
    if page["kind"] == "Paper":
        source = f"Paper · {raw.get('journal') or urlparse(url).netloc}"[:120]
    else:
        source = who[0] if who else urlparse(url).netloc.removeprefix("www.")
    return {**page, "source": source, "country": (who[1] if who else "") or None, "lang": "en",
            "domain": "sains_kosmetik" if row.get("section") == "publication" else None}


def process_pasted(store: Any, llm: Any, *, timeout: int = 30, limit: int = 10, now: datetime | None = None) -> str:
    """Read every link waiting in semasa_watch. Never raises: a missing column (013 not run) is a line in the summary."""
    now = now or datetime.now(UTC)
    try:
        store.table(WATCH).update({"status": "pending"}).eq("status", "working") \
            .lt("claimed_at", (now - PASTE_STALE).isoformat()).lt("attempts", PASTE_ATTEMPTS).execute()
        rows = store.table(WATCH).select("*").eq("status", "pending").order("created_at").limit(limit).execute().data or []
    except Exception as exc:  # noqa: BLE001
        return f"Pasted links: not set up ({str(exc)[:120]}); run supabase/013_watch_paste.sql"
    done = failed = 0
    for row in rows:
        claim = store.table(WATCH).update({"status": "working", "attempts": int(row.get("attempts") or 0) + 1,
                                           "claimed_at": now.isoformat()}).eq("id", row["id"]).eq("status", "pending").execute()
        if not (claim.data or []):
            continue                                        # another run took it
        try:
            item = resolve(row, timeout)
            item["summary"] = item.get("snippet")
            annotate(llm, [item])
            fields = to_row({**row, **item, "section": row["section"], "url": row["url"]})
            if (row.get("title") or "") not in ("", row["url"]):
                fields["title"] = row["title"]              # Wan named it himself
            fields.update(relevant=True, status="ready", error=None)
            fields.pop("url", None)
            store.table(WATCH).update(fields).eq("id", row["id"]).execute()
            done += 1
        except Exception as exc:  # noqa: BLE001 - one bad link must not stop the others
            msg = str(exc) if isinstance(exc, PasteError) else f"{type(exc).__name__}: {str(exc)[:300]}"
            store.table(WATCH).update({"status": "error", "error": msg[:500]}).eq("id", row["id"]).execute()
            failed += 1
            log.warning("pasted link %s: %s", row.get("url"), msg)
    if not rows:
        return ""
    note = f"Pasted links: {done} read" + (f", {failed} failed" if failed else "")
    try:
        db.log_event(store, "info" if not failed else "warn", "scrape", "watch.paste", note)
    except Exception:  # noqa: BLE001
        pass
    return note


ISSUERS = {s.name for s in SOURCES} | {name for _, name, _ in HOSTS}


def is_issuer(name: str | None) -> bool:
    """An idea taken from a regulator's own page or a paper: the issuer is the source to cite, not a portal to hide."""
    n = str(name or "")
    return n in ISSUERS or n.startswith(("PubMed ·", "Paper ·"))
