"""The three Studio duties that read Wan's own sources, run from one place (sources.yml): Reddit and YouTube
(community.py), the OneDrive reference folders (folders.py) and MYRA's daily sheet (myra.py). Brought over 30 Sep 2026
("port all three before Friday"), before ws.regulab Studio's Routines are switched off on Fri 2 Oct.

What they produce is FEED ROWS in `semasa_watch` (sections `reddit`, `youtube`, `folder`, `myra`), never ideas, never
drafts, never anything approved: Wan reads them in the page and clicks "Jadikan idea", or autofill (which is off until
Fri 2 Oct 20:00 MYT) writes an idea for an empty slot from them, and either way the result is a draft that waits for his
Approve. That is Studio's own rule 9 ("the sweep writes only to ideas, never to drafts"), kept.

This is a duplicate READ of what Studio's Routines still read until Friday 19:45 MYT, not a duplicate SCHEDULE: nothing
here posts, and nothing here is approved.

    python -m semasa.intake            # write the rows
    SOURCES_DRY=1 python -m semasa.intake   # read and judge, write nothing (no SQL needed)
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import community, db, folders, myra, watch
from .log import get_logger

log = get_logger("semasa.intake")

WATCH = "semasa_watch"
KEY = "sources"                     # semasa_settings row: Wan's overrides, and the last run's report
KEEP_DAYS = {"reddit": 14, "youtube": 14, "myra": 45}     # what is loud now is not kept; the folder bank is not pruned

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "community": {
        "enabled": True, "subreddit": "malaysia", "window": "week", "limit": 15, "keep": 10,
        "terms": ["halal", "kosmetik", "skincare", "sunscreen", "NPRA", "supplement", "label"],
        "youtube": {"enabled": True, "days": 14, "max_results": 8,
                    "queries": ["sunscreen skincare Malaysia", "halal certification Malaysia", "kosmetik NPRA"]},
    },
    "folders": {
        "enabled": True, "use_writer": True, "root": "/40. HERMES", "account": "Muhammad-Ridzuan",
        "domains": {"kosmetik": "Cosmetic", "kajian_kes": "Cosmetic Case Studies", "halal_my": "Halal", "fatwa": "Fatwa",
                    "farmaseutikal": "Farmaseutikal", "makanan": "Food"},
        "urgent": "urgent post", "angles_per_file": 8, "files_per_run": 3, "matrix_pool": 8,
    },
    "myra": {
        "enabled": True, "spreadsheet_id": "15GMFlA5IXSc453oV3CRwLS7HJcUaGILBD1t-IwKhMaI",
        "account": "googlesheets_serau-tucker", "range": "Sheet1!A1:G500", "days": 10, "per_run": 8,
    },
}


class NeedsMigration(RuntimeError):
    pass


def merged(base: Any, over: Any) -> Any:
    if isinstance(base, dict) and isinstance(over, dict):
        return {**{k: merged(base[k], over[k]) if k in over else base[k] for k in base},
                **{k: v for k, v in over.items() if k not in base}}
    return base if over is None else over


def load_config(store: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = store.table(db.SETTINGS).select("value").eq("key", KEY).execute().data or []
    stored = (rows[0].get("value") if rows else None) or {}
    over = {k: v for k, v in stored.items() if k in DEFAULTS}
    return merged(DEFAULTS, over), stored


def have(store: Any, urls: list[str]) -> set[str]:
    out: set[str] = set()
    for chunk in db._in_filter_chunks(urls):
        out |= {r["url"] for r in (store.table(WATCH).select("url").in_("url", chunk).execute().data or [])}
    return out


def used(store: Any, urls: list[str]) -> set[str]:
    """Addresses an idea already carries: the feed's own test for 'this one has been used'."""
    out: set[str] = set()
    for chunk in db._in_filter_chunks(urls):
        rows = store.table(db.IDEAS).select("source_url").in_("source_url", chunk).execute().data or []
        out |= {r["source_url"] for r in rows}
    return out


def write(store: Any, rows: list[dict[str, Any]], dry: bool) -> int:
    if not rows or dry:
        return len(rows)
    written = 0
    try:
        for i in range(0, len(rows), 50):
            res = store.table(WATCH).upsert(rows[i:i + 50], on_conflict="url", ignore_duplicates=True).execute()
            written += len(res.data or [])
    except Exception as exc:  # noqa: BLE001
        if "section_check" in str(exc) or "check constraint" in str(exc).lower():
            raise NeedsMigration("supabase/024_sources.sql has not been run in the SQL editor yet") from exc
        raise
    return written


# --- the three duties -------------------------------------------------------------------------------------------------

def do_community(store: Any, llm: Any, client: Any, cfg: dict[str, Any], now: datetime, dry: bool) -> dict[str, Any]:
    raw = community.fetch(client, cfg)
    cands = community.candidates(raw, now)
    known = have(store, [c["url"] for c in cands])
    fresh = [c for c in cands if c["url"] not in known]
    by = {"reddit": [], "youtube": []}
    for c in fresh:
        by[c["platform"]].append(c)
    keep = int(cfg.get("keep") or 10)
    batch = by["reddit"][:keep] + by["youtube"][:keep]
    kept, rejected = community.annotate(llm, batch)
    rows = [community.to_row(r) for r in kept] + [community.tombstone(r) for r in rejected]
    write(store, rows, dry)
    rep = {"read": {"reddit": len(raw.get("posts") or []), "youtube": len(raw.get("videos") or [])},
           "new": len(fresh), "shown": {p: sum(1 for r in kept if r["platform"] == p) for p in ("reddit", "youtube")},
           "hidden": len(rejected), "reddit_error": raw.get("reddit_error") or None,
           "youtube_error": raw.get("youtube_error") or None}
    if raw.get("youtube_error"):
        log.warning("YouTube: %s (Reddit carries on)", raw["youtube_error"])
    return rep


def known_folder_rows(store: Any) -> dict[str, Any]:
    rows = store.table(WATCH).select("url,raw,dismissed").eq("section", "folder").limit(3000).execute().data or []
    mined: set[str] = set()
    matrix_files: set[str] = set()
    matrix_rows: dict[str, set[int]] = {}
    matrix_urls: list[str] = []
    for r in rows:
        fid = folders.file_id_of(r["url"])
        if not fid:
            continue
        mined.add(fid)
        raw = r.get("raw") or {}
        if raw.get("matrix"):
            matrix_files.add(fid)
            matrix_rows.setdefault(fid, set()).add(int(raw.get("row") or 0))
            if not r.get("dismissed"):
                matrix_urls.append(r["url"])
    return {"mined": mined, "matrix_files": matrix_files, "matrix_rows": matrix_rows, "matrix_urls": matrix_urls}


def do_folders(store: Any, llm: Any, client: Any, cfg: dict[str, Any], now: datetime, dry: bool) -> dict[str, Any]:
    listing = folders.list_files(client, cfg, now)
    files = {f["id"]: f for f in listing.get("files") or []}
    known = known_folder_rows(store)
    pool_left = len(known["matrix_urls"]) - len(used(store, known["matrix_urls"]))
    want = max(0, int(cfg.get("matrix_pool") or 8) - pool_left)
    todo, matrix_files = folders.plan(list(files.values()), known, int(cfg.get("files_per_run") or 3))
    refill = [f for f in matrix_files if want > 0]
    skip = sorted({n for rows in known["matrix_rows"].values() for n in rows})
    rep: dict[str, Any] = {"listed": len(files), "mined": 0, "angles": 0, "matrix_rows": 0, "errors": listing.get("errors") or [],
                           "waiting": max(0, len([f for f in files.values() if f["id"] not in known["mined"]]) - len(todo))}
    if not todo and not refill:
        return rep
    per_file = int(cfg.get("angles_per_file") or 8)
    docs = folders.read_files(client, cfg, todo + refill, {"skip": skip, "want": max(want, 1)})
    for d in docs.get("docs") or []:
        f = files.get(d.get("id"))
        if not f:
            continue
        if d.get("error"):
            rep["errors"].append(f"{f.get('folder')}: {d['error']}")
            if d["error"].startswith(("too big", "type ")):          # will never work: mark it so it is not retried
                write(store, folders.angle_rows(f, {"kind": "?"}, []), dry)
            continue
        if d.get("kind") == "matrix":
            rows = folders.matrix_rows(f, d)[:max(want, 1)]         # the pool is topped up to matrix_pool, not past it
            rep["matrix_rows"] += write(store, rows, dry)
            rep["mined"] += 0 if f["id"] in known["matrix_files"] else 1
            continue
        if cfg.get("use_writer") is False:
            continue
        angles = folders.mine(llm, d, f, per_file)
        if angles is None:
            rep["errors"].append(f"{f.get('folder')}: the writer gave no answer, will retry")
            continue
        rep["angles"] += write(store, folders.angle_rows(f, d, angles), dry) if angles else 0
        if not angles:
            write(store, folders.angle_rows(f, d, []), dry)
        rep["mined"] += 1
    return rep


def do_myra(store: Any, llm: Any, client: Any, cfg: dict[str, Any], now: datetime, dry: bool) -> dict[str, Any]:
    raw = myra.fetch(client, cfg)
    if raw.get("error"):
        raise RuntimeError(f"the sheet could not be read: {raw['error']}")
    today = (now + timedelta(hours=8)).date()
    rows = myra.findings(raw.get("rows") or [], today, int(cfg.get("days") or 10), limit=int(cfg.get("per_run") or 8) * 2)
    known = have(store, [r["url"] for r in rows])
    fresh = [r for r in rows if r["url"] not in known][:int(cfg.get("per_run") or 8)]
    watch.annotate(llm, fresh)
    write(store, [watch.to_row(r) for r in fresh], dry)
    return {"read": len(raw.get("rows") or []), "new": len(fresh), "hidden": sum(1 for r in fresh if r.get("relevant") is False)}


PARTS = (("community", do_community), ("folders", do_folders), ("myra", do_myra))


def prune(store: Any, now: datetime) -> None:
    for section, days in KEEP_DAYS.items():
        try:
            cutoff = (now - timedelta(days=days)).isoformat()
            store.table(WATCH).delete().eq("section", section).lt("created_at", cutoff).execute()
        except Exception as exc:  # noqa: BLE001 - retention never fails a sweep
            log.info("could not prune %s: %s", section, str(exc)[:100])


def run(store: Any, llm: Any, client: Any, now: datetime | None = None, only: list[str] | None = None,
        dry: bool = False) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cfg, stored = load_config(store)
    report: dict[str, Any] = {}
    if cfg.get("enabled") is False:
        return {"off": True}
    for name, fn in PARTS:
        if (only and name not in only) or cfg[name].get("enabled") is False:
            continue
        try:
            report[name] = {"ok": True, **fn(store, llm, client, cfg[name], now, dry)}
        except NeedsMigration:
            raise
        except Exception as exc:  # noqa: BLE001 - one dead source must not stop the other two
            report[name] = {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            log.warning("%s failed: %s", name, exc)
    if not dry:
        prune(store, now)
        store.table(db.SETTINGS).upsert({"key": KEY, "value": {**stored, "last_run": now.isoformat(), "report": report,
                                                                "force": False},        # the page's "Sweep now" is answered
                                         "updated_at": now.isoformat()}, on_conflict="key").execute()
        shown = sum(int((v.get("shown") or {}).get("reddit", 0)) + int((v.get("shown") or {}).get("youtube", 0))
                    for v in report.values() if isinstance(v, dict) and isinstance(v.get("shown"), dict))
        db.log_event(store, "info", "idea", "sources.sweep",
                     f"Sumber saya disapu: {shown} hujah, {(report.get('folders') or {}).get('angles', 0)} sudut folder, "
                     f"{(report.get('myra') or {}).get('new', 0)} penemuan MYRA",
                     detail={k: {a: b for a, b in v.items() if a != "errors"} for k, v in report.items()})
    return report


def main() -> int:
    from . import ai_config
    from .config import LLMSettings, SupabaseSettings
    from .foryou import ForYou
    from .llm import LLM

    key = os.environ.get("COMPOSIO_CONSUMER_KEY")
    if not key:
        print("COMPOSIO_CONSUMER_KEY is not set: the For You key that reaches Reddit, YouTube, OneDrive and Google Sheets")
        return 1
    dry = os.environ.get("SOURCES_DRY", "").lower() in ("1", "true", "yes")
    only = [p for p in os.environ.get("SOURCES_ONLY", "").replace(",", " ").split() if p] or None
    store = db.client(SupabaseSettings.load())
    llm = LLM(ai_config.llm_settings(LLMSettings.load(), ai_config.read(store)))
    try:
        report = run(store, llm, ForYou(key), only=only, dry=dry)
    except NeedsMigration as exc:
        print(f"::error::{exc}")
        return 1
    lines = [f"## Sources ({'DRY RUN, nothing written' if dry else 'written'})", ""]
    failed = 0
    for name, rep in report.items():
        if not isinstance(rep, dict):
            continue
        if rep.get("ok") is False:
            failed += 1
        lines.append(f"- **{name}**: " + ", ".join(f"{k}={v}" for k, v in rep.items() if k != "ok" and v not in (None, [], {})))
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 1 if report and failed == len([r for r in report.values() if isinstance(r, dict)]) else 0


if __name__ == "__main__":
    sys.exit(main())
