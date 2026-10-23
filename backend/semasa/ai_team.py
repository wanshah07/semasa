"""The AI team: every gateway as one Wanshah robot, and the router that picks which robot does which job
(Wan, 23 Oct 2026: "for all segments, make sure can have each robot, AI providers and its model, and the model automatically
switch to use the fastest rate or if the current use models got any issue ... for API segment, I can see whole progress, can
change the model if needed (the system still automatically switch)").

Three robots, the same three as halal-executive's AI team:
  Wanshah 1  rootsys (Afiq)   reads and writes text
  Wanshah 2  Mireld           reads and writes text
  Wanshah 3  KiosAPI          reads a picture and MAKES pictures; never a text writer

Before this, llm.py had a fixed order (rootsys first, Mireld only when rootsys gave nothing) and the page's reader slot could
point a TEXT job at an IMAGE gateway: on 23 Oct the reader slot was kiosapi.com with gpt-image-2, and every scrape answer
was "400 This model is not supported on the Chat Completions endpoint" (screenshot 54). The router does three things:

  1. CANDIDATES: every text gateway with a key (GitHub's primary, GitHub's backup, the page's reader slot), each once,
     minus any that cannot write text (an image host, or an image model on a text slot: those are named in the state
     so the API tab shows WHY they were skipped instead of silently failing).
  2. ORDER: a pinned robot goes first while it is healthy; otherwise the fastest measured one. "Measured" is the average
     answer time of its OK calls in the last 48 hours (semasa_api_usage), else the probe's chat_ms (semasa_api_status).
     A robot the last probe found down, or that failed more than half of its last calls, goes last: it is still asked,
     but only when everything ahead of it gave nothing. llm.py keeps its own in-run failover on top
     (PRIMARY_DOWN_AFTER), so a robot that dies mid-run is still switched away from.
  3. RECORD: settings.ai_team_state says what was chosen and why, for the API tab. Nothing here writes a key anywhere:
     a key still goes only to the host it belongs to (ai_config._key, config.blocked_host).

settings.ai_team (written by the page) = {"pins": {"reader": {"gateway": slug, "model": name} | null,
                                                    "image_gen": {...} | null, "image_reader": {...} | null}}
A pin is a preference, not a lock: the system still switches when the pinned robot is unhealthy.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import db
from .config import LLMSettings, MediaSettings, host_of
from .log import get_logger

log = get_logger("semasa.ai_team")

SETTINGS_KEY = "ai_team"
STATE_KEY = "ai_team_state"
USAGE_WINDOW = timedelta(hours=48)
PROBE_FRESH = timedelta(hours=13)          # the probe runs every 6 h; older than this says nothing about now
MIN_CALLS = 3                              # fewer measured calls than this: trust the probe, not the average

# slug (api_status.slug_of) -> the robot. A host nobody named here is a "guest" robot with no mascot of its own.
ROBOTS: dict[str, dict[str, Any]] = {
    "rootsys": {"robot": "W1", "name": "Wanshah 1", "tone": "afiq", "does": ["read", "write"]},
    "mireld": {"robot": "W2", "name": "Wanshah 2", "tone": "mireld", "does": ["read", "write"]},
    "kiosapi": {"robot": "W3", "name": "Wanshah 3", "tone": "kios", "does": ["read_image", "make_image"]},
}
IMAGE_HOSTS = {"kiosapi.com"}
# a model that draws, not one that talks: never a text writer whatever slot it was typed into
IMAGE_MODEL_RE = re.compile(r"image|dall-?e|flux|stable-?diffusion|sdxl|imagen|seedream|sora|veo|kling|wan2|hunyuan", re.I)


def slug_of(base_url: str) -> str:
    from .api_status import slug_of as _slug
    return _slug(base_url)[0]


def robot_of(base_url: str) -> dict[str, Any]:
    slug = slug_of(base_url)
    return {"slug": slug, **ROBOTS.get(slug, {"robot": "W?", "name": host_of(base_url) or slug, "tone": "guest",
                                             "does": ["read", "write"]})}


def cannot_write_text(base_url: str, model: str) -> str:
    """Why this gateway+model is not a text writer, or ""."""
    host = host_of(base_url).lower()
    if host in IMAGE_HOSTS:
        return f"{ROBOTS['kiosapi']['name']} ({host}) makes pictures; it is not a text reader"
    if model and IMAGE_MODEL_RE.search(model):
        return f"{model} is an image model: the Chat Completions endpoint refuses it (HTTP 400)"
    return ""


# --- what the page saved and what the probes measured ---------------------------------------------------------------

def read_pins(store: Any) -> dict[str, dict[str, Any] | None]:
    try:
        rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    except Exception as exc:  # noqa: BLE001 - no pins is the default
        log.info("ai_team settings not read (%s)", str(exc)[:120])
        return {}
    pins = ((rows[0].get("value") or {}) if rows else {}).get("pins") or {}
    return {k: (v if isinstance(v, dict) and v.get("gateway") else None) for k, v in pins.items()}


def health(store: Any, now: datetime | None = None) -> dict[str, dict[str, Any]]:
    """{slug: {probe_ok, probe_ms, probe_at, fresh, calls, failed, avg_ms}} from the probe rows and 48 h of usage."""
    now = now or datetime.now(UTC)
    out: dict[str, dict[str, Any]] = {}
    try:
        for r in store.table(db.API_STATUS).select("*").execute().data or []:
            at = _parse(r.get("checked_at"))
            out[r["slug"]] = {
                "probe_ok": r.get("chat_ok"), "probe_ms": r.get("chat_ms") or r.get("latency_ms"),
                "probe_at": r.get("checked_at"), "fresh": bool(at and now - at <= PROBE_FRESH),
                "error": r.get("error") or "", "calls": 0, "failed": 0, "avg_ms": None, "_ms": [],
            }
        since = (now - USAGE_WINDOW).isoformat()
        for u in store.table(db.API_USAGE).select("gateway,ms,ok,created_at").gte("created_at", since).execute().data or []:
            h = out.setdefault(u["gateway"], {"probe_ok": None, "probe_ms": None, "probe_at": None, "fresh": False,
                                              "error": "", "calls": 0, "failed": 0, "avg_ms": None, "_ms": []})
            h["calls"] += 1
            if u.get("ok"):
                h["_ms"].append(int(u.get("ms") or 0))
            else:
                h["failed"] += 1
    except Exception as exc:  # noqa: BLE001 - with nothing measured the fixed order stands
        log.info("AI health not read (%s); the configured order is kept", str(exc)[:120])
    for h in out.values():
        ms = h.pop("_ms")
        h["avg_ms"] = int(sum(ms) / len(ms)) if ms else None
    return out


def _parse(s: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


# --- the decision ---------------------------------------------------------------------------------------------------

def candidates(github: LLMSettings, cfg: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Every text gateway a key exists for, each host once: GitHub's primary, GitHub's backup, the page's reader slot.
    `skipped` names the ones that cannot write text, so the API tab can say why."""
    from . import ai_config
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(source: str, provider: str, base: str, key: str | None, model: str, blocked: str = "") -> None:
        base = (base or "").rstrip("/")
        if not base or not key:
            return
        slug = slug_of(base)
        if slug in seen:
            return
        seen.add(slug)
        out.append({"source": source, "slug": slug, "provider": provider or "openai", "base_url": base, "key": key,
                    "model": model or "", "blocked": blocked or cannot_write_text(base, model), **robot_of(base)})

    r = cfg.get("reader") or {}
    if r.get("base_url"):
        provider = r.get("provider") or "openai"
        base = r["base_url"]
        key = ai_config._key(r, "reader", provider, base)        # the page's key, only at the host it was saved for
        if key:
            add("page", provider, base, key, r.get("model") or "")
        elif host_of(base) == host_of(github.base_url) and github.api_key:
            add("page", provider, base, github.api_key, r.get("model") or github.model, github.blocked)
    add("github", github.provider, github.base_url, github.api_key, github.model, github.blocked)
    if github.fallback_key:
        add("backup", "openai", github.fallback_base_url, github.fallback_key, github.fallback_model, github.fallback_blocked)
    return out


def order(cands: list[dict[str, Any]], hl: dict[str, dict[str, Any]], pin: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The usable candidates, fastest first; the pinned one first while healthy; an unhealthy one last. Each carries `why`."""
    usable = [c for c in cands if not c["blocked"]]
    for c in usable:
        h = hl.get(c["slug"]) or {}
        c["probe_ok"], c["probe_ms"], c["avg_ms"], c["calls"], c["failed"] = \
            h.get("probe_ok"), h.get("probe_ms"), h.get("avg_ms"), h.get("calls", 0), h.get("failed", 0)
        down = (h.get("fresh") and h.get("probe_ok") is False) or (c["calls"] >= MIN_CALLS and c["failed"] * 2 > c["calls"])
        c["healthy"] = not down
        measured = c["avg_ms"] if c["calls"] >= MIN_CALLS and c["avg_ms"] is not None else c["probe_ms"]
        c["speed_ms"] = measured
        c["why"] = ("down: " + (h.get("error") or f"{c['failed']} of {c['calls']} calls failed")) if down \
            else (f"{measured} ms" if measured is not None else "not measured yet")
    pinned = (pin or {}).get("gateway")
    for c in usable:
        if pinned and c["slug"] == pinned:
            if (pin or {}).get("model"):
                c["model"] = pin["model"]
            c["pinned"] = True
            if c["healthy"]:
                c["why"] = "pinned · " + c["why"]
            else:
                c["why"] = "pinned but " + c["why"] + " · switched away"
    usable.sort(key=lambda c: (0 if c["healthy"] else 1,
                               0 if (c.get("pinned") and c["healthy"]) else 1,
                               c["speed_ms"] if c["speed_ms"] is not None else 10**9))
    return usable


def route(store: Any, github: LLMSettings, cfg: dict[str, dict[str, Any]], now: datetime | None = None) -> LLMSettings:
    """LLMSettings with the fastest healthy text robot as the primary and the next as the backup; the picture reader as
    ai_config decides it. Records the decision in settings.ai_team_state. With nothing measured the configured order
    stands, so a store that cannot be read changes nothing."""
    from . import ai_config
    base = ai_config.llm_settings(github, cfg)                 # the page's picture reader and vision model, as before
    cands = candidates(github, cfg)
    pins = read_pins(store)
    ranked = order(cands, health(store, now), pins.get("reader"))
    skipped = [c for c in cands if c["blocked"]]
    state: dict[str, Any] = {
        "at": (now or datetime.now(UTC)).isoformat(),
        "reader": {
            "order": [{k: c.get(k) for k in ("slug", "robot", "name", "model", "source", "healthy", "speed_ms", "why", "pinned")}
                      for c in ranked],
            "skipped": [{"slug": c["slug"], "robot": c["robot"], "name": c["name"], "model": c["model"], "why": c["blocked"]}
                        for c in skipped],
            "pin": pins.get("reader"),
        },
    }
    if not ranked:
        state["reader"]["chosen"] = None
        state["reader"]["why"] = "no text robot has a usable key" + (": " + skipped[0]["blocked"] if skipped else "")
        _record(store, state)
        # keep what ai_config made, minus a reader that cannot write text: llm.py then says why_off() honestly
        if skipped and host_of(base.base_url) == host_of(skipped[0]["base_url"]):
            base = dataclasses.replace(base, blocked=skipped[0]["blocked"])
        return base
    first = ranked[0]
    second = next((c for c in ranked[1:] if c["provider"] == "openai"), None)   # the backup speaks the OpenAI dialect only
    state["reader"]["chosen"] = {"slug": first["slug"], "robot": first["robot"], "name": first["name"], "model": first["model"]}
    state["reader"]["why"] = first["why"]
    state["reader"]["backup"] = {"slug": second["slug"], "robot": second["robot"], "name": second["name"],
                                 "model": second["model"]} if second else None
    _record(store, state)
    change: dict[str, Any] = dict(provider=first["provider"], base_url=first["base_url"], api_key=first["key"],
                                  model=first["model"], blocked="",
                                  fallback_base_url=second["base_url"] if second else "",
                                  fallback_key=second["key"] if second else None,
                                  fallback_model=second["model"] if second else "", fallback_blocked="")
    # a writer that moved host or model reads pictures with its own model unless the page set a picture reader
    if not base.vision_reader_model and (host_of(first["base_url"]) != host_of(base.base_url) or first["model"] != base.model):
        change["vision_model"] = first["model"]
    log.info("AI team: %s (%s, %s) writes%s", first["name"], first["slug"], first["model"],
             f"; {second['name']} is the backup" if second else "")
    return dataclasses.replace(base, **change)


def route_media(store: Any, s: MediaSettings) -> MediaSettings:
    """The picture maker: a pinned model for the image slot wins over the saved one. The provider itself is Tetapan's."""
    pin = read_pins(store).get("image_gen") or {}
    if not pin.get("model"):
        return s
    if s.provider == "openai" and (not pin.get("gateway") or slug_of(s.openai_base_url) == pin["gateway"]):
        return dataclasses.replace(s, openai_image_model=pin["model"])
    if s.provider == "cloudflare" and pin.get("gateway") in ("", None, "cloudflare"):
        return dataclasses.replace(s, cloudflare_t2i_model=pin["model"])
    if s.provider == "replicate" and pin.get("gateway") in ("", None, "replicate"):
        return dataclasses.replace(s, replicate_t2i_model=pin["model"])
    return s


def _record(store: Any, state: dict[str, Any]) -> None:
    try:
        old = store.table(db.SETTINGS).select("value").eq("key", STATE_KEY).execute().data or []
        value = {**((old[0].get("value") or {}) if old else {}), **state}
        store.table(db.SETTINGS).upsert({"key": STATE_KEY, "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - the record is for the page; the run goes on
        log.info("ai_team_state not written (%s)", str(exc)[:120])
