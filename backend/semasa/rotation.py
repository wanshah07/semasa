"""Hooks and poster looks take their TURN and never repeat (Wan, 20 Nov 2026: "make sure hook sentiasa berubah, tak berulang
dan ikut turutan" and "follow turn not repeat").

Before this the writer was told to pick whichever of the 25 hook shapes fitted the story best, so it picked the same one:
shape 16 ("Semua orang cakap ___, tapi realitinya ___") opened nearly every recent post, and every poster was drawn in the one
default look. Now the next shape and the next look are chosen HERE, from what the stream used last, and the writer is told which.

  * Hooks: the shapes are taken in a fixed turn that goes round the families (1, 6, 16, 21, 2, 7, ...), so two posts in a row
    are never the same shape or even the same family. The writer is given THIS post's shape, two fall-backs for when it cannot
    be filled without inventing a fact, and the hooks of the last posts so it does not echo their opening words.
  * Looks: the Semasa poster looks (hand-drawn, marker, torn paper, colour blocks, neon, cardboard, chalkboard, line map, torn
    strips, grid, Semasa's own) in a fixed turn, skipping the ones Wan has hidden and the last few used.

Wan's own choice always wins: an idea that names a look keeps it, and a hook style he made from screenshots is rotated the same
way. Nothing here raises: a store that cannot answer means the turn simply starts again, which only costs the rotation, never
the post.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import db, hook_bank
from .log import get_logger

log = get_logger("semasa.rotation")

# The Semasa poster looks in the order they come round (Wan's attached picker). "photo" needs a background picture, "image" and
# "threads" put the post's own picture on the slide, and "era" is not offered any more: none of those can be relied on for a
# post that is made with no picture, so they are chosen by hand and are not part of the turn.
LOOK_TURN = ("hand", "marker", "torn", "block", "neon", "deck", "chalk", "metro", "strip", "grid", "classic")
LOOK_WINDOW = 4          # a look is not used again until this many others have been
SHAPE_WINDOW = 8         # nor a hook shape until this many others have been (fewer when the bank is small)
RECENT_HOOKS = 8


def _briefs(store: Any, stream: str, limit: int = 40) -> list[dict[str, Any]]:
    """The briefs of the stream's latest written ideas, newest first."""
    try:
        rows = (store.table(db.IDEAS).select("brief,updated_at").eq("stream", stream).order("updated_at", desc=True)
                .limit(limit).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("rotation: ideas not read (%s): the turn starts again", str(exc)[:120])
        return []
    return [r["brief"] for r in rows if isinstance(r.get("brief"), dict)]


def recent_hooks(store: Any, stream: str, n: int = RECENT_HOOKS) -> list[str]:
    """The first lines of the stream's latest posts (rejected ones included: they were still read), newest first."""
    try:
        rows = (store.table(db.POSTS).select("hook,created_at").eq("stream", stream).order("created_at", desc=True)
                .limit(n).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("rotation: posts not read (%s)", str(exc)[:120])
        return []
    return [" ".join(str(r.get("hook") or "").split())[:110] for r in rows if str(r.get("hook") or "").strip()]


# --- hooks ---------------------------------------------------------------------------------------------------------------------


def shape_order(stream: str, bank: hook_bank.Bank | None = None, family: str | None = None) -> list[int]:
    """The shapes the stream may use, in the order they come round: one from each family in turn, so the family changes every
    post. Shapes keep their series order inside a family."""
    by_family: dict[str, list[int]] = {}
    for number, fam, _shape in hook_bank.allowed(stream, family, bank):
        by_family.setdefault(fam, []).append(number)
    lanes = list(by_family.values())
    out: list[int] = []
    for i in range(max((len(x) for x in lanes), default=0)):
        out.extend(lane[i] for lane in lanes if i < len(lane))
    return out


def _used_shapes(briefs: list[dict[str, Any]], bank: hook_bank.Bank | None) -> list[int]:
    """The shape numbers of the ideas written with this same bank, newest first (a number means another shape in another bank)."""
    style = bank.id if bank else ""
    out: list[int] = []
    for b in briefs:
        if str(b.get("hook_style") or "") != style:
            continue
        try:
            out.append(int(b.get("hook_shape")))
        except (TypeError, ValueError):
            continue
    return out


@dataclass
class Turn:
    """This post's hook: the shape it is built on, the fall-backs, and the hooks it must not echo."""
    assigned: int | None = None
    fallbacks: list[int] = field(default_factory=list)
    recent: list[str] = field(default_factory=list)

    @property
    def permitted(self) -> list[int]:
        return ([self.assigned] if self.assigned else []) + self.fallbacks

    def hint(self) -> str:
        if not self.assigned:
            return ""
        spare = f" Only if shape {self.assigned} cannot be filled without inventing a fact, use shape {self.fallbacks[0]}" + (
            f", then {self.fallbacks[1]}." if len(self.fallbacks) > 1 else ".") if self.fallbacks else ""
        echo = ("\nThe latest hooks already posted (never echo their opening words, their sentence shape or their idea):\n"
                + "\n".join(f"- {h}" for h in self.recent)) if self.recent else ""
        return (f"THIS POST'S HOOK SHAPE IS NUMBER {self.assigned} (Wan, 20 Nov 2026: the hooks take their turn, always change "
                f"and never repeat). Build the hook on shape {self.assigned}, not on the shape you like best.{spare}{echo}")

    def ask_again(self) -> str:
        spare = f" (or {', '.join(str(n) for n in self.fallbacks)} only if it cannot be filled without inventing a fact)" \
            if self.fallbacks else ""
        return (f"\n\nYOUR LAST ANSWER USED A HOOK SHAPE THAT IS NOT THIS POST'S TURN. The hook must be built on shape "
                f"{self.assigned}{spare}. Answer again in the same JSON with \"hook_shape\" set to that number and the hook, the "
                "caption's first line and the cover headline built on it, with every blank filled and no underscores left.")


def turn_for(store: Any, stream: str, bank: hook_bank.Bank | None = None, family: str | None = None) -> Turn:
    """The shape this stream's NEXT post is built on: the one after the last used in the turn, skipping the latest few."""
    order = shape_order(stream, bank, family)
    if not order:
        return Turn()
    used = _used_shapes(_briefs(store, stream), bank)
    start = (order.index(used[0]) + 1) % len(order) if used and used[0] in order else 0
    window = set(used[:max(1, min(SHAPE_WINDOW, len(order) // 2))])
    picks: list[int] = []
    for k in range(len(order)):
        n = order[(start + k) % len(order)]
        if n not in window:
            picks.append(n)
        if len(picks) == 3:
            break
    picks = picks or [order[start]]
    return Turn(assigned=picks[0], fallbacks=picks[1:], recent=recent_hooks(store, stream))


# --- looks ---------------------------------------------------------------------------------------------------------------------


def next_look(store: Any, stream: str, hidden: list[str] | None = None) -> str:
    """The poster look this stream's next post is drawn in: the one after the last used in the turn, skipping the ones Wan hid
    and the latest few, so it follows the turn and never repeats."""
    gone = {str(h) for h in (hidden or [])}
    order = [k for k in LOOK_TURN if k not in gone] or list(LOOK_TURN)
    used = [str(b.get("look") or "") for b in _briefs(store, stream) if b.get("look")]
    start = (order.index(used[0]) + 1) % len(order) if used and used[0] in order else 0
    window = set(used[:max(1, min(LOOK_WINDOW, len(order) - 1))])
    for k in range(len(order)):
        look = order[(start + k) % len(order)]
        if look not in window:
            return look
    return order[start]
