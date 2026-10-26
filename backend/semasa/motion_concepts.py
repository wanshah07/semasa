"""Concept renditions of the styles that need footage or a capture (Wan, 26 Oct 2026: "use style that identify as concept
fallback").

Most of the 99 styles edit a filmed speaker, a screen recording or a real screenshot. Semasa's films have none of those and must
never invent proof, so Wan's own catalogue marks them `fallback / concept`: "original qualitative concept diagram instead".
That is what this module draws, from the scene's own words and the idea's own source address and nothing else: a device frame
holds a line, a browser frame shows the source's host, a wipe sets two lines side by side, a chat has the lines as bubbles.
Each is a normal-flow block of the scene's flex column (so nothing can cross the words around it), set in type of 46px or more,
and the film's report lists every one under `concept`, so a concept rendition is never mistaken for the real thing.
"""

from __future__ import annotations

import html as html_mod
import re
from collections.abc import Callable
from typing import Any, NamedTuple

# style code -> the kind of concept diagram that stands in for it
KIND = {
    "L01": "split", "L02": "pip", "L03": "stack", "L04": "device", "L07": "chat", "L09": "wall", "L10": "callout",
    "X01": "orbit", "X02": "ticker", "X03": "frame", "X04": "browser", "X05": "tunnel", "X07": "frame", "X08": "echo",
    "X09": "carousel",
    "P01": "doc", "P02": "callout", "P04": "wipe", "P05": "search", "P06": "receipt", "P07": "mark", "P10": "device",
    "B01": "browser", "B02": "float", "B03": "device", "B06": "frame", "B07": "route", "B09": "checklist", "B10": "browser",
    "V07": "callout", "H04": "teaser",
}
# and the ones that are a movement or a look, not a block
MOTION = {"M01", "M06", "M10"}
CAPTION_CONCEPT = {"C01"}
FILTER_CONCEPT = {"F01", "F04"}
CONCEPT_CODES = set(KIND) | MOTION | CAPTION_CONCEPT | FILTER_CONCEPT
# the roles and needs of each (hook, fact, why, solution; the needs are motion_auto's letters)
RECIPES: dict[str, tuple[str, str, str]] = {
    "L01": ("fw", "l", "concept of a vertical split screen: two lines in two panels side by side"),
    "L02": ("fw", "l", "concept of picture-in-picture: the main line large, the next in a small panel beside it"),
    "L03": ("ws", "l", "concept of a triple stack: up to three lines in three bands, one under the other"),
    "L04": ("fws", "L", "concept of a floating device frame: the key line inside a phone-shaped frame"),
    "L07": ("fws", "l", "concept of a grid conversation: the lines as chat bubbles, left and right"),
    "L09": ("w", "W", "concept of a collage canvas: the scene's own key words as tiles"),
    "L10": ("s", "L", "concept of an adaptive proof panel: the key line in a callout (it is never presented as proof)"),
    "X01": ("fw", "l", "concept of orbit cards: up to three lines as three cards side by side"),
    "X02": ("w", "L", "concept of an infinite content wall: a news-ticker strip carrying the key line"),
    "X03": ("hw", "", "concept of a frame break: the key line in a frame with its corners broken open"),
    "X04": ("f", "L", "concept of a UI world: the key line in a browser-style frame"),
    "X05": ("h", "", "concept of an infinite zoom tunnel: nested frames around the key line, pulsing inward"),
    "X07": ("hw", "", "concept of a reality portal: the key line in a doorway-shaped frame"),
    "X08": ("h", "W", "concept of a clone echo: the heading repeated three times, fainter each time"),
    "X09": ("ws", "L", "concept of a cinematic carousel: a card with arrows and position squares, sliding in"),
    "P01": ("fw", "L", "concept of a screenshot punch: the key line on a document sheet with the line highlighted"),
    "P02": ("fw", "L", "concept of a comment spotlight: the key line in a speech bubble"),
    "P04": ("fw", "l", "concept of a before-and-after wipe: two lines side by side, the second wiped in"),
    "P05": ("hf", "", "concept of search-to-result: the heading typed into a search bar, the first line as the result"),
    "P06": ("fw", "l", "concept of a receipt stack: the lines as rows of a slip with a tick each"),
    "P07": ("fw", "L", "concept of an annotation marker: the key line with a marker stroke drawn across it"),
    "P10": ("fs", "L", "concept of an app UI breakdown: the key line in a phone-shaped frame"),
    "B01": ("fs", "", "concept of a browser flythrough: a browser frame showing the source's own address"),
    "B02": ("fw", "l", "concept of floating screenshot cards: the lines as cards that float left and right"),
    "B03": ("s", "L", "concept of a device showcase: the key line inside a phone-shaped frame"),
    "B06": ("fws", "", "concept of a product cut-out reveal: the key line in a frame that lifts into place"),
    "B07": ("sw", "l", "concept of an animated map journey: a route with a stop for each line"),
    "B09": ("fw", "l", "concept of a document flyover: a sheet with the lines as a checklist"),
    "B10": ("s", "L", "concept of an interface component breakdown: a browser frame holding the key line"),
    "V07": ("fw", "L", "concept of a callout bubble: the key line in a speech bubble"),
    "H04": ("h", "", "concept of result before process: the film's last heading shown first, as a teaser"),
    "M01": ("*", "p", "a snap zoom: the photo punches in fast and settles"),
    "M06": ("hws", "p", "a speed ramp: the photo's push-in starts slow and ends fast"),
    "M10": ("h", "", "a stutter: the heading steps in over four frames"),
    "C01": ("*", "VT", "concept of karaoke captions: each subtitle word turns dark as the voice reaches it"),
    "F01": ("*", "", "photos in a clean creator grade: a touch of contrast and saturation"),
    "F04": ("*", "", "photos with a cool shadow tint (the concept of teal shadows)"),
}


# how many of the scene's lines a concept diagram shows (and so takes off the plain list); a kind not listed shows one
CONSUME = {"orbit": 3, "receipt": 3, "float": 3, "checklist": 3, "carousel": 1, "ticker": 1, "stack": 3, "split": 2,
           "pip": 2, "wipe": 2, "chat": 3, "route": 3, "wall": 0, "echo": 0, "teaser": 0, "search": 0, "tunnel": 1}
MULTI_CODES = {c for c, k in KIND.items() if CONSUME.get(k, 1) >= 2}


class Ctx(NamedTuple):
    scale: float
    box_w: float
    gap: float
    fs: float                                   # the type of every concept block (46px at 1080 wide)
    pad: float
    host: str                                   # the source's host, when the idea has one
    text_h: Callable[..., float]


def esc(s: Any) -> str:
    return html_mod.escape(str(s), quote=False)


def host_of(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/?#]+)", str(url or ""))
    return m.group(1)[:40] if m else ""


def css(c: Ctx, accent: str, rgba: Callable[[str, float], str]) -> list[str]:
    s, fs, pad = c.scale, c.fs, c.pad
    ring = f"{max(3, 4 * s):.0f}px solid {accent}"
    soft = f"{max(2, 3 * s):.0f}px solid {rgba(accent, .45)}"
    paper = "background:rgba(255,255,255,.76);"
    return [
        f".cb{{flex:none;box-sizing:border-box;width:100%;font-size:{fs:.0f}px;line-height:1.22;font-weight:600;}}",
        ".cb .cbt{overflow-wrap:anywhere;}",
        f".dev{{width:{c.box_w * .62:.0f}px;align-self:center;border:{ring};border-radius:{44 * s:.0f}px;{paper}"
        f"padding:{pad * 1.4:.0f}px {pad:.0f}px;text-align:center;}}",
        f".dev .nt{{display:block;width:{120 * s:.0f}px;height:{14 * s:.0f}px;background:{accent};border-radius:{8 * s:.0f}px;"
        f"margin:0 auto {pad:.0f}px;}}",
        f".brw{{border:{ring};border-radius:{24 * s:.0f}px;{paper}overflow:hidden;}}",
        f".brw .bar{{display:flex;align-items:center;gap:{12 * s:.0f}px;padding:{pad * .5:.0f}px {pad:.0f}px;"
        f"background:{rgba(accent, .16)};}}",
        f".brw .sq{{width:{16 * s:.0f}px;height:{16 * s:.0f}px;background:{accent};border-radius:{4 * s:.0f}px;flex:none;}}",
        f".brw .ad{{flex:1;min-width:0;padding:{6 * s:.0f}px {14 * s:.0f}px;background:#fff;border-radius:{12 * s:.0f}px;"
        f"font-weight:500;overflow-wrap:anywhere;}}",
        f".brw .bd2{{padding:{pad:.0f}px;}}",
        f".sk{{border:{soft};border-radius:{20 * s:.0f}px;{paper}padding:{pad:.0f}px;margin-bottom:{c.gap * .4:.0f}px;}}",
        f".sk:nth-child(2){{margin-left:{40 * s:.0f}px;}} .sk:nth-child(3){{margin-left:{80 * s:.0f}px;}}",
        f".two{{display:flex;gap:{c.gap:.0f}px;}} .two>div{{flex:1;min-width:0;border:{soft};border-radius:{20 * s:.0f}px;{paper}"
        f"padding:{pad:.0f}px;position:relative;overflow:hidden;}}",
        f".two>div.hit{{border:{ring};}}",
        f".wp{{position:absolute;left:0;top:0;width:100%;height:100%;background:{rgba(accent, .18)};transform-origin:100% 50%;}}",
        f".bub{{position:relative;border:{soft};{paper}border-radius:{26 * s:.0f}px;padding:{pad:.0f}px {pad * 1.2:.0f}px;}}",
        f".bub.tail{{margin-bottom:{22 * s:.0f}px;}}",
        f".bub.tail::after{{content:\"\";position:absolute;left:{60 * s:.0f}px;bottom:-{20 * s:.0f}px;width:0;height:0;"
        f"border-left:{16 * s:.0f}px solid transparent;border-right:{16 * s:.0f}px solid transparent;"
        f"border-top:{20 * s:.0f}px solid {rgba(accent, .45)};}}",
        f".chat{{display:flex;flex-direction:column;gap:{c.gap * .5:.0f}px;}}",
        f".chat .bub{{max-width:78%;}} .chat .bub.me{{align-self:flex-end;background:{rgba(accent, .16)};}}",
        f".docs{{border:{soft};border-radius:{14 * s:.0f}px;{paper}padding:{pad:.0f}px;}}",
        f".docs .bar2{{height:{14 * s:.0f}px;border-radius:{8 * s:.0f}px;background:{rgba(accent, .18)};"
        f"margin-bottom:{16 * s:.0f}px;}}",
        f".docs .hl{{background:{rgba(accent, .22)};padding:0 {10 * s:.0f}px;border-radius:{8 * s:.0f}px;}}",
        f".srch{{display:flex;align-items:center;gap:{14 * s:.0f}px;border:{ring};border-radius:{60 * s:.0f}px;{paper}"
        f"padding:{pad * .7:.0f}px {pad * 1.2:.0f}px;margin-bottom:{c.gap * .5:.0f}px;}}",
        f".srch .sq{{width:{22 * s:.0f}px;height:{22 * s:.0f}px;border:{max(3, 4 * s):.0f}px solid {accent};"
        f"border-radius:{6 * s:.0f}px;flex:none;}}",
        f".wall{{display:grid;grid-template-columns:1fr 1fr;gap:{c.gap * .5:.0f}px;}}",
        f".wall>div{{border:{soft};border-radius:{16 * s:.0f}px;{paper}padding:{pad * .7:.0f}px;text-align:center;"
        "font-weight:700;"
        f"overflow-wrap:anywhere;}}",
        f".ech{{font-weight:800;line-height:1.1;color:{accent};}}",
        ".tun{display:flex;justify-content:center;}",
        f".tun>div{{border:{soft};border-radius:{24 * s:.0f}px;padding:{pad * .8:.0f}px;}}",
        f".tun>div>div{{border:{soft};border-radius:{20 * s:.0f}px;padding:{pad * .8:.0f}px;{paper}text-align:center;}}",
        f".frm{{position:relative;border:{soft};border-radius:{20 * s:.0f}px;{paper}padding:{pad * 1.2:.0f}px;"
        "text-align:center;}}",
        f".frm i{{position:absolute;width:{44 * s:.0f}px;height:{44 * s:.0f}px;border:{ring};}}",
        ".frm i.a{left:-4px;top:-4px;border-right:0;border-bottom:0;}",
        ".frm i.b{right:-4px;bottom:-4px;border-left:0;border-top:0;}",
        f".rte{{position:relative;display:flex;border-top:{max(4, 5 * s):.0f}px dashed {accent};padding-top:{30 * s:.0f}px;}}",
        f".rte>div{{flex:1;min-width:0;position:relative;padding-right:{c.gap * .4:.0f}px;}}",
        f".rte>div::before{{content:\"\";position:absolute;left:0;top:-{44 * s:.0f}px;width:{22 * s:.0f}px;height:{22 * s:.0f}px;"
        f"background:{accent};border-radius:{4 * s:.0f}px;}}",
        f".tz{{border:{ring};border-radius:{20 * s:.0f}px;{paper}padding:{pad:.0f}px;}} .tz b{{color:{accent};}}",
        f".flt>div{{width:86%;border:{soft};border-radius:{20 * s:.0f}px;{paper}padding:{pad:.0f}px;"
        f"margin-bottom:{c.gap * .4:.0f}px;}}",
        ".flt>div:nth-child(even){margin-left:auto;}",
        f".orb{{display:flex;gap:{c.gap * .6:.0f}px;}} .orb>div{{flex:1;min-width:0;border:{soft};border-radius:{20 * s:.0f}px;"
        f"{paper}padding:{pad * .8:.0f}px;text-align:center;overflow-wrap:anywhere;}}",
        f".car{{display:flex;align-items:center;gap:{c.gap * .5:.0f}px;}} .car .chv{{flex:none;font-weight:800;color:{accent};"
        f"font-size:{fs * 1.5:.0f}px;line-height:1;}} .car .cd2{{flex:1;min-width:0;border:{ring};border-radius:{24 * s:.0f}px;"
        f"{paper}padding:{pad:.0f}px;text-align:center;}}",
        f".cars{{display:flex;justify-content:center;gap:{12 * s:.0f}px;margin-top:{16 * s:.0f}px;}}",
        f".cars i{{width:{18 * s:.0f}px;"
        f"height:{18 * s:.0f}px;background:{rgba(accent, .3)};border-radius:{4 * s:.0f}px;}} .cars i.on{{background:{accent};}}",
        f".rcp{{border-left:{soft};border-right:{soft};{paper}padding:{pad:.0f}px {pad * 1.2:.0f}px;}}",
        f".rcp .rw{{display:flex;gap:{c.gap * .4:.0f}px;padding:{8 * s:.0f}px 0;border-bottom:{max(2, 3 * s):.0f}px dashed "
        f"{rgba(accent, .4)};}}",
        f".rcp .rw b{{color:{accent};flex:none;}} .rcp .rw span{{flex:1;min-width:0;overflow-wrap:anywhere;}}",
        f".tkr{{display:flex;align-items:center;gap:{c.gap * .6:.0f}px;background:{accent};color:#fff;"
        f"border-radius:{14 * s:.0f}px;"
        f"padding:{pad * .7:.0f}px {pad:.0f}px;}} .tkr b{{flex:none;background:#fff;color:{accent};border-radius:{8 * s:.0f}px;"
        f"padding:{4 * s:.0f}px {14 * s:.0f}px;}} .tkr span{{flex:1;min-width:0;overflow-wrap:anywhere;}}",
        f".chk{{border:{soft};border-radius:{14 * s:.0f}px;{paper}padding:{pad:.0f}px;}}",
        f".chk .rw{{display:flex;gap:{c.gap * .5:.0f}px;padding:{6 * s:.0f}px 0;}}",
        f".chk .bx{{flex:none;width:{40 * s:.0f}px;height:{40 * s:.0f}px;border:{ring};border-radius:{8 * s:.0f}px;"
        f"color:{accent};font-weight:800;text-align:center;line-height:{36 * s:.0f}px;}} .chk .rw span{{flex:1;min-width:0;}}",
    ]


class Block(NamedTuple):
    html: str
    height: float
    tweens: Callable[[float], list[str]]


def whole(texts: list[str], fs: float, width: float) -> bool:
    """Every word fits `width` unbroken: a word the box would split in half or clip is a reason to draw no diagram."""
    return all(len(word) * fs * 0.6 <= width for t in texts for word in str(t).split())


def build(kind: str, sid: str, c: Ctx, heading: str, lines: list[str], teaser: str = "") -> Block | None:
    """The concept block of `kind` for a scene, or None when its words cannot carry it."""
    fs, pad, w = c.fs, c.pad, c.box_w
    key = lines[0] if lines else heading
    if not key:
        return None
    # the narrowest place each kind sets its words, so a long word can never be split or clipped
    narrow = {"device": w * .62 - 2 * pad, "browser": w - 2 * pad, "stack": w - 2 * pad - 80 * c.scale,
              "split": (w - c.gap) / 2 - 2 * pad, "wipe": (w - c.gap) / 2 - 2 * pad, "pip": (w - c.gap) * .37 - 2 * pad,
              "chat": w * .78 - 2.4 * pad, "route": w / 3 - c.gap * .4, "callout": w - 2.4 * pad, "mark": w - 2.4 * pad,
              "doc": w - 2 * pad, "frame": w - 2.4 * pad, "tunnel": w - 6 * pad, "teaser": w - 2 * pad,
              "search": w - 3 * pad - 40 * c.scale, "echo": w, "wall": (w - c.gap * .5) / 2 - 1.4 * pad,
              "float": w * .86 - 2 * pad, "orbit": (w - c.gap * 1.2) / 3 - 1.6 * pad, "carousel": w - 2 * pad - 2 * fs * 1.1,
              "receipt": w - 2.4 * pad - 3 * fs, "ticker": w - 2 * pad - 5 * fs,
              "checklist": w - 2 * pad - 40 * c.scale - c.gap * .5}.get(kind, w)
    shown = {"split": lines[:2], "wipe": lines[:2], "pip": lines[:2], "stack": lines[:3], "chat": lines[:3], "route": lines[:3],
             "search": [heading or key, key], "teaser": [teaser], "echo": [heading or key], "wall": [],
             "float": lines[:3], "orbit": lines[:3], "receipt": lines[:3], "checklist": lines[:3]}.get(kind, [key])
    if not whole(shown, fs, narrow):
        return None
    th = c.text_h
    s = c.scale
    uid = f"{sid}-cb"

    def fade(at: float) -> list[str]:
        return [f'tl.fromTo("#{uid}",{{opacity:0,y:{26 * s:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power2.out"}},{at:g});']

    if kind == "device":
        h = th(key, fs, .56, w * .62 - 2 * pad) + 14 * s + 2 * pad * 2.4 + pad
        return Block(f'<div class="cb dev" id="{uid}"><i class="nt"></i><div class="cbt">{esc(key)}</div></div>', h, fade)
    if kind == "browser":
        addr = c.host or "ws.regulab"
        h = th(addr, fs, .56, w - 5 * pad) + pad + th(key, fs, .56, w - 2 * pad) + 2 * pad + 8 * s
        return Block(f'<div class="cb brw" id="{uid}"><div class="bar"><i class="sq"></i><i class="sq"></i><i class="sq"></i>'
                     f'<div class="ad">{esc(addr)}</div></div><div class="bd2 cbt">{esc(key)}</div></div>', h, fade)
    if kind in {"stack", "split", "pip", "wipe", "chat", "route", "wall"} and not lines and kind not in {"wall"}:
        return None
    if kind == "stack":
        use = lines[:3]
        h = sum(th(t, fs, .56, w - 2 * pad - 80 * s) + 2 * pad + c.gap * .4 + 6 * s for t in use)
        inner = "".join(f'<div class="sk {sid}-sk">{esc(t)}</div>' for t in use)
        return Block(f'<div class="cb" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-sk",{{opacity:0,x:{-80 * s:.0f}}},{{opacity:1,x:0,duration:.5,ease:"power3.out",stagger:.25}},'
            f'{at:g});'])
    if kind in {"split", "pip", "wipe"}:
        if len(lines) < 2:
            return None
        colw = (w - c.gap) / 2 - 2 * pad
        a, b = lines[0], lines[1]
        h = max(th(a, fs, .56, colw), th(b, fs, .56, colw)) + 2 * pad + 8 * s
        wipe = f'<i class="wp" id="{sid}-wp"></i>' if kind == "wipe" else ""
        first = f'<div>{esc(a)}</div>'
        second = f'<div class="hit">{esc(b)}{wipe}</div>'
        if kind == "pip":
            first = f'<div style="flex:1.7">{esc(a)}</div>'
            second = f'<div class="hit" style="flex:1">{esc(b)}</div>'
            colw = (w - c.gap) * .37 - 2 * pad
            h = max(th(a, fs, .56, (w - c.gap) * .63 - 2 * pad), th(b, fs, .56, colw)) + 2 * pad + 8 * s

        def tw(at: float, kind: str = kind) -> list[str]:
            out = fade(at)
            if kind == "wipe":
                out.append(f'tl.fromTo("#{sid}-wp",{{scaleX:1}},{{scaleX:0,duration:.9,ease:"power2.inOut"}},{at + .5:g});')
            return out
        return Block(f'<div class="cb two" id="{uid}">{first}{second}</div>', h, tw)
    if kind in {"callout", "mark"}:
        body = esc(key) if kind == "callout" else f'<span class="kw">{esc(key)}<i id="{sid}-mk"></i></span>'
        h = th(key, fs, .56, w - 2.4 * pad) + 2 * pad + (22 * s if kind == "callout" else 8 * s)

        def tw2(at: float, kind: str = kind) -> list[str]:
            out = fade(at)
            if kind == "mark":
                out.append(f'tl.fromTo("#{sid}-mk",{{scaleX:0}},{{scaleX:1,duration:.6,ease:"power2.inOut"}},{at + .5:g});')
            return out
        return Block(f'<div class="cb bub {"tail" if kind == "callout" else ""}" id="{uid}">{body}</div>', h, tw2)
    if kind == "chat":
        if len(lines) < 2:
            return None
        use = lines[:3]
        h = sum(th(t, fs, .56, w * .78 - 2.4 * pad) + 2 * pad + c.gap * .5 for t in use)
        inner = "".join(f'<div class="bub {"me" if i % 2 else ""} {sid}-bu">{esc(t)}</div>' for i, t in enumerate(use))
        return Block(f'<div class="cb chat" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-bu",{{opacity:0,scale:.8}},{{opacity:1,scale:1,duration:.4,ease:"power2.out",stagger:.35}},{at:g});'])
    if kind == "doc":
        h = 3 * (14 * s + 16 * s) + th(key, fs, .56, w - 2 * pad) + 2 * pad + 8 * s
        bars = '<div class="bar2"></div><div class="bar2" style="width:82%"></div><div class="bar2" style="width:64%"></div>'
        return Block(f'<div class="cb docs" id="{uid}">{bars}<div class="cbt"><span class="hl">{esc(key)}</span></div></div>',
                     h, fade)
    if kind == "search":
        q = heading or key
        h = th(q, fs, .56, w - 3 * pad - 40 * s) + 1.4 * pad + 12 * s + th(key, fs, .56, w - 2 * pad) + 2 * pad
        typed = " ".join('<span class="wd">' + "".join(f'<span class="{sid}-sc">{esc(ch)}</span>' for ch in wd) + "</span>"
                         for wd in q.split())
        return Block(f'<div class="cb" id="{uid}"><div class="srch"><i class="sq"></i><div class="cbt">{typed}</div></div>'
                     f'<div class="sk" style="margin-left:0">{esc(key)}</div></div>', h, lambda at: [
            *fade(at), f'tl.fromTo(".{sid}-sc",{{opacity:0}},{{opacity:1,duration:.01,stagger:.04}},{at + .3:g});'])
    if kind == "wall":
        words = list(dict.fromkeys(x.strip(".,:;!?\"'()") for x in (heading + " " + " ".join(lines)).split()
                                   if len(x.strip(".,:;!?\"'()")) >= 4))[:6]
        words = [x for x in words if whole([x], fs, narrow)]
        if len(words) < 3:
            return None
        rows = (len(words) + 1) // 2
        h = rows * (th(max(words, key=len), fs, .62, (w - c.gap * .5) / 2 - 1.4 * pad) + 1.4 * pad) + (rows - 1) * c.gap * .5
        inner = "".join(f"<div class=\"{sid}-wl\">{esc(x)}</div>" for x in words)
        return Block(f'<div class="cb wall" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-wl",{{opacity:0,scale:.7}},{{opacity:1,scale:1,duration:.35,ease:"power2.out",stagger:.12}},{at:g});'])
    if kind == "echo":
        t = heading or key
        h = 3 * th(t, fs, .62, w) * 1.0
        inner = "".join(f'<div class="ech {sid}-ec" style="opacity:{o}">{esc(t)}</div>' for o in (1, .55, .28))
        return Block(f'<div class="cb" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-ec",{{opacity:0,x:{-60 * s:.0f}}},{{opacity:(i,el)=>[1,.55,.28][i],x:0,duration:.5,stagger:.2}},'
            f'{at:g});'])
    if kind == "tunnel":
        h = th(key, fs, .56, w - 6 * pad) + 6 * pad + 16 * s
        return Block(f'<div class="cb tun" id="{uid}"><div><div><div class="cbt">{esc(key)}</div></div></div></div>',
                     h, lambda at: [
            f'tl.fromTo("#{uid}",{{opacity:0,scale:1.25}},{{opacity:1,scale:1,duration:.7,ease:"power3.out"}},{at:g});'])
    if kind == "frame":
        h = th(key, fs, .56, w - 2.4 * pad) + 2.4 * pad + 8 * s
        return Block(f'<div class="cb frm" id="{uid}"><i class="a"></i><i class="b"></i><div class="cbt">{esc(key)}</div></div>',
                     h, fade)
    if kind == "route":
        if len(lines) < 2:
            return None
        use = lines[:3]
        cw = w / len(use) - c.gap * .4
        h = max(th(t, fs, .56, cw) for t in use) + 30 * s + 44 * s
        inner = "".join(f'<div class="{sid}-rs">{esc(t)}</div>' for t in use)
        return Block(f'<div class="cb rte" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-rs",{{opacity:0,y:{20 * s:.0f}}},{{opacity:1,y:0,duration:.4,stagger:.3}},{at:g});'])
    if kind == "float":
        use = lines[:3]
        h = sum(th(t, fs, .56, w * .86 - 2 * pad) + 2 * pad + c.gap * .4 + 6 * s for t in use)
        inner = "".join(f"<div class=\"{sid}-fc\">{esc(t)}</div>" for t in use)
        return Block(f'<div class="cb flt" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-fc",{{opacity:0,y:{40 * s:.0f}}},{{opacity:1,y:0,duration:.5,ease:"power3.out",stagger:.25}},'
            f'{at:g});'])
    if kind == "orbit":
        use = lines[:3]
        if len(use) < 2:
            return None
        cw = (w - c.gap * 1.2) / len(use) - 1.6 * pad
        h = max(th(t, fs, .56, cw) for t in use) + 1.6 * pad + 8 * s
        inner = "".join(f"<div class=\"{sid}-oc\">{esc(t)}</div>" for t in use)
        return Block(f'<div class="cb orb" id="{uid}">{inner}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-oc",{{opacity:0,scale:.6}},{{opacity:1,scale:1,duration:.45,ease:"power3.out",stagger:.18}},'
            f'{at:g});'])
    if kind == "carousel":
        dots = "".join(f'<i class="{"on" if i == 0 else ""}"></i>' for i in range(min(3, max(2, len(lines) or 2))))
        h = th(key, fs, .56, w - 2 * pad - 2 * fs * 1.1) + 2 * pad + 18 * s + 16 * s + 8 * s
        return Block(f'<div id="{uid}" class="cb"><div class="car"><span class="chv">‹</span><div class="cd2">{esc(key)}</div>'
                     f'<span class="chv">›</span></div><div class="cars">{dots}</div></div>', h, lambda at: [
            f'tl.fromTo("#{uid}",{{opacity:0,x:{120 * s:.0f}}},{{opacity:1,x:0,duration:.6,ease:"power3.out"}},{at:g});'])
    if kind == "receipt":
        use = lines[:3]
        h = sum(th(t, fs, .56, w - 2.4 * pad - 3 * fs) + 16 * s + 3 * s for t in use) + 2 * pad
        rows = "".join(f'<div class="rw {sid}-rr"><span>{esc(t)}</span><b>✓</b></div>' for t in use)
        return Block(f'<div class="cb rcp" id="{uid}">{rows}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-rr",{{opacity:0,y:{-30 * s:.0f}}},{{opacity:1,y:0,duration:.4,ease:"power2.out",stagger:.3}},'
            f'{at:g});'])
    if kind == "ticker":
        h = th(key, fs, .56, w - 2 * pad - 5 * fs) + 1.4 * pad + 8 * s
        return Block(f'<div class="cb tkr" id="{uid}"><b>▸</b><span>{esc(key)}</span></div>', h, lambda at: [
            f'tl.fromTo("#{uid}",{{opacity:0,x:{-160 * s:.0f}}},{{opacity:1,x:0,duration:.5,ease:"power3.out"}},{at:g});'])
    if kind == "checklist":
        use = lines[:3]
        h = sum(th(t, fs, .56, w - 2 * pad - 40 * s - c.gap * .5) + 12 * s for t in use) + 2 * pad + 8 * s
        rows = "".join(f'<div class="rw {sid}-ck"><i class="bx">✓</i><span>{esc(t)}</span></div>' for t in use)
        return Block(f'<div class="cb chk" id="{uid}">{rows}</div>', h, lambda at: [
            f'tl.fromTo(".{sid}-ck",{{opacity:0,x:{-50 * s:.0f}}},{{opacity:1,x:0,duration:.4,ease:"power2.out",stagger:.3}},'
            f'{at:g});'])
    if kind == "teaser":
        if not teaser:
            return None
        h = th(teaser, fs, .56, w - 2 * pad) + 2 * pad + 8 * s
        return Block(f'<div class="cb tz" id="{uid}"><b>→</b> {esc(teaser)}</div>', h, fade)
    return None
