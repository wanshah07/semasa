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

LIVE CHECKS (Wan, 31 Oct 2026: "why I cannot change the model, make sure for auto model search is live"). The probe asks each
gateway ONE model every 6 hours, so a gateway whose probe model had a bad hour (rootsys answering 502 on kimi-k3.1-pro) was
written off as down, and a pin to ANOTHER of its models (glm-5.3) was thrown away without ever being tried: Wan changed the
model and the text writer stayed on Mireld's kimi-k3. So the router now checks live, a five-token question at decision time:
  * a pinned model is asked itself; if it answers, the pin stands whatever the 6-hourly probe of another model said;
  * Auto, when a gateway's configured model is not known to work, SEARCHES the gateway's live /models list: the models that
    answered its recent calls first (fastest first), then the rest of the chat models, up to LIVE_TRIES; the first that
    answers is used, and the decision says which and why.
Answers are remembered LIVE_TTL minutes in ai_team_state.live so every worker run does not repeat the questions.
"""

from __future__ import annotations

import dataclasses
import os
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
LIVE_TTL = timedelta(minutes=10)           # a live answer is trusted this long (runs are frequent; a question is not free)
LIVE_TRIES = 3                             # models asked per gateway in one search
LIVE_TIMEOUT = 12                          # seconds a live question may take
# usage rows that are CHECKS, not work: the 6-hourly probe and the 5-minute edge-function pulse. They are left out of the
# calls / avg_ms / models_ok ranking (the probe's verdict reaches health() through semasa_api_status instead).
CHECK_AREAS = ("probe", "pulse")
# Wan, 8 Nov 2026: "make the robot priority like this - Rootsys > Mireld > KioskAPI > ChatGPT > Gemini for reasoning, read, write,
# read image". Among the robots that are healthy, this order decides who is asked first; speed only breaks a tie between robots
# Wan has not ranked (the providers he adds). A down robot is still last and the chain still falls over down the list. Gemini
# stays off every job Wan has not allowed it for (gemini_keys.allowed), whatever its place here.
PRIORITY = ("rootsys", "mireld", "kiosapi", "chatgpt", "gemini")
# gateways that carry both text and picture models: their robot reads a picture only with the model pinned for the picture reader,
# because the writer model it holds by default (deepseek-v4-pro on rootsys) would describe a picture it never saw
VISION_BY_PIN = ("rootsys",)


def priority_rank(slug: str) -> int:
    """0 for the first of PRIORITY ... 4 for the last; a robot Wan has not ranked comes after all of them."""
    return PRIORITY.index(slug) if slug in PRIORITY else len(PRIORITY)


# slug (api_status.slug_of) -> the robot. A host nobody named here is a "guest" robot with no mascot of its own.
ROBOTS: dict[str, dict[str, Any]] = {
    # Wan, 11 Nov 2026: "make wanshah1 read the image". rootsys lists many models and its writer model (deepseek) is not one that
    # sees, so W1 reads a picture with the model pinned for the Picture reader job, never with its writer model (VISION_BY_PIN)
    "rootsys": {"robot": "W1", "name": "Wanshah 1", "tone": "afiq", "does": ["read", "write", "read_image"]},
    "mireld": {"robot": "W2", "name": "Wanshah 2", "tone": "mireld", "does": ["read", "write", "make_image"]},
    # KiosAPI serves chat models too (Wan's reader slot runs gpt-5.6-sol there), so it may write text; what it may NOT do is
    # answer a chat question with an image model, which cannot_write_text() refuses by the model's name.
    "kiosapi": {"robot": "W3", "name": "Wanshah 3", "tone": "kios", "does": ["read", "write", "read_image", "make_image"]},
    # Gemini (Wan, 6 Nov 2026): several keys picked automatically (gemini_keys.py); only the jobs Wan allows ever see it
    "gemini": {"robot": "W4", "name": "Wanshah 4", "tone": "guest", "does": ["read", "write", "read_image", "make_image"]},
    # ChatGPT (Wan, 7 Nov 2026: "add bot for chatgpt"): Wan's own ChatGPT login (chatgpt_login.py), not an API key
    "chatgpt": {"robot": "W5", "name": "Wanshah 5", "tone": "guest", "does": ["read", "write", "read_image", "make_image"]},
}
# Providers Wan adds on the API tab (ai_providers.py, supabase/074) follow as W6, W7, ... in creation order: robots() merges them.
PROVIDER_TONE = "provider"
# a model that draws, not one that talks: never a text writer whatever slot it was typed into
IMAGE_MODEL_RE = re.compile(r"image|dall-?e|flux|stable-?diffusion|sdxl|imagen|seedream|sora|veo|kling|wan2|hunyuan", re.I)


def slug_of(base_url: str) -> str:
    from .api_status import slug_of as _slug
    return _slug(base_url)[0]


def robot_of(base_url: str) -> dict[str, Any]:
    slug = slug_of(base_url)
    return {"slug": slug, **ROBOTS.get(slug, {"robot": "W?", "name": host_of(base_url) or slug, "tone": "guest",
                                             "does": ["read", "write"]})}


def robots(store: Any) -> dict[str, dict[str, Any]]:
    """ROBOTS plus every provider Wan added (W6, W7, ...), keyed by slug: the table Telegram and the page read names from."""
    from . import ai_providers
    return {**ROBOTS, **ai_providers.robots(ai_providers.load(store))}


def cannot_write_text(base_url: str, model: str) -> str:
    """Why this gateway+model is not a text writer, or "". By the MODEL, never the host: a gateway that draws pictures may
    also serve chat models, and judging it by its address skipped Wan's own text model (gpt-5.6-sol on kiosapi.com)."""
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


def read_models(store: Any) -> dict[str, str]:
    """The model Wan chose as a robot's own default, {slug: model} (settings.ai_team.models). It beats the model GitHub's
    variables or the page's slots carry for that gateway, for the probe and the router alike (Wan, 9 Nov 2026: "allow me to adjust
    model mireld": Mireld's configured kimi-k3 answered in 27 s and was reported down while claude-fable-5.1 answered in 3 s)."""
    try:
        rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    except Exception as exc:  # noqa: BLE001 - no override is the default
        log.info("ai_team models not read (%s)", str(exc)[:120])
        return {}
    raw = ((rows[0].get("value") or {}) if rows else {}).get("models") or {}
    return {str(k): str(v).strip() for k, v in raw.items() if isinstance(raw, dict) and isinstance(v, str) and v.strip()}


EFFORTS = ("low", "medium", "high", "xhigh")


def read_efforts(store: Any) -> dict[str, str]:
    """The reasoning effort Wan chose for a model, {"slug|model": effort} (settings.ai_team.efforts; the API tab writes it). Only
    the four known levels are kept: anything else is read as "no choice", which sends nothing to the gateway."""
    try:
        rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    except Exception as exc:  # noqa: BLE001 - no choice is the default
        log.info("ai_team efforts not read (%s)", str(exc)[:120])
        return {}
    raw = ((rows[0].get("value") or {}) if rows else {}).get("efforts") or {}
    return {str(k): str(v).strip().lower() for k, v in raw.items()
            if isinstance(raw, dict) and isinstance(v, str) and v.strip().lower() in EFFORTS}


def efforts_for(chosen: dict[str, str], ranked: list[dict[str, Any]],
                extra: tuple[str, str, str] | None = None) -> tuple[tuple[str, str], ...]:
    """The choices as ("host|model", effort) pairs for the robots and models a call can actually reach, so llm.py needs no slug
    table. `extra` is (slug, base_url, model) for the pinned picture reader, whose model is not the robot's writer model."""
    out: dict[str, str] = {}
    for c in ranked:
        e = chosen.get(f"{c['slug']}|{c.get('model') or ''}")
        if e:
            out[f"{host_of(c['base_url'])}|{c['model']}"] = e
    if extra:
        e = chosen.get(f"{extra[0]}|{extra[2]}")
        if e:
            out[f"{host_of(extra[1])}|{extra[2]}"] = e
    return tuple(out.items())


def apply_models(cands: list[dict[str, Any]], models: dict[str, str]) -> list[dict[str, Any]]:
    """Each candidate (or probe row) whose slug has a chosen model gets it. A "blocked" reason that was only about the OLD model
    (an image model on the chat endpoint) is recomputed for the new one; a block for the gateway's HOST stays."""
    for c in cands:
        want = models.get(c.get("slug") or "")
        if not want or want == c.get("model"):
            continue
        old_reason = cannot_write_text(c.get("base_url", ""), c.get("model", ""))
        c["model"] = want
        if "blocked" in c and (not c["blocked"] or c["blocked"] == old_reason):
            c["blocked"] = cannot_write_text(c.get("base_url", ""), want)
    return cands


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
        usage = store.table(db.API_USAGE).select("gateway,model,ms,ok,created_at,area").gte("created_at", since).execute()
        for u in usage.data or []:
            if u.get("area") in CHECK_AREAS:
                continue          # a five-token check says nothing about real work, and 12 pulses an hour would drown it
            h = out.setdefault(u["gateway"], {"probe_ok": None, "probe_ms": None, "probe_at": None, "fresh": False,
                                              "error": "", "calls": 0, "failed": 0, "avg_ms": None, "_ms": []})
            h["calls"] += 1
            if u.get("ok"):
                h["_ms"].append(int(u.get("ms") or 0))
                if u.get("model"):
                    h.setdefault("_by_model", {}).setdefault(u["model"], []).append(int(u.get("ms") or 0))
            else:
                h["failed"] += 1
    except Exception as exc:  # noqa: BLE001 - with nothing measured the fixed order stands
        log.info("AI health not read (%s); the configured order is kept", str(exc)[:120])
    for h in out.values():
        ms = h.pop("_ms")
        h["avg_ms"] = int(sum(ms) / len(ms)) if ms else None
        # the models that answered this gateway's real calls, fastest first: the live search asks these before the rest
        by_model = h.pop("_by_model", {})
        h["models_ok"] = sorted(by_model, key=lambda m: sum(by_model[m]) / len(by_model[m]))
    return out


def _parse(s: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


# --- asking a gateway live ------------------------------------------------------------------------------------------------

class Live:
    """The two live questions: does THIS model answer a five-token question right now, and which models does the gateway list
    right now. Tests pass a stand-in; the real one is `LIVE`, used by the runners (`llm_for`) and the API workflow."""

    def chat(self, c: dict[str, Any], model: str, timeout: int = LIVE_TIMEOUT) -> tuple[bool, int | None, str]:
        from . import api_status
        gw = {"provider": c["provider"], "base_url": c["base_url"], "key": c["key"], "model": model}
        ok, ms, _usage, err = api_status._chat(gw, timeout)
        return ok, ms, err

    def models(self, c: dict[str, Any], timeout: int = LIVE_TIMEOUT) -> list[str]:
        from . import api_status
        gw = {"provider": c["provider"], "base_url": c["base_url"], "key": c["key"]}
        return [m.removeprefix("models/") for m in api_status._models(gw, timeout)[0]]     # Gemini lists "models/gemini-..."


    def native_models(self, c: dict[str, Any], timeout: int = LIVE_TIMEOUT) -> list[dict[str, Any]]:
        """Gemini's own model list: [{name, methods}], which says what each model can DO (generateContent draws a picture, an
        embedding model cannot). [] when it cannot be read."""
        import requests
        try:
            r = requests.get(f"{c['base_url']}/models", headers={"x-goog-api-key": c["key"]}, params={"pageSize": 200},
                             timeout=timeout)
            if r.status_code != 200:
                return []
            return [{"name": str(m.get("name") or "").removeprefix("models/"),
                     "methods": list(m.get("supportedGenerationMethods") or [])}
                    for m in r.json().get("models") or [] if isinstance(m, dict)]
        except (requests.RequestException, ValueError):
            return []


LIVE = Live()


def live_enabled() -> bool:
    """On by default; AI_TEAM_LIVE=0 turns the questions off (a run that must not spend a call, or an offline test)."""
    return os.environ.get("AI_TEAM_LIVE", "1") != "0"


def text_models(listed: list[str]) -> list[str]:
    """The listed models that can write text, in a steady order: the ones that draw, hear or embed are left out."""
    skip = re.compile(r"embed|whisper|tts|speech|moderation|rerank|transcri", re.I)
    return [m for m in listed if not IMAGE_MODEL_RE.search(m) and not skip.search(m)]


def _remembered(old: dict[str, Any], slug: str, model: str, now: datetime) -> dict[str, Any] | None:
    r = (old.get("live") or {}).get(f"{slug}|{model}")
    at = _parse((r or {}).get("at"))
    return r if r and at and now - at <= LIVE_TTL else None


def live_verify(cands: list[dict[str, Any]], hl: dict[str, dict[str, Any]], pin: dict[str, Any] | None, live: Any,
                old_state: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Ask the gateways live (see the module doc) and correct `cands` and `hl` with what they said. Returns the record the API
    tab shows: {"answers": {"slug|model": {ok, ms, error, at}}, "found": {slug: model}, "searched": {slug: [models tried]}}."""
    answers: dict[str, dict[str, Any]] = {}
    found: dict[str, str] = {}
    searched: dict[str, list[str]] = {}

    def ask(c: dict[str, Any], model: str) -> dict[str, Any]:
        key = f"{c['slug']}|{model}"
        if key not in answers:
            r = _remembered(old_state, c["slug"], model, now)
            if r is None:
                ok, ms, err = live.chat(c, model)
                r = {"ok": bool(ok), "ms": ms, "error": "" if ok else str(err or "")[:160], "at": now.isoformat()}
            answers[key] = r
        return answers[key]

    def settle(c: dict[str, Any], r: dict[str, Any], note: str = "") -> None:
        h = hl.setdefault(c["slug"], {"calls": 0, "failed": 0, "avg_ms": None, "models_ok": []})
        h.update(probe_ok=r["ok"], probe_ms=r["ms"], probe_at=r["at"], fresh=True,
                 error=("" if r["ok"] else (note + r["error"])))

    pinned = (pin or {}).get("gateway")
    for c in cands:
        if c["blocked"]:
            continue
        h = hl.get(c["slug"]) or {}
        down = (h.get("fresh") and h.get("probe_ok") is False) or (
            h.get("calls", 0) >= MIN_CALLS and h.get("failed", 0) * 2 > h["calls"])
        if pinned and c["slug"] == pinned and (pin or {}).get("model"):
            # Wan chose this model: ask it itself, and let the answer outrank the probe of whatever model the probe asked
            c["model"] = pin["model"]
            r = ask(c, pin["model"])
            settle(c, r, f"pinned model {pin['model']} answered ")
            if r["ok"]:
                h = hl[c["slug"]]
                h["calls"], h["failed"] = 0, 0                    # a model that answers now is not "down" for an old failed run
            continue
        if not (down or not h.get("fresh")):
            continue                                              # known to work: no question needed
        tried: list[str] = []
        pool = [m for m in [c["model"], *h.get("models_ok", [])] if m]
        for attempt in range(LIVE_TRIES):
            if attempt == len(pool):
                pool += [m for m in text_models(live.models(c)) if m not in pool]          # then the gateway's own live list
            if attempt >= len(pool):
                break
            model = pool[attempt]
            tried.append(model)
            r = ask(c, model)
            if r["ok"]:
                if model != c["model"]:
                    found[c["slug"]] = model
                    c["found"] = model
                    c["model"] = model
                settle(c, r)
                h = hl[c["slug"]]
                h["calls"], h["failed"] = 0, 0
                break
            settle(c, r)
        searched[c["slug"]] = tried
    return {"answers": answers, "found": found, "searched": searched}


# --- the decision ---------------------------------------------------------------------------------------------------

def candidates(github: LLMSettings, cfg: dict[str, dict[str, Any]], job: str = "reader",
               providers: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Every text gateway a key exists for, each host once: for the motion job the page's own motion slot first, then the
    page's reader slot, GitHub's primary, GitHub's backup, then every provider Wan added (`providers`, the rows
    ai_providers.load returns) whose `jobs` allow this job. `skipped` names the ones that cannot write text."""
    from . import ai_config, ai_providers
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

    for slot, source in ((("motion", "motion"),) if job == "motion" else ()) + (("reader", "page"),):
        r = cfg.get(slot) or {}
        if not r.get("base_url"):
            continue
        provider = r.get("provider") or "openai"
        base = r["base_url"]
        key = ai_config._key(r, slot, provider, base)            # the page's key, only at the host it was saved for
        if key:
            add(source, provider, base, key, r.get("model") or "")
        elif slot == "reader" and host_of(base) == host_of(github.base_url) and github.api_key:
            add(source, provider, base, github.api_key, r.get("model") or github.model, github.blocked)
    add("github", github.provider, github.base_url, github.api_key, github.model, github.blocked)
    if github.fallback_key:
        add("backup", "openai", github.fallback_base_url, github.fallback_key, github.fallback_model, github.fallback_blocked)
    for c in ai_providers.candidates(None, job, providers or []):
        if c["slug"] not in seen:                      # a provider is its own robot even on a host a built-in also uses
            seen.add(c["slug"])
            out.append(c)
    return out


def order(cands: list[dict[str, Any]], hl: dict[str, dict[str, Any]], pin: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The usable candidates: the healthy ones first, the pinned one first while healthy, then Wan's priority (PRIORITY), then the
    fastest; an unhealthy one last. Each carries `why`."""
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
        if c.get("found"):
            c["why"] = f"{c['found']} found by a live search · {c['why']}"
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
                               priority_rank(c["slug"]),
                               c["speed_ms"] if c["speed_ms"] is not None else 10**9))
    return usable


def chain(store: Any, github: LLMSettings, cfg: dict[str, dict[str, Any]], now: datetime | None = None,
          job: str = "reader", live: Any = None, details: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """The FULL ranked chain for this job: every usable text robot `candidates()` lists (plus Gemini when the job is one
    Wan allows it, gemini_keys.allowed), healthy first, the pinned one first while it is healthy, a down one last and
    still in the list; every dialect, so an Anthropic robot is a link too. Each link carries {slug, provider, base_url,
    key, model, vision_model, ...}; `vision_model` is the robot's own model when it reads pictures, else "", so llm.py
    never sends a picture to a model that cannot see. Records the decision in settings.ai_team_state, exactly as
    route() always did. `details`, when given, is filled with {"skipped": [...], "state": {...}} for route().

    This consumes candidates() and gemini_keys.candidate() as they are: a robot added to either is a link here with no
    change to this function. (Feature C, 8 Nov 2026: every backend AI call falls over to another live robot.)"""
    providers: list[dict[str, Any]] = []
    try:                          # the providers Wan added on the API tab (supabase/074): robots W6, W7, ... for their jobs
        from . import ai_providers, api_status
        providers = ai_providers.load(store)
        api_status.remember_providers(providers)           # so their usage rows carry the provider's slug, not its host
    except Exception as exc:  # noqa: BLE001 - no providers is the team as it was
        log.info("AI providers not considered (%s)", str(exc)[:120])
    cands = apply_models(candidates(github, cfg, job, providers), read_models(store))
    gem_seed: dict[str, Any] | None = None
    try:                          # Gemini joins the team for the jobs Wan allows, with the key it picks (gemini_keys.py)
        from . import gemini_keys
        gem, gem_seed = gemini_keys.candidate(store, job, live, now or datetime.now(UTC))
        if gem and not any(c["slug"] == "gemini" for c in cands):
            cands.append(gem)
    except Exception as exc:  # noqa: BLE001 - Gemini is an extra: the team without it is the team as it was
        log.info("Gemini not considered (%s)", str(exc)[:120])
    try:                          # Wan's ChatGPT login writes and reads pictures for the worker jobs (chatgpt_login.candidate)
        from . import chatgpt_login
        cg = chatgpt_login.candidate(store, job, now)
        if cg and not any(c["slug"] == "chatgpt" for c in cands):
            cands.append(cg)
    except Exception as exc:  # noqa: BLE001 - ChatGPT is an extra: the team without it is the team as it was
        log.info("ChatGPT not considered (%s)", str(exc)[:120])
    pins = read_pins(store)
    pin = pins.get(job)
    if not pin and job == "motion" and cands and cands[0]["source"] == "motion":
        pin = {"gateway": cands[0]["slug"], "model": ""}        # Wan's own motion API goes first while it is healthy
    hl = health(store, now)
    if gem_seed:                              # the key's own check already answered: the live question is not asked twice
        hl["gemini"] = {**hl.get("gemini", {"calls": 0, "failed": 0, "avg_ms": None, "models_ok": []}), **gem_seed}
    now_at = now or datetime.now(UTC)
    asked: dict[str, Any] = {}
    if live is not None:
        try:
            asked = live_verify(cands, hl, pin, live, _read_state(store), now_at)
        except Exception as exc:  # noqa: BLE001 - a live question that breaks leaves the measured order as it was
            log.warning("AI team live check failed (%s); the measured order stands", str(exc)[:160])
    ranked = order(cands, hl, pin)
    for c in ranked:
        c["vision_model"] = c["model"] if "read_image" in (c.get("does") or []) and c["slug"] not in VISION_BY_PIN else ""
    skipped = [c for c in cands if c["blocked"]]
    state: dict[str, Any] = {
        "at": now_at.isoformat(),
        job: {
            "order": [{k: c.get(k) for k in ("slug", "robot", "name", "model", "source", "healthy", "speed_ms", "why", "pinned")}
                      for c in ranked],
            "skipped": [{"slug": c["slug"], "robot": c["robot"], "name": c["name"], "model": c["model"], "why": c["blocked"]}
                        for c in skipped],
            "pin": pin,
            "live": {"found": asked.get("found") or {}, "searched": asked.get("searched") or {},
                     "answers": {k: {"ok": v["ok"], "ms": v["ms"], "error": v["error"]}
                                 for k, v in (asked.get("answers") or {}).items()}} if asked else None,
        },
    }
    if asked:
        state["live"] = {**{k: v for k, v in (_read_state(store).get("live") or {}).items()
                            if _parse(v.get("at")) and now_at - _parse(v["at"]) <= LIVE_TTL}, **asked["answers"]}
    if ranked:
        first = ranked[0]
        second = next((c for c in ranked[1:] if c["provider"] == "openai"), None)   # the OpenAI-dialect backup in the settings
        state[job]["chosen"] = {"slug": first["slug"], "robot": first["robot"], "name": first["name"], "model": first["model"]}
        state[job]["why"] = first["why"]
        state[job]["backup"] = {"slug": second["slug"], "robot": second["robot"], "name": second["name"],
                                "model": second["model"]} if second else None
        state[job]["chain"] = [c["slug"] for c in ranked]
    else:
        state[job]["chosen"] = None
        state[job]["why"] = "no text robot has a usable key" + (": " + skipped[0]["blocked"] if skipped else "")
    _record(store, state)
    if details is not None:
        details.update(skipped=skipped, state=state)
    return ranked


def picture_reader_change(pin: dict[str, Any] | None, ranked: list[dict[str, Any]]) -> dict[str, Any]:
    """The LLMSettings fields that make a pinned robot the picture reader: {} when nothing is pinned, the robot is not a usable
    text robot with a key here, or it cannot read pictures. A pin with no model uses the robot's own vision model, which a
    robot in VISION_BY_PIN does not have, so it reads nothing until Wan picks one."""
    gateway = (pin or {}).get("gateway")
    if not gateway:
        return {}
    c = next((x for x in ranked if x["slug"] == gateway), None)
    if c is None or "read_image" not in (c.get("does") or []):
        return {}
    model = (pin or {}).get("model") or c.get("vision_model") or ""
    if not model or not c.get("key"):
        return {}
    return {"vision_provider": c["provider"], "vision_base_url": c["base_url"], "vision_key": c["key"],
            "vision_reader_model": model}


def route(store: Any, github: LLMSettings, cfg: dict[str, dict[str, Any]], now: datetime | None = None,
          job: str = "reader", live: Any = None) -> LLMSettings:
    """LLMSettings with the fastest healthy text robot as the primary, the next OpenAI-dialect one as the backup, and the
    WHOLE ranked list in `chain` (llm.LLM walks it); the picture reader as ai_config decides it. With nothing measured the
    configured order stands, so a store that cannot be read changes nothing."""
    from . import ai_config
    base = ai_config.llm_settings(github, cfg)                 # the page's picture reader and vision model, as before
    details: dict[str, Any] = {}
    ranked = chain(store, github, cfg, now, job, live, details)
    skipped = details.get("skipped") or []
    if not ranked:
        # keep what ai_config made, minus a reader that cannot write text: llm.py then says why_off() honestly
        if skipped and host_of(base.base_url) == host_of(skipped[0]["base_url"]):
            base = dataclasses.replace(base, blocked=skipped[0]["blocked"])
        return base
    first = ranked[0]
    second = next((c for c in ranked[1:] if c["provider"] == "openai"), None)   # the backup speaks the OpenAI dialect only
    links = tuple({k: c.get(k) for k in ("slug", "provider", "base_url", "key", "model", "vision_model", "robot", "name")}
                  for c in ranked)
    change: dict[str, Any] = dict(provider=first["provider"], base_url=first["base_url"], api_key=first["key"],
                                  model=first["model"], blocked="",
                                  fallback_base_url=second["base_url"] if second else "",
                                  fallback_key=second["key"] if second else None,
                                  fallback_model=second["model"] if second else "", fallback_blocked="",
                                  chain=links)
    # the picture reader pinned on the API tab (Wan, 11 Nov 2026): that robot and model are asked first for a picture, with the
    # robot's own key at its own address; the rest of the chain still reads it when it gives nothing
    change.update(picture_reader_change(read_pins(store).get("image_reader"), ranked))
    # a writer that moved host or model reads pictures with its own model unless the page set a picture reader
    reader_set = base.vision_reader_model or change.get("vision_reader_model")
    if not reader_set and (host_of(first["base_url"]) != host_of(base.base_url) or first["model"] != base.model):
        change["vision_model"] = first["model"]
    pic = None
    if change.get("vision_reader_model"):
        pic = next((x for x in ranked if x["base_url"] == change.get("vision_base_url")), None)
    reader = (pic["slug"], pic["base_url"], change["vision_reader_model"]) if pic else None
    efforts = efforts_for(read_efforts(store), ranked, reader)
    if efforts:
        change["efforts"] = efforts
    log.info("AI team: %s (%s, %s) writes; the chain is %s", first["name"], first["slug"], first["model"],
             " > ".join(c["slug"] for c in ranked))
    return dataclasses.replace(base, **change)


def route_media(store: Any, s: MediaSettings, github: LLMSettings | None = None,
                cfg: dict[str, dict[str, Any]] | None = None) -> MediaSettings:
    """The picture maker: a pinned model for the image slot wins over the saved one. The provider is Tetapan's, except that a pin
    on ANOTHER OpenAI-dialect robot that holds a key here (Mireld, Wanshah 2: "add wanshah2, mireld" to the picture maker, 9 Nov
    2026) draws through that robot's own address and key, as a pair: a key never goes to a host it was not saved for."""
    pin = read_pins(store).get("image_gen") or {}
    if not pin.get("model"):
        return s
    if s.provider == "openai" and (not pin.get("gateway") or slug_of(s.openai_base_url) == pin["gateway"]):
        return dataclasses.replace(s, openai_image_model=pin["model"])
    if s.provider == "cloudflare" and pin.get("gateway") in ("", None, "cloudflare"):
        return dataclasses.replace(s, cloudflare_t2i_model=pin["model"])
    if s.provider == "replicate" and pin.get("gateway") in ("", None, "replicate"):
        return dataclasses.replace(s, replicate_t2i_model=pin["model"])
    gw = pin.get("gateway") or ""
    if gw and gw not in ("cloudflare", "replicate") and not (s.provider == "openai" and slug_of(s.openai_base_url) == gw):
        other = _picture_gateway(store, gw, github, cfg)
        if other:
            return dataclasses.replace(s, provider="openai", openai_base_url=other["base_url"], openai_key=other["key"],
                                       openai_image_model=pin["model"])
        log.info("picture maker pinned to %s, which has no key here: the saved provider stays", gw)
    return s


def _picture_gateway(store: Any, slug: str, github: LLMSettings | None,
                     cfg: dict[str, dict[str, Any]] | None) -> dict[str, str] | None:
    """{base_url, key} of an OpenAI-dialect robot a key exists for, or None. Never raises: no key is the saved provider."""
    try:
        from . import ai_config, ai_providers
        github = github or LLMSettings.load()
        cfg = cfg if cfg is not None else ai_config.read(store)
        for c in candidates(github, cfg, "reader", ai_providers.load(store)):
            host_blocked = bool(c.get("blocked")) and c["blocked"] != cannot_write_text(c["base_url"], c.get("model", ""))
            if c["slug"] == slug and c.get("key") and (c.get("provider") or "openai") == "openai" and not host_blocked:
                return {"base_url": c["base_url"], "key": c["key"]}
    except Exception as exc:  # noqa: BLE001 - the picture still gets drawn by the saved provider
        log.info("picture gateway %s not resolved (%s)", slug, str(exc)[:120])
    return None


def _read_state(store: Any) -> dict[str, Any]:
    try:
        old = store.table(db.SETTINGS).select("value").eq("key", STATE_KEY).execute().data or []
        return (old[0].get("value") or {}) if old else {}
    except Exception:  # noqa: BLE001 - no record is no memory
        return {}


def _record(store: Any, state: dict[str, Any]) -> None:
    try:
        old = store.table(db.SETTINGS).select("value").eq("key", STATE_KEY).execute().data or []
        value = {**((old[0].get("value") or {}) if old else {}), **state}
        store.table(db.SETTINGS).upsert({"key": STATE_KEY, "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - the record is for the page; the run goes on
        log.info("ai_team_state not written (%s)", str(exc)[:120])
