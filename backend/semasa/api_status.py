"""API gateway status: are rootsys (Afiq's) and Mireld up, is each key accepted, which models does each list, how many
tokens have we spent (Wan, 9 Oct 2026: "track status of token from mireld and afiq API including their models").

Two halves:
  1. the PROBE (run by .github/workflows/api.yml every 6 hours, and on demand): for every gateway the workers are configured
     with (the primary writer, the backup, and the page's own reader slot when it points elsewhere) GET /models with its key,
     ask the configured model a five-token question, try the balance endpoints an OpenAI-compatible gateway may expose, and
     write one semasa_api_status row (supabase/035_repos_api.sql). A key goes only to its own host, as everywhere else.
  2. the USAGE SINK: `attach(store, area)` hands llm.py a function that writes one semasa_api_usage row per AI call the
     run makes (gateway, model, tokens, ms, ok). Every runner that builds an LLM calls attach first; the page sums the rows
     by day and gateway. A gateway that reports no `usage` gets a row with zero tokens, so the call is still counted.

Nothing here changes which writer answers: llm.py decides that. This only watches.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from . import ai_config, db
from . import llm as llm_mod
from .config import LLMSettings, host_of

log = logging.getLogger("semasa.api_status")
SETTINGS_KEY = "api_probe"
NAMES = {
    "rootsys.cloud": ("rootsys", "rootsys (Afiq)"),
    "api.mireld.my": ("mireld", "Mireld"),
    "api.openai.com": ("openai", "OpenAI"),
    "api.anthropic.com": ("anthropic", "Anthropic"),
}
BALANCE_PATHS = (
    "/dashboard/billing/credit_grants",
    "/dashboard/billing/subscription",
    "/credits",
    "/balance",
    "/user/balance",
    "/usage",
    "/key",
)


def slug_of(base_url: str) -> tuple[str, str]:
    host = host_of(base_url).lower()
    if host in NAMES:
        return NAMES[host]
    return host.replace(".", "-") or "unknown", host or "unknown"


def gateways(s: LLMSettings) -> list[dict[str, Any]]:
    """The gateways the workers are configured with, each once: primary, backup, and a page reader on another host."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(role: str, base: str, key: str | None, model: str, provider: str = "openai") -> None:
        if not base:
            return
        slug, name = slug_of(base)
        if slug in seen:
            return
        seen.add(slug)
        out.append(
            {
                "slug": slug,
                "name": name,
                "role": role,
                "base_url": base.rstrip("/"),
                "key": key or "",
                "model": model or "",
                "provider": provider,
            }
        )

    add("primary", s.base_url, s.api_key, s.model, s.provider)
    if getattr(s, "fallback_base_url", "") and getattr(s, "fallback_key", None):
        add("backup", s.fallback_base_url, s.fallback_key, getattr(s, "fallback_model", ""))
    if getattr(s, "vision_base_url", "") and getattr(s, "vision_key", None):
        add("reader", s.vision_base_url, s.vision_key, getattr(s, "vision_reader_model", ""))
    return out


def _models(gw: dict[str, Any], timeout: int) -> tuple[list[str], int | None, int | None, str]:
    """(models, http, latency_ms, error). Anthropic lists under /v1/models with x-api-key; OpenAI dialect under /models."""
    t0 = time.monotonic()
    try:
        if gw["provider"] == "anthropic":
            r = requests.get(
                f"{gw['base_url']}/v1/models",
                headers={"x-api-key": gw["key"], "anthropic-version": "2023-06-01"},
                timeout=timeout,
            )
        else:
            r = requests.get(f"{gw['base_url']}/models", headers={"Authorization": f"Bearer {gw['key']}"}, timeout=timeout)
    except requests.RequestException as exc:
        return [], None, None, str(exc)[:200]
    ms = int((time.monotonic() - t0) * 1000)
    if r.status_code >= 400:
        return [], r.status_code, ms, r.text[:200]
    try:
        data = r.json()
        items = data.get("data") if isinstance(data, dict) else data
        ids = sorted({str(m.get("id") if isinstance(m, dict) else m) for m in (items or []) if m})
        return ids[:300], r.status_code, ms, ""
    except ValueError:
        return [], r.status_code, ms, "not JSON"


def _chat(gw: dict[str, Any], timeout: int) -> tuple[bool, int | None, dict[str, int], str]:
    """A five-token question to the configured model: (ok, ms, usage, error)."""
    if not gw.get("model"):
        return False, None, {}, "no model configured"
    t0 = time.monotonic()
    try:
        if gw["provider"] == "anthropic":
            r = requests.post(
                f"{gw['base_url']}/v1/messages",
                headers={"x-api-key": gw["key"], "anthropic-version": "2023-06-01"},
                json={"model": gw["model"], "max_tokens": 5, "messages": [{"role": "user", "content": "Say OK"}]},
                timeout=timeout,
            )
        else:
            r = requests.post(
                f"{gw['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {gw['key']}"},
                json={"model": gw["model"], "max_tokens": 5, "messages": [{"role": "user", "content": "Say OK"}]},
                timeout=timeout,
            )
    except requests.RequestException as exc:
        return False, None, {}, str(exc)[:200]
    ms = int((time.monotonic() - t0) * 1000)
    if r.status_code >= 400:
        return False, ms, {}, f"{r.status_code} {r.text[:160]}"
    try:
        return True, ms, usage_of(r.json()), ""
    except ValueError:
        return False, ms, {}, "not JSON"


def usage_of(j: Any) -> dict[str, int]:
    """{prompt_tokens, completion_tokens, total_tokens} from either dialect's answer; zeros when it says nothing."""
    u = (j or {}).get("usage") if isinstance(j, dict) else None
    if not isinstance(u, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    p = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
    c = int(u.get("completion_tokens") or u.get("output_tokens") or 0)
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": int(u.get("total_tokens") or (p + c))}


def _balance(gw: dict[str, Any], timeout: int) -> dict[str, Any]:
    """Whatever balance endpoint answers JSON with a number in it, else {}. Gateways differ; none is assumed."""
    if gw["provider"] == "anthropic":
        return {}
    for path in BALANCE_PATHS:
        try:
            r = requests.get(
                f"{gw['base_url']}{path}", headers={"Authorization": f"Bearer {gw['key']}"}, timeout=min(timeout, 15)
            )
        except requests.RequestException:
            continue
        if r.status_code != 200:
            continue
        try:
            j = r.json()
        except ValueError:
            continue
        if isinstance(j, dict) and any(isinstance(v, (int, float)) for v in j.values()):
            return {"path": path, **{k: v for k, v in j.items() if isinstance(v, (int, float, str)) and len(str(v)) < 80}}
    return {}


def probe(gw: dict[str, Any], timeout: int = 30) -> dict[str, Any]:
    row: dict[str, Any] = {
        "slug": gw["slug"],
        "name": gw["name"],
        "role": gw["role"],
        "base_url": gw["base_url"],
        "key_set": bool(gw["key"]),
        "key_last4": gw["key"][-4:] if gw["key"] else "",
        "model": gw["model"],
        "checked_at": datetime.now(UTC).isoformat(),
        "models": [],
        "balance": {},
        "error": "",
    }
    if not gw["key"]:
        row.update(reachable=False, key_ok=None, error="no key set")
        return row
    models, http, ms, err = _models(gw, timeout)
    row.update(
        http=http,
        latency_ms=ms,
        models=models,
        reachable=http is not None,
        key_ok=None if http is None else http not in (401, 403),
        error=err,
    )
    row["model_listed"] = (gw["model"] in models) if models and gw["model"] else None
    chat_ok, chat_ms, _usage, chat_err = _chat(gw, timeout)
    row.update(chat_ok=chat_ok, chat_ms=chat_ms)
    if chat_err and not row["error"]:
        row["error"] = chat_err
    if chat_ok:
        row["key_ok"] = True
    row["balance"] = _balance(gw, timeout) if row["key_ok"] else {}
    return row


def run(store: Any, settings: LLMSettings, timeout: int = 30) -> list[dict[str, Any]]:
    rows = []
    for gw in gateways(settings):
        row = probe(gw, timeout)
        rows.append(row)
        store.table(db.API_STATUS).upsert(row, on_conflict="slug").execute()
        if row.get("chat_ok"):
            store.table(db.API_USAGE).insert(
                {
                    "gateway": row["slug"],
                    "model": row["model"],
                    "area": "probe",
                    "ms": row.get("chat_ms") or 0,
                    "ok": True,
                    **{k: 0 for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
                }
            ).execute()
        log.info(
            "%s: reachable=%s key_ok=%s models=%d chat_ok=%s %s",
            row["name"],
            row.get("reachable"),
            row.get("key_ok"),
            len(row["models"]),
            row.get("chat_ok"),
            row.get("error") or "",
        )
    bad = [r for r in rows if not r.get("chat_ok")]
    db.log_event(
        store,
        "warn" if bad else "info",
        "api",
        "api_probe",
        "API: " + ", ".join(f"{r['name']} {'OK' if r.get('chat_ok') else 'GAGAL'}" for r in rows)
        if rows
        else "API: tiada gateway dikonfigurasi",
        detail={
            r["slug"]: {"chat_ok": r.get("chat_ok"), "models": len(r["models"]), "error": r.get("error") or ""} for r in rows
        },
    )
    prune(store)
    return rows


def prune(store: Any, now: datetime | None = None) -> None:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    keep = int(((rows[0].get("value") or {}) if rows else {}).get("keep_days") or 90)
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=keep)).isoformat()
    try:
        store.table(db.API_USAGE).delete().lt("created_at", cutoff).execute()
    except Exception as exc:  # noqa: BLE001 - pruning never fails a probe
        log.info("usage not pruned: %s", str(exc)[:120])


def attach(store: Any, area: str) -> None:
    """Make every AI call this run makes write a semasa_api_usage row. Never raises, never slows a call that failed."""

    def sink(rec: dict[str, Any]) -> None:
        try:
            slug, _name = slug_of(rec.get("base") or "")
            store.table(db.API_USAGE).insert(
                {
                    "gateway": slug,
                    "model": rec.get("model") or "",
                    "area": area,
                    "prompt_tokens": int(rec.get("prompt_tokens") or 0),
                    "completion_tokens": int(rec.get("completion_tokens") or 0),
                    "total_tokens": int(rec.get("total_tokens") or 0),
                    "ms": int(rec.get("ms") or 0),
                    "ok": bool(rec.get("ok")),
                    "error": str(rec.get("error") or "")[:200],
                }
            ).execute()
        except Exception as exc:  # noqa: BLE001 - the record is the lesser thing
            log.info("usage row not written: %s", str(exc)[:120])

    llm_mod.set_usage_sink(sink)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = db.client()
    settings = ai_config.llm_settings(LLMSettings.load(), ai_config.read(store))
    rows = run(store, settings, timeout=int(os.environ.get("LLM_TIMEOUT") or 30))
    for r in rows:
        print(
            f"{r['name']}: reachable={r.get('reachable')} key_ok={r.get('key_ok')} chat_ok={r.get('chat_ok')} "
            f"models={len(r['models'])} model_listed={r.get('model_listed')} {r.get('error') or ''}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
