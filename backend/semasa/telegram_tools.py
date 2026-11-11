"""Semasa on Telegram, the second round (Wan, 7 Nov 2026: "how to make sure chat from telegram always improve or auto improve ...
create robot button in telegram and make sure telegram can identify which model run now and I can choose which model to run,
make sure telegram can develop report or poster or motion or video").

  * /robot: the AI team as Telegram buttons. Each robot's state (the API check's last answer), which one writes now, and a button
    per healthy robot to pin it, or Auto. A pin is the API page's own pin (settings.ai_team.pins.reader): a preference, not a
    lock; the router still moves off a pinned robot that stops answering.
  * Every answer ends with the robot and model that actually wrote it (read off the call itself, not guessed), and the model is
    told who it is, so "which model are you" is answered truthfully.
  * It improves itself: Wan's standing notes (semasa_chat_memory, the same notes the AI chat page keeps) go into every answer;
    /ingat saves one; 👎 under an answer asks what to change and his reply becomes a note; 👍 is counted. The conversation is kept
    in the AI chat page's own "Telegram" thread, so the two remember the same things.
  * /poster and /karusel write an idea (the worker drafts it, the draft comes back here for approval); /motion and /video queue a
    film in the Motion queue (waiting, like one made from the page) with a button to start it with the default styles; /laporan
    writes a report and sends it as a file.
Nothing here approves, posts or deletes anything: approval stays semasa_telegram_decide (the page's gate).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from . import db
from .log import get_logger

log = get_logger("semasa.telegram_tools")

MEMORY = "semasa_chat_memory"
THREADS = "semasa_chat_threads"
MESSAGES = "semasa_chat_messages"
MOTIONS = "semasa_motions"
CHAT_KEY = "telegram_chat"              # settings row: {thread_id, await_note, pending, likes, videos_sent}
THREAD_TITLE = "Telegram"
NOTES_MAX = 40                          # the AI chat's own ceiling (semasa-chat logic.js MEMORY.notes): the newest 40
HISTORY_TURNS = 8
URL_RE = re.compile(r"https?://[^\s<>\"']+")
# robots that write text through the router; ChatGPT draws Motion's pictures and writes its storyboard, it is not a pin here.
# The providers Wan added on the API tab (ai_providers.py) join at call time: pinnable(store).
PINNABLE = ("rootsys", "mireld", "kiosapi", "gemini")


def pinnable(store: Any) -> tuple[str, ...]:
    """PINNABLE plus every enabled provider's slug, read now (a provider switched off a minute ago is no longer a button)."""
    from . import ai_providers
    try:
        return PINNABLE + tuple(s for s in ai_providers.slugs(store) if s not in PINNABLE)
    except Exception as exc:  # noqa: BLE001 - the built-in four still pin
        log.info("providers not read for /robot (%s)", str(exc)[:100])
        return PINNABLE


# ---- settings row for the conversation ------------------------------------------------------------------------------------

def chat_state(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("value").eq("key", CHAT_KEY).execute().data or []
    return dict(rows[0].get("value") or {}) if rows else {}


def save_chat_state(store: Any, changes: dict[str, Any]) -> None:
    """Write ONLY the keys a caller owns, merged onto a fresh read taken immediately before the write.

    The row has several writers (this worker, the webhook's thread_id, earlier the motion worker), and writing back a whole
    copy read minutes before put back stale values of the keys someone else had changed meanwhile."""
    store.table(db.SETTINGS).upsert({"key": CHAT_KEY, "value": {**chat_state(store), **changes}}, on_conflict="key").execute()


# ---- the robots -----------------------------------------------------------------------------------------------------------

def _settings(store: Any, key: str) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("value").eq("key", key).execute().data or []
    return dict(rows[0].get("value") or {}) if rows else {}


def team(store: Any, job: str = "reader") -> dict[str, Any]:
    """{rows: [robot rows], chosen: {...} | None, pin: {...} | None} from the API check and the router's last decision for
    `job` (the router's own job names: reader, ideas, motion)."""
    from .ai_team import robots
    ROBOTS = robots(store)                               # the built-in five plus Wan's providers (W6, W7, ...)
    pins_ok = pinnable(store)
    status = store.table(db.API_STATUS).select("slug,name,model,chat_ok,chat_ms,checked_at,role,error").execute().data or []
    state = _settings(store, "ai_team_state")
    pins = (_settings(store, "ai_team").get("pins") or {})
    rows = []
    for s in status:
        if s.get("role") == "image" and s.get("slug") != "kiosapi":
            continue
        r = ROBOTS.get(s["slug"], {"robot": "W?", "name": s.get("name") or s["slug"]})
        rows.append({"slug": s["slug"], "robot": r["robot"], "name": r["name"], "model": s.get("model") or "",
                     "ok": bool(s.get("chat_ok")), "ms": s.get("chat_ms"), "error": str(s.get("error") or "")[:120],
                     "pinnable": s["slug"] in pins_ok})
    rows.sort(key=lambda r: r["robot"])
    decided = state.get(job) or {}
    return {"rows": rows, "chosen": decided.get("chosen"), "pin": pins.get(job), "why": decided.get("why") or ""}


def robot_reply(store: Any) -> tuple[str, list[list[dict[str, str]]]]:
    t = team(store)
    chosen, pin = t["chosen"], t["pin"]
    lines = ["🤖 Pasukan AI Semasa"]
    if chosen:
        lines.append(f"✍️ Sedang menulis: {chosen.get('name')} · {chosen.get('model')}")
    picked = f"{pin.get('gateway')} · {pin.get('model')}" if pin else "Auto (paling sihat dan pantas)"
    lines.append("📌 Pilihan anda: " + picked)
    lines.append("")
    for r in t["rows"]:
        speed = f" · {r['ms'] / 1000:.1f} s" if r["ms"] else ""
        mark = "🟢" if r["ok"] else "🔴"
        extra = "" if r["pinnable"] else " (gambar & storyboard Motion)" if r["slug"] == "chatgpt" else ""
        why = "" if r["ok"] else f"\n   {r['error']}"
        lines.append(f"{mark} {r['robot']} {r['name']} · {r['model']}{speed}{extra}{why}")
    lines.append("\nTekan untuk pilih model yang menulis. Auto = Semasa pilih yang sihat dan pantas; robot yang dipilih "
                 "tetap ditukar jika ia berhenti menjawab.")
    buttons = [[{"text": ("✅ " if not pin else "") + "⚡ Auto", "callback_data": "pin:auto"}]]
    row: list[dict[str, str]] = []
    for r in t["rows"]:
        if not (r["pinnable"] and r["ok"]):
            continue
        on = pin and pin.get("gateway") == r["slug"]
        row.append({"text": ("✅ " if on else "") + f"{r['robot']} {r['model']}"[:30], "callback_data": f"pin:{r['slug']}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return "\n".join(lines), buttons


# the router's jobs a pin can name (ai_team.chain, gemini_keys.JOBS): "reader" is every worker that reads or answers (Telegram's
# answers, the repo library, writing styles, reports), "ideas" writes the posts, "motion" writes a film's script and storyboard.
# Telegram's own answers have no job of their own: they are "reader" calls, which is also the pin the webhook's fast answer reads.
TASK_JOBS = ("reader", "ideas", "motion")


def pin_job(store: Any, slug: str, job: str = "reader") -> tuple[str, dict[str, Any] | None]:
    """Pin the robot for one router job (settings.ai_team.pins[job]), exactly as the API page does; 'auto' clears it.
    Other pins are kept. Returns (what happened, the robot's row): 'auto' | 'pinned' | 'down' | 'unknown'.
    Nothing is written for the last two."""
    if job not in TASK_JOBS:
        return "unknown", None
    cur = _settings(store, "ai_team")
    pins = dict(cur.get("pins") or {})
    row = None
    if slug == "auto":
        pins[job] = None
        what = "auto"
    else:
        row = next((r for r in team(store, job)["rows"] if r["slug"] == slug and r["pinnable"]), None)
        if not row:
            return "unknown", None
        if not row["ok"]:
            return "down", row
        pins[job] = {"gateway": slug, "model": row["model"]}
        what = "pinned"
    store.table(db.SETTINGS).upsert({"key": "ai_team", "value": {**cur, "pins": pins}}, on_conflict="key").execute()
    return what, row


def set_pin(store: Any, slug: str, job: str = "reader") -> str:
    """The legacy /robot wording (Malay) around pin_job. Pins the text writer by default."""
    what, row = pin_job(store, slug, job)
    if what == "auto":
        return "⚡ Auto: Semasa pilih robot yang paling sihat dan pantas."
    if what == "unknown" or row is None:
        return "Robot itu tidak boleh dipilih sekarang."
    if what == "down":
        return f"{row['name']} tidak menjawab pada semakan terakhir: tidak dipilih."
    return (f"📌 {row['robot']} {row['name']} · {row['model']} dipilih untuk menulis. "
            "Jika ia berhenti menjawab, Semasa tukar sendiri.")


def served_by(rec: dict[str, Any]) -> str:
    """'Wanshah 1 · glm-5.3' for the call that actually answered."""
    from .ai_team import robot_of
    base, model = str(rec.get("base") or ""), str(rec.get("model") or "")
    if not base and not model:
        return ""
    r = robot_of(base) if base else {"name": ""}
    return " · ".join(x for x in (r.get("name"), model) if x)


def ask(llm: Any, system: str, user: str, max_tokens: int = 900) -> tuple[str, str]:
    """(answer, who answered). The robot is read off the call's own usage record, so a failover is reported as it happened."""
    from . import llm as llm_mod
    seen: dict[str, Any] = {}
    prev = llm_mod._USAGE_SINK

    def sink(rec: dict[str, Any]) -> None:
        seen.clear()
        seen.update(rec)
        if prev:
            prev(rec)
    llm_mod.set_usage_sink(sink)
    try:
        got = llm.chat_text(system, user, max_tokens=max_tokens)
    finally:
        llm_mod.set_usage_sink(prev)
    return str(got or "").strip(), served_by(seen)


# ---- memory: Wan's standing notes and the conversation ----------------------------------------------------------------------

def notes(store: Any, user_id: str) -> list[dict[str, Any]]:
    """Wan's standing notes: the NEWEST NOTES_MAX, oldest first (reading ascending with a limit kept the oldest and dropped
    every note added after the ceiling)."""
    rows = store.table(MEMORY).select("id,note,source,created_at").eq("user_id", user_id).order("created_at", desc=True) \
        .limit(NOTES_MAX).execute().data or []
    return list(reversed(rows))


def remember(store: Any, user_id: str, note: str, source: str = "user") -> str:
    note = " ".join(str(note).split())[:500]
    if len(note) < 3:
        return ("Tulis /ingat diikuti apa yang perlu saya ingat. "
                "Contoh: /ingat caption ws.regulab jangan lebih 120 patah perkataan")
    store.table(MEMORY).insert({"user_id": user_id, "note": note, "source": source}).execute()
    return f"🧠 Diingat: {note}"


def forget(store: Any, user_id: str, note_id: str) -> str:
    store.table(MEMORY).delete().eq("id", note_id).eq("user_id", user_id).execute()
    return "🗑 Nota dipadam."


def memory_reply(store: Any, user_id: str) -> tuple[str, list[list[dict[str, str]]]]:
    rows = notes(store, user_id)
    if not rows:
        return ("🧠 Tiada nota lagi. /ingat <nota> untuk tambah, atau tekan 👎 di bawah jawapan "
                "dan beritahu apa patut berubah.", [])
    text = "🧠 Nota tetap (dibaca oleh setiap jawapan, di sini dan di AI Chat):\n" + "\n".join(
        f"{i}. {r['note']}" for i, r in enumerate(rows, 1))
    buttons = [[{"text": f"🗑 {i}", "callback_data": f"forget:{r['id']}"} for i, r in list(enumerate(rows, 1))[k:k + 5]]
               for k in range(0, len(rows), 5)]
    return text, buttons


def thread_id(store: Any, user_id: str) -> str:
    st = chat_state(store)
    if st.get("thread_id"):
        got = store.table(THREADS).select("id").eq("id", st["thread_id"]).execute().data or []
        if got:
            return st["thread_id"]
    row = (store.table(THREADS).insert({"user_id": user_id, "title": THREAD_TITLE}).execute().data or [{}])[0]
    save_chat_state(store, {"thread_id": row.get("id")})
    return str(row.get("id") or "")


def log_turn(store: Any, user_id: str, question: str, reply: str) -> None:
    """Keep the exchange in the AI chat page's Telegram thread (so both remember it). Never fails an answer."""
    try:
        tid = thread_id(store, user_id)
        if not tid:
            return
        base = {"thread_id": tid, "user_id": user_id}
        store.table(MESSAGES).insert([{**base, "role": "user", "content": question[:40000]},
                                      {**base, "role": "assistant", "content": reply[:40000]}]).execute()
    except Exception as exc:  # noqa: BLE001
        log.info("Telegram turn not kept (%s)", str(exc)[:120])


def recent_turns(store: Any, user_id: str, n: int = HISTORY_TURNS) -> list[tuple[str, str]]:
    try:
        tid = chat_state(store).get("thread_id")
        if not tid:
            return []
        rows = store.table(MESSAGES).select("id,role,content").eq("thread_id", tid).order("id", desc=True) \
            .limit(n * 2).execute().data or []
    except Exception:  # noqa: BLE001
        return []
    rows.reverse()
    out, q = [], None
    for r in rows:
        if r["role"] == "user":
            q = r["content"]
        elif q is not None:
            out.append((q[:600], r["content"][:800]))
            q = None
    return out


def feedback_buttons(row_id: int) -> list[list[dict[str, str]]]:
    return [[{"text": "👍", "callback_data": f"fb:up:{row_id}"},
             {"text": "👎 perlu baiki", "callback_data": f"fb:down:{row_id}"}]]


def on_feedback(store: Any, kind: str, row_id: str) -> str:
    if kind == "up":
        save_chat_state(store, {"likes": int(chat_state(store).get("likes") or 0) + 1})
        return "👍 Terima kasih, saya teruskan cara ini."
    save_chat_state(store, {"await_note": row_id})
    return ("👎 Apa patut saya ubah? Balas dengan satu ayat (contoh: \"jawab lebih ringkas\" atau "
            "\"sentiasa beri rujukan NPRA\"). Saya simpan sebagai nota tetap untuk semua jawapan seterusnya.")


def take_correction(store: Any, user_id: str, text: str) -> str | None:
    """After 👎, Wan's next plain message is the correction: saved as a standing note. None when nothing was waiting."""
    st = chat_state(store)
    if not st.get("await_note") or text.startswith("/"):
        return None
    save_chat_state(store, {"await_note": None})
    return remember(store, user_id, f"Pembetulan Wan: {text}", source="chat").replace("🧠 Diingat", "🧠 Pembetulan diingat")


# ---- making things --------------------------------------------------------------------------------------------------------

def _topic(text: str, command: str) -> str:
    return re.sub(rf"^/{command}(@\w+)?", "", text.strip(), flags=re.I).strip()


def make_poster(store: Any, link: dict[str, Any], text: str, command: str) -> str:
    topic = _topic(text, command)
    if not topic:
        return f"Tulis /{command} diikuti topik atau link. Contoh: /{command} amaran label krim pemutih"
    urls = URL_RE.findall(topic)
    note = URL_RE.sub("", topic).strip()
    carousel = command in ("karusel", "carousel")
    brief: dict[str, Any] = {"via": "telegram"}
    if not carousel:
        brief["format"] = "poster"
    row = {"source_title": (note or urls[0])[:300], "source_url": urls[0] if urls else None, "source_name": "Telegram",
           "stream": "regulab", "make_media": "image", "make_slides": carousel, "note": note[:2000], "reference_urls": urls[1:8],
           "status": "new", "created_by": link["user_id"], "brief": brief}
    store.table(db.IDEAS).insert(row).execute()
    what = "karusel" if carousel else "poster"
    return (f"🎨 {what.capitalize()} dihantar kepada penulis: {row['source_title'][:120]}\n"
            "Semasa tulis draf dan lukis gambarnya; draf itu akan sampai di sini untuk anda lulus.")


def queue_motion(store: Any, link: dict[str, Any], brief: str, *, source_url: str = "", stream: str = "regulab",
                 language: str = "bm", idea_id: str | None = None, options: dict[str, Any] | None = None) -> str | None:
    """A film waiting in the Motion queue (status 'waiting', like one made from the page). Nothing starts until Wan taps Start
    (mgo: sets it pending) and nothing is made until he approves its storyboard (supabase/071). Returns the film's id."""
    row: dict[str, Any] = {"brief": brief[:1900], "source_url": source_url, "stream": stream, "language": language,
                           "resolution": "portrait", "status": "waiting", "created_by": link["user_id"],
                           "options": {"via": "telegram", **(options or {})}}
    if idea_id:
        row["idea_id"] = idea_id
    got = (store.table(MOTIONS).insert(row).execute().data or [{}])[0]
    return got.get("id")


def make_motion(store: Any, link: dict[str, Any], text: str, command: str) -> tuple[str, list[list[dict[str, str]]], str | None]:
    topic = _topic(text, command)
    if not topic:
        return (f"Tulis /{command} diikuti idea atau link. Contoh: /{command} 3 perkara sebelum notifikasi kosmetik", [], None)
    urls = URL_RE.findall(topic)
    brief = URL_RE.sub("", topic).strip() or topic
    mid = queue_motion(store, link, brief, source_url=urls[0] if urls else "")
    from .billing import SITE_URL
    buttons = [[{"text": "▶️ Mula (gaya rawak)", "callback_data": f"mgo:{mid}"}],
               [{"text": "🎨 Pilih gaya", "callback_data": f"msk:{mid}"}],
               [{"text": "🎬 Buka Motion di Semasa", "url": f"{SITE_URL.rstrip('/')}/#video"}]]
    return (f"🎬 Dalam barisan Motion: {brief[:120]}\nTekan Mula untuk gaya rawak (satu daripada gaya 2D), atau Pilih gaya "
            "untuk tentukan sendiri.",
            buttons, mid)


def start_motion(store: Any, motion_id: str) -> str:
    got = store.table(MOTIONS).update({"status": "pending"}).eq("id", motion_id).eq("status", "waiting").execute().data
    return ("▶️ Motion dimulakan. Saya hantar storyboard di sini dahulu untuk anda luluskan; gambar dan video dibuat "
            "selepas itu." if got
            else "Motion itu sudah bermula atau tiada lagi dalam barisan.")


REPORT_SYSTEM = ("You write reports for Wan (Registered Chemist, regulatory affairs specialist, owner of WS REGULAB) in "
                 "Markdown: a title, a 3-line summary, then sections with short paragraphs and bullet points, and a closing "
                 "'Next steps'. Write in the language of his request: Malaysian Bahasa Malaysia (never Bahasa Indonesia) or "
                 "English. Use the SNAPSHOT for facts about Semasa. On regulations, never invent a number, date, limit or "
                 "reference: say what must be checked and where (NPRA, ACD, EC 1223/2009).")


def report_file(title: str, body: str, when: datetime) -> tuple[str, bytes]:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "laporan"
    return f"semasa-{slug}-{when.strftime('%Y%m%d')}.md", body.encode("utf-8")


def due_motion_videos(store: Any, since: str) -> list[dict[str, Any]]:
    """Telegram-queued films finished since `since`, to send back where they were asked for."""
    rows = store.table(MOTIONS).select("id,title,brief,video_url,status,options,updated_at").eq("status", "done") \
        .gte("updated_at", since).execute().data or []
    return [r for r in rows if (r.get("options") or {}).get("via") == "telegram" and r.get("video_url")]


# ---- topics a legacy button asked for --------------------------------------------
# The button menu is telegram_catalogue.py now (Wan, 9 Nov 2026). What stays here is the handler behind the OLD `menu:<action>`
# buttons, so a menu message already sitting in Wan's chat still works: an action that needs words asks for them (pending) and
# the next plain message he sends is that topic. None of these is offered by the new menu.
NEEDS_TOPIC = {
    "idea": "💡 Hantar link atau tulis idea:",
    "poster": "🎨 Topik atau link untuk poster:",
    "karusel": "🖼 Topik atau link untuk karusel:",
    "motion": "🎬 Idea atau link untuk video motion:",
    "laporan": "📄 Laporan tentang apa?",
    "ingat": "✍️ Apa yang perlu saya ingat untuk semua jawapan?",
}


def ask_topic(store: Any, action: str) -> str:
    save_chat_state(store, {"pending": action})
    return NEEDS_TOPIC[action]


def take_pending(store: Any, text: str) -> str | None:
    """A topic Wan was asked for from the menu: the plain message becomes "/<action> <text>" (the catalogue's repo, idea and
    style prompts use this too). None when nothing waits. A command sent instead of the topic drops the question."""
    st = chat_state(store)
    action = st.get("pending")
    if not action or not text or text.startswith("/"):
        if action and text.startswith("/"):
            save_chat_state(store, {"pending": None})        # a command instead of the topic: the question is dropped
        return None
    save_chat_state(store, {"pending": None})
    return f"/{action} {text}"
