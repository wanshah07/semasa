"""A small picture on every poster (Wan, 22 Nov 2026: "setiap poster at least tambah gambar kecil with transparent background,
make sure tulisan still visible kalau ada gambar di belakang, bukan poster plain semata"; for LinkedIn: "put small picture at the
background with various style, but make sure not block the text").

The picture is a cut-out with a transparent background, made once per post and kept on the render job (`meta.sticker_url`):

  * a REAL picture, never an illustration (Wan, 22 Nov 2026: "small picture is real picture not illustration"): Cloudflare
    Workers AI makes a realistic product photograph of the post's subject on plain white, and the white that touches the edge
    is made transparent (a flood fill from the border, so white INSIDE the object stays), with a white sticker outline;
  * failing that, an Unsplash photograph of the subject is cut into a circle badge with a white ring.

It is laid on the finished slide in the emptiest corner (measured from the slide's own pixels), in one of a few styles that
change from slide to slide (a plain cut-out with a soft shadow, a tilted one, one on a white disc). On a corner that is free it
is drawn whole; on a lone poster or a cover with no free corner it is drawn faint, so the words stay readable; a middle slide
with no free corner gets none. Wan keeps or removes it on the post (`meta.sticker` false: none; a cleared `sticker_url`:
a new one).
Nothing here raises: a picture that cannot be made only costs the picture, never the post.
"""

from __future__ import annotations

import io
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFilter

from . import db
from .log import get_logger

log = get_logger("semasa.stickers")

SUBJECTS = {
    "kosmetik": "a cosmetic cream jar and a serum dropper bottle",
    "kajian_kes": "a magnifying glass over a cosmetic bottle",
    "sains_kosmetik": "a laboratory flask with a drop of serum",
    "halal_my": "a plate of food with a green leaf",
    "fatwa": "an open book with a crescent moon",
    "farmaseutikal": "medicine capsules and a pill bottle",
    "makanan": "a food package with fresh vegetables",
}
DEFAULT_SUBJECT = "a laboratory flask and a clipboard"
PROMPT = ("A realistic studio product photograph of {subject}, a real object, sharp focus, soft natural light, one object in the "
          "centre with a wide empty margin, isolated on a plain pure white seamless background, no text, no letters, no logos, "
          "no people")
SENTINEL = (1, 254, 3)
FREE = 0.02            # a corner with less of the slide's ink than this is free
FAINT = 0.22           # the sticker's strength where no corner is free (a lone poster or a cover only)


def subject_for(meta: dict[str, Any]) -> str:
    said = str(meta.get("sticker_subject") or "").strip()
    return said or SUBJECTS.get(str(meta.get("domain") or ""), DEFAULT_SUBJECT)


def cutout(data: bytes, size: int = 640) -> bytes | None:
    """The drawing with the white around it made transparent and a white sticker outline, as PNG; None when it is not a
    cut-out."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((size, size))
    w, h = im.size
    work = im.copy()
    step = max(8, w // 24)
    for x in range(0, w, step):
        for y in (0, h - 1):
            if sum(work.getpixel((x, y))) > 690:
                ImageDraw.floodfill(work, (x, y), SENTINEL, thresh=38)
    for y in range(0, h, step):
        for x in (0, w - 1):
            if sum(work.getpixel((x, y))) > 690:
                ImageDraw.floodfill(work, (x, y), SENTINEL, thresh=38)
    alpha = Image.new("L", (w, h), 255)
    wp, ap = work.load(), alpha.load()
    for y in range(h):
        for x in range(w):
            if wp[x, y] == SENTINEL:
                ap[x, y] = 0
    kept = sum(1 for v in alpha.getdata() if v) / (w * h)
    if kept < 0.05 or kept > 0.92:
        return None
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    art = im.convert("RGBA")
    art.putalpha(alpha)
    ring = alpha.filter(ImageFilter.MaxFilter(13))
    out = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    out.paste((255, 255, 255, 255), mask=ring)
    out.alpha_composite(art)
    box = out.getchannel("A").getbbox()
    if box:
        out = out.crop(box)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def circle(data: bytes, size: int = 560) -> bytes:
    """A photograph as a round badge with a white ring, as PNG."""
    im = Image.open(io.BytesIO(data)).convert("RGB")
    side = min(im.size)
    left, top = (im.width - side) // 2, (im.height - side) // 2
    im = im.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    ring = round(size * 0.045)
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    ImageDraw.Draw(out).ellipse([0, 0, size - 1, size - 1], fill=(255, 255, 255, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([ring, ring, size - 1 - ring, size - 1 - ring], fill=255)
    out.paste(im, (0, 0), mask)
    buf = io.BytesIO()
    out.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def make(s: Any, subject: str) -> tuple[bytes, str] | None:
    """(PNG bytes, where it came from) or None."""
    try:
        from .providers.cloudflare import CloudflareProvider
        got = CloudflareProvider(s).generate_from_text(PROMPT.format(subject=subject), {})
        png = cutout(got.data)
        if png:
            return png, "cloudflare"
        log.info("stickers: the Cloudflare drawing was not a clean cut-out; trying Unsplash")
    except Exception as exc:  # noqa: BLE001 - the next source is tried
        log.info("stickers: Cloudflare gave no picture (%s)", str(exc)[:160])
    try:
        from . import unsplash
        found = unsplash.search(subject.replace("a ", "").replace("an ", ""), "squarish")
        if found:
            return circle(unsplash.fetch(found[0])), "unsplash"
    except Exception as exc:  # noqa: BLE001 - no picture this time
        log.info("stickers: Unsplash gave no picture (%s)", str(exc)[:160])
    return None


def ensure(store: Any, s: Any, row_id: str, meta: dict[str, Any]) -> bytes | None:
    """The post's sticker as PNG bytes, made and kept on the job the first time; None when Wan removed it or none could be
    made."""
    if meta.get("sticker") is False:
        return None
    url = str(meta.get("sticker_url") or "")
    if url:
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.content
        except Exception as exc:  # noqa: BLE001 - a new one is made below
            log.info("stickers: %s could not be read again (%s); making a new one", url[:80], str(exc)[:120])
    made = make(s, subject_for(meta))
    if not made:
        return None
    png, source = made
    try:
        meta["sticker_url"] = db.upload_generated(store, f"stickers/{row_id}.png", png, "image/png")
        meta["sticker_source"] = source
    except Exception as exc:  # noqa: BLE001 - drawn this time, made again next time
        log.info("stickers: not stored (%s)", str(exc)[:120])
    return png


# --- laying it on the slide --------------------------------------------------------------------------------------------


def _ink(region: Image.Image) -> float:
    """How much of a corner the slide's own drawing covers: the share of pixels far from the corner's usual colour."""
    small = region.convert("RGB").resize((40, 40))
    px = list(small.getdata())
    base = tuple(sorted(c[i] for c in px)[len(px) // 2] for i in range(3))
    far = sum(1 for c in px if abs(c[0] - base[0]) + abs(c[1] - base[1]) + abs(c[2] - base[2]) > 60)
    return far / len(px)


def lay(slide: bytes, sticker: bytes, place: str, index: int) -> bytes:
    """The slide with the sticker in its emptiest corner, in this slide's style; the slide unchanged when it has no room."""
    im = Image.open(io.BytesIO(slide)).convert("RGB")
    st = Image.open(io.BytesIO(sticker)).convert("RGBA")
    w, h = im.size
    lone = place in ("single", "cover")
    m = round(w * 0.045)
    top, foot = m + round(h * 0.09), round(h * 0.07)

    def spots(side: int) -> list[tuple[int, int]]:
        low, mid = h - side - m - foot, (h - side) // 2
        return [(w - side - m, low), (m, low), (w - side - m, top), (m, top), ((w - side) // 2, low),
                (w - side - m, mid), (m, mid)]

    pad = round(w * 0.035)                                 # clear space around it, so it never touches the words

    def ink_at(x: int, y: int, side: int) -> float:
        return _ink(im.crop((max(0, x - pad), max(0, y - pad), min(w, x + side + pad), min(h, y + side + pad))))

    best = None
    for share in ((0.27, 0.22, 0.17) if lone else (0.2, 0.16)):     # the largest size that finds a free spot
        side = round(w * share)
        ink, bx, by = min((ink_at(x, y, side), x, y) for x, y in spots(side))
        if ink < FREE:
            best = (side, bx, by, True)
            break
    if best is None:
        if not lone:
            return slide                                       # a middle slide with no room gets none
        side = round(w * 0.17)
        _, bx, by = min((ink_at(x, y, side), x, y) for x, y in spots(side))
        best = (side, bx, by, False)
    side, bx, by, free = best
    style = index % 3
    art = st.copy()
    art.thumbnail((round(side * (0.78 if style == 2 else 0.95)),) * 2, Image.LANCZOS)
    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    if style == 2:                                            # on a white disc
        ImageDraw.Draw(tile).ellipse([2, 2, side - 3, side - 3], fill=(255, 255, 255, 240))
    tile.alpha_composite(art, ((side - art.width) // 2, (side - art.height) // 2))
    if style == 1:                                            # tilted, alternately left and right
        tile = tile.rotate(8 if index % 2 else -8, resample=Image.BICUBIC, expand=False)
    shadow = tile.getchannel("A").filter(ImageFilter.GaussianBlur(side * 0.03))
    shade = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    shade.putalpha(shadow.point(lambda v: round(v * 0.22)))
    if not free:                                              # nowhere empty: faint, so the words stay readable over it
        a = tile.getchannel("A").point(lambda v: round(v * FAINT))
        tile.putalpha(a)
        shade.putalpha(Image.new("L", (side, side), 0))
    out = im.convert("RGBA")
    off = max(2, round(side * 0.02))
    out.alpha_composite(shade, (bx + off, by + off))
    out.alpha_composite(tile, (bx, by))
    buf = io.BytesIO()
    out.convert("RGB").save(buf, "JPEG", quality=90, optimize=True, progressive=True)
    return buf.getvalue()


def place_of(i: int, n: int) -> str:
    return "single" if n <= 1 else "cover" if i == 0 else "closing" if i == n - 1 else "middle"


def on_slides(pics: list[bytes], sticker: bytes | None) -> list[bytes]:
    """Every slide but the last of a set (the takeaway or closing) gets the sticker where it fits."""
    if not sticker:
        return pics
    n = len(pics)
    out = []
    for i, data in enumerate(pics):
        place = place_of(i, n)
        try:
            out.append(data if place == "closing" else lay(data, sticker, place, i))
        except Exception as exc:  # noqa: BLE001 - the slide as drawn stands
            log.info("stickers: slide %d left as drawn (%s)", i + 1, str(exc)[:120])
            out.append(data)
    return out
