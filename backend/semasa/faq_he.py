"""The Halal Executive FAQ, mirrored into Semasa (Wan, 23 Oct 2026: "For FAQ, pull the FAQ from halal executive repo, and
if that faq in the repo update, so semasa also will update").

halal-executive (wanshah07/halal-executive) keeps its FAQ in a Google Sheet behind an Apps Script web app; the page there
reads `<exec url>?action=data`, whose `faq` list carries only PUBLISHED rows, each already written in English and Malay
(question_en/bm, answer_formal_en/bm, answer_layman_en/bm). So nothing here is rewritten: a row lands in semasa_faqs as
`ready`, with source_key `he:<id>`, and every scrape re-reads the feed and UPDATES a row whose words changed. A row the
feed no longer carries (unpublished or deleted there) is marked `dismissed`, never deleted, so Wan can see it went.

The exec URL is not in the repository (it is a deploy secret of that project): Wan pastes it once in Tetapan → FAQ
(settings.faq.he_api_url), or sets HE_API_URL on the scrape workflow. Without it this source reports "not configured"
and does nothing.

Category: Halal Executive's categories are halal topics, so a row files under Semasa's `halal` category with the HE
category + subcategory as the subcategory, unless Wan filed it himself (category_by = wan), which is never moved.
"""

from __future__ import annotations

import os
from typing import Any

from . import db, fetch
from .log import get_logger

log = get_logger("semasa.faq_he")

FAQS = "semasa_faqs"
SOURCE_NAME = "FAQ · Halal Executive"
SOURCE_URL = "https://halalexecutive.kkmhalalconsultant.com/#faq"
PREFIX = "he:"
CATEGORY = "halal"
TAG = "halal-executive"
# the fields a change in which means "update the row": the words, and the filing
MIRROR = ("question_bm", "question_en", "answer_bm", "answer_en", "subcategory")


def api_url(store: Any) -> str:
    """settings.faq.he_api_url, else HE_API_URL, else ''."""
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", "faq").execute().data or []
        url = str(((rows[0].get("value") or {}) if rows else {}).get("he_api_url") or "").strip()
    except Exception as exc:  # noqa: BLE001 - the env var still works
        log.info("faq settings not read (%s)", str(exc)[:120])
        url = ""
    return url or (os.environ.get("HE_API_URL") or "").strip()


def read_feed(url: str, *, timeout: int = 25) -> list[dict[str, Any]]:
    """The published FAQ rows the Apps Script answers with. Raises on anything that is not a feed."""
    r = fetch.get(f"{url}{'&' if '?' in url else '?'}action=data", timeout=timeout)
    data = r.json()
    if not isinstance(data, dict) or data.get("ok") is False:
        raise RuntimeError(str((data or {}).get("error") if isinstance(data, dict) else "not a JSON object")[:160])
    rows = data.get("faq")
    if not isinstance(rows, list):
        raise RuntimeError("the feed carries no `faq` list: is this the Halal Executive exec URL?")
    return [x for x in rows if isinstance(x, dict) and x.get("id")]


def to_row(he: dict[str, Any]) -> dict[str, Any]:
    """One semasa_faqs row from one Halal Executive row. Formal answer first; the layman one when that is all there is."""
    sub = " · ".join(s for s in (str(he.get("category") or "").strip(), str(he.get("subcategory") or "").strip()) if s)
    return {
        "source_kind": "auto",
        "source_key": f"{PREFIX}{he['id']}",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "status": "ready",
        "raw_question": str(he.get("question_en") or he.get("question_bm") or "").strip(),
        "raw_answer": str(he.get("answer_formal_en") or he.get("answer_layman_en") or "").strip(),
        "question_bm": str(he.get("question_bm") or "").strip(),
        "question_en": str(he.get("question_en") or "").strip(),
        "answer_bm": str(he.get("answer_formal_bm") or he.get("answer_layman_bm") or "").strip(),
        "answer_en": str(he.get("answer_formal_en") or he.get("answer_layman_en") or "").strip(),
        "category": CATEGORY,
        "subcategory": sub[:120],
        "tags": [TAG],
        "instrument": "",
        "answer_source": "given",
        "needs_check": False,
        "check_note": "",
        "error": None,
    }


def sync(store: Any, url: str, *, timeout: int = 25) -> dict[str, int]:
    """Mirror the feed: insert what is new, update what changed, dismiss what left. Raises when the feed cannot be read,
    so the scrape's source table shows it; a feed that reads fine but is empty changes nothing (never dismisses all)."""
    feed = read_feed(url, timeout=timeout)
    wanted = {r["source_key"]: r for r in (to_row(h) for h in feed) if r["question_bm"] or r["question_en"]}
    have = {r["source_key"]: r for r in db.fetch_all(lambda: store.table(FAQS).select("*").like("source_key", f"{PREFIX}%"))}
    added = updated = dismissed = 0
    for key, row in wanted.items():
        old = have.get(key)
        if old is None:
            store.table(FAQS).insert(row).execute()
            added += 1
            continue
        change = {k: row[k] for k in MIRROR if (old.get(k) or "") != row[k]}
        if old.get("status") == "dismissed":
            change["status"] = "ready"                            # published again
        if old.get("category_by") == "wan":
            change.pop("subcategory", None)                       # Wan's own filing is never moved
        if change:
            store.table(FAQS).update(change).eq("id", old["id"]).execute()
            updated += 1
    if wanted:
        for key, old in have.items():
            if key not in wanted and old.get("status") not in ("dismissed",):
                store.table(FAQS).update({"status": "dismissed"}).eq("id", old["id"]).execute()
                dismissed += 1
    log.info("%-28s faq    %d in the feed: %d new, %d updated, %d dismissed", SOURCE_NAME, len(wanted), added, updated, dismissed)
    return {"feed": len(wanted), "added": added, "updated": updated, "dismissed": dismissed}
