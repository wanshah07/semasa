"""Gemini, with several API keys that are picked automatically (Wan, 6 Nov 2026: "add gemini api key I can add multiple and its
auto select same like chatgpt").

Wan adds any number of Google AI Studio keys on the API tab (supabase/061: `semasa_gemini_keys`, which no page policy can read).
Semasa then uses Gemini in two places and picks the key itself each time:

  * AS A TEXT ROBOT (Wanshah 4) in the AI team (ai_team.py): a candidate beside rootsys, Mireld and KiosAPI that the router
    ranks by health and speed. Only for the jobs Wan allows (`settings.gemini.jobs`, default Motion and the idea writer): Otak
    AI, receipts, billing and the CRM never reach it, because a free Gemini key may let Google use what it is sent.
  * TO DRAW MOTION'S SCENE PICTURES (gemini_images.py), after ChatGPT, or alone when ChatGPT is not connected.

PICKING A KEY. The usable keys are the enabled ones that are not `bad` (Google refused the key) and not cooling down after a
rate-limit answer. They are tried least-recently-used first, so the load and the free quota spread over all of them. A key that
answered in the last ten minutes is used without another question; any other is asked a five-token question first, and a key that
fails is marked (limited: 30 minutes; a hiccup: 2 minutes; bad: until Wan switches it on again) and the next is tried, up to three
in one decision. The key itself goes only to generativelanguage.googleapis.com, never anywhere else.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.gemini_keys")

TABLE = "semasa_gemini_keys"
SETTINGS_KEY = "gemini"
HOST = "generativelanguage.googleapis.com"
BASE = f"https://{HOST}/v1beta/openai"          # the OpenAI-compatible chat endpoint (text and pictures read)
NATIVE = f"https://{HOST}/v1beta"               # the native endpoint (a picture is made here)
DEFAULTS: dict[str, Any] = {"enabled": True, "model": "gemini-2.5-flash", "image_model": "gemini-2.5-flash-image",
                            "images": True, "max_images": 6, "jobs": ["motion", "ideas"]}
JOBS = ("reader", "motion", "ideas")             # the router's jobs; "reader" is every other worker (brain, receipts, scrape ...)
FRESH = timedelta(minutes=10)                    # a key that answered this recently is not asked again
COOLDOWN = {"limited": timedelta(minutes=30), "retry": timedelta(minutes=2)}
TRIES = 3                                        # keys asked in one decision

LIMITED = re.compile(r"\b429\b|resource_exhausted|quota|rate.?limit|too many requests|exceeded", re.I)
BAD = re.compile(r"\b(400|401|403)\b.*(api key|api_key|permission|unauthori|invalid|expired|denied)|api key not valid|"
                 r"api_key_invalid|permission_denied|unauthenticated|key.*(revoked|disabled|suspended)", re.I)


def classify(error: Any) -> str:
    """"bad" (Google refuses the key), "limited" (its quota or rate is used up), or "retry" (anything else: a hiccup)."""
    text = str(error or "")
    if BAD.search(text) and not LIMITED.search(text):
        return "bad"
    if LIMITED.search(text):
        return "limited"
    return "retry"


def load_settings(store: Any) -> dict[str, Any]:
    """settings.gemini laid over the defaults; a missing row (061 not run) or a failed read is the defaults."""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", SETTINGS_KEY).execute().data or []
        value = (rows[0].get("value") or {}) if rows else {}
    except Exception as exc:  # noqa: BLE001
        log.info("gemini settings not read (%s)", str(exc)[:100])
        value = {}
    out = {**DEFAULTS, **{k: v for k, v in value.items() if k in DEFAULTS and v is not None and v != ""}}
    out["jobs"] = [j for j in (out.get("jobs") or []) if j in JOBS]
    out["max_images"] = max(1, min(8, int(out.get("max_images") or 6)))
    return out


def _parse(stamp: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def keys(store: Any) -> list[dict[str, Any]]:
    """Every key row, key included (service role only). [] when the table is not there or cannot be read."""
    try:
        return [r for r in store.table(TABLE).select("*").execute().data or [] if r.get("api_key")]
    except Exception as exc:  # noqa: BLE001 - 061 not applied yet: Gemini is simply off
        log.info("gemini keys not read (%s)", str(exc)[:100])
        return []


def usable(rows: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    """The keys that may be tried now, least recently used first: enabled, not bad, not cooling down."""
    ok = []
    for r in rows:
        if not r.get("enabled", True) or r.get("status") == "bad":
            continue
        cool = _parse(r.get("cooldown_until"))
        if cool and cool > now:
            continue
        ok.append(r)
    ok.sort(key=lambda r: (_parse(r.get("last_used_at")) or datetime.min.replace(tzinfo=UTC), int(r.get("failures") or 0)))
    return ok


def note(store: Any, row: dict[str, Any], ok: bool, error: Any = "", now: datetime | None = None) -> str:
    """Records what a key just did: ok clears its cooldown; a failure marks it by kind. Returns the kind ("ok", "bad", "limited",
    "retry"). Never raises: a status line lost must not lose a post."""
    now = now or datetime.now(UTC)
    stamp = now.isoformat()
    if ok:
        patch: dict[str, Any] = {"status": "ok", "last_ok_at": stamp, "last_used_at": stamp, "cooldown_until": None,
                                 "last_error": None, "last_error_at": None, "calls": int(row.get("calls") or 0) + 1}
        kind = "ok"
    else:
        kind = classify(error)
        patch = {"last_used_at": stamp, "last_error": " ".join(str(error or "").split())[:300], "last_error_at": stamp,
                 "failures": int(row.get("failures") or 0) + 1, "calls": int(row.get("calls") or 0) + 1}
        patch["status"] = "bad" if kind == "bad" else "limited"
        patch["cooldown_until"] = None if kind == "bad" else (now + COOLDOWN[kind]).isoformat()
    try:
        store.table(TABLE).update({**patch, "updated_at": stamp}).eq("id", row["id"]).execute()
        row.update(patch)
    except Exception as exc:  # noqa: BLE001
        log.info("gemini key status not saved: %s", str(exc)[:100])
    return kind


def pick(store: Any, now: datetime, ask: Any = None, tries: int = TRIES) -> tuple[dict[str, Any] | None, int | None]:
    """(the key row to use, its answer time in ms). `ask(row) -> (ok, ms, error)` is the five-token question; None means no
    question is asked (a run that must not spend a call): the first usable key is taken. (None, None) when no key can be used."""
    for row in usable(keys(store), now)[:tries]:
        last = _parse(row.get("last_ok_at"))
        if row.get("status") == "ok" and last and now - last <= FRESH:
            return row, None
        if ask is None:
            return row, None
        ok, ms, err = ask(row)
        if ok:
            note(store, row, True, now=now)
            return row, ms
        note(store, row, False, err, now=now)
    return None, None


def allowed(store: Any, job: str) -> bool:
    s = load_settings(store)
    return bool(s["enabled"]) and job in s["jobs"]


def candidate(store: Any, job: str, live: Any, now: datetime) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """(the AI-team candidate, the health the key's own check already proved) for this job, or (None, None) when Gemini is off,
    not allowed for the job, or has no usable key. The key is the one pick() chose; it goes only to the Gemini host."""
    if not allowed(store, job):
        return None, None
    s = load_settings(store)

    def ask(row: dict[str, Any]) -> tuple[bool, int | None, str]:
        c = {"slug": "gemini", "provider": "openai", "base_url": BASE, "key": row["api_key"]}
        return live.chat(c, s["model"])

    row, ms = pick(store, now, ask if live is not None else None)
    if row is None:
        return None, None
    from . import ai_team
    cand = {"source": "gemini", "slug": "gemini", "provider": "openai", "base_url": BASE, "key": row["api_key"],
            "model": s["model"], "blocked": ai_team.cannot_write_text(BASE, s["model"]), "gemini_key": row["id"],
            **ai_team.robot_of(BASE)}
    seed = {"probe_ok": True, "probe_ms": ms, "probe_at": now.isoformat(), "fresh": True, "error": ""} if ms is not None else None
    return cand, seed


def gateway(store: Any, now: datetime | None = None) -> dict[str, Any] | None:
    """The Gemini gateway for the API tab's probe: the key that would be used next, no question asked here (the probe asks)."""
    now = now or datetime.now(UTC)
    if not load_settings(store)["enabled"]:
        return None
    row, _ = pick(store, now, None)
    if row is None:
        return None
    s = load_settings(store)
    return {"slug": "gemini", "name": "Gemini (Wanshah 4)", "role": "primary", "base_url": BASE, "key": row["api_key"],
            "model": s["model"], "provider": "openai", "blocked": ""}
