"""ws.regulab Studio's card catalogue for the worker: the poses and Wan's own photographs (rules/cards.json, the one copy
the page also reads; files in web/public/cards/). The Studio renderer loads them from the routed origin, and a
photograph used as a ground is read here as bytes, exactly like any other background."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CARDS = ROOT / "rules" / "cards.json"
ASSETS = ROOT / "web" / "public" / "cards"


@lru_cache(maxsize=1)
def catalogue() -> dict[str, Any]:
    return json.loads(CARDS.read_text(encoding="utf-8"))


def ground_bytes(token: str) -> bytes | None:
    """"lib:g_makmal02" → that photograph's bytes; anything else, or a missing file → None."""
    if not str(token or "").startswith("lib:"):
        return None
    k = token[4:]
    g = next((x for x in catalogue()["grounds"] if x["k"] == k), None)
    if not g:
        return None
    path = (ASSETS / g["file"]).resolve()
    if ASSETS.resolve() not in path.parents or not path.is_file():
        return None
    return path.read_bytes()


def default_ground(stream: str, domain: str | None, angle: str | None) -> str | None:
    """Studio's default ground: by domain for ws.regulab, by angle for LinkedIn. A bg token, or None."""
    c = catalogue()
    if stream == "linkedin":
        k = c["ground_by_angle"].get(str(angle or "").strip().upper()) or c["ground_default_linkedin"]
    else:
        k = c["ground_by_domain"].get(str(domain or ""))
    return f"lib:{k}" if k and ground_bytes(f"lib:{k}") else None


def mascots(store: Any = None) -> list[dict[str, str]]:
    """The poses on offer to the Studio renderer, as addresses on its routed origin. With a store, the Wanshah pictures Wan
    approved (settings row `wanshah`, supabase/040) stand in for their poses, as https addresses the browser fetches itself."""
    out = [{"k": m["k"], "url": "/cards/" + m["file"]} for m in catalogue()["mascots"] if (ASSETS / m["file"]).is_file()]
    if store is None:
        return out
    try:
        rows = store.table("semasa_settings").select("value").eq("key", "wanshah").execute().data or []
    except Exception:  # noqa: BLE001 - a missing row or table is the original poses, never a failed render
        return out
    poses = ((rows[0].get("value") if rows else None) or {}).get("poses") or {}
    for m in out:
        url = (poses.get(m["k"]) or {}).get("url") if isinstance(poses.get(m["k"]), dict) else None
        if isinstance(url, str) and url.startswith("https://"):
            m["url"] = url
    return out
