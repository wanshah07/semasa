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

from . import motion_auto, motion_concepts

# the ambient background of every scene, chosen per film (Wan, 26 Oct 2026: "tone color like attachment 3 is preferable (remain
# the line), let me choose the background ambient colour in semasa"): the reference films' soft mint-to-cream diagonal is the
# default; the others are the same gradient in another light tone. The line grid sits on top of each (see `grid-all`).
AMBIENTS = {
    "mint": ("#e0f5e9", "#fff9ed", "#e4f4e8", "#fcf9ed", "Mint (rujukan)", "Mint (reference)"),
    "lime": ("#dff0c2", "#fbf7da", "#e2f0c6", "#fbf8de", "Kuning-hijau", "Yellow-green"),
    "cream": ("#fdf0d3", "#fffaf0", "#fdf1d8", "#fffaf0", "Krim", "Cream"),
    "sky": ("#dcecf7", "#f6fbff", "#dfedf7", "#f6fbff", "Langit", "Sky"),
    "blush": ("#fbe3e6", "#fff8f3", "#fbe6e8", "#fff8f3", "Merah jambu lembut", "Soft blush"),
}
DEFAULT_AMBIENT = "mint"


def gradients(design: str, ambient: str) -> tuple[str, str]:
    """The film's background rule and the second gradient that fades in and out over it."""
    a, b, a2, b2 = AMBIENTS.get(ambient, AMBIENTS[DEFAULT_AMBIENT])[:4]
    if design == "continuous-line":
        return f"background:{b2} linear-gradient(150deg,{a2},{b2});", f"linear-gradient(210deg,{a2},{b2})"
    return f"background:{b} linear-gradient(145deg,{a},{b} 70%);", f"linear-gradient(215deg,{a},{b} 70%)"


GRADIENT = {d: gradients(d, DEFAULT_AMBIENT)[0] for d in ("bright-editorial", "continuous-line")}
GRADIENT_ALT = {d: gradients(d, DEFAULT_AMBIENT)[1] for d in ("bright-editorial", "continuous-line")}
SAFE = {"left": 0.08, "right": 0.14, "top": 0.13, "bottom": 0.23}
LANE = (0.78, 0.115)              # the subtitle lane of a narrated film: top and height as fractions of the frame
GAP = 0.028                       # between blocks, as a fraction of the frame width
WIDE = 0.62                       # estimated average glyph width / font size for a bold heading (system sans, never narrower)
BODY = 0.56
MIN_PX = 44                       # on a 1080-wide frame (the contract's floor)
FILTERS = {"F01": "contrast(1.05) saturate(1.12) brightness(1.03)",
           "F04": "contrast(1.1) saturate(.95) hue-rotate(-14deg) brightness(.98)",
           "F02": "sepia(.16) saturate(1.05) brightness(1.02)", "F03": "saturate(.88) contrast(1.06) brightness(1.02)",
           "F05": "grayscale(1) contrast(1.15)", "F06": "saturate(1.35) contrast(1.08)",
           "F07": "saturate(.86) contrast(.93) brightness(1.06)", "F10": "contrast(1.06) saturate(1.04)"}
BUILT = motion_auto.BUILDABLE


def wrap_lines(text: str, px: float, width: float, factor: float) -> int:
    """How many lines `text` takes at `px` in a column `width` wide (greedy by word, estimated glyph width). A token wider than
    the column is broken inside (overflow-wrap) and takes as many lines as it needs."""
    n, cur = 1, 0.0
    space = px * factor * 0.5
    for word in text.split():
        wpx = len(word) * px * factor
        if wpx > width:
            n += (1 if cur else 0) + int(-(-wpx // width)) - 1
            cur = wpx - (int(-(-wpx // width)) - 1) * width
            continue
        if cur and cur + space + wpx > width:
            n += 1
            cur = wpx
        else:
            cur += (space if cur else 0) + wpx
    return n


def fit(blocks: list[tuple[str, float, float]], width: float, height: float, fixed: float, scale: float) -> list[float]:
    """Font sizes (px) for text blocks [(text, first_px, factor)] so the column plus `fixed` pixels of other blocks fits
    `height`. Every size scales together and never goes under the readable floor; a block is also never set so large that its
    longest word would be split across two lines. The caller drops lines if it cannot fit."""
    floor = MIN_PX * scale
    caps = [width / (max((len(x) for x in t.split()), default=1) * f * 1.04) for t, _, f in blocks]
    k = 1.0
    while True:
        sizes = [max(floor, min(px * k, cap)) for (_, px, _), cap in zip(blocks, caps, strict=True)]
        used = fixed + sum(wrap_lines(t, s, width, f) * s * 1.18 + s * 0.35 for (t, _, f), s in zip(blocks, sizes, strict=True))
        if used <= height or all(s <= floor + 0.01 for s in sizes):
            return sizes if used <= height else []
        k *= 0.94


def phrase_cuts(words: list[str], k: int) -> list[int]:
    """Where to cut `words` into k subtitles: near equal parts, but after a comma, full stop or similar when one is within four
    words, so a subtitle never ends in the middle of a phrase (Wan, 26 Oct 2026: "not hanging")."""
    n, cuts = len(words), []
    for i in range(1, k):
        ideal = round(n * i / k)
        lo = max((cuts[-1] if cuts else 0) + 2, ideal - 4)
        hi = min(n - 2, ideal + 4)
        best, best_score = None, 99.0
        for j in range(lo, hi + 1):
            if re.search(r"[,.;:!?…—–]$", words[j - 1]):
                score = abs(j - ideal) - (2 if re.search(r"[.!?…]$", words[j - 1]) else 0)
                if score < best_score:
                    best, best_score = j, score
        cut = best if best is not None else max(lo, min(hi, ideal))
        if (not cuts or cut > cuts[-1]) and 0 < cut < n:
            cuts.append(cut)
    return cuts


def caption_chunks(sc: dict[str, Any]) -> list[tuple[str, float, float]]:
    """The narration as short subtitles (the references show two short lines at a time), about nine words each, cut at a
    phrase boundary where there is one and timed to the recording: each starts at the word the voice reaches, from the real
    word times when the service gave them."""
    words = str(sc.get("narration") or "").split()
    start, span = float(sc["start"]), float(sc.get("audio_s") or sc["duration"])
    end = start + float(sc["duration"])
    if len(words) < 6:
        return [(" ".join(words), start, end)]
    k = min(4, max(2, -(-len(words) // 9)))
    cuts = phrase_cuts(words, k)
    timed = sc.get("words") or []
    weights = [len(w) + 1 for w in words]
    total = sum(weights)
    bounds = [0, *cuts, len(words)]
    times = [start]
    for cut in cuts:
        t = start + (float(timed[cut][0]) if len(timed) == len(words) else span * sum(weights[:cut]) / total)
        times.append(min(max(t, times[-1] + 0.5), end - 0.4 * (len(bounds) - len(times) - 1)))
    times.append(end)
    return [(" ".join(words[bounds[i]:bounds[i + 1]]), times[i], times[i + 1]) for i in range(len(bounds) - 1)]


def esc(s: str) -> str:
    return html_mod.escape(str(s), quote=False)


def plain(text: Any) -> str:
    """Words only: the script writer sometimes answers with markup (`<br>`, `<span class="accent">`), which would be drawn as
    letters on the film and read aloud by the voice. Line breaks become spaces and every tag goes."""
    out = re.sub(r"<\s*br\s*/?\s*>", " ", str(text or ""), flags=re.I)
    out = re.sub(r"</?\s*[a-zA-Z][^>]*>", "", out)
    return " ".join(html_mod.unescape(out).split())


def rgba(colour: str, alpha: float) -> str:
    h = colour.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    try:
        return f"rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{alpha})"
    except ValueError:
        return f"rgba(0,0,0,{alpha})"


NUM = re.compile(r"\d[\d.,]*%?")
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
STAT = re.compile(r"(?<![\d.,])\d{1,7}(?![\d.,])")
PCT = re.compile(r"(\d+(?:[.,]\d+)?)\s?%")
CAPTIONS = {"C01", "C02", "C03", "C04", "C05", "C06", "C07", "C09", "C10"}
TRANSITIONS = {"M02", "M08", "M09"}
# the hook chip that opens the first scene (Wan, 26 Oct 2026: "do not forget the hook ... Did you know, Warning, Breaking News")
HOOKS = {"know": ("TAHUKAH ANDA?", "DID YOU KNOW?", None), "warn": ("AMARAN", "WARNING", "#c0392b"),
         "news": ("BERITA TERKINI", "BREAKING NEWS", "#1d5fbf")}
TAGS = {"bm": ("KAJIAN RUJUKAN", "FAKTA"), "both": ("KAJIAN RUJUKAN", "FAKTA"), "en": ("SOURCE STUDY", "FACT")}


def inline(text: str, sid: str, numbers: bool, counts: list[tuple[str, int]] | None = None) -> str:
    """Escaped text. With `numbers` every figure is its own inline-block so it can pop (V02); with `counts` a plain whole number
    gets an id and is recorded so it can count up to the number printed (P03): nothing is counted that is not in the words."""
    if not numbers and counts is None:
        return esc(text)
    out, last = [], 0
    for m in NUM.finditer(text):
        out.append(esc(text[last:m.start()]))
        token = m.group(0)
        body, pct = (token[:-1], "%") if token.endswith("%") else (token, "")
        body = body.rstrip(".,")
        tail = token[len(body) + len(pct):] if not pct else ""
        cls = "num " + f"{sid}-n" if numbers else "num"
        countable = body.isdigit() and 2 <= int(body) <= 9_999_999 and not (len(body) == 4 and YEAR.fullmatch(body))
        if counts is not None and countable:
            uid = f"{sid}-cu{len(counts)}"
            counts.append((uid, int(body)))
            out.append(f'<span class="{cls}">' + f'<span id="{uid}">{body}</span>{pct}{esc(tail)}</span>')
        else:
            out.append(f'<span class="{cls}">{esc(token)}</span>')
        last = m.end()
    out.append(esc(text[last:]))
    return "".join(out)


def typed(text: str, sid: str) -> str:
    """Every character in its own span (C03/C09): words stay whole, so wrapping is the same as plain text."""
    return " ".join('<span class="wd">' + "".join(f'<span class="ch {sid}-ch">{esc(c)}</span>' for c in word) + "</span>"
                    for word in text.split())


def quiet(text: str, sid: str, numbers: bool, counts: list[tuple[str, int]] | None = None) -> str:
    """V10: the sentence in muted type, its last two words in full colour."""
    words = text.split()
    head, tail = " ".join(words[:-2]), " ".join(words[-2:])
    return (f'<span class="mut">{inline(head, sid, numbers, counts)}</span> ' if head else "") + \
        f'<span class="str">{inline(tail, sid, numbers, counts)}</span>'


def label_of(line: str, token: str) -> str:
    return re.sub(r"\s{2,}", " ", line.replace(token, " ")).strip(" :-–—,.;")


def compose(*, scenes: list[dict[str, Any]], total: float, w: int, h: int, lang: str, plan: dict[str, Any],
            palette: dict[str, str], gsap: str, html_lang: str, resolution: str,
            design: str = "bright-editorial", ambient: str = DEFAULT_AMBIENT) -> tuple[str, dict[str, Any]]:
    design = design if design in GRADIENT else "bright-editorial"
    ambient = ambient if ambient in AMBIENTS else DEFAULT_AMBIENT
    grad_main, grad_alt = gradients(design, ambient)
    scale = w / 1080
    box_w = w * (1 - SAFE["left"] - SAFE["right"])
    teaching = [s for s in scenes if s.get("id") != "brand-outro"]
    narrated = any(s.get("audio") for s in teaching)
    # a silent film has no subtitle lane, so its column takes the room (Wan: "jangan bagi window terlalu kosong")
    top_frac = SAFE["top"] if narrated else 0.11
    box_h = h * ((LANE[0] - 0.02 if narrated else 0.85) - top_frac)
    gap = w * GAP
    video = plan.get("video") or {}
    caption = video.get("captions") if video.get("captions") in CAPTIONS else "C05"
    transition = video.get("transition") or "M09"
    finish_code = video.get("finish") if video.get("finish") in FILTERS else "F07"
    study = plan.get("study") or None
    accent, ink = palette["accent"], palette["ink"]
    bd = 84 * scale                                   # the numbered badge of B04
    step_pad = bd + 22 * scale
    pad_card = 22 * scale
    card_w = (box_w - gap) / 2 - 2 * pad_card
    trk_h = max(10, 16 * scale)
    rule_h = max(3, 5 * scale)
    fs_d = 46 * scale                                 # the type of every data block: above the 44px floor
    fs_p = 34 * scale                                 # the reference footnote
    arrow_h = 30 * scale
    dropped: list[str] = []
    applied: set[str] = set()
    mono = "ui-monospace,Menlo,Consolas,monospace"
    css = [
        f"html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:{palette['ground']};}}",
        f'body{{font-family:"Inter",system-ui,-apple-system,"Segoe UI",sans-serif;color:{ink};}}',
        f"#root{{position:absolute;left:0;top:0;width:{w}px;height:{h}px;overflow:hidden;{grad_main}}}",
        f".sc{{position:absolute;left:{w * SAFE['left']:.0f}px;top:{h * top_frac:.0f}px;width:{box_w:.0f}px;"
        f"height:{box_h:.0f}px;display:flex;flex-direction:column;justify-content:space-evenly;align-items:flex-start;"
        f"gap:{gap:.0f}px;overflow:hidden;}}",
        # a photo has no border line: bigger, and its edges fade into the background (Wan, 26 Oct 2026)
        ".ph{position:relative;align-self:center;overflow:hidden;flex:none;"
        "-webkit-mask-image:linear-gradient(to right,transparent,#000 14%,#000 86%,transparent),"
        "linear-gradient(to bottom,transparent,#000 16%,#000 84%,transparent);-webkit-mask-composite:source-in;"
        "mask-image:linear-gradient(to right,transparent,#000 14%,#000 86%,transparent),"
        "linear-gradient(to bottom,transparent,#000 16%,#000 84%,transparent);mask-composite:intersect;}",
        f".hook{{flex:none;align-self:flex-start;color:#fff;font-weight:800;letter-spacing:.05em;line-height:1.1;"
        f"padding:{14 * scale:.0f}px {30 * scale:.0f}px;border-radius:{14 * scale:.0f}px;font-size:{60 * scale:.0f}px;}}",
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
        ".kk{display:inline-block;}",
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
        f".gridx.strong{{background-image:"
        f"repeating-linear-gradient(0deg,{rgba(accent, .2)} 0 2px,transparent 2px {72 * scale:.0f}px),"
        f"repeating-linear-gradient(90deg,{rgba(accent, .2)} 0 2px,transparent 2px {72 * scale:.0f}px);}}",
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
        # data blocks: a chart, a timeline, a flow diagram, the study card, a side panel and a small morphing shape
        f".chart{{flex:none;width:100%;display:flex;flex-direction:column;gap:{gap * .5:.0f}px;}}",
        f".cl{{display:flex;justify-content:space-between;align-items:baseline;gap:{gap:.0f}px;font-size:{fs_d:.0f}px;"
        "font-weight:600;line-height:1.2;}",
        ".ct{flex:1;min-width:0;overflow-wrap:anywhere;}",
        f".cv{{white-space:nowrap;color:{accent};font-weight:800;}}",
        f".ctk{{height:{max(14, 22 * scale):.0f}px;margin-top:{10 * scale:.0f}px;background:{rgba(accent, .16)};"
        f"border-radius:{12 * scale:.0f}px;overflow:hidden;}}",
        f".ctk i{{display:block;height:100%;background:{accent};transform-origin:0 50%;border-radius:{12 * scale:.0f}px;}}",
        f".tlw{{flex:none;position:relative;display:flex;width:100%;"
        f"border-top:{max(3, 4 * scale):.0f}px solid {rgba(accent, .3)};"
        f"padding-top:{26 * scale:.0f}px;}}",
        f".tll{{position:absolute;left:0;top:-{max(3, 4 * scale):.0f}px;width:100%;height:{max(3, 4 * scale):.0f}px;"
        f"background:{accent};transform-origin:0 50%;}}",
        f".te{{position:relative;flex:1;min-width:0;padding-right:{gap * .5:.0f}px;font-size:{fs_d:.0f}px;line-height:1.2;}}",
        f".te::before{{content:\"\";position:absolute;left:0;top:-{38 * scale:.0f}px;"
        f"width:{16 * scale:.0f}px;height:{16 * scale:.0f}px;"
        f"background:{accent};transform:rotate(45deg);}}",
        f".te b{{display:block;font-size:{fs_d * 1.15:.0f}px;font-weight:800;color:{accent};}}",
        ".fl{flex:none;width:100%;display:flex;flex-direction:column;align-items:center;gap:0;}",
        f".fb{{box-sizing:border-box;width:100%;padding:{pad_card:.0f}px;border-radius:{20 * scale:.0f}px;"
        f"background:rgba(255,255,255,.74);border:{max(2, 3 * scale):.0f}px solid {rgba(accent, .55)};}}",
        f".ar{{flex:none;width:0;height:0;border-left:{16 * scale:.0f}px solid transparent;"
        f"border-right:{16 * scale:.0f}px solid transparent;"
        f"border-top:{arrow_h * .75:.0f}px solid {accent};margin:{arrow_h * .125:.0f}px 0;}}",
        # the reference is a footnote (Wan, 26 Oct 2026: "part rujukan boleh kecilkan"): the facts above it are the film
        f".pub{{flex:none;box-sizing:border-box;width:100%;padding:{pad_card * .55:.0f}px {pad_card * .9:.0f}px;"
        f"border-radius:{14 * scale:.0f}px;background:rgba(255,255,255,.7);"
        f"border:{max(2, 2 * scale):.0f}px solid {rgba(accent, .4)};"
        f"border-left:{max(6, 9 * scale):.0f}px solid {accent};font-size:{fs_p:.0f}px;line-height:1.2;}}",
        f".pub .tag{{font-weight:800;color:{accent};letter-spacing:.06em;}}",
        ".pub .jn{font-weight:800;} .pub .tt{font-weight:500;} .pub .rf{opacity:.65;font-weight:600;}",
        f".qm{{font-size:{110 * scale:.0f}px;line-height:1;height:{110 * scale:.0f}px;margin-bottom:{10 * scale:.0f}px;"
        f"font-weight:800;color:{accent};}}",
        f".row{{flex:none;display:flex;gap:{gap:.0f}px;width:100%;align-items:center;}}",
        f".pair{{flex:none;display:flex;gap:{gap * .6:.0f}px;width:100%;justify-content:center;}}",
        f".stat{{flex:none;display:flex;align-items:center;gap:{gap:.0f}px;width:100%;}}",
        f".stat b{{flex:none;font-size:{150 * scale:.0f}px;font-weight:800;color:{accent};line-height:1;}}",
        f".stat span{{flex:1;min-width:0;font-size:{54 * scale:.0f}px;font-weight:700;line-height:1.15;overflow-wrap:anywhere;}}",
        f".pnlx{{flex:1;min-width:0;box-sizing:border-box;padding:{pad_card:.0f}px;border-radius:{24 * scale:.0f}px;"
        f"background:rgba(255,255,255,.74);border:{max(2, 3 * scale):.0f}px solid {rgba(accent, .45)};}}",
        f".mph{{flex:none;align-self:flex-start;width:{110 * scale:.0f}px;height:{110 * scale:.0f}px;background:{accent};"
        "clip-path:polygon(0 0,100% 0,100% 100%,0 100%);}",
    ]
    parts, tw = [], []
    # the background is a soft diagonal gradient and nothing else (Wan, 26 Oct 2026: "I don't want circles in the background
    # but more like gradient"): the reference films' own gradients, with a second one that fades in and out for slow movement
    parts.append(f'<div id="grad2" style="position:absolute;left:0;top:0;width:{w}px;height:{h}px;opacity:0;'
                 f'background:{grad_alt};"></div>')
    tw.append(f'tl.to("#grad2",{{opacity:.65,duration:{total / 2:g},ease:"sine.inOut"}},0);')
    tw.append(f'tl.to("#grad2",{{opacity:0,duration:{total / 2:g},ease:"sine.inOut"}},{total / 2:g});')
    # the line grid sits behind every scene, the same in all of them (Wan, 26 Oct 2026: "all scene ... have line background")
    parts.append('<div class="gridx" id="grid-all"></div>')
    parts.append('<div class="flash" id="flash"></div>')

    def text_h(text: str, px: float, factor: float, width: float, lh: float = 1.2) -> float:
        return wrap_lines(text or " ", px, width, factor) * px * lh

    ev = plan.get("evidence_url") or ""
    cctx = motion_concepts.Ctx(scale, box_w, gap, 54 * scale, pad_card, motion_concepts.host_of(ev), text_h)   # the facts, larger
    css.extend(motion_concepts.css(cctx, accent, rgba))
    concept_used: list[str] = []
    last_heading = plain(teaching[-1].get("heading")) if teaching else ""

    for idx, sc in enumerate(teaching):
        sid, start, dur = sc["id"], float(sc["start"]), float(sc["duration"])
        first = idx == 0
        eff = set(plan.get("scenes", {}).get(sid, []))
        # this scene's own looks (the plan gives each scene a caption style, a finish and the hand-over that leaves it)
        cap_s = next((c for c in eff if c in CAPTIONS), caption)
        prev_eff = set(plan.get("scenes", {}).get(teaching[idx - 1]["id"], [])) if idx else eff
        trn_s = next((c for c in prev_eff if c in TRANSITIONS), transition)
        fin_s = next((c for c in eff if c in FILTERS), finish_code)
        lines = [plain(x) for x in (sc.get("lines") or []) if plain(x)]
        heading = plain(sc.get("heading"))
        photo = sc.get("photo")
        photo2 = sc.get("photo2")
        is_typed = cap_s in {"C03", "C09"}
        role = sc.get("role") or ""
        # a concept rendition of a style that needs footage or a capture (it takes its lines off the plain list)
        ccode = next((c for c in eff if c in motion_concepts.KIND), None)
        cblock = None
        base_lines = list(lines)
        if ccode:
            kind = motion_concepts.KIND[ccode]
            teaser = last_heading if idx < len(teaching) - 1 else ""
            cblock = motion_concepts.build(kind, sid, cctx, heading, lines, teaser=teaser)
            if cblock:
                lines = lines[min(motion_concepts.CONSUME.get(kind, 1), len(lines)):]
        use_concept = cblock is not None
        # a big number (P03): the first whole number a line prints, set large and counted up to; only a figure the words give
        stat, after_concept = None, list(lines)
        if "P03" in eff:
            for ln in lines:
                m = STAT.search(ln)
                if m and not PCT.search(ln) and not YEAR.fullmatch(m.group(0)):
                    stat = (ln, m.group(0), label_of(ln, m.group(0)))
                    break
        if stat:
            lines = [x for x in lines if x != stat[0]]
        # what the scene's own words can carry: percentages for a chart, years for a timeline, figures to count up
        pct_rows = [(ln, m) for ln in lines for m in [PCT.search(ln)] if m][:3] if "V09" in eff else []
        yrs = [(ln, YEAR.search(ln).group(0)) for ln in lines if YEAR.search(ln)] if "P08" in eff else []
        events = sorted({y: ln for ln, y in yrs}.items())[:4] if len({y for _, y in yrs}) >= 2 else []
        quote = next((ln for ln in lines if re.search(r"[“”\"]", ln)), "") if "P09" in eff and not study else ""
        photo_h = (h * 0.34 if h >= w else h * 0.40) if photo else 0
        extra_blocks = ("V06" in eff) + bool(study and "P09" in eff) + ("V08" in eff) + bool(pct_rows or events or quote) \
            + use_concept
        if photo and extra_blocks:
            photo_h *= max(0.55, 1 - 0.16 * extra_blocks)
        photo_w = box_w if h >= w else min(box_w, photo_h * 1.6)
        # the type starts large and `fit` brings it down to what the column holds, so a short scene fills the window
        # (Wan, 26 Oct 2026: "jangan bagi window terlalu kosong") and a long one still fits
        px_h = (128 if len(heading.split()) <= 4 else 108 if len(heading.split()) <= 7 else 88 if len(heading.split()) <= 11
                else 66) * scale
        px_l = 62 * scale
        if not photo and len((heading + " " + " ".join(lines)).split()) <= 14:
            px_h, px_l = px_h * 1.25, px_l * 1.2                      # a sparse scene is set larger, so the window is not empty
        hook_kind = plan.get("hook") if idx == 0 and plan.get("hook") in HOOKS else None
        lead = (1.1 if "H05" in eff else 0.8 if "H10" in eff else 0.4 if "M04" in eff else 0.3 if "H06" in eff else 0.0)
        if lead and dur < 3.6:
            lead = min(lead, 0.4)

        def column(lines_now: list[str], eff: set[str] = eff, heading: str = heading, px_h: float = px_h, px_l: float = px_l,
                   is_typed: bool = is_typed, cap_s: str = cap_s, role: str = role, photo: Any = photo,
                   pct_rows: list = pct_rows, events: list = events) -> dict[str, Any]:
            longest = max((len(x) for ln in lines_now[:2] for x in ln.split()), default=0)
            side = "L05" in eff and bool(photo) and bool(lines_now)
            cards = (not side and "V05" in eff and len(lines_now) >= 2
                     and longest * MIN_PX * scale * BODY * 1.05 <= card_w)
            consumed = not side and not cards and not pct_rows and not events
            flow = consumed and "B04" in eff and role == "solution" and len(lines_now) >= 2
            steps = consumed and not flow and len(lines_now) >= 2
            track = "V06" in eff and len(lines_now) >= 2 and not cards and not side
            if side or pct_rows or events:
                rest = [ln for ln in lines_now if not (events and YEAR.search(ln))
                        and not any(ln == r for r, _ in pct_rows)] if not side else []
            else:
                rest = lines_now[2:] if cards else lines_now
            f = BODY * box_w / (box_w - step_pad) if steps else (0.62 if is_typed and cap_s == "C09" else BODY)
            if flow:
                f = BODY * box_w / max(box_w - 2 * pad_card - 8, 1)
            texts = ([(heading, px_h, WIDE)] if heading else [])
            if cards:
                texts.append((max(lines_now[:2], key=len), px_l * 0.9, BODY * box_w / max(card_w, 1)))
            texts += [(ln, px_l, f) for ln in rest]
            return {"texts": texts, "cards": cards, "steps": steps, "track": track, "flow": flow, "side": side, "rest": rest}

        while True:
            col = column(lines)
            texts, rest = col["texts"], col["rest"]
            cards, steps, track, flow, side = (col[k] for k in ("cards", "steps", "track", "flow", "side"))
            rule = ("H10" in eff or (cap_s == "C06" and bool(lines))) and bool(heading or lines)
            extra = (photo_h + gap if photo and not side else 0) + (trk_h + gap if track else 0) + (rule_h + gap if rule else 0) \
                + (2 * pad_card if cards else 0)
            if "V08" in eff:
                extra += 110 * scale + gap
            if study and "P09" in eff:
                lab = TAGS.get(lang, TAGS["bm"])[0] + " · " + study["journal"]
                inner = box_w - 2 * pad_card * 0.9 - 12 * scale
                extra += (text_h(lab, fs_p, 0.6, inner, 1.2) + text_h(study["title"], fs_p, BODY, inner, 1.2)
                          + text_h(study["ref"], fs_p, BODY, inner, 1.2)
                          + 1.1 * pad_card + gap) if (study["journal"] or study["title"]) else 0
            if quote:
                extra += text_h(quote, fs_d, BODY, box_w - 2 * pad_card * 1.2, 1.22) + 122 * scale + 2 * pad_card + gap
            if pct_rows:
                vw = max(len(m.group(0)) for _, m in pct_rows) * fs_d * 0.66 + gap
                bar = max(14, 22 * scale) + 10 * scale + gap * .5
                extra += sum(text_h(label_of(ln, m.group(0)), fs_d, BODY, box_w - vw) + bar for ln, m in pct_rows) + gap
            if events:
                cw = box_w / len(events) - gap * .5
                tallest = max(text_h(label_of(ln, y), fs_d, BODY, cw) for y, ln in events)
                extra += tallest + fs_d * 1.4 + 26 * scale + gap + 20 * scale
            if flow:
                inner = box_w - 2 * pad_card - 8
                extra += sum(text_h(ln, px_l, BODY, inner, 1.18) for ln in rest) + len(rest) * 2 * pad_card \
                    + (len(rest) - 1) * arrow_h + gap
            if use_concept and cblock:
                extra += cblock.height + gap
            if stat:
                numw = len(stat[1]) * 150 * scale * 0.62 + gap
                extra += max(150 * scale, text_h(stat[2], 54 * scale, BODY, max(box_w - numw, 1), 1.15)) + gap
            if steps:
                extra += len(rest) * 34 * scale
            if hook_kind:
                extra += 60 * scale * 1.1 + 28 * scale + gap
            sizes = fit(texts, box_w, box_h, extra + gap * (len(texts) + 1), scale) if texts else []
            if not sizes and use_concept and (lines or texts):
                use_concept, cblock, lines = False, None, list(base_lines)     # words outrank a concept diagram
                if stat:
                    lines = [x for x in lines if x != stat[0]]
                continue
            if side:
                panel_w = box_w * 0.56 - 2 * pad_card
                side_sizes = fit([(ln, px_l * 0.9, BODY * (box_w * 0.56) / max(panel_w, 1)) for ln in lines], panel_w,
                                 photo_h - 2 * pad_card, 0, scale)
                if not side_sizes:
                    eff.discard("L05")                    # the sidebar cannot hold these lines beside the photo: plain column
                    continue
                sizes = fit(texts[:1], box_w, box_h, photo_h + gap + extra + gap * 2, scale) if texts else [0]
                if texts and not sizes:
                    eff.discard("L05")                    # photo, panel and the other blocks together do not fit: plain column
                    continue
            if sizes or (not lines and not texts):
                break
            if lines:
                dropped.append(f"{sid}: {lines.pop()[:40]}")
                continue
            if stat:
                stat, lines = None, list(after_concept)           # the big number goes before the words do
                continue
            spare = next((c for c in ("P09", "V08", "V06") if c in eff), None)
            if spare:
                eff.discard(spare)                        # an extra block that cannot fit goes before the heading shrinks
                continue
            break
        if texts and not sizes:
            sizes = [MIN_PX * scale] * len(texts)
        if photo and not side and texts and sizes:
            # the photo takes the room the words leave, up to about half the frame (Wan: "make it bigger", "not too empty")
            used = extra + gap * (len(texts) + 1) + sum(wrap_lines(t, s, box_w, f) * s * 1.18 + s * 0.35
                                                         for (t, _, f), s in zip(texts, sizes, strict=True))
            room = h * (0.5 if h >= w else 0.56) - photo_h
            if box_h - used > 0 and room > 0:
                photo_h += min((box_h - used) * 0.92, room)
        hs = sizes[0] if heading and sizes else px_h
        ls = sizes[1:] if heading else sizes
        block, photo_html = [], ""
        counts: list[tuple[str, int]] | None = [] if "P03" in eff else None
        numbers = "V02" in eff
        if photo:
            pw = min(box_w * 0.42, photo_h * 0.8) if side else photo_w
            filt = FILTERS[fin_s]
            if "X06" in eff:
                inner = "".join(f'<i class="tl {sid}-t" style="left:{c * 100 / 3:.3f}%;top:{r * 100 / 3:.3f}%;'
                                f'background-image:url({photo});background-position:{c * 50}% {r * 50}%;"></i>'
                                for r in range(3) for c in range(3))
                inner = f'<div id="{sid}-photo" style="filter:{filt};">{inner}</div>'
            else:
                inner = f'<div id="{sid}-photo" style="background-image:url({photo});filter:{filt};"></div>'
            photo_html = (f'<div class="ph" id="{sid}-ph" style="width:{pw:.0f}px;height:{photo_h:.0f}px;'
                          f'">{inner}</div>')
            if photo2 and not side:
                half = (box_w - gap * .6) / 2
                inner2 = f'<div id="{sid}-photo2" style="background-image:url({photo2});filter:{filt};"></div>'
                photo_html = (f'<div class="pair" id="{sid}-pair"><div class="ph" id="{sid}-ph" '
                              f'style="width:{half:.0f}px;height:{photo_h:.0f}px;">{inner}</div>'
                              f'<div class="ph" id="{sid}-ph2" style="width:{half:.0f}px;height:{photo_h:.0f}px;">'
                              f'{inner2}</div></div>')
            applied.add(fin_s)
        if "V08" in eff:
            block.append(f'<div class="mph" id="{sid}-mph"></div>')
            applied.add("V08")
        if rule and "H10" in eff:
            block.append(f'<div class="rule" id="{sid}-r0"></div>')
            applied.add("H10")
        if hook_kind:
            bm_label, en_label, colour = HOOKS[hook_kind]
            block.append(f'<div class="hook" id="{sid}-hook" style="background:{colour or accent}">'
                         f'{esc(en_label if lang == "en" else bm_label)}</div>')
        key_done = key7_done = False
        if heading:
            words = heading.split()
            style = f"font-size:{hs:.0f}px;" + ('font-family:Georgia,"Times New Roman",serif;' if "H10" in eff else "")
            # the key word is an inline-block: only one that fits the column whole may be wrapped, or it would break inside
            fits = [j for j in range(len(words)) if len(words[j]) * hs * WIDE * 1.08 <= box_w * 0.92]
            key = max(fits, key=lambda j: len(words[j])) if fits else -1
            if cap_s == "C04" and len(words) > 2 and key >= 0:
                words[key] = f'<span class="kw">{esc(words[key])}<i id="{sid}-kw"></i></span>'
                body = " ".join(esc(x) if "<span" not in x else x for x in words)
                key_done = True
            elif cap_s == "C07" and len(words) > 1 and key >= 0:
                # the key word bursts alone: the other words arrive only once it has settled, so nothing is ever crossed
                words = [f'<span class="ow {sid}-ow">{esc(x)}</span>' if j != key else
                         f'<span class="k7" id="{sid}-k7">{esc(x)}</span>' for j, x in enumerate(words)]
                body = " ".join(words)
                key7_done = True
            elif cap_s == "C02":
                body = " ".join(f'<span class="w {sid}-w" style="display:inline-block;">{inline(x, sid, numbers, counts)}</span>'
                                for x in words)
            else:
                body = inline(heading, sid, numbers, counts)
            block.append(f'<h2 class="h" id="{sid}-h" style="{style}">{body}</h2>')
        if photo_html and not side:
            block.append(photo_html)
        if track:
            block.append(f'<div class="trk" id="{sid}-trk">' + "".join(
                f'<span class="sg"><b id="{sid}-f{k}"></b></span>' for k in range(len(lines))) + "</div>")
            applied.add("V06")
        if cap_s == "C06" and lines and "H10" not in eff:
            block.append(f'<div class="rule" id="{sid}-r"></div>')

        def para(ln: str, size: float, j: int, klass: str, sid: str = sid, eff: set[str] = eff, steps: bool = steps,
                 numbers: bool = numbers, is_typed: bool = is_typed, cap_s: str = cap_s, counts: Any = counts) -> str:
            en = lang == "both" and " / " in ln
            primary, _, secondary = ln.partition(" / ") if en else (ln, "", "")
            marker = '<span class="dot"></span>' if ("V04" in eff and not steps) else ""
            if is_typed:
                inner_html = typed(primary, sid)
            elif "V10" in eff:
                inner_html = quiet(primary, sid, numbers, counts)
            else:
                inner_html = inline(primary, sid, numbers, counts)
            mono_cls = " mono" if cap_s == "C09" else ""
            out = f'<p class="l{mono_cls} {klass}" id="{sid}-l{j}" style="font-size:{size:.0f}px;">{marker}{inner_html}</p>'
            if secondary:
                out += (f'<p class="l en {klass}" id="{sid}-e{j}" style="font-size:{size * .82:.0f}px;">'
                        f'{inline(secondary, sid, numbers, counts)}</p>')
            return out

        pub_html = ""
        lcls = f"{sid}-lt" if is_typed else f"{sid}-l"
        shown = 0
        # a style that takes over the lines draws them its own way
        if side:
            sz = (min(ls) if ls else 0) or px_l * .9
            panel_w = box_w * 0.56 - 2 * pad_card
            side_sizes = fit([(ln, px_l * 0.9, BODY * (box_w * 0.56) / max(panel_w, 1)) for ln in lines], panel_w,
                             photo_h - 2 * pad_card, 0, scale)
            ps = "".join(para(ln, side_sizes[j] if j < len(side_sizes) else MIN_PX * scale, j, lcls)
                         for j, ln in enumerate(lines))
            block.append(f'<div class="row" id="{sid}-row">{photo_html}<div class="pnlx" id="{sid}-pnl">{ps}</div></div>')
            applied.add("L05")
            shown = len(lines)
            del sz
        elif cards:
            sz = ls[0] if ls else MIN_PX * scale
            block.append(f'<div class="cards" id="{sid}-cards">' + "".join(
                f'<div class="card {sid}-cd{k}">{para(lines[k], sz, k, lcls)}</div>' for k in (0, 1)) + "</div>")
            applied.add("V05")
            shown = 2
        if pct_rows:
            vw = max(len(m.group(0)) for _, m in pct_rows)
            rows_html = ""
            for k, (ln, m) in enumerate(pct_rows):
                rows_html += (f'<div class="cr {sid}-cr"><div class="cl"><span class="ct">{esc(label_of(ln, m.group(0)))}</span>'
                              f'<b class="cv">{esc(m.group(0).replace(" ", ""))}</b></div>'
                              f'<div class="ctk"><i id="{sid}-cf{k}"></i></div></div>')
            del vw
            block.append(f'<div class="chart" id="{sid}-chart">{rows_html}</div>')
            applied.add("V09")
        if events:
            cols = "".join(f'<div class="te {sid}-te"><b>{esc(y)}</b>{esc(label_of(ln, y))}</div>' for y, ln in events)
            block.append(f'<div class="tlw" id="{sid}-tlw"><i class="tll" id="{sid}-tll"></i>{cols}</div>')
            applied.add("P08")
        if stat:
            block.append(f'<div class="stat" id="{sid}-stat"><b id="{sid}-stn">{esc(stat[1])}</b>'
                         f'<span>{esc(stat[2])}</span></div>')
            applied.add("P03")
        if study and "P09" in eff and (study["journal"] or study["title"]):
            tag = TAGS.get(lang, TAGS["bm"])[0]
            pub_html = (f'<div class="pub {sid}-pub" id="{sid}-pub"><div><span class="tag">{esc(tag)}</span>'
                        + (f' · <span class="jn">{esc(study["journal"])}</span>' if study["journal"] else "") + "</div>"
                        + (f'<div class="tt">{esc(study["title"])}</div>' if study["title"] else "")
                        + (f'<div class="rf">{esc(study["source"] + " · " if study["source"] else "")}{esc(study["ref"])}</div>'
                           if study["ref"] else "") + "</div>")
            applied.add("P09")
        elif quote:
            block.append(f'<div class="pub {sid}-pub" id="{sid}-pub"><div class="qm">“</div>'
                         f'<div class="tt">{esc(quote.strip(chr(34) + "“”"))}</div></div>')
            applied.add("P09")
            lines = [ln for ln in lines if ln != quote]
        if use_concept and cblock:
            block.append(cblock.html)
            applied.add(ccode)
            concept_used.append(ccode)
        rest_sizes = ls[1:] if cards else ls
        if flow:
            inner_boxes = []
            for j, ln in enumerate(rest):
                size = rest_sizes[j] if j < len(rest_sizes) else MIN_PX * scale
                inner_boxes.append(f'<div class="fb {sid}-l" id="{sid}-s{j}">{para(ln, size, j, f"{sid}-lx")}</div>')
            block.append(f'<div class="fl" id="{sid}-flow">' + f'<i class="ar {sid}-ar"></i>'.join(inner_boxes) + "</div>")
            applied.add("B04")
            tail_lines: list[str] = []
        else:
            tail_lines = rest if (pct_rows or events or side) else lines[shown:]
        for j, ln in enumerate(tail_lines, start=shown):
            size = rest_sizes[j - shown] if j - shown < len(rest_sizes) else MIN_PX * scale
            if steps:
                last = j == len(lines) - 1
                block.append(f'<div class="stp {sid}-l" id="{sid}-s{j}"><span class="bd {sid}-bd">{j + 1}</span>'
                             + ("" if last else f'<i class="cn {sid}-cn"></i>') + para(ln, size, j, f"{sid}-lx") + "</div>")
            else:
                block.append(para(ln, size, j, lcls))
        if pub_html:
            block.append(pub_html)                       # the reference closes the column, under the facts
        if steps and "B04" in eff:
            applied.add("B04")
        if "V04" in eff and not steps and (tail_lines or cards or side):
            applied.add("V04")
        if "V10" in eff and not is_typed and (tail_lines or cards or side):
            applied.add("V10")
        extras = ""
        if "H06" in eff:
            extras += f'<div class="pl" id="{sid}-pa" style="left:0"></div><div class="pl" id="{sid}-pb" style="right:0"></div>'
            applied.add("H06")
        if "H05" in eff:
            digits = "".join(f'<span id="{sid}-cd{n}">{n}</span>' for n in (3, 2, 1))
            extras += f'<div class="cd" id="{sid}-cd">{digits}</div>'
            applied.add("H05")
        fx = ""
        if "X10" in eff:
            fx += f'<div class="gridx strong" id="{sid}-gx"></div>'
            applied.add("X10")
        if "B08" in eff:
            fx += "".join(f'<div class="ln {sid}-ln" style="top:{pos}%;"></div>' for pos in (24, 50, 76))
            applied.add("B08")
        if fx:
            parts.append(f'<div class="clip fx" id="{sid}-fx" data-start="{start:g}" data-duration="{dur:g}">{fx}</div>')
        parts.append(f'<div class="clip sc" id="{sid}" data-start="{start:g}" data-duration="{dur:g}">'
                     + "".join(block) + extras + "</div>")
        if narrated and sc.get("audio") and str(sc.get("narration") or "").strip():
            lane_h = h * LANE[1]
            chunks = caption_chunks(sc)
            timed = sc.get("words") or []
            karaoke = cap_s == "C01" and len(timed) == len(str(sc.get("narration")).split())
            for k, (text, a, b) in enumerate(chunks):
                size = 52 * scale
                while size > MIN_PX * scale and wrap_lines(text, size, box_w, BODY) * size * 1.3 > lane_h:
                    size -= 2 * scale
                inner = esc(text)
                if karaoke:
                    off = 0 if k == 0 else len(chunks[0][0].split())
                    inner = " ".join(f'<span class="kk" id="{sid}-kk{off + j}">{esc(wd)}</span>'
                                     for j, wd in enumerate(text.split()))
                    for j in range(len(text.split())):
                        tw.append(f'tl.fromTo("#{sid}-kk{off + j}",{{opacity:.4}},{{opacity:1,duration:.08}},'
                                  f'{start + float(timed[off + j][0]):g});')
                    applied.add("C01")
                parts.append(f'<div class="clip cap" id="{sid}-c{k}" data-start="{a:g}" data-duration="{b - a:g}" '
                             f'style="font-size:{size:.0f}px;">{inner}</div>')
                tw.append(f'tl.fromTo("#{sid}-c{k}",{{opacity:0}},{{opacity:1,duration:.18,ease:"power1.out"}},{a:g});')
                tw.append(f'tl.to("#{sid}-c{k}",{{opacity:0,duration:.12}},{max(a, b - .14):g});')
        t0, t1 = start, start + dur
        enter = 0.45 if trn_s != "M02" else 0.28
        dx = {"M09": 70, "M02": 150, "M08": 0}.get(trn_s, 70) * scale
        applied.add(trn_s)
        y0 = 26 * scale
        opening = ".35" if first and not lead else "0"
        th = t0 + .05 + lead
        # openers that hold the scene back for a moment: the countdown, the split panels, the silent pause, the flash
        if "H05" in eff:
            for i, n in enumerate((3, 2, 1)):
                at = t0 + i * 0.36
                tw.append(f'tl.fromTo("#{sid}-cd{n}",{{opacity:0,scale:2.2}},{{opacity:1,scale:1,duration:.2,ease:"power3.out"}},{at:g});')
                tw.append(f'tl.to("#{sid}-cd{n}",{{opacity:0,scale:.8,duration:.1}},{at + .26:g});')
        if hook_kind:
            tw.append(f'tl.fromTo("#{sid}-hook",{{opacity:0,scale:.6}},{{opacity:1,scale:1,duration:.45,ease:"back.out(2)"}},'
                      f'{t0 + lead + .02:g});')
        if "H06" in eff:
            tw.append(f'tl.fromTo("#{sid}-pa",{{xPercent:0}},{{xPercent:-101,duration:.5,ease:"power3.inOut"}},{t0 + .1:g});')
            tw.append(f'tl.fromTo("#{sid}-pb",{{xPercent:0}},{{xPercent:101,duration:.5,ease:"power3.inOut"}},{t0 + .1:g});')
        if "H10" in eff:
            tw.append(f'tl.fromTo("#{sid}-r0",{{scaleX:0}},{{scaleX:1,duration:.7,ease:"power2.out"}},{t0 + .05:g});')
        if "V08" in eff:
            sq, tri, dia = ("polygon(0 0,100% 0,100% 100%,0 100%)", "polygon(50% 0,50% 0,100% 100%,0 100%)",
                            "polygon(50% 0,100% 50%,50% 100%,0 50%)")
            tw.append(f'tl.fromTo("#{sid}-mph",{{clipPath:"{sq}",opacity:0}},{{clipPath:"{sq}",opacity:1,duration:.3}},'
                      f'{t0 + lead:g});')
            tw.append(f'tl.to("#{sid}-mph",{{clipPath:"{tri}",duration:.6,ease:"power2.inOut"}},{t0 + lead + .5:g});')
            tw.append(f'tl.to("#{sid}-mph",{{clipPath:"{dia}",duration:.6,ease:"power2.inOut"}},{t0 + lead + 1.3:g});')
        if "M04" in eff:
            applied.add("M04")
            tw.append(f'tl.fromTo("#flash",{{opacity:.35}},{{opacity:0,duration:.4,ease:"power2.out",immediateRender:false}},'
                      f'{t0:g});')
            if heading:
                tw.append(f'tl.fromTo("#{sid}-h",{{scale:1.07}},{{scale:1,duration:.35,ease:"power2.out"}},{t0 + lead:g});')
        if "X10" in eff:
            tw.append(f'tl.fromTo("#{sid}-gx",{{clipPath:"inset(0 100% 0 0)"}},{{clipPath:"inset(0 0% 0 0)",duration:.9,'
                      f'ease:"power2.inOut"}},{t0:g});')
        if "B08" in eff:
            tw.append(f'tl.fromTo(".{sid}-ln",{{x:{-w * .06:.0f}}},{{x:{w * .16:.0f},duration:{dur:g},ease:"none"}},{t0:g});')
        if heading:
            if cap_s == "C02":
                applied.add("C02")
                tw.append(f'tl.fromTo(".{sid}-w",{{opacity:{opening},scale:.82,y:{y0:.0f}}},{{opacity:1,scale:1,y:0,duration:.4,'
                          f'ease:"back.out(1.5)",stagger:.07}},{th:g});')
            else:
                dy = y0 if not dx else 0
                tw.append(f'tl.fromTo("#{sid}-h",{{opacity:{opening},x:{dx:.0f},y:{dy:.0f}}},{{opacity:1,x:0,y:0,'
                          f'duration:{enter + .1:g},ease:"power3.out"}},{th:g});')
            if "M10" in eff:
                applied.add("M10")
                stut = f"{-14 * scale:.0f}"
                tw.append(f'tl.fromTo("#{sid}-h",{{x:{stut},opacity:0}},{{x:0,opacity:1,duration:.45,ease:"steps(4)"}},{th:g});')
            if "M07" in eff:
                applied.add("M07")
                jolt = ",".join(f"{{x:{x * scale:.0f},duration:.05}}" for x in (-16, 12, -7, 3, 0))
                tw.append(f'tl.to("#{sid}-h",{{keyframes:[{jolt}]}},{th + enter + .2:g});')
            if key_done:
                applied.add("C04")
                tw.append(f'tl.fromTo("#{sid}-kw",{{scaleX:0}},{{scaleX:1,duration:.6,ease:"power2.inOut"}},{th + .45:g});')
            if key7_done:
                applied.add("C07")
                est = max(len(x) for x in heading.split()) * hs * WIDE
                burst = min(2.3, max(1.2, box_w * 0.96 / max(est, 1)))
                # a word that grows about its own centre must stay inside the frame wherever the line puts it: the growth on
                # each side (about half the extra width) may not exceed the margin between the column and the frame edge
                key_w = len(heading.split()[key]) * hs * WIDE
                burst = max(1.08, min(burst, 1 + 2 * (w * SAFE["left"]) * 0.9 / max(key_w, 1)))
                tw.append(f'tl.fromTo("#{sid}-k7",{{scale:{burst:.2f},opacity:0}},{{scale:1,opacity:1,duration:.5,ease:"back.out(1.6)"}},'
                          f'{th:g});')
                tw.append(f'tl.fromTo(".{sid}-ow",{{opacity:0}},{{opacity:1,duration:.3,ease:"power1.out"}},{th + .55:g});')
        tl_start = t0 + .35 + lead
        gap_in = 0.5 if not sc.get("narration") else 0.35
        if side:
            tw.append(f'tl.fromTo("#{sid}-pnl",{{opacity:0,x:{box_w * .3:.0f}}},'
                      f'{{opacity:1,x:0,duration:.6,ease:"power3.out"}},{tl_start:g});')
        if cards:
            for k, side_x in ((0, -1), (1, 1)):
                tw.append(f'tl.fromTo(".{sid}-cd{k}",{{opacity:0,x:{side_x * box_w * .5:.0f}}},'
                          f'{{opacity:1,x:0,duration:.6,ease:"power3.out"}},{tl_start:g});')
        if pct_rows:
            tw.append(f'tl.fromTo(".{sid}-cr",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.4,stagger:.25}},{tl_start:g});')
            for k, (_ln, m) in enumerate(pct_rows):
                pct = min(100.0, float(m.group(1).replace(",", ".")))
                tw.append(f'tl.fromTo("#{sid}-cf{k}",{{scaleX:0}},{{scaleX:{pct / 100:.3f},duration:.9,ease:"power2.out"}},'
                          f'{tl_start + .25 * k + .2:g});')
        if events:
            tw.append(f'tl.fromTo("#{sid}-tll",{{scaleX:0}},{{scaleX:1,duration:.9,ease:"power2.inOut"}},{tl_start:g});')
            tw.append(f'tl.fromTo(".{sid}-te",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.4,stagger:.3}},'
                      f'{tl_start + .2:g});')
        if use_concept and cblock:
            tw.extend(cblock.tweens(tl_start))
        if stat:
            tw.append(f'tl.fromTo("#{sid}-stat",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out"}},{tl_start:g});')
            tw.append(f'tl.fromTo("#{sid}-stn",{{textContent:0}},{{textContent:{int(stat[1])},duration:1.2,ease:"power2.out",'
                      f'snap:{{textContent:1}}}},{tl_start + .2:g});')
        if (study and "P09" in eff) or quote:
            tw.append(f'tl.fromTo("#{sid}-pub",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out"}},{tl_start:g});')
        if is_typed and lines:
            applied.add(cap_s)
            chars = sum(len(re.sub(r"\s", "", ln.partition(" / ")[0])) for ln in lines)
            per = max(0.012, min(0.045, min(3.0, dur * .6) / max(chars, 1)))
            tw.append(f'tl.fromTo(".{sid}-ch",{{opacity:0}},{{opacity:1,duration:.01,stagger:{per:.3f}}},{tl_start:g});')
        elif tail_lines or flow or (cards and lines[2:]):
            tw.append(f'tl.fromTo(".{sid}-l",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out",'
                      f'stagger:{gap_in:g}}},{tl_start:g});')
        if flow:
            tw.append(f'tl.fromTo(".{sid}-ar",{{opacity:0,scaleY:0}},{{opacity:1,scaleY:1,duration:.3,stagger:{gap_in:g}}},'
                      f'{tl_start + .2:g});')
        if steps:
            tw.append(f'tl.fromTo(".{sid}-bd",{{scale:0}},{{scale:1,duration:.4,ease:"back.out(2)",stagger:{gap_in:g}}},{tl_start:g});')
            tw.append(f'tl.fromTo(".{sid}-cn",{{scaleY:0}},{{scaleY:1,duration:.4,ease:"power2.out",stagger:{gap_in:g}}},'
                      f'{tl_start + .2:g});')
        if track:
            for k in range(len(lines)):
                tw.append(f'tl.to("#{sid}-f{k}",{{scaleX:1,duration:.5,ease:"power2.out"}},{tl_start + k * gap_in:g});')
        if numbers:
            applied.add("V02")
            tw.append(f'tl.fromTo(".{sid}-n",{{scale:.4,opacity:0}},{{scale:1,opacity:1,duration:.4,ease:"power3.out",stagger:.15}},'
                      f'{tl_start + .3:g});')
        for uid, value in (counts or []):
            applied.add("P03")
            tw.append(f'tl.fromTo("#{uid}",{{textContent:0}},{{textContent:{value},duration:1.1,ease:"power2.out",'
                      f'snap:{{textContent:1}}}},{tl_start + .3:g});')
        if cap_s == "C06" and lines and "H10" not in eff:
            applied.add("C06")
            tw.append(f'tl.fromTo("#{sid}-r",{{scaleX:0}},{{scaleX:1,duration:.5,ease:"power2.out"}},{t0 + .3 + lead:g});')
        if cap_s == "C05" and (lines or heading):
            applied.add("C05")
        if cap_s == "C10" and any(" / " in ln for ln in lines) and lang == "both":
            applied.add("C10")
        if photo:
            zoom = 1.07 if ({"M03", "B05"} & eff) else 1.03
            if {"M03", "B05"} & eff:
                applied.update({"M03", "B05"} & eff)
            if lead:
                tw.append(f'tl.fromTo("#{sid}-ph",{{opacity:0}},{{opacity:1,duration:.35}},{t0 + lead:g});')
            if "L06" in eff and not side:
                applied.add("L06")
                tw.append(f'tl.fromTo("#{sid}-ph",{{scale:1.16,opacity:0}},{{scale:1,opacity:1,duration:.7,ease:"power3.out"}},'
                          f'{t0 + .1 + lead:g});')
                tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1.45}},{{scale:{zoom},duration:{dur:g},ease:"power2.out"}},'
                          f'{t0 + lead:g});')
            elif "M01" in eff:
                applied.add("M01")
                tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1.35}},{{scale:{zoom},duration:.35,ease:"power4.out"}},{t0:g});')
            elif "M06" in eff:
                applied.add("M06")
                tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1}},{{scale:1.12,duration:{dur:g},ease:"power3.in"}},{t0:g});')
            elif "X06" in eff:
                applied.add("X06")
                far = f"{220 * scale:.0f}"
                tw.append(f'tl.fromTo(".{sid}-t",{{x:(i)=>[-1,1,0][i%3]*{far},y:(i)=>[1,-1,0][Math.floor(i/3)%3]*{far},'
                          f'rotation:(i)=>(i%2?1:-1)*20,opacity:0}},{{x:0,y:0,rotation:0,opacity:1,duration:.7,'
                          f'ease:"back.out(1.3)",stagger:.05}},{t0 + .1 + lead:g});')
            else:
                tw.append(f'tl.fromTo("#{sid}-photo",{{scale:1}},{{scale:{zoom},duration:{dur:g},ease:"none"}},{t0:g});')
            if "B05" in eff and "X06" not in eff and "L06" not in eff:
                tw.append(f'tl.fromTo("#{sid}-photo",{{xPercent:-2.5}},{{xPercent:2.5,duration:{dur:g},ease:"none"}},{t0:g});')
            if "B05" in eff:
                # the photo tilts in 3D and settles (Wan: "3D image")
                tw.append(f'tl.fromTo("#{sid}-photo",{{transformPerspective:900,rotationY:-16,rotationX:7}},'
                          f'{{rotationY:0,rotationX:0,duration:1.1,ease:"power3.out"}},{t0 + lead:g});')
            if photo2 and not side:
                tw.append(f'tl.fromTo("#{sid}-ph2",{{opacity:0,y:{y0:.0f}}},{{opacity:1,y:0,duration:.6,ease:"power2.out"}},'
                          f'{t0 + .3 + lead:g});')
                tw.append(f'tl.fromTo("#{sid}-photo2",{{scale:1}},{{scale:{zoom},duration:{dur:g},ease:"none"}},{t0:g});')
        fade = min(0.3, dur / 6)
        tw.append(f'tl.to("#{sid}",{{opacity:0,duration:{fade:g},ease:"power1.in"}},{t1 - fade:g});')
        if "X10" in eff or "B08" in eff:
            tw.append(f'tl.to("#{sid}-fx",{{opacity:0,duration:{fade:g},ease:"power1.in"}},{t1 - fade:g});')
        if first and {"H02", "H08"} & eff:
            applied.update({"H02", "H08"} & eff)
            tw.append('tl.fromTo("#flash",{opacity:.85},{opacity:0,duration:.22,ease:"power2.out"},0.04);')
    page = (f'<!doctype html>\n<html lang="{html_lang}" data-resolution="{resolution}">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width={w}, height={h}">\n<script src="{gsap}"></script>\n'
            f"<style>\n{chr(10).join(css)}\n</style>\n</head>\n<body>\n"
            f'<div id="root" data-composition-id="main" data-start="0" data-duration="{total:g}" data-width="{w}" '
            f'data-height="{h}">\n' + "\n".join(parts) + "\n</div>\n<script>\nconst tl = gsap.timeline({ paused: true });\n"
            + "\n".join(tw) + '\nwindow.__timelines = window.__timelines || {};\nwindow.__timelines["main"] = tl;\ntl.seek(0);\n'
            "</script>\n</body>\n</html>\n")
    chosen = {c for cs in plan.get("scenes", {}).values() for c in cs} | {v for v in video.values()}
    report = {"layout": "safe-layout", "built": sorted(chosen & applied),
              "not_built": sorted(chosen - applied - motion_auto.NATIVE_TEXT),
              "concept": sorted(set(concept_used) | ({"C01"} & applied) | ({"M01", "M06", "M10", "F01", "F04"} & applied)),
              "hook": plan.get("hook") if plan.get("hook") in HOOKS else "", "ambient": ambient,
              "dropped_lines": dropped, "caption": caption, "transition": transition}
    return page, report


def layout_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The check's errors that mean words collide, are hidden or leave the frame."""
    code = re.compile(r"overlap|occlud|overflow|clipped|on_photo|out_of_|off_?(?:frame|canvas|screen)|cut_?off|truncat", re.I)
    said = re.compile(r"overlap|occlud|clipped|cut off|outside (?:the )?(?:frame|canvas|safe)", re.I)
    return [f for f in findings if f.get("code") != "probe_unavailable"
            and (code.search(str(f.get("code") or "")) or said.search(str(f.get("message") or "")))]

