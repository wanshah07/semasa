"""Is each Gemini key live? (Wan, 7 Nov 2026: "don't know if the api is live or not")

A key Wan adds stays "Not tried yet" until Motion or the AI team happens to use it. This asks every switched-on key now, from a
GitHub run (the page can never read a key, and a browser cannot hold one): it lists the models the key can see, asks the text
model a five-token question, and writes the result on the key's row (status, last error, and a one-line note that says what was
found, including whether the picture model is in the key's own list). The page wakes it (supabase/062: a new key, a key switched
on, or the "Check now" button).

It only reads and asks: nothing is posted, nothing is drawn (a picture is not requested, because that spends the free quota), and
the key goes only to generativelanguage.googleapis.com.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import Any

from . import ai_team, db, gemini_keys
from .log import get_logger

log = get_logger("semasa.gemini_check")


def _note(store: Any, row: dict[str, Any], text: str, now: datetime) -> None:
    try:
        patch = {"checked_at": now.isoformat(), "check_note": text[:300]}
        store.table(gemini_keys.TABLE).update(patch).eq("id", row["id"]).execute()
    except Exception as exc:  # noqa: BLE001 - a note lost is not a reason to stop the check
        log.info("gemini check note not saved: %s", str(exc)[:100])


def check_key(store: Any, row: dict[str, Any], settings: dict[str, Any], live: Any, now: datetime) -> str:
    """Asks one key and records the answer. Returns "ok", "bad", "limited" or "retry"."""
    c = {"slug": "gemini", "provider": "openai", "base_url": gemini_keys.BASE, "key": row["api_key"]}
    try:
        listed = live.models(c)
    except Exception as exc:  # noqa: BLE001
        listed = []
        log.info("gemini models not listed: %s", str(exc)[:100])
    model = settings["model"]
    ok, ms, err = live.chat(c, model)
    said = ""
    if not ok and listed and str(err).startswith("404"):          # the model name is wrong, the key may be fine
        for alt in ai_team.text_models(listed):
            if "flash" in alt and alt != model:
                ok2, ms2, err2 = live.chat(c, alt)
                if ok2:
                    ok, ms, err, said = True, ms2, "", f"the model {model} was not found, {alt} answered: set it on the card. "
                    model = alt
                break
    kind = gemini_keys.note(store, row, ok, err, now)
    if ok:
        image = settings["image_model"]
        pic = (f"picture model {image} is in this key's list" if image in listed else
               f"picture model {image} is NOT in this key's list: pictures will look for another" if listed else
               "the model list could not be read")
        _note(store, row, f"{said}answered in {ms} ms ({model}); {pic}", now)
    else:
        why = {"bad": "Google refused this key: check that it is a Google AI Studio key and that it is not restricted",
               "limited": "the key's quota or rate limit is used up: it rests, then is tried again"}
        _note(store, row, why.get(kind, "Google did not answer: it is tried again"), now)
    return kind


def run(store: Any, live: Any = None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    live = live or ai_team.LIVE
    rows = [r for r in gemini_keys.keys(store) if r.get("enabled", True)]
    if not rows:
        return "no Gemini key is switched on"
    settings = gemini_keys.load_settings(store)
    kinds = [check_key(store, r, settings, live, now) for r in rows]
    return f"{kinds.count('ok')} of {len(kinds)} Gemini keys answered" + (
        f"; {kinds.count('bad')} refused, {kinds.count('limited')} limited" if kinds.count("ok") < len(kinds) else "")


def main() -> int:
    print(f"Gemini check: {run(db.client())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
