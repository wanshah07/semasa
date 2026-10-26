"""The safe layout (Wan, 25 Oct 2026: "the text not overlap").

The AI writer lays a film out freely, and a free layout can put one line of type on top of another: HyperFrames reported
`content_overlap` and `text_occluded` on test renders that shipped anyway. This module writes the same film
deterministically, and overlap is impossible by construction:

  * the format is the one in Wan's four approved reference films (25 Oct 2026): the heading on top, the visual (a photo in an
    arch frame) in the middle, the narration as two-line transparent subtitles in their own lane below the column, no kicker
    labels, no presenter;
  * every scene is ONE flex column inside the safe area (clear of the top 12%, the subtitle lane and the right 12%), and every
    block in it (heading, photo frame, lines) is a normal-flow child: nothing is placed by coordinates;
  * type is sized from the words: the heading shrinks until the estimated wrapped height of the whole column fits the
    box, and when it cannot fit at the smallest readable size the last line is dropped (and recorded), never squeezed on top;
  * a photo sits in its own frame above the text, never behind it;
  * motion moves opacity and y inside each block's own slot, by a few pixels.

It is the writer's fallback: the film uses it when the writer's layout still fails the overlap check after its fix passes.
It builds a subset of the chosen styles (the others are named in the report as not built here).
"""

from __future__ import annotations

import html as html_mod
import re
from typing import Any

from . import motion_auto

SAFE = {"left": 0.08, "right": 0.14, "top": 0.13, "bottom": 0.23}
LANE = (0.78, 0.115)              # the subtitle lane of a narrated film: top and height as fractions of the frame
GAP = 0.028                       # between blocks, as a fraction of the frame width
WIDE = 0.62                       # estimated average glyph width / font size for a bold heading (system sans, never narrower)
BODY = 0.56
MIN_PX = 44                       # on a 1080-wide frame (the contract's floor)
FILTERS = {"F02": "sepia(.16) saturate(1.05) brightness(1.02)", "F03": "saturate(.88) contrast(1.06) brightness(1.02)",
           "F05": "grayscale(1) contrast(1.15)", "F06": "saturate(1.35) contrast(1.08)",
           "F07": "saturate(.86) contrast(.93) brightness(1.06)", "F10": "contrast(1.06) saturate(1.04)"}
BUILT = {"H02", "H08", "C02", "C04", "C05", "C06", "V04", "V08", "B05", "B08", "M02", "M03", "M08", "M09",
         "F02", "F03", "F05", "F06", "F07", "F10"}


def wrap_lines(text: str, px: float, width: float, factor: float) -> int:
    """How many lines `text` takes at `px` in a column `width` wide (greedy by word, estimated glyph width)."""
    n, cur = 1, 0.0
    space = px * factor * 0.5
    for word in text.split():
        wpx = len(word) * px * factor
        if wpx > width:                                   # a token wider than the column breaks inside (overflow-wrap)
            wpx = width
        if cur and cur + space + wpx > width:
            n += 1
            cur = wpx
        else:
            cur += (space if cur else 0) + wpx
    return n


def fit(blocks: list[tuple[str, float, float]], width: float, height: float, fixed: float, scale: float) -> list[float]:
    """Font sizes (px) for text blocks [(text, first_px, factor)] so the column plus `fixed` pixels of other blocks fits
    `height`. Every size scales together and never goes under the readable floor; the caller drops lines if it cannot."""
    floor = MIN_PX * scale
    k = 1.0
    while True:
        sizes = [max(floor, px * k) for _, px, _ in blocks]
        used = fixed + sum(wrap_lines(t, s, width, f) * s * 1.18 + s * 0.35 for (t, _, f), s in zip(blocks, sizes, strict=True))
        if used <= height or all(s <= floor + 0.01 for s in sizes):
            return sizes if used <= height else []
        k *= 0.94


def caption_chunks(sc: dict[str, Any]) -> list[tuple[str, float, float]]:
    """2–4-word actual-boundary groups, otherwise honestly estimated phrase captions.

    Historical sentence-spread `words` without actual-word provenance are never alignment.
    """
    words = str(sc.get("narration") or "").split()
    if not words:
        return []
    start = float(sc["start"])
    span = float(sc.get("audio_s") or sc["duration"])
    timed = sc.get("words") or []
    if sc.get("timing_source") == "actual-word" and timed:
        groups = [timed[i:i + 4] for i in range(0, len(timed), 4)]
        if len(groups) > 1 and len(groups[-1]) == 1:
            groups[-1].insert(0, groups[-2].pop())
        return [(" ".join(str(w[2]) for w in group), round(start + float(group[0][0]), 3),
                 round(start + min(span, float(group[-1][1])), 3)) for group in groups]
    # Phrase timing is proportional, not karaoke, and explicitly reported as estimated.
    groups = [words[i:i + 6] for i in range(0, len(words), 6)]
    total = sum(len(w) + 1 for w in words)
    used, out = 0, []
    for group in groups:
        end = used + sum(len(w) + 1 for w in group)
        out.append((" ".join(group), round(start + span * used / total, 3), round(start + span * end / total, 3)))
        used = end
    return out


def esc(s: str) -> str:
    return html_mod.escape(str(s), quote=False)


def compose(*, scenes: list[dict[str, Any]], total: float, w: int, h: int, lang: str, plan: dict[str, Any],
            palette: dict[str, str], gsap: str, html_lang: str, resolution: str,
            worker_captions: bool = False) -> tuple[str, dict[str, Any]]:
    scale = w / 1080
    box_w = w * (1 - SAFE["left"] - SAFE["right"])
    teaching = [s for s in scenes if s.get("id") != "brand-outro"]
    narrated = any(s.get("audio") for s in teaching)
    box_h = h * ((LANE[0] - 0.02 if narrated else 1 - SAFE["bottom"]) - SAFE["top"])
    gap = w * GAP
    video = plan.get("video") or {}
    caption = video.get("captions") if video.get("captions") in {"C02", "C04", "C05", "C06"} else "C05"
    transition = video.get("transition") or "M09"
    finish = FILTERS.get(video.get("finish") or "", FILTERS["F07"])
    dropped: list[str] = []
    css = [
        f"html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{palette['ground']};}}",
        f'body{{font-family:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;color:{palette["ink"]};}}',
        f"#root{{position:absolute;left:0;top:0;width:{w}px;height:{h}px;overflow:hidden;"
        f"background:linear-gradient(160deg,{palette['ground']} 0%,{palette['accent2']} 100%);}}",
        ".bg{position:absolute;border-radius:50%;opacity:.14;}",
        f".sc{{position:absolute;left:{w * SAFE['left']:.0f}px;top:{h * SAFE['top']:.0f}px;width:{box_w:.0f}px;"
        f"height:{box_h:.0f}px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;"
        f"gap:{gap:.0f}px;overflow:hidden;}}",
        ".ph{position:relative;align-self:center;overflow:hidden;flex:none;}",
        f".cap{{position:absolute;left:{w * SAFE['left']:.0f}px;top:{h * LANE[0]:.0f}px;width:{box_w:.0f}px;"
        f"height:{h * LANE[1]:.0f}px;display:flex;align-items:center;justify-content:center;text-align:center;"
        f"font-weight:500;line-height:1.3;color:{palette['ink']};overflow-wrap:anywhere;}}",
        ".ph>div{position:absolute;inset:0;background-size:cover;background-position:center;}",
        f".h{{margin:0;font-weight:800;line-height:1.12;color:{palette['ink']};overflow-wrap:anywhere;max-width:100%;}}",
        f".l{{margin:0;font-weight:600;line-height:1.18;color:{palette['ink']};overflow-wrap:anywhere;max-width:100%;}}",
        f".l.en{{color:{palette['accent']};font-weight:600;}}",
        f".kw{{position:relative;display:inline-block;isolation:isolate;}} "
        f".kw i{{position:absolute;left:0;right:0;bottom:.04em;height:.34em;"
        f"background:{palette['accent']};opacity:.28;transform-origin:0 50%;}}",
        f".rule{{flex:none;height:{max(3, 5 * scale):.0f}px;width:{w * .18:.0f}px;background:{palette['accent']};"
        "transform-origin:0 50%;}",
        f".dot{{display:inline-block;width:.42em;height:.42em;border-radius:50%;background:{palette['accent']};"
        "margin-right:.45em;vertical-align:middle;}",
        f".flash{{position:absolute;left:0;top:0;width:{w}px;height:{h}px;background:{palette['accent']};opacity:0;"
        "pointer-events:none;z-index:30;}",
    ]
    parts, tw = [], []
    bgs = [(0.66, 0.74, 0.55), (0.04, 0.84, 0.34), (0.8, 0.06, 0.26)]
    for i, (fx, fy, fr) in enumerate(bgs):
        size = w * fr
        parts.append(f'<div class="bg" id="bg{i}" style="left:{w * fx - size / 2:.0f}px;top:{h * fy - size / 2:.0f}px;'
                     f'width:{size:.0f}px;height:{size:.0f}px;'
                     f'background:{palette["accent"] if i != 1 else palette["accent2"]};"></div>')
        tw.append(f'tl.to("#bg{i}",{{x:{(-1) ** i * 40 * scale:.0f},y:{(-1) ** (i + 1) * 30 * scale:.0f},'
                  f'duration:{total:g},ease:"none"}},0);')
    picked = {c for cs in plan.get("scenes", {}).values() for c in cs}
    if {"V08", "B08"} & picked:
        tw.append(f'tl.to("#bg0",{{rotation:90,scale:1.12,duration:{total:g},ease:"none"}},0);')
    parts.append('<div class="flash" id="flash"></div>')
    for idx, sc in enumerate(teaching):
        sid, start, dur = sc["id"], float(sc["start"]), float(sc["duration"])
        first = idx == 0
        lines = [x for x in (sc.get("lines") or []) if str(x).strip()]
        heading = str(sc.get("heading") or "").strip()
        photo = sc.get("photo")
        photo_h = (h * 0.32 if h >= w else h * 0.36) if photo else 0
        photo_w = min(box_w, photo_h * 0.8)
        px_h = (104 if len(heading.split()) <= 4 else 88 if len(heading.split()) <= 7 else 72 if len(heading.split()) <= 11
                else 60) * scale
        px_l = 50 * scale
        texts = ([(heading, px_h, WIDE)] if heading else []) + [(ln, px_l, BODY) for ln in lines]
        while True:
            fixed = photo_h + gap
            sizes = fit(texts, box_w, box_h, fixed + gap * (len(texts) + 1), scale) if texts else []
            if sizes or not lines:
                break
            dropped.append(f"{sid}: {lines.pop()[:40]}")
            texts = ([(heading, px_h, WIDE)] if heading else []) + [(ln, px_l, BODY) for ln in lines]
        if texts and not sizes:
            sizes = [MIN_PX * scale] * len(texts)
        hs = sizes[0] if heading and sizes else px_h
        ls = sizes[1:] if heading else sizes
        block, photo_html = [], ""
        if photo:
            arch = f"{photo_w / 2:.0f}px {photo_w / 2:.0f}px {28 * scale:.0f}px {28 * scale:.0f}px"
            photo_html = (f'<div class="ph" style="width:{photo_w:.0f}px;height:{photo_h:.0f}px;border-radius:{arch};">'
                          f'<div id="{sid}-photo" style="background-image:url({photo});filter:{finish};"></div></div>')
        if heading:
            words = heading.split()
            if caption == "C04" and len(words) > 2:
                key = max(range(len(words)), key=lambda j: len(words[j]))
                words[key] = f'<span class="kw">{esc(words[key])}<i id="{sid}-kw"></i></span>'
                body = " ".join(esc(x) if "<span" not in x else x for x in words)
            elif caption == "C02":
                body = " ".join(f'<span class="w {sid}-w" style="display:inline-block;">{esc(x)}</span>' for x in words)
            else:
                body = esc(heading)
            block.append(f'<h2 class="h" id="{sid}-h" style="font-size:{hs:.0f}px;">{body}</h2>')
        if photo_html:
            block.append(photo_html)
        if caption == "C06" and lines:
            block.append(f'<div class="rule" id="{sid}-r"></div>')
        for j, ln in enumerate(lines):
            size = ls[j] if j < len(ls) else MIN_PX * scale
            en = lang == "both" and " / " in ln
            primary, _, secondary = ln.partition(" / ") if en else (ln, "", "")
            marker = '<span class="dot"></span>' if "V04" in plan.get("scenes", {}).get(sid, []) else ""
            block.append(f'<p class="l {sid}-l" id="{sid}-l{j}" style="font-size:{size:.0f}px;">{marker}{esc(primary)}</p>')
            if secondary:
                block.append(f'<p class="l en {sid}-l" id="{sid}-e{j}" '
                             f'style="font-size:{size * .82:.0f}px;">{esc(secondary)}</p>')
        parts.append(f'<div class="clip sc" id="{sid}" data-start="{start:g}" data-duration="{dur:g}">'
                     + "".join(block) + "</div>")
        if not worker_captions and narrated and sc.get("audio") and str(sc.get("narration") or "").strip():
            lane_h = h * LANE[1]
            for k, (text, a, b) in enumerate(caption_chunks(sc)):
                size = 52 * scale
                while size > MIN_PX * scale and wrap_lines(text, size, box_w, BODY) * size * 1.3 > lane_h:
                    size -= 2 * scale
                parts.append(f'<div class="clip cap" id="{sid}-c{k}" data-start="{a:g}" data-duration="{b - a:g}" '
                             f'style="font-size:{size:.0f}px;">{esc(text)}</div>')
                tw.append(f'tl.fromTo("#{sid}-c{k}",{{opacity:0}},{{opacity:1,duration:.18,ease:"power1.out"}},{a:g});')
                tw.append(f'tl.to("#{sid}-c{k}",{{opacity:0,duration:.12}},{max(a, b - .14):g});')
        t0, t1 = start, start + dur
        enter = 0.45 if transition != "M02" else 0.28
        dx = {"M09": 70, "M02": 150, "M08": 0}.get(transition, 70) * scale
        y0 = 26 * scale
        opening = ".35" if first else "0"
        if heading:
            if caption == "C02":
                tw.append(f'tl.fromTo(".{sid}-w",{{opacity:{opening},scale:.82,y:{y0:.0f}}},{{opacity:1,scale:1,y:0,duration:.4,'
                          f'ease:"back.out(1.5)",stagger:.07}},{t0 + .05:g});')
            else:
                dy = y0 if not dx else 0
                tw.append(f'tl.fromTo("#{sid}-h",{{opacity:{opening},x:{dx:.0f},y:{dy:.0f}}},{{opacity:1,x:0,y:0,'
                          f'duration:{enter + .1:g},ease:"power3.out"}},{t0 + .05:g});')
            if caption == "C04" and len(heading.split()) > 2:
                tw.append(f'tl.fromTo("#{sid}-kw",{{scaleX:0}},{{scaleX:1,duration:.6,ease:"power2.inOut"}},{t0 + .5:g});')
        if lines:
            gap_in = 0.5 if not sc.get("narration") else 0.35
            tw.append(f'tl.fromTo(".{sid}-l",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out",'
                      f'stagger:{gap_in:g}}},{t0 + .35:g});')
        if caption == "C06" and lines:
            tw.append(f'tl.fromTo("#{sid}-r",{{scaleX:0}},{{scaleX:1,duration:.5,ease:"power2.out"}},{t0 + .3:g});')
        if photo:
            zoom = 1.07 if ({"M03", "B05"} & set(plan.get("scenes", {}).get(sid, []))) else 1.03
            tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1}},{{scale:{zoom},duration:{dur:g},ease:"none"}},{t0:g});')
        fade = min(0.3, dur / 6)
        tw.append(f'tl.to("#{sid}",{{opacity:0,duration:{fade:g},ease:"power1.in"}},{t1 - fade:g});')
        if first and {"H02", "H08"} & set(plan.get("scenes", {}).get(sid, [])):
            tw.append('tl.fromTo("#flash",{opacity:.85},{opacity:0,duration:.22,ease:"power2.out"},0.04);')
    page = (f'<!doctype html>\n<html lang="{html_lang}" data-resolution="{resolution}">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width={w}, height={h}">\n<script src="{gsap}"></script>\n'
            f"<style>\n{chr(10).join(css)}\n</style>\n</head>\n<body>\n"
            f'<div id="root" data-composition-id="main" data-start="0" data-duration="{total:g}" data-width="{w}" '
            f'data-height="{h}">\n' + "\n".join(parts) + "\n</div>\n<script>\nconst tl = gsap.timeline({ paused: true });\n"
            + "\n".join(tw) + '\nwindow.__timelines = window.__timelines || {};\nwindow.__timelines["main"] = tl;\ntl.seek(0);\n'
            "</script>\n</body>\n</html>\n")
    chosen = {c for cs in plan.get("scenes", {}).values() for c in cs} | {v for v in video.values()}
    report = {"layout": "safe-layout", "built": sorted(chosen & BUILT),
              "not_built": sorted(chosen - BUILT - motion_auto.NATIVE_TEXT),
              "dropped_lines": dropped, "caption": caption, "transition": transition}
    return page, report


def layout_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The check's errors that mean words collide, are hidden or leave the frame."""
    code = re.compile(r"overlap|occlud|overflow|clipped|on_photo|out_of_|off_?(?:frame|canvas|screen)|cut_?off|truncat", re.I)
    said = re.compile(r"overlap|occlud|clipped|cut off|outside (?:the )?(?:frame|canvas|safe)", re.I)
    return [f for f in findings if f.get("code") != "probe_unavailable"
            and (code.search(str(f.get("code") or "")) or said.search(str(f.get("message") or "")))]

