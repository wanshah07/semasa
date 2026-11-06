"""A picture drawn for each scene of a Motion film, from its storyboard and the styles chosen (Wan, 5 Nov 2026: "for motion - add
codex or chatgpt login Oauth, so image motion can generate based on story board and styles apply").

The storyboard is the writer's plan: the scenes, each with its heading, its lines on screen and its narration. For every scene
that is not the closing card this module asks ChatGPT (through Wan's saved login, semasa.chatgpt_login) for one picture, and the
prompt carries the film's look: the design (Bright Editorial or Continuous Line), the platform's palette and the chosen ambient
colour, the style repo's name, and the platform's tone (ws.regulab or LinkedIn). The picture becomes that scene's own photo, so
the style chooser frames it like any photograph (an arch, a side-by-side, a full-bleed ground) and Unsplash keeps every scene
this module did not draw.

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

from . import chatgpt_login
from .log import get_logger

log = get_logger("semasa.motion.gpt")

BUDGET_S = 480                    # all the pictures of one film together: the film is rendered after, and the job has 30 minutes
MIN_SIDE = 256              # a picture smaller than this on either side is not a picture

LOOK = {
    "bright-editorial": "bright editorial photo-illustration: clean and airy, soft natural daylight, gentle depth of field, "
                        "calm composition with generous empty space for large type",
    "continuous-line": "one continuous hand-drawn line illustration on a pale ground: minimal, a single flowing ink line, "
                       "a few flat colour accents, lots of white space",
}
TONE = {
    "regulab": "warm, friendly and clear, for small Malaysian businesses",
    "linkedin": "sober, credible and professional, for industry peers",
}
ROLE = {
    "hook": "an arresting establishing image that makes a viewer stop scrolling",
    "fact": "an objective, documentary-style still life of the subject (a bench, a shelf, a document, an instrument)",
    "why": "a clear visual metaphor for why it matters",
    "solution": "a calm, reassuring image of a situation resolved and in order",
}
NEVER = ("No text, no letters, no numbers, no logos, no brand names, no packaging or product labels, no watermarks. "
         "No recognisable real person and no clear faces. No before-and-after, no medical or cure imagery, no warning signs. "
         "It is an illustration of the topic and never evidence of anything.")


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
    parts = [
        f"A picture for one scene of a short explainer video. Scene: {' '.join(said.split())[:260]}.",
        f"What the narrator says over it: {told[:300]}." if told else "",
        f"The film's topic: {brief}." if brief else "",
        f"Show {role}.",
        f"Look: {LOOK.get(design, LOOK['bright-editorial'])}.",
        f"Palette: ground {palette.get('ground', '#e5f6ed')}, ink {palette.get('ink', '#143e35')}, "
        f"accent {palette.get('accent', '#287b65')}"
        + (f", with a soft {ambient} ambient tone" if ambient else "") + ".",
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
                clock: Any = None) -> tuple[dict[str, dict[str, Any]], str]:
    """({scene id: photo} for the scenes drawn, note). A photo is {path, id, credit, page, alt, generated} like the others, so the
    film's report and credits treat it the same way. ({}, note) when nothing was drawn, and the note says why."""
    login = login or chatgpt_login.Login(store)
    cfg = login.settings()
    if cfg is None:
        return {}, ""                                     # not connected: not worth a line in every film's report
    if not cfg["enabled"]:
        return {}, "ChatGPT pictures: switched off"
    clock = clock or time.monotonic
    started = clock()
    todo = storyboard(scenes, cfg["max_images"])
    out: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for sc in todo:
        if clock() - started > BUDGET_S:
            problems.append("out of time for the rest")
            break
        sid = str(sc.get("id") or len(out))
        prompt = scene_prompt(row, sc, design=design, palette=palette, ambient=ambient, style_name=style_name)
        try:
            data = login.draw(prompt, size=size_for(resolution), model=cfg["model"])
            rel = save(data, folder, f"scene-{sid}")
        except chatgpt_login.ChatGPTError as exc:
            problems.append(f"{sid}: {exc}")
            login.failed(str(exc))
            if exc.limit or exc.auth:
                break                                      # the allowance or the login is the same for every scene
            continue
        except Exception as exc:  # noqa: BLE001 - one unreadable picture never stops the film
            problems.append(f"{sid}: {str(exc)[:120]}")
            continue
        out[sid] = {"path": rel, "id": f"chatgpt-{sid}", "credit": "", "page": "", "generated": True,
                    "alt": str(sc.get("heading") or "")[:140]}
    if out:
        login.ok()
    note = f"ChatGPT pictures: {len(out)} of {len(todo)} scenes drawn" + (f" ({'; '.join(problems)[:300]})" if problems else "")
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
