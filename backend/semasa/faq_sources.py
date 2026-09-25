"""Q&A-shaped items the scraper offers as FAQ CANDIDATES. Nothing here is rewritten or published:
a candidate waits in the FAQ tab until Wan accepts it (then the writer rewrites it) or dismisses it.

Measured before it was written (25 Sep 2026, from an open-internet caller; a GitHub runner is
checked by the run's own source table, which reports every failure):
  JAKIM · Isu-Isu Tular Halal   200  sites.google.com/islam.gov.my/skkbph/isu-isu-tular-halal/<section>:
                                     each "PENJELASAN …" heading is a viral claim and the text under
                                     it is JAKIM's own answer, so these arrive WITH an answer
  Reddit r/malaysia             200  search.rss (the .json API answers 403; per-post comment feeds
                                     answer 429), so a Reddit candidate carries the QUESTION only
  forum.lowyat.net              403  bot-blocked at the origin: not a source
  Telegram groups               a BOT Wan adds to the group (TELEGRAM_BOT_TOKEN), read with the official
                                Bot API. Transparent: the members see the bot join. Question-shaped
                                messages become candidates, and replies to them become their answer.
                                No sender name, username or phone number is ever stored.
A source that fails is reported and skipped; it never stops the scrape.
"""

from __future__ import annotations

import html
import os
import re
from typing import Any
from urllib.parse import quote

from . import fetch
from .log import get_logger

log = get_logger("semasa.faq_sources")

FAQS = "semasa_faqs"
JAKIM_BASE = "https://sites.google.com/islam.gov.my/skkbph/isu-isu-tular-halal"
JAKIM_SECTIONS = ["bahan-ramuan", "pekerja", "profil-syarikat", "logo-halal", "bukan-pemegang-sphm",
                  "syarikat-luar-negara", "prosedur-pensijilan-halal", "lain-lain"]
# ONE search: Reddit answered the first of six separate searches and 429 to the other five
REDDIT_QUERY = 'halal OR "sijil halal" OR skincare OR sunscreen OR kosmetik OR NPRA'
REDDIT_MAX = 8
QUESTION_WORDS = re.compile(r"\?|^(adakah|boleh ke|bolehkah|macam mana|bagaimana|kenapa|mengapa|apa|is it|can i|"
                            r"how|what|which|should|does|do i|anyone)\b", re.I)

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def _text(fragment: str) -> str:
    fragment = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", fragment)
    fragment = re.sub(r"<br\s*/?>|</p>|</li>|</div>", "\n", fragment)
    txt = html.unescape(_TAGS.sub(" ", fragment))
    lines = [_WS.sub(" ", ln).strip() for ln in txt.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:80]


def parse_jakim(page: str, section: str) -> list[dict[str, Any]]:
    """Every "PENJELASAN …" heading and the text under it, up to the next heading."""
    out = []
    parts = re.split(r"<h[1-4][^>]*>", page)
    for part in parts[1:]:
        head, _, rest = part.partition("</h")
        title = _WS.sub(" ", html.unescape(_TAGS.sub(" ", head))).strip()
        if not title.upper().startswith("PENJELASAN"):
            continue
        rest = rest.split(">", 1)[1] if ">" in rest else rest
        body = _text(rest)
        body = re.split(r"\n(?:Report abuse|Page details|BAHAGIAN PENGURUSAN HALAL, JABATAN)", body)[0].strip()
        if len(body) < 40:
            continue
        out.append({"source_kind": "auto", "status": "candidate", "source_key": f"jakim:{section}:{_slug(title)}",
                    "source_name": "JAKIM · Isu-Isu Tular Halal", "source_url": f"{JAKIM_BASE}/{section}",
                    "raw_question": title, "raw_answer": body[:6000]})
    return out


def parse_reddit(feed: str, query: str) -> list[dict[str, Any]]:
    """Posts from a search feed whose title reads as a question. Question only: no answer."""
    out = []
    for entry in re.findall(r"<entry>([\s\S]*?)</entry>", feed):
        m_title = re.search(r"<title>([\s\S]*?)</title>", entry)
        m_link = re.search(r'<link href="([^"]+)"', entry)
        if not m_title or not m_link:
            continue
        title = _WS.sub(" ", html.unescape(m_title.group(1))).strip()
        link = m_link.group(1)
        m_id = re.search(r"/comments/([a-z0-9]+)/", link)
        if not m_id or not QUESTION_WORDS.search(title):
            continue
        m_body = re.search(r"<content[^>]*>([\s\S]*?)</content>", entry)
        body = _text(html.unescape(m_body.group(1))) if m_body else ""
        body = re.sub(r"submitted by\s+/u/\S+.*$", "", body, flags=re.S).strip()
        out.append({"source_kind": "auto", "status": "candidate", "source_key": f"reddit:{m_id.group(1)}",
                    "source_name": f"Reddit r/malaysia (carian: {query})", "source_url": link,
                    "raw_question": (title + ("\n\n" + body if body else ""))[:6000], "raw_answer": ""})
        if len(out) >= REDDIT_MAX:
            break
    return out


# --- Telegram -------------------------------------------------------------------------------

TG_API = "https://api.telegram.org/bot{token}/{method}"
TG_MIN_LEN = 25
TG_QUESTION = re.compile(r"\?|(?<![a-z])(soalan|nak tanya|nak minta|mohon (?:pencerahan|nasihat|bantuan|pandangan)|"
                         r"boleh ke|bolehkah|adakah|macam mana|bagaimana|perlu ke|wajib ke|kena ke|how|can i|"
                         r"is it|does|should|anyone know)(?![a-z])", re.I)


def _tg_text(m: dict[str, Any]) -> str:
    return str(m.get("text") or m.get("caption") or "").strip()


def _tg_link(chat: dict[str, Any], mid: Any) -> str | None:
    return f"https://t.me/{chat['username']}/{mid}" if chat.get("username") else None


def parse_telegram(updates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(questions, replies) from getUpdates. Group messages only; bots and /commands are skipped.
    Only the TEXT is kept: never who wrote it."""
    questions: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []
    for u in updates:
        m = u.get("message") or {}
        chat = m.get("chat") or {}
        if chat.get("type") not in ("group", "supergroup") or (m.get("from") or {}).get("is_bot"):
            continue
        text = _tg_text(m)
        if not text or text.startswith("/"):
            continue
        title = str(chat.get("title") or "kumpulan")
        rt = m.get("reply_to_message") or {}
        if rt and _tg_text(rt) and not (rt.get("from") or {}).get("is_bot"):
            replies.append({"key": f"tg:{chat.get('id')}:{rt.get('message_id')}", "answer": text[:4000],
                            "question": _tg_text(rt)[:6000], "chat_title": title,
                            "url": _tg_link(chat, rt.get("message_id"))})
        elif len(text) >= TG_MIN_LEN and TG_QUESTION.search(text):
            questions.append({"source_kind": "auto", "status": "candidate",
                              "source_key": f"tg:{chat.get('id')}:{m.get('message_id')}",
                              "source_name": f"Telegram · {title}", "source_url": _tg_link(chat, m.get("message_id")),
                              "raw_question": text[:6000], "raw_answer": ""})
    return questions, replies


def apply_replies(store: Any, replies: list[dict[str, Any]]) -> int:
    """A reply becomes (part of) its question's answer while the question is still a candidate. A reply to a
    question that was never stored makes the pair a candidate if the question reads as one. Returns rows touched."""
    touched = 0
    for r in replies:
        got = store.table(FAQS).select("id,status,raw_answer").eq("source_key", r["key"]).limit(1).execute().data or []
        if got:
            row = got[0]
            if row.get("status") != "candidate" or r["answer"] in (row.get("raw_answer") or ""):
                continue                       # accepted already, or this reply was applied on an earlier run
            answer = ((row.get("raw_answer") or "") + "\n" + r["answer"]).strip()[:6000]
            store.table(FAQS).update({"raw_answer": answer}).eq("id", row["id"]).eq("status", "candidate").execute()
            touched += 1
        elif TG_QUESTION.search(r["question"]) and len(r["question"]) >= TG_MIN_LEN:
            touched += insert_candidates(store, [{"source_kind": "auto", "status": "candidate", "source_key": r["key"],
                                                  "source_name": f"Telegram · {r['chat_title']}", "source_url": r["url"],
                                                  "raw_question": r["question"], "raw_answer": r["answer"]}])
    return touched


def telegram(store: Any, token: str, *, timeout: int = 25) -> int:
    """Read the bot's waiting updates, store candidates and answers, then confirm them (the offset), so the
    next run starts after them. Telegram keeps unconfirmed updates for 24 hours: the 8-hourly scrape is inside."""
    import requests
    got = store.table("semasa_settings").select("key,value").eq("key", "telegram").limit(1).execute().data or []
    state = dict(got[0]["value"]) if got and isinstance(got[0].get("value"), dict) else {}
    params: dict[str, Any] = {"timeout": 0, "allowed_updates": '["message"]'}
    if state.get("offset"):
        params["offset"] = int(state["offset"])
    r = requests.get(TG_API.format(token=token, method="getUpdates"), params=params, timeout=timeout)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if not body.get("ok"):
        why = body.get("description") or f"HTTP {r.status_code}"
        raise RuntimeError(f"Telegram refused getUpdates: {why}")
    updates = body.get("result") or []
    questions, replies = parse_telegram(updates)
    n = insert_candidates(store, questions) + apply_replies(store, replies)
    if updates:
        chats = dict(state.get("chats") or {})
        for u in updates:
            c = (u.get("message") or {}).get("chat") or {}
            if c.get("type") in ("group", "supergroup"):
                chats[str(c.get("id"))] = str(c.get("title") or "")
        state.update(offset=max(int(u["update_id"]) for u in updates) + 1, chats=chats)
    from datetime import UTC, datetime
    state["last_run"] = datetime.now(UTC).isoformat()
    if got:
        store.table("semasa_settings").update({"value": state}).eq("key", "telegram").execute()
    else:
        store.table("semasa_settings").insert({"key": "telegram", "value": state}).execute()
    return n


def insert_candidates(store: Any, rows: list[dict[str, Any]]) -> int:
    """New candidates only: a key already seen (accepted, dismissed or still waiting) is left alone."""
    if not rows:
        return 0
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        seen.setdefault(r["source_key"], r)
    res = store.table(FAQS).upsert(list(seen.values()), on_conflict="source_key", ignore_duplicates=True).execute()
    return len(res.data or [])


def collect(store: Any, *, timeout: int = 25) -> list[dict[str, Any]]:
    """Gather candidates and store them. Returns one report row per source, the scraper's shape."""
    report: list[dict[str, Any]] = []

    def run_source(name: str, fn) -> None:
        try:
            rows = fn()
            added = insert_candidates(store, rows)
            report.append({"name": name, "kind": "faq", "ok": True, "items": added, "error": None})
            log.info("%-28s faq    %d found, %d new", name, len(rows), added)
        except Exception as exc:  # noqa: BLE001 - one source never stops the others or the scrape
            err = f"{type(exc).__name__}: {str(exc)[:160]}"
            if FAQS in str(exc):
                err = "the semasa_faqs table is missing: run supabase/007_faq.sql once"
            report.append({"name": name, "kind": "faq", "ok": False, "items": 0, "error": err})
            log.warning("%-28s faq    FAILED %s", name, err)

    def jakim() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for sec in JAKIM_SECTIONS:
            rows += parse_jakim(fetch.get(f"{JAKIM_BASE}/{sec}", timeout=timeout).text, sec)
        return rows

    def reddit() -> list[dict[str, Any]]:
        url = f"https://www.reddit.com/r/malaysia/search.rss?q={quote(REDDIT_QUERY)}&restrict_sr=1&sort=new"
        return parse_reddit(fetch.get(url, timeout=timeout).text, "halal / skincare / kosmetik")

    run_source("FAQ · JAKIM Isu Tular Halal", jakim)
    run_source("FAQ · Reddit r/malaysia", reddit)
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if token:                                   # dormant until Wan gives the bot a token
        try:
            added = telegram(store, token, timeout=timeout)
            report.append({"name": "FAQ · Telegram", "kind": "faq", "ok": True, "items": added, "error": None})
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {str(exc)[:160]}".replace(token, "***")
            report.append({"name": "FAQ · Telegram", "kind": "faq", "ok": False, "items": 0, "error": err})
            log.warning("FAQ · Telegram faq    FAILED %s", err)
    return report
