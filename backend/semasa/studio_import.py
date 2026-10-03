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

Studio's still-open IDEAS (the regulatory notices its sweep found and Wan had not yet turned into a post) come over as
rows in `semasa_watch` (the Regulatory row of Isu semasa), where "Jadikan idea" is Wan's click, exactly as "Approve ->
draft" was in Studio. They are NEVER written to `semasa_ideas`: a new idea there wakes the worker, which drafts it at once.
An idea whose reference or name already appears in an approved, scheduled or posted post is skipped, so nothing Studio
already put in Buffer is touched or repeated (Wan, 3 Oct 2026). Posts are never written by this path.

A post Semasa has ALREADY scheduled or sent is never overwritten by Studio's copy. Pictures come over as one media row
per post (mode 'slides', status done) pointing at the proven `argus-cards` addresses; nothing is uploaded here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Any

from . import compliance, db
from .config import SupabaseSettings
from .log import get_logger

log = get_logger("semasa.studio_import")

LOCKED = ("scheduled", "posted")
LIVE = ("approved", "scheduled", "posted")
WATCH = "semasa_watch"
SAHKAN = re.compile(r"\s*\[SAHKAN[^\]]*\]", re.I)
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


def watch_row(i: dict[str, Any]) -> dict[str, Any]:
    """One open Studio idea as a Regulatory row. The `[SAHKAN: ...]` caveats Studio's sweep left in the note are lifted out
    of the words (a writer would copy them into a caption) and kept in `raw.caveat`; the link is whatever the idea
    carried, else the regulator's register with the reference after a `#`, which opens the right site and never claims to
    be a page about this finding."""
    note = str(i.get("note") or "")
    caveats = [m.strip() for m in re.findall(r"\[SAHKAN[^\]]*\]", note, re.I)]
    note = SAHKAN.sub("", note).strip()
    summary, _, why = note.partition("Sudut:")
    raw = {"from": "ws.regulab Studio idea", "studio_id": i["studio_id"], "ref": i.get("ref_no") or "",
           "tier": i.get("tier") or "", "markets": i.get("markets") or [], "evidence": i.get("evidence") or "",
           "caveat": "; ".join(caveats) or ("Studio's sweep did not record a link of its own for this finding: check the "
                                            "reference in the register before posting" if not i.get("evidence") else "")}
    return {"section": "regulatory", "source": i["source"], "kind": i.get("kind"), "country": i.get("country"),
            "title": i["title"], "url": i["url"], "summary": summary.strip() or None, "why": why.strip() or None,
            "domain": i.get("domain") or "kosmetik", "relevant": True, "dismissed": False, "lang": "ms",
            "summary_source": "source", "published_at": i.get("at"), "status": "ready", "pasted": False,
            "raw": {k: v for k, v in raw.items() if v not in ("", [], None)}}


def apply_ideas(store: Any, ideas: list[dict[str, Any]], dry: bool = False) -> dict[str, Any]:
    """Open Studio ideas into the Regulatory feed. Writes only `semasa_watch`, only rows whose link is new, and none whose
    reference or name an approved, scheduled or posted post already carries."""
    report: dict[str, Any] = {"written": [], "already_there": [], "already_posted": [], "dry": dry}
    live = (store.table(db.POSTS).select("id,status,hook,citation,text").in_("status", list(LIVE)).execute().data or [])
    blobs = [(p, json.dumps([p.get("hook"), p.get("citation"), p.get("text")], ensure_ascii=False).lower()) for p in live]
    have = {r["url"] for r in (store.table(WATCH).select("url").in_("url", [i["url"] for i in ideas]).execute().data or [])}
    fresh = []
    for i in ideas:
        terms = [t.lower() for t in ([i.get("ref_no")] if i.get("ref_no") else []) + list(i.get("match") or []) if t]
        hit = next((p for p, blob in blobs if any(t in blob for t in terms)), None)
        if hit:
            report["already_posted"].append(f"{i['studio_id']} is already in post {hit['id']} ({hit['status']})")
        elif i["url"] in have:
            report["already_there"].append(i["studio_id"])
        else:
            fresh.append(i)
            report["written"].append(f"{i['studio_id']} -> {i['source']}: {i['title'][:70]}")
    if fresh and not dry:
        store.table(WATCH).upsert([watch_row(i) for i in fresh], on_conflict="url", ignore_duplicates=True).execute()
        db.log_event(store, "info", "system", "studio.ideas",
                     f"{len(fresh)} idea terbuka dari ws.regulab Studio dimasukkan ke Regulatory",
                     detail={"ideas": [i["studio_id"] for i in fresh]})
    return report


def main() -> int:
    raw = os.environ.get("STUDIO_IMPORT", "")
    dry = os.environ.get("STUDIO_IMPORT_DRY", "true").lower() != "false"
    try:
        msg = json.loads(raw)
        rows, ideas = list(msg.get("posts") or []), list(msg.get("ideas") or [])
        if not rows and not ideas:
            raise KeyError("posts")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        log.error("studio import: the message is not {\"posts\": [...]} or {\"ideas\": [...]}: %s", exc)
        return 1
    store = db.client(SupabaseSettings.load())
    report = apply(store, rows, dry=dry) if rows else {"written": [], "kept_semasa": [], "clashes": [], "hard": []}
    lines = [f"## Studio import ({'DRY RUN, nothing written' if dry else 'written'})", "",
             # proves the pasted message arrived byte for byte: compare with the sha256 of the file it was made from
             f"message: {len(raw)} characters, sha256 {hashlib.sha256(raw.encode()).hexdigest()[:16]}", ""]
    for key, title in (("written", "Posts"), ("kept_semasa", "Kept Semasa's own (already scheduled or sent)"),
                       ("clashes", "Slot clashes (both kept; move one)"), ("hard", "Approved but blocked by a check")):
        if report[key]:
            lines += [f"**{title}**", *[f"- {x}" for x in report[key]], ""]
    if ideas:
        irep = apply_ideas(store, ideas, dry=dry)
        for key, title in (("written", "Ideas into Regulatory"), ("already_there", "Already in the feed (same link)"),
                           ("already_posted", "Skipped: already in a post (left alone)")):
            if irep[key]:
                lines += [f"**{title}**", *[f"- {x}" for x in irep[key]], ""]
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
