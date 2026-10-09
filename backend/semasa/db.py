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
# Bil (supabase/028_billing.sql)
CLIENTS = "semasa_clients"
PROJECTS = "semasa_projects"
BILLING_DOCS = "semasa_billing_docs"
BILLING_EVENTS = "semasa_billing_events"
BILLING_OUTBOX = "semasa_billing_outbox"
SUBSCRIPTIONS = "semasa_subscriptions"
RECEIPTS = "semasa_receipts"
# CRM (supabase/031_crm.sql)
CRM_CONTACTS = "semasa_crm_contacts"
CRM_CAMPAIGNS = "semasa_crm_campaigns"
CRM_OUTBOX = "semasa_crm_outbox"
CRM_ACTIVITIES = "semasa_crm_activities"


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


PAGE = 1000   # Supabase's default max_rows: a single read never returns more, whatever .limit() asks for


def fetch_all(make_query: Any, cap: int = 50000) -> list[dict[str, Any]]:
    """Every row of a query, read page by page. `make_query()` builds the query afresh (a builder cannot be
    reused), and it must be ordered, or pages can overlap."""
    out: list[dict[str, Any]] = []
    while len(out) < cap:
        page = make_query().range(len(out), len(out) + PAGE - 1).execute().data or []
        out.extend(page)
        if len(page) < PAGE:
            break
    return out[:cap]


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
        picked = {r["trend_id"] for r in fetch_all(lambda: db.table(IDEAS).select("id,trend_id")
                                                   .not_.is_("trend_id", "null").order("id")) if r.get("trend_id")}
        try:   # a headline made into a FAQ is picked too (the table arrives with 007_faq.sql)
            picked |= {r["trend_id"] for r in fetch_all(lambda: db.table("semasa_faqs").select("id,trend_id")
                                                        .not_.is_("trend_id", "null").order("id")) if r.get("trend_id")}
        except Exception as exc:
            log.info("no FAQ table to consult yet (%s)", str(exc)[:80])
        old = fetch_all(lambda: db.table(TRENDS).select("id").lt("created_at", shown_cutoff_iso)
                        .lt("published_at", refetch_cutoff_iso).order("id"))
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

    A run started for one job (`only_id`, the page's dispatch) takes that job FIRST and then fills the rest of the batch
    with the oldest other waiting jobs. Taking the one job alone could loop: a slide job waiting for its post's picture
    goes back to `pending`, that re-dispatches a run for the slide alone, and the picture it waits on was never taken
    (the queued runs that would have taken it were cancelled by the concurrency group) until SLIDES_WAIT ran out.
    """
    rows: list[dict[str, Any]] = []
    if only_id:
        rows = db.table(MEDIA).select("*").eq("status", "pending").eq("id", only_id).limit(1).execute().data or []
    if len(rows) < limit:
        more = db.table(MEDIA).select("*").eq("status", "pending").order("created_at").limit(limit + 1).execute().data or []
        rows += [r for r in more if r["id"] != only_id][: limit - len(rows)]
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


def requeue_stale(db: Client, table: str, *, working: str, back: str, cutoff: str, max_attempts: int,
                  what: str, column: str = "updated_at") -> int:
    """A runner that dies (timeout, cancelled, lost) leaves its rows `working` for ever: nothing else would take them,
    and the page shows a spinner that never stops. Put them back in the queue, EXCEPT a row that has already been tried
    `max_attempts` times: that one ends in `error`. Without the cap, a job that kills its runner (a video longer than
    the job's time limit) was taken again, killed again, for ever, and the whole queue behind it starved."""
    try:
        (db.table(table).update({"status": "error",
                                 "error": f"the {what} stopped its runner {max_attempts} times (too long or too big); "
                                          "not tried again. Change it or delete it."})
         .eq("status", working).lt(column, cutoff).gte("attempts", max_attempts).execute())
        back_patch = {"status": back, "error": "runner stopped before finishing; queued again"}
        try:
            res = db.table(table).update(back_patch).eq("status", working).lt(column, cutoff).execute()
            return len(res.data or [])
        except Exception as exc:  # noqa: BLE001
            # One row the database refuses (before 018: an idea whose draft was approved meanwhile) failed the whole
            # statement and left EVERY stuck row stuck. Row by row, the others still go back.
            log.info("recovering %s rows one by one (%s)", table, str(exc)[:120])
            stuck = db.table(table).select("id").eq("status", working).lt(column, cutoff).limit(200).execute().data or []
            done = 0
            for r in stuck:
                try:
                    db.table(table).update(back_patch).eq("id", r["id"]).eq("status", working).execute()
                    done += 1
                except Exception as one:  # noqa: BLE001
                    log.warning("could not recover %s %s: %s", what, r["id"], str(one)[:160])
            return done
    except Exception as exc:  # noqa: BLE001 - recovery must never stop the run
        log.warning("could not recover stuck %s rows: %s", table, exc)
        return 0


def release_media(db: Client, row: dict[str, Any]) -> None:
    """Hand a claimed job back unstarted (the run is out of time): `pending` again, and the attempt it was charged
    at the claim is given back, since nothing was tried."""
    try:
        db.table(MEDIA).update({"status": "pending", "attempts": max(0, int(row.get("attempts") or 1) - 1),
                                "error": None}).eq("id", row["id"]).eq("status", "processing").execute()
    except Exception as exc:  # noqa: BLE001 - recovery puts it back within the hour anyway
        log.warning("could not hand %s back: %s", row.get("id"), exc)


def recover_stale_media(db: Client, stale_minutes: int, max_attempts: int = 3) -> int:
    """Media rows left `processing` by a dead runner go back to `pending`, or to `error` at MEDIA_MAX_ATTEMPTS."""
    cutoff = (datetime.now(UTC) - timedelta(minutes=stale_minutes)).isoformat()
    n = requeue_stale(db, MEDIA, working="processing", back="pending", cutoff=cutoff, max_attempts=max_attempts,
                      what="job")
    if n:
        log.warning("put %d stuck media job(s) back in the queue", n)
    return n


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
            got = db.table(MEDIA).select("id,mode,meta").in_("id", ids).execute().data or []
            # a Design-tab artwork attached to the post is not its carousel, and stays
            old = {r["id"] for r in got if r.get("mode") == "slides" and not (r.get("meta") or {}).get("design")}
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
