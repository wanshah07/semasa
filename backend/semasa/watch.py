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

import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import db, fetch
from .log import get_logger
from .sources import Source, clean_title, parse_rss

log = get_logger("semasa.watch")

WATCH = "semasa_watch"
KEY = "watch"                       # semasa_settings row: last run, the page's "sweep now", the last report
EVERY = timedelta(hours=23)         # the scrape runs every 8 h; the first run after 23 h does the daily sweep
MAX_AGE = timedelta(days=45)        # a notice older than this on its own page is not "latest"
KEEP = timedelta(days=45)
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
)


# --- PubMed ----------------------------------------------------------------------------------------------------------

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_QUERIES: tuple[tuple[str, str], ...] = (
    # the key word in the TITLE: in an abstract "cosmetic" is mostly surgery ("a good cosmetic outcome")
    ("Cosmetic science", '(cosmetic*[ti] OR cosmeceutical*[ti] OR sunscreen*[ti] OR "skin care"[ti] OR skincare[ti] '
                         'OR "personal care"[ti] OR "hair dye*"[ti]) NOT (surg*[ti] OR surgical[tiab] OR implant*[ti])'),
    ("Dermatology for consumers", '(topical[ti] OR moisturi*[ti] OR emollient*[ti] OR "skin barrier"[ti]) AND '
                                  '(atopic OR acne OR rosacea OR hyperpigmentation OR melasma OR photoaging OR "skin barrier")'),
    ("Halal science", '(halal[tiab] OR "pork adulteration"[tiab] OR (porcine[ti] AND (gelatin* OR adulterat* OR '
                      'authenticat* OR "species identification")) OR (gelatin*[ti] AND (source OR species OR authenticat*)))'),
    ("Cosmetic contaminants", '("skin lightening"[tiab] OR "skin whitening"[tiab] OR cosmetic*[ti]) AND '
                              '(mercury OR hydroquinone OR "heavy metal*" OR PFAS OR benzene OR lead[ti] OR arsenic OR '
                              '"steroid*")'),
)


def _get(url: str, timeout: int) -> str:
    return fetch.get(url, timeout=timeout).text           # fetch.get carries a browser identity itself


def pubmed(timeout: int = 30, days: int = 14, per_query: int = 12) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(items, report) — the papers entered in PubMed in the last `days`, one search per topic, with abstracts."""
    ids: dict[str, str] = {}
    report = []
    for label, term in PUBMED_QUERIES:
        try:
            q = json.loads(_get(f"{EUTILS}/esearch.fcgi?db=pubmed&retmode=json&sort=date&datetype=edat&reldate={days}"
                                f"&retmax={per_query}&tool=semasa&term={_quote(term)}", timeout))
            got = (q.get("esearchresult") or {}).get("idlist") or []
            for i in got:
                ids.setdefault(i, label)
            report.append({"name": f"PubMed · {label}", "ok": True, "items": len(got), "error": None})
        except Exception as exc:  # noqa: BLE001 - one topic failing must not end the sweep
            report.append({"name": f"PubMed · {label}", "ok": False, "items": 0,
                           "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    if not ids:
        return [], report
    idlist = ",".join(ids)
    summ = json.loads(_get(f"{EUTILS}/esummary.fcgi?db=pubmed&retmode=json&tool=semasa&id={idlist}", timeout)).get("result") or {}
    abstracts = parse_abstracts(_get(f"{EUTILS}/efetch.fcgi?db=pubmed&retmode=xml&tool=semasa&id={idlist}", timeout))
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
                           snippet=abstracts.get(pmid, "")[:1500], source=f"PubMed · {journal}"[:120],
                           raw={"pmid": pmid, "doi": doi, "journal": journal, "authors": authors[:6],
                                "topic": label, "pubdate": s.get("pubdate")}))
    return items, report


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
  who advise them; false for ceremonies, staff news, courtesy visits, vaccines-only or medical-device-only matters.
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
            r["summary"] = str(ans["summary"]).strip()[:700]
            r["why"] = str(ans.get("why") or "").strip()[:400] or None
            dom = str(ans.get("domain") or "").strip().lower()
            r["domain"] = dom if dom in DOMAINS else r.get("domain")
            r["relevant"] = bool(ans.get("relevant", True))
            r["summary_source"] = "llm"


# --- one sweep --------------------------------------------------------------------------------------------------------

def collect(timeout: int = 30, today: date | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
    papers, rep = pubmed(timeout)
    rows += [{"section": "publication", "country": "", "lang": "en", "domain": "sains_kosmetik", **p} for p in papers]
    report += rep
    return rows, report


def to_row(r: dict[str, Any]) -> dict[str, Any]:
    when = r.get("published_at")
    raw = dict(r.get("raw") or {})
    if r["section"] == "publication" and r.get("snippet"):
        raw.setdefault("abstract", r["snippet"])          # the Malay summary replaces it; an idea needs the paper's words
    return {"section": r["section"], "source": r.get("source") or "", "title": r["title"], "url": r["url"],
            "summary": r.get("summary") or r.get("snippet") or None, "why": r.get("why"), "domain": r.get("domain"),
            "relevant": r.get("relevant", True), "kind": r.get("kind"), "country": r.get("country") or None,
            "lang": r.get("lang") or "en",
            "summary_source": r.get("summary_source") or ("source" if r.get("snippet") else "none"),
            "published_at": when.isoformat() if isinstance(when, date) else when, "raw": raw}


def sweep(store: Any, llm: Any, timeout: int = 30) -> dict[str, Any]:
    rows, report = collect(timeout)
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
        store.table(WATCH).delete().lt("created_at", (datetime.now(UTC) - KEEP).isoformat()).execute()
    except Exception as exc:  # noqa: BLE001 - retention never fails the sweep
        log.warning("could not prune %s: %s", WATCH, exc)
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
        result = sweep(store, llm, timeout)
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


ISSUERS = {s.name for s in SOURCES}


def is_issuer(name: str | None) -> bool:
    """An idea taken from a regulator's own page: the regulator is the source to cite, not a portal to hide."""
    n = str(name or "")
    return n in ISSUERS or n.startswith("PubMed ·")
