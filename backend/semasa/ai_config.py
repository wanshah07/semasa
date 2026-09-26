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


def describe(cfg: dict[str, dict[str, Any]]) -> str:
    """One line for the run log: which slots came from the page (never a key)."""
    if not cfg:
        return "AI settings: GitHub only"
    parts = [f"{slot}={r.get('provider') or '-'}:{r.get('model') or '-'}{' +key' if r.get('api_key') else ''}"
             for slot, r in sorted(cfg.items())]
    return "AI settings from the page: " + ", ".join(parts)
