"""Housekeeping: one daily sweep that keeps the database, the storage bucket and the egress they cost small (Wan, 22 Nov 2026:
"make do routine cleaning to make sure supabase or egress/db is not tight").

WHAT ALREADY CLEANS UP, and stays where it is (this module does not repeat it):
  * the publisher, three times a day (publisher.main → archive.py): a posted post is compacted 24 h after it went out; a rejected
    post and the pictures made for it are deleted 72 h after the rejection; the files of a posted post (pictures, slides, a Motion
    film with its social copy, poster and storyboard) go `settings.prune.hours` (12) after it went out, the rows staying as the
    record; files no row names are deleted after 24 h (`prune.orphans = "delete"`, 200 a run);
  * the scraper: headlines and run rows after SCRAPE_KEEP_DAYS (30), unpicked headlines after 48 h, the log after 90 days;
  * the regulators' feed (watch.compact), the community sweep (intake.prune) and AI usage rows after 90 days (api_status.prune).

WHAT THIS ADDS, each a step that reports what it found and, in "delete" mode, removes it:
  rows
    pulse_log     the API pulse's "robot down" lines in semasa_log after 14 days (the pulse only reads back a few hours of them;
                  every other log line keeps its 90 days)
    pulse_usage   the API pulse's own semasa_api_usage rows (area "pulse", one per robot every 5 minutes, ~940 a day) after
                  14 days; every AI call a worker makes keeps its 90 days
    telegram      Telegram updates already handled (done, skipped, error) after 30 days; Telegram never re-sends one that old
    cron          pg_cron's run history of Semasa's own jobs (semasa_*) after 14 days, through supabase/089 (skipped until run)
  files
    deleted_posts pictures and slides made FOR a post that was then deleted by hand: the idea was drafted (or rejected), it has
                  no post any more, the picture is on no post, it is not a Design-tab artwork (meta.design / design_id) nor a
                  daily-series art (meta.comic), and nothing else in the database names its id or its files. The clock is the
                  row's updated_at, which the delete stamps (media_generations.post_id is ON DELETE SET NULL and the row's own
                  trigger dates every update): 7 days after. Row and files go, as purge_rejected does for a rejected post.
                  A picture made in the Image tab (no idea) is the library and is never touched.
    idle_films    a finished Motion film never put on a post (no queued post, no post holding its media) and not touched for
                  30 days: REPORTED ONLY unless `settings.housekeeping.idle_films` is "delete". When on, its files go and the
                  rows stay as the record, exactly as purge_films does 12 h after a film is posted.
  thumbs (adds, never deletes)
    the small JPEG each stored picture now gets for the page's library tiles (semasa/thumbs.py): pictures stored before
                  22 Nov 2026 have none, so up to thumbs.BACKFILL_CAP a run are made (one download of the picture each, once).

Guards: nothing that belongs to a draft, approved, scheduled or posted post is a candidate; a step that cannot read what it needs
deletes nothing; files are removed only after their row is gone (a file left behind is the orphan sweep's, a row pointing at a
missing file would be a broken tile); at most CAP rows a step a run; only Semasa's tables and the semasa-generated bucket are
touched (the project is shared with KPI). Every read asks for the columns it needs and every delete returns nothing, so the
sweep itself costs little egress.

Settings (`semasa_settings` key "housekeeping", every field optional, DEFAULTS below): mode "delete" | "report" (report = count
only, for everything), the days of each step, and idle_films "report" | "delete".

    python -m semasa.housekeeping --dry-run     # count only, change nothing (the workflow's "dry run" box)
    python -m semasa.housekeeping               # do what settings say (mode "delete" unless set to "report")
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from . import archive, db, thumbs
from .log import get_logger

log = get_logger("semasa.housekeeping")

KEY = "housekeeping"
DEFAULTS: dict[str, Any] = {
    "mode": "delete",
    "pulse_log_days": 14,
    "pulse_usage_days": 14,
    "telegram_days": 30,
    "cron_days": 14,
    "deleted_post_media_days": 7,
    "idle_films": "report",
    "idle_film_days": 30,
}
FLOOR_DAYS = 3            # no step keeps less than this, whatever the setting says
CAP = 300                 # rows a step deletes in one run at most: a bug in a rule must not empty a table in one go
TELEGRAM_INBOX = "semasa_telegram_inbox"
MOTIONS = "semasa_motions"
_DESIGN_KEYS = ("design", "design_id", "comic")


def load_settings(store: Any) -> dict[str, Any]:
    """DEFAULTS overlaid with settings.housekeeping; every number at least FLOOR_DAYS. Unreadable settings: the defaults."""
    cfg = dict(DEFAULTS)
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", KEY).limit(1).execute().data or []
        value = (rows[0].get("value") or {}) if rows else {}
        if isinstance(value, dict):
            cfg.update({k: v for k, v in value.items() if k in DEFAULTS})
    except Exception as exc:  # noqa: BLE001 - settings unreadable: the defaults
        log.info("housekeeping settings not read: %s", str(exc)[:120])
    for k, v in DEFAULTS.items():
        if isinstance(v, int):
            try:
                cfg[k] = max(FLOOR_DAYS, int(cfg[k]))
            except (TypeError, ValueError):
                cfg[k] = v
    cfg["mode"] = "report" if cfg.get("mode") == "report" else "delete"
    cfg["idle_films"] = "delete" if cfg.get("idle_films") == "delete" else "report"
    return cfg


def _ago(now: datetime, days: int) -> str:
    return (now - timedelta(days=days)).isoformat()


def _older(stamp: Any, cutoff: str) -> bool:
    """Is a stored timestamp before the cutoff? An unreadable stamp is never old (failing safe keeps the thing)."""
    try:
        when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        return when < datetime.fromisoformat(cutoff)
    except (TypeError, ValueError):
        return False


def _count(res: Any) -> int:
    """A HEAD request with count=exact answers in `count`; the test store answers with the rows."""
    n = getattr(res, "count", None)
    return int(n) if n is not None else len(getattr(res, "data", None) or [])


# --- rows ------------------------------------------------------------------------------------------------------------------

ROW_RULES: tuple[tuple[str, str, str, str, Callable[[Any], Any]], ...] = (
    # name, table, date column, setting, the filter that names the rows
    ("pulse_log", db.LOG, "at", "pulse_log_days", lambda q: q.like("event", "api_pulse.%")),
    ("pulse_usage", db.API_USAGE, "created_at", "pulse_usage_days", lambda q: q.eq("area", "pulse")),
    ("telegram", TELEGRAM_INBOX, "created_at", "telegram_days", lambda q: q.in_("status", ["done", "skipped", "error"])),
)


def sweep_rows(store: Any, cfg: dict[str, Any], now: datetime, dry: bool) -> dict[str, dict[str, Any]]:
    """Each row rule: count what is older than its window, and in delete mode delete it (returning nothing over the wire)."""
    out: dict[str, dict[str, Any]] = {}
    for name, table, col, setting, where in ROW_RULES:
        cutoff = _ago(now, cfg[setting])
        try:
            n = _count(where(store.table(table).select("id", count="exact", head=True)).lt(col, cutoff).execute())
            deleted = 0
            if n and not dry:
                where(store.table(table).delete(returning="minimal")).lt(col, cutoff).execute()
                deleted = n
            out[name] = {"found": n, "deleted": deleted, "days": cfg[setting]}
        except Exception as exc:  # noqa: BLE001 - one table must not stop the others
            out[name] = {"error": str(exc)[:160], "days": cfg[setting]}
    return out


def sweep_cron(store: Any, cfg: dict[str, Any], dry: bool) -> dict[str, Any]:
    days = cfg["cron_days"]
    try:
        n = int(store.rpc("semasa_housekeeping_cron", {"p_days": days, "p_dry": True}).execute().data or 0)
        deleted = 0
        if n and not dry:
            deleted = int(store.rpc("semasa_housekeeping_cron", {"p_days": days, "p_dry": False}).execute().data or 0)
        return {"found": n, "deleted": deleted, "days": days}
    except Exception as exc:  # noqa: BLE001 - 089 not run yet
        msg = str(exc)
        if "semasa_housekeeping_cron" in msg or "PGRST202" in msg:
            return {"skipped": "run supabase/089_housekeeping.sql", "days": days}
        return {"error": msg[:160], "days": days}


# --- files -----------------------------------------------------------------------------------------------------------------

def _paths(row: dict[str, Any]) -> list[str]:
    """Every file of a picture row in the generated bucket: the picture, the slides, and what its addresses name."""
    paths = archive.files_of(row) + [archive.path_of(row.get("generated_media_url")), archive.path_of(row.get("reference_url"))]
    return list(dict.fromkeys(p for p in paths if p))


def _posts(store: Any) -> list[dict[str, Any]]:
    return db.fetch_all(lambda: store.table(db.POSTS).select("id,idea_id,status,media_ids").order("id"))


def _in_chunks(store: Any, table: str, cols: str, col: str, ids: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in db._in_filter_chunks(ids):
        out += store.table(table).select(cols).in_(col, chunk).execute().data or []
    return out


def deleted_post_media(store: Any, now: datetime, days: int) -> list[dict[str, Any]]:
    """Pictures made for a post that was deleted by hand (see the module docstring), oldest first. Raises when a read fails:
    the caller then deletes nothing."""
    cutoff = _ago(now, days)
    rows = db.fetch_all(lambda: store.table(db.MEDIA)
                        .select("id,idea_id,post_id,type,status,meta,generated_media_url,reference_url,updated_at")
                        .is_("post_id", "null").not_.is_("idea_id", "null").in_("status", ["done", "error"])
                        .lt("updated_at", cutoff).order("id"))
    rows = [r for r in rows if r.get("type") != "video" and _older(r.get("updated_at"), cutoff)
            and not any((r.get("meta") or {}).get(k) for k in _DESIGN_KEYS)]
    if not rows:
        return []
    ideas = {i["id"]: i.get("status") for i in _in_chunks(store, db.IDEAS, "id,status", "id",
                                                         sorted({str(r["idea_id"]) for r in rows}))}
    posts = _posts(store)
    with_post = {str(p.get("idea_id")) for p in posts if p.get("idea_id")}
    attached = {str(m) for p in posts for m in (p.get("media_ids") or [])}
    keep = [r for r in rows if ideas.get(str(r["idea_id"])) in ("drafted", "rejected")
            and str(r["idea_id"]) not in with_post and str(r["id"]) not in attached]
    return sorted(keep, key=lambda r: str(r.get("updated_at")))


def _named_elsewhere(text: str, row: dict[str, Any]) -> bool:
    return str(row["id"]) in text or any(p in text for p in _paths(row))


def sweep_deleted_posts(store: Any, cfg: dict[str, Any], now: datetime, dry: bool, sizes: dict[str, int]) -> dict[str, Any]:
    days = cfg["deleted_post_media_days"]
    try:
        found = deleted_post_media(store, now, days)
        if found:
            # the one wide read of the run, and only when there is something to check: every other row of every table that may
            # name a file, so a picture whose id or file another row still names (a slide, a brief, a design) is kept
            text = archive.referenced_text(store, skip={db.MEDIA: {str(r["id"]) for r in found}})
            found = [r for r in found if not _named_elsewhere(text, r)]
    except Exception as exc:  # noqa: BLE001 - when in doubt, keep everything
        return {"error": str(exc)[:160], "days": days}
    files = [p for r in found for p in _paths(r) if p in sizes]
    out = {"found": len(found), "files": len(files), "bytes": sum(sizes[p] for p in files), "deleted": 0, "days": days}
    if dry or not found:
        return out
    gone: list[dict[str, Any]] = []
    for r in found[:CAP]:
        try:
            # checked again just before: a post that took the picture meanwhile keeps it
            if store.table(db.POSTS).select("id").contains("media_ids", [r["id"]]).limit(1).execute().data:
                continue
            res = store.table(db.MEDIA).delete().eq("id", r["id"]).is_("post_id", "null").execute().data or []
            if res:
                gone.append(r)
        except Exception as exc:  # noqa: BLE001 - one row must not stop the others
            log.warning("media %s not deleted: %s", r["id"], str(exc)[:160])
    paths = [p for r in gone for p in _paths(r)]
    for i in range(0, len(paths), 100):
        try:
            store.storage.from_(db.GENERATED_BUCKET).remove(paths[i:i + 100])
        except Exception as exc:  # noqa: BLE001 - a file left behind is the orphan sweep's, a day later
            log.info("could not remove %d file(s): %s", len(paths[i:i + 100]), str(exc)[:120])
    out.update(deleted=len(gone), freed=sum(sizes.get(p, 0) for p in paths))
    return out


def idle_films(store: Any, now: datetime, days: int) -> tuple[list[tuple[dict[str, Any], list[dict[str, Any]]]], int, int]:
    """(films idle for `days`, with their media rows), and how many finished films are on no post at all, with their bytes."""
    films = db.fetch_all(lambda: store.table(MOTIONS)
                         .select("id,status,queued_post_id,updated_at,video_path,video_url,social_url,poster_url,check_report,"
                                 "bytes,social_bytes").eq("status", "done").is_("queued_post_id", "null").order("id"))
    films = [f for f in films if f.get("video_url") and not (f.get("check_report") or {}).get("film_purged_at")]
    if not films:
        return [], 0, 0
    media = db.fetch_all(lambda: store.table(db.MEDIA).select("id,post_id,mode,meta,generated_media_url,reference_url")
                         .eq("type", "video").order("id"))
    by_film: dict[str, list[dict[str, Any]]] = {}
    for m in media:
        if (m.get("meta") or {}).get("motion_id"):
            by_film.setdefault(str(m["meta"]["motion_id"]), []).append(m)
    attached = {str(x) for p in _posts(store) for x in (p.get("media_ids") or [])}
    unposted = [f for f in films if not any(m.get("post_id") or str(m["id"]) in attached for m in by_film.get(str(f["id"]), []))]
    total = sum(int(f.get("bytes") or 0) + int(f.get("social_bytes") or 0) for f in unposted)
    cutoff = _ago(now, days)
    idle = [(f, by_film.get(str(f["id"]), [])) for f in unposted if _older(f.get("updated_at"), cutoff)]
    return idle, len(unposted), total


def sweep_idle_films(store: Any, cfg: dict[str, Any], now: datetime, dry: bool, sizes: dict[str, int]) -> dict[str, Any]:
    days, on = cfg["idle_film_days"], cfg["idle_films"] == "delete"
    try:
        idle, unposted, unposted_bytes = idle_films(store, now, days)
        plan = [(f, ms, archive.film_files(store, f, ms[0] if ms else {}) + [p for m in ms[1:] for p in _paths(m)])
                for f, ms in idle]
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:160], "days": days}
    out = {"found": len(plan), "files": sum(len(p) for _, _, p in plan),
           "bytes": sum(sizes.get(x, 0) for _, _, p in plan for x in p), "deleted": 0, "days": days,
           "unposted_films": unposted, "unposted_bytes": unposted_bytes, "switch": cfg["idle_films"]}
    if dry or not on:
        return out
    stamp = now.isoformat()
    for film, ms, paths in plan[:CAP]:
        try:
            paths = list(dict.fromkeys(paths))
            if paths:
                store.storage.from_(db.GENERATED_BUCKET).remove(paths)      # a failure raises: no record changes
            report = dict(film.get("check_report") or {})
            report.update(film_purged_at=stamp, purged_because=f"idle {days} days, never posted")
            store.table(MOTIONS).update({"video_url": "", "social_url": "", "poster_url": "", "video_path": "", "html": "",
                                         "check_report": report}).eq("id", film["id"]).eq("status", "done") \
                .is_("queued_post_id", "null").execute()
            for m in ms:
                meta = dict(m.get("meta") or {})
                meta.update(film_purged_at=stamp, purge_days=days, poster_url="", generated_path=None)
                store.table(db.MEDIA).update({**archive._cleared(m), "meta": meta}).eq("id", m["id"]).execute()
            out["deleted"] += 1
        except Exception as exc:  # noqa: BLE001 - one film must not stop the others
            log.warning("film %s not cleared: %s", film["id"], str(exc)[:160])
    return out


# --- the run ---------------------------------------------------------------------------------------------------------------

def bucket_sizes(store: Any) -> dict[str, int]:
    """name → bytes for every file in the generated bucket (one listing a run; the orphan sweep reads the same)."""
    return {f["name"]: int(f.get("size") or 0) for f in archive.list_bucket(store)}


def run(store: Any, now: datetime | None = None, dry: bool | None = None) -> dict[str, Any]:
    """Every step, each on its own (one failing never stops the next). `dry` None follows settings.housekeeping.mode."""
    now = now or datetime.now(UTC)
    cfg = load_settings(store)
    dry = cfg["mode"] == "report" if dry is None else dry
    try:
        sizes = bucket_sizes(store)
        bucket = {"files": len(sizes), "bytes": sum(sizes.values())}
    except Exception as exc:  # noqa: BLE001 - sizes are for the report only
        sizes, bucket = {}, {"error": str(exc)[:160]}
    report: dict[str, Any] = {"at": now.isoformat(), "dry": dry, "bucket": bucket}
    report.update(sweep_rows(store, cfg, now, dry))
    report["cron"] = sweep_cron(store, cfg, dry)
    report["deleted_posts"] = sweep_deleted_posts(store, cfg, now, dry, sizes)
    report["idle_films"] = sweep_idle_films(store, cfg, now, dry, sizes)
    # not a delete: the library thumbnails pictures stored before 22 Nov 2026 are missing (semasa/thumbs.py), a few a run.
    # Only with a bucket listing to compare against; without one, nothing is made rather than everything again
    report["thumbs"] = thumbs.backfill(store, set(sizes), dry) if sizes else {"skipped": "bucket not listed"}
    if not dry:
        rows = sum(int((report.get(k) or {}).get("deleted") or 0) for k in ("pulse_log", "pulse_usage", "telegram", "cron"))
        pics, films = report["deleted_posts"].get("deleted", 0), report["idle_films"].get("deleted", 0)
        if rows or pics or films:
            mb = (report["deleted_posts"].get("freed", 0)) / 1048576
            db.log_event(store, "info", "system", "housekeeping",
                         f"Kemas rumah: {rows} baris lama dipadam, {pics} gambar post yang dipadam dibuang ({mb:.0f} MB)"
                         + (f", {films} video Motion terbiar dikosongkan" if films else ""),
                         detail={k: v for k, v in report.items() if k != "at"})
    return report


def _mb(n: Any) -> str:
    return f"{(int(n or 0)) / 1048576:.1f} MB"


def summary(report: dict[str, Any]) -> str:
    """The report as lines a person reads (the job summary, the log)."""
    verb = "would delete" if report.get("dry") else "deleted"
    lines = [f"Housekeeping ({'dry run, nothing changed' if report.get('dry') else 'delete mode'}), {report.get('at', '')}"]
    b = report.get("bucket") or {}
    lines.append(f"- bucket semasa-generated: {b.get('files', '?')} files, {_mb(b.get('bytes'))}" if "error" not in b
                 else f"- bucket not listed: {b['error']}")
    names = {"pulse_log": "API pulse log lines", "pulse_usage": "API pulse usage rows", "telegram": "handled Telegram updates",
             "cron": "pg_cron run history (semasa_*)"}
    for k, label in names.items():
        r = report.get(k) or {}
        if "found" in r:
            n = r["found"] if report.get("dry") else r["deleted"]
            lines.append(f"- {label} older than {r['days']} days: {r['found']} found, {n} {verb}")
        else:
            lines.append(f"- {label}: {r.get('skipped') or r.get('error')}")
    d = report.get("deleted_posts") or {}
    if "found" in d:
        n = d["found"] if report.get("dry") else d["deleted"]
        lines.append(f"- pictures of posts deleted over {d['days']} days ago: {d['found']} rows, {d['files']} files, "
                     f"{_mb(d['bytes'])}; {n} {verb}")
    else:
        lines.append(f"- pictures of deleted posts: not checked ({d.get('error')})")
    f = report.get("idle_films") or {}
    if "found" in f:
        acted = "report only (settings housekeeping.idle_films = delete turns it on)" if f["switch"] != "delete" else \
            f"{f['found'] if report.get('dry') else f['deleted']} {verb}"
        lines.append(f"- finished Motion films on no post: {f['unposted_films']} ({_mb(f['unposted_bytes'])}); idle over "
                     f"{f['days']} days: {f['found']}, {_mb(f['bytes'])}; {acted}")
    else:
        lines.append(f"- idle Motion films: not checked ({f.get('error')})")
    th = report.get("thumbs") or {}
    if "found" in th:
        lines.append(f"- library thumbnails missing: {th['found']}; " + ("none made (dry run)" if report.get("dry")
                     else f"{th['made']} made from {_mb(th['bytes'])} of pictures"))
    elif th:
        lines.append(f"- library thumbnails: {th.get('skipped') or th.get('error')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Semasa housekeeping: old rows and dead files")
    ap.add_argument("--dry-run", action="store_true", help="count only, change nothing")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)
    report = run(db.client(), dry=True if args.dry_run else None)
    text = summary(report)
    print(json.dumps(report, indent=2, default=str) if args.json else text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write("## Semasa housekeeping\n\n" + text + "\n")
    failed = [k for k, v in report.items() if isinstance(v, dict) and v.get("error")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
