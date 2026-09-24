"""Supabase access for the runners. Service-role only — this module never runs in a browser."""

from __future__ import annotations

import hashlib
from typing import Any

from supabase import Client, create_client

from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.db")

TRENDS = "isu_semasa_trends"
MEDIA = "media_generations"
RUNS = "scrape_runs"


def client(settings: SupabaseSettings | None = None) -> Client:
    s = settings or SupabaseSettings.load()
    return create_client(s.url, s.service_role_key)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- trends ------------------------------------------------------------------

def existing_urls(db: Client, urls: list[str]) -> set[str]:
    """Which of these URLs are already stored. Chunked: PostgREST `in` filters have a URL-length limit."""
    found: set[str] = set()
    for i in range(0, len(urls), 100):
        chunk = urls[i : i + 100]
        res = db.table(TRENDS).select("url").in_("url", chunk).execute()
        found.update(row["url"] for row in (res.data or []))
    return found


def upsert_trends(db: Client, rows: list[dict[str, Any]]) -> int:
    """Insert new headlines; a URL already present is left exactly as it was
    (`ignore_duplicates`), so a re-run never overwrites an LLM summary with a rules one."""
    if not rows:
        return 0
    written = 0
    for i in range(0, len(rows), 200):
        chunk = rows[i : i + 200]
        res = db.table(TRENDS).upsert(chunk, on_conflict="url", ignore_duplicates=True).execute()
        written += len(res.data or [])
    return written


def start_run(db: Client, git_sha: str | None) -> str | None:
    try:
        res = db.table(RUNS).insert({"git_sha": git_sha}).execute()
        return res.data[0]["id"]
    except Exception as exc:  # a missing runs table must not stop the scrape
        log.warning("could not open scrape_runs row: %s", exc)
        return None


def finish_run(db: Client, run_id: str | None, **fields: Any) -> None:
    if not run_id:
        return
    try:
        db.table(RUNS).update({"finished_at": "now()", **fields}).eq("id", run_id).execute()
    except Exception as exc:
        log.warning("could not close scrape_runs row: %s", exc)


# --- media ---------------------------------------------------------------------

def claim_pending(db: Client, limit: int, only_id: str | None = None) -> list[dict[str, Any]]:
    """Take `pending` rows, oldest first, and mark them `processing` one by one.

    The update is conditional on the row still reading `pending`, so two runners
    started seconds apart (a dispatch and the poll) cannot both take the same job.
    """
    q = db.table(MEDIA).select("*").eq("status", "pending").order("created_at").limit(limit)
    if only_id:
        q = q.eq("id", only_id)
    rows = q.execute().data or []
    claimed: list[dict[str, Any]] = []
    for row in rows:
        res = (
            db.table(MEDIA)
            .update({"status": "processing", "attempts": int(row.get("attempts") or 0) + 1, "error": None})
            .eq("id", row["id"])
            .eq("status", "pending")
            .execute()
        )
        if res.data:
            claimed.append(res.data[0])
    return claimed


def finish_media(db: Client, row_id: str, **fields: Any) -> None:
    db.table(MEDIA).update(fields).eq("id", row_id).execute()


def upload_generated(db: Client, path: str, data: bytes, content_type: str) -> str:
    """Put the bytes in bucket `generated` and return the public address."""
    bucket = db.storage.from_("generated")
    bucket.upload(path, data, {"content-type": content_type, "upsert": "true"})
    return bucket.get_public_url(path)
