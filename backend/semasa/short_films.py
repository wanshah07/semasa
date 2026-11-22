"""Short-film categories (Wan, 22 Nov 2026: "Untuk short film ada kan dua kategori - kisah keluarga halal dan cats, dan kategori
ini boleh ditambah"). A category is data, not code: the same Nexabot machinery films any of them.

One file holds the built-in ones, rules/short_films.json, read by the page too (web/src/lib/shortFilms.js). Wan's own are the
settings row `short_films` ({categories: [...], hidden: [...]}), merged over the file by id, as the comic library does
(comic_library.py): a new id is added, at most `limits.own` of them, and an entry that is not a whole category is left out, never
half-used. A built-in category is never replaced by an entry of his with the same id (its hand-written script and its sheet go
with it); he can only hide it from the page's list, and `hidden` does nothing else.

  category {id, name: {bm, en}, about: {bm, en}, cast: [{name, look}], setting, style, voice: {mode, name, notes},
            scene_count, workflow, [sheet], [file], [script]}
           `look` is the character's exact appearance, repeated word for word in every scene prompt and in the character sheet.
           `voice.mode` is "narrator" (one narrator line per scene, laid over the clip and burned as a subtitle: the cats film)
           or "in_prompt" (the dialogue is written inside the scene prompt and the video speaks it: the halal family film).
           `script` is a hand-written film ({sheet_prompt, scenes: [{prompt, narration}], panel_lines, credit}), used word
           for word. A category without one is written by the writer (`write`) from its cast, setting and style plus the day's
           topic; Wan's own categories never carry one and are always narrated.

Nothing here draws or posts. `library(value)` takes the settings value the caller already holds; `write` needs a writer.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .comic_library import _line, _pair

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "short_films.json"
RULES: dict[str, Any] = json.loads(RULES_PATH.read_text(encoding="utf-8"))
LIMITS: dict[str, int] = RULES["limits"]
VOICES: list[str] = RULES["voices"]
MODES = ("narrator", "in_prompt")
OWN_WORKFLOW = "nexabot-cat-film.yml"      # the narrated machine: it draws its own character sheet, so any category can use it
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
_FIGURE = re.compile(r"\d+(?:[.,/]\d+)*")


class FilmError(Exception):
    """Why a film cannot be made from this category, in words for the run log."""


def _cast(raw: Any) -> list[dict[str, str]] | None:
    """One to `limits.cast` people (or animals), each a name and an appearance long enough to draw the same one twice."""
    people = []
    for c in raw if isinstance(raw, list) else []:
        c = c if isinstance(c, dict) else {}
        person = {"name": _line(c.get("name"), LIMITS["cast_name"]), "look": _line(c.get("look"), LIMITS["look"])}
        if not person["name"] or len(person["look"]) < 20:
            return None
        people.append(person)
    if not 1 <= len(people) <= LIMITS["cast"] or len({p["name"].lower() for p in people}) != len(people):
        return None
    return people


def _scene_count(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = 4
    return max(LIMITS["scenes_min"], min(LIMITS["scenes_max"], n))


def _script(raw: Any) -> dict[str, Any] | None:
    """A built-in category's hand-written film, kept exactly as the file has it (it is not Wan's typing, so nothing is cut)."""
    if not isinstance(raw, dict) or not isinstance(raw.get("sheet_prompt"), str):
        return None
    scenes = [s for s in raw.get("scenes") or [] if isinstance(s, dict) and isinstance(s.get("prompt"), str) and s["prompt"]]
    if not scenes:
        return None
    lines = [x for x in raw.get("panel_lines") or [] if isinstance(x, dict) and x.get("who") and x.get("text")]
    return {"sheet_prompt": raw["sheet_prompt"],
            "scenes": [{"prompt": s["prompt"], "narration": str(s.get("narration") or "")} for s in scenes],
            "panel_lines": [{"who": str(x["who"]), "text": str(x["text"])} for x in lines],
            "credit": str(raw.get("credit") or "")}


def clean_category(raw: Any, *, built_in: bool = False) -> dict[str, Any] | None:
    """A whole category, or None: a name, at least one character with a look, a setting and a style. Wan's own one is always
    narrated, filmed by the narrated workflow and written by the writer; a built-in one keeps its script, sheet and workflow."""
    if not isinstance(raw, dict) or not ID_RE.match(str(raw.get("id") or "")):
        return None
    name = _pair(raw.get("name"), LIMITS["name"])
    cast = _cast(raw.get("cast"))
    setting = _line(raw.get("setting"), LIMITS["setting"])
    style = _line(raw.get("style"), LIMITS["style"])
    if not name["bm"] or not cast or len(setting) < 10 or len(style) < 10:
        return None
    voice_in = raw.get("voice") if isinstance(raw.get("voice"), dict) else {}
    mode = voice_in.get("mode") if built_in and voice_in.get("mode") in MODES else "narrator"
    speaker = voice_in.get("name") if voice_in.get("name") in VOICES else (VOICES[0] if mode == "narrator" else "")
    voice = {"mode": mode, "name": speaker, "notes": _line(voice_in.get("notes"), LIMITS["voice_notes"])}
    out: dict[str, Any] = {"id": str(raw["id"]), "name": name, "about": _pair(raw.get("about"), LIMITS["about"]), "cast": cast,
                           "setting": setting, "style": style, "voice": voice,
                           "scene_count": _scene_count(raw.get("scene_count")), "workflow": OWN_WORKFLOW}
    if built_in:
        script = _script(raw.get("script"))
        if script:
            out["script"] = script
            out["scene_count"] = len(script["scenes"])
        for key in ("workflow", "sheet", "file"):
            if isinstance(raw.get(key), str) and raw[key]:
                out[key] = raw[key]
    return out


def library(value: Any = None) -> dict[str, Any]:
    """{categories, default, hidden}: the built-in categories (each `built_in`) then Wan's own (each `own`), every one carrying
    `hidden` when he hid it from the page's list. An own entry that reuses a built-in id is left out."""
    value = value if isinstance(value, dict) else {}
    hidden = {str(x) for x in value.get("hidden") or [] if isinstance(x, str)}
    out = [dict(c, built_in=True) for c in (clean_category(r, built_in=True) for r in RULES["categories"]) if c]
    kept = 0
    for raw in value.get("categories") if isinstance(value.get("categories"), list) else []:
        item = clean_category(raw)
        if not item or kept >= LIMITS["own"]:
            continue
        at = next((i for i, x in enumerate(out) if x["id"] == item["id"]), None)
        if at is not None:
            if out[at].get("own"):
                out[at] = dict(item, own=True)          # his later copy of his own category wins
            continue                                    # a built-in one is never replaced
        kept += 1
        out.append(dict(item, own=True))
    for c in out:
        c["hidden"] = c["id"] in hidden
    default = str(value.get("default") or "")
    return {"categories": out, "hidden": sorted(hidden),
            "default": default if any(c["id"] == default for c in out) else RULES["default"]}


def category_of(lib: dict[str, Any], category_id: Any) -> dict[str, Any] | None:
    return next((c for c in lib["categories"] if c["id"] == category_id), None)


def built_in_ids() -> list[str]:
    return [str(c["id"]) for c in RULES["categories"]]


def cast_words(cat: dict[str, Any]) -> str:
    """The cast as every scene prompt carries it: each name with its look, exactly as the category holds it."""
    return "; ".join(f"{p['name']}: {p['look']}" for p in cat["cast"])


def sheet_prompt(cat: dict[str, Any]) -> str:
    """The character sheet's prompt: the hand-written one, else every character side by side in the category's own place."""
    if cat.get("script"):
        return cat["script"]["sheet_prompt"]
    people = "; ".join(f"{p['name']}, {p['look']}" for p in cat["cast"])
    many = len(cat["cast"]) > 1
    return (f"{cat['style']} Character sheet: {'all the characters side by side' if many else 'one character'}, full body, "
            f"facing the camera, soft even light, in {cat['setting']}: {people}. "
            + ("Each character clearly different. " if many else "")
            + "Highly detailed, natural proportions. No text, no logo, no watermark, no caption.")


def scene_prompt(cat: dict[str, Any], action: str) -> str:
    """One scene's prompt for the video maker: the style, the place, the cast word for word, then what happens. No dialogue."""
    return (f"{cat['style']} Tempat: {cat['setting']}. Watak: {cast_words(cat)}. {action.strip()} "
            "Tiada teks, papan tanda atau logo. Pergerakan semula jadi.")


def film_script(cat: dict[str, Any], *, llm: Any = None, topic: str = "") -> dict[str, Any]:
    """{sheet_prompt, scenes, narration, written, title}: the film this category makes. A hand-written script is used word for
    word (the built-in films look exactly as they did); otherwise the writer writes it now."""
    script = cat.get("script")
    if script:
        return {"sheet_prompt": script["sheet_prompt"], "scenes": [s["prompt"] for s in script["scenes"]],
                "narration": [s["narration"] for s in script["scenes"]], "written": False, "title": ""}
    out = write(llm, cat, topic)
    return {"sheet_prompt": sheet_prompt(cat), "scenes": [scene_prompt(cat, s["action"]) for s in out["scenes"]],
            "narration": [s["narration"] for s in out["scenes"]], "written": True, "title": out["title"]}


SHAPE = """Answer with JSON only:
{{"title": "<a short title in Malaysian Malay>",
  "scenes": [{{"action": "<what the characters do and how it looks, in Malaysian Malay, naming them by name only>",
              "narration": "<one narrator sentence in Malaysian Malay, at most {chars} characters>"}}]}}
Exactly {n} scenes, in film order."""


def system_prompt(cat: dict[str, Any]) -> str:
    from . import antislop
    people = "\n".join(f"- {p['name']}: {p['look']}" for p in cat["cast"])
    return (f"You write a short film of {cat['scene_count']} scenes, about 8 seconds each, for Wan to watch. "
            f"The category: {cat['name']['en']}. {cat['about']['en']}\n"
            f"THE LOOK of every picture: {cat['style']}\n\nTHE CAST (the same in every scene; their looks are "
            f"added to every scene for you, so never describe a look yourself):\n{people}\n\nTHE PLACE: {cat['setting']}\n\n"
            "RULES\n"
            "- Malaysian Malay only (boleh, ubat, syarikat, kualiti), never Indonesian.\n"
            "- `action` is pictures only: what happens and how the camera sees it. No dialogue, no words on screen, no signs, "
            "no logos, no brand names. Only the cast appears by name.\n"
            "- `narration` is one short sentence a narrator says over that scene; the characters never speak.\n"
            "- State no fact, figure, date, ruling, product or name that the topic does not give. A story needs none.\n"
            "- Nothing frightening, nothing unkind to anyone, no religious ruling, no medical or health claim.\n"
            "- No em dash and no en dash.\n"
            + (f"- How the narration sounds: {cat['voice']['notes']}\n" if cat["voice"].get("notes") else "")
            + "\n" + SHAPE.format(chars=LIMITS["narration"], n=cat["scene_count"]) + antislop.prompt_block(film=True))


def problems(out: Any, cat: dict[str, Any], topic: str) -> tuple[list[dict[str, str]], str]:
    """The writer's answer tidied ({title, scenes}), and "" or the reason it is refused."""
    from . import compliance, motion
    say = motion.speaker("bm")
    scenes_in = out.get("scenes") if isinstance(out, dict) and isinstance(out.get("scenes"), list) else []
    scenes = [{"action": say(_line(s.get("action"), LIMITS["action"])), "narration": say(_line(s.get("narration"), 400))}
              for s in scenes_in if isinstance(s, dict)]
    if len(scenes) != cat["scene_count"]:
        return scenes, f"it has {len(scenes)} scenes, not {cat['scene_count']}"
    for i, s in enumerate(scenes, 1):
        if not s["action"] or not s["narration"]:
            return scenes, f"scene {i} has no action or no narration"
        if len(s["narration"]) > LIMITS["narration"]:
            return scenes, f"scene {i}'s narration is longer than {LIMITS['narration']} characters"
    words = " ".join(f"{s['action']} {s['narration']}" for s in scenes)
    indo = compliance.indo_hits(words, [])
    if indo:
        return scenes, "it uses Indonesian, not Malaysian Malay (" + "; ".join(indo[:3]) + ")"
    known = set(_FIGURE.findall(topic or ""))
    extra = [f for f in _FIGURE.findall(words) if f not in known]
    if extra:
        return scenes, f"it gives a figure the topic does not ({', '.join(extra[:4])})"
    if "\u2014" in words or "\u2013" in words:
        return scenes, "it uses a dash"
    return scenes, ""


def write(llm: Any, cat: dict[str, Any], topic: str = "") -> dict[str, Any]:
    """{title, scenes: [{action, narration}]} written for this category, checked. Raises FilmError with the reason when the
    writer is off, does not answer, or twice returns a script that breaks a rule."""
    if not llm or not getattr(llm, "configured", False):
        raise FilmError("this category has no hand-written scenes and the writer is off: "
                        + (llm.why_off() if llm and hasattr(llm, "why_off") else "no writer"))
    topic = _line(topic, LIMITS["topic"]) if topic else ""
    user = (f"TODAY'S TOPIC (Wan's): {topic}" if topic else
            "No topic today: tell one small, warm, everyday story that suits this category and its cast.")
    why = ""
    for _ in range(2):
        ask = user + (f"\n\nYour last script was refused: {why}. Write it again and fix exactly that." if why else "")
        out = llm.chat_json(system_prompt(cat), ask, max_tokens=1800)
        if not isinstance(out, dict):
            raise FilmError("the writer did not answer (see the run log)")
        scenes, why = problems(out, cat, topic)
        if not why:
            from . import antislop
            return {"title": antislop.clean(_line(out.get("title"), 90)), "scenes": scenes}
    raise FilmError(f"the script was refused twice: {why}")
