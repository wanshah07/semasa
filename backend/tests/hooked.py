"""A film script the way the writer must now give it: with a hook shape (Wan, 7 Nov 2026). Tests that are not about the hook
wrap their canned plans in hooked(), which adds a valid shape and a hook equal to scene 1's heading when the plan has none."""

from __future__ import annotations

from typing import Any


def hooked(plan: Any) -> Any:
    if not isinstance(plan, dict) or not plan.get("scenes") or "hook_shape" in plan:
        return plan
    first = next((s for s in plan["scenes"] if isinstance(s, dict) and s.get("heading")), None)
    if first is None:
        return plan
    # shape 18 ("___ dah mati. Ni apa yang sebenarnya berkesan sekarang") opens with a blank, so its stem is empty and the
    # strict opening-words check is skipped — the only built-in shape a freeform test heading can claim without lying.
    return {**plan, "hook_shape": 18, "hook": first["heading"]}
