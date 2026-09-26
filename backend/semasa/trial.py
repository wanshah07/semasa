"""A one-run trial of the backup writer (Wan, 26 Sep 2026: "can we try mireld for 1 run to scan and do the image").

The page's Settings tab sets `semasa_settings.llm_trial` to {"scrape": true, "media": true}. The next scrape run and
the next worker run that actually asks a writer anything each ask Mireld FIRST (llm.prefer_backup): every summary, the
idea drafts, and the picture read in a recreate job. rootsys still answers whatever Mireld does not, so the run
finishes its work either way. Each part then writes what happened back into the same row and switches itself off:
how many answers came from Mireld and from rootsys, whether Mireld could read a picture, and the models Mireld's own
/models list names (which says whether it has an image model at all).

The row is created by the worker (the page can edit settings but not add a key), so the button works from the
worker's first run after this ships.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.trial")

KEY = "llm_trial"
IMAGE_HINTS = ("image", "flux", "dall", "stable", "sdxl", "imagen", "seedream", "kolors", "midjourney", "gpt-image",
               "hidream", "recraft", "ideogram", "vision", "-vl", "vl-")


def read(store: Any) -> dict[str, Any]:
    try:
        rows = store.table(db.SETTINGS).select("key,value").eq("key", KEY).execute().data or []
        return dict(rows[0].get("value") or {}) if rows else {}
    except Exception as exc:  # noqa: BLE001 - a trial never stops a run
        log.warning("could not read %s: %s", KEY, str(exc)[:160])
        return {}


def ensure_row(store: Any) -> None:
    """Create the switch the page flips (an insert the browser is not allowed to make). Never overwrites it."""
    try:
        if not store.table(db.SETTINGS).select("key").eq("key", KEY).execute().data:
            store.table(db.SETTINGS).insert({"key": KEY, "value": {}}).execute()
    except Exception as exc:  # noqa: BLE001
        log.info("could not create %s: %s", KEY, str(exc)[:160])


def start(store: Any, llm: Any, part: str) -> bool:
    """True, and the writer set to ask Mireld first, when the page asked for a trial of this part."""
    ensure_row(store)
    if read(store).get(part) is not True:
        return False
    if not getattr(llm, "backup_ok", False):
        why = getattr(llm.s, "fallback_blocked", "") or "LLM_FALLBACK_API_KEY / LLM_FALLBACK_MODEL are not set on this workflow"
        _write(store, part, {"ok": False, "why": f"the trial could not start: {why}"})
        print(f"::warning::Mireld trial requested but the backup is off: {why}")
        return False
    llm.prefer_backup = True
    log.warning("TRIAL: Mireld (%s) is asked first in this %s run; rootsys answers only what it cannot",
                llm.s.fallback_model, part)
    return True


def finish(store: Any, llm: Any, part: str) -> str:
    """Record the trial and switch it off, but only when a writer was actually asked: a run with no work proves
    nothing, so the trial waits for the next one."""
    answers = dict(getattr(llm, "answers", {}))
    misses = dict(getattr(llm, "misses", {}))
    vision = dict(getattr(llm, "vision", {}))
    asked = sum(answers.values()) + sum(misses.values()) + vision.get("backup_missed", 0)
    if not asked:
        log.info("TRIAL: nothing was asked of a writer in this %s run; the trial waits for the next one", part)
        return f"Mireld trial ({part}): waiting, this run asked the writer nothing"
    models = llm.backup_models()
    image_models = [m for m in models if any(h in m.lower() for h in IMAGE_HINTS)]
    result = {"ok": answers.get("backup", 0) > 0, "model": llm.s.fallback_model, "base": llm.s.fallback_base_url,
              "mireld_answers": answers.get("backup", 0), "mireld_misses": misses.get("backup", 0),
              "rootsys_answers": answers.get("primary", 0), "rootsys_misses": misses.get("primary", 0),
              "picture_read_by_mireld": vision.get("backup", 0), "picture_not_read_by_mireld": vision.get("backup_missed", 0),
              "picture_read_by_rootsys": vision.get("primary", 0), "models": models, "image_models": image_models,
              "stopped": getattr(llm, "trial_stopped", "") or None}
    _write(store, part, result)
    line = (f"Mireld trial ({part}): Mireld answered {result['mireld_answers']}, missed {result['mireld_misses']}; "
            f"rootsys answered {result['rootsys_answers']}. Pictures read by Mireld {result['picture_read_by_mireld']}, "
            f"not read {result['picture_not_read_by_mireld']}. Models listed: {len(models)}"
            + (f", image-looking: {', '.join(image_models[:8])}" if image_models else ", none look like image models")
            + (f". Stopped early: {result['stopped']}" if result["stopped"] else ""))
    log.warning(line)
    print(f"::notice::{line}")
    try:
        db.log_event(store, "info", "system", "llm.trial",
                     f"Percubaan Mireld ({part}): Mireld jawab {result['mireld_answers']}, "
                     f"rootsys jawab {result['rootsys_answers']}", detail=result)
    except Exception as exc:  # noqa: BLE001
        log.info("could not log the trial: %s", str(exc)[:120])
    return line


def _write(store: Any, part: str, result: dict[str, Any]) -> None:
    run = os.environ.get("GITHUB_RUN_ID")
    repo = os.environ.get("GITHUB_REPOSITORY")
    value = read(store)
    value[part] = False
    value[f"{part}_result"] = {**result, "at": datetime.now(UTC).isoformat(),
                               "run": f"https://github.com/{repo}/actions/runs/{run}" if run and repo else None}
    try:
        store.table(db.SETTINGS).update({"value": value}).eq("key", KEY).execute()
    except Exception as exc:  # noqa: BLE001
        log.warning("could not record the trial: %s", str(exc)[:160])
