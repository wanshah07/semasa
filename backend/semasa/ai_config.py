"""The AI settings Wan sets in the page (supabase/016_ai_settings.sql), laid over the GitHub secrets and variables.

Wan, 27 Sep 2026: "can add in setting reader, image generation, image reader key and endpoint".

Three slots:
  reader        the text model that reads the news and writes: LLM_PROVIDER / LLM_BASE_URL / LLM_MODEL / LLM_API_KEY
  image_gen     the picture maker: MEDIA_PROVIDER and that provider's account, key and models
  image_reader  the model that READS a picture (a reference, a label check); before this it was always the writer's
                own endpoint with VISION_MODEL, so a text-only writer meant no picture was ever read

An empty slot or an empty field keeps what GitHub says, so nothing changes until Wan saves something. A key from the
page is used ONLY at the host it was entered for (key_host, set by the database): the same rule the writer's
allowed-hosts list keeps for the GitHub key. If the settings cannot be read, the run goes on with GitHub's.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from .config import LLMSettings, MediaSettings, blocked_host, host_of
from .log import get_logger

log = get_logger("semasa.ai_config")

CONFIG = "semasa_ai_config"
SECRETS = "semasa_ai_secrets"


def read(store: Any) -> dict[str, dict[str, Any]]:
    """{slot: row with its api_key}, or {} when the tables are not there yet (016 not run) or cannot be read."""
    try:
        rows = store.table(CONFIG).select("*").execute().data or []
        keys = store.table(SECRETS).select("slot,api_key").execute().data or []
    except Exception as exc:  # noqa: BLE001 - the GitHub settings still work
        log.info("AI settings from the page not read (%s); the GitHub settings are used", str(exc)[:160])
        return {}
    secret = {k.get("slot"): k.get("api_key") for k in keys}
    return {r["slot"]: {**r, "api_key": secret.get(r["slot"])} for r in rows if r.get("slot")}


def key_host(slot: str, provider: str | None, base_url: str | None) -> str:
    """The same rule as semasa_ai_key_host() in 016: where a key for this slot may go."""
    if slot == "image_gen" and provider == "replicate":
        return "api.replicate.com"
    if slot == "image_gen" and provider == "cloudflare":
        return f"cloudflare:{base_url.lower()}" if base_url else ""
    return host_of(base_url).lower() if (base_url or "").startswith("https://") else ""


def _key(row: dict[str, Any], slot: str, provider: str, base: str | None) -> str | None:
    """The page's key, only where it belongs."""
    key = row.get("api_key")
    if not key:
        return None
    host = key_host(slot, provider, base)
    if not host or host != (row.get("key_host") or ""):
        log.warning("%s: the key saved in the page belongs to %s, not %s; it is not used", slot,
                    row.get("key_host") or "nothing", host or "this endpoint")
        return None
    return key


def llm_settings(s: LLMSettings, cfg: dict[str, dict[str, Any]]) -> LLMSettings:
    change: dict[str, Any] = {}
    r = cfg.get("reader")
    if r:
        provider = r.get("provider") or s.provider
        base = (r.get("base_url") or s.base_url).rstrip("/")
        key = _key(r, "reader", provider, base)
        change.update(provider=provider, base_url=base)
        if r.get("model"):
            change["model"] = r["model"]
        if key:
            change.update(api_key=key, blocked="")           # Wan gave this key FOR this endpoint
        elif host_of(base) != host_of(s.base_url):
            # a new endpoint with no key of its own: the GitHub key may go there only if the host is allowed
            change["blocked"] = blocked_host(base)
        # The picture step asks the writer's endpoint for vision_model. Moving the reader to another host or model left
        # that at GitHub's VISION_MODEL, a model the new host does not have, so every picture read failed. The reader's
        # own model reads pictures unless the image-reader slot names one (below).
        if host_of(base) != host_of(s.base_url) or (r.get("model") and r["model"] != s.model):
            change["vision_model"] = r.get("model") or s.model
    v = cfg.get("image_reader")
    if v:
        provider = v.get("provider") or "openai"
        base = (v.get("base_url") or "").rstrip("/")
        key = _key(v, "image_reader", provider, base) if base else None
        if key and v.get("model"):
            change.update(vision_provider=provider, vision_base_url=base, vision_key=key,
                          vision_reader_model=v["model"])
        elif v.get("model"):
            change["vision_model"] = v["model"]                # the writer's endpoint, another model
    return dataclasses.replace(s, **change) if change else s


def media_settings(s: MediaSettings, cfg: dict[str, dict[str, Any]]) -> MediaSettings:
    r = cfg.get("image_gen")
    if not r:
        return s
    provider = r.get("provider") or s.provider
    change: dict[str, Any] = {"provider": provider}
    if provider == "cloudflare":
        account = r.get("base_url") or s.cloudflare_account_id
        change["cloudflare_account_id"] = account
        key = _key(r, "image_gen", provider, account)
        if key:
            change["cloudflare_token"] = key
        if r.get("model"):
            change["cloudflare_t2i_model"] = r["model"]
        if r.get("edit_model"):
            change["cloudflare_edit_model"] = r["edit_model"]
    elif provider == "openai":
        base = (r.get("base_url") or s.openai_base_url).rstrip("/")
        change["openai_base_url"] = base
        key = _key(r, "image_gen", provider, base)
        if key:
            change["openai_key"] = key
        elif host_of(base) != host_of(s.openai_base_url):
            change["openai_key"] = None                        # the GitHub key never follows to another host
        if r.get("model"):
            change["openai_image_model"] = r["model"]
    elif provider == "replicate":
        key = _key(r, "image_gen", provider, None)
        if key:
            change["replicate_token"] = key
        if r.get("model"):
            change["replicate_t2i_model"] = r["model"]
        if r.get("edit_model"):
            change["replicate_image_model"] = r["edit_model"]
    return dataclasses.replace(s, **change)


# --- what GitHub says, for the page ------------------------------------------------------------------------------
# Wan, 27 Sep 2026: "can this part display what in github secret". A GitHub secret can never be read back, by the page
# or by anyone, so each run writes down what IT loaded from GitHub before the page's own settings were laid over it:
# providers, endpoints and models in full (they are Variables, not secrets), and for a key only whether it is set and
# its last 4 characters, the same rule the page keeps for its own keys. One settings row per workflow, because
# scrape.yml and media.yml are handed different secrets.
GITHUB_KEY = {"scrape": "ai_github_scrape", "media": "ai_github_media"}


def key_hint(key: str | None) -> str | None:
    """"…abcd" for a key long enough that 4 characters give nothing away, "set" for a short one, None when unset."""
    if not key:
        return None
    return "…" + key[-4:] if len(key) >= 12 else "set"


def github_snapshot(llm: LLMSettings, media: MediaSettings | None = None) -> dict[str, Any]:
    """What this run loaded from GitHub, with every secret reduced to key_hint. Never a key, never an account ID."""
    snap: dict[str, Any] = {
        "reader": {
            "provider": llm.provider, "base_url": llm.base_url, "model": llm.model,
            "key": key_hint(llm.api_key), "blocked": llm.blocked or None,
            "fallback": {"base_url": llm.fallback_base_url or None, "model": llm.fallback_model or None,
                         "key": key_hint(llm.fallback_key), "blocked": llm.fallback_blocked or None},
        },
        "image_reader": {"provider": llm.provider, "base_url": llm.base_url, "model": llm.vision_model,
                         "key": key_hint(llm.api_key), "note": "the writer's own endpoint (VISION_MODEL)"},
    }
    if media is not None:
        m = media
        snap["image_gen"] = {
            "provider": m.provider,
            "cloudflare": {"account": key_hint(m.cloudflare_account_id), "key": key_hint(m.cloudflare_token),
                           "model": m.cloudflare_t2i_model, "edit_model": m.cloudflare_edit_model,
                           "size": m.cloudflare_size},
            "openai": {"base_url": m.openai_base_url, "key": key_hint(m.openai_key), "model": m.openai_image_model},
            "replicate": {"key": key_hint(m.replicate_token), "model": m.replicate_t2i_model,
                          "edit_model": m.replicate_image_model},
        }
    return snap


def record_github(store: Any, workflow: str, llm: LLMSettings, media: MediaSettings | None = None) -> None:
    """Save this run's GitHub snapshot for the Settings tab. A failure here never stops the run."""
    import os
    from datetime import UTC, datetime
    value = {**github_snapshot(llm, media), "at": datetime.now(UTC).isoformat(),
             "run": os.environ.get("GITHUB_RUN_ID") or None}
    try:
        store.table("semasa_settings").upsert({"key": GITHUB_KEY[workflow], "value": value},
                                              on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - only the page's display depends on it
        log.info("GitHub AI settings not recorded for the page (%s)", str(exc)[:160])


def describe(cfg: dict[str, dict[str, Any]]) -> str:
    """One line for the run log: which slots came from the page (never a key)."""
    if not cfg:
        return "AI settings: GitHub only"
    parts = [f"{slot}={r.get('provider') or '-'}:{r.get('model') or '-'}{' +key' if r.get('api_key') else ''}"
             for slot, r in sorted(cfg.items())]
    return "AI settings from the page: " + ", ".join(parts)
