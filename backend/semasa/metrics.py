"""Prestasi: what each published post did on its channel (Wan, 9 Oct 2026: "add feature that can track post same as
attached" — Threads' own analytics screen: reach, average views, engagement, replies, peak post, best publishing window,
a day × 3-hour heatmap).

The figures come from Buffer, which already holds every ws.regulab post (Facebook, Instagram, Threads) and refreshes each
sent post's metrics about once a day. This worker reads every sent post in the window with its metrics
(senders.Buffer.sent_with_metrics), normalises the per-network names into one row shape, joins each Buffer post to the
Semasa post whose `published.<channel>.id` names it, and upserts `semasa_post_metrics` (supabase/034_post_metrics.sql).
The page computes everything else in Malaysia time (web/src/lib/analytics.js); this worker writes figures, never a verdict.

What each network gives through Buffer, measured 9 Oct 2026:
  threads    views, reactions, comments, quotes, reposts, engagementRate
  instagram  views, reach, reactions, comments, shares, saves, follows, engagementRate
  facebook   impressions, reactions, comments, shares, clicks, engagementRate
LinkedIn gives nothing through Composio: that connection holds w_member_social only (CLAUDE.md rule 5).

Zernio is the publisher since 10 Nov 2026, so a post it sent is not in Buffer at all. The second pass reads Zernio's own
analytics (senders.Zernio.analytics, GET /v1/analytics, posts sent through Zernio only) for all five platforms, TikTok and
LinkedIn included (Wan, 11 Nov 2026: "linkedn no analysis, add for tiktok"). Zernio reads a personal LinkedIn profile's
figures only for posts it published itself, which is exactly those. Rows are written with source 'zernio'
(supabase/077_post_metrics_zernio.sql allows the value); until that file is run the pass says so in the log and writes
nothing, and the Buffer pass is unaffected.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import db, senders
from .publisher import zernio_hub

log = logging.getLogger("semasa.metrics")
SETTINGS_KEY = "metrics"
DEFAULTS: dict[str, Any] = {"days_back": 120}
CHANNELS = ("facebook", "instagram", "threads")
ZERNIO_CHANNELS = ("facebook", "instagram", "threads", "tiktok", "linkedin")
# Zernio's name for a figure → the row's column
ZERNIO_FIELDS = {"views": "views", "reach": "reach", "impressions": "impressions", "likes": "reactions", "comments": "comments",
                 "shares": "shares", "saves": "saves", "clicks": "clicks", "follows": "follows", "reposts": "reposts"}
COUNTS = ("views", "reach", "impressions", "reactions", "comments", "shares", "saves", "reposts", "quotes", "clicks", "follows")


def load_settings(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", SETTINGS_KEY).execute().data or []
    raw = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    return {**DEFAULTS, **raw}


def buffer_config(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", "channels").execute().data or []
    v = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    return v.get("buffer") or {}


def normalise(metrics: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Buffer's metric list → the row's columns. Unknown types are kept only in the raw list."""
    out: dict[str, Any] = {k: None for k in COUNTS}
    out["engagement"] = None
    for m in metrics or []:
        t, v = str(m.get("type") or ""), m.get("value")
        if v is None:
            continue
        if t == "engagementRate":
            out["engagement"] = round(float(v), 2)
        elif t in COUNTS:
            out[t] = int(round(float(v)))
    return out


def post_index(store: Any, channels: tuple[str, ...] = CHANNELS) -> dict[str, str]:
    """Buffer (or Zernio) post id → Semasa post id, from every post's `published` record (the publisher writes `id` per
    channel)."""
    rows = store.table(db.POSTS).select("id,published").in_("status", ["scheduled", "posted"]).execute().data or []
    out: dict[str, str] = {}
    for r in rows:
        pub = r.get("published") if isinstance(r.get("published"), dict) else {}
        for ch, rec in pub.items():
            if ch in channels and isinstance(rec, dict) and rec.get("id"):
                out[str(rec["id"])] = r["id"]
    return out


def _int(v: Any) -> int | None:
    try:
        return None if v is None or isinstance(v, bool) else int(round(float(v)))
    except (TypeError, ValueError):
        return None


def zernio_rows(post: dict[str, Any], index: dict[str, str], now: datetime) -> list[dict[str, Any]]:
    """One Zernio analytics post → one row per platform it was published on. A platform that failed has no figures and no
    row. The row's id is the Zernio post id plus the platform, so a post sent to three platforms is three rows."""
    late = str(post.get("latePostId") or post.get("postId") or post.get("_id") or "")
    if not late:
        return []
    entries = post.get("platformAnalytics")
    if not isinstance(entries, list) or not entries:
        entries = [{"platform": post.get("platform"), "analytics": post.get("analytics"), "status": "published",
                    "platformPostUrl": post.get("platformPostUrl")}]
    out: list[dict[str, Any]] = []
    for e in entries:
        platform = str((e or {}).get("platform") or "").lower()
        if platform not in ZERNIO_CHANNELS or str(e.get("status") or "published") == "failed":
            continue
        a = e.get("analytics") if isinstance(e.get("analytics"), dict) else {}
        row: dict[str, Any] = {k: None for k in COUNTS}
        for theirs, ours in ZERNIO_FIELDS.items():
            row[ours] = _int(a.get(theirs))
        try:
            engagement = round(float(a["engagementRate"]), 2) if a.get("engagementRate") is not None else None
        except (TypeError, ValueError):
            engagement = None
        acc = e.get("accountId")
        out.append({
            "source": "zernio", "external_id": f"{late}:{platform}", "channel": platform,
            "channel_id": str(acc.get("_id") if isinstance(acc, dict) else acc or ""), "post_id": index.get(late),
            "sent_at": post.get("publishedAt") or post.get("scheduledFor"),
            "url": str(e.get("platformPostUrl") or post.get("platformPostUrl") or ""),
            "text_head": str(post.get("content") or "")[:200],
            "metrics": [{"type": k, "value": v} for k, v in a.items() if isinstance(v, (int, float)) and not isinstance(v, bool)],
            "metrics_at": a.get("lastUpdated"), "fetched_at": now.isoformat(), "engagement": engagement, **row,
        })
    return out


def process_zernio(store: Any, settings: dict[str, Any], hub: Any, now: datetime) -> dict[str, int]:
    """Read every post Zernio published in the window and upsert its figures, one row per platform."""
    counts = {"read": 0, "written": 0, "linked": 0, "no_figures": 0}
    start = (now - timedelta(days=min(int(settings.get("days_back") or DEFAULTS["days_back"]), 360))).isoformat()
    index = post_index(store, ZERNIO_CHANNELS)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for post in hub.analytics(start, (now + timedelta(days=1)).isoformat()):
        for row in zernio_rows(post, index, now):
            if row["external_id"] in seen:
                continue
            seen.add(row["external_id"])
            counts["read"] += 1
            counts["linked"] += 1 if row["post_id"] else 0
            counts["no_figures"] += 0 if row["metrics"] else 1
            rows.append(row)
    for i in range(0, len(rows), 100):
        store.table(db.POST_METRICS).upsert(rows[i:i + 100], on_conflict="source,external_id").execute()
        counts["written"] += len(rows[i:i + 100])
    logins = getattr(hub, "last_analytics", None)
    if isinstance(logins, list):
        counts["logins"] = logins                    # what each Zernio login answered, for the log
        for login in logins:
            if login.get("access") is False or not login.get("posts"):
                why = "has no analytics access" if login.get("access") is False else "returned no post with figures"
                db.log_event(store, "warn", "metrics", "metrics.zernio_empty",
                             f"Prestasi: the Zernio login holding {', '.join(login.get('accounts') or [])} {why}"[:300],
                             detail=login)
    return counts


def row_of(node: dict[str, Any], index: dict[str, str], now: datetime) -> dict[str, Any]:
    text = str(node.get("text") or "")
    return {
        "source": "buffer", "external_id": str(node.get("id")), "channel": str(node.get("channelService") or ""),
        "channel_id": str(node.get("channelId") or ""), "post_id": index.get(str(node.get("id"))),
        "sent_at": node.get("sentAt") or node.get("dueAt"), "url": str(node.get("externalLink") or ""),
        "text_head": text[:200], "metrics": node.get("metrics") or [], "metrics_at": node.get("metricsUpdatedAt"),
        "fetched_at": now.isoformat(), **normalise(node.get("metrics")),
    }


def process(store: Any, settings: dict[str, Any], client: Any, now: datetime) -> dict[str, int]:
    """Read every sent post in the window and upsert its figures. Returns the tallies for the log."""
    counts = {"read": 0, "written": 0, "linked": 0, "no_figures": 0}
    cfg = buffer_config(store)
    channel_ids = [str(cfg[c]) for c in CHANNELS if cfg.get(c)]
    if not channel_ids:
        raise senders.SendError("refused", "no Buffer channel ids in settings.channels.buffer")
    start = (now - timedelta(days=int(settings.get("days_back") or DEFAULTS["days_back"]))).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    nodes = client.sent_with_metrics(channel_ids, start, end)
    index = post_index(store)
    rows: list[dict[str, Any]] = []
    for node in nodes:
        if str(node.get("channelService") or "") not in CHANNELS or not node.get("id"):
            continue
        counts["read"] += 1
        row = row_of(node, index, now)
        if row["post_id"]:
            counts["linked"] += 1
        if not (node.get("metrics") or []):
            counts["no_figures"] += 1
        rows.append(row)
    for i in range(0, len(rows), 100):
        store.table(db.POST_METRICS).upsert(rows[i:i + 100], on_conflict="source,external_id").execute()
        counts["written"] += len(rows[i:i + 100])
    return counts


def _zernio_config(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("key,value").eq("key", "channels").execute().data or []
    v = rows[0]["value"] if rows and isinstance(rows[0].get("value"), dict) else {}
    return v.get("zernio") or {}


def run(store: Any, now: datetime | None = None, client: Any | None = None, hub: Any | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    counts = {"read": 0, "written": 0, "linked": 0, "no_figures": 0}
    if hub is None:
        hub = zernio_hub(_zernio_config(store))
    if client is None:
        key, org = os.environ.get("BUFFER_API_KEY"), buffer_config(store).get("organizationId")
        if key and org:
            client = senders.Buffer(key, str(org))
        elif hub is None:
            db.log_event(store, "warn", "metrics", "metrics.skipped",
                         "Prestasi: BUFFER_API_KEY or the Buffer organisation is missing, and no Zernio key is set")
            return counts
    failed: senders.SendError | None = None
    if client is not None:
        try:
            counts = process(store, settings, client, now)
        except senders.SendError as exc:      # Buffer failing must not cost the Zernio pass (and the other way round)
            db.log_event(store, "error", "metrics", "metrics.failed", f"Prestasi (Buffer): {exc.message}"[:300])
            failed = exc
    zcounts = None
    if hub is not None:
        try:
            zcounts = process_zernio(store, settings, hub, now)
            counts = {k: counts[k] + int(zcounts.get(k) or 0) for k in counts}
        except senders.SendError as exc:
            db.log_event(store, "error", "metrics", "metrics.failed", f"Prestasi (Zernio): {exc.message}"[:300])
            failed = failed or exc
        except Exception as exc:  # noqa: BLE001 - the table refusing source 'zernio' (077 not run) must not fail the Buffer pass
            if "semasa_post_metrics_source_check" not in str(exc):
                raise
            db.log_event(store, "warn", "metrics", "metrics.zernio_blocked",
                         "Prestasi: Zernio figures were read but not saved. Run supabase/077_post_metrics_zernio.sql once.")
    if failed is not None and not counts["written"]:
        raise failed
    db.log_event(store, "info", "metrics", "metrics.read",
                 f"Prestasi: {counts['written']} channel-posts refreshed, {counts['linked']} linked to a Semasa post"
                 + (f" ({zcounts['written']} from Zernio)" if zcounts else ""),
                 detail={**counts, "zernio": zcounts})
    return counts


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = db.client()
    counts = run(store)
    log.info("metrics: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## Prestasi\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
