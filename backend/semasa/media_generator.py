"""Media generator. Entry point: `python -m semasa.media_generator` (see .github/workflows/media.yml).

Takes `pending` rows from media_generations, runs the provider the row names (or the
default), stores the result in bucket `semasa-generated`, and writes the public address back.
A failure is stored ON THE ROW (`error`), and the row goes back to `pending` until
`attempts` reaches MEDIA_MAX_ATTEMPTS — after that it is `error` and the page offers a
requeue. Nothing here ever deletes a row or a file.

MEDIA_ONLY_ID (from a repository_dispatch payload) narrows a run to one row.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import UTC, datetime
from typing import Any

from . import db
from .config import MediaSettings, SupabaseSettings
from .log import get_logger
from .providers import Generated, Provider, ProviderError

log = get_logger("semasa.media")


def make_provider(name: str, s: MediaSettings) -> Provider:
    if name == "replicate":
        from .providers.replicate import ReplicateProvider
        return ReplicateProvider(s)
    if name == "openai":
        from .providers.openai_images import OpenAIProvider
        return OpenAIProvider(s)
    raise ProviderError(f"unknown provider {name!r}")


def process_row(store: Any, row: dict[str, Any], s: MediaSettings, providers: dict[str, Provider]) -> bool:
    row_id = row["id"]
    kind = row.get("type") or "image"
    name = (row.get("provider") or s.provider).lower()
    options = dict((row.get("meta") or {}).get("options") or {})
    try:
        if name not in providers:
            providers[name] = make_provider(name, s)
        provider = providers[name]
        log.info("%s: %s via %s — %s", row_id, kind, name, (row.get("prompt") or "")[:80])
        gen: Generated = provider.generate(kind, row["reference_url"], row.get("prompt") or "", options)
        if not gen.data:
            raise ProviderError("provider returned no bytes")
        day = datetime.now(UTC).strftime("%Y/%m")
        path = f"{day}/{row_id}.{gen.extension}"
        url = db.upload_generated(store, path, gen.data, gen.content_type)
        meta = {**(row.get("meta") or {}), **gen.meta, "bytes": len(gen.data),
                "sha256": hashlib.sha256(gen.data).hexdigest(), "content_type": gen.content_type,
                "generated_path": path, "finished_at": datetime.now(UTC).isoformat()}
        db.finish_media(store, row_id, status="done", generated_media_url=url, provider=name, model=gen.model,
                        error=None, meta=meta)
        log.info("%s: done → %s (%d bytes)", row_id, url, len(gen.data))
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it; the run continues
        attempts = int(row.get("attempts") or 0)
        final = isinstance(exc, ProviderError) or attempts >= s.max_attempts
        status = "error" if final else "pending"
        msg = f"{type(exc).__name__}: {str(exc)[:600]}"
        log.error("%s: %s (attempt %d, → %s)", row_id, msg, attempts, status)
        db.finish_media(store, row_id, status=status, error=msg, provider=name)
        return False


def main() -> int:
    s = MediaSettings.load()
    store = db.client(SupabaseSettings.load())
    only_id = (os.environ.get("MEDIA_ONLY_ID") or "").strip() or None
    rows = db.claim_pending(store, s.batch, only_id)
    if not rows:
        log.info("nothing pending")
        return 0
    providers: dict[str, Provider] = {}
    done = sum(process_row(store, r, s, providers) for r in rows)
    log.info("%d/%d generated", done, len(rows))
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(f"## Semasa media\n\n{done}/{len(rows)} jobs generated (default provider {s.provider})\n")
    return 0 if done == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
