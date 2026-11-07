"""Is each Gemini key live, and which model should it call? (Wan, 7 Nov 2026: "don't know if the api is live or not", then, with
the first real check on screen, "models/gemini-2.5-flash is no longer available to new users": "it's auto update model and I can
choose the model")

A key Wan adds stays "Not tried yet" until Motion or the AI team happens to use it. This asks every switched-on key now, from a
GitHub run (the page can never read a key, and a browser cannot hold one): it reads the models the key can see, asks a text model
a five-token question, and writes the result on the key's row (status, last error, and a one-line note).

THE MODEL FOLLOWS THE KEYS. settings.gemini.model / image_model are "auto" unless Wan picks a name on the card. With "auto", or
when his choice is no longer listed or no longer answers, the run ranks the keys' own text models (Google's refusal may even name
the replacement) and keeps the first that really answers as `text_pick`; the best picture-capable model is `image_pick`. Both,
with the lists, are written to settings.gemini_models for the card's menus and for every worker (gemini_keys.load_settings
resolves them), so a retired model heals by itself on the next check, and a worker that meets "model gone" asks for that check
once (refresh_models). A model that is gone is never the key's fault: the key is not rested or refused.

It only reads and asks: nothing is posted, nothing is drawn (a picture is not requested, because that spends the free quota), and
the key goes only to generativelanguage.googleapis.com.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from typing import Any

from . import ai_team, db, gemini_keys
from .log import get_logger

log = get_logger("semasa.gemini_check")

ASK_LIMIT = 4                      # models asked per key when the wanted one is gone
NOT_TEXT = re.compile(r"image|tts|embed|live|audio|robotics|computer|native|thinking|aqa|vision|learnlm|imagen|veo", re.I)
PREVIEW = re.compile(r"preview|exp|beta", re.I)
VERSION = re.compile(r"^gemini-(\d+(?:\.\d+)?)-(flash|pro)(-lite)?(?:-(.+))?$")


def text_rank(name: str) -> tuple | None:
    """A sort key (best first) for a text model, or None when it is not one to write with. Stable models before previews, the
    newest version first, Flash before Pro (quicker and kinder to a free key), the lite size last of its version, the `-latest`
    alias handled by the caller (it is tried before these)."""
    n = name.removeprefix("models/")
    if not n.startswith("gemini") or NOT_TEXT.search(n):
        return None
    m = VERSION.match(n)
    if not m:
        return (1, 0.0, 0, 0, n) if n.endswith("-latest") else None
    return (1 if PREVIEW.search(n) else 0, -float(m.group(1)), 0 if m.group(2) == "flash" else 1, 1 if m.group(3) else 0, n)


def text_candidates(listed: list[str], wanted_gone: str = "", suggestion: str = "") -> list[str]:
    """The order to try: Google's own suggestion, the always-current alias, then the ranked list."""
    ranked = [n for _, n in sorted((text_rank(n), n) for n in listed if text_rank(n) is not None)]
    out: list[str] = []
    for n in [suggestion, "gemini-flash-latest" if "gemini-flash-latest" in listed or not listed else "", *ranked]:
        if n and n != wanted_gone and n not in out and (not listed or n in listed or n == suggestion):
            out.append(n)
    return out


def image_rank(name: str) -> tuple | None:
    """A sort key for a model that can draw (generateContent with 'image' in its name; the Imagen family uses another call)."""
    n = name.removeprefix("models/")
    if "image" not in n or "imagen" in n or not n.startswith("gemini"):
        return None
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
    return (1 if PREVIEW.search(n) else 0, -(float(m.group(1)) if m else 0.0), n)


def read_lists(keys: list[dict[str, Any]], live: Any) -> tuple[list[str], list[str], str]:
    """(text models, picture models, the label of the key that listed them), the union over every key that could list."""
    text: set[str] = set()
    image: set[str] = set()
    source = ""
    for row in keys:
        c = {"slug": "gemini", "provider": "openai", "base_url": gemini_keys.NATIVE, "key": row["api_key"]}
        native = []
        try:
            native = live.native_models(c) if hasattr(live, "native_models") else []
        except Exception as exc:  # noqa: BLE001
            log.info("gemini native models not read: %s", str(exc)[:100])
        if native:
            can = [m["name"] for m in native if "generateContent" in (m.get("methods") or [])]
        else:
            try:
                can = live.models({**c, "base_url": gemini_keys.BASE})
            except Exception as exc:  # noqa: BLE001
                can = []
                log.info("gemini models not listed: %s", str(exc)[:100])
        if can and not source:
            source = str(row.get("label") or row.get("hint") or "a key")
        text |= {n for n in can if text_rank(n) is not None}
        image |= {n for n in can if image_rank(n) is not None}
    return sorted(text), sorted(image, key=lambda n: image_rank(n) or ()), source


def _note(store: Any, row: dict[str, Any], text: str, now: datetime) -> None:
    try:
        patch = {"checked_at": now.isoformat(), "check_note": text[:300]}
        store.table(gemini_keys.TABLE).update(patch).eq("id", row["id"]).execute()
    except Exception as exc:  # noqa: BLE001 - a note lost is not a reason to stop the check
        log.info("gemini check note not saved: %s", str(exc)[:100])


def _write_models(store: Any, text: list[str], image: list[str], text_pick: str, source: str, now: datetime,
                  unavailable: list[str] | None = None) -> None:
    value = {"text": text, "image": image, "text_pick": text_pick, "image_pick": image[0] if image else "",
             "unavailable": sorted(set(unavailable or [])), "at": now.isoformat(), "from": source}
    try:
        store.table(db.SETTINGS).upsert({"key": gemini_keys.MODELS_KEY, "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001
        log.info("gemini models not saved: %s", str(exc)[:100])


def find_working(row: dict[str, Any], live: Any, first: str, listed: list[str],
                 gone: list[str] | None = None) -> tuple[str, int | None, str]:
    """Asks `first`; when it is gone, the next candidates in turn. (the model that answered, ms, the last error); the model is ""
    when none answered, and the error says why. Every model found gone is appended to `gone`."""
    gone = gone if gone is not None else []
    c = {"slug": "gemini", "provider": "openai", "base_url": gemini_keys.BASE, "key": row["api_key"]}
    ok, ms, err = live.chat(c, first)
    if ok:
        return first, ms, ""
    if gemini_keys.classify(err) != "model":
        return "", ms, str(err)
    gone.append(first)
    tried = {first}
    for alt in text_candidates(listed, wanted_gone=first, suggestion=gemini_keys.suggested_model(err))[:ASK_LIMIT]:
        if alt in tried:
            continue
        tried.add(alt)
        ok, ms, err2 = live.chat(c, alt)
        if ok:
            return alt, ms, ""
        if gemini_keys.classify(err2) != "model":
            return "", ms, str(err2)
        gone.append(alt)
        err = err2
    return "", None, str(err)


def run(store: Any, live: Any = None, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    live = live or ai_team.LIVE
    rows = [r for r in gemini_keys.keys(store) if r.get("enabled", True)]
    if not rows:
        return "no Gemini key is switched on"
    settings = gemini_keys.load_settings(store)
    text, image, source = read_lists(rows, live)
    wanted = settings["model"]       # already resolved: Wan's choice while listed, else the last pick, else the alias
    picture = settings["image_model_setting"]
    chosen = ""
    gone: list[str] = []
    kinds: list[str] = []
    for row in rows:
        model, ms, err = find_working(row, live, chosen or wanted, text, gone)
        if model and not chosen:
            chosen = model
        kind = gemini_keys.note(store, row, bool(model), err, now)
        kinds.append(kind)
        if model:
            moved = f"the model {wanted} did not answer, so {model} is used automatically. " if model != wanted else ""
            image_now = gemini_keys.resolve(picture, image, image[0] if image else "", gemini_keys.FALLBACK_IMAGE)
            pic = (f"picture model {image_now} is in this key's list" if image_now in image else
                   f"picture model {image_now} is NOT in this key's list: pictures will look for another" if image else
                   "no picture model is in this key's list" if text else "the model list could not be read")
            _note(store, row, f"{moved}answered in {ms} ms ({model}); {pic}", now)
        else:
            why = {"bad": "Google refused this key: check that it is a Google AI Studio key and that it is not restricted",
                   "limited": "the key's quota or rate limit is used up: it rests, then is tried again",
                   "model": "no text model this key lists answered: pick one on the card, or try again later"}
            _note(store, row, why.get(kind, "Google did not answer: it is tried again"), now)
    if text or image or chosen:
        raw = settings["model_setting"]
        # the pick is what auto follows: the model that answered when Wan's own choice is auto or is gone or silent
        keep = raw != gemini_keys.AUTO and raw in text and chosen == raw
        previous = gemini_keys.load_models(store)["text_pick"]
        _write_models(store, text, image, (previous if keep and previous else chosen) or previous, source, now, gone)
    good = kinds.count("ok")
    return (f"{good} of {len(kinds)} Gemini keys answered" + (f" with {chosen}" if chosen else "") + (
        f"; {kinds.count('bad')} refused, {kinds.count('limited')} limited" if good < len(kinds) else ""))


def refresh_models(store: Any, live: Any, now: datetime | None = None, gone_error: str = "") -> bool:
    """A worker met "that model is gone" on every key: look the models up again (one key is enough) and keep the first that
    answers. True when the model to call is now a different one, so the caller may try again. Never raises."""
    now = now or datetime.now(UTC)
    try:
        keys = [r for r in gemini_keys.usable(gemini_keys.keys(store), now)][:1]
        if not keys:
            return False
        before = gemini_keys.load_settings(store)["model"]
        text, image, source = read_lists(keys, live)
        gone: list[str] = []
        model, _ms, _err = find_working(keys[0], live, before, text, gone)
        if not model:
            return False
        _write_models(store, text, image, model, source, now, gone)
        return gemini_keys.load_settings(store)["model"] != before
    except Exception as exc:  # noqa: BLE001
        log.info("gemini models not refreshed: %s", str(exc)[:100])
        return False


def main() -> int:
    print(f"Gemini check: {run(db.client())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
