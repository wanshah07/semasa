"""Semasa on Telegram (Wan, 7 Nov 2026): only the linked account is obeyed, approve goes through the database gate with the
version Wan was shown, a link becomes an idea on his tap, questions are answered, new drafts are pushed once."""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fakestore import FakeStore  # noqa: E402

from semasa import db, health  # noqa: E402
from semasa import telegram_bot as tb

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
WAN, STRANGER, CHAT = 111, 999, 111
LINK = {"id": 1, "telegram_user_id": WAN, "chat_id": CHAT, "username": "wan", "user_id": "u-wan",
        "linked_at": "2026-11-07T00:00:00+00:00"}
GOOD = {"bm": {"facebook": "Notifikasi kosmetik bukan kelulusan produk. Semak status di portal NPRA sebelum jual.",
               "instagram": "Notifikasi kosmetik bukan kelulusan produk.", "threads": "Notifikasi bukan kelulusan."}}


class Bot:
    token = "123:ABC"

    def __init__(self, webhook=""):
        self.calls, self.n, self.webhook = [], 100, webhook

    def call(self, method, **p):
        self.calls.append((method, p))
        if method == "getMe":
            return {"username": "semasa_bot"}
        if method == "getWebhookInfo":
            return {"url": self.webhook, "pending_update_count": 0}
        if method == "setWebhook":
            self.webhook = p["url"]
        if method in ("sendMessage", "sendPhoto"):
            self.n += 1
            return {"message_id": self.n}
        return True

    send, photo, drop_buttons = tb.Bot.send, tb.Bot.photo, tb.Bot.drop_buttons

    def sent(self):
        return [p for m, p in self.calls if m == "sendMessage"]


class Store(FakeStore):
    """FakeStore plus the one RPC: semasa_telegram_decide's rules (supabase/069) on the fake tables."""

    def __init__(self, **tables):
        super().__init__(**tables)
        self.rpcs = []

    def rpc(self, name, args):
        self.rpcs.append((name, args))
        store = self

        class R:
            def execute(self):
                from types import SimpleNamespace
                post = next((p for p in store.tables[db.POSTS] if p["id"] == args["p_post"]), None)
                if args["p_telegram_user_id"] != WAN:
                    return SimpleNamespace(data="not_linked")
                if post is None:
                    return SimpleNamespace(data="gone")
                if post["status"] != "draft":
                    return SimpleNamespace(data="status:" + post["status"])
                if args["p_version"] != post["updated_at"]:
                    return SimpleNamespace(data="changed")
                if args["p_action"] == "approve" and args.get("p_hard_flags"):
                    raise RuntimeError("violates check constraint semasa_posts_approve_clean")
                post["status"] = "approved" if args["p_action"] == "approve" else "rejected"
                post["approved_by"] = LINK["user_id"] if args["p_action"] == "approve" else None
                return SimpleNamespace(data="ok")
        return R()


PIC = {"id": "m0", "status": "done", "type": "image", "generated_media_url": "https://cdn.example/p1.jpg", "meta": {}}


def post(id_="p1", **kw):
    base = {"id": id_, "stream": "regulab", "status": "draft", "date": "2026-11-09", "slot": "08:00", "lang": "bm",
            "domain": "kosmetik", "hook": "Notifikasi bukan kelulusan", "text": GOOD, "citation": "NPRA Garis Panduan",
            "media_ids": ["m0"], "updated_at": "2026-11-07T10:00:00.123456+00:00", "created_at": "2026-11-07T09:00:00+00:00"}
    return {**base, **kw}


def store(**extra):
    base = {"semasa_telegram_link": [LINK], tb.INBOX: [], tb.SENT: [], db.POSTS: [], db.IDEAS: [], db.MEDIA: [PIC],
            db.SETTINGS: [], db.BILLING_DOCS: []}
    base.update(extra)
    return Store(**base)


def msg(id_, text, frm=WAN):
    return {"id": id_, "kind": "private", "status": "new", "from_id": frm, "chat_id": CHAT,
            "payload": {"update_id": id_, "message": {"message_id": 500 + id_, "chat": {"id": CHAT, "type": "private"},
                                                      "from": {"id": frm}, "text": text}}}


def tap(id_, data, frm=WAN, message_id=700):
    return {"id": id_, "kind": "callback", "status": "new", "from_id": frm, "chat_id": CHAT,
            "payload": {"update_id": id_, "callback_query": {"id": f"cq{id_}", "from": {"id": frm}, "data": data,
                                                             "message": {"message_id": message_id, "chat": {"id": CHAT}}}}}


def inbox(st):
    return {r["id"]: r for r in st.tables[tb.INBOX]}


def test_the_webhook_secret_is_the_one_functions_yml_computes_with_openssl():
    # printf %s "semasa-telegram-webhook" | openssl dgst -sha256 -hmac "123:ABC" -r
    assert tb.webhook_secret("123:ABC") == "02d79f9c1aadfd875893f77b0516ce432f90079137590c406a346f8e504ad4bf"


def test_the_webhook_is_pointed_at_semasa_once_and_the_commands_are_named(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    st, bot = store(), Bot()
    tb.run(st, bot=bot, now=NOW, push=False)
    sets = [p for m, p in bot.calls if m == "setWebhook"]
    assert sets == [{"url": "https://x.supabase.co/functions/v1/semasa-telegram", "secret_token": tb.webhook_secret("123:ABC"),
                     "allowed_updates": ["message", "callback_query"], "max_connections": 10}]
    assert any(m == "setMyCommands" for m, _ in bot.calls)
    state = next(r for r in st.tables[db.SETTINGS] if r["key"] == "telegram_bot")["value"]
    assert state["username"] == "semasa_bot" and state["webhook"].endswith("/semasa-telegram")
    tb.run(st, bot=bot, now=NOW, push=False)
    assert len([1 for m, _ in bot.calls if m == "setWebhook"]) == 1, "already pointed: not set again"


def test_only_the_linked_account_is_obeyed():
    st = store(**{tb.INBOX: [msg(1, "/status", frm=STRANGER)]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    assert bot.sent() == [] and inbox(st)[1]["status"] == "skipped"


def test_drafts_come_with_buttons_and_the_version_shown_is_kept():
    st = store(**{db.POSTS: [post("p1"), post("p2", text={"bm": {"facebook": "Dijamin lulus NPRA dalam 3 hari!"}})],
                  tb.INBOX: [msg(1, "/draf")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    m1, m2 = bot.sent()
    assert "Notifikasi kosmetik bukan kelulusan" in m1["text"] and "ws.regulab · 2026-11-09 08:00 · kosmetik" in m1["text"]
    assert [b["callback_data"] for b in m1["reply_markup"]["inline_keyboard"][0]] == ["ok:p1", "no:p1"]
    photo = {"chat_id": CHAT, "photo": "https://cdn.example/p1.jpg", "caption": "📝 ws.regulab · 2026-11-09 08:00 · kosmetik"}
    assert ("sendPhoto", photo) in bot.calls, "the picture first"
    assert "Belum boleh diluluskan" in m2["text"], "a post the publisher would block cannot be approved here either"
    assert [b["callback_data"] for b in m2["reply_markup"]["inline_keyboard"][0]] == ["no:p2"]
    sent = {r["post_id"]: r for r in st.tables[tb.SENT]}
    assert sent["p1"]["version"] == "2026-11-07T10:00:00.123456+00:00"


def test_approve_goes_through_the_gate_with_the_version_shown():
    st = store(**{db.POSTS: [post("p1")], tb.SENT: [{"post_id": "p1", "version": "2026-11-07T10:00:00.123456+00:00",
                                                     "chat_id": CHAT, "message_id": 700}],
                  tb.INBOX: [tap(1, "ok:p1")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    name, args = st.rpcs[0]
    assert name == "semasa_telegram_decide" and args["p_hard_flags"] == 0 and isinstance(args["p_flags"], list)
    assert {k: args[k] for k in ("p_post", "p_version", "p_action", "p_telegram_user_id")} == \
        {"p_post": "p1", "p_version": "2026-11-07T10:00:00.123456+00:00", "p_action": "approve", "p_telegram_user_id": WAN}
    assert st.tables[db.POSTS][0]["status"] == "approved"
    assert any(m == "editMessageReplyMarkup" for m, _ in bot.calls), "the buttons go once it is decided"
    assert "Diluluskan" in bot.sent()[-1]["text"] and inbox(st)[1]["note"] == "approved"


def test_a_draft_edited_since_it_was_shown_is_never_approved_blind():
    st = store(**{db.POSTS: [post("p1", updated_at="2026-11-07T11:30:00+00:00")],
                  tb.SENT: [{"post_id": "p1", "version": "2026-11-07T10:00:00.123456+00:00", "chat_id": CHAT}],
                  tb.INBOX: [tap(1, "ok:p1")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    assert st.tables[db.POSTS][0]["status"] == "draft"
    texts = [m["text"] for m in bot.sent()]
    assert any("telah berubah" in t for t in texts) and any(t.startswith("📝 Draf") for t in texts), "the new version is shown"
    assert st.tables[tb.SENT][0]["version"] == "2026-11-07T11:30:00+00:00"


def test_a_blocked_post_is_refused_before_the_gate_and_reject_needs_no_check():
    bad = post("p1", text={"bm": {"facebook": "Dijamin lulus NPRA dalam 3 hari!"}})
    st = store(**{db.POSTS: [bad], tb.SENT: [{"post_id": "p1", "version": bad["updated_at"], "chat_id": CHAT}],
                  tb.INBOX: [tap(1, "ok:p1"), tap(2, "no:p1")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    assert [a["p_action"] for _, a in st.rpcs] == ["reject"]
    assert st.tables[db.POSTS][0]["status"] == "rejected"


def test_a_link_becomes_an_idea_only_on_wans_tap(monkeypatch):
    monkeypatch.setattr(tb, "page_title", lambda url: "NPRA: Amaran label baharu")
    st = store(**{tb.INBOX: [msg(1, "https://www.npra.gov.my/notis/123 fokus pada amaran label")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    offer = bot.sent()[0]
    assert "NPRA: Amaran label baharu" in offer["text"] and st.tables[db.IDEAS] == []
    assert [b["callback_data"] for b in offer["reply_markup"]["inline_keyboard"][0]] == ["idea:r:1", "idea:l:1", "idea:x:1"]
    st.tables[tb.INBOX].append(tap(2, "idea:l:1"))
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    idea = st.tables[db.IDEAS][0]
    assert idea["source_url"] == "https://www.npra.gov.my/notis/123" and idea["stream"] == "linkedin"
    assert idea["note"] == "fokus pada amaran label" and idea["created_by"] == "u-wan" and idea["status"] == "new"
    assert idea["brief"] == {"via": "telegram"} and idea["source_title"] == "NPRA: Amaran label baharu"


def test_a_failed_idea_can_be_tried_again_from_ralat():
    ideas = [{"id": "i1", "source_title": "Recall krim", "status": "error", "error": "the writer did not answer", "attempts": 1,
              "updated_at": "2026-11-06T10:00:00+00:00"}]
    st = store(**{db.IDEAS: ideas, tb.INBOX: [msg(1, "/ralat")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    m = bot.sent()[0]
    assert "Recall krim" in m["text"] and m["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "retry:i1"
    st.tables[tb.INBOX].append(tap(2, "retry:i1"))
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    assert st.tables[db.IDEAS][0]["status"] == "new"


def test_a_question_is_answered_with_a_snapshot_and_the_earlier_turns():
    asked = []

    class LLM:
        def chat_text(self, system, user, max_tokens):
            asked.append((system, user))
            return "Ada 1 draf menunggu. Taip /draf."
    st = store(**{db.POSTS: [post("p1")], tb.INBOX: [msg(1, "Berapa draf yang tunggu saya?")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False, llm_factory=lambda s: LLM())
    assert bot.sent()[0]["text"] == "Ada 1 draf menunggu. Taip /draf."
    assert "Draf menunggu: 1" in asked[0][1] and "never Bahasa Indonesia" in asked[0][0]
    st.tables[tb.INBOX].append(msg(2, "Dan esok?"))
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False, llm_factory=lambda s: LLM())
    assert "Wan: Berapa draf yang tunggu saya?" in asked[1][1], "it remembers the conversation"


def test_new_drafts_are_pushed_once_and_a_draft_still_drawing_waits():
    st = store(**{db.POSTS: [post("p1"), post("p2", media_ids=["m1"]), post("old", created_at="2026-11-01T00:00:00+00:00")],
                  db.MEDIA: [PIC, {"id": "m1", "status": "working", "generated_media_url": None}]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False)
    assert [r["post_id"] for r in st.tables[tb.SENT]] == ["p1"], "p2 waits for its picture; a draft from before the link is not"
    tb.run(st, bot=bot, now=NOW, webhook=False)
    assert len(st.tables[tb.SENT]) == 1


def test_status_and_billing_read_without_error():
    docs = [{"kind": "invoice", "number": "INV-2026-020", "status": "sent", "total": 840, "currency": "MYR",
             "due_date": "2026-11-20", "client": {"name": "Marosia"}}]
    st = store(**{db.BILLING_DOCS: docs, tb.INBOX: [msg(1, "/status"), msg(2, "/bil"), msg(3, "/jadual"), msg(4, "/kesihatan")]})
    bot = Bot()
    tb.run(st, bot=bot, now=NOW, webhook=False, push=False)
    texts = [m["text"] for m in bot.sent()]
    assert texts[0].startswith("Semasa sekarang") and "INV-2026-020" in texts[1] and "MYR 840.00" in texts[1]
    assert "Tiada post" in texts[2] and "Semua berjalan baik" in texts[3]


def test_the_watchdog_reports_unanswered_messages_and_a_broken_webhook():
    st = store(**{db.SETTINGS: [{"key": "telegram_bot", "value": {"webhook": "", "username": "semasa_bot"}}],
                  tb.INBOX: [{"id": 1, "kind": "private", "status": "new", "created_at": "2026-11-07T10:00:00+00:00"}]})
    whats = [p["what"] for p in health.check_telegram(st, NOW)]
    assert "the bot is not connected to Semasa's webhook" in whats
    assert "1 message(s) from Wan not answered for 30 minutes" in whats
    assert health.check_telegram(store(), NOW) == [], "silent until the bot has been connected once"
