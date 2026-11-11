"""A picture drawn for each scene of a Motion film, from its storyboard and the styles chosen (Wan, 5 Nov 2026: "for motion - add
codex or chatgpt login Oauth, so image motion can generate based on story board and styles apply").

The storyboard is the writer's plan: the scenes, each with its heading, its lines on screen and its narration. For every scene
that is not the closing card this module asks ChatGPT (through Wan's saved login, semasa.chatgpt_login) for one picture, and the
prompt carries the film's look: the design (Bright Editorial or Continuous Line), the platform's palette and the chosen ambient
colour, the style repo's name, and the platform's tone (ws.regulab or LinkedIn). The picture becomes that scene's own photo, so
the style chooser frames it like any photograph (an arch, a side-by-side, a full-bleed ground) and Unsplash keeps every scene
this module did not draw.

Gemini (gemini_images.py, Wan's key pool) draws a scene ChatGPT could not, or every scene when ChatGPT is not connected, and
Cloudflare Workers AI (cloudflare_images.py, the free FLUX allowance) draws a scene neither could. When the storyboard
(motion_storyboard.py) has written a SHOT for a scene, that shot is what is drawn.

Nothing here may stop a film. Not connected, switched off, a login ChatGPT refuses, the plan's allowance used up, a scene whose
picture comes back empty: each is a note in the film's report and the scene keeps what it had. The picture is illustration, never
evidence, so every prompt forbids words, logos, packaging, faces and anything that reads as a before-and-after or a cure.
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

from PIL import Image

from . import chatgpt_login, cloudflare_images, gemini_images
from .log import get_logger

log = get_logger("semasa.motion.gpt")

BUDGET_S = 480                    # all the pictures of one film together: the film is rendered after, and the job has 30 minutes
LABEL = {"chatgpt": "ChatGPT", "gemini": "Gemini", "cloudflare": "Cloudflare"}
ORDER = ("chatgpt", "gemini", "cloudflare")             # who draws a scene first, for an explainer film
MIN_SIDE = 256              # a picture smaller than this on either side is not a picture

LOOK = {
    "bright-editorial": "bright editorial photo-illustration: clean and airy, soft natural daylight, gentle depth of field, "
                        "calm composition with generous empty space for large type",
    "continuous-line": "one continuous hand-drawn line illustration on a pale ground: minimal, a single flowing ink line, "
                       "a few flat colour accents, lots of white space",
    # the 2D film styles (motion_skins): the scene's picture is drawn in the film's own look, so it sits inside the style
    # instead of being a photograph pasted onto it (Wan, 11 Nov 2026: "the motion must be embedded with generated images")
    "comic": "comic-book panel illustration: thick black ink outlines, flat red, yellow and "
              "blue, halftone dot shading, cream paper",
    "pixel": "16-colour pixel art scene on a dark navy night ground, chunky square pixels, warm yellow and orange highlights",
    "chalk": "white and pastel chalk drawing on a dark green chalkboard: hand-drawn, slightly rough strokes, no photograph",
    "glow": "warm white glowing line drawing on a pure black ground: outlines only, soft neon glow, no fills",
    "flat": "flat vector illustration: no gradients, no outlines, deep navy and muted blue shapes with one orange accent",
    "papercut": "layered paper cut-out illustration: torn kraft paper shapes in cream, tan, "
                 "terracotta and brown with soft drop shadows",
    "dankoe": "minimal fine white line drawing on pure black: very few thin lines, lots of empty space, no colour",
    "riso": "two-colour risograph print illustration: blue and pink inks with a little "
             "yellow, visible grain, slightly off register, cream paper",
    "blueprint": "technical blueprint drawing: fine white line work, centre lines and dimension "
                  "marks on Prussian blue paper, no shading",
    "transit": "clean transit-map style diagram illustration on off-white paper: bold flat "
                "lines and dots in red, blue, green and yellow",
    "swiss": "Swiss graphic design poster illustration: high-contrast black and white "
              "photograph or shapes on white with one red element",
    "whiteboard": "dry-erase marker drawing on a white board: dark blue marker lines with small "
                   "red and green accents, hand-drawn",
}
OWN_PALETTE = frozenset(LOOK) - {"bright-editorial", "continuous-line"}      # looks that carry their own colours
TONE = {
    "regulab": "warm, friendly and clear, for small Malaysian businesses",
    "linkedin": "sober, credible and professional, for industry peers",
}
ROLE = {
    "hook": "an arresting establishing image that makes a viewer stop scrolling",
    "fact": "an objective, documentary-style still life of the subject (a bench, a shelf, a document, an instrument)",
    "why": "a clear visual metaphor for the one detail most people overlook",
    "solution": "a calm, welcoming image of a situation in order that invites the viewer to come back for more",
}
NEVER = ("No text, no letters, no numbers, no logos, no brand names, no packaging or product labels, no watermarks. "
         "No recognisable real person and no clear faces. No before-and-after, no medical or cure imagery, no warning signs. "
         "It is an illustration of the topic and never evidence of anything.")


def ready(store: Any, *, login: Any = None, gemini: Any = None, cloudflare: Any = None) -> bool:
    """Whether any picture maker can draw now (ChatGPT connected and on, a usable Gemini key, or Cloudflare set up): the
    storyboard is only worth writing when something will draw it."""
    cfg = (login or chatgpt_login.Login(store)).settings()
    if cfg and cfg.get("enabled"):
        return True
    return bool((gemini if gemini is not None else gemini_images.Drawer(store)).ready()
                or (cloudflare if cloudflare is not None else cloudflare_images.Drawer(store)).ready())


def size_for(resolution: str) -> str:
    return chatgpt_login.SIZES.get(resolution, "1024x1024")


def scene_prompt(row: dict[str, Any], sc: dict[str, Any], *, design: str, palette: dict[str, str], ambient: str,
                 style_name: str = "") -> str:
    """The picture request for one scene of the storyboard."""
    stream = "linkedin" if row.get("stream") == "linkedin" else "regulab"
    said = " ".join(x for x in (sc.get("heading"), *(sc.get("lines") or [])) if isinstance(x, str) and x.strip())
    told = " ".join(str(sc.get("narration") or "").split())
    role = ROLE.get(str(sc.get("role") or "").lower(), "a clear, specific image of the scene's subject")
    brief = " ".join(str(row.get("brief") or "").split())[:240]
    shot = " ".join(str(sc.get("shot") or "").split())[:340]      # the storyboard shot written for this scene, if any
    mood = " ".join(str(sc.get("mood") or "").split())[:80]
    parts = [
        f"A picture for one scene of a short explainer video. Scene: {' '.join(said.split())[:260]}.",
        f"What the narrator says over it: {told[:300]}." if told else "",
        f"The film's topic: {brief}." if brief else "",
        f"Directed shot (draw this): {shot}." if shot else f"Show {role}.",
        f"Mood: {mood}." if shot and mood else "",
        f"Look: {LOOK.get(design, LOOK['bright-editorial'])}.",
        "" if design in OWN_PALETTE else (
            f"Palette: ground {palette.get('ground', '#e5f6ed')}, ink {palette.get('ink', '#143e35')}, "
            f"accent {palette.get('accent', '#287b65')}"
            + (f", with a soft {ambient} ambient tone" if ambient else "") + "."),
        f"Tone: {TONE[stream]}.",
        f"In the visual spirit of the chosen style reference: {style_name}." if style_name else "",
        NEVER,
    ]
    return " ".join(p for p in parts if p)


def storyboard(scenes: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """The scenes that get a picture: every teaching scene in order (never the closing card), at most `limit`."""
    return [sc for sc in scenes if sc.get("id") != "brand-outro" and (sc.get("heading") or sc.get("narration"))][:max(0, limit)]


def save(data: bytes, folder: Path, name: str) -> str:
    """The picture as assets/<name>.jpg at 1600 px at most; raises on bytes that are not a usable picture."""
    im = Image.open(io.BytesIO(data))
    im.load()
    if min(im.size) < MIN_SIDE:
        raise ValueError(f"picture too small ({im.size[0]}x{im.size[1]})")
    im = im.convert("RGB")
    im.thumbnail((1600, 1600))
    rel = f"assets/{name}.jpg"
    (folder / "assets").mkdir(parents=True, exist_ok=True)
    im.save(folder / rel, "JPEG", quality=88)
    return rel


def draw_scenes(store: Any, row: dict[str, Any], scenes: list[dict[str, Any]], folder: Path, *, design: str,
                palette: dict[str, str], ambient: str, resolution: str, style_name: str = "", login: Any = None,
                clock: Any = None, gemini: Any = None, cloudflare: Any = None, order: tuple[str, ...] = ORDER,
                prompt_of: Any = None) -> tuple[dict[str, dict[str, Any]], str]:
    """({scene id: photo} for the scenes drawn, note). A photo is {path, id, credit, page, alt, generated} like the others, so the
    film's report and credits treat it the same way. ({}, note) when nothing was drawn, and the note says why.

    Each scene is drawn by ChatGPT (Wan's login) and, when that fails or is not connected, by Gemini (his key pool,
    gemini_images.py), and when that fails too, by Cloudflare Workers AI (cloudflare_images.py).
    A provider whose allowance is used up or whose login is refused is not asked again for the rest of the film.

    `order` changes who is asked first (the film templates ask ChatGPT, then Cloudflare, then Gemini: Wan, 7 Nov 2026, "picture
    from chatgpt or cloudflare"), and `prompt_of(scene)` gives a scene's whole picture request when the caller wrote its own."""
    login = login or chatgpt_login.Login(store)
    drawer = gemini if gemini is not None else gemini_images.Drawer(store)
    cfg = login.settings()
    chatgpt_on = bool(cfg and cfg["enabled"])
    gemini_on = bool(drawer.ready())
    flare = cloudflare if cloudflare is not None else cloudflare_images.Drawer(store)
    flare_on = bool(flare.ready())
    if cfg is None and not gemini_on and not flare_on:
        return {}, ""                                     # nothing connected: not worth a line in every film's report
    if not chatgpt_on and not gemini_on and not flare_on:
        return {}, "ChatGPT pictures: switched off"
    clock = clock or time.monotonic
    started = clock()
    todo = storyboard(scenes, cfg["max_images"] if cfg else drawer.max_images())
    on = {"chatgpt": chatgpt_on, "gemini": gemini_on, "cloudflare": flare_on}
    active = [name for name in dict.fromkeys(order) if on.get(name)]
    tripped: set[str] = set()
    out: dict[str, dict[str, Any]] = {}
    by: dict[str, int] = {"chatgpt": 0, "gemini": 0, "cloudflare": 0}
    problems: list[str] = []
    for sc in todo:
        if clock() - started > BUDGET_S:
            problems.append("out of time for the rest")
            break
        if all(name in tripped for name in active):
            break
        sid = str(sc.get("id") or len(out))
        prompt = (prompt_of(sc) if prompt_of else
                  scene_prompt(row, sc, design=design, palette=palette, ambient=ambient, style_name=style_name))
        for name in active:
            if name in tripped:
                continue
            try:
                if name == "chatgpt":
                    data = login.draw(prompt, size=size_for(resolution), model=cfg["model"])
                elif name == "gemini":
                    data = drawer.draw(prompt, resolution=resolution)
                else:
                    data = flare.draw(prompt, resolution=resolution)
                rel = save(data, folder, f"scene-{sid}")
            except chatgpt_login.ChatGPTError as exc:
                problems.append(f"{sid} (ChatGPT): {exc}")
                login.failed(str(exc))
                if exc.limit or exc.auth:
                    tripped.add("chatgpt")                  # the allowance or the login is the same for every scene
                continue
            except gemini_images.GeminiError as exc:
                problems.append(f"{sid} (Gemini): {exc}")
                if exc.limit:
                    tripped.add("gemini")
                continue
            except cloudflare_images.CloudflareError as exc:
                problems.append(f"{sid} (Cloudflare): {exc}")
                if exc.limit:
                    tripped.add("cloudflare")
                continue
            except Exception as exc:  # noqa: BLE001 - one unreadable picture never stops the film
                problems.append(f"{sid} ({LABEL[name]}): {str(exc)[:120]}")
                continue
            by[name] += 1
            out[sid] = {"path": rel, "id": f"{name}-{sid}", "credit": "", "page": "", "generated": True,
                        "alt": str(sc.get("heading") or "")[:140]}
            break
    if by["chatgpt"]:
        login.ok()
    tail = f" ({'; '.join(problems)[:300]})" if problems else ""
    if flare_on:
        note = (f"Pictures: {len(out)} of {len(todo)} scenes drawn "
                f"(ChatGPT {by['chatgpt']}, Gemini {by['gemini']}, Cloudflare {by['cloudflare']})" + tail)
    elif gemini_on:
        note = (f"Pictures: {len(out)} of {len(todo)} scenes drawn (ChatGPT {by['chatgpt']}, Gemini {by['gemini']})" + tail)
    else:
        note = f"ChatGPT pictures: {len(out)} of {len(todo)} scenes drawn" + tail
    return out, note


def pin(scenes: list[dict[str, Any]], drawn: dict[str, dict[str, Any]]) -> None:
    """Make each drawn picture its own scene's photo. It replaces what the scene had (an Unsplash photo, or one of the idea's
    own), and the second photo of a pair goes with it, because a scene shows the picture drawn for it, not a mixture."""
    for sc in scenes:
        p = drawn.get(str(sc.get("id")))
        if not p:
            continue
        sc["photo"], sc["photo_credit"] = p["path"], p.get("credit", "")
        sc.pop("photo2", None)


def used(scenes: list[dict[str, Any]], photos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The photos some scene still shows (the report and the credits list these, not pictures that were set aside)."""
    shown = {x for sc in scenes for x in (sc.get("photo"), sc.get("photo2")) if x}
    return [p for p in photos if p.get("path") in shown]
