"""Semasa on Telegram, the things a menu button queues or reads (Wan, 9 Nov 2026, then 16 Nov 2026: "make sure all features
appear in telegram semasa button").

The menu itself is telegram_menu.py, drawn from rules/telegram_menu.json: the page's own segments and pages. This module is
what stands behind the buttons that do something in the chat:

  Model by task   which AI robot does reading and answers, post writing and motion scripts (the router's own jobs
                  reader / ideas / motion), or Auto. A pin is the API page's own pin (settings.ai_team.pins[job]).
  Repo library    a link becomes a semasa_repo_library row (status pending, note, created_by); the repo worker reads it.
  Idea            a link or some text becomes a semasa_ideas row (status new, stream regulab or linkedin); the idea worker
                  writes the draft. A poster or a carousel is the same row with its format and the look Wan picked.
  Writing style   a post link or pasted text becomes a semasa_writing_styles row (status new); the style worker describes it.
  Post            the drafts waiting, with Edit, Make carousel, Make motion, Approve, Reject and Open in Semasa
                  (the posts half lives in telegram_bot.py, beside the preview and the approval gate).
  Reads           the newest ideas of a stream, the vague-wording check on pasted text, an ayat al-Quran by surah:ayat.

Everything here only WRITES A ROW that an existing worker picks up, or READS. Nothing is published, approved, cloned or run from
this file. A question the menu asks ("send a link") is kept as settings.telegram_chat.pending = "cat:<kind>[:<arg>]"; the next
plain message is the answer, a command sent instead drops the question. The legacy slash commands and the old `menu:` and `c:`
buttons stay in telegram_bot.py as compatibility handlers, so a menu message already in Wan's chat still works.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from . import compliance, db, repo_library
from . import telegram_menu as menu
from . import telegram_tools as tt
from .log import get_logger

log = get_logger("semasa.telegram_catalogue")

REPOS = repo_library.TABLE                  # semasa_repo_library (supabase/042)
STYLES = "semasa_writing_styles"            # (supabase/067)
PREFIX = "cat:"                             # what telegram_chat.pending starts with while the menu waits for words
URL_RE = re.compile(r"https?://[^\s<>\"']+")
TRAILING = ".,;:!?)]}>'\""
MAX_URL = 500
MAX_NOTE = 500
MIN_SAMPLE = 80                             # semasa_writing_styles' own insert policy: a pasted sample of at least 80 characters
MAX_LINKS = 8                               # the same table's size check
MAX_SAMPLE = 12000
MIN_IDEA = 6                                # characters of plain text that can be an idea

TASKS = (("reader", "📖 Reading and answers", "Telegram answers, repo and style analysis, reports"),
         ("ideas", "💡 Writing posts", "the captions and hooks of every draft"),
         ("motion", "🎬 Motion scripts", "a film's script and storyboard"))
TASK_NAME = {job: name for job, name, _ in TASKS}


def _back(to: str = "m:home", label: str = "⬅ Back") -> list[dict[str, str]]:
    return [{"text": label, "callback_data": to}]


def lang(store: Any) -> str:
    """The language Wan picked for the menu (settings.telegram_chat.lang; the 🌐 button on the home menu): Malay unless he
    chose English, like the page."""
    return menu.lang_of(tt.chat_state(store).get("lang"))


# ---- the home menu --------------------------------------------------------------------------------------------------------

def home_reply(link: dict[str, Any] | None = None, lang: str = "bm", site: str = "") -> tuple[str, list[list[dict[str, str]]]]:
    """The home menu: two quick buttons, every segment of the page, the language switch and a link to Semasa."""
    from .billing import SITE_URL
    return menu.home(menu.lang_of(lang), site or SITE_URL, str((link or {}).get("username") or "Wan"))


def post_reply(site: str) -> tuple[str, list[list[dict[str, str]]]]:
    return ("📝 Post\n\nChoose a draft to edit, turn into a carousel or motion, and approve through the Semasa gate.",
            [[{"text": "📋 Show drafts", "callback_data": "c:pd"}],
             [{"text": "🌐 Open Post editor", "url": menu.page_url(site, "post")}],
             _back("m:home", "⬅ Menu")])


# ---- questions the menu asks ------------------------------------------------------------------------------------------------

def clear_pending(store: Any) -> None:
    """Leaving a question (Back, Menu, another button) drops it; only a catalogue question is touched."""
    if str(tt.chat_state(store).get("pending") or "").startswith(PREFIX):
        tt.save_chat_state(store, {"pending": None})


def ask(store: Any, kind: str, arg: str = "") -> None:
    tt.save_chat_state(store, {"pending": f"{PREFIX}{kind}" + (f":{arg}" if arg else "")})


def waiting(store: Any, text: str) -> tuple[str, str] | None:
    """(kind, arg) when this plain message answers a question the menu asked; None when nothing waits. A command sent instead
    of the answer drops the question (and is then handled as a command)."""
    pending = str(tt.chat_state(store).get("pending") or "")
    if not pending.startswith(PREFIX):
        return None
    if not text or text.startswith("/"):
        tt.save_chat_state(store, {"pending": None})
        return None
    kind, _, arg = pending[len(PREFIX):].partition(":")
    return kind, arg


# ---- Model by task --------------------------------------------------------------------------------------------------------

def _pins(store: Any) -> dict[str, Any]:
    return dict(tt._settings(store, "ai_team").get("pins") or {})


def _pin_words(pin: dict[str, Any] | None) -> str:
    return f"{pin.get('gateway')} · {pin.get('model')}" if pin else "Auto"


def model_reply(store: Any) -> tuple[str, list[list[dict[str, str]]]]:
    """The tasks, each with the robot pinned for it now."""
    pins = _pins(store)
    lines = ["🤖 Model by task", "", "Pick a task to see which robot does it and to change that."]
    for job, name, what in TASKS:
        lines.append(f"• {name}: {_pin_words(pins.get(job))}  ({what})")
    buttons = [[{"text": name, "callback_data": f"c:mt:{job}"}] for job, name, _ in TASKS]
    buttons.append(_back("m:home", "⬅ Menu"))
    return "\n".join(lines), buttons


def task_reply(store: Any, job: str, note: str = "") -> tuple[str, list[list[dict[str, str]]]]:
    """One task: who writes it now, the pin, every robot with its state, and a button per healthy robot that can be pinned."""
    if job not in tt.TASK_JOBS:
        return model_reply(store)
    t = tt.team(store, job)
    chosen, pin = t["chosen"], t["pin"]
    lines = [note, ""] if note else []
    lines.append(f"🤖 Model by task · {TASK_NAME[job]}")
    if chosen:
        lines.append(f"Writing now: {chosen.get('name')} · {chosen.get('model')}")
    lines.append(f"Your pick: {_pin_words(pin) if pin else 'Auto (the healthiest and fastest)'}")
    lines.append("")
    for r in t["rows"]:
        speed = f" · {r['ms'] / 1000:.1f} s" if r["ms"] else ""
        extra = "" if r["pinnable"] else " (Motion pictures and storyboards only)" if r["slug"] == "chatgpt" else ""
        why = "" if r["ok"] else f"\n   {r['error']}"
        lines.append(f"{'🟢' if r['ok'] else '🔴'} {r['robot']} {r['name']} · {r['model']}{speed}{extra}{why}")
    lines.append("\nA pin is a preference: if the robot stops answering, Semasa moves to a healthy one. "
                 "Auto lets Semasa choose.")
    buttons: list[list[dict[str, str]]] = [[
        {"text": ("✅ " if not pin else "") + "⚡ Auto", "callback_data": f"c:pin:{job}:auto"}
    ]]
    row: list[dict[str, str]] = []
    for r in t["rows"]:
        if not (r["pinnable"] and r["ok"]):
            continue
        on = pin and pin.get("gateway") == r["slug"]
        label = ("✅ " if on else "") + f"{r['robot']} {r['model']}"[:30]
        row.append({"text": label, "callback_data": f"c:pin:{job}:{r['slug']}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(_back("c:model", "⬅ Tasks"))
    return "\n".join(lines), buttons


def apply_pin(store: Any, job: str, slug: str) -> tuple[str, list[list[dict[str, str]]]]:
    """Pin (or clear) the robot for one task, exactly as the API page does, then show the task again with what happened."""
    what, row = tt.pin_job(store, slug, job)
    name = TASK_NAME.get(job, job)
    if what == "auto":
        note = f"⚡ {name}: Auto. Semasa picks the healthiest and fastest robot."
    elif what == "pinned" and row:
        note = f"📌 {name}: {row['robot']} {row['name']} · {row['model']}. If it stops answering, Semasa switches on its own."
    elif what == "down" and row:
        note = f"{row['name']} did not answer its last check, so it was not pinned."
    else:
        note = "That robot cannot be pinned for this task."
    return task_reply(store, job, note)


# ---- the questions the menu asks ------------------------------------------------------------------------------------------

def prompt_reply(kind: str, lang: str = "bm", arg: str = "") -> tuple[str, list[list[dict[str, str]]]]:
    """The question a button asks, in Wan's language, with a way back (the words are in telegram_menu.PROMPTS)."""
    return menu.prompt(kind, lang, arg)


def _urls(text: str) -> list[str]:
    out: list[str] = []
    for u in URL_RE.findall(text or ""):
        u = u.rstrip(TRAILING)
        p = urlparse(u)
        if p.scheme in ("http", "https") and p.netloc and not p.username and not p.password and len(u) <= MAX_URL \
                and u not in out:
            out.append(u)
    return out


def _words(text: str) -> str:
    return " ".join(URL_RE.sub(" ", text or "").split())


# ---- Repo library ---------------------------------------------------------------------------------------------------------

def add_repo(store: Any, link: dict[str, Any], text: str) -> tuple[str, bool]:
    """(what to tell Wan, whether the question is answered). One row in semasa_repo_library, status pending: the repo worker (its
    own trigger and schedule) does the reading. A GitHub link is kept as https://github.com/owner/name; any other link is kept
    as given, as a source note. Nothing is fetched, cloned or run here."""
    urls = _urls(text)
    if not urls:
        return "I did not find a link. Send a GitHub repository link, or tap Back.", False
    note = _words(text)[:MAX_NOTE]
    full = repo_library.parse_github(urls[0])
    url = f"https://github.com/{full}" if full else urls[0]
    held = {str(r.get("url") or "").lower(): r for r in store.table(REPOS).select("id,url,status").execute().data or []}
    if url.lower() in held:
        return (f"📚 Already in the Repo library ({held[url.lower()].get('status') or 'pending'}): {full or url}\n"
                "Open it in Semasa to read the summary or re-check it."), True
    if full:
        row = {"url": url, "full_name": full, "status": "pending", "note": note, "created_by": link["user_id"]}
        reply = (f"📚 Added to the Repo library: {full}\nQueued for analysis: Semasa reads the README and files, checks them "
                 "for safety and files a summary. Nothing is cloned or run.")
    else:
        host = urlparse(url).netloc.lower()
        row = {"url": url, "status": "pending", "created_by": link["user_id"],
               "note": (f"Source link from Telegram ({host}), not a GitHub repository. " + note).strip()[:MAX_NOTE]}
        reply = (f"📚 Saved as a source note and queued for analysis: {host}\nSemasa only reads and summarises; nothing is "
                 "cloned, downloaded or run. If the repo worker cannot read a link that is not a GitHub repository, it stays "
                 "in the library as a note.")
    store.table(REPOS).insert(row).execute()
    return reply, True


# ---- Idea -----------------------------------------------------------------------------------------------------------------

REQUIREMENTS = {"hook": "the first line is built on one of the 25 hook shapes (or the selected hook style)",
                "source": "the draft cites its source and states no fact the source does not carry"}


def idea_made_from(store: Any, inbox_id: Any) -> dict[str, Any] | None:
    """The idea already made from this Telegram message, so a message processed twice makes one idea."""
    if inbox_id is None:
        return None
    got = store.table(db.IDEAS).select("id,source_title").contains("brief", {"telegram_inbox_id": inbox_id}).limit(1) \
        .execute().data or []
    return got[0] if got else None


def add_idea(store: Any, link: dict[str, Any], text: str, inbox_id: Any = None, stream: str = "regulab", fmt: str = "",
             look: str = "", lang: str = "en") -> tuple[str, bool]:
    """(what to tell Wan, whether the question is answered). A real semasa_ideas row, status new, for ws.regulab or for Wan's own
    LinkedIn. The idea worker writes the draft (hook shape, citation, pictures) and the draft comes back to Telegram for
    approval. `fmt` "poster" or "carousel" asks for that artwork, in the look Wan picked (brief.look, the idea composer's own
    field: ideas.look_of). Nothing is published."""
    bm = lang == "bm"
    stream = "linkedin" if stream == "linkedin" else "regulab"
    urls = _urls(text)
    note = _words(text)
    if not urls and len(note) < MIN_IDEA:
        return ("Terlalu pendek untuk jadi idea. Hantar pautan, atau satu ayat tentang topiknya." if bm else
                "That is too short for an idea. Send a link, or a sentence about the topic."), False
    made = idea_made_from(store, inbox_id)
    if made:
        return (f"💡 Idea itu sudah bersama penulis: {made.get('source_title') or ''}" if bm else
                f"💡 That idea is already with the writer: {made.get('source_title') or ''}"), True
    title = (note[:200] or urls[0])
    brief: dict[str, Any] = {"via": "telegram", "catalogue": "idea", "telegram_inbox_id": inbox_id, "hook_required": True,
                             "source_required": True, "requirements": REQUIREMENTS, "source_kind": "link" if urls else "text"}
    if fmt == "poster":
        brief["format"] = "poster"                       # telegram_tools.make_poster's own mark (the /poster command)
    if look:
        brief["look"] = look
    row = {"source_title": title[:300], "source_url": urls[0] if urls else None, "source_name": "Telegram",
           "stream": stream, "make_media": "image", "make_slides": fmt == "carousel", "note": note[:2000],
           "reference_urls": urls[1:8], "status": "new", "created_by": link["user_id"], "brief": brief}
    store.table(db.IDEAS).insert(row).execute()
    where = "LinkedIn" if stream == "linkedin" else "ws.regulab"
    what = {"poster": "Poster", "carousel": "Carousel"}.get(fmt, "Idea")
    dress = f" · {menu.look_name(look, lang)}" if look else ""
    if bm:
        return (f"💡 {what}{dress} dihantar kepada penulis ({where}): {title[:120]}\nIa menjadi draf dengan hook dan sumber "
                "yang disebut, dan sampai di sini untuk anda luluskan. Tiada apa yang diterbitkan."), True
    return (f"💡 {what}{dress} sent to the writer ({where}): {title[:120]}\nIt becomes a draft with a hook and a cited source, "
            "and comes back here for you to approve. Nothing is published."), True


def ideas_reply(store: Any, stream: str, lang: str = "bm", limit: int = 10) -> str:
    """The newest ideas of one stream, read only: what each is and where it stands."""
    bm = lang == "bm"
    stream = "linkedin" if stream == "linkedin" else "regulab"
    rows = store.table(db.IDEAS).select("id,source_title,status,stream,created_at").eq("stream", stream) \
        .order("created_at", desc=True).limit(limit).execute().data or []
    where = "LinkedIn" if stream == "linkedin" else "ws.regulab"
    if not rows:
        return f"💡 Tiada idea {where} lagi." if bm else f"💡 No {where} ideas yet."
    icon = {"new": "🆕", "working": "✍️", "drafted": "📝", "rejected": "❌", "error": "❗"}
    head = (f"💡 Idea {where} terkini (🆕 baharu · ✍️ sedang ditulis · 📝 sudah jadi draf · ❌ ditolak · ❗ gagal)" if bm else
            f"💡 Latest {where} ideas (🆕 new · ✍️ being written · 📝 drafted · ❌ rejected · ❗ failed)")
    return head + "\n" + "\n".join(f"{icon.get(r.get('status'), '·')} {str(r.get('source_title') or '')[:80]}" for r in rows)


# ---- reads: the vague-wording check and an ayat ---------------------------------------------------------------------------

def check_vague(text: str, lang: str = "bm") -> tuple[str, bool]:
    """The publisher's own vague-wording rule (compliance.vague_hits, rules/compliance.json) on pasted text. Read only."""
    bm = lang == "bm"
    units = compliance.sentences(text)
    if not units:
        return ("Tampal teks yang hendak disemak." if bm else "Paste the text to check."), False
    hits = compliance.vague_hits(units)
    if not hits:
        return ("🔎 Tiada frasa kabur ditemui: setiap frasa disokong angka, tarikh atau nombor entri." if bm else
                "🔎 No vague phrase found: each one is pinned down by a figure, a date or an entry number."), True
    listed = "\n".join(f'• "{h}"' for h in hits[:12])
    if bm:
        return (f"🔎 Frasa kabur ({len(hits)}):\n{listed}\n\nNyatakan butiran tepat (angka, tarikh atau nombor entri) dalam ayat "
                "yang sama atau dua ayat selepasnya. Post baharu dengan frasa begini tidak boleh diluluskan."), True
    return (f"🔎 Vague phrases ({len(hits)}):\n{listed}\n\nState the exact detail (a figure, a date or an entry number) in the "
            "same sentence or the two after it. A new post carrying one of these cannot be approved."), True


def lookup_ayat(text: str, lang: str = "bm", client: Any = None) -> tuple[str, bool]:
    """An ayat by surah:ayat, fetched from the published source the cards use (quran.fetch): the Arabic, the translation and
    where it came from. Read only: the tick that says Wan checked a verse on a card is his alone, on the page."""
    from . import quran
    bm = lang == "bm"
    ref = "".join(str(text or "").split())
    if not quran.parse(ref):
        return ('Tulis rujukan sebagai surah:ayat, contohnya 2:168 atau 2:168-169.' if bm else
                "Write the reference as surah:ayat, for example 2:168 or 2:168-169."), False
    try:
        got = quran.fetch(ref, "regulab" if bm else "linkedin", client)
    except quran.QuranError as exc:
        return f"📖 {exc}", True
    except Exception as exc:  # noqa: BLE001 - a published source that does not answer is said plainly, never guessed around
        log.info("ayat not fetched (%s)", str(exc)[:120])
        return ("📖 Sumber ayat tidak menjawab sekarang. Cuba lagi sebentar." if bm else
                "📖 The verse source did not answer just now. Try again shortly."), True
    foot = (f"Sumber: {got['ayat_ed']}. Untuk kad, namakan {got['ayat']} pada slaid di Jana poster dan tandakan sendiri bahawa "
            "anda sudah menyemaknya." if bm else
            f"Source: {got['ayat_ed']}. For a card, name {got['ayat']} on a slide in Generate poster and tick it as checked "
            "yourself.")
    return f"📖 {quran.label(got['ayat'])}\n\n{got['ayat_ar']}\n\n{got['ayat_tr']}\n\n{foot}"[:3800], True


# ---- Writing style --------------------------------------------------------------------------------------------------------

HARD_HOSTS = ("instagram.com", "linkedin.com", "tiktok.com", "x.com", "twitter.com", "facebook.com", "threads.net")


def add_style(store: Any, link: dict[str, Any], text: str) -> tuple[str, bool]:
    """(what to tell Wan, whether the question is answered). A semasa_writing_styles row, status new, with the links and/or the
    pasted sample; the writing-style worker reads them and writes the instruction and traits. Nothing is copied word for word."""
    urls = _urls(text)[:MAX_LINKS]
    lines = [" ".join(line.split()) for line in URL_RE.sub(" ", str(text or "")).splitlines()]
    sample = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:MAX_SAMPLE]
    if not urls and len(sample) < MIN_SAMPLE:
        return ("A pasted sample needs at least 80 characters. Paste the whole post, or send a link to it.", False)
    if urls and 0 < len(sample) < MIN_SAMPLE:
        sample = ""                                  # a few words beside a link are a remark, not a sample
    row = {"name": "", "source": "analyse", "status": "new", "links": urls, "sample": sample, "images": [],
           "attempts": 0, "created_by": link["user_id"]}
    store.table(STYLES).insert(row).execute()
    what = f"{len(urls)} link(s)" if urls else "the pasted text"
    hidden = any(h in u.lower() for u in urls for h in HARD_HOSTS)
    reply = (f"✍️ Writing style queued from {what}. Semasa describes how it is written, never what it says, and files it "
             "under Gaya penulisan in Semasa.")
    if hidden and not sample:
        reply += ("\nInstagram, LinkedIn, TikTok, X and Facebook often hide a post from a plain fetch. If the analysis comes "
                  "back empty, send the pasted text here too.")
    return reply, True


# ---- the answer to a question the menu asked ------------------------------------------------------------------------------

def take_answer(store: Any, link: dict[str, Any], kind: str, text: str, inbox_id: Any = None, arg: str = "",
                lang: str = "bm") -> tuple[str, list[list[dict[str, str]]]] | None:
    """(reply, buttons) for the questions this module answers. None for a kind that is not this module's (an edit, which needs
    the post and the gate and lives in telegram_bot.py). A question that was not answered (no link in it) stays pending.
    `arg` is what the button narrowed the question to: an idea's stream, a poster's look."""
    if kind == "repo":
        reply, done = add_repo(store, link, text)
    elif kind == "idea":
        reply, done = add_idea(store, link, text, inbox_id, stream=arg or "regulab", lang=lang)
    elif kind in ("poster", "karusel"):
        reply, done = add_idea(store, link, text, inbox_id, fmt="poster" if kind == "poster" else "carousel",
                               look=arg if arg in menu.LOOKS["names"] else "", lang=lang)
    elif kind == "style":
        reply, done = add_style(store, link, text)
    elif kind == "vague":
        reply, done = check_vague(text, lang)
    elif kind == "ayat":
        reply, done = lookup_ayat(text, lang)
    else:
        return None
    if done:
        tt.save_chat_state(store, {"pending": None})
    key = f"{kind}:{arg}" if f"{kind}:{arg}" in menu.ASK_TAB else kind
    # an answer keeps its place in the chat (keep=True); a question that was not answered is still a question
    return reply, [menu.back_row(lang, menu.ASK_TAB.get(key, ""), keep=done)]


def carousel_options(post_id: str) -> tuple[str, list[list[dict[str, str]]]]:
    return ("🖼 Carousel\n\nChoose the slide design first:", [
        [{"text": "Threads", "callback_data": f"c:pcpick:{post_id}:threads"}],
        [{"text": "Grid", "callback_data": f"c:pcpick:{post_id}:grid"},
         {"text": "Info ERA", "callback_data": f"c:pcpick:{post_id}:era"}],
        [{"text": "Photo", "callback_data": f"c:pcpick:{post_id}:photo"},
         {"text": "Image", "callback_data": f"c:pcpick:{post_id}:image"}],
        _back("c:post", "⬅ Post")])


def picture_options(post_id: str, look: str) -> tuple[str, list[list[dict[str, str]]]]:
    return (f"🖼 Carousel · {look}\n\nChoose the picture source:", [
        [{"text": "📷 Use the post picture", "callback_data": f"c:pcgo:{post_id}:{look}:post"}],
        [{"text": "🎨 Original paper/illustration", "callback_data": f"c:pcgo:{post_id}:{look}:none"}],
        _back("c:post", "⬅ Post")])


def single_options(post_id: str) -> tuple[str, list[list[dict[str, str]]]]:
    return ("🎨 Single card\n\nChoose the slide design:", [
        [{"text": "Semasa", "callback_data": f"c:scpick:{post_id}:classic"}],
        [{"text": "Grid", "callback_data": f"c:scpick:{post_id}:grid"},
         {"text": "Info ERA", "callback_data": f"c:scpick:{post_id}:era"}],
        [{"text": "Photo", "callback_data": f"c:scpick:{post_id}:photo"},
         {"text": "Image", "callback_data": f"c:scpick:{post_id}:image"}],
        _back("c:post", "⬅ Post")])


def single_picture_options(post_id: str, look: str) -> tuple[str, list[list[dict[str, str]]]]:
    return (f"🎨 Single card · {look}\n\nChoose the picture source:", [
        [{"text": "📷 Use the post picture", "callback_data": f"c:scgo:{post_id}:{look}:post"}],
        [{"text": "🎨 Original paper/illustration", "callback_data": f"c:scgo:{post_id}:{look}:none"}],
        _back("c:post", "⬅ Post")])


def requeue_single(store: Any, post_id: str, look: str, picture: str) -> str:
    rows = store.table(db.MEDIA).select("id,meta,status").eq("post_id", post_id).eq("mode", "slides") \
        .order("created_at", desc=True).limit(1).execute().data or []
    if not rows:
        return "No single-card render is attached to that post yet. Open Semasa and generate the card first."
    row = rows[0]
    meta = dict(row.get("meta") or {})
    meta.update(look=look, bg="post_image" if picture == "post" else "none", design="card", format="portrait")
    store.table(db.MEDIA).update({"status": "pending", "attempts": 0, "error": None, "meta": meta}).eq("id", row["id"]).execute()
    return ("🎨 Single card queued with the selected design and picture source. "
            "The updated card will appear here when Semasa finishes.")


# ---- Post: carousel and motion from a draft (the card and the edit are in telegram_bot.py) -------------------------------------

def _caption_of(post: dict[str, Any]) -> str:
    lang = post.get("lang") or ("en" if post.get("stream") == "linkedin" else "bm")
    text = (post.get("text") or {}).get(lang) or (post.get("text") or {}).get("en") or (post.get("text") or {}).get("bm") or {}
    return str(text.get("facebook") or text.get("instagram") or text.get("threads") or text.get("linkedin")
               or next(iter(text.values()), "") or "").strip()


def _words_of_post(post: dict[str, Any]) -> str:
    """The film's brief, like the page's motionFromPost: the slides' words when there are any, else the caption."""
    slides = post.get("slides") if isinstance(post.get("slides"), list) else []
    parts = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        lines = [str(s.get("title") or "").strip()] + [f"- {str(p or '').strip()}" for p in (s.get("points") or [])]
        block = "\n".join(x for x in lines if x and x != "-")
        if block:
            parts.append(block)
    return ("\n\n".join(parts) or _caption_of(post))[:1900]


def make_carousel(store: Any, link: dict[str, Any], post: dict[str, Any], look: str = "image", picture: str = "post") -> str:
    """A carousel version of a draft: a NEW idea on the same source with make_slides, written by the idea worker like any
    carousel (its slides and pictures are media jobs, its caption goes through the same hook and citation rules). The draft it
    comes from is not touched."""
    if post.get("status") not in ("draft", "approved", "scheduled"):
        return "That post is no longer active, so I did not make a carousel from it."
    made = store.table(db.IDEAS).select("id,status,brief").contains("brief", {"from_post": post["id"]}).execute().data or []
    if any(i.get("status") in ("new", "working") for i in made):
        return "🖼 A carousel for this post is already with the writer."
    src: dict[str, Any] = {}
    if post.get("idea_id"):
        src = (store.table(db.IDEAS).select("source_title,source_url,source_name,source_summary,reference_urls")
               .eq("id", post["idea_id"]).limit(1).execute().data or [{}])[0]
    stream = "linkedin" if post.get("stream") == "linkedin" else "regulab"
    caption = _caption_of(post)
    row = {"source_title": (src.get("source_title") or post.get("hook") or caption)[:300] or "Carousel from a draft",
           "source_url": src.get("source_url"), "source_name": src.get("source_name") or "Telegram",
           "source_summary": src.get("source_summary"), "reference_urls": src.get("reference_urls") or [],
           "stream": stream, "make_media": "image", "make_slides": True,
           "domain": post.get("domain") if stream == "regulab" else None,
           "angle": post.get("angle") if stream == "linkedin" else None,
           "note": ("A carousel version of an existing draft. Keep every fact and the citation the draft carries and add none. "
                    f"Draft hook: {post.get('hook') or ''} Draft caption: {caption[:600]}")[:2000],
           "status": "new", "created_by": link["user_id"],
           "brief": {"via": "telegram", "catalogue": "post", "format": "carousel", "from_post": post["id"],
                     "look": look, "picture": picture,
                     "hook_required": True, "source_required": True, "requirements": REQUIREMENTS}}
    store.table(db.IDEAS).insert(row).execute()
    return ("🖼 Carousel sent to the writer. It comes back as a new draft with its slides and pictures; the draft you "
            "are looking at is unchanged.")


def make_motion(store: Any, link: dict[str, Any], post: dict[str, Any]) -> tuple[str, list[list[dict[str, str]]]]:
    """A film in the Motion queue, status 'waiting', from a draft: the same row the page's Motion video button writes. Nothing
    starts until you tap Start, and nothing is drawn or voiced until you approve its storyboard (supabase/071)."""
    from .billing import SITE_URL
    if post.get("status") not in ("draft", "approved", "scheduled"):
        return "That post is no longer active, so I did not queue a film from it.", []
    if post.get("stream") == "linkedin":
        return "LinkedIn gets a carousel or a single card, never a film, so I did not queue one.", []
    brief = _words_of_post(post)
    if not brief:
        return "This draft has no words to make a film from.", []
    films = store.table(tt.MOTIONS).select("id,status").contains("options", {"post_id": post["id"]}).execute().data or []
    live = [m for m in films if m.get("status") not in ("done", "error", "failed")]
    stream = "linkedin" if post.get("stream") == "linkedin" else "regulab"
    if live:
        mid = live[0]["id"]
        note = "🎬 A film for this post is already in the Motion queue."
    else:
        lang = post.get("lang") or ("en" if stream == "linkedin" else "bm")
        mid = tt.queue_motion(store, link, brief, source_url=str(post.get("source_url") or ""), stream=stream,
                              language=lang if lang in ("bm", "en") else "bm", idea_id=post.get("idea_id"),
                              options={"post_id": post["id"], "catalogue": "post"})
        note = "🎬 Film queued in Motion from this draft."
    buttons = [[{"text": "▶️ Start (random style)", "callback_data": f"c:ms:{mid}"}],
               [{"text": "🎨 Choose the style", "callback_data": f"msk:{mid}:?en"}],
               [{"text": "🔗 Open Motion in Semasa", "url": f"{SITE_URL.rstrip('/')}/#video"}]]
    return (f"{note}\nTap Start for a random style (one of the 2D styles), or choose the style yourself. Motion writes the "
            "storyboard and waits: nothing is drawn or voiced until you approve it here or in Semasa."), buttons


def start_motion(store: Any, motion_id: str) -> str:
    """Start a waiting film (the Motion trigger wakes the worker). It writes the storyboard and stops at review."""
    got = store.table(tt.MOTIONS).update({"status": "pending"}).eq("id", motion_id).eq("status", "waiting").execute().data
    return ("▶️ Motion started. The storyboard comes here first for your approval; pictures, voice and the film are made only "
            "after that." if got else "That film has already started or is no longer in the queue.")
