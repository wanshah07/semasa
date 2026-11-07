"""Memory from chats (Wan, 7 Nov 2026: "should I add obsidian or memory base so telegram and AI chat can improve auto and
remember", the "Generate memory from chats" switch of Claude's own settings). Once a day this reads what Wan wrote in the last
day, in every conversation he has (the AI chat's threads and the "Telegram" thread the bot keeps), asks the AI team for at most
MAX_NEW lasting facts or preferences he STATED, and saves the ones that are new as notes in `semasa_chat_memory` with source
'chat'. The AI chat and the Telegram bot send every note with every call, so what he said once is known everywhere afterwards.

What keeps it from filling the memory with noise or with things it must never hold:
  * only Wan's own turns are read, never the assistant's: an answer can carry a web page's words, and a page must never be able
    to write a note (the same rule the chat's `remember` tool keeps);
  * the model is told what a lasting fact is (who he is, how he works, standing preferences and decisions) and what is not (a
    one-off question, a task, today's news), and to give nothing when nothing qualifies;
  * a note that looks like a secret (a key, a password, an OTP, a long number such as a phone, IC or bank account) or carries an
    e-mail address or a phone number is dropped here whatever the model says, since another person's details are not Wan's to
    keep and a secret in a note would be sent to the model on every call;
  * a note too close to one he already has is not added (the notes are compared word by word), and the memory never grows past
    the chat's own ceiling of NOTES_MAX notes;
  * the switch is Wan's: settings.ai_memory.auto_memory false (Memori & Arahan page) and this run reads nothing.

It writes notes and its own bookmark (settings.memory_auto: which message it read up to) and nothing else. Every note it adds is
shown on Memori & Arahan as "auto", where Wan edits or deletes it.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from . import ai_config, api_status, db
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.memory_auto")

SETTINGS_KEY = "ai_memory"        # Wan's switches: {search_chats, auto_memory}; both on when absent
STATE_KEY = "memory_auto"         # this job's bookmark: {at, upto_id, added}
MESSAGES = "semasa_chat_messages"
THREADS = "semasa_chat_threads"
MEMORY = "semasa_chat_memory"

WINDOW_HOURS = 24
MAX_NEW = 5                       # notes one run may add
NOTES_MAX = 40                    # the chat function's ceiling (supabase/functions/semasa-chat/logic.js MEMORY.notes)
NOTE_MIN, NOTE_MAX = 3, 500       # the table's own check (supabase/025_chat_memory.sql)
MAX_MESSAGES = 150
MAX_CHARS = 24000                 # what is sent to the model in one go
TURN_CHARS = 1200
SIMILAR = 0.6                     # share of a new note's words already in an old one that makes it a repeat

SYSTEM = (
    "You keep the long-term memory of an assistant that works for Wan (a Registered Chemist and regulatory affairs "
    "consultant in Malaysia, owner of WS REGULAB). You are given ONLY the messages Wan himself wrote in the last day, and "
    "the notes the assistant already keeps. Pick out at most 5 LASTING facts or preferences that Wan STATED and that will "
    "still be true and useful in future conversations: who he is and what he does, his businesses and clients as "
    "businesses, how he wants answers written, tools and sources he uses or refuses, standing decisions and rules he set. "
    "Never: a one-off question or request, a task for today, news, anything the assistant said, anything you infer or "
    "guess, a password, key, token, code or account number, or personal details (phone, e-mail, address, IC, health) of any"
    " other person. Skip anything already in the existing notes. Each note is one plain sentence of 3 to 300 characters, "
    'about Wan in the third person ("Wan prefers ..."), in the language he used (Malaysian Malay, never Indonesian, or '
    'English), with no em dash. When nothing qualifies, return an empty list. Answer JSON only: {"notes": [{"note": "...", '
    '"from": "the words of his that it rests on"}]}'
)

_SECRET = re.compile(
    r"(api[ _-]?key|secret|token|password|passwd|kata laluan|katalaluan|\botp\b|\bpin\b|bearer"
    r"|sk-[a-z0-9]|ghp_|xox[bap]-|-----begin)",
    re.I,
)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_LONG_NUMBER = re.compile(r"\d[\d\s-]{8,}\d")      # a phone, an IC, a bank account: nine digits or more in a run
_WORD = re.compile(r"[\w']+", re.U)


def _setting(store: Any, key: str) -> dict[str, Any]:
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", key).execute().data or []
    except Exception as exc:  # noqa: BLE001 - an unreadable setting is the default, never a crash
        log.info("setting %s not read: %s", key, str(exc)[:120])
        return {}
    v = rows[0].get("value") if rows else None
    return v if isinstance(v, dict) else {}


def enabled(store: Any) -> bool:
    """Wan's "Generate memory from chats" switch. On unless he turned it off: the page shows it on by default too."""
    return _setting(store, SETTINGS_KEY).get("auto_memory") is not False


def clean_note(note: Any) -> str | None:
    """One note as the table takes it, or None when it may not be kept at all."""
    n = re.sub(r"\s*\u2014\s*", ", ", str(note or ""))          # the house rule: no em dash in anything a person reads
    n = re.sub(r"\s+", " ", n.replace("\u2013", "-")).strip()
    if not (NOTE_MIN <= len(n) <= NOTE_MAX):
        return None
    if _SECRET.search(n) or _EMAIL.search(n) or _LONG_NUMBER.search(n):
        return None
    return n


def _words(s: str) -> set[str]:
    return {w for w in _WORD.findall(s.lower()) if len(w) > 2}


def is_repeat(note: str, existing: list[str]) -> bool:
    """True when most of the note's words are already in one existing note (or the other way round): the same fact said again."""
    a = _words(note)
    if not a:
        return True
    for old in existing:
        b = _words(old)
        if not b:
            continue
        shared = len(a & b)
        if shared / len(a) >= SIMILAR or shared / len(b) >= SIMILAR:
            return True
    return False


def gather(store: Any, now: datetime, after_id: int = 0) -> dict[str, list[dict[str, Any]]]:
    """{user_id: [{id, thread, text}]}: what each person wrote in the last WINDOW_HOURS, after the bookmark, oldest first."""
    since = (now - timedelta(hours=WINDOW_HOURS)).isoformat()
    q = store.table(MESSAGES).select("id,thread_id,user_id,role,content,created_at").eq("role", "user").gte("created_at", since)
    if after_id:
        q = q.gt("id", after_id)
    rows = q.order("id").limit(MAX_MESSAGES * 4).execute().data or []
    titles: dict[str, str] = {}
    ids = sorted({str(r.get("thread_id")) for r in rows if r.get("thread_id")})
    if ids:
        try:
            for t in store.table(THREADS).select("id,title").in_("id", ids).execute().data or []:
                titles[str(t.get("id"))] = str(t.get("title") or "")
        except Exception as exc:  # noqa: BLE001 - titles only label the lines
            log.info("thread titles not read: %s", str(exc)[:120])
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        text = str(r.get("content") or "").strip()
        uid = str(r.get("user_id") or "")
        if not text or not uid:
            continue
        out.setdefault(uid, []).append({"id": r.get("id"), "thread": titles.get(str(r.get("thread_id")), ""), "text": text})
    return {u: m[-MAX_MESSAGES:] for u, m in out.items()}


def request(messages: list[dict[str, Any]], existing: list[str]) -> str:
    lines, used = [], 0
    for m in reversed(messages):                  # the newest first, so a long day keeps its latest words
        label = "Telegram" if m["thread"].strip().lower() == "telegram" else "AI chat"
        line = f"[{label}] {m['text'][:TURN_CHARS]}"
        if used + len(line) > MAX_CHARS:
            break
        lines.append(line)
        used += len(line)
    have = "\n".join(f"- {n}" for n in existing) or "(none)"
    return f"Existing notes:\n{have}\n\nWan's messages (newest first):\n" + "\n".join(lines)


def extract(llm: Any, messages: list[dict[str, Any]], existing: list[str], room: int) -> list[str] | None:
    """The new notes worth keeping, at most `room` (and never more than MAX_NEW). None when the model gave no usable answer, so
    the caller knows these messages were not read and leaves its bookmark where it was."""
    if not messages or room <= 0:
        return []
    data = llm.chat_json(SYSTEM, request(messages, existing), max_tokens=900)
    if not isinstance(data, dict):
        return None
    items = data.get("notes")
    out: list[str] = []
    for it in items if isinstance(items, list) else []:
        n = clean_note(it.get("note") if isinstance(it, dict) else it)
        if not n or is_repeat(n, existing + out):
            continue
        out.append(n)
        if len(out) >= min(room, MAX_NEW):
            break
    return out


def make_llm(store: Any) -> Any | None:
    try:
        api_status.attach(store, "memory")
        return LLM(ai_config.llm_for(store))
    except Exception as exc:  # noqa: BLE001 - no key is "nothing learned today", never a crash
        log.warning("no LLM: %s", exc)
        return None


def run(store: Any, llm: Any = None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    if not enabled(store):
        return {"skipped": "off", "added": 0}
    state = _setting(store, STATE_KEY)
    try:
        after = int(state.get("upto_id") or 0)
    except (TypeError, ValueError):
        after = 0
    try:
        by_user = gather(store, now, after)
    except Exception as exc:  # noqa: BLE001 - 025 not run, or the table unreadable: say so, change nothing
        log.warning("chat messages not read: %s", str(exc)[:200])
        return {"skipped": "unreadable", "added": 0}
    if not by_user:
        return {"skipped": "nothing new", "added": 0}
    llm = llm if llm is not None else make_llm(store)
    if llm is None or not getattr(llm, "configured", False):
        return {"skipped": "no AI", "added": 0}

    added, upto, unread = 0, after, None
    for uid, msgs in by_user.items():
        rows = store.table(MEMORY).select("id,note").eq("user_id", uid).limit(NOTES_MAX * 2).execute().data or []
        existing = [str(r.get("note") or "") for r in rows]
        new = extract(llm, msgs, existing, NOTES_MAX - len(existing))
        ids = [int(m["id"]) for m in msgs if isinstance(m.get("id"), int)]
        if new is None:        # the model gave nothing usable: these messages are read again on the next run
            unread = min([unread] + ids) if unread is not None else min(ids, default=None)
            continue
        if new:
            store.table(MEMORY).insert([{"user_id": uid, "note": n, "source": "chat"} for n in new]).execute()
            added += len(new)
        upto = max([upto] + ids)
    if unread is not None:     # ids are shared by every person, so the bookmark stops short of the first message nobody read
        upto = max(after, min(upto, unread - 1))
    store.table(db.SETTINGS).upsert({"key": STATE_KEY, "value": {"at": now.isoformat(), "upto_id": upto, "added": added}},
                                    on_conflict="key").execute()
    if added:
        db.log_event(store, "info", "system", "memory.auto", f"Memori: {added} nota baharu daripada sembang",
                     detail={"added": added})
    return {"added": added, "upto_id": upto, "people": len(by_user)}


def main() -> int:
    out = run(db.client())
    print(f"Memory from chats: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
