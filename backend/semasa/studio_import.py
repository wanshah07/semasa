"""Studio's live queue into Semasa, once, on the night Studio is retired (Wan, 29 Sep 2026: "all post from friday night
move to semasa"). Entry point: `python -m semasa.studio_import` (studio-import.yml), fed by the cutover session.

The session reads Studio's store, proves every card's address in `argus-cards` (md5 against Studio's own bytes), and
hands this module the posts already shaped for Semasa (ops/studio_cutover.py). This module only writes them, as the
service role, keyed by the SAME ids the 27 Sep import used (uuid5 of Studio's id), so a post brought over then as a
draft is brought up to date rather than doubled, and running it twice changes nothing.

What each Studio post becomes
  approved, nothing in Buffer yet   approved      Semasa's publisher sends it at its slot (your click in Studio stands)
  approved, SOME channels in Buffer approved      those channels keep Studio's Buffer ids; the publisher sends the rest
  in Buffer on every channel        scheduled     Semasa never sends it again; its tally marks it posted once it fires
  posted                            posted        history
  draft                             draft         waits for your click in Semasa
  rejected                          (skipped)

A post Semasa has ALREADY scheduled or sent is never overwritten by Studio's copy. Pictures come over as one media row
per post (mode 'slides', status done) pointing at the proven `argus-cards` addresses; nothing is uploaded here.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from . import compliance, db
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.studio_import")

LOCKED = ("scheduled", "posted")
POST_FIELDS = ("stream", "domain", "angle", "lang", "hook", "text", "citation", "slides", "date", "slot", "status",
               "published", "approved_at")


def media_row(row: dict[str, Any]) -> dict[str, Any] | None:
    m = row.get("media")
    if not m or not m.get("urls"):
        return None
    return {"id": m["id"], "post_id": row["id"], "type": "image", "mode": "slides", "status": "done",
            "reference_url": None, "generated_media_url": m["urls"][0], "prompt": "",
            "meta": {"slide_urls": list(m["urls"]), "slides": row.get("slides") or [], "alt": m.get("alt") or "",
                     "from": "ws.regulab Studio", "studio_media_ids": m.get("studio_ids") or [],
                     "md5": m.get("md5") or []}}


def post_row(row: dict[str, Any], brand: dict[str, Any]) -> dict[str, Any]:
    out = {k: row.get(k) for k in POST_FIELDS}
    out["id"] = row["id"]
    m = media_row(row)
    out["media_ids"] = [m["id"]] if m else []
    scan_media = [{"alt": m["meta"]["alt"], "slides": m["meta"]["slides"]}] if m else []
    flags = compliance.scan({**out, "media": scan_media}, brand=brand)
    out["flags"], out["hard_flags"] = flags, compliance.hard_count(flags)
    if out["status"] in LOCKED:
        out["flags"], out["hard_flags"] = [], 0
    return out


def apply(store: Any, rows: list[dict[str, Any]], dry: bool = False) -> dict[str, Any]:
    settings = {r["key"]: r["value"] for r in (store.table(db.SETTINGS).select("key,value").execute().data or [])}
    brand = (settings.get("brand") or {}).get("regulab") or {}
    ids = [r["id"] for r in rows]
    existing = {r["id"]: r for r in (store.table(db.POSTS).select("id,status,date,slot,stream").in_("id", ids)
                                     .execute().data or [])}
    report: dict[str, Any] = {"written": [], "kept_semasa": [], "clashes": [], "hard": [], "dry": dry}
    dates = sorted({r["date"] for r in rows if r.get("date")})
    others = (store.table(db.POSTS).select("id,stream,date,slot,status,hook").in_("date", dates)
              .neq("status", "rejected").execute().data or []) if dates else []
    held = {(o["stream"], str(o["date"]), o["slot"]): o for o in others if o["id"] not in set(ids)}
    for row in rows:
        ex = existing.get(row["id"])
        if ex and ex["status"] in LOCKED and row["status"] not in LOCKED:
            report["kept_semasa"].append(row["studio_id"])
            continue
        clash = held.get((row["stream"], str(row.get("date")), row.get("slot")))
        if clash:
            report["clashes"].append(f"{row['studio_id']} and Semasa post {clash['id']} both hold "
                                     f"{row['stream']} {row['date']} {row['slot']}")
        post = post_row(row, brand)
        if post["hard_flags"] and post["status"] == "approved":
            report["hard"].append(f"{row['studio_id']}: " + "; ".join(
                f"{f['where']}: {f['msg']}" for f in post["flags"] if f["hard"]))
        report["written"].append(f"{row['studio_id']} -> {post['status']} {post['date']} {post['slot']} "
                                 f"({len((row.get('media') or {}).get('urls') or [])} picture(s))")
        if dry:
            continue
        m = media_row(row)
        store.table(db.POSTS).upsert(post, on_conflict="id").execute()      # the post first: the picture row points at it
        if m:
            store.table(db.MEDIA).upsert(m, on_conflict="id").execute()
    if not dry and report["written"]:
        db.log_event(store, "info", "post", "studio.import",
                     f"{len(report['written'])} post dari ws.regulab Studio dipindahkan ke Semasa",
                     detail={"posts": len(report["written"]), "clashes": len(report["clashes"])})
    return report


def main() -> int:
    raw = os.environ.get("STUDIO_IMPORT", "")
    if raw.strip().endswith(".json") and not raw.lstrip().startswith("{"):     # a file name under ops/import/, from the
        root = os.environ.get("GITHUB_WORKSPACE", "..")                          # cutover branch: exact bytes, no retyping
        with open(os.path.join(root, "ops", "import", os.path.basename(raw.strip())), encoding="utf-8") as fh:
            raw = fh.read()
    dry = os.environ.get("STUDIO_IMPORT_DRY", "true").lower() != "false"
    try:
        rows = json.loads(raw)["posts"]
    except (ValueError, KeyError, TypeError) as exc:
        log.error("studio import: the message is not {\"posts\": [...]}: %s", exc)
        return 1
    store = db.client(SupabaseSettings.load())
    report = apply(store, rows, dry=dry)
    lines = [f"## Studio import ({'DRY RUN, nothing written' if dry else 'written'})", ""]
    for key, title in (("written", "Posts"), ("kept_semasa", "Kept Semasa's own (already scheduled or sent)"),
                       ("clashes", "Slot clashes (both kept; move one)"), ("hard", "Approved but blocked by a check")):
        if report[key]:
            lines += [f"**{title}**", *[f"- {x}" for x in report[key]], ""]
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
