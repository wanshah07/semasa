"""Pre-publish checks, ported from ws.regulab Studio's scanInner.

The patterns live in rules/compliance.json, which the page (web/src/lib/compliance.js)
reads too, so the badge Wan sees before he approves and the check the publisher runs
before it sends are the SAME rules. rules/cases.json is run by both test suites; a rule
that behaves differently in the two languages fails one of them.

scan(post, brand=None) -> list of {"hard": bool, "where": str, "msg": str}
A post with any hard flag must not be approved and must not be sent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "compliance.json"
RULES: dict[str, Any] = json.loads(RULES_PATH.read_text(encoding="utf-8"))

_WORD = re.compile(r"[a-z]+")
_TAG = re.compile(r"#\w+")
DOW_MS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _rx(rule: dict[str, Any]) -> re.Pattern[str]:
    return re.compile(rule["re"], re.I if "i" in rule.get("flags", "") else 0)


HARD = [(_rx(r), r["label"]) for r in RULES["hard"]] + [(_rx(r), r["label"]) for r in RULES["cta"]]
CTA = [(_rx(r), r["label"]) for r in RULES["cta"]]
SOFT = [(_rx(r), r["label"]) for r in RULES["soft"]]
SOCIAL_SRC = _rx(RULES["social_src"])
AGGREGATOR = _rx(RULES["aggregator"])
ANY_URL = _rx(RULES["any_url"])


def _esc(s: str) -> str:
    return re.escape(s)


def brand_url_re(brand: dict[str, Any]) -> re.Pattern[str]:
    parts = [RULES["brand_url_always"]]
    host = re.sub(r"^https?://", "", str(brand.get("website") or ""))
    host = re.sub(r"^www\.", "", host)
    host = re.sub(r"/.*$", "", host).strip()
    if host and "kkmhalalconsultant" not in host.lower():
        parts.append(_esc(host))
    return re.compile("(" + "|".join(parts) + ")", re.I)


def brand_mark_re(brand: dict[str, Any]) -> re.Pattern[str] | None:
    bits = []
    for key in ("website", "name", "handle", "tagline"):
        x = brand.get(key)
        if isinstance(x, str) and len(x.strip()) > 2:
            bits.append(_esc(re.sub(r"^www\.", "", x.strip(), flags=re.I)))
    if not bits:
        return None
    return re.compile(r"(?:www\.)?(?:" + "|".join(bits) + ")", re.I)


def platforms_for(stream: str) -> list[str]:
    return RULES["platforms"].get(stream, RULES["platforms"]["regulab"])


def lang_of(post: dict[str, Any]) -> str:
    return post.get("lang") or RULES["default_lang"].get(post.get("stream") or "regulab", "bm")


def text_of(post: dict[str, Any], plat: str, lang: str) -> str:
    """Language is the OUTER key and platform the inner one: text[lang][plat]."""
    t = post.get("text") or {}
    return str(((t.get(lang) or {}).get(plat)) or "")


def dow_of(iso_date: str) -> int | None:
    """Weekday of a YYYY-MM-DD date, 0 = Sunday (Studio's convention)."""
    from datetime import date
    try:
        y, m, d = (int(x) for x in iso_date[:10].split("-"))
        return (date(y, m, d).weekday() + 1) % 7
    except (ValueError, AttributeError):
        return None


def tabung(raw: Any) -> list[tuple[str, str]]:
    """Wan's own list of Indonesian words to avoid (semasa_settings.bahasa.indo, edited in Tetapan):
    [(indo, bm)], lowercase, deduped, minus anything the built-in list already catches."""
    out: list[tuple[str, str]] = []
    seen = set(RULES["indo"])
    for e in raw if isinstance(raw, list) else []:
        indo = re.sub(r"\s+", " ", _str(e.get("indo") if isinstance(e, dict) else e)).strip().lower()
        bm = _str(e.get("bm") if isinstance(e, dict) else "").strip()
        if indo and indo not in seen:
            seen.add(indo)
            out.append((indo, bm))
    return out


def indo_hits(text: str, extra: list[tuple[str, str]]) -> list[str]:
    """Messages for every Indonesian word in `text`: the built-in list, then Wan's tabung. A tabung
    entry of several words is matched as a phrase; one word is matched as a whole word."""
    low = text.lower()
    words = _WORD.findall(low)
    msgs = [f'Bahasa Indonesia word "{w}"' for w in RULES["indo"] if w in words]
    for indo, bm in extra:
        hit = indo in words if re.fullmatch(r"[a-z]+", indo) else \
            re.search(r"(?<![a-z])" + re.escape(indo) + r"(?![a-z])", low) is not None
        if hit:
            msgs.append(f'Bahasa Indonesia word "{indo}" (tabung' + (f': write "{bm}")' if bm else ")"))
    return msgs


def avoid_line(indo_extra: Any) -> str:
    """The tabung as one instruction for a writer's prompt ("" when the list is empty)."""
    items = [f'"{i}"' + (f' (write "{b}")' if b else "") for i, b in tabung(indo_extra)]
    return ("\nALSO NEVER USE these Indonesian words or phrases (Wan's own list; they have slipped through before): "
            + "; ".join(items) + ".") if items else ""


MAX_SLIDES = 10
MAX_POINTS = 5


def _str(v: Any) -> str:
    return "" if v is None else str(v)


def normalise_slides(raw: Any) -> list[dict[str, Any]]:
    """[{title, points[]}]: the one shape the writer, the page, the renderer and this scan use.
    Mirrored exactly by normaliseSlides in web/src/lib/compliance.js."""
    out: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for s in raw[:MAX_SLIDES]:
        if isinstance(s, str):
            s = {"title": s}
        if not isinstance(s, dict):
            continue
        title = _str(s.get("title")).strip()[:240]
        pts = s.get("points")
        if isinstance(pts, str):
            pts = pts.split("\n")
        # a point is one line: the page edits points as lines, so "a\nb" stored as one point reads as two there
        lines = [ln for p in (pts if isinstance(pts, list) else []) for ln in _str(p).split("\n")]
        points = [ln.strip()[:400] for ln in lines if ln.strip()][:MAX_POINTS]
        body = _str(s.get("body")).strip()
        if body and not points:
            points = [body[:400]]
        extra = slide_extras(s)
        if title or points or any(extra.get(k) for k in SLIDE_WORDS):
            out.append({"title": title, "points": points, **extra})
    return out


# A slide's own design (Studio's per-slide editor, brought over 27 Sep 2026): the words each design draws besides the
# headline and the points, and how it is drawn. Kept only when set, in this order, so a slide written before these
# existed compares equal to itself. Mirrored exactly by slideExtras in web/src/lib/compliance.js.
SLIDE_WORDS = {"lead": 400, "eyebrow": 80, "chip": 60, "note": 240, "footnote": 300}
SLIDE_STYLE = {
    "template": re.compile(r"^[gep]_[a-z]{2,8}$"),
    "scrim": re.compile(r"^(light|medium|heavy)$"),
    "bg": re.compile(r"^(none|post_image|lib:g_[a-z0-9]{2,30}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"),
    "mascot": re.compile(r"^(none|[a-z]{2,20})$"),
    # typography and the character's placement (Wan, 3 Oct 2026); 100% is the default and is never stored
    "type_size": re.compile(r"^(60|70|80|90|110|120)$"),
    "font": re.compile(r"^(sans|round|hand)$"),
    "mascot_pos": re.compile(r"^(bl|bc|br)$"),
    "mascot_size": re.compile(r"^(60|80|130|160)$"),
}


def slide_extras(s: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, cap in SLIDE_WORDS.items():
        v = _str(s.get(k)).strip()[:cap]
        if v:
            out[k] = v
    for k, rx in SLIDE_STYLE.items():
        v = _str(s.get(k)).strip()
        if v and rx.match(v):
            out[k] = v
    return out


def slide_text(sl: dict[str, Any]) -> str:
    """Every word a slide can put on the picture, for the scan."""
    return "\n".join([sl.get("title") or "", *(sl.get("points") or []), *(sl.get(k) or "" for k in SLIDE_WORDS)])


def slides_key(raw: Any) -> str:
    """Comparable form of a slide list: equal keys mean the same words."""
    return json.dumps(normalise_slides(raw), ensure_ascii=False, separators=(",", ":"))


def scan(post: dict[str, Any], brand: dict[str, Any] | None = None,
         schedule: dict[str, list[str]] | None = None, indo_extra: Any = None) -> list[dict[str, Any]]:
    brand = {**RULES["brand"], **(brand or {})}
    stream = post.get("stream") or "regulab"
    flags: list[dict[str, Any]] = []
    extra = tabung(indo_extra)

    def add(hard: bool, where: str, msg: str) -> None:
        flags.append({"hard": hard, "where": where, "msg": msg})

    lang = lang_of(post)
    burl = brand_url_re(brand)
    limits = RULES["limits"].get(stream, {})
    for p in platforms_for(stream):
        where = f"Caption ({p})"
        t = text_of(post, p, lang)
        if not t:
            add(True, where, "empty")
            continue
        lim = limits.get(p)
        if lim and len(t) > lim["max"]:
            add(True, where, f"{len(t)} chars, over the {lim['max']} limit")
        for rx, label in HARD:
            if rx.search(t):
                add(True, where, label)
        for rx, label in SOFT:
            if rx.search(t):
                add(False, where, label)
        if SOCIAL_SRC.search(t):
            add(True, where, "names a social source. Never say the idea came from Reddit, YouTube, a forum or a post.")
        words = _WORD.findall(t.lower())
        for msg in indo_hits(t, extra):
            add(True, where, msg)
        for w, why in RULES["indo_soft"]:
            if w in words:
                add(False, where, why)
        if burl.search(t):
            add(True, where, "the ws.regulab website. The artwork footer already carries it.")
        elif ANY_URL.search(t):
            add(False, where, "a link. Naming the instrument usually reads better than pasting a URL.")
        if re.search(r"kepada\s+bapak", t, re.I):
            add(False, where, '"kepada bapak" reads as Bahasa Indonesia')
        tags = len(_TAG.findall(t))
        if lim and tags > lim["hashtags"]:
            add(False, where, f"{tags} hashtags, over the {lim['hashtags']} limit")
        if p == "linkedin" and t.strip().endswith("?"):
            add(False, where, "ends with a question")
        if stream == "linkedin":
            hit = AGGREGATOR.search(t)
            if hit:
                add(True, where, f'cites "{hit.group(0)}", a blog or news aggregator. '
                                 "On LinkedIn cite the instrument, not where you read it.")
            mark = brand_mark_re(brand)
            if mark and mark.search(t):
                add(True, where, "a ws.regulab mark on LinkedIn. That stream is Wan's own byline.")

    # The other language is not sent, so its problems warn; they block the moment it is switched.
    other = "en" if lang == "bm" else "bm"
    for p in platforms_for(stream):
        t = text_of(post, p, other)
        if not t:
            continue
        tag = "BM" if other == "bm" else "EN"
        for rx, label in HARD:
            if rx.search(t):
                add(False, f"{tag} variant ({p})", label)
        for msg in indo_hits(t, extra):
            add(False, f"{tag} variant ({p})", msg)

    # The citation is printed on the artwork's source line, so it is judged like the artwork.
    cit = str(post.get("citation") or "")
    alts = [str(m.get("alt") or "") for m in (post.get("media") or []) if isinstance(m, dict)]
    for where, t in [("Source", cit)] + [(f"Picture {i + 1} alt text", a) for i, a in enumerate(alts)]:
        if not t:
            continue
        for rx, label in CTA:
            if rx.search(t):
                add(True, where, label)
        if burl.search(t):
            add(True, where, "the ws.regulab website")
        if SOCIAL_SRC.search(t):
            add(True, where, "names a social source. A post stands on the instrument, never on where the idea was spotted.")
        if stream == "linkedin":
            hit = AGGREGATOR.search(t)
            if hit:
                add(True, where, f'cites "{hit.group(0)}", a blog or news aggregator. Cite the instrument.')
            mark = brand_mark_re(brand)
            if mark and mark.search(t):
                add(True, where, "a ws.regulab mark on LinkedIn")

    # Slides are artwork: judged like a caption, and what is DRAWN must be what is written.
    def artwork(items: list[dict[str, Any]], label: str) -> None:
        for i, sl in enumerate(items):
            where = f"{label} {i + 1}"
            t = slide_text(sl)
            for rx, lab in HARD:
                if rx.search(t):
                    add(True, where, lab)
            if SOCIAL_SRC.search(t):
                add(True, where, "names a social source. A post stands on the instrument, never on where the idea was spotted.")
            for msg in indo_hits(t, extra):
                add(True, where, msg)
            if burl.search(t):
                add(True, where, "the ws.regulab website. Only the artwork footer carries it.")
            if stream == "linkedin":
                hit = AGGREGATOR.search(t)
                if hit:
                    add(True, where, f'cites "{hit.group(0)}", a blog or news aggregator. Cite the instrument.')
                mark = brand_mark_re(brand)
                if mark and mark.search(t):
                    add(True, where, "a ws.regulab mark on LinkedIn")

    slides = normalise_slides(post.get("slides"))
    artwork(slides, "Slide")
    # Wan's shape for a carousel (Studio, 7 Sep 2026): a cover, at least three slides carrying facts, then a closing
    # line that leaves them curious. One slide is a single card and is not a carousel.
    if len(slides) > 1:
        min_facts = int(RULES.get("carousel_min_facts") or 3)
        facts = sum(1 for x in slides[1:-1] if x.get("title") or x.get("lead") or x.get("points"))
        if facts < min_facts:
            add(True, "Carousel", f"{facts} slide{'' if facts == 1 else 's'} of substance between the cover and the "
                                  f"closing. At least {min_facts}.")
        last = slides[-1]
        if not (last.get("title") or last.get("lead")):
            add(True, "Carousel", "write the closing line: one statement that leaves them curious. Not a question, not an ask.")
    # A poster, card or carousel from the Design tab carries its own words: the same rules, but it is not a drawing
    # of this post's slides, so it is never compared with them.
    for k, m in enumerate(post.get("media") or []):
        if isinstance(m, dict) and "artwork" in m:
            artwork(normalise_slides(m["artwork"]), f"Design {k + 1}, slide")
    drawn = [m.get("slides") for m in (post.get("media") or []) if isinstance(m, dict) and "slides" in m]
    if any(slides_key(d) != slides_key(slides) for d in drawn):
        add(True, "Slides", "the slide pictures carry different words from the slides written here. "
                            "Draw them again (Jana slaid) so what is sent is what was checked.")
    elif slides and not drawn:
        add(False, "Slides", "written but not drawn yet. Only drawn slides are sent.")

    if stream == "regulab" and post.get("domain") == "fatwa":
        body = text_of(post, "facebook", lang) + text_of(post, "instagram", lang)
        if not re.search(r"diwartakan", body, re.I):
            add(True, "Post", "fatwa: gazette warning missing (diwartakan)")
    if stream == "regulab" and "instagram" in platforms_for(stream) and not (post.get("media") or []):
        add(True, "Post", "instagram needs an image")
    if stream == "regulab" and schedule and post.get("date") and post.get("domain"):
        dow = dow_of(str(post["date"]))
        allow = schedule.get(str(dow)) if dow is not None else None
        if allow and post["domain"] not in allow and post["domain"] not in RULES.get("rota_any_day", []):
            add(False, "Rota", f"{DOW_MS[dow]} carries {' and '.join(allow)}, and this is {post['domain']}. A note, not a block.")
    return flags


def hard_count(flags: list[dict[str, Any]]) -> int:
    return sum(1 for f in flags if f["hard"])
