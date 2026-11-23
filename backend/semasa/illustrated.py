"""The Journal look's illustrations (Wan, 23 Nov 2026: "try develop carousel like this, each slide got illustration in the middle
related to content", a Threads carousel with a hand-inked picture on every slide).

How the reference does it, and how it is done here:

  * ONE style for the whole set (pen-and-ink on cream paper, loose black line, a little cross-hatching, colour used sparingly in
    one deep blue and one orange), so the slides read as one hand; the style is the constant STYLE below and goes first in every
    prompt;
  * ONE scene per slide that shows what THAT slide says: the writer is asked once for all the scenes together (plan), so they
    differ from each other and follow the story of the set;
  * the picture maker is told to leave every letter out. The small hand-lettered label under the picture is drawn by the card
    (studio.js, Caveat), so its spelling is never a picture maker's and the compliance scan can read it;
  * the picture goes on the card as it is made: rounded, with a shadow, on the slide's own words.

Each picture is made once and kept on the render job (`meta.art`, keyed by the slide's words), so a redraw, a retry after one
slide failed, or a change to another slide never pays for a picture twice, and a slide whose words change gets a new
picture. Nothing here approves, schedules or sends anything.
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

import requests
from PIL import Image

from . import compliance, db
from .log import get_logger

log = get_logger("semasa.illustrated")

LOOK = "journal"
MAX_ART = 20                         # a set longer than this fails with the reason, never with some pages left bare
STYLE_VERSION = 2                    # bump it and every kept picture is made again
STYLE = ("Editorial pen-and-ink illustration on warm cream paper. A loose hand-drawn black ink line with fine "
         "cross-hatching and pencil texture. Flat crayon colour used sparingly: one deep forest green and one "
         "warm orange only, everything else left uncoloured. Everyday Malaysian people (men and women, some "
         "women in a tudung), expressive faces, one clear scene that explains the idea. The drawing fills the "
         "whole picture edge to edge on the paper, wide landscape, no border, no frame, no paper edge. "
         "Absolutely no text, no letters, no numbers, no signs, no logos, no captions in the picture.")
# The same hand, as a CUT-OUT (Wan, 23 Nov 2026: "same like other slide design, make illustration with transparent
# background"): the subject alone on a plain white page, so the white can be taken away and the drawing sits straight on
# the slide or the cover.
STYLE_CUT = ("Editorial pen-and-ink illustration. A loose hand-drawn black ink line with fine cross-hatching and pencil texture. "
             "Flat crayon colour used sparingly: one deep forest green and one warm orange only, the rest uncoloured. "
             "Everyday Malaysian people (men and women, some women in a tudung), expressive faces. Draw ONLY the people and the "
             "few objects that explain the idea, floating on a plain pure white page: no room, no walls, no floor, no furniture "
             "backdrop, no ground shadow, no paper texture, no frame, and a clear margin of white all round so the drawing "
             "never touches the edge of the picture. Wide landscape. "
             "Absolutely no text, no letters, no numbers, no signs, no logos, no captions in the picture.")
CUT_WHITE = 232                      # a pixel whose three channels are all at least this, and joined to the edge, is the page
CUT_EDGE = 5                         # the white sticker border round the drawing, in pixels of the working size
PLAN_SYSTEM = (
    "You are the art director of a social-media carousel drawn as hand-inked illustrations, one per slide. For EVERY slide below "
    "write ONE scene that shows, as a picture, what that slide says: who is there, what they are doing, the object or the "
    "moment that makes the idea clear. The scenes must differ from each other and follow the story of the set. Plain words, "
    "at most 40 words each, in English. A scene shows people, objects and places only: never any writing, never a real person, "
    "never a brand, a logo or a product name, never the Prophet, a religious figure or an ayat (for halal or fatwa topics draw "
    "an ordinary kitchen, factory, shop, office, lab or family instead). Also write a LABEL for each: at most four words in "
    "%s, a hand-lettered tag that names the idea of the picture; it adds no fact, no figure, no name that the slide does not "
    "have; \"\" when nothing short says it. Answer with ONE JSON object: "
    "{\"slides\": [{\"n\": 1, \"scene\": \"...\", \"label\": \"...\"}]}")


class ArtError(Exception):
    """A picture could not be made; the job tries again (what was made is kept)."""


def wants(look: str, kind: str = "") -> bool:
    """Every Studio look draws a picture per slide, on a carousel only: a post's own carousel, or the Design tab's Carousel mode
    (Wan, 23 Nov 2026: "all carousel slide design ... must have illustration"). The Journal look puts it in the middle of the
    page, the others in a band at the foot (studio.js renderWithArt). A Design-tab poster, card, comic or Threads set has its
    own single picture, and Semasa's own (classic) look is drawn without Studio's renderer, so it has none."""
    from . import studio_cards
    return kind in ("", "carousel") and look in studio_cards.LOOKS


def key_of(item: dict[str, Any], cut: bool = False) -> str:
    """What a slide's picture depends on: its own words (and whether it is the cut-out version). A different headline is a
    different picture."""
    words = "\n".join([str(item.get("title") or ""), str(item.get("lead") or ""), *[str(p) for p in item.get("points") or []],
                       str(item.get("note") or "")])
    return hashlib.sha1(f"{STYLE_VERSION}|{'cut|' if cut else ''}{words}".encode()).hexdigest()[:16]


def slides_needing_art(items: list[dict[str, Any]], stream: str, covered: bool | None = None) -> list[int]:
    """Indexes of the slides that get a picture: every one. The first slide of a ws.regulab post's own carousel is replaced by the
    white brand cover, and its picture is the HOOK's illustration on that cover (Wan, 23 Nov 2026: "can adjust coverpage by add
    illustration hook"); `covered` is kept so a caller can say which kind of set it is, and changes nothing here."""
    # a slide that names an ayat is drawn as the verse card in every look (studio.js specsFor), which has no place for a picture
    return [i for i, it in enumerate(items) if (it.get("title") or it.get("points")) and not it.get("ayat")]


def safe_label(text: Any, stream: str, lang: str) -> str:
    """A label that passes the rules a slide's words pass; anything else is left off (the picture stands without it)."""
    label = " ".join(str(text or "").replace("*", "").split())[:36]
    if not label or len(label.split()) > 5:
        return ""
    flags = compliance.scan({"stream": stream, "lang": lang, "media": [{"artwork": [{"title": label, "points": []}]}]})
    where = ("Design", "Slide", "Artwork")
    hard = compliance.hard_count([f for f in flags if str(f.get("where") or "").startswith(where)])
    return "" if hard else label


def plan(llm: Any, items: list[dict[str, Any]], idx: list[int], stream: str) -> dict[int, dict[str, str]]:
    """{slide index: {scene, label}}. A slide the writer gave nothing usable for gets a plain scene from its headline, so a
    failed plan never stops the set."""
    tongue = "natural English" if stream == "linkedin" else "casual Malaysian Malay (never Bahasa Indonesia)"
    lang = "en" if stream == "linkedin" else "bm"
    def words(it: dict[str, Any]) -> str:
        parts = [str(it.get("lead") or ""), *[str(p) for p in it.get("points") or []], str(it.get("note") or "")]
        return "\n".join(x for x in parts if x)
    brief = "\n\n".join(f"SLIDE {n}: {items[i].get('title') or ''}\n{words(items[i])}" for n, i in enumerate(idx, 1))
    got: dict[int, dict[str, str]] = {}
    try:
        out = llm.chat_json(PLAN_SYSTEM % tongue, brief[:6000], max_tokens=2200) if llm is not None else None
        rows = out.get("slides") if isinstance(out, dict) else None
        for row in rows if isinstance(rows, list) else []:
            try:
                n = int(row.get("n"))
            except (TypeError, ValueError, AttributeError):
                continue
            scene = " ".join(str(row.get("scene") or "").split())[:400]
            if 1 <= n <= len(idx) and scene:
                got[idx[n - 1]] = {"scene": scene, "label": safe_label(row.get("label"), stream, lang)}
    except Exception as exc:  # noqa: BLE001 - the plain scenes below stand in
        log.info("the scenes could not be planned (%s); each slide's own headline stands in", str(exc)[:120])
    for i in idx:
        headline = " ".join(str(items[i].get("title") or "the idea").split())[:200]
        got.setdefault(i, {"scene": "an everyday scene that shows: " + headline, "label": ""})
    return got


def prompt_of(scene: str, cut: bool = False) -> str:
    return f"{STYLE_CUT if cut else STYLE}\n\nScene: {scene}"


def cutout(data: bytes) -> bytes:
    """The picture as a transparent PNG: the plain white page round the drawing is taken away (only white JOINED TO THE EDGE,
    so the white of a shirt or a face inside the drawing stays), and the drawing gets a thin white sticker border, which keeps
    its black line readable on a dark slide. Raises ArtError when the picture has no page to take away (all of it is drawing)."""
    from PIL import ImageChops, ImageDraw, ImageFilter
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((1000, 1000))
    r, g, b = im.split()
    low = ImageChops.darker(ImageChops.darker(r, g), b)
    mask = low.point(lambda v: 255 if v >= CUT_WHITE else 0)                 # 255 where it is white
    w, h = im.size
    edge = [(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)]
    for xy in edge:
        if mask.getpixel(xy) == 255:
            ImageDraw.floodfill(mask, xy, 128)                               # the page: white joined to the edge
    page = mask.point(lambda v: 255 if v == 128 else 0)
    if page.getbbox() is None or sum(page.resize((20, 20)).getdata()) < 255 * 400 * 0.12:
        raise ArtError("the picture has no plain page round the drawing to take away")
    body = ImageChops.invert(page).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.1))   # no white fringe
    sticker = body
    for _ in range(max(1, CUT_EDGE // 2)):
        sticker = sticker.filter(ImageFilter.MaxFilter(5))
    sticker = sticker.filter(ImageFilter.GaussianBlur(1.4))
    out = Image.new("RGBA", im.size, (255, 255, 255, 0))
    out.paste((255, 255, 255, 255), mask=sticker)                             # the sticker border first
    out.paste(im.convert("RGBA"), mask=body)
    box = sticker.getbbox()
    if box:
        out = out.crop(box)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def shrink(data: bytes, edge: int = 1400) -> bytes:
    """The picture as a JPEG no wider than `edge`: the card shows it at about 970 px, so more is only weight."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((edge, edge))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, optimize=True)
    return buf.getvalue()


def makers(s: Any, store: Any) -> list[str]:
    """The picture makers tried in order, each only when it has credentials here (the comic's list: the ones that draw people)."""
    from . import media_generator as mg
    from .comic_job import MAKERS
    return [n for n in MAKERS if mg.has_credentials(n, s, store)]


def draw(store: Any, s: Any, prompt: str, names: list[str], providers: dict[str, Any], deadline: float | None,
         row_id: str) -> tuple[bytes, str]:
    from . import media_generator as mg
    from .providers import ProviderError

    def one(p: Any) -> Any:
        opts = {"resolution": "landscape", **({"size": "1536x1024"} if getattr(p, "name", "") == "openai" else {})}
        return p.generate_from_text(prompt, opts)
    gen, name, _tried = mg.generate_with_failover(providers, names, s, store, one, deadline=deadline, row_id=row_id)
    if not gen.data:
        raise ProviderError("the picture maker returned no picture")
    return shrink(gen.data), name


def art_bytes(item: dict[str, Any]) -> bytes | None:
    """The picture bytes of a slide that carries `art_url` (a data address), or None."""
    import base64
    url = str(item.get("art_url") or "")
    if not url.startswith("data:") or "," not in url:
        return None
    try:
        return base64.b64decode(url.split(",", 1)[1])
    except ValueError:
        return None


def fetch(url: str) -> bytes | None:
    try:
        r = requests.get(url, timeout=(10, 30))
        return r.content if r.ok and r.content else None
    except requests.RequestException:
        return None


def with_art(store: Any, s: Any, row: dict[str, Any], meta: dict[str, Any], items: list[dict[str, Any]], stream: str,
             llm: Any = None, *, providers: dict[str, Any] | None = None, deadline: float | None = None,
             draw_fn: Any = None, fetch_fn: Any = None, covered: bool | None = None, cut: bool = False) -> list[dict[str, Any]]:
    """`items` with each picture-bearing slide carrying `art_url` (a data address) and `art_label`, ready for the renderer.
    Pictures already kept on the job (`meta.art`, by the slide's words) are reused; the rest are made, uploaded and kept before
    the next one starts, so a failure part-way costs only what is missing. Raises ArtError when a picture cannot be made.
    `cut` makes each one a transparent cut-out PNG (every look but Diari)."""
    import base64
    from datetime import UTC, datetime
    idx = slides_needing_art(items, stream, covered)
    if not idx:
        return items
    if len(idx) > MAX_ART:
        raise ArtError(f"{len(idx)} slides each need a picture, and the most one set draws is {MAX_ART}: shorten the set")
    kept: dict[str, Any] = dict(meta.get("art") or {}) if isinstance(meta.get("art"), dict) else {}
    keys = {i: key_of(items[i], cut) for i in idx}
    missing = [i for i in idx if not (kept.get(keys[i]) or {}).get("url")]
    scenes = plan(llm, items, missing, stream) if missing else {}
    names = [] if draw_fn else makers(s, store)
    if missing and not draw_fn and not names:
        raise ArtError("no picture maker is connected (ChatGPT, Gemini, OpenAI, Cloudflare or Replicate): connect one on the API "
                       "page, or pick another look")
    row_id = row["id"]
    day, stamp = datetime.now(UTC).strftime("%Y/%m"), datetime.now(UTC).strftime("%d%H%M%S")
    provs = providers if providers is not None else {}
    for i in missing:
        sc = scenes[i]
        try:
            prompt = prompt_of(sc["scene"], cut)
            data, maker = (draw_fn(prompt), "test") if draw_fn else draw(store, s, prompt, names, provs, deadline, row_id)
            if cut:
                data = cutout(data)
        except Exception as exc:  # noqa: BLE001 - what is made stays; the job tries again for the rest
            raise ArtError(f"slide {i + 1}: the picture could not be made ({str(exc)[:200]})") from exc
        ext, mime = ("png", "image/png") if cut else ("jpg", "image/jpeg")
        path = f"{day}/{row_id}-{stamp}-art{i + 1:02d}{'c' if cut else ''}.{ext}"
        url = db.upload_generated(store, path, data, mime)
        kept[keys[i]] = {"url": url, "path": path, "scene": sc["scene"], "label": sc["label"], "maker": maker, "mime": mime,
                         "at": datetime.now(UTC).isoformat()}
        meta["art"] = kept
        meta["art_paths"] = [e["path"] for e in kept.values() if e.get("path")]
        store.table(db.MEDIA).update({"meta": meta}).eq("id", row_id).execute()
    out = []
    for i, it in enumerate(items):
        entry = kept.get(keys.get(i, "")) if i in keys else None
        if not entry:
            # the first slide of a ws.regulab set is replaced by the white brand cover: told so, it draws no empty picture frame
            out.append({**it, "art_skip": True} if i == 0 and (stream != "linkedin" if covered is None else covered) else it)
            continue
        data = (fetch_fn or fetch)(entry["url"])
        if not data:
            raise ArtError(f"slide {i + 1}: its kept picture could not be read back")
        out.append({**it, "art_url": f"data:{entry.get('mime') or 'image/jpeg'};base64," + base64.b64encode(data).decode("ascii"),
                    "art_label": entry.get("label") or ""})
    # pictures of words that no longer exist on this job are left for housekeeping (their paths stay in meta.art_paths)
    return out


def stale_paths(meta: dict[str, Any], items: list[dict[str, Any]], stream: str, covered: bool | None = None) -> list[str]:
    """Kept pictures whose slide's words are gone: files to remove once the redraw has used the rest."""
    live = {key_of(items[i], c) for i in slides_needing_art(items, stream, covered) for c in (False, True)}
    live |= {"cover|" + key_of(items[0], True)} if items else set()
    return [e["path"] for k, e in (meta.get("art") or {}).items() if k not in live and isinstance(e, dict) and e.get("path")]


def cover_art(store: Any, s: Any, row: dict[str, Any], meta: dict[str, Any], item: dict[str, Any], stream: str,
              llm: Any = None, *, providers: dict[str, Any] | None = None, deadline: float | None = None, draw_fn: Any = None,
              fetch_fn: Any = None) -> bytes | None:
    """The hook's illustration for the white brand cover: a transparent cut-out PNG, made once and kept on the job like the others
    (Wan, 23 Nov 2026: "for cover, the illustration must have transparent background"). Raises ArtError when it cannot be
    made; the cover is then drawn without it."""
    from datetime import UTC, datetime
    key = "cover|" + key_of(item, True)
    kept: dict[str, Any] = dict(meta.get("art") or {}) if isinstance(meta.get("art"), dict) else {}
    entry = kept.get(key)
    if not (entry or {}).get("url"):
        earlier = kept.get(key_of(item)) or kept.get(key_of(item, True)) or {}
        scene = str(earlier.get("scene") or "").strip()
        if not scene:
            scene = plan(llm, [item], [0], stream)[0]["scene"]
        names = [] if draw_fn else makers(s, store)
        if not draw_fn and not names:
            raise ArtError("no picture maker is connected for the cover's illustration")
        provs = providers if providers is not None else {}
        try:
            prompt = prompt_of(scene, True)
            data, maker = (draw_fn(prompt), "test") if draw_fn else draw(store, s, prompt, names, provs, deadline, row["id"])
            data = cutout(data)
        except Exception as exc:  # noqa: BLE001 - the cover is drawn without it
            raise ArtError(f"cover: the illustration could not be made ({str(exc)[:200]})") from exc
        path = f"{datetime.now(UTC).strftime('%Y/%m')}/{row['id']}-{datetime.now(UTC).strftime('%d%H%M%S')}-cover.png"
        url = db.upload_generated(store, path, data, "image/png")
        entry = kept[key] = {"url": url, "path": path, "scene": scene, "label": "", "maker": maker, "mime": "image/png",
                             "at": datetime.now(UTC).isoformat()}
        meta["art"] = kept
        meta["art_paths"] = [e["path"] for e in kept.values() if e.get("path")]
        store.table(db.MEDIA).update({"meta": meta}).eq("id", row["id"]).execute()
        return data
    return (fetch_fn or fetch)(entry["url"])
