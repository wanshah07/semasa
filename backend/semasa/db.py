"""Supabase access for the runners. Service-role only — this module never runs in a browser."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from supabase import Client, create_client

from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.db")

TRENDS = "isu_semasa_trends"
MEDIA = "media_generations"
RUNS = "scrape_runs"
IDEAS = "semasa_ideas"
POSTS = "semasa_posts"
SETTINGS = "semasa_settings"
PUBLISH_LOG = "semasa_publish_log"
GENERATED_BUCKET = "semasa-generated"


def client(settings: SupabaseSettings | None = None) -> Client:
    s = settings or SupabaseSettings.load()
    return create_client(s.url, s.service_role_key)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --- trends ------------------------------------------------------------------

# An `in.(…)` filter travels in the request URL. 100 Google News links came to about
# 45,000 characters and the gateway answered 400 (scrape run 36026074962), so batches
# are sized by what is actually sent, not by count.
IN_FILTER_BUDGET = 6000


def _in_filter_chunks(values: Iterable[str], budget: int = IN_FILTER_BUDGET) -> Iterator[list[str]]:
    """Split values so each `in.(…)` stays under `budget` URL-encoded characters.
    Mirrors the client's own quoting (values holding , : ( ) are wrapped in quotes).
    A single value longer than the budget travels alone rather than being dropped."""
    chunk: list[str] = []
    size = 0
    for value in values:
        token = f'"{value}"' if any(c in value for c in ",:()") else value
        cost = len(quote(token, safe="")) + 3  # + the encoded comma between values
        if chunk and size + cost > budget:
            yield chunk
            chunk, size = [], 0
        chunk.append(value)
        size += cost
    if chunk:
        yield chunk


def existing_urls(db: Client, urls: list[str]) -> set[str]:
    """Which of these URLs are already stored.

    This lookup only saves LLM calls on headlines we already have. If a batch fails,
    those URLs are treated as new: the upsert (`ignore_duplicates`) still refuses to
    store them twice, so the cost of a failure is a few extra summaries, never a crash.
    """
    found: set[str] = set()
    failed = 0
    for chunk in _in_filter_chunks(urls):
        try:
            res = db.table(TRENDS).select("url").in_("url", chunk).execute()
            found.update(row["url"] for row in (res.data or []))
        except Exception as exc:  # noqa: BLE001 - see docstring
            failed += 1
            log.warning("existing_urls: batch of %d failed (%s); treating them as new", len(chunk), str(exc)[:200])
    if failed:
        log.warning("existing_urls: %d batch(es) failed; duplicates are still refused by the upsert", failed)
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


def prune_older_than(db: Client, cutoff_iso: str) -> None:
    """Delete headlines and run rows created before `cutoff_iso`. Never touches media."""
    for table in (TRENDS, RUNS):
        column = "created_at" if table == TRENDS else "started_at"
        try:
            db.table(table).delete().lt(column, cutoff_iso).execute()
        except Exception as exc:  # retention must never fail the scrape
            log.warning("could not prune %s: %s", table, exc)


def drop_unpicked(db: Client, shown_cutoff_iso: str, refetch_cutoff_iso: str) -> int:
    """Delete headlines nobody turned into an idea (Wan, 25 Sep 2026: "the news will be drop if
    not select within 48 hours"). The page already stops SHOWING a headline 48 hours after it
    arrived; this removes the row, but only when the scraper can never bring it back:
      * created before `shown_cutoff_iso` (out of the page's window), and
      * the feed dated it before `refetch_cutoff_iso` (SCRAPE_MAX_AGE_HOURS), so the age filter
        refuses it on every later run. An UNDATED headline would come back as "new" the moment
        its row was gone, so it stays (hidden) until the normal retention; the row is its memory.
    A picked headline stays too; the idea keeps its own copy either way. Never raises."""
    try:
        picked = {r["trend_id"] for r in (db.table(IDEAS).select("trend_id").not_.is_("trend_id", "null")
                                          .execute().data or []) if r.get("trend_id")}
        try:   # a headline made into a FAQ is picked too (the table arrives with 007_faq.sql)
            picked |= {r["trend_id"] for r in (db.table("semasa_faqs").select("trend_id").not_.is_("trend_id", "null")
                                               .execute().data or []) if r.get("trend_id")}
        except Exception as exc:
            log.info("no FAQ table to consult yet (%s)", str(exc)[:80])
        old = (db.table(TRENDS).select("id").lt("created_at", shown_cutoff_iso)
               .lt("published_at", refetch_cutoff_iso).limit(5000).execute().data or [])
        doomed = [r["id"] for r in old if r["id"] not in picked]
        for chunk in _in_filter_chunks(doomed):
            db.table(TRENDS).delete().in_("id", chunk).execute()
        if doomed:
            log.info("dropped %d headline(s) nobody picked", len(doomed))
        return len(doomed)
    except Exception as exc:
        log.warning("could not drop unpicked headlines: %s", exc)
        return 0


LOG = "semasa_log"
LOG_KEEP_DAYS = 90


def log_event(db: Client, level: str, area: str, event: str, title: str, *, ref_table: str | None = None,
              ref_id: str | None = None, detail: dict[str, Any] | None = None) -> None:
    """One row in the log (supabase/008_log.sql) for what no table change records by itself: candidates
    gathered, headlines dropped, a sheet written. Same shape as the triggers' rows. Never raises."""
    try:
        db.table(LOG).insert({"level": level, "area": area, "event": event, "title": title[:300],
                              "ref_table": ref_table, "ref_id": ref_id, "detail": detail or {}}).execute()
    except Exception as exc:
        log.info("log not written (%s): %s", event, str(exc)[:120])


def prune_log(db: Client, now: datetime | None = None) -> None:
    cutoff = ((now or datetime.now(UTC)) - timedelta(days=LOG_KEEP_DAYS)).isoformat()
    try:
        db.table(LOG).delete().lt("at", cutoff).execute()
    except Exception as exc:
        log.info("log not pruned: %s", str(exc)[:120])


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


def recover_stale_media(db: Client, stale_minutes: int) -> int:
    """A runner that dies (timeout, cancelled, lost) leaves its rows `processing` for ever:
    nothing else would ever take them, and the page shows a spinner that never stops. Put
    them back in the queue; `attempts` already counts the lost try, so a job that keeps
    killing its runner still ends in `error` at MEDIA_MAX_ATTEMPTS."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=stale_minutes)).isoformat()
    try:
        res = (db.table(MEDIA).update({"status": "pending", "error": "runner stopped before finishing; queued again"})
               .eq("status", "processing").lt("updated_at", cutoff).execute())
        n = len(res.data or [])
        if n:
            log.warning("put %d stuck media job(s) back in the queue", n)
        return n
    except Exception as exc:  # recovery must never stop the run
        log.warning("could not recover stuck media jobs: %s", exc)
        return 0


def attach_media_to_draft(db: Client, post_id: str, media_id: str) -> None:
    """Add a finished picture to its post, but only while the post is a DRAFT: adding a
    picture to an approved post would publish something Wan never saw (the page-side gate
    trigger does not run for the service key, so this check is the gate here)."""
    try:
        rows = db.table(POSTS).select("id,status,media_ids").eq("id", post_id).limit(1).execute().data or []
        if not rows or rows[0]["status"] != "draft":
            return
        ids = list(rows[0].get("media_ids") or [])
        if media_id in ids:
            return
        db.table(POSTS).update({"media_ids": ids + [media_id]}).eq("id", post_id).eq("status", "draft").execute()
    except Exception as exc:
        log.warning("could not attach media %s to post %s: %s", media_id, post_id, exc)


def attach_slides_to_draft(db: Client, post_id: str, media_id: str) -> None:
    """A new slide render REPLACES the post's earlier slide set (one carousel per post) in the
    same place in the order; drafts only, for the same reason as attach_media_to_draft."""
    try:
        rows = db.table(POSTS).select("id,status,media_ids").eq("id", post_id).limit(1).execute().data or []
        if not rows or rows[0]["status"] != "draft":
            return
        ids = list(rows[0].get("media_ids") or [])
        if media_id in ids:
            return
        old: set[str] = set()
        if ids:
            got = db.table(MEDIA).select("id,mode").in_("id", ids).execute().data or []
            old = {r["id"] for r in got if r.get("mode") == "slides"}
        at = next((i for i, x in enumerate(ids) if x in old), 0)   # a first carousel leads the post
        kept = [x for x in ids if x not in old]
        kept.insert(min(at, len(kept)), media_id)
        db.table(POSTS).update({"media_ids": kept}).eq("id", post_id).eq("status", "draft").execute()
    except Exception as exc:
        log.warning("could not attach slides %s to post %s: %s", media_id, post_id, exc)


def finish_media(db: Client, row_id: str, **fields: Any) -> None:
    db.table(MEDIA).update(fields).eq("id", row_id).execute()


def upload_generated(db: Client, path: str, data: bytes, content_type: str) -> str:
    """Put the bytes in bucket `semasa-generated` and return the public address."""
    bucket = db.storage.from_(GENERATED_BUCKET)
    bucket.upload(path, data, {"content-type": content_type, "upsert": "true"})
    return bucket.get_public_url(path)
