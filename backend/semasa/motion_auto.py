"""Automatic style choice for every motion video (Wan, 25 Oct 2026: "make sure every video apply 99 styles based on
suitability").

The 99 effects in rules/motion/style-effects.json come from video-editing guides: most of them edit footage of a speaker, a
screen recording or a real screenshot. Semasa's films have none of those (and must never invent proof), so every effect is
judged here, per film and per scene, and one of three things happens:

  * it is ASSIGNED to the scene it suits, with a one-line recipe the writer builds in HTML/CSS/GSAP (text, shapes, photos);
  * it is NATIVE: the worker animates the scene's own heading itself (H01, H03, V01, V03: native_text.py), or the mix does it
    (S05, S08, S10);
  * it is UNAVAILABLE for this film, with the reason (needs footage, a capture, a sound file, or would break a rule).

Nothing is claimed that did not happen: the row's check_report lists what was assigned, what is native and why each of the
rest was not used. The choice is deterministic for a given row (same row, same styles) and varies between rows.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .motion_styles import EFFECT_LIBRARY

NAMES = {e["id"]: e["name"] for e in EFFECT_LIBRARY["effects"]}
ROLES = ("hook", "fact", "why", "solution")
LABELS = {"bm": ("HOOK", "FAKTA", "KENAPA", "SOLUSI"), "both": ("HOOK", "FAKTA", "KENAPA", "SOLUSI"),
          "en": ("HOOK", "FACT", "WHY", "SOLUTION")}

FOOTAGE = "needs a filmed speaker or source footage; Semasa films have none"
CAPTURE = "needs a real screenshot, screen capture or verified data; it would have to be invented"
SOUND = "needs a licensed sound-effect file; the library has none"
POLICY = "breaks a house rule (transparent captions, nothing over the text, or a clean brand look)"
HEAVY = "layers that can hide text; not used while no-overlap is enforced"
UNAVAILABLE = {
    **dict.fromkeys(["X01", "X02", "X03", "X04", "X07", "X08", "L01", "L02", "L03", "L04", "L07", "M01", "M06", "M10",
                     "C01", "F01", "F04", "H04"], FOOTAGE),
    **dict.fromkeys(["P01", "P02", "P03", "P04", "P05", "P06", "P07", "P10", "B01", "B02", "B03", "B07", "B09", "B10",
                     "B06", "V07", "V09", "L10"], CAPTURE),
    **dict.fromkeys(["S01", "S02", "S03", "S04", "S06", "S07", "S09", "M05"], SOUND),
    **dict.fromkeys(["C08", "F08", "F09", "L08"], POLICY),
    **dict.fromkeys(["X05", "X09", "L09"], HEAVY),
}
NATIVE_AUDIO = {"S05": "the music drops to near-silence for a breath before the Solusi scene (voiced films)",
                "S08": "the music ducks under every spoken line (always on in the mix)",
                "S10": "the music resolves with a fade as the logo page lands (always on in the mix)"}

# id: (roles, needs, recipe). roles: h f w s or * ; needs (all must hold): p photo on the scene, n digits in the scene's words,
# l two or more lines, c a comparison, m a myth, q a question heading, b both languages, d two years in the script,
# V voiced only, S silent only. One recipe sentence each: HTML/CSS/GSAP, inside the scene's own box, never over text.
RECIPES: dict[str, tuple[str, str, str]] = {
    "H01": ("h", "", "headline lands with a scale overshoot (the worker does this itself)"),
    "H02": ("h", "", "open on a 3-frame inverted-colour flash, then settle on the headline"),
    "H03": ("h", "q", "the question builds word by word (the worker does this itself)"),
    "H05": ("h", "V", "a 3-2-1 countdown in huge numerals zooms into the first line"),
    "H06": ("h", "", "two halves of the headline panel slide together, then lock"),
    "H08": ("h", "", "a 0.15 s high-contrast flash, then ONE oversized keyword hits"),
    "H09": ("h", "m", "the common belief is struck through, the correct claim takes its place"),
    "H10": ("h", "S", "a calm 0.8 s pause with a thin rule, then the title in elegant type"),
    "C02": ("*", "V", "lines pop in one to three words at a time with a small overshoot"),
    "C03": ("*", "", "short lines type on character by character with a blinking caret"),
    "C04": ("*", "", "an accent block sweeps behind one key word per line"),
    "C05": ("*", "", "lines stack in two or three short rows that rise one after another"),
    "C06": ("*", "S", "calm sentence-case lines under a thin accent rule, crossfading softly"),
    "C07": ("*", "V", "one key word per scene bursts to several times its size, then settles"),
    "C09": ("*", "t", "lines print word by word in a monospace block with a blinking cursor"),
    "C10": ("*", "b", "the Malay line big, the English line smaller and in the second accent colour"),
    "L05": ("fws", "p", "the text panel slides in beside the photo, the photo stays in its own frame"),
    "L06": ("hw", "p", "the photo contracts into a sharp central frame with a thin accent ring"),
    "P08": ("fws", "d", "a timeline draws across and the years pop on, each with its own label"),
    "P09": ("fw", "Q", "the quoted words sit on a card behind large quote marks, revealed line by line"),
    "V01": ("fws", "", "a short chapter title rises out of a mask line (the worker does this itself)"),
    "V02": ("fws", "n", "the numbers in the words burst on one after another with a staggered pop"),
    "V03": ("fws", "", "one short heading is framed by a highlight outline (the worker does this itself)"),
    "V04": ("fs", "l", "list items slide in one by one with numbered markers; earlier ones dim"),
    "V05": ("w", "c", "two option cards fly in from opposite edges and settle side by side"),
    "V06": ("ws", "l", "a progress track with labelled steps fills from one to the next"),
    "V08": ("fw", "", "a bold shape morphs between a circle, square and triangle behind the text"),
    "V10": ("ws", "S", "the sentence appears phrase by phrase in muted type, the last key words in full colour"),
    "B04": ("fws", "l", "an icon pops in for each step with connectors drawn between them"),
    "B05": ("hws", "p", "the photo drifts slowly in two layers (a slow pan and a slower zoom) for depth"),
    "B08": ("fw", "", "circles, grids and lines drift calmly behind the text to picture the idea"),
    "X06": ("h", "p", "the photo breaks into a grid of tiles that snap together into the whole picture"),
    "X10": ("fw", "", "a blueprint grid spreads behind the text and outlines trace in"),
    "M02": ("*", "", "scenes hand over with a fast directional streak"),
    "M03": ("hws", "p", "the photo creeps in by about 6 percent over the whole scene"),
    "M04": ("s", "V", "everything holds for 0.4 s with a soft flash and a small punch, then the answer lands"),
    "M07": ("h", "", "the first frame jolts with four decaying micro-offsets (hook only, never the text block)"),
    "M08": ("*", "", "a shared shape stays in place while the scene changes around it"),
    "M09": ("*", "", "a hard-edged mask sweeps across and reveals the next scene"),
    "F02": ("*", "", "photos warmed a few hundred Kelvin with cream highlights"),
    "F03": ("*", "", "photos neutral-to-cool with deeper blues"),
    "F05": ("*", "", "photos in black and white with a firm readable contrast"),
    "F06": ("*", "", "photos with strong saturation and a punchy accent"),
    "F07": ("*", "", "photos lifted into a soft pastel floor with lower contrast"),
    "F10": ("*", "", "photos with clean neutral whites and crisp micro-contrast"),
}
NATIVE_TEXT = {"H01", "H03", "V01", "V03"}
CAPTION = ("C02", "C03", "C04", "C05", "C06", "C07", "C09", "C10")
TRANSITION = ("M02", "M08", "M09")
FINISH = ("F02", "F03", "F05", "F06", "F07", "F10")
FINISH_SCENE_BOOST = {"F05": r"\b(recall|ban|banned|warning|danger|cancel|tarik|larang|amaran|bahaya|palsu|fake)\b",
                      "F06": r"\b(tips?|easy|quick|mudah|cepat|launch|baru|new|promo)\b",
                      "F03": r"\b(tech|digital|data|ai|system|sistem|software|lab|science|sains)\b",
                      "F02": r"\b(halal|food|makanan|beauty|kosmetik|cosmetic|skin|kulit|family|keluarga)\b"}
COMPARE = re.compile(r"\b(vs|versus|berbanding|atau|bukan|but|however|whereas|sebaliknya|tetapi|beza|difference|myth|mitos)\b",
                     re.I)
MYTH = re.compile(r"\b(myth|mitos|salah faham|misconception|wrong|silap|bukan|not)\b", re.I)
STEPS = re.compile(r"\b(step|langkah|first|then|next|pertama|kedua|kemudian|seterusnya|finally|akhir)\b", re.I)
TECH = re.compile(r"\b(code|api|system|sistem|data|software|digital|ai|algorithm|database|pangkalan)\b", re.I)


def role_of(index: int) -> str:
    return ROLES[min(index, len(ROLES) - 1)]


def words_of(sc: dict[str, Any]) -> str:
    return " ".join([sc.get("kicker", ""), sc.get("heading", ""), *(sc.get("lines") or []), sc.get("narration", "")])


def _tiebreak(seed: str, code: str) -> int:
    return int(hashlib.sha1(f"{seed}:{code}".encode()).hexdigest()[:6], 16)


def _holds(needs: str, sc: dict[str, Any], ctx: dict[str, Any]) -> bool:
    text = words_of(sc)
    on_screen = " ".join([sc.get("heading", ""), *(sc.get("lines") or [])])
    for n in needs:
        ok = {
            "p": bool(sc.get("photo")),
            "n": bool(re.search(r"\d", on_screen)),
            "l": len(sc.get("lines") or []) >= 2,
            "c": bool(COMPARE.search(text) or COMPARE.search(ctx["brief"])),
            "m": bool(MYTH.search(text) or MYTH.search(ctx["brief"])),
            "q": on_screen.strip().endswith("?"),
            "b": ctx["lang"] == "both",
            "d": len(set(re.findall(r"\b(?:19|20)\d{2}\b", ctx["all_text"]))) >= 2,
            "V": ctx["voiced"],
            "S": not ctx["voiced"],
            "Q": bool(re.search(r"[“”\"]", on_screen)),
            "t": bool(TECH.search(text) or TECH.search(ctx["brief"])),
        }[n]
        if not ok:
            return False
    return True


def assign_photos(scenes: list[dict[str, Any]], photos: list[dict[str, Any]]) -> None:
    """Hook, Kenapa and Solusi carry a photo when there are three; Hook and Solusi with two; the Hook alone with one. The
    Fakta scene stays words and shapes: it is the one most likely to carry a number or a rule, and a picture is no proof."""
    slots = {3: (0, 2, 3), 2: (0, 3), 1: (0,)}.get(min(len(photos), 3), ())
    for i, sc in enumerate(s for s in scenes if s.get("id") != "brand-outro"):
        sc.pop("photo", None)
        sc.pop("photo_credit", None)
        if i in slots:
            p = photos[slots.index(i)]
            sc["photo"], sc["photo_credit"] = p["path"], p.get("credit", "")


def choose(row: dict[str, Any], scenes: list[dict[str, Any]], *, voiced: bool, lang: str,
           stream: str = "regulab") -> dict[str, Any]:
    """Assign effects to a film's teaching scenes. Returns {scenes: {id: [codes]}, video: {...}, assigned, native,
    unavailable, notes}. Needs scenes with kicker/heading/lines/narration (and photo, set by assign_photos)."""
    seed = str(row.get("id") or row.get("brief") or "x")
    teaching = [s for s in scenes if s.get("id") != "brand-outro"]
    ctx = {"brief": str(row.get("brief") or ""), "lang": lang, "voiced": voiced,
           "all_text": " ".join(words_of(s) for s in teaching) + " " + str(row.get("brief") or "")}
    out: dict[str, list[str]] = {}
    used: set[str] = set()

    def ranked(role_letter: str, sc: dict[str, Any], pool: list[str] | None = None) -> list[str]:
        cands = []
        for code, (roles, needs, _how) in RECIPES.items():
            if pool is not None and code not in pool:
                continue
            if pool is None and (code in CAPTION or code in TRANSITION or code in FINISH):
                continue
            if roles != "*" and role_letter not in roles:
                continue
            if not _holds(needs, sc, ctx):
                continue
            score = 10 + (6 if needs else 0) + (3 if code in NATIVE_TEXT else 0)
            if code == "V03" and len((sc.get("heading") or "").split()) > 3:
                continue
            if code == "V01" and len((sc.get("heading") or "").split()) > 4:
                continue
            if code == "H01" and len((sc.get("heading") or "").split()) > 5:
                continue
            cands.append((-(score), _tiebreak(seed + sc.get("id", ""), code), code))
        return [c[2] for c in sorted(cands)]

    for i, sc in enumerate(teaching):
        letter = "hfws"[min(i, 3)]
        picks: list[str] = []
        for code in ranked(letter, sc):
            if code in used or any(p[0] == code[0] for p in picks):
                continue                                 # a style once per film, and one of each family per scene
            picks.append(code)
            used.add(code)
            if len(picks) >= 3:
                break
        out[sc["id"]] = picks
    caption = next(iter(ranked("f", teaching[min(1, len(teaching) - 1)], list(CAPTION))), "C05")
    transition = next(iter(ranked("w", teaching[min(2, len(teaching) - 1)], list(TRANSITION))), "M09")
    boost = [(0 if re.search(rx, ctx["all_text"], re.I) else 1, _tiebreak(seed, c), c) for c, rx in FINISH_SCENE_BOOST.items()]
    finish = "F07" if all(b[0] for b in boost) else min(boost)[2]
    if stream == "linkedin" and finish == "F07":
        finish = "F10"
    video = {"captions": caption, "transition": transition, "finish": finish}
    native = sorted({c for codes in out.values() for c in codes if c in NATIVE_TEXT})
    audio = ["S08", "S10"] + (["S05"] if voiced else [])
    assigned = sorted({*(c for codes in out.values() for c in codes), *video.values()} - NATIVE_TEXT)
    applied = set(assigned) | set(native) | set(audio)
    unavailable = dict(UNAVAILABLE)
    unavailable.update({c: "not needed by this film's words, or it suits a different scene" for c in NAMES
                        if c not in applied and c not in unavailable})
    return {"scenes": out, "video": video, "assigned": assigned, "native": native, "audio": audio,
            "unavailable": unavailable, "considered": len(NAMES)}


def prompt_block(plan: dict[str, Any], scenes: list[dict[str, Any]]) -> str:
    """What the writer is told: per scene and for the whole film, which styles to build, one recipe each."""
    def line(code: str) -> str:
        return f"{code} {NAMES.get(code, '')}: {RECIPES[code][2]}"
    rows = []
    for sc in scenes:
        codes = [c for c in plan["scenes"].get(sc["id"], []) if c not in NATIVE_TEXT]
        if codes:
            rows.append(f"- {sc['id']} ({sc.get('role', '')}): " + "; ".join(line(c) for c in codes))
    v = plan["video"]
    rows.append("- WHOLE FILM: " + "; ".join(line(v[k]) for k in ("captions", "transition", "finish")))
    native = [c for c in plan["native"]]
    tail = (f"\nThe worker applies {', '.join(native)} to the headings itself: do not animate those headings a second time."
            if native else "")
    return ("STYLES CHOSEN FOR THIS FILM (picked for what each scene says; build each in HTML/CSS/GSAP inside the scene's own "
            "box, from the scene's own words and photos; reading time and a clean layout outrank every effect, so drop an "
            "effect rather than let it touch the words):\n" + "\n".join(rows) + tail)


def effect_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """The native text effects as the asset plan wants them, so native_text.inject can apply them."""
    return [{"id": c, "readiness": "ready", "adapter": "native-text", "asset": None,
             "reason": "Chosen automatically for this film's heading."} for c in plan["native"]]
