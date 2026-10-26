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

GRADIENT = {"bright-editorial": "background:#fff9ed linear-gradient(145deg,#e0f5e9,#fff9ed 70%);",
            "continuous-line": "background:#fcf9ed linear-gradient(150deg,#e4f4e8,#fcf9ed);"}
GRADIENT_ALT = {"bright-editorial": "linear-gradient(215deg,#e0f5e9,#fff9ed 70%)",
                "continuous-line": "linear-gradient(210deg,#e4f4e8,#fcf9ed)"}
SAFE = {"left": 0.08, "right": 0.14, "top": 0.13, "bottom": 0.23}
LANE = (0.78, 0.115)              # the subtitle lane of a narrated film: top and height as fractions of the frame
GAP = 0.028                       # between blocks, as a fraction of the frame width
WIDE = 0.62                       # estimated average glyph width / font size for a bold heading (system sans, never narrower)
BODY = 0.56
MIN_PX = 44                       # on a 1080-wide frame (the contract's floor)
FILTERS = {"F02": "sepia(.16) saturate(1.05) brightness(1.02)", "F03": "saturate(.88) contrast(1.06) brightness(1.02)",
           "F05": "grayscale(1) contrast(1.15)", "F06": "saturate(1.35) contrast(1.08)",
           "F07": "saturate(.86) contrast(.93) brightness(1.06)", "F10": "contrast(1.06) saturate(1.04)"}
BUILT = motion_auto.BUILDABLE


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
    """The narration as two subtitle chunks (the references show two short lines at a time), timed to the recording: the
    second starts at the word the voice reaches half-way, from the real word times when the service gave them."""
    words = str(sc.get("narration") or "").split()
    start, span = float(sc["start"]), float(sc.get("audio_s") or sc["duration"])
    end = start + float(sc["duration"])
    if len(words) < 6:
        return [(" ".join(words), start, end)]
    mid = len(words) // 2
    timed = sc.get("words") or []
    if len(timed) == len(words):
        cut = start + float(timed[mid][0])
    else:
        total = sum(len(w) + 1 for w in words)
        cut = start + span * sum(len(w) + 1 for w in words[:mid]) / total
    cut = min(max(cut, start + 0.6), end - 0.4)
    return [(" ".join(words[:mid]), start, cut), (" ".join(words[mid:]), cut, end)]


def esc(s: str) -> str:
    return html_mod.escape(str(s), quote=False)


def rgba(colour: str, alpha: float) -> str:
    h = colour.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    try:
        return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"
    except ValueError:
        return f"rgba(0,0,0,{alpha})"


NUM = re.compile(r"\d[\d.,]*%?")


def inline(text: str, sid: str, numbers: bool) -> str:
    """Escaped text; with `numbers` every figure is its own inline-block so it can pop (V02)."""
    if not numbers:
        return esc(text)
    out, last = [], 0
    for m in NUM.finditer(text):
        out.append(esc(text[last:m.start()]))
        out.append(f'<span class="num {sid}-n">{esc(m.group(0))}</span>')
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


def typed(text: str, sid: str) -> str:
    """Every character in its own span (C03/C09): words stay whole, so wrapping is the same as plain text."""
    return " ".join('<span class="wd">' + "".join(f'<span class="ch {sid}-ch">{esc(c)}</span>' for c in word) + "</span>"
                    for word in text.split())


def quiet(text: str, sid: str, numbers: bool) -> str:
    """V10: the sentence in muted type, its last two words in full colour."""
    words = text.split()
    head, tail = " ".join(words[:-2]), " ".join(words[-2:])
    return (f'<span class="mut">{inline(head, sid, numbers)}</span> ' if head else "") + \
        f'<span class="str">{inline(tail, sid, numbers)}</span>'


def compose(*, scenes: list[dict[str, Any]], total: float, w: int, h: int, lang: str, plan: dict[str, Any],
            palette: dict[str, str], gsap: str, html_lang: str, resolution: str,
            design: str = "bright-editorial") -> tuple[str, dict[str, Any]]:
    design = design if design in GRADIENT else "bright-editorial"
    scale = w / 1080
    box_w = w * (1 - SAFE["left"] - SAFE["right"])
    teaching = [s for s in scenes if s.get("id") != "brand-outro"]
    narrated = any(s.get("audio") for s in teaching)
    box_h = h * ((LANE[0] - 0.02 if narrated else 1 - SAFE["bottom"]) - SAFE["top"])
    gap = w * GAP
    video = plan.get("video") or {}
    captions = {"C02", "C03", "C04", "C05", "C06", "C07", "C09", "C10"}
    caption = video.get("captions") if video.get("captions") in captions else "C05"
    transition = video.get("transition") or "M09"
    finish = FILTERS.get(video.get("finish") or "", FILTERS["F07"])
    accent, ink = palette["accent"], palette["ink"]
    bd = 84 * scale                                   # the numbered badge of B04
    step_pad = bd + 22 * scale
    pad_card = 22 * scale
    card_w = (box_w - gap) / 2 - 2 * pad_card
    trk_h = max(10, 16 * scale)
    rule_h = max(3, 5 * scale)
    dropped: list[str] = []
    mono = "ui-monospace,Menlo,Consolas,monospace"
    css = [
        f"html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{palette['ground']};}}",
        f'body{{font-family:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;color:{ink};}}',
        f"#root{{position:absolute;left:0;top:0;width:{w}px;height:{h}px;overflow:hidden;{GRADIENT[design]}}}",
        f".sc{{position:absolute;left:{w * SAFE['left']:.0f}px;top:{h * SAFE['top']:.0f}px;width:{box_w:.0f}px;"
        f"height:{box_h:.0f}px;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;"
        f"gap:{gap:.0f}px;overflow:hidden;}}",
        ".ph{position:relative;align-self:center;overflow:hidden;flex:none;}",
        f".cap{{position:absolute;left:{w * SAFE['left']:.0f}px;top:{h * LANE[0]:.0f}px;width:{box_w:.0f}px;"
        f"height:{h * LANE[1]:.0f}px;display:flex;align-items:center;justify-content:center;text-align:center;"
        f"font-weight:500;line-height:1.3;color:{ink};overflow-wrap:anywhere;}}",
        ".ph>div{position:absolute;inset:0;background-size:cover;background-position:center;}",
        ".tl{position:absolute;width:33.4%;height:33.4%;background-size:300% 300%;display:block;}",
        f".h{{margin:0;font-weight:800;line-height:1.12;color:{ink};overflow-wrap:anywhere;max-width:100%;}}",
        f".l{{margin:0;font-weight:600;line-height:1.18;color:{ink};overflow-wrap:anywhere;max-width:100%;}}",
        f".l.en{{color:{accent};font-weight:600;}}",
        f".l.mono{{font-family:{mono};font-weight:600;}}",
        ".wd{display:inline-block;white-space:nowrap;}",
        f".mut{{opacity:.6;font-weight:500;}} .str{{font-weight:800;color:{ink};}}",
        ".num{display:inline-block;}",
        f".kw{{position:relative;display:inline-block;isolation:isolate;}} "
        f".kw i{{position:absolute;left:0;right:0;bottom:.04em;height:.34em;"
        f"background:{accent};opacity:.28;transform-origin:0 50%;}}",
        ".k7{display:inline-block;transform-origin:50% 60%;}",
        f".rule{{flex:none;height:{rule_h:.0f}px;width:{w * .18:.0f}px;background:{accent};transform-origin:0 50%;}}",
        f".dot{{display:inline-block;width:.42em;height:.42em;border-radius:50%;background:{accent};"
        "margin-right:.45em;vertical-align:middle;}",
        f".flash{{position:absolute;left:0;top:0;width:{w}px;height:{h}px;background:{accent};opacity:0;"
        "pointer-events:none;z-index:30;}",
        f".fx{{position:absolute;left:0;top:0;width:{w}px;height:{h}px;overflow:hidden;pointer-events:none;}}",
        f".gridx{{position:absolute;inset:0;background-image:"
        f"repeating-linear-gradient(0deg,{rgba(accent, .11)} 0 2px,transparent 2px {72 * scale:.0f}px),"
        f"repeating-linear-gradient(90deg,{rgba(accent, .11)} 0 2px,transparent 2px {72 * scale:.0f}px);}}",
        f".ln{{position:absolute;left:-12%;width:76%;height:{max(2, 3 * scale):.0f}px;background:{rgba(accent, .22)};"
        "transform:rotate(-16deg);}",
        ".pl{position:absolute;top:0;width:50.5%;height:100%;background:#eef8f1;z-index:6;}",
        ".cd{position:absolute;inset:0;z-index:5;pointer-events:none;}",
        f".cd span{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;opacity:0;"
        f"font-size:{360 * scale:.0f}px;font-weight:800;color:{accent};}}",
        f".trk{{flex:none;display:flex;gap:{10 * scale:.0f}px;width:100%;height:{trk_h:.0f}px;}}",
        f".sg{{flex:1;position:relative;overflow:hidden;border-radius:{trk_h:.0f}px;background:{rgba(accent, .18)};}}",
        f".sg b{{position:absolute;inset:0;background:{accent};transform-origin:0 50%;transform:scaleX(0);}}",
        f".cards{{flex:none;display:flex;gap:{gap:.0f}px;width:100%;}}",
        f".card{{flex:1;min-width:0;box-sizing:border-box;padding:{pad_card:.0f}px;border-radius:{24 * scale:.0f}px;"
        f"background:rgba(255,255,255,.72);border:{max(2, 3 * scale):.0f}px solid {rgba(accent, .45)};}}",
        f".stp{{position:relative;box-sizing:border-box;width:100%;padding-left:{step_pad:.0f}px;min-height:{bd:.0f}px;}}",
        f".bd{{position:absolute;left:0;top:0;width:{bd:.0f}px;height:{bd:.0f}px;border-radius:50%;background:{accent};"
        f"color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:{46 * scale:.0f}px;}}",
        f".cn{{position:absolute;left:{bd / 2 - 1.5 * scale:.0f}px;top:{bd:.0f}px;bottom:-{gap:.0f}px;"
        f"width:{max(3, 4 * scale):.0f}px;"
        f"background:{rgba(accent, .45)};transform-origin:50% 0;}}",
    ]
    parts, tw = [], []
    # the background is a soft diagonal gradient and nothing else (Wan, 26 Oct 2026: "I don't want circles in the background
    # but more like gradient"): the reference films' own gradients, with a second one that fades in and out for slow movement
    parts.append(f'<div id="grad2" style="position:absolute;left:0;top:0;width:{w}px;height:{h}px;opacity:0;'
                 f'background:{GRADIENT_ALT[design]};"></div>')
    tw.append(f'tl.to("#grad2",{{opacity:.65,duration:{total / 2:g},ease:"sine.inOut"}},0);')
    tw.append(f'tl.to("#grad2",{{opacity:0,duration:{total / 2:g},ease:"sine.inOut"}},{total / 2:g});')
    parts.append('<div class="flash" id="flash"></div>')
    for idx, sc in enumerate(teaching):
        sid, start, dur = sc["id"], float(sc["start"]), float(sc["duration"])
        first = idx == 0
        eff = set(plan.get("scenes", {}).get(sid, []))
        lines = [x for x in (sc.get("lines") or []) if str(x).strip()]
        heading = str(sc.get("heading") or "").strip()
        photo = sc.get("photo")
        photo_h = (h * 0.32 if h >= w else h * 0.36) if photo else 0
        photo_w = min(box_w, photo_h * 0.8)
        px_h = (104 if len(heading.split()) <= 4 else 88 if len(heading.split()) <= 7 else 72 if len(heading.split()) <= 11
                else 60) * scale
        px_l = 50 * scale
        is_typed = caption in {"C03", "C09"}
        lead = (1.1 if "H05" in eff else 0.8 if "H10" in eff else 0.4 if "M04" in eff else 0.3 if "H06" in eff else 0.0)
        if lead and dur < 3.6:
            lead = min(lead, 0.4)

        def column(lines_now: list[str], eff: set[str] = eff, heading: str = heading, px_h: float = px_h, px_l: float = px_l,
                   is_typed: bool = is_typed) -> tuple[list[tuple[str, float, float]], bool, bool, bool]:
            # two option cards need every word of the pair to fit a half-width card: a word wider than that would break mid-word
            longest = max((len(x) for ln in lines_now[:2] for x in ln.split()), default=0)
            cards = ("V05" in eff and len(lines_now) >= 2
                     and longest * MIN_PX * scale * BODY * 1.05 <= card_w)
            steps = "B04" in eff and not cards and bool(lines_now)
            track = "V06" in eff and len(lines_now) >= 2 and not cards
            rest = lines_now[2:] if cards else lines_now
            f = BODY * box_w / (box_w - step_pad) if steps else (0.62 if is_typed and caption == "C09" else BODY)
            out = ([(heading, px_h, WIDE)] if heading else [])
            if cards:
                out.append((max(lines_now[:2], key=len), px_l * 0.9, BODY * box_w / max(card_w, 1)))
            return out + [(ln, px_l, f) for ln in rest], cards, steps, track

        while True:
            texts, cards, steps, track = column(lines)
            rule = ("H10" in eff or (caption == "C06" and bool(lines))) and bool(heading or lines)
            extra = (photo_h + gap if photo else 0) + (trk_h + gap if track else 0) + (rule_h + gap if rule else 0) \
                + (2 * pad_card if cards else 0)
            sizes = fit(texts, box_w, box_h, extra + gap * (len(texts) + 1), scale) if texts else []
            if sizes or not lines:
                break
            dropped.append(f"{sid}: {lines.pop()[:40]}")
        if texts and not sizes:
            sizes = [MIN_PX * scale] * len(texts)
        hs = sizes[0] if heading and sizes else px_h
        ls = sizes[1:] if heading else sizes
        block, photo_html = [], ""
        if photo:
            ring = f"box-shadow:0 0 0 {max(3, 5 * scale):.0f}px {accent};" if "L06" in eff else ""
            arch = f"{photo_w / 2:.0f}px {photo_w / 2:.0f}px {28 * scale:.0f}px {28 * scale:.0f}px"
            if "X06" in eff:
                inner = "".join(f'<i class="tl {sid}-t" style="left:{c * 100 / 3:.3f}%;top:{r * 100 / 3:.3f}%;'
                                f'background-image:url({photo});background-position:{c * 50}% {r * 50}%;"></i>'
                                for r in range(3) for c in range(3))
                inner = f'<div id="{sid}-photo" style="filter:{finish};">{inner}</div>'
            else:
                inner = f'<div id="{sid}-photo" style="background-image:url({photo});filter:{finish};"></div>'
            photo_html = (f'<div class="ph" id="{sid}-ph" style="width:{photo_w:.0f}px;height:{photo_h:.0f}px;'
                          f'border-radius:{arch};{ring}">{inner}</div>')
        numbers = "V02" in eff
        if rule and "H10" in eff:
            block.append(f'<div class="rule" id="{sid}-r0"></div>')
        if heading:
            words = heading.split()
            style = f"font-size:{hs:.0f}px;" + ('font-family:Georgia,"Times New Roman",serif;' if "H10" in eff else "")
            # the key word is an inline-block: only one that fits the column whole may be wrapped, or it would break inside
            fits = [j for j in range(len(words)) if len(words[j]) * hs * WIDE * 1.08 <= box_w * 0.92]
            key = max(fits, key=lambda j: len(words[j])) if fits else -1
            if caption == "C04" and len(words) > 2 and key >= 0:
                words[key] = f'<span class="kw">{esc(words[key])}<i id="{sid}-kw"></i></span>'
                body = " ".join(esc(x) if "<span" not in x else x for x in words)
            elif caption == "C07" and len(words) > 1 and key >= 0:
                # the key word bursts alone: the other words arrive only once it has settled, so nothing is ever crossed
                words = [f'<span class="ow {sid}-ow">{esc(x)}</span>' if j != key else
                         f'<span class="k7" id="{sid}-k7">{esc(x)}</span>' for j, x in enumerate(words)]
                body = " ".join(words)
            elif caption == "C02":
                body = " ".join(f'<span class="w {sid}-w" style="display:inline-block;">{inline(x, sid, numbers)}</span>'
                                for x in words)
            else:
                body = inline(heading, sid, numbers)
            block.append(f'<h2 class="h" id="{sid}-h" style="{style}">{body}</h2>')
        if photo_html:
            block.append(photo_html)
        if track:
            block.append(f'<div class="trk" id="{sid}-trk">' + "".join(
                f'<span class="sg"><b id="{sid}-f{k}"></b></span>' for k in range(len(lines))) + "</div>")
        if caption == "C06" and lines and "H10" not in eff:
            block.append(f'<div class="rule" id="{sid}-r"></div>')

        def para(ln: str, size: float, j: int, klass: str, sid: str = sid, eff: set[str] = eff, steps: bool = steps,
                 numbers: bool = numbers, is_typed: bool = is_typed) -> str:
            en = lang == "both" and " / " in ln
            primary, _, secondary = ln.partition(" / ") if en else (ln, "", "")
            marker = '<span class="dot"></span>' if ("V04" in eff and not steps) else ""
            if is_typed:
                inner_html = typed(primary, sid)
            elif "V10" in eff:
                inner_html = quiet(primary, sid, numbers)
            else:
                inner_html = inline(primary, sid, numbers)
            mono_cls = " mono" if caption == "C09" else ""
            out = f'<p class="l{mono_cls} {klass}" id="{sid}-l{j}" style="font-size:{size:.0f}px;">{marker}{inner_html}</p>'
            if secondary:
                out += (f'<p class="l en {klass}" id="{sid}-e{j}" style="font-size:{size * .82:.0f}px;">'
                        f'{inline(secondary, sid, numbers)}</p>')
            return out

        lcls = f"{sid}-lt" if is_typed else f"{sid}-l"
        shown = 0
        if cards:
            sz = ls[0] if ls else MIN_PX * scale
            block.append(f'<div class="cards" id="{sid}-cards">' + "".join(
                f'<div class="card {sid}-cd{k}">{para(lines[k], sz, k, lcls)}</div>' for k in (0, 1)) + "</div>")
            shown = 2
        rest_sizes = ls[1:] if cards else ls
        for j, ln in enumerate(lines[shown:], start=shown):
            size = rest_sizes[j - shown] if j - shown < len(rest_sizes) else MIN_PX * scale
            if steps:
                last = j == len(lines) - 1
                block.append(f'<div class="stp {sid}-l" id="{sid}-s{j}"><span class="bd {sid}-bd">{j + 1}</span>'
                             + ("" if last else f'<i class="cn {sid}-cn"></i>') + para(ln, size, j, f"{sid}-lx") + "</div>")
            else:
                block.append(para(ln, size, j, lcls))
        extras = ""
        if "H06" in eff:
            extras += f'<div class="pl" id="{sid}-pa" style="left:0"></div><div class="pl" id="{sid}-pb" style="right:0"></div>'
        if "H05" in eff:
            digits = "".join(f'<span id="{sid}-cd{n}">{n}</span>' for n in (3, 2, 1))
            extras += f'<div class="cd" id="{sid}-cd">{digits}</div>'
        fx = ""
        if "X10" in eff:
            fx += f'<div class="gridx" id="{sid}-gx"></div>'
        if "B08" in eff:
            fx += "".join(f'<div class="ln {sid}-ln" style="top:{pos}%;"></div>' for pos in (24, 50, 76))
        if fx:
            parts.append(f'<div class="clip fx" id="{sid}-fx" data-start="{start:g}" data-duration="{dur:g}">{fx}</div>')
        parts.append(f'<div class="clip sc" id="{sid}" data-start="{start:g}" data-duration="{dur:g}">'
                     + "".join(block) + extras + "</div>")
        if narrated and sc.get("audio") and str(sc.get("narration") or "").strip():
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
        opening = ".35" if first and not lead else "0"
        th = t0 + .05 + lead
        # openers that hold the scene back for a moment: the countdown, the split panels, the silent pause, the flash
        if "H05" in eff:
            for i, n in enumerate((3, 2, 1)):
                at = t0 + i * 0.36
                tw.append(f'tl.fromTo("#{sid}-cd{n}",{{opacity:0,scale:2.2}},{{opacity:1,scale:1,duration:.2,ease:"power3.out"}},{at:g});')
                tw.append(f'tl.to("#{sid}-cd{n}",{{opacity:0,scale:.8,duration:.1}},{at + .26:g});')
        if "H06" in eff:
            tw.append(f'tl.fromTo("#{sid}-pa",{{xPercent:0}},{{xPercent:-101,duration:.5,ease:"power3.inOut"}},{t0 + .1:g});')
            tw.append(f'tl.fromTo("#{sid}-pb",{{xPercent:0}},{{xPercent:101,duration:.5,ease:"power3.inOut"}},{t0 + .1:g});')
        if "H10" in eff:
            tw.append(f'tl.fromTo("#{sid}-r0",{{scaleX:0}},{{scaleX:1,duration:.7,ease:"power2.out"}},{t0 + .05:g});')
        if "M04" in eff:
            tw.append(f'tl.fromTo("#flash",{{opacity:.35}},{{opacity:0,duration:.4,ease:"power2.out"}},{t0:g});')
            if heading:
                tw.append(f'tl.fromTo("#{sid}-h",{{scale:1.07}},{{scale:1,duration:.35,ease:"power2.out"}},{t0 + lead:g});')
        if "X10" in eff:
            tw.append(f'tl.fromTo("#{sid}-gx",{{clipPath:"inset(0 100% 0 0)"}},{{clipPath:"inset(0 0% 0 0)",duration:.9,'
                      f'ease:"power2.inOut"}},{t0:g});')
        if "B08" in eff:
            tw.append(f'tl.fromTo(".{sid}-ln",{{x:{-w * .06:.0f}}},{{x:{w * .16:.0f},duration:{dur:g},ease:"none"}},{t0:g});')
        if heading:
            if caption == "C02":
                tw.append(f'tl.fromTo(".{sid}-w",{{opacity:{opening},scale:.82,y:{y0:.0f}}},{{opacity:1,scale:1,y:0,duration:.4,'
                          f'ease:"back.out(1.5)",stagger:.07}},{th:g});')
            elif "M07" in eff:
                tw.append(f'tl.fromTo("#{sid}-h",{{opacity:0}},{{opacity:1,duration:.12}},{th:g});')
                jolt = ",".join(f"{{x:{x * scale:.0f},duration:.05}}" for x in (-16, 12, -7, 3, 0))
                tw.append(f'tl.to("#{sid}-h",{{keyframes:[{jolt}]}},{th + .1:g});')
            else:
                dy = y0 if not dx else 0
                tw.append(f'tl.fromTo("#{sid}-h",{{opacity:{opening},x:{dx:.0f},y:{dy:.0f}}},{{opacity:1,x:0,y:0,'
                          f'duration:{enter + .1:g},ease:"power3.out"}},{th:g});')
            if f'id="{sid}-kw"' in "".join(block):
                tw.append(f'tl.fromTo("#{sid}-kw",{{scaleX:0}},{{scaleX:1,duration:.6,ease:"power2.inOut"}},{th + .45:g});')
            if f'id="{sid}-k7"' in "".join(block):
                est = max(len(x) for x in heading.split()) * hs * WIDE
                burst = min(2.3, max(1.2, box_w * 0.96 / max(est, 1)))
                tw.append(f'tl.fromTo("#{sid}-k7",{{scale:{burst:.2f},opacity:0}},{{scale:1,opacity:1,duration:.5,ease:"back.out(1.6)"}},'
                          f'{th:g});')
                tw.append(f'tl.fromTo(".{sid}-ow",{{opacity:0}},{{opacity:1,duration:.3,ease:"power1.out"}},{th + .55:g});')
        tl_start = t0 + .35 + lead
        gap_in = 0.5 if not sc.get("narration") else 0.35
        if cards:
            for k, side in ((0, -1), (1, 1)):
                tw.append(f'tl.fromTo(".{sid}-cd{k}",{{opacity:0,x:{side * box_w * .5:.0f}}},'
                          f'{{opacity:1,x:0,duration:.6,ease:"power3.out"}},{tl_start:g});')
        if is_typed and lines:
            chars = sum(len(re.sub(r"\s", "", ln.partition(" / ")[0])) for ln in lines)
            per = max(0.012, min(0.045, min(3.0, dur * .6) / max(chars, 1)))
            tw.append(f'tl.fromTo(".{sid}-ch",{{opacity:0}},{{opacity:1,duration:.01,stagger:{per:.3f}}},{tl_start:g});')
        elif lines[shown:]:
            tw.append(f'tl.fromTo(".{sid}-l",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out",'
                      f'stagger:{gap_in:g}}},{tl_start:g});')
        if steps:
            tw.append(f'tl.fromTo(".{sid}-bd",{{scale:0}},{{scale:1,duration:.4,ease:"back.out(2)",stagger:{gap_in:g}}},{tl_start:g});')
            tw.append(f'tl.fromTo(".{sid}-cn",{{scaleY:0}},{{scaleY:1,duration:.4,ease:"power2.out",stagger:{gap_in:g}}},'
                      f'{tl_start + .2:g});')
        if track:
            for k in range(len(lines)):
                tw.append(f'tl.to("#{sid}-f{k}",{{scaleX:1,duration:.5,ease:"power2.out"}},{tl_start + k * gap_in:g});')
        if numbers:
            tw.append(f'tl.fromTo(".{sid}-n",{{scale:0}},{{scale:1,duration:.5,ease:"back.out(2.4)",stagger:.18}},'
                      f'{tl_start + .3:g});')
        if caption == "C06" and lines and "H10" not in eff:
            tw.append(f'tl.fromTo("#{sid}-r",{{scaleX:0}},{{scaleX:1,duration:.5,ease:"power2.out"}},{t0 + .3 + lead:g});')
        if photo:
            zoom = 1.07 if ({"M03", "B05"} & eff) else 1.03
            if lead:
                tw.append(f'tl.fromTo("#{sid}-ph",{{opacity:0}},{{opacity:1,duration:.35}},{t0 + lead:g});')
            if "L06" in eff:
                tw.append(f'tl.fromTo("#{sid}-ph",{{scale:1.16,opacity:0}},{{scale:1,opacity:1,duration:.7,ease:"power3.out"}},'
                          f'{t0 + .1 + lead:g});')
                tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1.45}},{{scale:{zoom},duration:{dur:g},ease:"power2.out"}},'
                          f'{t0 + lead:g});')
            elif "X06" in eff:
                far = f"{220 * scale:.0f}"
                tw.append(f'tl.fromTo(".{sid}-t",{{x:(i)=>[-1,1,0][i%3]*{far},y:(i)=>[1,-1,0][Math.floor(i/3)%3]*{far},'
                          f'rotation:(i)=>(i%2?1:-1)*20,opacity:0}},{{x:0,y:0,rotation:0,opacity:1,duration:.7,'
                          f'ease:"back.out(1.3)",stagger:.05}},{t0 + .1 + lead:g});')
            else:
                tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1}},{{scale:{zoom},duration:{dur:g},ease:"none"}},{t0:g});')
            if "B05" in eff and "X06" not in eff and "L06" not in eff:
                tw.append(f'tl.fromTo("#{sid}-photo",{{xPercent:-2.5}},{{xPercent:2.5,duration:{dur:g},ease:"none"}},{t0:g});')
        fade = min(0.3, dur / 6)
        tw.append(f'tl.to("#{sid}",{{opacity:0,duration:{fade:g},ease:"power1.in"}},{t1 - fade:g});')
        if "X10" in eff or "B08" in eff:
            tw.append(f'tl.to("#{sid}-fx",{{opacity:0,duration:{fade:g},ease:"power1.in"}},{t1 - fade:g});')
        if first and {"H02", "H08"} & eff:
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

