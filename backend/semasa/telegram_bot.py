"""Semasa on Telegram (Wan, 7 Nov 2026: "communicate from telegram, approve post and I can attach link so semasa can read",
then "add all relevant features to telegram bot"). `python -m semasa.telegram_bot`, from telegram.yml.

The webhook (supabase/functions/semasa-telegram) stores what Telegram sends in semasa_telegram_inbox and answers at once;
the database wakes this worker for Wan's own messages and taps (repository_dispatch 'telegram'), and a scheduled run is the
net. Only the ONE Telegram account Wan linked from the page (Tetapan → Telegram, a one-time code) is ever obeyed.

What Wan can do from Telegram:
  /draf       drafts waiting for him, each with its picture and ✅ Lulus / ❌ Tolak buttons
  /jadual     the next 7 days, slot by slot
  /status     drafts, approved, scheduled, errors and open watchdog problems at a glance
  /ralat      failed ideas (🔁 Cuba lagi on each) and posts the publisher could not send
  /kesihatan  the watchdog's open problems (the same list the e-mail reports)
  /bil        unpaid invoices and open quotations, with their due dates
  /idea …     text or a link becomes an idea; a bare link does too. He picks ws.regulab or LinkedIn on a button.
  anything else is a question: the AI team answers it with a snapshot of Semasa (it can explain, never change anything).
It also pushes new drafts as they are written (scheduled runs) and the watchdog's alerts (health.py → notify()).

APPROVE goes through the page's own database gate: semasa_telegram_decide() (supabase/069) runs the update as Wan's own
login, so the slot and duplicate guards and approved_by apply exactly as for his click in the page; it approves only the
version he was shown (semasa_telegram_sent.version), and the same compliance scan the publisher runs is checked first.
Nothing here posts: the publisher still sends an approved post at its slot, never early and never late.
"""

from __future__ import annotations

import hashlib
import hmac
import html as htmllib
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

import requests

from . import billing, compliance, db, motion_review, motion_skins
from . import telegram_catalogue as cat
from . import telegram_tools as tt
from .log import get_logger

log = get_logger("semasa.telegram_bot")

TG = "https://api.telegram.org/bot{token}/{method}"
INBOX = "semasa_telegram_inbox"
SENT = "semasa_telegram_sent"
LINK = "semasa_telegram_link"
STATE_KEY = "telegram_bot"
LABEL = b"semasa-telegram-webhook"
SITE = billing.SITE_URL
URL_RE = re.compile(r"https?://[^\s<>\"']+")
PER_RUN = 30                     # inbox rows a run
PUSH_PER_RUN = 5                 # new drafts pushed a run
MSG_MAX = 3900                   # Telegram's limit is 4096
MYT = timedelta(hours=8)
LATE_GRACE = timedelta(minutes=45)   # publisher.LATE_GRACE and the page's PostEditor: a slot more than 45 min gone never sends
COMMANDS = [
    ("robot", "Robot AI: siapa menulis, pilih model / pick the model"),
    ("draf", "Draf menunggu kelulusan / drafts to approve"),
    ("poster", "Buat poster daripada topik/link / make a poster"),
    ("karusel", "Buat karusel / make a carousel"),
    ("motion", "Buat video motion / make a motion video"),
    ("laporan", "Tulis laporan / write a report"),
    ("ingat", "Simpan nota tetap / remember a standing note"),
    ("memori", "Lihat nota tetap / the standing notes"),
    ("jadual", "Jadual 7 hari / the next 7 days"),
    ("status", "Ringkasan Semasa / Semasa at a glance"),
    ("ralat", "Ralat dan idea gagal / errors and failed ideas"),
    ("kesihatan", "Masalah watchdog / open problems"),
    ("bil", "Invois belum dibayar / unpaid invoices"),
    ("idea", "Teks atau link jadi idea / text or a link as an idea"),
    ("menu", "Menu butang / the button menu"),
    ("help", "Senarai arahan / the commands"),
]
HELP = ("Semasa di Telegram 🤖\n\n" + "\n".join(f"/{c} — {d}" for c, d in COMMANDS) +
        "\n\nHantar link terus untuk jadikan idea. Tanya apa-apa tentang Semasa dalam BM atau English.\n"
        "Send a link to make it an idea. Ask anything about Semasa in BM or English.")
STREAM_WORDS = {"regulab": "ws.regulab", "linkedin": "LinkedIn"}


class TelegramError(RuntimeError):
    pass


TOKEN_RE = re.compile(r"bot\d+:[A-Za-z0-9_-]+")


def scrub(text: Any, token: str = "") -> str:
    """Never let the bot token reach a log, the inbox or a message: a requests error names the URL, /bot<TOKEN>/<method>."""
    out = str(text)
    if token:
        out = out.replace(token, "***")
    return TOKEN_RE.sub("bot***", out)


def webhook_secret(token: str) -> str:
    """The X-Telegram-Bot-Api-Secret-Token, derived from the bot token so there is no second secret to keep.
    functions.yml computes the same value for the Edge Function (openssl dgst -sha256 -hmac)."""
    return hmac.new(token.encode(), LABEL, hashlib.sha256).hexdigest()


def secret_fingerprint(secret: str) -> str:
    """A short sha256 of the webhook secret, stored so a changed bot token is noticed. Never the secret itself."""
    return hashlib.sha256(secret.encode()).hexdigest()[:12]


def function_url() -> str:
    base = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
    return f"{base}/functions/v1/semasa-telegram" if base else ""


class Bot:
    def __init__(self, token: str, session: Any = None):
        self.token, self.http = token, session or requests.Session()

    def _post(self, method: str, timeout: int, **kw: Any) -> Any:
        try:
            return self.http.post(TG.format(token=self.token, method=method), timeout=timeout, **kw)
        except requests.RequestException as exc:   # its message carries the URL, and so the token
            raise TelegramError(f"{method}: {type(exc).__name__}: {scrub(exc, self.token)}") from None

    def call(self, method: str, **params: Any) -> Any:
        r = self._post(method, 30, json=params)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if not body.get("ok"):
            why = str(body.get("description") or f"HTTP {getattr(r, 'status_code', '?')}").replace(self.token, "***")
            raise TelegramError(f"{method}: {why}")
        return body.get("result")

    def send(self, chat: int, text: str, buttons: list[list[dict[str, str]]] | None = None, reply_to: int | None = None) -> int:
        params: dict[str, Any] = {"chat_id": chat, "text": text[:MSG_MAX], "disable_web_page_preview": True}
        if buttons:
            params["reply_markup"] = {"inline_keyboard": buttons}
        if reply_to:
            params["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
        res = self.call("sendMessage", **params) or {}
        return int(res.get("message_id") or 0)

    def photo(self, chat: int, url: str, caption: str = "") -> None:
        self.call("sendPhoto", chat_id=chat, photo=url, caption=caption[:1000])

    def document(self, chat: int, name: str, data: bytes, caption: str = "") -> None:
        r = self._post("sendDocument", 60, data={"chat_id": chat, "caption": caption[:1000]},
                       files={"document": (name, data, "text/markdown")})
        try:
            ok = r.json().get("ok")
        except ValueError:
            ok = False
        if not ok:
            raise TelegramError(f"sendDocument: HTTP {getattr(r, 'status_code', '?')}")

    def video(self, chat: int, url: str, caption: str = "") -> None:
        self.call("sendVideo", chat_id=chat, video=url, caption=caption[:1000], supports_streaming=True)

    def drop_buttons(self, chat: int, message_id: int) -> None:
        try:
            self.call("editMessageReplyMarkup", chat_id=chat, message_id=message_id, reply_markup={"inline_keyboard": []})
        except TelegramError as exc:
            log.info("buttons not removed (%s)", exc)


def make_bot() -> Bot | None:
    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    return Bot(token) if token else None


# ---- the link, the webhook ------------------------------------------------------------------------------------------------

def link_of(store: Any) -> dict[str, Any] | None:
    try:
        rows = store.table(LINK).select("*").eq("id", 1).execute().data or []
    except Exception as exc:  # noqa: BLE001 - before supabase/069
        log.info("no link table yet (%s)", str(exc)[:120])
        return None
    return rows[0] if rows else None


def save_state(store: Any, value: dict[str, Any]) -> None:
    try:
        store.table(db.SETTINGS).upsert({"key": STATE_KEY, "value": value}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001
        log.info("state not saved (%s)", str(exc)[:120])


def ensure_webhook(store: Any, bot: Bot, now: datetime) -> dict[str, Any]:
    """Point Telegram at the Edge Function (once, and again whenever it has drifted), name the commands, and keep what
    Telegram says about the webhook in settings.telegram_bot for the page and the watchdog."""
    if os.environ.get("SEMASA_TELEGRAM_TRANSPORT", "").strip().lower() == "hermes":
        me = bot.call("getMe") or {}
        state = {"username": me.get("username"), "transport": "hermes", "webhook": "",
                 "checked_at": now.isoformat(), "set_now": False, "last_error": ""}
        save_state(store, state)
        return state
    want = function_url()
    me = bot.call("getMe") or {}
    info = bot.call("getWebhookInfo") or {}
    rows = store.table(db.SETTINGS).select("value").eq("key", STATE_KEY).execute().data or []
    before = (rows[0].get("value") or {}) if rows else {}
    secret = webhook_secret(bot.token)
    fp = secret_fingerprint(secret)
    # a new bot token derives a new secret: Telegram must be told it, even though the address is the same (and the
    # Edge Function's TELEGRAM_WEBHOOK_SECRET follows when "Deploy functions" runs again: the watchdog says so)
    changed = False
    if want and (info.get("url") != want or before.get("secret_fp") != fp):
        bot.call("setWebhook", url=want, secret_token=secret,
                 allowed_updates=["message", "callback_query"], max_connections=10)
        info = bot.call("getWebhookInfo") or {}
        changed = True
    names = ",".join(c for c, _ in COMMANDS)
    if changed or before.get("commands") != names:   # the menu follows the code
        bot.call("setMyCommands", commands=[{"command": c, "description": d[:256]} for c, d in COMMANDS])
    state = {"username": me.get("username"), "webhook": info.get("url") or "", "pending": info.get("pending_update_count", 0),
             "last_error": info.get("last_error_message") or "", "last_error_at": info.get("last_error_date"),
             "checked_at": now.isoformat(), "set_now": changed, "commands": names,
             "secret_fp": fp if (changed or before.get("secret_fp") == fp) else before.get("secret_fp")}
    save_state(store, state)
    return state


# ---- what Wan reads -------------------------------------------------------------------------------------------------------

def _caption(post: dict[str, Any]) -> str:
    lang = compliance.lang_of(post)
    for plat in compliance.platforms_of(post):
        t = compliance.text_of(post, plat, lang)
        if t:
            return t
    return str(post.get("hook") or "")


def _where(post: dict[str, Any]) -> str:
    when = f"{post.get('date') or 'tiada tarikh'} {post.get('slot') or ''}".strip()
    bits = [STREAM_WORDS.get(post.get("stream") or "regulab", post.get("stream") or ""), when,
            post.get("domain") or post.get("angle") or ""]
    return " · ".join(b for b in bits if b)


def slot_utc(post: dict[str, Any]) -> datetime | None:
    """The post's slot as a UTC moment (date and slot are Malaysia time), or None when either is missing or unreadable."""
    try:
        y, m, d = (int(x) for x in str(post.get("date") or "")[:10].split("-"))
        hh, mm = (int(x) for x in str(post.get("slot") or "").split(":")[:2])
        return datetime(y, m, d, hh, mm, tzinfo=UTC) - MYT
    except (TypeError, ValueError):
        return None


def slot_past(post: dict[str, Any], now: datetime) -> bool:
    due = slot_utc(post)
    return due is not None and due < now - LATE_GRACE


def position_problem(post: dict[str, Any], now: datetime) -> str:
    """The page's position checks (PostEditor): a post with no date and slot, or whose slot is more than 45 minutes gone, is
    never sent by the publisher, so it is not approved here either. Wan moves it in Semasa first."""
    if slot_utc(post) is None:
        return "tiada tarikh atau slot: pilih tarikh dan slot di Semasa (tab Post) dahulu"
    if slot_past(post, now):
        return (f"slot {post.get('date')} {post.get('slot')} MYT sudah lepas lebih 45 minit: penerbit tidak akan "
                "menghantarnya. Pindahkan ke slot baharu di Semasa (tab Post → Jadual → Pindah semua)")
    return ""


def scan(store: Any, post: dict[str, Any], now: datetime | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """(the compliance flags to save with an approval, what stops it): the publisher's own hard checks, plus the page's
    position checks (which depend on the clock, so they stop the approval but are never saved as flags)."""
    from .publisher import load_settings, media_for, scan_entry
    settings = load_settings(store)
    reg = (settings.get("brand") or {}).get("regulab") or {}
    media = media_for(store, list(post.get("media_ids") or []))
    flags = compliance.scan({**post, "media": [scan_entry(m) for m in media if m.get("status") == "done"]},
                            brand=reg, schedule=reg.get("schedule"), indo_extra=(settings.get("bahasa") or {}).get("indo"))
    hard = [f"{f['where']}: {f['msg']}" for f in flags if f["hard"]]
    if any(m.get("status") != "done" or not m.get("generated_media_url") for m in media):
        hard.append("gambar belum siap dijana")
    if len(media) < len(post.get("media_ids") or []):
        hard.append("gambar yang dilampirkan sudah dipadam")
    where = position_problem(post, now or datetime.now(UTC))
    if where:
        hard.insert(0, where)
    return flags, hard


def blockers(store: Any, post: dict[str, Any], now: datetime | None = None) -> list[str]:
    return scan(store, post, now)[1]


def edit_draft_caption(store: Any, post_id: str, caption: str) -> str:
    rows = store.table(db.POSTS).select("id,status,lang,text").eq("id", post_id).eq("status", "draft").execute().data or []
    if not rows:
        return "That draft is no longer editable."
    post = rows[0]
    lang = post.get("lang") or "bm"
    text = dict(post.get("text") or {})
    variants = dict(text.get(lang) or {})
    channel = "linkedin" if lang == "en" else "instagram"
    variants[channel] = caption[:3000]
    text[lang] = variants
    got = store.table(db.POSTS).update({"text": text}).eq("id", post_id).eq("status", "draft").execute().data or []
    return ("✏️ Caption updated. Semasa will re-run its compliance checks before approval."
            if got else "The draft changed before the edit was saved.")


def send_draft(store: Any, bot: Bot, chat: int, post: dict[str, Any], now: datetime | None = None) -> None:
    from .publisher import media_for, pictures_of
    media = media_for(store, list(post.get("media_ids") or []))
    pics = [u for m in media for u in pictures_of(m)]
    if pics:
        for index, picture in enumerate(pics, 1):
            try:
                label = (f"🖼 Carousel · page {index}/{len(pics)}" if len(pics) > 1
                         else f"📝 {_where(post)}")
                bot.photo(chat, picture, label)
            except TelegramError as exc:
                log.info("picture %d/%d not sent (%s)", index, len(pics), exc)
    hard = blockers(store, post, now)
    text = f"📝 Draf · {_where(post)}\n\n{_caption(post)[:3000]}"
    if post.get("citation"):
        text += f"\n\nSumber: {str(post['citation'])[:300]}"
    open_btn = [{"text": "🔗 Buka di Semasa", "url": f"{SITE.rstrip('/')}/#posts"}]
    if hard:
        text += "\n\n⚠️ Approval blocked:\n• " + "\n• ".join(hard[:6])
        buttons = [[{"text": "✏️ Edit", "callback_data": f"c:pe:{post['id']}"},
                    {"text": "🖼 Carousel", "callback_data": f"c:pc:{post['id']}"}],
                   [{"text": "🎨 Single card", "callback_data": f"c:sc:{post['id']}"},
                    {"text": "🎬 Motion", "callback_data": f"c:pm:{post['id']}"}],
                   [{"text": "❌ Reject", "callback_data": f"no:{post['id']}"}], open_btn]
    else:
        buttons = [[{"text": "✏️ Edit", "callback_data": f"c:pe:{post['id']}"},
                    {"text": "🖼 Carousel", "callback_data": f"c:pc:{post['id']}"}],
                   [{"text": "🎨 Single card", "callback_data": f"c:sc:{post['id']}"},
                    {"text": "🎬 Motion", "callback_data": f"c:pm:{post['id']}"}],
                   [{"text": "✅ Approve", "callback_data": f"ok:{post['id']}"},
                    {"text": "❌ Reject", "callback_data": f"no:{post['id']}"}], open_btn]
    mid = bot.send(chat, text, buttons)
    store.table(SENT).upsert({"post_id": post["id"], "version": post["updated_at"], "chat_id": chat, "message_id": mid,
                              "sent_at": datetime.now(UTC).isoformat()}, on_conflict="post_id").execute()


def draft_rows(store: Any) -> list[dict[str, Any]]:
    return store.table(db.POSTS).select("*").eq("status", "draft").execute().data or []


def drafts(store: Any, limit: int = 5, now: datetime | None = None,
           rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Drafts Wan can still approve, soonest slot first: one whose slot is more than 45 minutes gone is left out (the
    publisher would never send it; /draf says how many and where to move them). A draft with no date yet comes last."""
    now = now or datetime.now(UTC)
    rows = [p for p in (draft_rows(store) if rows is None else rows) if not slot_past(p, now)]
    rows.sort(key=lambda p: (str(p.get("date") or "9999"), str(p.get("slot") or "")))
    return rows[:limit]


def schedule_text(store: Any, now: datetime) -> str:
    today = (now + timedelta(hours=8)).date()
    end = today + timedelta(days=7)
    rows = store.table(db.POSTS).select("id,date,slot,stream,status,hook,domain,angle") \
        .in_("status", ["draft", "approved", "scheduled", "posted"]).gte("date", today.isoformat()).execute().data or []
    rows = [p for p in rows if str(p.get("date") or "") <= end.isoformat()]
    if not rows:
        return "Tiada post dalam 7 hari akan datang."
    rows.sort(key=lambda p: (p["date"], p.get("slot") or "", p.get("stream") or ""))
    icon = {"draft": "📝", "approved": "✅", "scheduled": "🕒", "posted": "📤"}
    out, day = ["Jadual 7 hari (📝 draf · ✅ lulus · 🕒 dijadual · 📤 dihantar)"], ""
    for p in rows:
        if p["date"] != day:
            day = p["date"]
            out.append(f"\n{day}")
        hook = (p.get("hook") or p.get("domain") or p.get("angle") or "").strip()[:60]
        out.append(f"{icon.get(p['status'], '·')} {p.get('slot') or '--:--'} {STREAM_WORDS.get(p.get('stream'), p.get('stream'))}"
                   + (f" — {hook}" if hook else ""))
    return "\n".join(out)


def _open_problems(store: Any) -> list[dict[str, Any]]:
    rows = store.table(db.SETTINGS).select("value").eq("key", "health_state").execute().data or []
    state = (rows[0].get("value") or {}) if rows else {}
    return list(state.get("problems") or [])


def status_text(store: Any, now: datetime) -> str:
    posts = store.table(db.POSTS).select("status,date,errors").in_("status", ["draft", "approved", "scheduled"]) \
        .execute().data or []
    count = {s: sum(1 for p in posts if p["status"] == s) for s in ("draft", "approved", "scheduled")}
    errs = sum(1 for p in posts if {k: v for k, v in (p.get("errors") or {}).items() if k not in ("scan", "at")})
    since = (now - timedelta(days=7)).isoformat()
    ideas = store.table(db.IDEAS).select("status,updated_at").in_("status", ["new", "working", "error"]).execute().data or []
    failed = sum(1 for i in ideas if i["status"] == "error" and str(i.get("updated_at") or "") >= since)
    writing = sum(1 for i in ideas if i["status"] in ("new", "working"))
    probs = _open_problems(store)
    return (f"Semasa sekarang ({(now + timedelta(hours=8)).strftime('%d/%m %H:%M')} MYT)\n"
            f"📝 Draf menunggu: {count['draft']}\n✅ Diluluskan: {count['approved']}\n🕒 Dijadualkan: {count['scheduled']}\n"
            f"✍️ Idea sedang ditulis: {writing}\n❗ Idea gagal (7 hari): {failed}\n📮 Post dengan ralat penerbit: {errs}\n"
            f"🩺 Masalah watchdog terbuka: {len(probs)}\n\n/draf untuk lulus · /ralat untuk ralat · /kesihatan untuk masalah")


def errors_reply(store: Any, now: datetime) -> tuple[str, list[list[dict[str, str]]]]:
    since = (now - timedelta(days=7)).isoformat()
    ideas = [i for i in store.table(db.IDEAS).select("id,source_title,error,attempts,updated_at").eq("status", "error")
             .execute().data or [] if str(i.get("updated_at") or "") >= since][:8]
    posts = [p for p in store.table(db.POSTS).select("id,date,slot,stream,hook,errors").in_("status", ["approved", "scheduled"])
             .execute().data or [] if {k: v for k, v in (p.get("errors") or {}).items() if k not in ("scan", "at")}][:8]
    if not ideas and not posts:
        return "Tiada ralat dalam 7 hari. 👍", []
    out, buttons = [], []
    if ideas:
        out.append("❗ Idea gagal:")
        for n, i in enumerate(ideas, 1):
            out.append(f"{n}. {(i.get('source_title') or '')[:70]} — {(i.get('error') or '')[:120]}")
            buttons.append([{"text": f"🔁 Cuba lagi {n}", "callback_data": f"retry:{i['id']}"}])
    if posts:
        out.append("\n📮 Post yang penerbit gagal hantar:")
        for p in posts:
            why = "; ".join(f"{ch}: {str((e or {}).get('message') if isinstance(e, dict) else e)[:90]}"
                            for ch, e in (p.get("errors") or {}).items() if ch not in ("scan", "at"))
            out.append(f"• {p.get('date')} {p.get('slot')} {STREAM_WORDS.get(p.get('stream'), '')} — {why}")
    return "\n".join(out), buttons


def health_text(store: Any) -> str:
    probs = _open_problems(store)
    if not probs:
        return "🩺 Semua berjalan baik. All working."
    lines = [f"• {p.get('area')}: {p.get('what')}" + (f"\n  → {p['todo']}" if p.get("todo") else "") for p in probs[:12]]
    return "🩺 Perlu perhatian:\n" + "\n".join(lines)


def billing_text(store: Any) -> str:
    rows = store.table(db.BILLING_DOCS).select("kind,number,status,total,currency,due_date,client") \
        .in_("status", list(billing.OPEN)).execute().data or []
    if not rows:
        return "💰 Tiada invois atau sebut harga terbuka."
    rows.sort(key=lambda d: str(d.get("due_date") or "9999"))
    lines = ["💰 Terbuka (belum dibayar / belum diterima):"]
    total: dict[str, float] = {}
    for d in rows[:15]:
        cur = d.get("currency") or "MYR"
        total[cur] = total.get(cur, 0.0) + (float(d.get("total") or 0) if d.get("kind") == "invoice" else 0.0)
        who = ((d.get("client") or {}).get("name") or "")[:40]
        amount = f"{cur} {float(d.get('total') or 0):,.2f}"
        lines.append(f"• {d.get('number')} · {who} · {amount} · tarikh akhir {d.get('due_date') or '-'}")
    if total:
        lines.append("\nJumlah invois belum dibayar: " + ", ".join(f"{c} {v:,.2f}" for c, v in total.items()))
    return "\n".join(lines)


# ---- links and ideas ------------------------------------------------------------------------------------------------------

def page_title(url: str) -> str:
    from . import fetch
    try:
        r = fetch.get(url, timeout=15, retries=0)
        m = re.search(r"<title[^>]*>(.*?)</title>", r.text[:200000], re.I | re.S)
        return htmllib.unescape(" ".join(m.group(1).split()))[:200] if m else ""
    except Exception as exc:  # noqa: BLE001 - the idea worker reads the page again; a title is only a courtesy here
        log.info("title not read (%s)", str(exc)[:120])
        return ""


def offer_idea(store: Any, bot: Bot, chat: int, row: dict[str, Any], text: str, reply_to: int | None) -> str:
    urls = URL_RE.findall(text)
    note = URL_RE.sub("", re.sub(r"^/idea(@\w+)?", "", text.strip())).strip()
    if not urls and not note:
        bot.send(chat, "Tulis /idea diikuti teks atau link. Contoh: /idea https://www.npra.gov.my/… fokus pada amaran label")
        return "asked for text"
    head = page_title(urls[0]) if urls else ""
    shown = (f"🔗 {head}\n{urls[0]}" if urls else f"💡 {note[:300]}") + (f"\n\nNota: {note[:300]}" if urls and note else "")
    bot.send(chat, shown + "\n\nJadikan idea untuk:", [[
        {"text": "ws.regulab", "callback_data": f"idea:r:{row['id']}"},
        {"text": "LinkedIn", "callback_data": f"idea:l:{row['id']}"},
        {"text": "Batal", "callback_data": f"idea:x:{row['id']}"}]], reply_to=reply_to)
    return "offered an idea"


def make_idea(store: Any, link: dict[str, Any], source: dict[str, Any], stream: str) -> dict[str, Any]:
    msg = (source.get("payload") or {}).get("message") or {}
    text = str(msg.get("text") or msg.get("caption") or "")
    urls = URL_RE.findall(text)
    note = URL_RE.sub("", re.sub(r"^/idea(@\w+)?", "", text.strip())).strip()
    title = (page_title(urls[0]) if urls else "") or note[:200] or (urls[0] if urls else "")
    row = {"source_title": title[:300], "source_url": urls[0] if urls else None, "source_name": "Telegram",
           "stream": stream, "make_media": "image", "note": note[:2000], "reference_urls": urls[1:8],
           "status": "new", "created_by": link["user_id"], "brief": {"via": "telegram", "telegram_inbox_id": source["id"]}}
    return (store.table(db.IDEAS).insert(row).execute().data or [row])[0]


def idea_from(store: Any, source_id: Any) -> dict[str, Any] | None:
    """The idea already made from this Telegram message (brief.telegram_inbox_id), so a double tap makes one idea, not two.
    Runs are one at a time (telegram.yml's concurrency group), so reading first is enough."""
    try:
        got = store.table(db.IDEAS).select("id,source_title,stream").contains("brief", {"telegram_inbox_id": source_id}) \
            .limit(1).execute().data or []
    except Exception as exc:  # noqa: BLE001 - unreadable: say so rather than risk a second idea
        raise TelegramError(f"ideas not read ({str(exc)[:120]})") from None
    return got[0] if got else None


# ---- questions ------------------------------------------------------------------------------------------------------------

SYSTEM = ("You are Semasa's assistant on Telegram for Wan (Registered Chemist, regulatory affairs specialist, owner of WS "
          "REGULAB). Semasa is his content and business system: ideas → drafts → his approval → the publisher posts to "
          "ws.regulab (Facebook, Instagram, Threads) and his LinkedIn; billing; FAQ; watchdog. Answer briefly, in the "
          "language he writes: Malaysian Bahasa Malaysia (never Bahasa Indonesia) or English. Plain text, no markdown. "
          "Use the SNAPSHOT for facts about Semasa; it is current. You cannot approve, post, delete or change anything "
          "yourself: say which command does it (/draf to approve, /poster, /karusel, /motion, /laporan, /idea, /robot to pick "
          "the model, /jadual, /status, /ralat, /kesihatan, /bil, /ingat to save a note). On regulations, "
          "never invent a number, date, limit or reference; say what should be checked and where.")


def history(store: Any, row_id: int, n: int = 6) -> list[tuple[str, str]]:
    rows = store.table(INBOX).select("id,payload,note").eq("kind", "private").eq("status", "done").lt("id", row_id) \
        .order("id", desc=True).limit(n).execute().data or []
    out = []
    for r in reversed(rows):
        q = str(((r.get("payload") or {}).get("message") or {}).get("text") or "")
        a = str(r.get("note") or "")
        if q and a.startswith("answered: "):
            out.append((q[:600], a[len("answered: "):][:800]))
    return out


def context(store: Any, link: dict[str, Any] | None, row: dict[str, Any], now: datetime) -> tuple[str, str]:
    """(who I am, what I know): the robot the router chose, Wan's standing notes, the snapshot and the last turns."""
    t = tt.team(store)
    chosen = t.get("chosen") or {}
    me = (f"You are answering through {chosen.get('name')} running the model {chosen.get('model')}, chosen by Semasa's AI team "
          "router. If Wan asks which model or robot you are, say exactly that and nothing else about your origin."
          if chosen else "If Wan asks which model you are, say that Semasa's AI team router chose it and /robot shows which.")
    notes = tt.notes(store, link["user_id"]) if link else []
    turns = (tt.recent_turns(store, link["user_id"]) if link else []) or history(store, row["id"])
    snap = status_text(store, now) + "\n\n" + schedule_text(store, now)[:1500] + "\n\n" + health_text(store)[:800]
    known = ("WAN'S STANDING NOTES (always follow)\n" + ("\n".join(f"- {n['note']}" for n in notes) or "(none)") +
             f"\n\nSNAPSHOT\n{snap}\n\nEARLIER\n" + ("\n".join(f"Wan: {q}\nSemasa: {a}" for q, a in turns) or "(none)"))
    return me, known


def answer(store: Any, llm: Any, row: dict[str, Any], text: str, now: datetime,
           link: dict[str, Any] | None = None) -> tuple[str, str]:
    """(the answer, the robot and model that wrote it)."""
    if llm is None:
        return "AI tidak tersedia sekarang. Cuba /status atau /draf.", ""
    me, known = context(store, link, row, now)
    try:
        got, who = tt.ask(llm, SYSTEM + " " + me, f"{known}\n\nWAN ASKS\n{text[:3000]}")
    except Exception as exc:  # noqa: BLE001
        log.warning("answer failed: %s", str(exc)[:160])
        got, who = "", ""
    return (got or "Maaf, AI tidak menjawab. Cuba lagi sebentar."), who


def report(store: Any, llm: Any, link: dict[str, Any], row: dict[str, Any], topic: str, now: datetime) -> tuple[str, str]:
    """(the report in Markdown, who wrote it) for /laporan."""
    if llm is None:
        return "", ""
    _me, known = context(store, link, row, now)
    got, who = tt.ask(llm, tt.REPORT_SYSTEM, f"{known}\n\nREPORT REQUEST\n{topic[:3000]}", max_tokens=3000)
    return got, who


# ---- one inbox row --------------------------------------------------------------------------------------------------------

DECIDE_WORDS = {
    "not_linked": "Akaun Telegram ini tidak disambung ke Semasa.",
    "gone": "Draf ini sudah tiada.",
    "bad_action": "Arahan tidak dikenali.",
}


def decide(store: Any, bot: Bot, link: dict[str, Any], chat: int, message_id: int, post_id: str, action: str,
           now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    rows = store.table(db.POSTS).select("*").eq("id", post_id).execute().data or []
    if not rows:
        bot.send(chat, DECIDE_WORDS["gone"], reply_to=message_id)
        return "gone"
    post = rows[0]
    sent = store.table(SENT).select("version,message_id").eq("post_id", post_id).execute().data or []
    version = sent[0]["version"] if sent else None
    # the version kept is the one in the NEWEST preview (every resend overwrites it): a tap on an older message would decide
    # a version that message never showed, so it is refused and the current preview is sent again
    shown_in = int((sent[0].get("message_id") or 0) if sent else 0)
    if post.get("status") == "draft" and shown_in and message_id and int(message_id) != shown_in:
        bot.drop_buttons(chat, message_id)
        bot.send(chat, "Ini pratonton lama: ada pratonton lebih baharu untuk draf ini. Tiada apa diubah. Ini versi terkini:",
                 reply_to=message_id)
        send_draft(store, bot, chat, post, now)
        return "old preview"
    flags: list[dict[str, Any]] = []
    if action == "approve":
        flags, hard = scan(store, post, now)
        if hard:
            bot.send(chat, "⚠️ Belum boleh diluluskan:\n• " + "\n• ".join(hard[:6]), reply_to=message_id)
            return "blocked"
    try:
        res = store.rpc("semasa_telegram_decide", {"p_post": post_id, "p_version": version, "p_action": action,
                                                   "p_telegram_user_id": link["telegram_user_id"], "p_flags": flags,
                                                   "p_hard_flags": compliance.hard_count(flags)}).execute().data
    except Exception as exc:  # noqa: BLE001 - the gate's own refusal (slot taken, duplicate words) is Wan's to read
        why = getattr(exc, "message", None) or str(exc)
        bot.send(chat, f"⛔ Tidak diluluskan: {str(why).replace('semasa: ', '')[:400]}", reply_to=message_id)
        return "refused"
    res = str(res or "")
    if res == "ok":
        bot.drop_buttons(chat, message_id)
        if action == "approve":
            bot.send(chat, f"✅ Diluluskan. Penerbit akan hantar pada slotnya: {post.get('date')} {post.get('slot')}.",
                     reply_to=message_id)
        else:
            bot.send(chat, "❌ Ditolak.", reply_to=message_id)
        return action + "d"
    if res == "changed":
        bot.drop_buttons(chat, message_id)
        bot.send(chat, "Draf ini telah berubah sejak dihantar. Ini versi terkini:", reply_to=message_id)
        send_draft(store, bot, chat, post, now)
        return "changed"
    if res.startswith("status:"):
        bot.drop_buttons(chat, message_id)
        bot.send(chat, f"Draf ini sudah {res.split(':', 1)[1]}.", reply_to=message_id)
        return res
    bot.send(chat, DECIDE_WORDS.get(res, f"Tidak berjaya: {res}"), reply_to=message_id)
    return res


def handle_callback(store: Any, bot: Bot, link: dict[str, Any], row: dict[str, Any], now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    cq = row["payload"]["callback_query"]
    data = str(cq.get("data") or "")
    msg = cq.get("message") or {}
    chat, mid = int(msg.get("chat", {}).get("id") or link["chat_id"]), int(msg.get("message_id") or 0)
    kind, _, rest = data.partition(":")
    if kind == "c":
        if rest == "home":
            text_, buttons = cat.home_reply(link)
        elif rest == "model":
            text_, buttons = cat.model_reply(store)
        elif rest in ("repo", "idea", "style"):
            cat.ask(store, rest)
            text_, buttons = cat.prompt_reply(rest)
        elif rest == "post":
            text_, buttons = cat.post_reply(SITE)
        elif rest.startswith("mt:"):
            text_, buttons = cat.task_reply(store, rest.split(":", 1)[1])
        elif rest.startswith("pin:"):
            _prefix, job, slug = rest.split(":", 2)
            text_, buttons = cat.apply_pin(store, job, slug)
        elif rest.startswith("pe:"):
            post_id = rest.split(":", 1)[1]
            cat.ask(store, "post_edit", post_id)
            bot.send(chat, "✏️ Send the replacement caption now. This only edits a draft and does not publish it.", reply_to=mid)
            return "catalogue edit asked"
        elif rest.startswith("pc:"):
            post_id = rest.split(":", 1)[1]
            text_, buttons = cat.carousel_options(post_id)
            bot.send(chat, text_, buttons, reply_to=mid)
            return "catalogue carousel options"
        elif rest.startswith("pcpick:"):
            _, post_id, look = rest.split(":", 2)
            text_, buttons = cat.picture_options(post_id, look)
            bot.send(chat, text_, buttons, reply_to=mid)
            return "catalogue carousel picture"
        elif rest.startswith("pcgo:"):
            _, post_id, look, picture = rest.split(":", 3)
            posts = store.table(db.POSTS).select("*").eq("id", post_id).limit(1).execute().data or []
            reply = cat.make_carousel(store, link, posts[0], look, picture) if posts else "That draft was not found."
            bot.send(chat, reply, reply_to=mid)
            return "catalogue carousel queued"
        elif rest.startswith("sc:"):
            post_id = rest.split(":", 1)[1]
            text_, buttons = cat.single_options(post_id)
            bot.send(chat, text_, buttons, reply_to=mid)
            return "catalogue single card options"
        elif rest.startswith("scpick:"):
            _, post_id, look = rest.split(":", 2)
            text_, buttons = cat.single_picture_options(post_id, look)
            bot.send(chat, text_, buttons, reply_to=mid)
            return "catalogue single card picture"
        elif rest.startswith("scgo:"):
            _, post_id, look, picture = rest.split(":", 3)
            bot.send(chat, cat.requeue_single(store, post_id, look, picture), reply_to=mid)
            return "catalogue single card queued"
        elif rest.startswith("pm:"):
            post_id = rest.split(":", 1)[1]
            posts = store.table(db.POSTS).select("*").eq("id", post_id).limit(1).execute().data or []
            if posts:
                reply, buttons = cat.make_motion(store, link, posts[0])
                bot.send(chat, reply, buttons or None, reply_to=mid)
            else:
                bot.send(chat, "That draft was not found.", reply_to=mid)
            return "catalogue motion"
        elif rest == "pd":
            for post in drafts(store, now=now):
                send_draft(store, bot, chat, post, now)
            return "catalogue drafts"
        elif rest.startswith("ms:"):
            bot.send(chat, cat.start_motion(store, rest.split(":", 1)[1]), reply_to=mid)
            return "catalogue motion started"
        else:
            text_, buttons = cat.home_reply(link)
        bot.send(chat, text_, buttons, reply_to=mid)
        return "catalogue button"
    if kind in ("ok", "no"):
        return decide(store, bot, link, chat, mid, rest, "approve" if kind == "ok" else "reject", now)
    if kind == "idea":
        choice, _, src = rest.partition(":")
        bot.drop_buttons(chat, mid)
        if choice == "x":
            bot.send(chat, "Dibatalkan.", reply_to=mid)
            return "idea cancelled"
        got = store.table(INBOX).select("*").eq("id", int(src or 0)).execute().data or []
        if not got or int(got[0].get("from_id") or 0) != int(link["telegram_user_id"]):
            bot.send(chat, "Mesej asal tidak dijumpai.", reply_to=mid)
            return "idea source missing"
        made = idea_from(store, got[0]["id"])
        if made:                          # a second tap on the same message (or on the other stream's button)
            bot.send(chat, f"💡 Idea ini sudah dihantar ({STREAM_WORDS.get(made.get('stream'), made.get('stream') or '')}): "
                           f"{made.get('source_title') or ''}", reply_to=mid)
            return "idea already made"
        stream = "linkedin" if choice == "l" else "regulab"
        idea = make_idea(store, link, got[0], stream)
        bot.send(chat, f"💡 Idea {STREAM_WORDS[stream]} dihantar: {idea.get('source_title') or ''}\n"
                       "Semasa akan baca dan tulis draf; anda akan terima draf di sini untuk diluluskan.", reply_to=mid)
        return "idea made"
    if kind == "menu":
        if rest in ("home", "main", "prev"):
            text_, buttons = cat.home_reply(link)
            bot.send(chat, text_, buttons, reply_to=mid)
            return "menu home"
        if rest in tt.NEEDS_TOPIC:
            bot.send(chat, tt.ask_topic(store, rest))
            return f"menu asks {rest}"
        fake = {**row, "payload": {"message": {"message_id": mid, "chat": {"id": chat}, "text": f"/{rest}"}}}
        return handle_message(store, bot, link, fake, lambda: None, now)
    if kind == "menug":
        try:
            index = int(rest)
        except ValueError:
            index = -1
        text_, buttons = cat.home_reply(link)
        bot.send(chat, text_, buttons, reply_to=mid)
        return f"menu group {index}"
    if kind == "pin":
        bot.drop_buttons(chat, mid)
        bot.send(chat, tt.set_pin(store, rest), reply_to=mid)
        return f"pin {rest}"
    if kind == "forget":
        bot.drop_buttons(chat, mid)
        bot.send(chat, tt.forget(store, link["user_id"], rest), reply_to=mid)
        return "forgot a note"
    if kind == "fb":
        what, _, src = rest.partition(":")
        bot.drop_buttons(chat, mid)
        bot.send(chat, tt.on_feedback(store, what, src), reply_to=mid)
        return f"feedback {what}"
    if kind in ("sbok", "sbre", "sbrej"):
        # a Motion storyboard (Wan, 7 Nov 2026: approved before a picture is drawn), through the page's own decision (071);
        # 072 adds 'reject' so a storyboard can be stopped, not just approved or rewritten
        action = {"sbok": "approve", "sbre": "rewrite", "sbrej": "reject"}[kind]
        motion_id, _, written = rest.partition(":")
        try:
            args = {"p_motion": motion_id, "p_action": action, "p_telegram_user_id": link["telegram_user_id"],
                    "p_written": int(written) if written.isdigit() else None}
            res = str(store.rpc("semasa_telegram_motion_decide", args).execute().data or "")
        except Exception as exc:  # noqa: BLE001 - shown to Wan as it is
            res = (getattr(exc, "message", None) or str(exc)).replace("semasa: ", "")[:300]
        if res == "ok" or res.startswith("status:"):
            bot.drop_buttons(chat, mid)
        bot.send(chat, motion_review.decide_words(res, action), reply_to=mid)
        return f"storyboard {action}: {res}"
    if kind == "sbrf":
        # 🔄 Refresh status: read the film's current status back, so Wan can confirm an earlier decision landed
        motion_id = rest
        try:
            rows = store.table(tt.MOTIONS).select("status").eq("id", motion_id).limit(1).execute().data or []
        except Exception as exc:  # noqa: BLE001
            rows = []
            log.info("refresh motion status not read (%s)", str(exc)[:120])
        if not rows:
            bot.send(chat, "Video itu sudah tiada.", reply_to=mid)
        else:
            status = rows[0].get("status")
            bot.send(chat, motion_review.status_words(status), reply_to=mid)
        return f"storyboard refresh: {rows[0].get('status') if rows else 'gone'}"
    if kind == "msk":
        # the film's style, chosen here as on the page: "<id>" opens the picker, "<id>:<style>" sets it and starts the film
        film, _, key = rest.partition(":")
        bm = not key.endswith("en")
        if key in ("", "?en"):
            text_, rows_ = motion_skins.picker(film, bm)
            if not bm:
                rows_ = [[{**b, "callback_data": b["callback_data"] + "|en"} for b in r] for r in rows_]
            bot.send(chat, text_, rows_, reply_to=mid)
            return "motion style picker"
        bot.drop_buttons(chat, mid)
        bot.send(chat, motion_skins.pick_and_start(store, film, key.removesuffix("|en"), bm), reply_to=mid)
        return "motion style chosen"
    if kind == "mgo":
        bot.drop_buttons(chat, mid)
        bot.send(chat, tt.start_motion(store, rest), reply_to=mid)
        return "motion started"
    if kind == "retry":
        upd = store.table(db.IDEAS).update({"status": "new", "error": None}).eq("id", rest).eq("status", "error").execute().data
        bot.drop_buttons(chat, mid)
        bot.send(chat, "🔁 Idea dihantar semula kepada penulis." if upd else "Idea itu tidak lagi gagal.", reply_to=mid)
        return "idea retried" if upd else "retry skipped"
    return "unknown button"


def handle_message(store: Any, bot: Bot, link: dict[str, Any], row: dict[str, Any], llm_factory: Any, now: datetime) -> str:
    msg = row["payload"].get("message") or {}
    chat, mid = int(msg["chat"]["id"]), int(msg.get("message_id") or 0)
    text = str(msg.get("text") or msg.get("caption") or "").strip()
    pending_answer = cat.waiting(store, text)
    if pending_answer:
        kind, _arg = pending_answer
        if kind in ("repo", "idea", "style"):
            reply = cat.take_answer(store, link, kind, text, row.get("id"))
            if reply:
                bot.send(chat, reply[0], reply[1], reply_to=mid)
                return f"catalogue {kind}"
        if kind == "post_edit":
            reply = edit_draft_caption(store, _arg, text)
            cat.clear_pending(store)
            bot.send(chat, reply, reply_to=mid)
            posts = store.table(db.POSTS).select("*").eq("id", _arg).limit(1).execute().data or []
            if posts:
                send_draft(store, bot, chat, posts[0], now)
            return "catalogue post edited"
    asked = tt.take_pending(store, text)                               # legacy menu question
    if asked:
        text = asked
    cmd = text.split()[0].split("@")[0].lower().lstrip("/") if text.startswith("/") else ""
    if cmd in ("start", "menu"):
        cat.clear_pending(store)
        text_, buttons = cat.home_reply(link)
        bot.send(chat, text_, buttons)
        return "catalogue menu"
    if not cmd and text:
        fixed = tt.take_correction(store, link["user_id"], text)        # after 👎: this message is the correction
        if fixed:
            bot.send(chat, fixed, reply_to=mid)
            return "correction saved"
    if cmd in ("robot", "bot", "model", "ai", "robots"):
        text_, buttons = tt.robot_reply(store)
        bot.send(chat, text_, buttons)
        return "robots"
    if cmd in ("ingat", "remember"):
        bot.send(chat, tt.remember(store, link["user_id"], re.sub(r"^/\w+(@\w+)?", "", text).strip()), reply_to=mid)
        return "remembered"
    if cmd in ("memori", "memory", "nota"):
        text_, buttons = tt.memory_reply(store, link["user_id"])
        bot.send(chat, text_, buttons or None)
        return "memory"
    if cmd in ("poster", "karusel", "carousel"):
        bot.send(chat, tt.make_poster(store, link, text, cmd), reply_to=mid)
        return f"{cmd} idea"
    if cmd in ("motion", "video"):
        text_, buttons, _mid = tt.make_motion(store, link, text, cmd)
        bot.send(chat, text_, buttons or None, reply_to=mid)
        return "motion queued" if _mid else "motion asked"
    if cmd in ("laporan", "report"):
        topic = re.sub(r"^/\w+(@\w+)?", "", text).strip()
        if not topic:
            bot.send(chat, "Tulis /laporan diikuti topik. Contoh: /laporan prestasi post minggu ini dan apa perlu ditambah baik")
            return "report asked"
        body, who = report(store, llm_factory(), link, row, topic, now)
        if not body:
            bot.send(chat, "Maaf, laporan tidak dapat ditulis sekarang. Cuba lagi sebentar.", reply_to=mid)
            return "report failed"
        name, data = tt.report_file(topic, body, now)
        bot.send(chat, body[:3500] + ("\n…" if len(body) > 3500 else "") + (f"\n\n— {who}" if who else ""), reply_to=mid)
        try:
            bot.document(chat, name, data, f"📄 {topic[:200]}")
        except Exception as exc:  # noqa: BLE001 - the text above already carries the report
            log.info("report file not sent (%s)", str(exc)[:120])
        tt.log_turn(store, link["user_id"], text, body)
        return "report"
    if cmd in ("help", "mula", "bantuan"):
        bot.send(chat, HELP)
        return "help"
    if cmd in ("draf", "drafts", "draft"):
        every = draft_rows(store)
        rows = drafts(store, now=now, rows=every)
        late = sum(1 for p in every if slot_past(p, now))
        if not rows and not late:
            bot.send(chat, "Tiada draf menunggu kelulusan. 👍")
        for p in rows:
            send_draft(store, bot, chat, p, now)
        if late:
            bot.send(chat, f"⏰ {late} draf lagi slotnya sudah lepas lebih 45 minit, jadi tidak boleh diluluskan di sini: "
                           "penerbit tidak menghantar post yang lewat. Pindahkan ke slot baharu di Semasa (tab Post → Jadual → "
                           "Pindah semua), kemudian /draf semula.",
                     [[{"text": "🔗 Buka di Semasa", "url": f"{SITE.rstrip('/')}/#posts"}]])
        return f"{len(rows)} draft(s)" + (f", {late} past their slot" if late else "")
    if cmd in ("jadual", "schedule"):
        bot.send(chat, schedule_text(store, now))
        return "schedule"
    if cmd == "status":
        bot.send(chat, status_text(store, now))
        return "status"
    if cmd in ("ralat", "errors"):
        text_, buttons = errors_reply(store, now)
        bot.send(chat, text_, buttons or None)
        return "errors"
    if cmd in ("kesihatan", "health"):
        bot.send(chat, health_text(store))
        return "health"
    if cmd in ("bil", "billing", "invois"):
        bot.send(chat, billing_text(store))
        return "billing"
    if cmd == "idea" or (not cmd and URL_RE.search(text)):
        return offer_idea(store, bot, chat, row, text, mid)
    if cmd:
        bot.send(chat, "Arahan tidak dikenali.\n\n" + HELP)
        return "unknown command"
    if not text:
        bot.send(chat, "Hantar teks atau link. Gambar dan fail belum dibaca di sini.")
        return "no text"
    reply, who = answer(store, llm_factory(), row, text, now, link)
    bot.send(chat, reply + (f"\n\n— {who}" if who else ""), tt.feedback_buttons(row["id"]), reply_to=mid)
    tt.log_turn(store, link["user_id"], text, reply)
    return "answered: " + reply[:800]


def claim(store: Any) -> list[dict[str, Any]]:
    rows = store.table(INBOX).select("*").in_("kind", ["private", "callback"]).eq("status", "new").order("id") \
        .limit(PER_RUN).execute().data or []
    out = []
    for r in rows:
        got = store.table(INBOX).update({"status": "working"}).eq("id", r["id"]).eq("status", "new").execute().data
        if got:
            out.append(r)
    return out


def push_new_drafts(store: Any, bot: Bot, link: dict[str, Any], now: datetime | None = None) -> int:
    """Drafts written since the last push, once their pictures are ready: each lands in Telegram with its buttons."""
    known = {r["post_id"] for r in store.table(SENT).select("post_id").execute().data or []}
    linked_at = str(link.get("linked_at") or "")
    now = now or datetime.now(UTC)
    todo = [p for p in drafts(store, 50, now) if p["id"] not in known and str(p.get("created_at") or "") >= linked_at]
    n = 0
    from .publisher import media_for
    for p in todo:
        if n >= PUSH_PER_RUN:
            break
        media = media_for(store, list(p.get("media_ids") or []))
        if any(m.get("status") not in ("done", "error") for m in media):
            continue                      # still drawing: it goes on a later run, with its picture
        try:
            send_draft(store, bot, int(link["chat_id"]), p, now)
            n += 1
        except Exception as exc:  # noqa: BLE001
            log.warning("draft %s not pushed: %s", p["id"], str(exc)[:160])
    return n


def notify(store: Any, text: str, bot: Bot | None = None) -> bool:
    """A message to Wan on Telegram (the watchdog's alerts). False, quietly, when no bot or no link."""
    bot = bot or make_bot()
    link = link_of(store) if bot else None
    if not bot or not link:
        return False
    try:
        bot.send(int(link["chat_id"]), text)
        return True
    except Exception as exc:  # noqa: BLE001
        log.info("telegram notify failed (%s)", str(exc)[:160])
        return False


def default_llm(store: Any) -> Any:
    try:
        from . import ai_config, api_status
        from .llm import LLM
        api_status.attach(store, "telegram")
        return LLM(ai_config.llm_for(store))
    except Exception as exc:  # noqa: BLE001
        log.warning("no LLM: %s", exc)
        return None


def run(store: Any, bot: Bot | None = None, now: datetime | None = None, llm_factory: Any = None,
        webhook: bool = True, push: bool = True) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    bot = bot if bot is not None else make_bot()
    out: dict[str, Any] = {"handled": 0, "errors": 0, "pushed": 0}
    if bot is None:
        out["note"] = "TELEGRAM_BOT_TOKEN is not set"
        return out
    if webhook:
        try:
            out["webhook"] = ensure_webhook(store, bot, now).get("webhook")
        except Exception as exc:  # noqa: BLE001 - the watchdog reads settings.telegram_bot and reports it
            log.warning("webhook check failed: %s", scrub(exc, getattr(bot, "token", "")))
            out["webhook_error"] = scrub(exc, getattr(bot, "token", ""))[:200]
    link = link_of(store)
    if not link:
        out["note"] = "no Telegram account linked yet (Tetapan → Telegram)"
        return out
    cache: dict[str, Any] = {}

    def llm() -> Any:
        if "llm" not in cache:
            cache["llm"] = (llm_factory or default_llm)(store)
        return cache["llm"]
    for row in claim(store):
        try:
            if int(row.get("from_id") or 0) != int(link["telegram_user_id"]):
                note, status = "not the linked account", "skipped"
            elif row["kind"] == "callback":
                note, status = handle_callback(store, bot, link, row, now), "done"
            else:
                note, status = handle_message(store, bot, link, row, llm, now), "done"
            out["handled"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad message never stops the others
            why = scrub(exc, getattr(bot, "token", ""))                # a backstop: Bot already scrubs its own errors
            log.warning("telegram row %s failed: %s", row["id"], why)
            note, status = f"{type(exc).__name__}: {why[:300]}", "error"
            out["errors"] += 1
            try:
                bot.send(int(link["chat_id"]), f"⚠️ Semasa tersangkut pada mesej itu: {why[:200]}")
            except Exception:  # noqa: BLE001
                pass
        store.table(INBOX).update({"status": status, "note": str(note)[:1000], "done_at": now.isoformat()}) \
            .eq("id", row["id"]).execute()
    if push:
        out["pushed"] = push_new_drafts(store, bot, link, now)
        out["videos"] = push_videos(store, bot, link, now)
        out["storyboards"] = push_storyboards(store, bot, link)
    return out


def push_storyboards(store: Any, bot: Bot, link: dict[str, Any]) -> int:
    """Motion storyboards waiting on Wan that never reached Telegram (the motion worker sends each itself; this is the net)."""
    n = 0
    for r in motion_review.due(store):
        try:
            if motion_review.telegram_notify(store, r, bot=bot, link=link):
                n += 1
        except Exception as exc:  # noqa: BLE001
            log.info("storyboard %s not sent (%s)", r["id"], str(exc)[:120])
    return n


def push_videos(store: Any, bot: Bot, link: dict[str, Any], now: datetime) -> int:
    """Films asked for on Telegram (/motion), sent back once they are done."""
    st = tt.chat_state(store)
    sent = list(st.get("videos_sent") or [])
    n = 0
    for v in tt.due_motion_videos(store, str(st.get("videos_since") or link.get("linked_at") or "")):
        if v["id"] in sent:
            continue
        try:
            bot.video(int(link["chat_id"]), v["video_url"], f"🎬 {(v.get('title') or v.get('brief') or '')[:200]}")
            sent.append(v["id"])
            n += 1
        except Exception as exc:  # noqa: BLE001
            log.info("video %s not sent (%s)", v["id"], str(exc)[:120])
    if n:
        tt.save_chat_state(store, {"videos_sent": sent[-50:]})
    return n


def main() -> int:
    out = run(db.client())
    print(f"Telegram: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
