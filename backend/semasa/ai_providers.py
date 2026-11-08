"""Extra AI providers Wan adds from the API tab (supabase/074): an Anthropic key, a second KiosAPI key, any OpenAI-compatible
gateway. Each enabled one is a robot the whole backend can use, numbered after the built-in five: Wanshah 6, 7, ...

  * the ROUTER (ai_team.py) appends each enabled provider as a candidate for the jobs its `jobs` list allows, with its dialect
    carried as `provider` so llm.py speaks Anthropic to an Anthropic endpoint (llm._anthropic) and OpenAI to everything else;
  * the PROBE (api_status.py) asks every enabled provider its models and a five-token question and writes one semasa_api_status
    row per provider slug, role "provider", so the API tab and Telegram's /robot show it like any robot;
  * Telegram's /robot may pin one (telegram_tools.pinnable), the same pin the API page writes.

The key is read with the service role from semasa_ai_provider_secrets and goes ONLY to the host it was saved for (key_host, the
rule ai_config._key keeps for the AI slots). A provider whose key is missing or bound to another host is not a robot at all.
"""

from __future__ import annotations

from typing import Any

from .log import get_logger

log = get_logger("semasa.ai_providers")

TABLE = "semasa_ai_providers"
SECRETS = "semasa_ai_provider_secrets"
RESERVED = ("rootsys", "mireld", "kiosapi", "gemini", "chatgpt")       # the built-in robots: W1..W5
JOBS = ("chat", "reader", "ideas", "motion", "telegram")     # chat, telegram: the edge functions; null/empty = every job
FIRST_ROBOT = 6                                                        # the first provider is Wanshah 6
ROLE = "provider"                                                      # semasa_api_status.role for a provider's row


def load(store: Any) -> list[dict[str, Any]]:
    """Every provider row with its api_key (service role only), oldest first. [] when 074 is not applied or the read fails."""
    try:
        rows = store.table(TABLE).select("*").execute().data or []
        keys = store.table(SECRETS).select("id,api_key").execute().data or []
    except Exception as exc:  # noqa: BLE001 - no providers is the team as it was
        log.info("AI providers not read (%s)", str(exc)[:120])
        return []
    secret = {k.get("id"): k.get("api_key") for k in keys}
    out = [{**r, "api_key": secret.get(r["id"])} for r in rows if r.get("id") and r["id"] not in RESERVED]
    out.sort(key=lambda r: (str(r.get("created_at") or ""), r["id"]))
    return out


def key_of(row: dict[str, Any]) -> str | None:
    """The provider's key, only where it belongs (ai_config._key: the key_host the database bound it to must be this host)."""
    from . import ai_config
    base = (row.get("base_url") or "").rstrip("/")
    if not base:
        return None
    return ai_config._key(row, f"provider:{row.get('id')}", row.get("dialect") or "openai", base)


def enabled(store: Any, rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The providers that are robots now: switched on, with a key that belongs to their host. Each carries `key` and `robot`."""
    out = []
    for n, r in enumerate(load(store) if rows is None else rows):
        if not r.get("enabled", True):
            continue
        key = key_of(r)
        if not key:
            continue
        out.append({**r, "key": key, "base_url": r["base_url"].rstrip("/"), "provider": r.get("dialect") or "openai",
                    "robot": f"W{FIRST_ROBOT + n}"})
    return out


def robots(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """{slug: {robot, name, tone, does}} for the ai_team.ROBOTS shape, numbered W6.. in creation order (every row, on or off,
    so a switched-off provider keeps its number)."""
    out: dict[str, dict[str, Any]] = {}
    for n, r in enumerate(rows):
        out[r["id"]] = {"robot": f"W{FIRST_ROBOT + n}", "name": r.get("name") or r["id"], "tone": "provider",
                        "does": ["read", "write"], "added": True}
    return out


def candidates(store: Any, job: str, rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The ai_team candidates for `job`: every enabled provider whose jobs name it. `blocked` says when its model paints."""
    from . import ai_team
    robots_by = robots(load(store) if rows is None else rows)
    out = []
    for r in enabled(store, rows):
        if r.get("jobs") and job not in r["jobs"]:          # null or an empty list means every job (the edge functions' rule)
            continue
        model = r.get("model") or ""
        out.append({"source": "provider", "slug": r["id"], "provider": r["provider"], "base_url": r["base_url"],
                    "key": r["key"], "model": model, "blocked": ai_team.cannot_write_text(r["base_url"], model),
                    **robots_by.get(r["id"], {"robot": r["robot"], "name": r.get("name") or r["id"], "tone": "provider",
                                              "does": ["read", "write"]})})
    return out


def gateways(store: Any, rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """The probe's view: one gateway per enabled provider, role "provider", the key only to its own host."""
    return [{"slug": r["id"], "name": r.get("name") or r["id"], "role": ROLE, "base_url": r["base_url"], "key": r["key"],
             "model": r.get("model") or "", "provider": r["provider"], "blocked": ""} for r in enabled(store, rows)]


def slugs(store: Any) -> tuple[str, ...]:
    """The enabled providers' slugs (for Telegram's pin buttons)."""
    return tuple(r["id"] for r in enabled(store))
