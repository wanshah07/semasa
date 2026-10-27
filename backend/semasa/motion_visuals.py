"""Seven more styles that put the facts on screen as a picture (Wan, 27 Oct 2026: "make sure add map, figure, chart, keratan
akhbar if applicable to make the motion video interesting besides add at least 25 styles in the video").

Each is drawn from what a scene already says, or from the idea's own source, and nothing else: a place the scene names is a
country on an outline map, a percentage is a ring and a row of people, a ratio ("3 daripada 10") is ten figures with three filled,
years with figures are a line, lines with figures are columns, a date is a calendar tile, and the headline of a news source is a
newspaper clipping with the outlet's own name. A scene whose words carry none of these gets none of these: a picture of data that
is not there would be an invented proof, which no Semasa film may show.

  G01 map        G02 people pictogram   G03 donut gauge   G04 trend line
  G05 columns    G06 news clipping      G07 calendar date

Like the concept diagrams (motion_concepts.py), each is one normal-flow block of the scene's column, with a height the layout
budgets, so nothing can cross the words around it, and every word on it is set in 44px or more at 1080 wide.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, NamedTuple

from . import compliance
from .motion_concepts import Block, esc, host_of, whole

GEO_PATH = Path(__file__).resolve().parents[2] / "rules" / "motion" / "geo.json"

NAMES = {"G01": "Map Locator", "G02": "People Pictogram", "G03": "Donut Gauge", "G04": "Trend Line", "G05": "Column Chart",
         "G06": "News Clipping (Keratan Akhbar)", "G07": "Calendar Date"}
# id: (roles, needs, recipe) in motion_auto's shape. Needs: G a place the scene names, R a percentage or a ratio, Y years with
# figures, K two or more lines with figures, J a news source for the idea, Z a date
RECIPES: dict[str, tuple[str, str, str]] = {
    "G01": ("hfws", "G", "an outline map with the countries the scene names filled in and numbered pins (the "
    "places are the scene's own words)"),
    "G02": ("fws", "R", "a row of people with as many filled as the ratio or the percentage says"),
    "G03": ("fws", "R", "a ring that fills to the percentage, the number counting up in its middle"),
    "G04": ("fws", "Y", "a line through the years and figures the scene prints, a point and a figure for each year"),
    "G05": ("fws", "K", "columns as tall as the figures in the lines, each with its own label"),
    "G06": ("hf", "J", "a newspaper clipping: the outlet's name and the news item's own headline (only when the "
    "idea came from a news page)"),
    "G07": ("hfws", "Z", "a calendar tile for each date the scene names, the day large"),
}
CODES = set(NAMES)


# --- what the words carry ------------------------------------------------------------------------------------------------

# iso3: (English name, Malay name, the words that name it)
PLACES: dict[str, tuple[str, str, str]] = {
    "MYS": ("Malaysia", "Malaysia", r"Malaysia"), "SGP": ("Singapore", "Singapura", r"Singapore|Singapura"),
    "IDN": ("Indonesia", "Indonesia", r"Indonesia"), "THA": ("Thailand", "Thailand", r"Thailand"),
    "VNM": ("Vietnam", "Vietnam", r"Vietnam|Viet Nam"), "PHL": ("Philippines", "Filipina", r"Philippines|Filipina"),
    "BRN": ("Brunei", "Brunei", r"Brunei"), "KHM": ("Cambodia", "Kemboja", r"Cambodia|Kemboja"), "LAO": ("Laos", "Laos", r"Laos"),
    "MMR": ("Myanmar", "Myanmar", r"Myanmar|Burma"), "CHN": ("China", "China", r"China|Cina"),
    "JPN": ("Japan", "Jepun", r"Japan|Jepun"), "KOR": ("South Korea", "Korea Selatan", r"South Korea|Korea Selatan|Korea"),
    "IND": ("India", "India", r"India"), "AUS": ("Australia", "Australia", r"Australia"),
    "NZL": ("New Zealand", "New Zealand", r"New Zealand"),
    "GBR": ("United Kingdom", "United Kingdom", r"UK|United Kingdom|Britain|England"),
    "USA": ("United States", "Amerika Syarikat", r"USA|US|United States|Amerika Syarikat|America"),
    "CAN": ("Canada", "Kanada", r"Canada|Kanada"), "DEU": ("Germany", "Jerman", r"Germany|Jerman"),
    "FRA": ("France", "Perancis", r"France|Perancis"), "ITA": ("Italy", "Itali", r"Italy|Itali"),
    "ESP": ("Spain", "Sepanyol", r"Spain|Sepanyol"), "NLD": ("Netherlands", "Belanda", r"Netherlands|Belanda"),
    "CHE": ("Switzerland", "Switzerland", r"Switzerland"), "SWE": ("Sweden", "Sweden", r"Sweden"),
    "DNK": ("Denmark", "Denmark", r"Denmark"), "NOR": ("Norway", "Norway", r"Norway"), "IRL": ("Ireland", "Ireland", r"Ireland"),
    "RUS": ("Russia", "Rusia", r"Russia|Rusia"), "TUR": ("Turkey", "Turki", r"Turkey|Turki"),
    "SAU": ("Saudi Arabia", "Arab Saudi", r"Saudi Arabia|Arab Saudi"), "ARE": ("UAE", "UAE", r"UAE|United Arab Emirates|Emiriah"),
    "EGY": ("Egypt", "Mesir", r"Egypt|Mesir"), "PAK": ("Pakistan", "Pakistan", r"Pakistan"),
    "BGD": ("Bangladesh", "Bangladesh", r"Bangladesh"), "LKA": ("Sri Lanka", "Sri Lanka", r"Sri Lanka"),
    "BRA": ("Brazil", "Brazil", r"Brazil"), "MEX": ("Mexico", "Mexico", r"Mexico"), "ZAF": ("South Africa", "Afrika Selatan",
                                                                                              r"South Africa|Afrika Selatan"),
    "TWN": ("Taiwan", "Taiwan", r"Taiwan"), "HKG": ("Hong Kong", "Hong Kong", r"Hong Kong"), "TLS": ("Timor-Leste", "Timor-Leste",
                                                                                                      r"Timor-Leste|Timor Leste"),
}
ASEAN = ("BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "VNM")
EU27 = ("AUT", "BEL", "BGR", "HRV", "CYP", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "IRL", "ITA", "LVA", "LTU",
        "LUX", "MLT", "NLD", "POL", "PRT", "ROU", "SVK", "SVN", "ESP", "SWE")
# a group: (the words, English label, Malay label, members). Short capitals are read case-sensitively, so "eu" is not the EU
GROUPS = {
    "ASEAN": (r"ASEAN", "ASEAN", "ASEAN", ASEAN),
    "SEA": (r"Southeast Asia|South-East Asia|South East Asia|Asia Tenggara", "Southeast Asia", "Asia Tenggara", (*ASEAN, "TLS")),
    "EU": (r"EU|European Union|Kesatuan Eropah|Eropah|Europe", "EU", "EU", EU27),
}
CASE_SENSITIVE = {"UK", "US", "USA", "UAE", "EU", "ASEAN"}
# where a pin sits when the country's own label point (a place inside its biggest piece) is not where a viewer looks
PIN = {"MYS": (101.9, 4.0), "IDN": (113.5, -1.2), "PHL": (122.0, 12.5), "JPN": (138.0, 36.0), "VNM": (107.0, 15.0),
       "THA": (101.0, 15.5), "MMR": (96.0, 21.0), "LAO": (103.5, 19.0), "KHM": (104.9, 12.6), "AUS": (134.0, -25.0),
       "IND": (79.0, 22.0), "CHN": (104.0, 35.0), "USA": (-98.0, 39.0), "RUS": (90.0, 60.0), "CAN": (-100.0, 58.0),
       "BRA": (-52.0, -10.0), "NOR": (9.0, 61.0), "SWE": (16.0, 62.0), "GBR": (-2.0, 53.0), "FRA": (2.5, 46.7),
       "KOR": (127.8, 36.5), "SAU": (45.0, 24.0), "TUR": (35.0, 39.0), "ZAF": (24.0, -29.0)}


def _word(pattern: str) -> re.Pattern[str]:
    parts = pattern.split("|")
    flags = 0 if all(p in CASE_SENSITIVE for p in parts) else re.I
    return re.compile(r"(?<![A-Za-z])(?:" + pattern + r")(?![A-Za-z])", flags)


_PLACE_RX = {iso: _word(words) for iso, (_, _, words) in PLACES.items()}
_GROUP_RX = {key: _word(words) for key, (words, *_rest) in GROUPS.items()}


def places_in(text: str) -> list[str]:
    """The countries and groups a text names, in the order they first appear: [ISO3 or group key]. A word that is also the name of
    a group (Europe) is a group, and a country the text names that belongs to a group it names too is left to the group."""
    found: list[tuple[int, str]] = []
    for key, rx in _GROUP_RX.items():
        m = rx.search(text)
        if m:
            found.append((m.start(), key))
    for iso, rx in _PLACE_RX.items():
        m = rx.search(text)
        if m:
            found.append((m.start(), iso))
    seen: list[str] = []
    for _, key in sorted(found):
        if key not in seen:
            seen.append(key)
    return seen


def meaningful_places(text: str) -> list[str]:
    """What a map is worth drawing for: two or more places, or one that is not Malaysia, or a group. Malaysia alone is the
    setting of almost every film and says nothing a map could add."""
    places = places_in(text)
    if places == ["MYS"] or not places:
        return []
    return places


PCT = re.compile(r"(\d{1,3}(?:[.,]\d+)?)\s?%")
RATIO = re.compile(r"\b(\d{1,2})\s*(?:daripada|dalam|dari|of|in|out of)\s*(\d{1,2})\b", re.I)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
NUM = re.compile(r"(?<![\w.,])(?:RM|USD|US\$|\$)?\s?\d[\d,.]*\d|(?<![\w.,])(?:RM|USD|US\$|\$)?\s?\d")


def _value(token: str) -> float | None:
    t = re.sub(r"[^\d.,]", "", token)
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"\d{1,3}(?:,\d{3})+", t) else t.replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def label_without(line: str, token: str) -> str:
    return re.sub(r"\s{2,}", " ", line.replace(token, " ")).strip(" :-–—,.;()")


def ratio_in(lines: list[str]) -> tuple[str, float, float] | None:
    """(the line, how many, out of how many) for the first line that says 'x daripada y' (y up to 12) or a percentage: a
    percentage is read as tenths of ten people, so 35% is four of ten (rounded), and the donut shows the exact figure."""
    for ln in lines:
        m = RATIO.search(ln)
        if m and 1 <= int(m.group(1)) < int(m.group(2)) <= 12:
            return ln, float(m.group(1)), float(m.group(2))
    for ln in lines:
        m = PCT.search(ln)
        if m:
            p = float(m.group(1).replace(",", "."))
            if 0 < p <= 100:
                return ln, p, 100.0
    return None


def percent_in(lines: list[str]) -> tuple[str, float, str] | None:
    for ln in lines:
        m = PCT.search(ln)
        if m:
            p = float(m.group(1).replace(",", "."))
            if 0 < p <= 100:
                return ln, p, m.group(0)
    return None


def trend_in(lines: list[str]) -> list[tuple[str, float, str]]:
    """[(year, figure, the figure as printed)] when at least three lines each carry one year and one figure "
    "that is not the year."""
    rows: dict[str, tuple[float, str]] = {}
    for ln in lines:
        years = YEAR.findall(ln)
        if len(set(years)) != 1:
            continue
        rest = ln.replace(years[0], " ")
        for m in NUM.finditer(rest):
            v = _value(m.group(0))
            if v is not None:
                rows[years[0]] = (v, m.group(0).strip())
                break
    pts = sorted((y, v, raw) for y, (v, raw) in rows.items())
    return pts if len(pts) >= 3 else []


def columns_in(lines: list[str]) -> list[tuple[str, float, str, str]]:
    """[(line, figure, the figure as printed, label)] for two to four lines that each carry a figure and a label. A line with a
    percentage or a year is left to the chart and the timeline that already draw those."""
    out = []
    for ln in lines:
        if PCT.search(ln) or YEAR.search(ln):
            continue
        for m in NUM.finditer(ln):
            v = _value(m.group(0))
            label = label_without(ln, m.group(0))
            if v is not None and v > 0 and len(label) >= 3:
                out.append((ln, v, m.group(0).strip(), label))
                break
    return out[:4] if len(out) >= 2 else []


MONTHS = {"jan": 1, "januari": 1, "january": 1, "feb": 2, "februari": 2, "february": 2, "mar": 3, "mac": 3, "march": 3, "apr": 4,
          "april": 4, "mei": 5, "may": 5, "jun": 6, "june": 6, "jul": 7, "julai": 7, "july": 7, "aug": 8, "ogos": 8, "august": 8,
          "sep": 9, "sept": 9, "september": 9, "oct": 10, "okt": 10, "oktober": 10, "october": 10, "nov": 11, "november": 11,
          "dec": 12, "dis": 12, "disember": 12, "december": 12}
MONTH_NAMES = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
                      "November", "December"],
               "bm": ["Januari", "Februari", "Mac", "April", "Mei", "Jun", "Julai", "Ogos", "September", "Oktober", "November",
                      "Disember"]}
_MON = r"(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\.?"
DATE_PATTERNS = (
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + _MON + r",?\s+((?:19|20)\d{2})\b", re.I), ("d", "m", "y")),
    (re.compile(r"\b" + _MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+((?:19|20)\d{2})\b", re.I), ("m", "d", "y")),
    (re.compile(r"\b((?:19|20)\d{2})-(\d{2})-(\d{2})\b"), ("y", "mn", "d")),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/((?:19|20)\d{2})\b"), ("d", "mn", "y")),
    (re.compile(r"\b" + _MON + r"\s+((?:19|20)\d{2})\b", re.I), ("m", "y")),
)


def dates_in(text: str) -> list[tuple[int | None, int, int]]:
    """[(day or None, month 1-12, year)] named in the text, in order of appearance, without repeats. 'Januari 2027' is a month
    with no day; '1/1/2027' is read the Malaysian way, day first."""
    found: list[tuple[int, tuple[int | None, int, int]]] = []
    for rx, parts in DATE_PATTERNS:
        for m in rx.finditer(text):
            got = dict(zip(parts, m.groups(), strict=True))
            month = MONTHS.get(str(got["m"]).lower()) if "m" in got else int(got["mn"])
            day = int(got["d"]) if "d" in got else None
            year = int(got["y"])
            if month and 1 <= month <= 12 and (day is None or 1 <= day <= 31):
                if not any(abs(m.start() - at) < 3 for at, _ in found):
                    found.append((m.start(), (day, month, year)))
    seen: list[tuple[int | None, int, int]] = []
    for _, d in sorted(found):
        if d not in seen:
            seen.append(d)
    return seen[:2]


# --- the news a film can show as a clipping ------------------------------------------------------------------------------

OUTLETS = {"bernama.com": "Bernama", "thestar.com.my": "The Star", "bharian.com.my": "Berita Harian",
           "hmetro.com.my": "Harian Metro",
           "utusan.com.my": "Utusan Malaysia", "freemalaysiatoday.com": "Free Malaysia Today", "malaymail.com": "Malay Mail",
           "nst.com.my": "New Straits Times", "astroawani.com": "Astro Awani", "sinarharian.com.my": "Sinar Harian",
           "theedgemalaysia.com": "The Edge", "malaysiakini.com": "Malaysiakini", "kosmo.com.my": "Kosmo!",
           "reuters.com": "Reuters", "bbc.com": "BBC News", "bbc.co.uk": "BBC News", "cnbc.com": "CNBC", "straitstimes.com":
           "The Straits Times", "channelnewsasia.com": "CNA", "theguardian.com": "The Guardian",
           "nytimes.com": "The New York Times",
           "scmp.com": "South China Morning Post", "aljazeera.com": "Al Jazeera", "bloomberg.com": "Bloomberg"}
# a source that is not a newspaper: an official site, a journal, a video or a forum, or Wan's own files
NOT_NEWS = re.compile(r"(\.gov(\.|$)|\.mil$|europa\.eu|who\.int|efsa|echa|fda\.gov|jakim|halal\.gov|npra|moh\.gov|"
                      r"pubmed|ncbi\.nlm|doi\.org|wiley|sciencedirect|springer|nature\.com|mdpi|elsevier|tandfonline|"
                      r"youtube|youtu\.be|reddit|tiktok|facebook|instagram|x\.com|twitter|onedrive|sharepoint|google\.|"
                      r"wikipedia|github|\.edu)", re.I)


def outlet_of(host: str) -> str:
    h = host.lower()
    for dom, name in OUTLETS.items():
        if h == dom or h.endswith("." + dom):
            return name
    return host


def news_of(row: dict[str, Any], stream: str = "regulab") -> dict[str, str] | None:
    """The news item behind the idea: its own headline and its outlet's name, from the idea's saved source and nothing else. None
    for a paper, an official page, a video, a forum or one of Wan's own files, and on the LinkedIn stream for a blog or a news
    aggregator, which that stream never names (rules/compliance.json `aggregator`)."""
    ev = (row.get("options") or {}).get("evidence") or {}
    url = str(ev.get("source_url") or row.get("source_url") or "")
    title = " ".join(str(ev.get("source_title") or row.get("source_title") or "").split())
    host = host_of(url)
    if not url.startswith(("http://", "https://")) or not host or NOT_NEWS.search(host):
        return None
    if len(title) < 25 or title.startswith("Hook"):
        return None
    outlet = outlet_of(host)
    if stream == "linkedin" and compliance.AGGREGATOR.search(f"{host} {outlet}"):
        return None
    if len(title) > 130:
        title = title[:130].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return {"title": title, "outlet": outlet[:40], "host": host}


# --- the blocks ------------------------------------------------------------------------------------------------------------


class VCtx(NamedTuple):
    scale: float
    box_w: float
    gap: float
    fs: float                                    # the type of every block (54px at 1080 wide)
    pad: float
    text_h: Any
    lang: str
    news: dict[str, str] | None
    accent: str
    rgba: Any
    frame_h: float = 1920.0                      # a short frame (1:1, landscape) gets a shorter map and a compact clipping


@lru_cache(maxsize=1)
def geo() -> dict[str, Any]:
    return json.loads(GEO_PATH.read_text(encoding="utf-8"))["countries"]


def css(c: VCtx) -> list[str]:
    s, fs, pad, accent, rgba = c.scale, c.fs, c.pad, c.accent, c.rgba
    ring = f"{max(3, 4 * s):.0f}px solid {accent}"
    soft = f"{max(2, 3 * s):.0f}px solid {rgba(accent, .45)}"
    return [
        f".gm{{position:relative;flex:none;width:100%;box-sizing:border-box;font-size:{fs:.0f}px;"
        f"line-height:1.22;font-weight:600;}}",
        f".gmap{{position:relative;box-sizing:border-box;width:100%;border:{soft};border-radius:{24 * s:.0f}px;"
        f"background:{rgba(accent, .07)};overflow:hidden;}}",
        ".gmap svg{display:block;width:100%;height:100%;}",
        f".gmap .c0{{fill:{rgba(accent, .14)};stroke:{rgba(accent, .3)};stroke-width:1;vector-effect:non-scaling-stroke;}}",
        f".gmap .c1{{fill:{rgba(accent, .5)};stroke:{accent};stroke-width:1.2;vector-effect:non-scaling-stroke;}}",
        f".gmap .c2{{fill:{accent};stroke:#fff;stroke-width:1.5;vector-effect:non-scaling-stroke;}}",
        f".gpin{{position:absolute;width:{62 * s:.0f}px;height:{62 * s:.0f}px;margin:-{31 * s:.0f}px 0 0 -{31 * s:.0f}px;"
        f"border-radius:50%;background:#fff;border:{ring};color:{accent};font-weight:800;font-size:{46 * s:.0f}px;"
        f"line-height:{54 * s:.0f}px;text-align:center;box-shadow:0 {4 * s:.0f}px {12 * s:.0f}px rgba(0,0,0,.18);}}",
        f".gleg{{display:flex;flex-wrap:wrap;gap:{c.gap * .3:.0f}px {c.gap * .9:.0f}px;margin-top:{c.gap * .4:.0f}px;}}",
        f".gleg span{{display:inline-flex;align-items:center;gap:{12 * s:.0f}px;min-width:0;overflow-wrap:anywhere;}}",
        f".gleg b{{flex:none;display:inline-block;width:{50 * s:.0f}px;height:{50 * s:.0f}px;border-radius:50%;"
        f"background:{accent};"
        f"color:#fff;text-align:center;line-height:{50 * s:.0f}px;font-size:{40 * s:.0f}px;}}",
        f".gleg i{{flex:none;display:inline-block;width:{44 * s:.0f}px;height:{30 * s:.0f}px;border-radius:{8 * s:.0f}px;"
        f"background:{rgba(accent, .5)};border:{max(2, 3 * s):.0f}px solid {accent};}}",
        f".gpic{{display:flex;gap:{max(6, 10 * s):.0f}px;align-items:flex-end;}}",
        ".gpic svg{flex:1;min-width:0;height:auto;}",
        f".gcap{{margin-top:{c.gap * .4:.0f}px;overflow-wrap:anywhere;}}",
        f".gdn{{display:flex;align-items:center;gap:{c.gap:.0f}px;}}",
        ".gdw{position:relative;flex:none;} .gdw svg{display:block;}",
        f".gdw b{{position:absolute;left:0;top:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;"
        f"font-size:{fs * 1.25:.0f}px;font-weight:800;color:{accent};}}",
        ".gdn .gdl{flex:1;min-width:0;overflow-wrap:anywhere;}",
        f".gtr{{border:{soft};border-radius:{24 * s:.0f}px;background:rgba(255,255,255,.7);padding:{pad:.0f}px;}}",
        ".gtr svg{display:block;width:100%;}",
        ".gtr .row{display:flex;} .gtr .row div{flex:1;min-width:0;text-align:center;overflow-wrap:anywhere;}",
        f".gtr .row b{{display:block;color:{accent};}}",
        f".gcol{{display:flex;gap:{c.gap * .5:.0f}px;align-items:flex-end;border-bottom:{ring};padding:0 {pad * .4:.0f}px;}}",
        ".gcol>div{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;}",
        f".gcol .bar{{width:68%;background:{accent};border-radius:{10 * s:.0f}px {10 * s:.0f}px 0 0;transform-origin:50% 100%;}}",
        f".gcol .val{{font-weight:800;color:{accent};margin-bottom:{8 * s:.0f}px;overflow-wrap:anywhere;text-align:center;}}",
        f".gcl{{display:flex;gap:{c.gap * .5:.0f}px;padding:{pad * .4:.0f}px;}} .gcl div{{flex:1;min-width:0;text-align:center;"
        "overflow-wrap:anywhere;}",
        f".gnews{{background:#f6f1e4;color:#1d1a14;border-radius:{6 * s:.0f}px;padding:{pad * 1.1:.0f}px {pad * 1.2:.0f}px;"
        f"box-shadow:0 {6 * s:.0f}px {20 * s:.0f}px rgba(0,0,0,.22);font-family:Georgia,'Times New Roman',serif;"
        f"position:relative;}}",
        f".gnews .mh{{display:flex;justify-content:space-between;align-items:baseline;gap:{c.gap * .6:.0f}px;"
        f"border-bottom:{max(3, 4 * s):.0f}px double #1d1a14;padding-bottom:{10 * s:.0f}px;margin-bottom:{16 * s:.0f}px;}}",
        ".gnews .mh b{font-weight:900;letter-spacing:.02em;text-transform:uppercase;min-width:0;overflow-wrap:anywhere;}",
        f".gnews .mh span{{flex:none;font-style:italic;color:{accent};}}",
        ".gnews h3{margin:0;font-weight:800;line-height:1.16;overflow-wrap:anywhere;}",
        f".gnews .ln{{height:{12 * s:.0f}px;border-radius:{6 * s:.0f}px;background:rgba(29,26,20,.16);"
        f"margin-top:{14 * s:.0f}px;}}",
        f".gnews .tape{{position:absolute;left:50%;top:-{18 * s:.0f}px;width:{170 * s:.0f}px;"
        f"height:{38 * s:.0f}px;margin-left:-{85 * s:.0f}px;"
        "background:rgba(255,236,160,.8);transform:rotate(-2deg);}",
        f".gcal{{display:flex;gap:{c.gap:.0f}px;justify-content:center;}}",
        f".gcal>div{{flex:1;min-width:0;max-width:{c.box_w * .5:.0f}px;border:{ring};"
        f"border-radius:{22 * s:.0f}px;background:#fff;"
        "overflow:hidden;text-align:center;}",
        f".gcal .mo{{background:{accent};color:#fff;font-weight:800;padding:{8 * s:.0f}px {10 * s:.0f}px;"
        f"overflow-wrap:anywhere;}}",
        f".gcal .dy{{font-weight:900;color:{accent};font-size:{fs * 2.3:.0f}px;line-height:1.05;padding:{6 * s:.0f}px 0;}}",
        f".gcal .yr{{padding:0 0 {10 * s:.0f}px;font-weight:700;}}",
    ]


def _fade(uid: str, s: float):
    def tw(at: float) -> list[str]:
        return [f'tl.fromTo("#{uid}",{{opacity:0,y:{26 * s:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out"}},{at:g});']
    return tw


def _project(lon: float, lat: float, cos0: float) -> tuple[float, float]:
    return lon * cos0, -lat


def _main_rings(rings: list[list[list[float]]]) -> list[list[list[float]]]:
    """The pieces of a country that set a map's frame: those not much smaller than the largest (so Alaska counts and a far-off
    island territory does not)."""
    def box_area(r: list[list[float]]) -> float:
        xs, ys = [p[0] for p in r], [p[1] for p in r]
        return (max(xs) - min(xs)) * (max(ys) - min(ys))
    top = max(box_area(r) for r in rings)
    return [r for r in rings if box_area(r) >= top * 0.2]


def map_block(sid: str, c: VCtx, text: str) -> tuple[Block, list[str]] | None:
    places = meaningful_places(text)
    if not places:
        return None
    data = geo()
    s, w = c.scale, c.box_w
    solo = [p for p in places if p in PLACES and p in data][:4]
    groups = [p for p in places if p in GROUPS][:2]
    if not solo and not groups:
        return None
    marked: dict[str, int] = {}                     # iso3 -> 0 context, 1 group member, 2 named
    for g in groups:
        for iso in GROUPS[g][3]:
            if iso in data:
                marked[iso] = 1
    for iso in solo:
        marked[iso] = 2
    # the frame: the main pieces of everything marked, padded, in degrees corrected for latitude
    pts = [p for iso in marked for r in _main_rings(data[iso]["rings"]) for p in r]
    lons, lats = [p[0] for p in pts], [p[1] for p in pts]
    lat0 = (min(lats) + max(lats)) / 2
    cos0 = max(0.35, math.cos(math.radians(lat0)))
    x0, x1 = min(lons) * cos0, max(lons) * cos0
    y0, y1 = -max(lats), -min(lats)
    pad_x, pad_y = max((x1 - x0) * .22, 2.5), max((y1 - y0) * .22, 2.5)
    x0, x1, y0, y1 = x0 - pad_x, x1 + pad_x, y0 - pad_y, y1 + pad_y
    compact = c.frame_h <= w * 1.5
    map_h = min(w * 0.5, c.frame_h * 0.3)
    map_w = w * 0.6 if compact else w
    aspect = map_w / map_h
    vw, vh = x1 - x0, y1 - y0
    if vw / vh < aspect:
        grow = vh * aspect - vw
        x0, x1 = x0 - grow / 2, x1 + grow / 2
    else:
        grow = vw / aspect - vh
        y0, y1 = y0 - grow / 2, y1 + grow / 2
    vw, vh = x1 - x0, y1 - y0
    paths = []
    for iso, rec in data.items():
        rings = []
        for r in rec["rings"]:
            xs = [p[0] * cos0 for p in r]
            ys = [-p[1] for p in r]
            if max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1:
                continue
            rings.append("M" + "L".join(f"{p[0] * cos0:.2f},{-p[1]:.2f}" for p in r) + "Z")
        if rings:
            cls = f"c{marked.get(iso, 0)}"
            paths.append(f'<path class="{cls}{" " + sid + "-hi" if iso in marked else ""}" d="{"".join(rings)}"/>')
    # pins: the named countries, numbered, kept apart so two badges never touch
    pin_px: list[tuple[float, float]] = []
    for iso in solo:
        lon, lat = PIN.get(iso) or tuple(data[iso]["label"])
        px, py = (_project(lon, lat, cos0)[0] - x0) / vw * map_w, (_project(lon, lat, cos0)[1] - y0) / vh * map_h
        pin_px.append((px, py))
    sep, edge = 78 * s, 44 * s
    for _ in range(40):
        moved = False
        for i in range(len(pin_px)):
            for j in range(i + 1, len(pin_px)):
                dx, dy = pin_px[j][0] - pin_px[i][0], pin_px[j][1] - pin_px[i][1]
                d = math.hypot(dx, dy)
                if d < sep:
                    ux, uy = (dx / d, dy / d) if d else (1.0, 0.0)
                    push = (sep - d) / 2 + 1
                    pin_px[i] = (pin_px[i][0] - ux * push, pin_px[i][1] - uy * push)
                    pin_px[j] = (pin_px[j][0] + ux * push, pin_px[j][1] + uy * push)
                    moved = True
        if not moved:
            break
    pin_px = [(min(max(x, edge), map_w - edge), min(max(y, edge), map_h - edge)) for x, y in pin_px]
    pins = "".join(f'<i class="gpin {sid}-pn" style="left:{x:.0f}px;top:{y:.0f}px;">{i + 1}</i>'
                   for i, (x, y) in enumerate(pin_px))
    en = c.lang == "en"
    legend = "".join(f"<span><b>{i + 1}</b>{esc(PLACES[iso][0] if en else PLACES[iso][1])}</span>" for i, iso in enumerate(solo))
    legend += "".join(f"<span><i></i>{esc(GROUPS[g][1] if en else GROUPS[g][2])}</span>" for g in groups)
    names = [PLACES[i][0] if en else PLACES[i][1] for i in solo] + [GROUPS[g][1] if en else GROUPS[g][2] for g in groups]
    if not whole(names, c.fs, (w - c.gap) / 2 - 80 * s):
        return None
    per_row = 1 if compact else 2
    rows = -(-(len(solo) + len(groups)) // per_row)
    legend_h = rows * c.fs * 1.3 + (rows - 1) * c.gap * .3
    h = max(map_h, legend_h) + 10 * s if compact else map_h + c.gap * .4 + legend_h + 10 * s
    uid = f"{sid}-gm"
    side = f" display:flex;gap:{c.gap * .6:.0f}px;align-items:center;" if compact else ""
    leg_style = "flex-direction:column;margin:0;flex:1;min-width:0;" if compact else ""
    html = (f'<div class="gm" id="{uid}" style="{side}">'
            f'<div class="gmap" style="height:{map_h:.0f}px;width:{map_w:.0f}px;flex:none;">'
            f'<svg viewBox="{x0:.2f} {y0:.2f} {vw:.2f} {vh:.2f}" preserveAspectRatio="none">{"".join(paths)}</svg>{pins}</div>'
            f'<div class="gleg" style="{leg_style}">{legend}</div></div>')

    def tw(at: float) -> list[str]:
        out = [*_fade(uid, s)(at),
               f'tl.fromTo(".{sid}-hi.c1,.{sid}-hi.c2",{{opacity:.1}},{{opacity:1,duration:.7,ease:"power2.out"}},{at + .3:g});']
        if pins:
            out.append(f'tl.fromTo(".{sid}-pn",{{opacity:0,scale:.2}},{{opacity:1,scale:1,duration:.4,ease:"back.out(2)",'
                       f'stagger:.25}},{at + .6:g});')
        return out
    return Block(html, h, tw), []


PERSON = ('<svg viewBox="0 0 40 80" class="{k}" aria-hidden="true"><circle cx="20" cy="12" r="10" fill="{f}"/>'
          '<path d="M6 30 Q6 26 12 26 H28 Q34 26 34 30 V54 H28 V78 H21 V56 H19 V78 H12 V54 H6 Z" fill="{f}"/></svg>')


def pictogram_block(sid: str, c: VCtx, lines: list[str]) -> tuple[Block, list[str]] | None:
    got = ratio_in(lines)
    if not got:
        return None
    line, x, y = got
    n = 10 if y == 100.0 else int(y)
    filled = max(1, round(x / 10)) if y == 100.0 else int(x)
    if y == 100.0 and x < 5:
        filled = 1
    s, w = c.scale, c.box_w
    cap = line
    if not whole([cap], c.fs, w):
        return None
    iw = (w - (n - 1) * max(6, 10 * s)) / n
    ih = min(iw * 2, 190 * s)
    h = ih + c.gap * .4 + c.text_h(cap, c.fs, .56, w)
    uid = f"{sid}-gm"
    icons = "".join(PERSON.format(k=f"{sid}-pp", f=(c.accent if i < filled else c.rgba(c.accent, .22))) for i in range(n))
    html = (f'<div class="gm" id="{uid}"><div class="gpic" style="height:{ih:.0f}px;">{icons}</div>'
            f'<div class="gcap">{esc(cap)}</div></div>')

    def tw(at: float) -> list[str]:
        return [*_fade(uid, s)(at),
                f'tl.fromTo(".{sid}-pp",{{opacity:0,y:{30 * s:.0f}}},{{opacity:1,y:0,duration:.35,'
                f'ease:"power2.out",stagger:.09}},'
                f'{at + .3:g});']
    return Block(html, h, tw), [line]


def donut_block(sid: str, c: VCtx, lines: list[str]) -> tuple[Block, list[str]] | None:
    got = percent_in(lines)
    if not got:
        return None
    line, p, token = got
    label = label_without(line, token) or line
    s, w = c.scale, c.box_w
    d = min(w * .36, 330 * s)
    stroke = d * .15
    r = (d - stroke) / 2
    circ = 2 * math.pi * r
    text_w = w - d - c.gap
    if not whole([label], c.fs, text_w) or text_w < c.fs * 3:
        return None
    h = max(d, c.text_h(label, c.fs, .56, text_w)) + 10 * s
    uid = f"{sid}-gm"
    shown = f"{p:g}"
    html = (f'<div class="gm gdn" id="{uid}"><div class="gdw" style="width:{d:.0f}px;height:{d:.0f}px;">'
            f'<svg width="{d:.0f}" height="{d:.0f}" viewBox="0 0 {d:.0f} {d:.0f}"><circle cx="{d / 2:.1f}" '
            f'cy="{d / 2:.1f}" r="{r:.1f}" '
            f'fill="none" stroke="{c.rgba(c.accent, .18)}" stroke-width="{stroke:.1f}"/>'
            f'<circle id="{sid}-dr" cx="{d / 2:.1f}" cy="{d / 2:.1f}" r="{r:.1f}" fill="none" stroke="{c.accent}" '
            f'stroke-width="{stroke:.1f}" stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{circ:.1f}" '
            f'transform="rotate(-90 {d / 2:.1f} {d / 2:.1f})"/></svg><b><span id="{sid}-dn">{shown}</span>%</b></div>'
            f'<div class="gdl">{esc(label)}</div></div>')

    def tw(at: float) -> list[str]:
        return [*_fade(uid, s)(at),
                f'tl.to("#{sid}-dr",{{strokeDashoffset:{circ * (1 - p / 100):.1f},duration:1.1,ease:"power2.out"}},{at + .3:g});',
                f'tl.fromTo("#{sid}-dn",{{textContent:0}},{{textContent:{p:g},duration:1.1,ease:"power2.out",'
                f'snap:{{textContent:{1 if p == int(p) else 0.1}}}}},{at + .3:g});']
    return Block(html, h, tw), [line]


def trend_block(sid: str, c: VCtx, lines: list[str]) -> tuple[Block, list[str]] | None:
    pts = trend_in(lines)
    if not pts:
        return None
    pts = pts[:5]
    s, w = c.scale, c.box_w
    n = len(pts)
    cell = (w - 2 * c.pad) / n
    labels = [f"{y}" for y, _, _ in pts] + [raw for _, _, raw in pts]
    if not whole(labels, c.fs, cell):
        return None
    vals = [v for _, v, _ in pts]
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    ch = 230 * s
    iw = w - 2 * c.pad
    xs = [(i + .5) / n * iw for i in range(n)]
    ys = [ch * .88 - (v - lo) / span * ch * .72 for v in vals]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys, strict=True))
    dots = "".join(f'<circle class="{sid}-td" cx="{x:.1f}" cy="{y:.1f}" r="{9 * s:.1f}" fill="{c.accent}" stroke="#fff" '
                   f'stroke-width="{3 * s:.1f}"/>' for x, y in zip(xs, ys, strict=True))
    row = "".join(f"<div><b>{esc(y)}</b>{esc(raw)}</div>" for y, _, raw in pts)
    uid = f"{sid}-gm"
    h = ch + 2 * c.pad + c.text_h("0000", c.fs, .62, cell) * 2 + 14 * s
    html = (f'<div class="gm gtr" id="{uid}"><svg viewBox="0 0 {iw:.0f} {ch:.0f}" style="height:{ch:.0f}px;">'
            f'<polyline id="{sid}-tl" points="{poly}" fill="none" stroke="{c.accent}" stroke-width="{5 * s:.1f}" '
            f'stroke-linejoin="round" stroke-linecap="round" pathLength="1" stroke-dasharray="1" stroke-dashoffset="1"/>'
            f'{dots}</svg><div class="row">{row}</div></div>')

    def tw(at: float) -> list[str]:
        return [*_fade(uid, s)(at),
                f'tl.to("#{sid}-tl",{{strokeDashoffset:0,duration:1.2,ease:"power1.inOut"}},{at + .3:g});',
                f'tl.fromTo(".{sid}-td",{{opacity:0}},{{opacity:1,duration:.2,stagger:.22}},{at + .4:g});']
    got = [ln for ln in lines if YEAR.search(ln)]
    return Block(html, h, tw), got[:n]


def columns_block(sid: str, c: VCtx, lines: list[str]) -> tuple[Block, list[str]] | None:
    cols = columns_in(lines)
    if not cols:
        return None
    s, w = c.scale, c.box_w
    n = len(cols)
    cell = (w - 2 * c.pad * .4 - (n - 1) * c.gap * .5) / n
    labels = [lab for _, _, _, lab in cols]
    if not whole([*labels, *(raw for _, _, raw, _ in cols)], c.fs, cell) or max(len(x) for x in labels) > 40:
        return None
    top = max(v for _, v, _, _ in cols)
    bar_max = 300 * s
    bars = "".join(
        f'<div><span class="val">{esc(raw)}</span><i class="bar {sid}-cb" '
        f'style="height:{max(0.08, v / top) * bar_max:.0f}px;"></i></div>'
        for _, v, raw, _ in cols)
    lab = "".join(f"<div>{esc(x)}</div>" for x in labels)
    uid = f"{sid}-gm"
    label_h = max(c.text_h(x, c.fs, .56, cell) for x in labels)
    h = c.text_h("0000", c.fs, .62, cell) + 8 * s + bar_max + label_h + c.pad * .8 + 10 * s
    html = f'<div class="gm" id="{uid}"><div class="gcol">{bars}</div><div class="gcl">{lab}</div></div>'

    def tw(at: float) -> list[str]:
        return [*_fade(uid, s)(at),
                f'tl.fromTo(".{sid}-cb",{{scaleY:0}},{{scaleY:1,duration:.7,ease:"power3.out",stagger:.2}},{at + .3:g});']
    return Block(html, h, tw), [ln for ln, *_ in cols]


def news_block(sid: str, c: VCtx) -> tuple[Block, list[str]] | None:
    n = c.news
    if not n:
        return None
    s, w = c.scale, c.box_w
    inner = w - 2 * c.pad * 1.2
    tag = "News clipping" if c.lang == "en" else "Keratan akhbar"
    compact = c.frame_h <= c.box_w * 1.5
    head_fs = c.fs * (0.9 if compact else 1.08)
    if not whole([n["title"], n["outlet"]], head_fs, inner):
        return None
    mast = max(c.text_h(n["outlet"], c.fs, .66, inner - len(tag) * c.fs * .5), c.text_h(tag, c.fs, .5, inner * .4))
    bars = 1 if compact else 3
    h = 2.2 * c.pad + mast + 26 * s + c.text_h(n["title"], head_fs, .58, inner, 1.16) + bars * 26 * s + 16 * s
    uid = f"{sid}-gm"
    html = (f'<div class="gm gnews" id="{uid}"><i class="tape"></i><div class="mh"><b>{esc(n["outlet"])}</b>'
            f'<span>{esc(tag)}</span></div>'
            f'<h3 style="font-size:{head_fs:.0f}px;">{esc(n["title"])}</h3><div class="ln"></div>'
            + ('' if compact else '<div class="ln" style="width:86%"></div><div class="ln" style="width:64%"></div>') + '</div>')

    def tw(at: float) -> list[str]:
        return [f'tl.fromTo("#{uid}",{{opacity:0,y:{70 * s:.0f},rotation:-3}},{{opacity:1,y:0,rotation:0,duration:.7,'
                f'ease:"back.out(1.4)"}},{at:g});']
    return Block(html, h, tw), []


def calendar_block(sid: str, c: VCtx, text: str) -> tuple[Block, list[str]] | None:
    dates = dates_in(text)
    if not dates:
        return None
    s, w = c.scale, c.box_w
    names = MONTH_NAMES["en" if c.lang == "en" else "bm"]
    n = len(dates)
    cell = (w - (n - 1) * c.gap) / n
    if not whole([names[m - 1] for _, m, _ in dates], c.fs, min(cell, w * .5) - 20 * s):
        return None
    tiles = ""
    for d, m, y in dates:
        mo = f'<div class="mo">{esc(names[m - 1])}</div>'
        if d is not None:
            tiles += f'<div class="{sid}-cd">{mo}<div class="dy">{d}</div><div class="yr">{y}</div></div>'
        else:
            tiles += (f'<div class="{sid}-cd">{mo}<div class="dy" style="font-size:{c.fs * 1.7:.0f}px;'
                      f'padding:{14 * s:.0f}px 0">{y}</div></div>')
    tile_h = max(c.fs * 2.3 * 1.05 + 12 * s + c.fs * 1.22 + 10 * s, c.fs * 1.7 * 1.05 + 28 * s)
    h = c.fs * 1.22 + 16 * s + tile_h + 10 * s
    uid = f"{sid}-gm"
    html = f'<div class="gm gcal" id="{uid}">{tiles}</div>'

    def tw(at: float) -> list[str]:
        return [*_fade(uid, s)(at),
                f'tl.fromTo(".{sid}-cd",{{opacity:0,scale:.6,rotation:-6}},{{opacity:1,scale:1,rotation:0,duration:.5,'
                f'ease:"back.out(1.8)",stagger:.25}},{at + .25:g});']
    return Block(html, h, tw), []


def build(code: str, sid: str, c: VCtx, heading: str, lines: list[str]) -> tuple[Block, list[str]] | None:
    """(the block, the lines it takes off the plain list) for a visual style, or None when the scene's words cannot carry it."""
    text = " ".join([heading, *lines])
    try:
        if code == "G01":
            return map_block(sid, c, text)
        if code == "G02":
            return pictogram_block(sid, c, lines)
        if code == "G03":
            return donut_block(sid, c, lines)
        if code == "G04":
            return trend_block(sid, c, lines)
        if code == "G05":
            return columns_block(sid, c, lines)
        if code == "G06":
            return news_block(sid, c)
        if code == "G07":
            return calendar_block(sid, c, text)
    except (KeyError, ValueError, ZeroDivisionError):
        return None
    return None


def needs(letter: str, heading: str, lines: list[str], news: dict[str, str] | None) -> bool:
    """The chooser's tests for the needs letters this module adds (motion_auto._holds)."""
    text = " ".join([heading, *lines])
    return {"G": bool(meaningful_places(text)), "R": ratio_in(lines) is not None, "Y": bool(trend_in(lines)),
            "K": bool(columns_in(lines)), "J": news is not None, "Z": bool(dates_in(text))}[letter]
