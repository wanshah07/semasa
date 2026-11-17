"""A film whose scene pictures are the four panels of a drawn comic (the daily series, comic_daily.py).

Motion already makes "template films" from a whole storyboard object (motion_templates.py: a product showcase and a photo
story, run by motion.template_film). This is the third template, `comic`, and it follows the same path: the same queue row,
the stage tracker, the storyboard gate (supabase/071), the HyperFrames render, the piano, the branded cover, the compressed
social copy, the poster frame and the captions. What is its own is where the pictures come from and how the page is laid out:

  * the storyboard is the comic's script (comic_daily.write_storyboard): the title, four panels, the people's words and the
    source line the system builds from the feed row. It waits for Wan (motion_review.hold) and NOTHING is drawn until he approves;
  * after the approval the comic is drawn ONCE (comic_job, as a Design job with `meta.comic.film`), and its square picture is
    stored beside the poster, so a film that fails later reuses it and never pays for the drawing again;
  * the film is laid out by code, 1080x1920: a title card (series, episode, title), the four panels in reading order, each
    with a slow camera move, and the bubbles appearing one by one in reading order (HTML over a WORDLESS panel when Semasa
    printed the words, which is the default: exact words, and the bubbles can come in one at a time; when the picture maker
    drew the words into the picture the panel is shown as drawn and each line is also said in a lane under it, in order),
    then the outro: the ws.regulab logo, the website and the source line.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from . import comic, comic_daily, comic_library, comic_writer, db, ideas, motion_captions, motion_review, motion_templates
from .log import get_logger

log = get_logger("semasa.comic_film")

W, H = motion_templates.W, motion_templates.H
SAFE_X = 90                    # side margin of everything on the film: 8% of the width, as the other template films keep
SAFE_Y = 96                    # nothing is placed above this or below H - SAFE_Y
BOX = W - 2 * SAFE_X           # a panel on the film, px
BOX_X, BOX_Y = SAFE_X, 420
INSET = 0.015                  # the share of a panel's side cut off each edge: the picture maker's outline and the gutter
PAPER, INK, MUTED, GREEN = "#f6f0e4", "#161616", "#6b6458", "#0f5d4a"
TITLE_SECONDS = 2.6
OUTRO_SECONDS = 3.6
LEAD = 0.8                     # a panel's picture is up this long before its first bubble
TAIL = 1.0                     # ... and holds this long after its last one is read
PANEL_MIN, PANEL_MAX = 4.0, 10.0
MOVE = 0.95                    # the camera move is the WHOLE panel (frame and bubbles) between this scale and 1.0: the panel
                               # is never larger than its box, so no edge, face or word ever leaves the picture
INSET_BAKED = 0.006            # ... and its edges are cut less (the picture maker drew words near them)
CHARS_PER_SECOND = 13.0        # how fast a bubble is read


# ------------------------------------------------------------------------------------------------------------ timeline

def reading(text: str) -> float:
    return len(" ".join(str(text or "").split())) / CHARS_PER_SECOND + 0.6


def panel_plan(panel: dict[str, Any]) -> dict[str, Any]:
    """{appear: [seconds after the panel starts, one per bubble, in reading order], duration}."""
    t, appear = LEAD, []
    for line in panel["lines"]:
        appear.append(round(t, 2))
        t += max(1.4, reading(line["text"]))
    return {"appear": appear, "duration": round(min(PANEL_MAX, max(PANEL_MIN, t + TAIL - 0.4)), 2)}


def timeline(sb: dict[str, Any]) -> dict[str, Any]:
    """{panels: [{start, duration, appear: [absolute seconds]}], outro_start, total}."""
    t = TITLE_SECONDS
    panels = []
    for p in sb["panels"]:
        plan = panel_plan(p)
        panels.append({"start": round(t, 2), "duration": plan["duration"], "appear": [round(t + a, 2) for a in plan["appear"]]})
        t += plan["duration"]
    return {"panels": panels, "outro_start": round(t, 2), "total": round(t + OUTRO_SECONDS, 2)}


# -------------------------------------------------------------------------------------------------------------- panels

def crop_panels(art: bytes | Image.Image, size: int = BOX, inset: float = INSET) -> list[Image.Image]:
    """The four panels of the square comic in reading order (top left, top right, bottom left, bottom right), each with its
    outline and the gutter cut off (`inset`) and made `size` px square."""
    img = Image.open(io.BytesIO(art)) if isinstance(art, bytes) else art
    img = img.convert("RGB")
    side = min(img.size)
    img = img.crop((0, 0, side, side)) if img.size[0] != img.size[1] else img
    half, cut = side / 2, side / 2 * inset
    out = []
    for n in range(comic.PANELS):
        x0, y0 = (n % 2) * half + cut, (n // 2) * half + cut
        out.append(img.crop((round(x0), round(y0), round(x0 + half - 2 * cut), round(y0 + half - 2 * cut)))
                   .resize((size, size), Image.LANCZOS))
    return out


def write_panels(art: bytes, folder: Path, *, wordless: bool = True) -> list[str]:
    """assets/panel1.jpg .. panel4.jpg in the film's project folder; the paths the page uses."""
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    paths = []
    for i, img in enumerate(crop_panels(art, inset=INSET if wordless else INSET_BAKED), 1):
        rel = f"assets/panel{i}.jpg"
        img.save(folder / rel, "JPEG", quality=92)
        paths.append(rel)
    return paths


def film_bubbles(script: dict[str, Any], heads: comic.Heads | None = None) -> list[list[dict[str, Any]]]:
    """Each panel's bubbles in reading order, placed on the film's panel box: {who, rows, size (font px), box (x, y, w, h), tail
    [(x, y) * 3], pad}. The geometry is comic.bubbles' own (the same words fit in the same places), scaled from the square comic
    to the panel as it is shown (the INSET is cut from each edge first). `heads` (comic.measure_heads of the wordless art)
    keeps every bubble above the people."""
    half = comic.SIDE / 2
    cut = half * INSET
    k = BOX / (half - 2 * cut)
    out: list[list[dict[str, Any]]] = [[] for _ in range(comic.PANELS)]
    for b in comic.bubbles(script, comic.SIDE, heads):
        n = b["panel"] - 1
        ox, oy = (n % 2) * half + cut, (n // 2) * half + cut
        x0, y0, x1, y1 = b["box"]
        box = ((x0 - ox) * k, (y0 - oy) * k, (x1 - x0) * k, (y1 - y0) * k)
        out[n].append({"who": b["who"], "rows": b["lines"], "size": round(b["size"] * k, 1),
                       "box": tuple(round(v, 1) for v in box),
                       "tail": [(round((x - ox) * k, 1), round((y - oy) * k, 1)) for x, y in b["tail"]],
                       "pad": round(comic.SIDE * 0.013 * k, 1)})
    return out


# ------------------------------------------------------------------------------------------------------------------ page

def _esc(text: Any) -> str:
    return motion_templates.esc(text)


def _bubble_svg(b: dict[str, Any]) -> str:
    x, y, w, h = b["box"]
    t0, t1, tip = b["tail"]
    st = 5
    return (f'<svg class="bsv" viewBox="0 0 {BOX} {BOX}" width="{BOX}" height="{BOX}" xmlns="http://www.w3.org/2000/svg">'
            f'<polygon points="{t0[0]:g},{t0[1]:g} {t1[0]:g},{t1[1]:g} {tip[0]:g},{tip[1]:g}" fill="#fff" stroke="{INK}" '
            f'stroke-width="{st}" stroke-linejoin="round"/>'
            f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" rx="34" ry="34" fill="#fff" stroke="{INK}" '
            f'stroke-width="{st}"/>'
            f'<line x1="{t0[0] + st:g}" y1="{t0[1]:g}" x2="{t1[0] - st:g}" y2="{t1[1]:g}" stroke="#fff" '
            f'stroke-width="{st + 3}"/>'
            "</svg>")


def _bubble_html(pid: str, b: dict[str, Any]) -> str:
    x, y, w, h = b["box"]
    rows = "<br>".join(_esc(r) for r in b["rows"])
    return (f'<div class="bb" id="{pid}">{_bubble_svg(b)}<div class="bt" style="left:{x:g}px;top:{y:g}px;width:{w:g}px;'
            f'height:{h:g}px;font-size:{b["size"]:g}px;line-height:{b["size"] * 1.24:g}px;">{rows}</div></div>')


def _say_html(pid: str, who: str, name: str, text: str, top: float, fs: int) -> str:
    return (f'<div class="say" id="{pid}" style="top:{top:g}px;font-size:{fs}px;"><b>{_esc(name)}:</b> {_esc(text)}</div>')


def compose(sb: dict[str, Any], script: dict[str, Any], panels: list[str], *, wordless: bool, website: str,
            episode_line: str, logo: str = "assets/official-logo-transparent.png",
            heads: comic.Heads | None = None) -> tuple[str, float]:
    """The film's page and its length. Every block has its own band of the frame, so no two words can meet; each scene is one
    clip and the bubbles of a panel come in one by one, in reading order, over the picture."""
    tl = timeline(sb)
    total = tl["total"]
    names = sb.get("names") or {"A": "A", "B": "B"}
    bubbles = film_bubbles(script, heads) if wordless else [[] for _ in range(comic.PANELS)]
    css = [
        motion_templates.FONT_CSS,
        f"html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:{PAPER};}}",
        f"body{{font-family:{motion_templates.FAMILY};color:{INK};}}",
        f"#root{{position:absolute;left:0;top:0;width:{W}px;height:{H}px;overflow:hidden;background:{PAPER};}}",
        ".sc{position:absolute;inset:0;}",
        f".ey{{position:absolute;left:{SAFE_X}px;width:{W - 2 * SAFE_X}px;font-weight:700;color:{MUTED};letter-spacing:.04em;}}",
        f".cnt{{position:absolute;right:{SAFE_X}px;top:118px;font-size:32px;font-weight:700;color:{GREEN};letter-spacing:.14em;}}",
        f".box{{position:absolute;left:{BOX_X}px;top:{BOX_Y}px;width:{BOX}px;height:{BOX}px;border-radius:34px;overflow:hidden;"
        f"background:#fff;box-shadow:0 0 0 7px {INK},0 22px 50px rgba(0,0,0,.18);}}",
        ".cam{position:absolute;inset:0;}",
        ".art{position:absolute;inset:0;background-size:cover;background-position:center;}",
        ".bb{position:absolute;inset:0;}",
        ".bsv{position:absolute;left:0;top:0;}",
        f".bt{{position:absolute;display:flex;align-items:center;justify-content:center;text-align:center;font-weight:800;"
        f"color:{INK};white-space:nowrap;}}",
        f".ttl{{position:absolute;left:{SAFE_X}px;width:{W - 2 * SAFE_X}px;text-align:center;font-weight:800;line-height:1.14;"
        f"color:{INK};}}",
        f".say{{position:absolute;left:{SAFE_X}px;width:{W - 2 * SAFE_X}px;font-weight:500;line-height:1.22;color:{INK};}}",
        f".say b{{font-weight:800;color:{GREEN};}}",
        f".dots{{position:absolute;left:{SAFE_X}px;width:{W - 2 * SAFE_X}px;display:flex;justify-content:center;gap:22px;}}",
        ".dots i{display:block;width:18px;height:18px;border-radius:50%;}",
        f"#out{{position:absolute;inset:0;background:{PAPER};}}",
        f".os{{position:absolute;left:{SAFE_X}px;width:{W - 2 * SAFE_X}px;text-align:center;}}",
    ]
    parts, tw = [], []
    # ---- the title card
    ep_fs = motion_templates._fit(episode_line, 40, W - 2 * SAFE_X, 26, factor=.56)
    t_fs = motion_templates._fit(sb["title"], 104, W - 180, 58, factor=.6, lines=3)
    t_lines = max(1, min(4, round(len(sb["title"]) * t_fs * .58 / (W - 180) + .49)))
    t_top = H * .46 - t_lines * t_fs * 1.14 / 2
    rule_top = t_top + t_lines * t_fs * 1.14 + 40
    parts.append(f'<div class="clip sc" id="s0" data-start="0" data-duration="{TITLE_SECONDS:g}" style="z-index:1;">'
                 f'<div class="ey" id="s0e" style="top:{t_top - 96:.0f}px;font-size:{ep_fs}px;text-align:center;">'
                 f'{_esc(episode_line)}</div>'
                 f'<div class="ttl" id="s0t" style="top:{t_top:.0f}px;font-size:{t_fs}px;">{_esc(sb["title"])}</div>'
                 f'<div class="ey" id="s0r" style="top:{rule_top:.0f}px;height:8px;background:{GREEN};'
                 f'left:{W / 2 - 70:.0f}px;width:140px;border-radius:4px;transform-origin:50% 50%;"></div></div>')
    tw += ['tl.fromTo("#s0e",{opacity:0,y:20},{opacity:1,y:0,duration:.5,ease:"power2.out"},.1);',
           'tl.fromTo("#s0t",{opacity:0,y:34},{opacity:1,y:0,duration:.6,ease:"power3.out"},.4);',
           'tl.fromTo("#s0r",{scaleX:0},{scaleX:1,duration:.5,ease:"power2.out"},1.0);',
           f'tl.to("#s0",{{opacity:0,duration:.3,ease:"power1.in"}},{TITLE_SECONDS - .3:g});']
    # ---- the four panels, in reading order
    for i, (p, when) in enumerate(zip(sb["panels"], tl["panels"], strict=True)):
        n = i + 1
        t0, dur = when["start"], when["duration"]
        sid = f"s{n}"
        bub = "".join(_bubble_html(f"b{n}{j + 1}", b) for j, b in enumerate(bubbles[i]))
        dots = "".join(f'<i style="background:{GREEN if k == i else "#d8cfbd"};"></i>' for k in range(comic.PANELS))
        say = ""
        if not wordless:
            top = 1580.0
            heavy = sum(len(ln["text"]) + 8 for ln in p["lines"])          # the lane holds two bubbles' words above the dots
            fs = 42 if heavy <= 100 else 36 if heavy <= 160 else 31
            for j, line in enumerate(p["lines"]):
                text = f"{names.get(line['who'], line['who'])}: {line['text']}"
                say += _say_html(f"y{n}{j + 1}", line["who"], names.get(line["who"], line["who"]), line["text"], top, fs)
                top += (1 + int(len(text) * fs * .53 / (W - 180))) * fs * 1.22 + 16
        s_fs = motion_templates._fit(sb["title"], 46, W - 140, 30, factor=.58, lines=2)
        parts.append(
            f'<div class="clip sc" id="{sid}" data-start="{t0:g}" data-duration="{dur:g}" style="z-index:{n + 1};">'
            f'<div class="ey" id="{sid}e" style="top:112px;font-size:32px;width:{W - 2 * SAFE_X - 260}px;">'
            f'{_esc(episode_line)}</div>'
            f'<div class="cnt" id="{sid}c">{n} / {comic.PANELS}</div>'
            f'<div class="box" id="{sid}x"><div class="cam" id="{sid}m">'
            f'<div class="art" style="background-image:url({panels[i]});"></div></div>{bub}</div>'
            f'<div class="ttl" id="{sid}t" style="top:1390px;font-size:{s_fs}px;font-weight:700;color:{MUTED};">'
            f'{_esc(sb["title"])}</div>'            f'{say}<div class="dots" style="top:1780px;">{dots}</div></div>')
        # the camera: the whole panel (frame, bubbles and all) pushes in from MOVE to 1 or pulls out from 1 to MOVE, never above 1
        a, z = (MOVE, 1) if i % 2 == 0 else (1, MOVE)
        tw.append(f'tl.fromTo("#{sid}x",{{scale:{a:g},transformOrigin:"50% 50%"}},'
                  f'{{scale:{z:g},transformOrigin:"50% 50%",duration:{dur:g},ease:"none"}},{t0:g});')
        tw += [f'tl.fromTo("#{sid}",{{opacity:0}},{{opacity:1,duration:.35,ease:"power1.out"}},{t0:g});',
               f'tl.fromTo("#{sid}x",{{y:30}},{{y:0,duration:.5,ease:"power3.out"}},{t0:g});']
        for j, at in enumerate(when["appear"]):
            if wordless:
                bx, by, bw, bh = bubbles[i][j]["box"]
                tw.append(f'tl.fromTo("#b{n}{j + 1}",{{opacity:0,scale:.82,transformOrigin:"{bx + bw / 2:g}px {by + bh:g}px"}},'
                          f'{{opacity:1,scale:1,duration:.4,ease:"back.out(1.7)"}},{at:g});')
            else:
                tw.append(f'tl.fromTo("#y{n}{j + 1}",{{opacity:0,y:14}},{{opacity:1,y:0,duration:.45,ease:"power2.out"}},'
                          f'{at:g});')
        tw.append(f'tl.to("#{sid}",{{opacity:0,duration:.3,ease:"power1.in"}},{t0 + dur - .3:g});')
    # ---- the outro: the brand, the website and the source
    o0 = tl["outro_start"]
    src = str(sb.get("source") or "")
    src_fs = motion_templates._fit(src, 34, W - 200, 24, factor=.54, lines=3)
    parts.append(
        f'<div class="clip" id="outc" data-start="{o0:g}" data-duration="{OUTRO_SECONDS:g}" style="z-index:30;">'
        f'<div id="out"><div id="ol" style="position:absolute;left:{W / 2 - 280:.0f}px;top:{H * .30:.0f}px;width:560px;'
        f'height:200px;background:url({logo}) center/contain no-repeat;"></div>'
        f'<div class="os" id="oe" style="top:{H * .30 + 250:.0f}px;font-size:36px;font-weight:700;color:{MUTED};">'
        f'{_esc(episode_line)}</div>'
        f'<div class="os" id="ow" style="top:{H * .30 + 330:.0f}px;font-size:44px;font-weight:800;color:{GREEN};">'
        f'{_esc(website)}</div>'
        + (f'<div class="os" id="os" style="top:{H * .30 + 450:.0f}px;font-size:{src_fs}px;font-weight:500;color:{MUTED};'
           f'line-height:1.3;">{_esc(src)}</div>' if src else "") + "</div></div>")
    tw += [f'tl.fromTo("#out",{{opacity:0}},{{opacity:1,duration:.5,ease:"power1.out"}},{o0:g});',
           f'tl.fromTo("#ol",{{opacity:0,y:30}},{{opacity:1,y:0,duration:.6,ease:"power3.out"}},{o0 + .3:g});',
           f'tl.fromTo("#oe",{{opacity:0}},{{opacity:1,duration:.5}},{o0 + .8:g});',
           f'tl.fromTo("#ow",{{opacity:0}},{{opacity:1,duration:.5}},{o0 + 1.1:g});']
    if src:
        tw.append(f'tl.fromTo("#os",{{opacity:0}},{{opacity:1,duration:.5}},{o0 + 1.5:g});')
    page = (motion_templates._head(sb["title"], "bm") + "<style>\n" + "\n".join(css) + "\n</style>\n</head>\n<body>\n"
            f'<div id="root" data-composition-id="main" data-start="0" data-duration="{total:g}" data-width="{W}" '
            f'data-height="{H}">\n' + "\n".join(parts) + "\n</div>\n" + motion_templates._tail(tw))
    return page, total


# ------------------------------------------------------------------------------------------------------------ the comic

def script_hash(sb: dict[str, Any]) -> str:
    """What the drawing was made from: the title, the setting and every bubble and scene. A new storyboard is a new drawing."""
    body = json.dumps({"t": sb.get("title"), "s": sb.get("setting"), "p": sb.get("panels")}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _series_options(store: Any, row: dict[str, Any], **fields: Any) -> dict[str, Any]:
    """Merge `fields` into options.series on the row and write it (read first: a style written by another step is kept)."""
    got = store.table(motion_review.TABLE).select("options").eq("id", row["id"]).limit(1).execute().data or []
    options = dict((got[0].get("options") if got else None) or row.get("options") or {})
    options["series"] = {**(options.get("series") or {}), **fields}
    store.table(motion_review.TABLE).update({"options": options}).eq("id", row["id"]).execute()
    row["options"] = options
    return options


def comic_job_row(sb: dict[str, Any], series: dict[str, Any], source: str, s: Any) -> dict[str, Any]:
    """The Design job the episode's drawing is made by: a `slides` job with meta.design "comic", the script already approved
    (so the writer is never asked again), the episode number the plan gave, and `film` so the square picture is kept."""
    script = {"title": sb["title"], "setting": sb["setting"], "panels": sb["panels"]}
    return {"type": "image", "mode": "slides", "status": "processing", "prompt": "", "created_by": None,
            "attempts": int(getattr(s, "max_attempts", 3)),          # one try: a failure is final, the film retries by itself
            "meta": {"flow": "comic-series", "design": "comic", "format": "portrait", "stream": "regulab",
                     "citation": source[:comic.MAX_SOURCE],
                     "comic": {"series": series["id"], "style": sb.get("style") or "", "script": script, "review": False,
                               "words_mode": str(sb.get("words_mode") or "art"), "episode": int(sb.get("episode") or 0),
                               "film": True, "script_sha": script_hash(sb)}}}


def ensure_comic(store: Any, row: dict[str, Any], sb: dict[str, Any], llm: Any, *, s: Any = None, providers: Any = None,
                 draw: Any = None, read: Any = "auto") -> dict[str, Any]:
    """The episode's drawn comic (a media_generations row, done, with its stored art): the one already drawn for THIS storyboard,
    else drawn now, once. A film that failed after the drawing finds the comic again and never pays for it twice; a new
    storyboard (Buat semula) is a new drawing. Raises RuntimeError with the reason when the comic could not be drawn."""
    from . import comic_job
    sx = ((row.get("options") or {}).get("series") or {}) if isinstance(row.get("options"), dict) else {}
    want = script_hash(sb)
    found: dict[str, Any] | None = None
    if sx.get("comic_id"):
        got = store.table(db.MEDIA).select("*").eq("id", sx["comic_id"]).limit(1).execute().data or []
        found = got[0] if got else None
    meta = (found.get("meta") or {}) if found else {}
    comic_meta = meta.get("comic") or {}
    drawn = found and found.get("status") == "done" and (comic_meta.get("art") or {}).get("path")
    if drawn and comic_meta.get("script_sha") == want:
        return found
    if s is None:
        from .config import MediaSettings
        s = MediaSettings.load()
    lib = comic_library.library(ideas.load_settings(store).get("comic"))
    series = comic_library.series_of(lib, sb.get("series")) or comic_library.series_of(lib, comic_daily.RULES["series"])
    source = str(sb.get("source") or "")
    fresh = comic_job_row({**sb, "style": sx.get("style") or ""}, series, source, s)
    if found and comic_meta.get("script_sha") == want:
        # the same storyboard whose drawing failed: tried again on the same row
        store.table(db.MEDIA).update({"status": "processing", "error": None, "attempts": fresh["attempts"],
                                      "meta": {**meta, "comic": {**comic_meta, "film": True}}}).eq("id", found["id"]).execute()
        job = {**found, "status": "processing", "attempts": fresh["attempts"]}
    else:
        job = store.table(db.MEDIA).insert(fresh).execute().data[0]
        _series_options(store, row, comic_id=job["id"], script_sha=want)
    ok = comic_job.process(store, job, s, llm, providers=providers if providers is not None else {}, draw=draw, read=read)
    after = (store.table(db.MEDIA).select("*").eq("id", job["id"]).limit(1).execute().data or [None])[0]
    art = (((after or {}).get("meta") or {}).get("comic") or {}).get("art") or {}
    if not ok or not after or after.get("status") != "done" or not art.get("path"):
        why = str((after or {}).get("error") or "the comic was not drawn")[:400]
        raise RuntimeError(f"the comic was not drawn, so no film was made: {why}")
    return after


# ----------------------------------------------------------------------------------------------------------- the worker

def caption_fallback(sb: dict[str, Any], platform: str) -> str:
    """A caption built from the storyboard alone: the title, the source, then the people's words, fitted to the platform."""
    names = sb.get("names") or {}
    said = "\n".join(f"{names.get(ln['who'], ln['who'])}: {ln['text']}" for p in sb["panels"] for ln in p["lines"])
    body = f"{sb['title']}\n\nSumber: {str(sb.get('source') or '').removeprefix('Sumber: ')}\n\n{said}"
    return motion_captions.fit(motion_captions._cut(body, motion_captions.SOFT.get(platform, 900)), "regulab", platform)


def safe_captions(llm: Any, row: dict[str, Any], sb: dict[str, Any], script: list[dict[str, Any]], *, lang: str, voice: str,
                  speak_as: Any) -> tuple[dict[str, str], list[str]]:
    """The captions: the writer's (motion_captions.write), each judged by the series' ruling rules and the hand-off rule;
    a platform whose caption fails them gets the storyboard's own words instead. Returns (captions, platforms that fell back)."""
    written = motion_captions.write(llm, row, script, sb["title"], lang=lang, voice=voice, speak_as=speak_as)
    ruling = sb.get("ruling") if isinstance(sb.get("ruling"), dict) else None
    out, fell = {}, []
    for plat in motion_captions.platforms_of("regulab"):
        text = str(written.get(plat) or "")
        bad = (not text or comic_daily.ruling_problems(re.split(r"(?<=[.!?])\s+|\n+", text), ruling)
               or re.search(r"https?://|www\.", text, re.I))
        if bad:
            fell.append(plat)
            text = caption_fallback(sb, plat)
        out[plat] = text
    return out, fell


def make_film(store: Any, llm: Any, row: dict[str, Any], settings: dict[str, Any], folder: Path, *,
              runner: Any = subprocess.run, s: Any = None, providers: Any = None, draw: Any = None, read: Any = "auto",
              fetch: Any = None) -> bool:
    """Motion's template path for the daily comic (motion.template_film calls this for `options.template == "comic"`):
    storyboard and stop; after the approval draw the comic once, make the film from its panels, draft the post. Raises on a
    failure (motion.process records it on the row, and a retry reuses the drawing)."""
    from . import motion
    all_settings = ideas.load_settings(store)
    folder.mkdir(parents=True, exist_ok=True)
    saved = motion_review.approved(row, "comic")
    if saved is None:
        motion.set_stage(store, row, "storyboard")
        sb, sb_note = comic_daily.write_storyboard(store, row, llm, all_settings)
        return motion_review.hold(store, row, "comic", {"sb": sb}, sb_note)
    try:
        sb = comic_daily.recheck(saved.get("sb"), all_settings)
    except motion_templates.StoryboardError as exc:
        motion_review.send_back(store, row, str(exc))
        return True
    sb_note = str(saved.get("note") or "")
    script = comic_daily.script_of(sb)
    motion.set_stage(store, row, "pictures", script=script)
    media = ensure_comic(store, row, sb, llm, s=s, providers=providers, draw=draw, read=read)
    art = ((media.get("meta") or {}).get("comic") or {}).get("art") or {}
    data = fetch(art["url"]) if fetch else store.storage.from_(db.GENERATED_BUCKET).download(art["path"])
    wordless = bool(art.get("wordless"))
    motion.set_stage(store, row, "film")
    motion_templates.copy_fonts(folder)
    panels = write_panels(data, folder, wordless=wordless)
    lib = comic_library.library(all_settings.get("comic"))
    series = comic_library.series_of(lib, sb.get("series")) or comic_library.series_of(lib, comic_daily.RULES["series"])
    comic_script = comic_writer.assemble({"title": sb["title"], "setting": sb["setting"], "panels": sb["panels"]}, series,
                                         "regulab", str(sb.get("source") or ""))
    reg = ((all_settings.get("brand") or {}).get("regulab") or {})
    website = str(reg.get("website") or "www.kkmhalalconsultant.com")
    episode_line = comic_library.episode_line(series["name"], sb.get("episode"), "bm")
    html, total = compose(sb, comic_script, panels, wordless=wordless, website=website, episode_line=episode_line,
                          heads=comic.measure_heads(data) if wordless else None)
    motion.write_project(folder, html, "regulab")
    report = motion.check(folder, settings["cli"], runner)
    report.update(template="comic", storyboard=sb_note, comic_media_id=media["id"], wordless=wordless,
                  series={"id": sb.get("series"), "episode": sb.get("episode"), "lane": sb.get("lane"), "day": sb.get("day")},
                  words=((media.get("meta") or {}).get("comic") or {}).get("words"), hook={"shape": None, "line": sb["title"]})
    video = motion.render(folder, settings["cli"], "portrait", runner)
    meta = motion.probe(video, runner)
    if not 0 < meta["duration_s"] <= motion.FILM_MAX + .5 or abs(meta["duration_s"] - total) > .5:
        raise ValueError(f"Rendered duration {meta['duration_s']}s does not match the comic's {total:g}s")
    video = motion.mix_music(video, [], total, runner)
    covered = motion.with_cover(video, sb["title"][:200], eyebrow=episode_line[:60], runner=runner)
    if covered != video:
        video, meta = covered, motion.probe(covered, runner)
        report["cover"] = {"seconds": motion.carousel.COVER_SECONDS}
    video = motion.fit_for_upload(video, runner)
    blob = video.read_bytes()
    path = f"motion/{row['id']}.mp4"
    url = db.upload_generated(store, path, blob, "video/mp4")
    jpg = motion.poster(video, runner)
    poster_url = db.upload_generated(store, f"motion/{row['id']}.jpg", jpg, "image/jpeg") if jpg else ""
    social_url, social_bytes = "", 0
    small = motion.social_copy(video, runner)
    if small:
        social_bytes = small.stat().st_size
        social_url = db.upload_generated(store, f"motion/{row['id']}-social.mp4", small.read_bytes(), "video/mp4")
    captions, fell = safe_captions(llm, row, sb, script, lang="bm", voice=motion.voice_line("regulab", "bm"),
                                   speak_as=motion.speaker("bm"))
    if fell:
        report["captions_from_storyboard"] = fell
    store.table(motion_review.TABLE).update({
        "status": "done", "title": sb["title"][:160], "html": html, "check_report": report, "video_path": path, "video_url": url,
        "poster_url": poster_url, "bytes": len(blob), "social_url": social_url, "social_bytes": social_bytes,
        "captions": captions, **meta, "model": getattr(llm, "last_model", "") or "", "error": "",
        "style_note": " · ".join(x for x in ("Template: daily comic", sb_note, "silent: the bubbles come in reading order",
                                             "approved self-owned piano") if x),
        "script": script}).eq("id", row["id"]).execute()
    db.log_event(store, "info", "media", "motion.done", f"Motion siap: komik episod {sb.get('episode')}: {sb['title'][:80]}",
                 ref_table=motion_review.TABLE, ref_id=row["id"])
    motion.set_stage(store, row, "done")
    comic_daily.queue_post(store, row, all_settings)          # a failure here leaves the film done; the next run drafts the post
    return True
