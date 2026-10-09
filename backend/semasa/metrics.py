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
LinkedIn gives nothing: the Composio connection holds w_member_social only (CLAUDE.md rule 5), so a LinkedIn post has no row.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import db, senders

log = logging.getLogger("semasa.metrics")
SETTINGS_KEY = "metrics"
DEFAULTS: dict[str, Any] = {"days_back": 120}
CHANNELS = ("facebook", "instagram", "threads")
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


def post_index(store: Any) -> dict[str, str]:
    """Buffer post id → Semasa post id, from every post's `published` record (the publisher writes `id` per channel)."""
    rows = store.table(db.POSTS).select("id,published").in_("status", ["scheduled", "posted"]).execute().data or []
    out: dict[str, str] = {}
    for r in rows:
        pub = r.get("published") if isinstance(r.get("published"), dict) else {}
        for ch, rec in pub.items():
            if ch in CHANNELS and isinstance(rec, dict) and rec.get("id"):
                out[str(rec["id"])] = r["id"]
    return out


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


def run(store: Any, now: datetime | None = None, client: Any | None = None) -> dict[str, int]:
    now = now or datetime.now(UTC)
    settings = load_settings(store)
    if client is None:
        key, org = os.environ.get("BUFFER_API_KEY"), buffer_config(store).get("organizationId")
        if not key or not org:
            db.log_event(store, "warn", "metrics", "metrics.skipped",
                         "Prestasi: BUFFER_API_KEY or the Buffer organisation is missing")
            return {"read": 0, "written": 0, "linked": 0, "no_figures": 0}
        client = senders.Buffer(key, str(org))
    try:
        counts = process(store, settings, client, now)
    except senders.SendError as exc:
        db.log_event(store, "error", "metrics", "metrics.failed", f"Prestasi: {exc.message}"[:300])
        raise
    db.log_event(store, "info", "metrics", "metrics.read",
                 f"Prestasi: {counts['written']} channel-posts refreshed, {counts['linked']} linked to a Semasa post",
                 detail=counts)
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
