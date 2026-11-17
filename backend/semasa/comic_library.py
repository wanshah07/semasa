"""The comic library: the cartoon styles and the cartoon series (Wan, 16 to 17 Nov 2026: "remember the comic style so other
model can use and render same based on topics / for comic style create multiples cartoon or comic style, and make it series
like cartoon series").

One file holds the built-in ones, rules/comic.json, read by the page too (web/src/lib/comic.js). Wan's own styles and series
are the settings row `comic` ({styles: [...], series: [...]}), merged over the built-in ones by id: the same id replaces a
built-in one (his edit of it), a new id is added. An entry of his that is not a whole style or series is left out, never
half-used, so a broken row can cost him his edit but never a comic.

  style   {id, name: {bm, en}, about: {bm, en}, prompt, lettering}
          `prompt` is the look, written so that any picture maker draws it the same way; it goes into every prompt verbatim.
          `lettering` is how the bubbles and letters look; it goes in only when the picture maker writes the words.
  series  {id, name, about: {bm, en}, setting, cast: {A: {name, look, role, voice}, B: {...}}}
          `look` is the character's exact appearance, repeated word for word in every episode. `role` and `voice` are for
          the script writer. A cast is two people inside a comic, not a brand mascot.

Nothing here draws, writes or reads the database: `library(value)` takes the settings value the caller already holds.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[2] / "rules" / "comic.json"
RULES: dict[str, Any] = json.loads(RULES_PATH.read_text(encoding="utf-8"))
LIMITS: dict[str, int] = RULES["limits"]
SPEAKERS = ("A", "B")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
_CONTROL = re.compile(r"[\u0000-\u001f\u007f\u2028\u2029]+")


def _line(value: Any, limit: int) -> str:
    """One line of plain text: control characters and line breaks become a space, runs of spaces one. "" when it is not text
    or is longer than `limit` (an over-long entry is refused whole, never cut: a cut style is a different style)."""
    if not isinstance(value, str):
        return ""
    text = " ".join(_CONTROL.sub(" ", value).split())
    return text if len(text) <= limit else ""


def _pair(value: Any, limit: int, fallback: str = "") -> dict[str, str]:
    """{bm, en} from a pair or from one string (a name Wan typed once serves both languages)."""
    if isinstance(value, dict):
        bm, en = _line(value.get("bm"), limit), _line(value.get("en"), limit)
    else:
        bm = en = _line(value, limit)
    return {"bm": bm or en or fallback, "en": en or bm or fallback}


def clean_style(raw: Any) -> dict[str, Any] | None:
    """A whole style, or None. The description must be long enough to be a description (a two-word style is a wish)."""
    if not isinstance(raw, dict) or not ID_RE.match(str(raw.get("id") or "")):
        return None
    prompt = _line(raw.get("prompt"), LIMITS["style_prompt"])
    name = _pair(raw.get("name"), LIMITS["name"])
    if len(prompt) < 40 or not name["bm"]:
        return None
    return {"id": str(raw["id"]), "name": name, "about": _pair(raw.get("about"), LIMITS["about"]), "prompt": prompt,
            "lettering": _line(raw.get("lettering"), LIMITS["lettering"])}


def clean_series(raw: Any) -> dict[str, Any] | None:
    """A whole series, or None: a name, a usual setting and both people, each with a name and an appearance."""
    if not isinstance(raw, dict) or not ID_RE.match(str(raw.get("id") or "")):
        return None
    name = _line(raw.get("name"), LIMITS["name"])
    cast_in = raw.get("cast") if isinstance(raw.get("cast"), dict) else {}
    cast: dict[str, dict[str, str]] = {}
    for who in SPEAKERS:
        c = cast_in.get(who) if isinstance(cast_in.get(who), dict) else {}
        person = {"name": _line(c.get("name"), LIMITS["name"]), "look": _line(c.get("look"), LIMITS["look"]),
                  "role": _line(c.get("role"), LIMITS["role"]), "voice": _line(c.get("voice"), LIMITS["voice"])}
        if not person["name"] or len(person["look"]) < 20:
            return None
        cast[who] = person
    if not name:
        return None
    return {"id": str(raw["id"]), "name": name, "about": _pair(raw.get("about"), LIMITS["about"]),
            "setting": _line(raw.get("setting"), LIMITS["setting"]), "cast": cast}


def _merge(built_in: list[dict[str, Any]], own: Any, clean: Any, most: int) -> list[dict[str, Any]]:
    out = [x for x in (clean(r) for r in built_in) if x]
    kept = 0
    for raw in own if isinstance(own, list) else []:
        item = clean(raw)
        if not item:
            continue
        at = next((i for i, x in enumerate(out) if x["id"] == item["id"]), None)
        if at is not None:
            out[at] = {**item, **({"own": True} if out[at].get("own") else {"edited": True})}
            continue
        if kept >= most:
            continue
        kept += 1
        out.append({**item, "own": True})
    return out


def library(value: Any = None) -> dict[str, Any]:
    """{styles, series, default_style, default_series}: the built-in ones with Wan's (the settings row `comic`) merged over
    them. A built-in entry he edited carries `edited`; one of his own carries `own`. The defaults are his choice when it
    names something that exists, else the file's."""
    value = value if isinstance(value, dict) else {}
    styles = _merge(RULES["styles"], value.get("styles"), clean_style, LIMITS["own_styles"])
    series = _merge(RULES["series"], value.get("series"), clean_series, LIMITS["own_series"])

    def pick(want: Any, items: list[dict[str, Any]], fallback: str) -> str:
        return str(want) if any(x["id"] == want for x in items) else fallback
    return {"styles": styles, "series": series,
            "default_style": pick(value.get("default_style"), styles, RULES["default_style"]),
            "default_series": pick(value.get("default_series"), series, RULES["default_series"])}


def style_of(lib: dict[str, Any], style_id: Any, snapshot: Any = None) -> dict[str, Any] | None:
    """The style a job names: the library's (so an edit reaches the next episode), else the copy the job carried when it was
    queued (a style deleted since), else None."""
    return next((s for s in lib["styles"] if s["id"] == style_id), None) or clean_style(snapshot)


def series_of(lib: dict[str, Any], series_id: Any, snapshot: Any = None) -> dict[str, Any] | None:
    return next((s for s in lib["series"] if s["id"] == series_id), None) or clean_series(snapshot)


def cast_of(series: dict[str, Any]) -> dict[str, str]:
    """The script's cast: each person's appearance exactly as the series holds it. Every episode gets these same words."""
    return {who: series["cast"][who]["look"] for who in SPEAKERS}


def names_of(series: dict[str, Any]) -> dict[str, str]:
    return {who: series["cast"][who]["name"] for who in SPEAKERS}


def episode_line(series_name: str, number: int | None, lang: str = "bm") -> str:
    """What the poster says above the title: "Siri Kak Lin Tanya · Episod 4" (English: "Kak Lin Tanya · Episode 4")."""
    name = " ".join(str(series_name or "").split())
    if not name:
        return ""
    if lang == "en":
        return f"{name} · Episode {number}" if number else name
    return f"Siri {name} · Episod {number}" if number else f"Siri {name}"
