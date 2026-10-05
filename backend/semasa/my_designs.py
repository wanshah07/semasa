"""My designs (Wan, 4 Oct 2026: "create a default design to use for carousel, poster and single card, like ERA, Photo, Grid and
Semasa. I need not fill any text: the design has the layout, and the text fills it when the idea comes in from the draft.").

A design is a saved look with no words: a Studio family, a template for each place a slide can have in a set (cover, middle,
closing, single card or poster), two colours, a background, a scrim, a character and a small label. It is made on the Designs
tab and kept in `semasa_settings.designs` (a list); `semasa_settings.default_design` ({"id": ...}) is the one new drafts use
when the idea did not pick a look of its own. A design is carried on a render job as a SNAPSHOT (`meta.design_pack`), so
editing or deleting a design later never changes a card that was already drawn, and a redraw gives the same card.
The drawing is the Studio renderer (web/src/lib/cards/studio.js normDesign), which drops anything it does not understand.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.my_designs")

ID_RE = re.compile(r"^d:([a-z0-9_]{4,24})$")
FAMILIES = ("grid", "era", "photo")
KEYS = ("look", "cover", "middle", "closing", "single", "accent", "paper", "bg", "scrim", "mascot", "eyebrow")


def token(look: str) -> str | None:
    """The design id inside a look value like "d:ab12cd", or None for a plain look."""
    m = ID_RE.match(str(look or ""))
    return m.group(1) if m else None


MAX_LAYOUT_BYTES = 80_000      # a design made from a reference carries its layouts; nothing bigger is kept
MAX_BG_PROMPT = 700
PLACES = ("cover", "middle", "closing", "single", "main")


def pack(design: dict[str, Any] | None) -> dict[str, Any] | None:
    """The snapshot a job carries: only the known keys, strings only, and only if the family is a Studio one. A design made
    from a reference also carries its `layouts` ({place: layout}), read by the renderer (studio.js normLayout), which keeps
    only what it understands; here they are only bounded in size and place."""
    if not isinstance(design, dict) or design.get("look") not in FAMILIES:
        return None
    out: dict[str, Any] = {k: str(design[k])[:120] for k in KEYS if isinstance(design.get(k), str) and design[k].strip()}
    prompt = " ".join(str(design.get("bg_prompt") or "").split())[:MAX_BG_PROMPT]
    if prompt:
        out["bg_prompt"] = prompt               # what the design's background looks like: the image provider paints a new one
    layouts = design.get("layouts")
    if isinstance(layouts, dict):
        keep = {k: v for k, v in layouts.items() if k in PLACES and isinstance(v, dict) and isinstance(v.get("elements"), list)}
        if keep and len(json.dumps(keep, separators=(",", ":"))) <= MAX_LAYOUT_BYTES:
            out["layouts"] = keep
    return out


def load(store: Any) -> tuple[list[dict[str, Any]], str]:
    """(designs, default id). A missing setting row (supabase/027 not run) or a failed read is an empty list: the feature is
    then simply off, and nothing that worked before changes."""
    try:
        rows = store.table(db.SETTINGS).select("key,value").in_("key", ["designs", "default_design"]).execute().data or []
    except Exception as exc:  # noqa: BLE001 - never stops a draft being written
        log.info("designs could not be read: %s", str(exc)[:120])
        return [], ""
    by = {r["key"]: r.get("value") for r in rows}
    lst = by.get("designs")
    dflt = by.get("default_design")
    return ([d for d in lst if isinstance(d, dict)] if isinstance(lst, list) else []), \
        str(dflt.get("id") or "") if isinstance(dflt, dict) else ""


def choose(designs: list[dict[str, Any]], default_id: str, look: str) -> tuple[str, dict[str, Any] | None]:
    """(look, design pack) for the look an idea or post asked for. "d:<id>" names a design; a plain look stays as it is,
    except that an idea that said nothing ("") takes the default design when one is set; "classic" is a choice and stands."""
    want = token(look) or (default_id if not look else "")
    if want:
        d = next((x for x in designs if str(x.get("id")) == want), None)
        got = pack(d)
        if got:
            return got["look"], got
    return (look if look in ("classic", *FAMILIES) else "classic"), None


def for_idea(store: Any, idea: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    """The look an idea was written with. An idea whose brief names a look (even "classic") keeps it; one that says nothing
    (older ideas, ideas made elsewhere) takes the default design when one is set."""
    from .ideas import look_of
    designs, default_id = load(store)
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    return choose(designs, default_id, look_of(idea) if brief.get("look") else "")
