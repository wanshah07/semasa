"""FAQ: a question (and its answer, when there is one) in, a clean bilingual entry out.

Three ways in, one row (`semasa_faqs`, supabase/007_faq.sql):
  paste     Wan pastes a Q&A in the FAQ tab (status `new`)
  headline  "Jadikan FAQ" on a scraped headline: the article is read and one FAQ drawn from it
  auto      the scraper collects Q&A-shaped items as `candidate`s (semasa.faq_sources); nothing is
            rewritten until Wan accepts one, which makes it `new`

`run()` (called by the media worker, right after the ideas) rewrites every `new` row into Malay
and English, anonymises it, picks a category from the live list, and marks it `ready`. Wan chose
on 25 Sep 2026 to publish the rewrite as it comes: `needs_check` is a warning on the entry, never
a gate. What the writer may NOT do is add a fact: a figure, clause, fee, date or instrument that
is not in the input stays out, and an uncertain answer keeps its uncertainty.

`sync_sheet()` mirrors every `ready` row into the Semasa FAQ Google Sheet through its Apps Script
(apps-script/Code.gs): the whole list, replaced, whenever it has changed. So an edit or a delete in
the page reaches the sheet on the next run, and the sheet can never drift from the database.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import compliance, db, faq_sort, sheet
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.faq")

FAQS = "semasa_faqs"
CATEGORIES_PATH = Path(__file__).resolve().parents[2] / "rules" / "faq_categories.json"
DEFAULT_CATEGORIES: list[dict[str, Any]] = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))["categories"]
STALE_MINUTES = 30
RAW_MAX = 6000

SYSTEM = """You turn a question and its answer into one clean FAQ entry, in Malaysian Malay AND English, for a
Malaysian regulatory-affairs knowledge base (halal, cosmetics, skincare, food, pharmaceuticals and supplements).

Rules. Follow them exactly:
1. Keep the substance of the answer and write it FIRMLY and FORMALLY, as a regulatory consultancy answering a
   client. Never hedge: drop "tak silap", "setahu kami", "rasanya", "apa yang saya nampak", "pada pendapat saya",
   "I think", "as far as we know" and the like, and state the point plainly. An answer drawn from practical
   experience is valid even when no guideline states it; do not invent a guideline for it. Do NOT add any fact,
   figure, fee, date, clause number, circular or instrument that is not in the input.
2. Anonymise. Remove the asker's name, company, customers, staff, phone numbers, emails, addresses and account
   handles. Keep a product or brand name only when it is the public subject of the question (for example an
   official clarification about that product).
3. The question is ONE self-contained question, neutral, with no greeting ("Salam", "Hi", "Tuan/Puan").
   The answer is 1 to 4 plain sentences. No call to action, no website, no "hubungi kami", no emoji.
4. Malaysian Malay only, never Bahasa Indonesia: boleh not bisa, ubat not obat, syarikat not perusahaan,
   kualiti not kualitas, pembungkusan not kemasan, kebenaran not izin. English: plain and clear.
5. "category" is one key from CATEGORIES below; "subcategory" is one of that category's subs, or "". When the
   category fits but none of its subs does, you may propose ONE new subcategory in "new_subcategory": Malaysian
   Malay, 1 to 4 words, general enough for future questions (for example "Tarikh luput"), never a product or
   company name. Otherwise "new_subcategory" is "".
6. "instrument" names the regulator or instrument ONLY if the input names it (for example "JAKIM, Penjelasan Isu
   Tular Halal" or "MPPHM (Domestik) 2020"); otherwise "". Never a social platform, forum or news portal.
7. If the input has NO answer, write your best short answer, set "answer_source" to "ai" and "needs_check" true.
   Otherwise "answer_source" is "given".
8. "needs_check" is true ONLY when you know the answer conflicts with a current regulation (or rule 7 applies);
   "check_note" then says in ONE Malay sentence what conflicts. Never set it merely because no instrument is
   cited: many good answers come from experience. Otherwise "needs_check" is false and "check_note" is "".

CATEGORIES: %s

Answer with ONE JSON object:
{"question_bm": "...", "answer_bm": "...", "question_en": "...", "answer_en": "...", "category": "...",
 "subcategory": "...", "new_subcategory": "", "tags": ["up to 5 short lowercase tags"], "instrument": "",
 "answer_source": "given", "needs_check": false, "check_note": ""}"""

HEADLINE_NOTE = ("This input is a NEWS ARTICLE, not a question. Write the ONE question a Malaysian business owner or "
                 "consumer would most likely ask about it, and answer it only from the ARTICLE. "
                 "The publisher's name never appears in the entry.")


HEDGES = [re.compile(r"(?<![a-z])(?:" + h + r")(?![a-z])", re.I)
          for h in json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))["hedges"]]
FIRM_RETRY = ("Your answer still hedges ({found}). Rewrite the SAME entry so every sentence is a firm, formal "
              "statement with no hedging words. Same JSON shape.")


def hedges_in(fields: dict[str, Any]) -> list[str]:
    """Hedging phrases left in any of the four texts, as found (lower-case, unique, in order)."""
    found: list[str] = []
    for k in ("question_bm", "answer_bm", "question_en", "answer_en"):
        for rx in HEDGES:
            for m in rx.finditer(fields.get(k) or ""):
                if m.group(0).lower() not in found:
                    found.append(m.group(0).lower())
    return found


def strip_leading_hedges(text: str) -> str:
    """Remove a hedge that opens a sentence ("Setahu kami, format…" → "Format…"). A hedge in the middle of
    a sentence is left for the retry or the flag: cutting it out blind can break the grammar."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", text.strip()):
        changed = True
        while changed:
            changed = False
            for rx in HEDGES:
                m = rx.match(sent)
                if m:
                    sent = sent[m.end():].lstrip(" ,;:-–").lstrip()
                    changed = True
        if sent:
            out.append(sent[0].upper() + sent[1:])
    return " ".join(out)


class FaqError(RuntimeError):
    """A failure shown on the entry in the page."""


# --- categories -------------------------------------------------------------------------

def categories(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """The live list from semasa_settings.faq, else the defaults. Every entry has key/bm/en/subs; one the bot made
    also keeps `auto`/`auto_at`, and `auto_subs` names the subcategories the bot added (semasa.faq_sort)."""
    raw = ((settings.get("faq") or {}).get("categories")) if isinstance(settings.get("faq"), dict) else None
    out = []
    for c in raw if isinstance(raw, list) and raw else DEFAULT_CATEGORIES:
        if isinstance(c, dict) and str(c.get("key") or "").strip():
            entry = {"key": str(c["key"]).strip(), "bm": str(c.get("bm") or c["key"]), "en": str(c.get("en") or c["key"]),
                     "subs": [str(s) for s in (c.get("subs") or []) if str(s).strip()]}
            if c.get("auto"):
                entry.update(auto=True, auto_at=c.get("auto_at"))
            auto_subs = [str(s) for s in (c.get("auto_subs") or []) if str(s) in entry["subs"]]
            if auto_subs:
                entry["auto_subs"] = auto_subs
            out.append(entry)
    if not any(c["key"] == "lain" for c in out):
        out.append({"key": "lain", "bm": "Lain-lain", "en": "Other", "subs": []})
    return out


def pick_category(cats: list[dict[str, Any]], key: Any, sub: Any) -> tuple[str, str]:
    """The writer's choice, held to the list: an unknown category is `lain`, an unknown sub is ""."""
    by_key = {c["key"]: c for c in cats}
    k = str(key or "").strip().lower()
    if k not in by_key:
        return "lain", ""
    s = str(sub or "").strip()
    subs = by_key[k]["subs"]
    match = next((x for x in subs if x.lower() == s.lower()), "")
    return k, match


# --- the rewrite --------------------------------------------------------------------------

def build_request(row: dict[str, Any], cats: list[dict[str, Any]], article: dict[str, Any] | None,
                  indo_extra: Any = None) -> tuple[str, str]:
    listing = "; ".join(f"{c['key']} ({c['bm']}: {', '.join(c['subs']) or 'no subs'})" for c in cats)
    system = SYSTEM % listing + compliance.avoid_line(indo_extra)
    parts = []
    wanted = preset(row, cats)
    if wanted:
        parts.append(f"CATEGORY WANTED (Wan chose it; use it): {wanted[0]}" + (f" / {wanted[1]}" if wanted[1] else ""))
    if row.get("source_kind") == "headline":
        parts.append(HEADLINE_NOTE)
        parts.append(f"HEADLINE: {row.get('raw_question') or ''}")
        if article and article.get("ok"):
            bits = [article.get(k) or "" for k in ("title", "description", "text")]
            parts.append("ARTICLE:\n" + "\n".join(bits))
        else:
            parts.append(f"ARTICLE: only the headline and this summary could be read: {row.get('raw_answer') or ''}")
    else:
        parts.append(f"QUESTION:\n{(row.get('raw_question') or '').strip()[:RAW_MAX]}")
        ans = (row.get("raw_answer") or "").strip()
        parts.append(f"ANSWER:\n{ans[:RAW_MAX]}" if ans else "ANSWER: (none given)")
        if row.get("source_name"):
            parts.append(f"WHERE IT CAME FROM (for your understanding only; never name a social site): {row['source_name']}")
    return system, "\n\n".join(parts)


def preset(row: dict[str, Any], cats: list[dict[str, Any]]) -> tuple[str, str] | None:
    """A category Wan chose by hand (category_by = 'wan') is kept through every rewrite. The bot's own earlier
    pick is not: a rewrite chooses again, so a better category made since can win. Wan choosing Lain-lain counts."""
    key = str(row.get("category") or "").strip()
    if row.get("category_by") != "wan" or not key or key not in {c["key"] for c in cats}:
        return None
    return pick_category(cats, key, row.get("subcategory"))


def clean(out: dict[str, Any], cats: list[dict[str, Any]], had_answer: bool) -> dict[str, Any]:
    def s(k: str, n: int = 4000) -> str:
        return str(out.get(k) or "").strip()[:n]
    fields = {k: s(k) for k in ("question_bm", "answer_bm", "question_en", "answer_en")}
    missing = [k for k, v in fields.items() if not v]
    if missing:
        raise FaqError(f"the writer left {', '.join(missing)} empty; press Cuba lagi")
    cat, sub = pick_category(cats, out.get("category"), out.get("subcategory"))
    tags = [str(t).strip().lower()[:40] for t in (out.get("tags") or []) if str(t).strip()][:5] \
        if isinstance(out.get("tags"), list) else []
    answer_source = "given" if had_answer and out.get("answer_source") != "ai" else "ai"
    needs = bool(out.get("needs_check")) or answer_source == "ai"
    note = s("check_note", 500)
    if answer_source == "ai" and not note:
        note = "Tiada jawapan diberi: jawapan ini ditulis oleh AI dan perlu disemak."
    return {**fields, "category": cat, "subcategory": sub, "tags": tags, "instrument": s("instrument", 300),
            "answer_source": answer_source, "needs_check": needs, "check_note": note if needs else "",
            "_new_sub": "" if sub else s("new_subcategory", 60)}


def indo_note(fields: dict[str, Any], indo_extra: Any) -> str:
    """One Malay sentence naming any Indonesian word left in the Malay text, or ""."""
    msgs = compliance.indo_hits(f"{fields['question_bm']}\n{fields['answer_bm']}", compliance.tabung(indo_extra))
    words = [m.split('"')[1] for m in msgs]
    return f"Perkataan Indonesia dalam teks BM: {', '.join(words)}. Tukar kepada perkataan Malaysia." if words else ""


def process(store: Any, llm: LLM, row: dict[str, Any], cats: list[dict[str, Any]], indo_extra: Any = None,
            grown: list[tuple[str, str]] | None = None, declined: list[str] | None = None) -> None:
    """Rewrite one entry. A new subcategory the writer proposes is added to `cats` in place and noted in `grown`
    for run() to save once."""
    if not llm.configured:
        raise FaqError("no LLM key: set the LLM_API_KEY secret (the writer needs it)")
    article = None
    if row.get("source_kind") == "headline" and row.get("source_url"):
        from .ideas import read_source
        article = read_source(row["source_url"])
    system, user = build_request(row, cats, article, indo_extra)
    out = llm.chat_json(system, user, max_tokens=2500)
    if not isinstance(out, dict) or not out:
        raise FaqError("the writer did not answer (see the run log); press Cuba lagi")
    had_answer = bool((row.get("raw_answer") or "").strip()) or row.get("source_kind") == "headline"
    fields = clean(out, cats, had_answer)
    found = hedges_in(fields)
    if found:                                  # Wan: firm, formal answers. One retry, then trim, then flag.
        again = llm.chat_json(system, user + "\n\n" + FIRM_RETRY.format(found=", ".join(found)), max_tokens=2500)
        if isinstance(again, dict) and again:
            try:
                fields = clean(again, cats, had_answer)
            except FaqError:
                pass                           # keep the first answer; it is complete
        for k in ("question_bm", "answer_bm", "question_en", "answer_en"):
            fields[k] = strip_leading_hedges(fields[k])
        left = hedges_in(fields)
        if left:
            fields["needs_check"] = True
            fields["check_note"] = (fields["check_note"] + f" Masih ada ayat ragu: {', '.join(left)}. "
                                    "Sunting supaya jawapan tegas.").strip()
    slip = indo_note(fields, indo_extra)
    if slip:                                   # published as rewritten (Wan's choice), but never unflagged
        fields["needs_check"] = True
        fields["check_note"] = (fields["check_note"] + " " + slip).strip()
    wanted = preset(row, cats)
    if wanted:
        # Wan's category wins; his sub too, else the writer's sub when it belongs to that category
        subs = next(c["subs"] for c in cats if c["key"] == wanted[0])
        fields["subcategory"] = wanted[1] or (fields["subcategory"] if fields["subcategory"] in subs else "")
        fields["category"] = wanted[0]
    new_sub = fields.pop("_new_sub", "")
    if new_sub and not fields["subcategory"] and fields["category"] != "lain":
        before = sum(len(c["subs"]) for c in cats)
        fields["subcategory"] = faq_sort.add_sub(cats, fields["category"], new_sub, declined)
        if grown is not None and sum(len(c["subs"]) for c in cats) > before:
            grown.append((fields["category"], fields["subcategory"]))
    fields["category_by"] = "wan" if wanted else "bot"
    fields["sorted_at"] = None                 # a fresh answer: the sorter may look at it again
    store.table(FAQS).update({**fields, "status": "ready", "error": None}).eq("id", row["id"]).execute()


def recover_stale(store: Any) -> int:
    cutoff = (datetime.now(UTC) - timedelta(minutes=STALE_MINUTES)).isoformat()
    try:
        res = (store.table(FAQS).update({"status": "new", "error": "worker stopped before finishing; queued again"})
               .eq("status", "working").lt("updated_at", cutoff).execute())
        return len(res.data or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("could not recover stuck FAQs: %s", exc)
        return 0


def claim(store: Any, limit: int) -> list[dict[str, Any]]:
    rows = store.table(FAQS).select("*").eq("status", "new").order("created_at").limit(limit).execute().data or []
    got = []
    for row in rows:
        res = (store.table(FAQS).update({"status": "working", "attempts": int(row.get("attempts") or 0) + 1,
                                          "error": None})
               .eq("id", row["id"]).eq("status", "new").execute())
        if res.data:
            got.append(res.data[0])
    return got


def run(store: Any, llm: LLM, limit: int | None = None) -> str:
    """Rewrite waiting entries, then mirror the list to the sheet. Never raises."""
    limit = limit or int(os.environ.get("FAQ_BATCH") or 8)
    try:
        recovered = recover_stale(store)
        rows = claim(store, limit)
    except Exception as exc:  # noqa: BLE001 - a missing table (007 not run) must not stop media
        log.warning("FAQ step skipped: %s", exc)
        return f"FAQ: skipped ({str(exc)[:120]})"
    from .ideas import load_settings
    settings = load_settings(store)
    cats = categories(settings)
    declined = faq_sort.declined_of(settings)
    grown: list[tuple[str, str]] = []
    ok = 0
    for row in rows:
        try:
            process(store, llm, row, cats, (settings.get("bahasa") or {}).get("indo"), grown, declined)
            ok += 1
            log.info("faq %s ready", row["id"])
        except Exception as exc:  # noqa: BLE001 - recorded on the entry
            msg = str(exc) if isinstance(exc, FaqError) else f"{type(exc).__name__}: {str(exc)[:400]}"
            log.error("faq %s: %s", row["id"], msg)
            store.table(FAQS).update({"status": "error", "error": msg[:800]}).eq("id", row["id"]).execute()
    note = f"FAQ: {ok}/{len(rows)} rewritten" + (f"; {recovered} stuck re-queued" if recovered else "")
    if grown:
        try:
            faq_sort.save_growth(store, [], grown)
            db.log_event(store, "info", "faq", "faq.subcategory",
                         "Bot menambah subkategori: " + ", ".join(f"{s} ({k})" for k, s in grown),
                         detail={"added": [{"category": k, "subcategory": s} for k, s in grown]})
        except Exception as exc:  # noqa: BLE001 - the entries keep their sub; the list catches up next time
            log.warning("could not save new subcategories: %s", exc)
    settings = load_settings(store)             # the list as saved, with anything the rewrites added
    cats = categories(settings)
    note += "; " + faq_sort.run_sort(store, llm, settings, cats)
    return note + "; " + sync_sheet(store, settings, cats)


# --- the Google Sheet ----------------------------------------------------------------------

SHEET_FIELDS = ["id", "category_bm", "subcategory", "question_bm", "answer_bm", "question_en", "answer_en", "tags",
                "needs_check", "check_note", "instrument", "answer_source", "source_kind", "source_name",
                "source_url", "created_at", "updated_at"]


def sheet_rows(rows: list[dict[str, Any]], cats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    label = {c["key"]: c["bm"] for c in cats}
    order = {c["key"]: i for i, c in enumerate(cats)}
    rows = sorted(rows, key=lambda r: (order.get(r.get("category"), 99), r.get("subcategory") or "", r.get("created_at") or ""))
    out = []
    for r in rows:
        out.append({"id": r["id"], "category_bm": label.get(r.get("category"), r.get("category") or ""),
                    "subcategory": r.get("subcategory") or "", "question_bm": r.get("question_bm") or "",
                    "answer_bm": r.get("answer_bm") or "", "question_en": r.get("question_en") or "",
                    "answer_en": r.get("answer_en") or "", "tags": ", ".join(r.get("tags") or []),
                    "needs_check": "YA" if r.get("needs_check") else "", "check_note": r.get("check_note") or "",
                    "instrument": r.get("instrument") or "", "answer_source": r.get("answer_source") or "",
                    "source_kind": r.get("source_kind") or "", "source_name": r.get("source_name") or "",
                    "source_url": r.get("source_url") or "", "created_at": r.get("created_at") or "",
                    "updated_at": r.get("updated_at") or ""})
    return out


def sync_sheet(store: Any, settings: dict[str, Any], cats: list[dict[str, Any]]) -> str:
    """Replace the FAQ tabs of the Semasa sheet with every ready entry when the list has changed. Never raises."""
    if not sheet.configured():
        return "sheet: not configured (SEMASA_SHEET_URL / SEMASA_SHEET_TOKEN)"
    try:
        ready = store.table(FAQS).select("*").eq("status", "ready").limit(5000).execute().data or []
        rows = sheet_rows(ready, cats)
        digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        state = settings.get("faq_sheet") if isinstance(settings.get("faq_sheet"), dict) else {}
        if state.get("hash") == digest:
            return f"sheet: unchanged ({len(rows)} rows)"
        sheet.call("replace", {"fields": SHEET_FIELDS, "rows": rows})
        value = {"hash": digest, "rows": len(rows), "at": datetime.now(UTC).isoformat()}
        if "faq_sheet" in settings:
            store.table(db.SETTINGS).update({"value": value}).eq("key", "faq_sheet").execute()
        else:
            store.table(db.SETTINGS).insert({"key": "faq_sheet", "value": value}).execute()
        log.info("sheet: replaced with %d rows", len(rows))
        db.log_event(store, "info", "faq", "faq.sheet", f"Google Sheet dikemas kini: {len(rows)} soalan",
                     detail={"rows": len(rows)})
        return f"sheet: {len(rows)} rows written"
    except Exception as exc:  # noqa: BLE001 - the sheet is a mirror; it must never stop the worker
        why = str(exc)[:160] if isinstance(exc, sheet.SheetError) else type(exc).__name__
        log.warning("sheet sync failed: %s", why)
        sheet.note_failure(store, "faq", "faq.sheet_failed", f"Google Sheet gagal dikemas kini: {why}")
        return f"sheet: FAILED ({why})"
