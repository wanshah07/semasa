"""The seven 2D film styles, picked at random (Wan, 11 Nov 2026: "reset motion format except cover in front, logo, CTA at the
end, idle Semasa's default style, and apply motion skill below randomly").

A film whose `options.design` is one of SKINS is drawn by Remotion in that style (backend/remotion/src/Skins.jsx): its own
ground, letters and movement, none of motion_layout's layout. A film with NO design, or "auto", gets one here: at random among
the styles not used by the last few films, so two films in a row never look alike. The pick is written back onto the row, so
the storyboard preview, the render and a Redo all show the same style.

The four older designs (motion_styles.DESIGNS) stay, by hand only: a film that names one is left exactly as it is and nothing
here ever chooses one. The cover in front, the logo card and the follow line at the end do not belong to a style and are the
same for every film."""

from __future__ import annotations

import random
from typing import Any

from .log import get_logger

log = get_logger("semasa.motion_skins")

TABLE = "semasa_motions"
AUTO = "auto"
SKINS = ("comic", "pixel", "chalk", "glow", "flat", "papercut", "dankoe")
# (Bahasa Malaysia, English, one line on what it looks like)
NAMES = {
    "comic": ("Komik", "Comic art", "cream halftone page, thick ink outlines, red, yellow and blue"),
    "pixel": ("Piksel", "Pixel art", "a 16-colour night sky on a coarse pixel grid"),
    "chalk": ("Papan hitam", "Chalkboard", "hand-written chalk on a green board in a wooden frame"),
    "glow": ("Lakaran bercahaya", "Glow sketch", "warm glowing lines that draw themselves on black"),
    "flat": ("Vektor rata", "Flat vector", "flat navy shapes, a moon and one orange accent"),
    "papercut": ("Potongan kertas", "Paper cut-out", "layered torn kraft paper with soft shadows"),
    "dankoe": ("Garis minimal", "Minimal line", "black, thin white lines, drifting dots, lots of empty space"),
}
LEGACY = {"bright-editorial": "Design 1", "continuous-line": "Design 2", "blur-photo": "Design 3", "blur-full": "Design 4"}
KEEP_APART = 3            # a style is not picked again while it is among the last three used


def _design(row: dict[str, Any]) -> str:
    options = row.get("options")
    return str(options.get("design") or "") if isinstance(options, dict) else ""


def skin(row: dict[str, Any]) -> str:
    """The film's 2D style, or "" when it has none (an older design chosen by hand, or not settled yet)."""
    key = _design(row)
    return key if key in SKINS else ""


def is_auto(row: dict[str, Any]) -> bool:
    """Nothing chosen: no design at all, "auto", or a name nothing knows. An older design chosen by hand is NOT auto."""
    key = _design(row)
    return key not in SKINS and key not in LEGACY


def name(key: str, bm: bool = False) -> str:
    return NAMES[key][0 if bm else 1] if key in NAMES else LEGACY.get(key, key)


def choose(recent: list[str] | None = None, rng: random.Random | None = None) -> str:
    """One style at random, never one of the last KEEP_APART used (`recent` is newest first)."""
    rng = rng or random.Random()
    lately = [s for s in (recent or []) if s in SKINS][:KEEP_APART]
    pool = [s for s in SKINS if s not in lately] or list(SKINS)
    return rng.choice(pool)


def recent(store: Any, limit: int = 12) -> list[str]:
    """The styles of the latest films, newest first. Never raises: no history only costs the spacing, never the film."""
    try:
        rows = store.table(TABLE).select("options,updated_at").order("updated_at", desc=True).limit(limit).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.warning("recent styles not read (%s)", str(exc)[:120])
        return []
    return [s for s in (skin(r) for r in rows) if s]


def resolve(store: Any, row: dict[str, Any], rng: random.Random | None = None) -> str:
    """Settle the film's style before anything is drawn. A style or an older design already on the row is kept; otherwise one
    is picked and written onto the row. Returns the style, or "" for a film on an older design."""
    if not is_auto(row):
        return skin(row)
    picked = choose(recent(store), rng)
    options = {**(row.get("options") if isinstance(row.get("options"), dict) else {}), "design": picked, "design_auto": True}
    row["options"] = options
    try:
        store.table(TABLE).update({"options": options}).eq("id", row["id"]).execute()
    except Exception as exc:  # noqa: BLE001 - the film is still drawn in this style; only the record of it failed
        log.warning("%s: style not recorded (%s)", str(row.get("id"))[:8], str(exc)[:120])
    return picked


# ---- Telegram: the same choice Wan has on the page (Wan, 11 Nov 2026: "make sure I can select the styles in Telegram as well")

def picker(motion_id: str, bm: bool = True) -> tuple[str, list[list[dict[str, str]]]]:
    """The style buttons for one waiting film: random, the seven styles two to a row, then the four older designs."""
    def b(label: str, key: str) -> dict[str, str]:
        return {"text": label, "callback_data": f"msk:{motion_id}:{key}"}
    keys = list(SKINS)
    rows = [[b("🎲 " + ("Rawak (disyorkan)" if bm else "Random (recommended)"), AUTO)]]
    rows += [[b(name(k, bm), k) for k in keys[i:i + 2]] for i in range(0, len(keys), 2)]
    old = list(LEGACY)
    rows += [[b(LEGACY[k], k) for k in old[i:i + 2]] for i in range(0, len(old), 2)]
    text = ("🎨 Pilih gaya filem ini. Rawak memilih satu daripada tujuh gaya 2D; Design 1 hingga 4 ialah reka bentuk lama, "
            "hanya jika anda pilih sendiri." if bm else
            "🎨 Choose this film's style. Random picks one of the seven 2D styles; Design 1 to 4 are the older designs, "
            "used only when you pick one yourself.")
    return text, rows


def pick_and_start(store: Any, motion_id: str, key: str, bm: bool = True) -> str:
    """Wan's tap on a style button: the style is written on the waiting film and the film is started. A film that already
    started keeps the style it started with."""
    if key != AUTO and key not in SKINS and key not in LEGACY:
        return "Gaya itu tidak dikenali." if bm else "That style is not known."
    rows = store.table(TABLE).select("id,status,options").eq("id", motion_id).execute().data or []
    if not rows or rows[0].get("status") != "waiting":
        return ("Motion itu sudah bermula atau tiada lagi dalam barisan." if bm
                else "That film has already started or is no longer in the queue.")
    options = {**(rows[0].get("options") if isinstance(rows[0].get("options"), dict) else {})}
    options.pop("design_auto", None)
    if key == AUTO:
        options.pop("design", None)
    else:
        options["design"] = key
    got = store.table(TABLE).update({"options": options, "status": "pending"}).eq("id", motion_id).eq("status", "waiting") \
        .execute().data
    if not got:
        return ("Motion itu sudah bermula atau tiada lagi dalam barisan." if bm
                else "That film has already started or is no longer in the queue.")
    label = ("rawak" if bm else "random") if key == AUTO else name(key, bm)
    return (f"▶️ Motion dimulakan dengan gaya: {label}. Saya hantar storyboard di sini dahulu untuk anda luluskan." if bm
            else f"▶️ Motion started in the style: {label}. The storyboard comes here first for your approval.")
