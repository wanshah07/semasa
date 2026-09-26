"""Wangian (fragrance): new ad designs for a perfume, with OUR bottle in them (Wan, 26 Sep 2026: "add one more segment
for fragrance, design is separate or can try to redesign via canva" / "you will run to find new design and will replace
the bottle in the design with our by render or via canva").

One media job (mode `fragrance`) walks through four steps, each started by the page and done by this worker:
  concepts  the writer proposes three designs from the perfume's notes, or from a reference ad Wan uploads (read as an
            art director reads it: its layout and mood are taken, never its artwork, brand or people)
  render    the chosen concept is drawn TWO ways, and Wan picks per design (his choice, 26 Sep 2026):
              cutout   the image model paints the scene with an empty place for the bottle; Wan's real bottle photo is
                       cut out and set into it with a shadow. The label is always right, because it is the photo.
              ai_edit  the image model paints the scene with the bottle photo as its reference. The light is more
                       natural; the label can come out wrong, so a model that sees reads it back and the page says
                       when it does not carry the brand and the perfume's name.
            Every word (the name, the tagline, the badges, the footnote) is typeset in Chrome on top, never drawn by the
            image model, so the text is exact in both.
  pick      waits for Wan: the version he keeps is saved, the other is deleted
  saved     the design is kept; a job never saved is cleared after UNSAVED_DAYS (compact storage)
  discard   Buang on the page: the files and the job are deleted (the page cannot delete from the generated bucket)

Badges only ever carry the claims Wan approved on the perfume (a fragrance is a cosmetic: a claim such as "more than 8
hours lasting" needs its evidence in the PIF), and the writer is told so. Canva designs are made in a chat session, not
here: the worker cannot sign in to Canva.

Where a design goes: Valorith, once Semasa's publishing is ready (Wan, 26 Sep 2026: "schedule to valorith once ready").
Until then a saved design is a picture to download; nothing here posts.
"""

from __future__ import annotations

import base64
import io
import json
import re
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from PIL import Image, ImageFilter

from . import db
from .log import get_logger
from .providers import Generated
from .providers.common import fetch_reference

log = get_logger("semasa.fragrance")

FRAGRANCES = "semasa_fragrances"
LAYOUTS = ("hero", "behind", "notes")
METHODS = ("cutout", "ai_edit")
SIZES = {"square": (1080, 1080), "portrait": (1080, 1350)}
UNSAVED_DAYS = 7


class FragranceError(RuntimeError):
    """Final for the job: the message is shown on the page."""


# --- the concepts --------------------------------------------------------------------------------------------------

CONCEPT_SYSTEM = ("You are the art director of a fragrance brand planning social media ads. Answer with ONE JSON object "
                  "only.")
CONCEPT_PROMPT = """Propose {n} NEW ad designs for this perfume, each different in setting and mood.

PERFUME: {product}
{reference}
Layouts you may use (one per design):
- "hero": the bottle on one side, the perfume's name very large on the other side, a short tagline under it, up to three
  round badges in a corner (like a luxury print ad);
- "behind": a huge condensed headline across the top, the bottle standing in front of it in the centre;
- "notes": the bottle in the centre among the ingredients of its notes, with up to three short call-outs naming the
  accords.

For each design answer:
"title": a short name for the design (English, a few words);
"why": one sentence in Malaysian Malay (never Bahasa Indonesia) on why it suits this perfume;
"layout": "hero" | "behind" | "notes";
"side": where the bottle stands: "left" | "center" | "right" ("behind" and "notes" are always "center");
"scene": one English paragraph for an image model: the setting, surface, props (ingredients from the notes, fabrics,
  light), lighting and colours, photographic style. There must be NO bottle, NO perfume, NO text, NO logos in it, and a
  clear empty place on the surface at the {side_word} where a bottle will stand;
"surface": "glossy" when the bottle stands on a mirror-like surface (polished marble, glass, still water, lacquer), else
  "matte";
"ink": the hex colour of the big words (readable on that scene); "accent": a second hex colour for small words;
"headline": the words set large: the perfume's name ("NOIR RUSH"), or for "behind" up to three short sensory words
  ("LUSHER SOFTER WARMER"). Never a claim;
"tagline": up to three words in spaced capitals ("TIMELESS ELEGANT"), or "". Never a claim: no duration, no number,
  no "long lasting", "best", "No.1", "halal", "safe", "natural", "organic", "clinically", "dermatologist";
"badges": up to three, copied WORD FOR WORD from APPROVED CLAIMS, or the concentration. Nothing else. [] if none;
"callouts": for "notes" only, up to three: {{"title": "SWEET & FRUITY", "line": "sweet, juicy & playful"}}, naming
  accords that are in NOTES only; [] otherwise.

Answer: {{"designs": [ ... ]}}"""

REFERENCE_SYSTEM = "You are an art director reading a reference ad. Answer with one JSON object only."
REFERENCE_PROMPT = """Read this perfume ad as a reference for NEW designs for another brand. Never copy its artwork,
brand, product or people. JSON keys: "layout" (the nearest of "hero", "behind", "notes"), "mood" (one English sentence:
setting, light, colours, props, style), "type" (one English sentence on its typography), "keep" (up to 3 short points in
Malaysian Malay: what to take from it), "brands" (logos or brand names visible, or [])."""


def product_text(p: dict[str, Any]) -> str:
    claims = [c for c in (p.get("claims") or []) if str(c).strip()]
    return (f'{p.get("brand") or "Valorith"} {p.get("name")} · {p.get("concentration") or "Extrait de Parfum"} · '
            f'{p.get("size") or ""}\nNOTES: {p.get("notes") or "(not given)"}\nMOOD: {p.get("mood") or "(not given)"}\n'
            f'APPROVED CLAIMS: {json.dumps(claims, ensure_ascii=False) if claims else "none: use no claim badges"}')


def read_reference(llm: Any, data: bytes, mime: str) -> dict[str, Any] | None:
    if llm is None or not getattr(llm, "configured", False):
        return None
    from .media_generator import shrink_for_read
    small, small_ct = shrink_for_read(data, mime)
    out = llm.describe_image(REFERENCE_SYSTEM, REFERENCE_PROMPT, small, small_ct, max_tokens=700)
    if not out or not str(out.get("mood") or "").strip():
        return None
    return {"layout": out.get("layout") if out.get("layout") in LAYOUTS else "hero", "mood": str(out["mood"])[:500],
            "type": str(out.get("type") or "")[:300],
            "keep": [str(k)[:160] for k in (out.get("keep") or [])][:3] if isinstance(out.get("keep"), list) else [],
            "brands": [str(b)[:60] for b in (out.get("brands") or [])][:6] if isinstance(out.get("brands"), list) else []}


# words that make a claim (a duration, a ranking, a certification, a safety or origin promise): on a fragrance artwork
# they may only appear as an approved badge, never in a headline, tagline or call-out the writer made up
CLAIMY = re.compile(r"\d|%|\b(long[- ]?lasting|lasts?|hours?|hrs?|jam|tahan|kekal|best|terbaik|no\.?\s*1|number one|nombor"
                    r" satu|halal|safe|selamat|natural|semula jadi|organic|organik|vegan|clinically|dermatolog\w*|proven|"
                    r"terbukti|guarantee\w*|dijamin|pure|tulen|100)\b", re.I)


def _claimy(text: str) -> bool:
    return bool(CLAIMY.search(text or ""))


def clean_concept(c: dict[str, Any], p: dict[str, Any]) -> dict[str, Any] | None:
    """One design as the page and the renderer need it; badges kept only when they are an approved claim word for word
    (or the concentration), whatever the writer answered."""
    if not isinstance(c, dict) or not str(c.get("scene") or "").strip():
        return None
    layout = c.get("layout") if c.get("layout") in LAYOUTS else "hero"
    side = c.get("side") if c.get("side") in ("left", "center", "right") else "left"
    if layout != "hero":
        side = "center"
    allowed = {str(x).strip().lower(): str(x).strip() for x in (p.get("claims") or []) if str(x).strip()}
    conc = str(p.get("concentration") or "").strip()
    if conc:
        allowed[conc.lower()] = conc
    badges = [allowed[str(b).strip().lower()] for b in (c.get("badges") or []) if str(b).strip().lower() in allowed][:3]
    callouts = []
    if layout == "notes":
        for k in (c.get("callouts") or [])[:3]:
            if isinstance(k, dict) and str(k.get("title") or "").strip():
                title, line = str(k["title"]).strip()[:28], str(k.get("line") or "").strip()[:40]
                if not _claimy(title) and not _claimy(line):
                    callouts.append({"title": title, "line": line})
    headline = str(c.get("headline") or "").strip()[:40]
    if not headline or _claimy(headline):
        headline = str(p.get("name") or "")[:40]
    tagline = str(c.get("tagline") or "").strip()[:40]
    return {"title": str(c.get("title") or "Design")[:60], "why": str(c.get("why") or "")[:240], "layout": layout,
            "side": side, "scene": str(c["scene"]).strip()[:900], "ink": _hex(c.get("ink"), "#fffaf0"),
            "accent": _hex(c.get("accent"), "#f3e6c4"), "surface": "glossy" if c.get("surface") == "glossy" else "matte",
            "headline": headline.upper(), "tagline": "" if _claimy(tagline) else tagline.upper(), "badges": badges,
            "callouts": callouts}


def _hex(v: Any, default: str) -> str:
    s = str(v or "").strip()
    return s if len(s) in (4, 7) and s.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in s[1:]) else default


def write_concepts(llm: Any, p: dict[str, Any], ref: dict[str, Any] | None = None, n: int = 3) -> list[dict[str, Any]]:
    if llm is None or not getattr(llm, "configured", False):
        raise FragranceError("the writer is not set up (LLM_API_KEY), so no concepts can be written")
    reference = ""
    if ref:
        reference = (f"REFERENCE AD WAN LIKES (take its layout and mood, never its artwork or brand): layout {ref['layout']}; "
                     f"mood: {ref['mood']}; typography: {ref['type']}\nMake the FIRST design follow this reference.\n")
    out = llm.chat_json(CONCEPT_SYSTEM, CONCEPT_PROMPT.format(n=n, product=product_text(p), reference=reference,
                                                              side_word="chosen side"), max_tokens=2600)
    designs = [d for d in (clean_concept(c, p) for c in ((out or {}).get("designs") or [])) if d]
    if not designs:
        raise FragranceError("the writer did not answer with any usable design; try again")
    return designs[:n]


# --- the bottle ----------------------------------------------------------------------------------------------------

def cutout(data: bytes) -> bytes:
    """The bottle on a transparent ground, cropped to it (PNG). A photo that is already transparent is used as it is; a
    pack shot on a plain background has that background removed from the edges inwards. A busy background cannot be
    removed safely, and says so rather than cutting the bottle badly.

    Two passes, because a pack shot is often a big frame with a small bottle in it (Wan's Noir Rush: 6000x4000, the
    bottle about 3% of it): a rough pass finds WHERE the bottle is, then the cut is made again on that crop alone, at a
    resolution where the edge is clean. Cutting the whole frame at thumbnail size gave a bottle edge a few pixels thick
    and blown up twentyfold."""
    img = Image.open(io.BytesIO(data))
    img.load()
    img = img.convert("RGBA")
    alpha = img.getchannel("A")
    if alpha.getextrema()[0] < 16 and _corners_clear(alpha):
        return _crop(img)
    rgb = img.convert("RGB")
    rough, bg = _flood(rgb, 480, None)
    box = rough.getbbox()
    rw, rh = rough.size
    if not box or rough.histogram()[255] < 0.002 * rw * rh or (box[3] - box[1]) < 0.05 * rh:
        raise FragranceError("no bottle was found on the plain background: is the bottle in the photo?")
    sx, sy = img.width / rw, img.height / rh
    pad = int(0.04 * max(img.width, img.height))
    crop_box = (max(0, int(box[0] * sx) - pad), max(0, int(box[1] * sy) - pad),
                min(img.width, int(box[2] * sx) + pad), min(img.height, int(box[3] * sy) + pad))
    part = img.crop(crop_box)
    part.thumbnail((1400, 1400))
    fine, _ = _flood(part.convert("RGB"), 720, bg)
    fine = fine.filter(ImageFilter.MinFilter(3))           # one pixel in: no white fringe on a dark scene
    part.putalpha(fine.resize(part.size, Image.BILINEAR).filter(ImageFilter.GaussianBlur(0.8)))
    return _crop(part)


def _flood(rgb: Image.Image, size: int, bg: tuple[int, ...] | None) -> tuple[Image.Image, tuple[int, ...]]:
    """A mask (255 = the object) of what is NOT reachable from the edges through background colour, worked at `size`."""
    small = rgb.copy()
    small.thumbnail((size, size))
    w, h = small.size
    px = small.load()
    border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + \
             [px[w - 1, y] for y in range(h)]
    if bg is None:
        bg = tuple(sorted(c[i] for c in border)[len(border) // 2] for i in range(3))
        if sum(1 for c in border if _dist(c, bg) > 40) / len(border) > 0.25:
            raise FragranceError("the bottle photo has a busy background, so it cannot be cut out cleanly: upload a "
                                 "pack shot on a plain white or light background, or a transparent PNG")
    seen = bytearray(w * h)
    mask = Image.new("L", (w, h), 255)
    mp = mask.load()
    queue = deque([(x, y) for x in range(w) for y in (0, h - 1)] + [(x, y) for y in range(h) for x in (0, w - 1)])
    while queue:
        x, y = queue.popleft()
        if not (0 <= x < w and 0 <= y < h) or seen[y * w + x]:
            continue
        seen[y * w + x] = 1
        if _dist(px[x, y], bg) > 30:
            continue
        mp[x, y] = 0
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))
    return mask, bg


def _dist(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    return sum((int(a[i]) - int(b[i])) ** 2 for i in range(3)) ** 0.5


def _corners_clear(alpha: Image.Image) -> bool:
    w, h = alpha.size
    return all(alpha.getpixel(p) < 16 for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)))


def _crop(img: Image.Image) -> bytes:
    box = img.getchannel("A").point(lambda v: 255 if v > 20 else 0).getbbox()
    if not box:
        raise FragranceError("the bottle photo is empty once its background is removed")
    img = img.crop(box)
    img.thumbnail((1400, 1400))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


# --- the scene and the words ---------------------------------------------------------------------------------------

SIDE_WORDS = {"left": "left third", "center": "centre", "right": "right third"}


def label_words(p: dict[str, Any]) -> list[str]:
    """What the real label says, as far as the perfume's own record knows: brand, name, concentration, size."""
    return [w for w in (str(p.get(k) or "").strip() for k in ("brand", "name", "concentration", "size")) if w]


def scene_prompt(c: dict[str, Any], with_bottle: bool, p: dict[str, Any] | None = None, strict: bool = False) -> str:
    where = SIDE_WORDS.get(c.get("side"), "centre")
    if with_bottle:
        words = ", ".join(f'"{w}"' for w in label_words(p or {}))
        label = (f"The label must read exactly these words and no others, spelled exactly: {words}. " if words else "")
        again = ("The previous attempt changed the label text; this time copy the label pixel for pixel from the photo "
                 "and do not invent any letters. " if strict else "")
        return (f"Place this exact perfume bottle standing on the surface in the {where} of this scene: {c['scene']} "
                "Keep the bottle exactly as in the photo: the same shape, cap, liquid colour and the same label; do not "
                f"redraw or change the label. {label}{again}Photorealistic luxury product photography, natural contact "
                "shadow. Leave calm space for large words. No other bottles, no other text, no logos.")
    return (f"{c['scene']} Leave a clear, empty place on the surface in the {where} for a product to stand. "
            "Photorealistic luxury product photography. No bottles, no perfume, no text, no letters, no logos, no people.")


def _esc(v: Any) -> str:
    return str(v or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _uri(data: bytes, kind: str) -> str:
    return f"data:{kind};base64," + base64.b64encode(data).decode("ascii")


# words never leave their box: the big line shrinks until it fits, never cut
FIT_SCRIPT = """document.fonts.ready.then(() => {
  const art = document.querySelector('.art');
  for (const el of document.querySelectorAll('.fit')) {
    let size = parseFloat(getComputedStyle(el).fontSize);
    const box = el.classList.contains('behind') ? el.clientWidth : el.parentElement.clientWidth;
    while ((el.scrollWidth > box + 1 || el.scrollHeight > art.clientHeight * 0.42) && size > 24) {
      size -= 4; el.style.fontSize = size + 'px';
    }
  }
  window.__ready = true;
});"""


def page_html(c: dict[str, Any], p: dict[str, Any], size: tuple[int, int], scene: bytes, bottle: bytes | None,
              logo: bytes | None) -> str:
    """The artwork as one HTML page: the scene, the bottle (the cut-out method) and every word, set in real fonts.
    The layout lives in web/public/cards/fragrance.css; this fills it."""
    w, h = size
    layout, side = c["layout"], c["side"]
    logo_html = (f'<img class="logo" src="{_uri(logo, "image/png")}">' if logo
                 else f'<div class="brand">{_esc(p.get("brand") or "Valorith")}</div>')
    gloss = " glossy" if c.get("surface") == "glossy" else ""
    bottle_html = (f'<div class="shadow {side}{gloss}"></div><img class="bottle {side}{gloss}" src="{_uri(bottle, "image/png")}">'
                   if bottle else "")
    if layout == "hero":
        words = [_esc(x) for x in c["headline"].split()]
        tag = f'<div class="tag">{_esc(c.get("tagline"))}</div>' if c.get("tagline") else ""
        where = "left" if side == "right" else "right"                    # the words stand opposite the bottle
        text = f'<div class="hero {where}"><div class="name fit">{"<br>".join(words)}</div>{tag}</div>'
    elif layout == "behind":
        text = f'<div class="behind fit">{_esc(c["headline"])}</div>'
    else:
        spots = ("l1", "r1", "r2")
        text = "".join(f'<div class="call {spots[i]}"><b>{_esc(k["title"])}</b><span>{_esc(k.get("line"))}</span></div>'
                       for i, k in enumerate((c.get("callouts") or [])[:3]))
    # the badges stand away from the bottle: beside the words on a hero, in a free corner when the bottle is central
    at = ("left" if side == "right" else "right") if layout == "hero" else ("left" if layout == "notes" else "right")
    wrap = "" if layout == "hero" else " wrap"
    badges = "".join(f'<div class="badge"><span>{_esc(b)}</span></div>' for b in c.get("badges") or [])
    starred = any("*" in b for b in c.get("badges") or [])
    foot = f'<div class="foot {at}">{_esc(p.get("footnote"))}</div>' if starred and p.get("footnote") else ""
    style = (f"--w:{w}px;--h:{h}px;--ink:{c['ink']};--accent:{c['accent']};"
             f"--bottle:{0.70 if layout == 'behind' else 0.64};--scene:url('{_uri(scene, 'image/jpeg')}')")
    return ('<!doctype html><html><head><meta charset="utf-8">'
            '<link rel="stylesheet" href="/cards/fonts.css"><link rel="stylesheet" href="/cards/fragrance-fonts.css">'
            '<link rel="stylesheet" href="/cards/fragrance.css"></head>'
            f'<body><div class="art" style="{style}"><div class="veil"></div>{logo_html}{text}{bottle_html}'
            f'<div class="badges {at}{wrap}">{badges}</div>{foot}</div><script>{FIT_SCRIPT}</script></body></html>')


def render_art(c: dict[str, Any], p: dict[str, Any], size: tuple[int, int], scene: bytes, bottle: bytes | None,
               logo: bytes | None = None) -> bytes:
    """JPEG bytes of one design, from the HTML page above, in the same headless Chrome the Studio cards use."""
    from playwright.sync_api import sync_playwright

    from .studio_cards import ORIGIN, _launch, _serve
    html = page_html(c, p, size, _jpeg(scene), bottle, logo)

    def serve(route: Any) -> None:
        path = route.request.url[len(ORIGIN):].split("?", 1)[0]
        if path == "/art.html":
            return route.fulfill(status=200, content_type="text/html", body=html)
        return _serve(route)
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            page = browser.new_page(viewport={"width": size[0], "height": size[1]})
            page.route(f"{ORIGIN}/**", serve)
            page.goto(f"{ORIGIN}/art.html")
            page.wait_for_function("window.__ready === true", timeout=30_000)
            return page.locator(".art").screenshot(type="jpeg", quality=92)
        finally:
            browser.close()


def _jpeg(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=92)
    return buf.getvalue()


LABEL_SYSTEM = "You read the words printed on a product in a photograph. Answer with one JSON object only."
LABEL_PROMPT = ('Read the words printed on the perfume bottle in this picture, exactly as they appear (spelling as '
                'printed). JSON: {"reads": "<the words on the bottle, or empty>"}')


def check_label(llm: Any, scene: bytes, p: dict[str, Any]) -> dict[str, Any] | None:
    """The AI edit redraws the bottle, and may redraw its label wrong. A model that sees reads it back; `ok` is whether
    every word the label must carry is there (brand, name, concentration, size: "EAU DE PARFUM 100 ML" on an Extrait
    de Parfum 30ml is caught), and `missing` names the ones that are not. None when no such model answered."""
    if llm is None or not getattr(llm, "configured", False):
        return None
    from .media_generator import shrink_for_read
    small, ct = shrink_for_read(scene, "image/jpeg")
    try:
        out = llm.describe_image(LABEL_SYSTEM, LABEL_PROMPT, small, ct, max_tokens=200)
    except Exception as exc:  # noqa: BLE001 - a check that could not run is reported as unchecked
        log.info("label check failed: %s", str(exc)[:120])
        return None
    if not isinstance(out, dict):
        return None
    reads = str(out.get("reads") or "").strip()[:200]
    flat = re.sub(r"[^a-z0-9]", "", reads.lower())
    missing = [w for w in label_words(p) if re.sub(r"[^a-z0-9]", "", w.lower()) not in flat]
    return {"reads": reads, "ok": not missing, "missing": missing}


# --- the job -------------------------------------------------------------------------------------------------------

def load_product(store: Any, fid: str) -> dict[str, Any]:
    rows = store.table(FRAGRANCES).select("*").eq("id", fid).limit(1).execute().data or []
    if not rows:
        raise FragranceError("this perfume is no longer in the list")
    return rows[0]


def process(store: Any, row: dict[str, Any], s: Any, llm: Any = None) -> bool:
    from .media_generator import _store, make_provider

    row_id = row["id"]
    meta = dict(row.get("meta") or {})
    step = meta.get("step") or "concepts"
    try:
        if step == "concepts":
            p = load_product(store, meta.get("fragrance_id") or "")
            meta["product"] = {k: p.get(k) for k in ("id", "brand", "name", "concentration", "size", "notes", "mood",
                                                      "claims", "footnote", "bottle_url", "logo_url")}
            ref = None
            if (meta.get("style_ref") or {}).get("url"):
                data, ct, _ = fetch_reference(meta["style_ref"]["url"])
                ref = read_reference(llm, data, ct)
                meta["review"] = ref or {"unread": "no model that can see answered, so the concepts come from the notes"}
            meta["concepts"] = write_concepts(llm, meta["product"], ref)
            meta["step"] = "choose"
            db.finish_media(store, row_id, status="done", provider="semasa", error=None, meta=meta)
            return True
        if step == "render":
            p = meta.get("product") or {}
            concepts = meta.get("concepts") or []
            pick = int(meta.get("pick") if meta.get("pick") is not None else -1)
            if not 0 <= pick < len(concepts):
                raise FragranceError("choose one of the concepts first")
            c = {**concepts[pick], **{k: v for k, v in (meta.get("edits") or {}).items() if k in ("headline", "tagline")}}
            size = SIZES.get(meta.get("format") or "square", SIZES["square"])
            methods = [m for m in (meta.get("methods") or list(METHODS)) if m in METHODS] or list(METHODS)
            if not p.get("bottle_url"):
                raise FragranceError("this perfume has no bottle photo: add one in the perfume list")
            bottle_raw, _, _ = fetch_reference(p["bottle_url"])
            logo = fetch_reference(p["logo_url"])[0] if p.get("logo_url") else None
            provider = make_provider(s.provider, s)
            renders, errors = [], {}
            label: dict[str, Any] | None = None
            stamp = datetime.now(UTC).strftime("%d%H%M%S")    # a new name each round: a redraw is never an old cached file
            earlier = [r["path"] for r in meta.get("renders") or [] if r.get("path")]
            for m in methods:
                try:
                    if m == "cutout":
                        bottle = cutout(bottle_raw)
                        scene = provider.generate_from_text(scene_prompt(c, with_bottle=False), {}).data
                        art = render_art(c, p, size, scene, bottle, logo)
                    else:
                        # an AI redraw may misspell the label: it is read back, drawn once more if wrong, and a label
                        # still wrong is kept only as a flagged picture Wan cannot save without checking it himself
                        for attempt in (1, 2):
                            scene = provider.generate("image", p["bottle_url"],
                                                      scene_prompt(c, True, p, strict=attempt > 1), {}).data
                            label = check_label(llm, scene, p)
                            if label is None or label["ok"]:
                                break
                        if label is not None:
                            label["attempts"] = attempt
                        art = render_art(c, p, size, scene, None, logo)
                    url, path = _store(store, row_id, Generated(art, "image/jpeg", "semasa-fragrance"), f"-{m}-{stamp}")
                    renders.append({"method": m, "url": url, "path": path,
                                    **({"label": label} if m == "ai_edit" and label else {})})
                except Exception as exc:  # noqa: BLE001 - one method failing leaves the other for Wan to pick
                    errors[m] = f"{type(exc).__name__}: {str(exc)[:300]}"
                    log.warning("%s: %s failed: %s", row_id, m, errors[m])
            if not renders:
                raise FragranceError("neither version could be made: " + "; ".join(f"{k}: {v}" for k, v in errors.items()))
            if earlier:                                       # another concept, or the same one again: the last round goes
                _remove(store, row_id, earlier)
            meta.update(renders=renders, render_errors=errors, rendered=c, step="pick",
                        rendered_at=datetime.now(UTC).isoformat())
            db.finish_media(store, row_id, status="done", provider="semasa", error=None, meta=meta,
                            generated_media_url=renders[0]["url"])
            return True
        if step == "save":
            keep = next((r for r in meta.get("renders") or [] if r.get("method") == meta.get("chosen")), None)
            if not keep:
                raise FragranceError("pick the version to keep first")
            _remove(store, row_id, [r["path"] for r in meta.get("renders") or [] if r is not keep and r.get("path")])
            meta.update(renders=[keep], saved=True, step="saved", saved_at=datetime.now(UTC).isoformat())
            db.finish_media(store, row_id, status="done", provider="semasa", error=None, meta=meta,
                            generated_media_url=keep["url"])
            return True
        if step == "discard":
            # Wan's Buang: the page cannot delete from the generated bucket, so the worker clears the files and the row
            _remove(store, row_id, [r["path"] for r in meta.get("renders") or [] if r.get("path")])
            if (meta.get("style_ref") or {}).get("path"):
                try:
                    store.storage.from_("semasa-reference").remove([meta["style_ref"]["path"]])
                except Exception as exc:  # noqa: BLE001
                    log.info("%s: could not delete the reference: %s", row_id, str(exc)[:120])
            store.table(db.MEDIA).delete().eq("id", row_id).execute()
            return True
        raise FragranceError(f"nothing to do at step {step!r}")
    except Exception as exc:  # noqa: BLE001
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, FragranceError) or attempts >= s.max_attempts
        msg = str(exc) if isinstance(exc, FragranceError) else f"{type(exc).__name__}: {str(exc)[:500]}"
        db.finish_media(store, row_id, status="error" if final else "pending", error=msg[:600], provider="semasa")
        log.error("%s: %s", row_id, msg)
        return False


def _remove(store: Any, row_id: str, paths: list[str]) -> None:
    if not paths:
        return
    try:
        store.storage.from_(db.GENERATED_BUCKET).remove(paths)
    except Exception as exc:  # noqa: BLE001 - a file left behind is housekeeping, not a failure
        log.info("%s: could not delete %d earlier file(s): %s", row_id, len(paths), str(exc)[:120])


def purge_unsaved(store: Any, now: datetime | None = None) -> int:
    """Fragrance designs never saved are cleared after UNSAVED_DAYS, with their files."""
    now = now or datetime.now(UTC)
    try:
        rows = store.table(db.MEDIA).select("id,meta,created_at").eq("mode", "fragrance") \
            .lt("created_at", (now - timedelta(days=UNSAVED_DAYS)).isoformat()).limit(200).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.info("could not look for unsaved fragrance designs: %s", str(exc)[:120])
        return 0
    gone = 0
    for r in rows:
        m = r.get("meta") or {}
        if m.get("saved"):
            continue
        try:
            files = [x["path"] for x in m.get("renders") or [] if x.get("path")]
            if files:
                store.storage.from_(db.GENERATED_BUCKET).remove(files)
            if (m.get("style_ref") or {}).get("path"):
                store.storage.from_("semasa-reference").remove([m["style_ref"]["path"]])
            store.table(db.MEDIA).delete().eq("id", r["id"]).execute()
            gone += 1
        except Exception as exc:  # noqa: BLE001
            log.info("could not clear fragrance design %s: %s", r.get("id"), str(exc)[:120])
    return gone
