"""The bot keeps the FAQ categories in order: it adds a category or a subcategory when the entries need one, and it
moves entries out of "Lain-lain" once there is somewhere better for them (Wan, 25 Sep 2026: "bot can help to create
card/category based on context … if bot can automatically sort out is better").

Two ways the list grows, both held to rules/faq_categories.json "auto":
  a subcategory  proposed by the writer for ONE entry (semasa.faq.process), under a category that already exists
  a category     proposed by the sorter (run_sort) only when at least `min_group` entries fit it, so one odd
                 question never opens a category of its own

What it never does:
  - move an entry Wan placed by hand (category_by = 'wan'), unless the category he chose has since been deleted
  - create a name that matches an existing category, or one Wan deleted (settings.faq.declined)
  - grow past max_categories / max_subs
Everything it adds carries `auto: true` (a category) or sits in `auto_subs` (a subcategory), so Tetapan and the
FAQ dashboard can say "dicipta bot", and Wan can rename or delete it like any other.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import compliance, db
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.faq_sort")

FAQS = "semasa_faqs"
_RULES = json.loads((Path(__file__).resolve().parents[2] / "rules" / "faq_categories.json").read_text(encoding="utf-8"))
AUTO = _RULES.get("auto") or {}
MAX_CATEGORIES = int(AUTO.get("max_categories") or 12)
MAX_SUBS = int(AUTO.get("max_subs") or 10)
MIN_GROUP = int(AUTO.get("min_group") or 2)
SORT_BATCH = int(AUTO.get("sort_batch") or 40)
STOP = {"dan", "and", "the", "of", "untuk", "for", "serta", "yang"}

SORT_SYSTEM = """You sort entries of a Malaysian regulatory-affairs FAQ (halal, cosmetics, skincare, food,
pharmaceuticals, supplements) into categories.

CATEGORIES (key: Malay name [subcategories]): %s

For EVERY entry give the best category key and one of that category's subcategories (or ""). Use "lain" only when
nothing fits. When at least %d entries share a clear topic that no category covers, you may propose a new category
for them in "new_categories" and use its key for those entries. A new category must be broad enough to hold future
questions (for example "Label & penandaan", "Import & eksport"), never one product, company or incident. Names:
Malaysian Malay (never Bahasa Indonesia) and English, 1 to 4 words each.

Answer with ONE JSON object:
{"items": [{"id": "...", "category": "...", "subcategory": ""}],
 "new_categories": [{"key": "short_snake_case", "bm": "...", "en": "...", "subs": []}]}"""


# --- names ------------------------------------------------------------------------------------------------

def norm(s: Any) -> str:
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(w for w in re.split(r"[^a-z0-9]+", t) if w and w not in STOP)


def same_name(a: Any, b: Any) -> bool:
    """"Label & Penandaan" = "label dan penandaan" = "Penandaan label"; "Import" is inside "Import & eksport"."""
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 4 and re.search(rf"(?<![a-z0-9]){re.escape(short)}(?![a-z0-9])", long_):
        return True
    ta, tb = set(na.split()), set(nb.split())
    return len(ta & tb) / len(ta | tb) >= 0.6


def slug_key(name: str, taken: set[str]) -> str:
    base = "_".join(norm(name).split())[:28] or "kategori"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}_{n}", n + 1
    return key


def clean_name(s: Any, n: int = 40) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip(" .,:;-")[:n]


def find_category(cats: list[dict[str, Any]], *names: Any) -> str | None:
    for c in cats:
        for n in names:
            if n and any(same_name(n, x) for x in (c["key"], c["bm"], c["en"])):
                return c["key"]
    return None


def declined_of(settings: dict[str, Any]) -> list[str]:
    faq = settings.get("faq") if isinstance(settings.get("faq"), dict) else {}
    return [str(x) for x in (faq.get("declined") or []) if str(x).strip()]


def is_declined(declined: list[str], *names: Any) -> bool:
    return any(n and same_name(n, d) for n in names for d in declined)


def bad_words(*names: str) -> bool:
    """A bot-made name is shown to clients in exports: an Indonesian word in it is not accepted."""
    return any(compliance.indo_hits(n, []) for n in names if n)


# --- growing the list (pure: the caller saves) -------------------------------------------------------------

def add_sub(cats: list[dict[str, Any]], key: str, sub: Any, declined: list[str] | None = None) -> str:
    """Add one bot subcategory under `key` (in place). Returns the sub to use: an existing one that means the
    same, the new one, or "" when it cannot be added (cap, declined, Indonesian, unknown category)."""
    name = clean_name(sub)
    cat = next((c for c in cats if c["key"] == key), None)
    if not name or cat is None or key == "lain":
        return ""
    same = next((s for s in cat["subs"] if same_name(s, name)), None)
    if same:
        return same
    if len(cat["subs"]) >= MAX_SUBS or is_declined(declined or [], name) or bad_words(name):
        return ""
    cat["subs"].append(name)
    cat.setdefault("auto_subs", []).append(name)
    return name


def add_category(cats: list[dict[str, Any]], proposal: dict[str, Any], declined: list[str] | None = None,
                 when: str | None = None) -> str:
    """Add one bot category (in place, before "lain"). Returns the key to use: an existing category that means the
    same, the new key, or "lain" when it cannot be added."""
    bm, en = clean_name(proposal.get("bm")), clean_name(proposal.get("en"))
    bm = bm or en
    en = en or bm
    if not bm:
        return "lain"
    same = find_category(cats, bm, en)
    if same:
        return same
    if len(cats) >= MAX_CATEGORIES or is_declined(declined or [], bm, en) or bad_words(bm):
        return "lain"
    key = slug_key(proposal.get("key") or en or bm, {c["key"] for c in cats})
    subs: list[str] = []
    for s in proposal.get("subs") or []:
        name = clean_name(s)
        if name and not any(same_name(name, x) for x in subs) and not bad_words(name) and len(subs) < MAX_SUBS:
            subs.append(name)
    entry = {"key": key, "bm": bm, "en": en, "subs": subs, "auto": True,
             "auto_at": when or datetime.now(UTC).isoformat()}
    at = next((i for i, c in enumerate(cats) if c["key"] == "lain"), len(cats))
    cats.insert(at, entry)
    return key


def save_growth(store: Any, added_cats: list[dict[str, Any]], added_subs: list[tuple[str, str]],
                stamp: str | None = None) -> bool:
    """Write the bot's additions into the LIVE list. The list is read again first, so an edit Wan saved in
    Tetapan while this run was working is kept, and the additions are merged on top of it."""
    if not added_cats and not added_subs:
        return False
    from .faq import categories
    got = store.table(db.SETTINGS).select("key,value").eq("key", "faq").limit(1).execute().data or []
    value = dict(got[0]["value"]) if got and isinstance(got[0].get("value"), dict) else {}
    fresh = categories({"faq": value})
    declined = declined_of({"faq": value})
    for c in added_cats:
        add_category(fresh, c, declined, c.get("auto_at"))
    for key, sub in added_subs:
        add_sub(fresh, key, sub, declined)
    # the sorter passes its own start time: what it looked at in this pass already saw the new category
    value.update(categories=fresh, changed_at=stamp or datetime.now(UTC).isoformat())
    if got:
        store.table(db.SETTINGS).update({"value": value}).eq("key", "faq").execute()
    else:
        store.table(db.SETTINGS).insert({"key": "faq", "value": value}).execute()
    return True


# --- sorting -----------------------------------------------------------------------------------------------

def when(s: Any) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def to_sort(rows: list[dict[str, Any]], cats: list[dict[str, Any]], changed_at: Any) -> list[dict[str, Any]]:
    """Ready entries worth another look: in Lain-lain (unless Wan put them there) and not looked at since the list
    last changed, or in a category that no longer exists."""
    keys = {c["key"] for c in cats}
    changed = when(changed_at)
    out = []
    for r in rows:
        cat = r.get("category") or "lain"
        if cat != "lain" and cat not in keys:
            out.append(r)
        elif cat == "lain" and r.get("category_by") != "wan":
            seen = when(r.get("sorted_at"))
            if seen is None or (changed is not None and seen < changed):
                out.append(r)
    out.sort(key=lambda r: str(r.get("created_at") or ""))
    return out[:SORT_BATCH]


SORT_PAUSE = timedelta(hours=3)


def recent_failure(store: Any) -> bool:
    try:
        cutoff = (datetime.now(UTC) - SORT_PAUSE).isoformat()
        return bool(store.table(db.LOG).select("id").eq("event", "faq.sort_failed").gt("at", cutoff)
                    .limit(1).execute().data)
    except Exception:  # noqa: BLE001 - no log table: no pause
        return False


def listing(cats: list[dict[str, Any]]) -> str:
    return "; ".join(f"{c['key']}: {c['bm']} [{', '.join(c['subs'])}]" for c in cats)


def run_sort(store: Any, llm: LLM, settings: dict[str, Any], cats: list[dict[str, Any]]) -> str:
    """One pass over the entries worth another look. Never raises; returns a line for the job summary."""
    try:
        return _sort(store, llm, settings, cats)
    except Exception as exc:  # noqa: BLE001 - sorting is housekeeping; it never stops the worker
        log.warning("sort failed: %s", exc)
        return f"sort: FAILED ({type(exc).__name__}: {str(exc)[:120]})"


def _sort(store: Any, llm: LLM, settings: dict[str, Any], cats: list[dict[str, Any]]) -> str:
    try:
        rows = db.fetch_all(lambda: store.table(FAQS)
                            .select("id,question_bm,answer_bm,category,subcategory,category_by,sorted_at,created_at")
                            .eq("status", "ready").order("id"))
    except Exception as exc:  # noqa: BLE001
        return f"sort: skipped ({str(exc)[:100]})"
    faq_settings = settings.get("faq") if isinstance(settings.get("faq"), dict) else {}
    todo = to_sort(rows, cats, faq_settings.get("changed_at"))
    if not todo:
        return "sort: nothing to sort"
    now = datetime.now(UTC).isoformat()
    keys = {c["key"] for c in cats}

    if not llm.configured:
        # no writer: an entry whose category was deleted still gets a home, and nothing else moves
        moved = 0
        for r in todo:
            if (r.get("category") or "lain") not in keys:
                store.table(FAQS).update({"category": "lain", "subcategory": "", "category_by": "bot",
                                          "sorted_at": now}).eq("id", r["id"]).execute()
                moved += 1
        return f"sort: no LLM key; {moved} entr{'y' if moved == 1 else 'ies'} from deleted categories put in Lain-lain"

    user = "ENTRIES:\n" + "\n".join(
        json.dumps({"id": r["id"], "q": (r.get("question_bm") or "")[:300], "a": (r.get("answer_bm") or "")[:300]},
                   ensure_ascii=False) for r in todo)
    if recent_failure(store):
        return "sort: waiting after a failed try (again within 3 hours)"
    out = llm.chat_json(SORT_SYSTEM % (listing(cats), MIN_GROUP), user, max_tokens=3000)
    if not isinstance(out, dict) or not isinstance(out.get("items"), list):
        log.warning("sorter did not answer")
        # one warning, and a pause: a model that keeps answering badly must not cost a call every worker run
        db.log_event(store, "warn", "faq", "faq.sort_failed",
                     "Susunan automatik FAQ gagal: AI tidak menjawab dengan betul; cuba semula dalam 3 jam",
                     detail={"looked_at": len(todo)})
        return "sort: the writer did not answer; tried again in 3 hours"

    picks = {str(i.get("id")): i for i in out["items"] if isinstance(i, dict) and i.get("id")}
    declined = declined_of(settings)

    # a proposed category is only opened when enough entries go to it
    proposals = [p for p in (out.get("new_categories") or []) if isinstance(p, dict)]
    counts: dict[str, int] = {}
    for p in picks.values():
        counts[str(p.get("category") or "")] = counts.get(str(p.get("category") or ""), 0) + 1
    alias: dict[str, str] = {}
    added_cats: list[dict[str, Any]] = []
    for p in proposals:
        pk = str(p.get("key") or "").strip()
        if not pk or pk in keys:
            continue
        if counts.get(pk, 0) < MIN_GROUP:
            alias[pk] = find_category(cats, p.get("bm"), p.get("en")) or "lain"
            continue
        before = len(cats)
        alias[pk] = add_category(cats, p, declined, now)
        if len(cats) > before:
            added_cats.append(next(c for c in cats if c["key"] == alias[pk]))
    keys = {c["key"] for c in cats}
    if added_cats:
        save_growth(store, added_cats, [], now)  # the list first: an entry never points at a category not saved

    moved: dict[str, int] = {}
    for r in todo:
        p = picks.get(str(r["id"])) or {}
        cat = str(p.get("category") or "").strip()
        cat = alias.get(cat, cat)
        if cat not in keys:
            cat = "lain"
        subs = next(c["subs"] for c in cats if c["key"] == cat)
        sub = next((s for s in subs if s.lower() == str(p.get("subcategory") or "").strip().lower()), "")
        patch = {"sorted_at": now}
        was = r.get("category") or "lain"
        if cat != was or was not in keys:
            patch.update(category=cat, subcategory=sub, category_by="bot")
            if cat != "lain":
                moved[cat] = moved.get(cat, 0) + 1
        store.table(FAQS).update(patch).eq("id", r["id"]).execute()

    names = {c["key"]: c["bm"] for c in cats}
    total = sum(moved.values())
    if total or added_cats:
        parts = [f"{n} ke {names[k]}" for k, n in sorted(moved.items(), key=lambda kv: -kv[1])]
        title = f"Bot menyusun {total} FAQ" + (f": {', '.join(parts)}" if parts else "")
        if added_cats:
            title += "; kategori baharu: " + ", ".join(c["bm"] for c in added_cats)
        db.log_event(store, "info", "faq", "faq.sorted", title,
                     detail={"moved": moved, "new_categories": [c["bm"] for c in added_cats], "looked_at": len(todo)})
    return f"sort: {len(todo)} looked at, {total} moved, {len(added_cats)} new categor{'y' if len(added_cats) == 1 else 'ies'}"
