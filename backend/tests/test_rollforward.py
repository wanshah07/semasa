"""Wan, 22 Nov 2026: "make sure hantar ke telegram setiap kali siap post draft untuk both ws dan linkedin untuk dapatkan
approval, kalau terlepas tarikh dan masa, auto cari next slot".

A missed slot moves to the next free slot of the stream (rollforward.py: the publisher, Telegram's Approve), and every new
draft is announced on Telegram once (telegram_bot.push_new_drafts, draft_announce.py)."""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fakestore import FakeStore, Query  # noqa: E402
from test_publisher import CAP, NOW, FakeBuffer, _live, _post  # noqa: E402
from test_telegram_bot import CHAT, LINK, Bot, post, store, tap  # noqa: E402
from test_telegram_bot import NOW as TG_NOW  # noqa: E402

from semasa import db, publisher, rollforward  # noqa: E402
from semasa import telegram_bot as tb  # noqa: E402

TOLD: list[str] = []


def told(_store, text):
    TOLD.append(text)
    return True


def _run(st, now=NOW, clients=None, monkeypatch=None):
    TOLD.clear()
    if monkeypatch is not None:
        monkeypatch.setattr(rollforward, "tell", lambda s, text, notify=None: told(s, text))
    return publisher.run(st, now, clients=clients if clients is not None else {"buffer": FakeBuffer()})


# ---- the publisher -------------------------------------------------------------------------------------------------------

def test_an_approved_post_that_missed_its_slot_moves_to_the_next_free_slot_and_is_scheduled_there(monkeypatch):
    st = _live(_post(date="2026-09-23", slot="08:00"))           # yesterday; NOW is 24 Sep 10:00 MYT
    buf = FakeBuffer()
    c = _run(st, clients={"buffer": buf}, monkeypatch=monkeypatch)
    p = st.tables["semasa_posts"][0]
    assert c["moved"] == 1 and c["overdue"] == 0
    assert (p["date"], p["slot"]) == ("2026-09-24", "13:00"), "today's next slot, not tomorrow's"
    assert {x["due_at"] for x in buf.created} == {"2026-09-24T05:00:00+00:00"}, "handed over for the NEW slot, never late"
    assert p["status"] == "scheduled"
    assert any(r["event"] == "publish.moved" for r in st.tables.get(db.LOG, []))
    assert len(TOLD) == 1 and "2026-09-23 08:00 → 2026-09-24 13:00" in TOLD[0]


def test_a_held_slot_is_never_double_booked(monkeypatch):
    other = _post(id="p2", status="draft", date="2026-09-24", slot="13:00",
                  text={"bm": {"instagram": "Perkataan lain sama sekali untuk post kedua ini, tiada kaitan."}})
    film = {"id": "f1", "stream": "regulab", "status": "pending", "queued_post_id": None,
            "options": {"position": {"date": "2026-09-24", "slot": "21:00"}}}
    st = _live(_post(date="2026-09-23", slot="08:00"), extra_posts=[other])
    st.tables["semasa_motions"] = [film]
    _run(st, monkeypatch=monkeypatch)
    p = st.tables["semasa_posts"][0]
    assert (p["date"], p["slot"]) == ("2026-09-25", "08:00"), "13:00 holds a draft, 21:00 a booked film"


def test_two_late_posts_take_two_slots_oldest_first(monkeypatch):
    b = _post(id="p2", date="2026-09-23", slot="13:00",
              text={"bm": {"instagram": "Satu lagi post yang terlepas, dengan perkataan lain sepenuhnya.",
                           "facebook": "Satu lagi post.", "threads": "Satu lagi."}})
    st = _live(_post(date="2026-09-23", slot="08:00"), extra_posts=[b])
    c = _run(st, monkeypatch=monkeypatch)
    got = {p["id"]: (p["date"], p["slot"]) for p in st.tables["semasa_posts"]}
    assert c["moved"] == 2 and got == {"p1": ("2026-09-24", "13:00"), "p2": ("2026-09-24", "21:00")}
    assert len(TOLD) == 1, "one message for the run"


def test_a_post_already_handed_over_is_never_moved(monkeypatch):
    rec = {"instagram": {"id": "b1", "status": "sent", "route": "buffer", "dueAt": "2026-09-23T00:00:00+00:00"}}
    st = _live(_post(date="2026-09-23", slot="08:00", published=rec))
    c = _run(st, monkeypatch=monkeypatch)
    p = st.tables["semasa_posts"][0]
    assert c["moved"] == 0 and (p["date"], p["slot"]) == ("2026-09-23", "08:00") and TOLD == []


def test_nothing_moves_while_publishing_is_off(monkeypatch):
    st = _live(_post(date="2026-09-23", slot="08:00"), enabled=False)
    c = _run(st, clients={}, monkeypatch=monkeypatch)
    assert c["overdue"] == 3 and c["moved"] == 0 and st.tables["semasa_posts"][0]["date"] == "2026-09-23"


def test_within_the_grace_the_post_keeps_its_slot(monkeypatch):
    st = _live(_post(date="2026-09-24", slot="09:30"))           # 30 minutes ago
    buf = FakeBuffer()
    c = _run(st, clients={"buffer": buf}, monkeypatch=monkeypatch)
    assert c["moved"] == 0 and st.tables["semasa_posts"][0]["slot"] == "09:30"


def test_the_rota_is_kept_when_a_post_moves(monkeypatch):
    st = _live(_post(date="2026-09-23", slot="08:00", domain="halal_my"))
    # Thursday 24 Sep is pharma and food, Friday 25 cosmetics, Saturday 26 halal
    st.tables["semasa_settings"][1]["value"] = {"regulab": {"schedule": {"4": ["farmaseutikal", "makanan"],
                                                                         "5": ["kosmetik"], "6": ["halal_my", "fatwa"]}},
                                                "linkedin": {"slots": ["06:00"]}}
    _run(st, monkeypatch=monkeypatch)
    p = st.tables["semasa_posts"][0]
    assert (p["date"], p["slot"]) == ("2026-09-26", "08:00")


def test_a_linkedin_post_moves_to_its_own_streams_slots(monkeypatch):
    li = _post(id="L1", stream="linkedin", lang="en", date="2026-09-22", slot="06:00", text={"en": {"linkedin": CAP}})
    st = _live(li)
    c = _run(st, clients={"linkedin": object()}, monkeypatch=monkeypatch)
    p = st.tables["semasa_posts"][0]
    assert c["moved"] == 1 and (p["date"], p["slot"]) == ("2026-09-24", "19:00")


def test_the_move_is_pinned_to_the_version_read():
    st = FakeStore(semasa_posts=[{"id": "p1", "status": "approved", "date": "2026-09-23", "slot": "08:00",
                                  "updated_at": "2026-09-23T10:00:00+00:00"}])
    stale = {"id": "p1", "status": "approved", "date": "2026-09-23", "slot": "08:00", "updated_at": "2026-09-22T10:00:00+00:00"}
    assert rollforward.move(st, stale, "2026-09-24", "13:00", "past", "publisher", NOW, "approved") is None
    assert st.tables["semasa_posts"][0]["date"] == "2026-09-23"
    fresh = dict(st.tables["semasa_posts"][0], decisions=[])
    got = rollforward.move(st, fresh, "2026-09-24", "13:00", "past", "publisher", NOW, "approved")
    assert got["slot"] == "13:00" and got["decisions"][-1]["action"] == "moved"
    assert "from 2026-09-23 08:00 to 2026-09-24 13:00" in got["decisions"][-1]["note"]


def test_next_position_skips_a_slot_due_within_the_lead():
    at = datetime(2026, 9, 24, 4, 40, tzinfo=UTC)                 # 12:40 MYT: 13:00 is twenty minutes away
    assert rollforward.next_position({"stream": "regulab"}, {}, set(), at) == ("2026-09-24", "21:00")
    assert rollforward.next_position({"stream": "regulab"}, {"regulab": {"schedule": {str(d): [] for d in range(7)}}},
                                     set(), at) is None, "no posting day at all: no slot"


# ---- Telegram's Approve --------------------------------------------------------------------------------------------------

class BumpStore:
    """The telegram test store, with the database's updated_at trigger: every write to a post moves its stamp."""

    @staticmethod
    def make(**tables):
        st = store(**tables)
        real = Query.execute

        def execute(q):
            if q.table == db.POSTS and q.op == "update":
                q.payload = {**q.payload, "updated_at": "2026-11-07T12:00:01.500000+00:00"}
            return real(q)
        st.table = lambda name: type("Q", (Query,), {"execute": execute})(st, name)
        return st


def test_telegram_approve_of_a_draft_on_a_held_slot_moves_it_and_approves_the_moved_version():
    mine = post("p1")
    other = post("p2", status="approved", text={"bm": {"facebook": "Perkataan lain sepenuhnya untuk post kedua di slot ini."}})
    st = BumpStore.make(**{db.POSTS: [mine, other], tb.SENT: [{"post_id": "p1", "version": mine["updated_at"],
                                                              "chat_id": CHAT, "message_id": 700}],
                           tb.INBOX: [tap(1, "ok:p1")]})
    bot = Bot()
    tb.run(st, bot=bot, now=TG_NOW, webhook=False, push=False)
    p = next(x for x in st.tables[db.POSTS] if x["id"] == "p1")
    assert (p["date"], p["slot"]) == ("2026-11-07", "21:00")
    assert st.rpcs[0][1]["p_version"] == "2026-11-07T12:00:01.500000+00:00", "the gate approves the version just moved"
    assert p["status"] == "approved" and "Dipindah dari 2026-11-09 08:00" in bot.sent()[-1]["text"]


def test_telegram_approve_with_no_free_slot_is_refused_and_nothing_moves():
    late = post("p1", date="2026-11-01", slot="08:00")
    closed = {"regulab": {"schedule": {str(d): [] for d in range(7)}}}
    st = store(**{db.POSTS: [late], db.SETTINGS: [{"key": "brand", "value": closed}],
                  tb.SENT: [{"post_id": "p1", "version": late["updated_at"], "chat_id": CHAT, "message_id": 700}],
                  tb.INBOX: [tap(1, "ok:p1")]})
    bot = Bot()
    tb.run(st, bot=bot, now=TG_NOW, webhook=False, push=False)
    assert st.rpcs == [] and st.tables[db.POSTS][0]["date"] == "2026-11-01"
    assert "tiada slot kosong" in bot.sent()[-1]["text"]


def test_a_blocked_draft_is_not_moved_before_it_is_refused():
    bad = post("p1", date="2026-11-01", slot="08:00", text={"bm": {"facebook": "Dijamin lulus NPRA dalam 3 hari!"}})
    st = store(**{db.POSTS: [bad], tb.SENT: [{"post_id": "p1", "version": bad["updated_at"], "chat_id": CHAT, "message_id": 700}],
                  tb.INBOX: [tap(1, "ok:p1")]})
    tb.run(st, bot=Bot(), now=TG_NOW, webhook=False, push=False)
    assert st.rpcs == [] and st.tables[db.POSTS][0]["date"] == "2026-11-01"


# ---- every new draft is announced, once --------------------------------------------------------------------------------

def test_both_streams_are_announced_once_with_a_heading_and_a_past_slot_draft_too():
    li = post("L1", stream="linkedin", lang="en", domain=None, angle="A", media_ids=[], text={"en": {"linkedin": CAP}},
              created_at="2026-11-07T11:00:00+00:00")
    late = post("p9", date="2026-11-06", slot="08:00")
    st = store(**{db.POSTS: [post("p1"), li, late]})
    bot = Bot()
    assert tb.push_new_drafts(st, bot, LINK, TG_NOW) == 3
    texts = [m["text"] for m in bot.sent()]
    assert sum("🆕 Draf ws.regulab baharu siap" in t for t in texts) == 2
    assert sum("🆕 Draf LinkedIn baharu siap" in t for t in texts) == 1
    assert any("2026-11-06 08:00" in t and "Lulus akan memindahkannya" in t for t in texts)
    assert all(r["message_id"] for r in st.tables[tb.SENT]), "each claim carries the message its buttons are on"
    assert tb.push_new_drafts(st, bot, LINK, TG_NOW) == 0 and len(bot.sent()) == 3, "never twice"
    assert sum(r["event"] == "post.announced" for r in st.tables.get(db.LOG, [])) == 3


def test_a_draft_whose_slides_are_still_queued_waits_then_goes_with_a_note():
    young = post("p1", media_ids=[], created_at="2026-11-07T11:50:00+00:00")
    st = store(**{db.POSTS: [young], db.MEDIA: [{"id": "j1", "post_id": "p1", "status": "pending", "mode": "slides"}]})
    bot = Bot()
    assert tb.push_new_drafts(st, bot, LINK, TG_NOW) == 0, "the slides are drawn first"
    st.tables[db.MEDIA][0]["status"] = "done"
    assert tb.push_new_drafts(st, bot, LINK, TG_NOW) == 1
    old = post("p2", media_ids=["m1"], created_at="2026-11-07T08:00:00+00:00")
    st = store(**{db.POSTS: [old], db.MEDIA: [{"id": "m1", "status": "processing", "generated_media_url": None}]})
    bot = Bot()
    assert tb.push_new_drafts(st, bot, LINK, TG_NOW) == 1, "four hours drawing: announced anyway"
    assert "gambar masih dijana" in bot.sent()[-1]["text"]


def test_an_unsplash_search_waiting_for_a_pick_does_not_hold_the_announcement():
    p = post("p1", media_ids=[], created_at="2026-11-07T11:50:00+00:00")
    st = store(**{db.POSTS: [p], db.MEDIA: [{"id": "u1", "post_id": "p1", "status": "pending", "provider": "unsplash"}]})
    assert tb.push_new_drafts(st, Bot(), LINK, TG_NOW) == 1


def test_a_failed_send_gives_the_claim_back_and_a_claim_another_run_holds_is_respected():
    class Down(Bot):
        def call(self, method, **p):
            if method == "sendMessage":
                raise tb.TelegramError("sendMessage: Bad Gateway")
            return super().call(method, **p)
    st = store(**{db.POSTS: [post("p1")]})
    assert tb.push_new_drafts(st, Down(), LINK, TG_NOW) == 0
    assert st.tables[tb.SENT] == [], "given back: the next run tries again"
    st.tables[tb.SENT].append({"post_id": "p1", "version": "x", "chat_id": CHAT, "message_id": None,
                               "sent_at": (TG_NOW - timedelta(minutes=1)).isoformat()})
    assert tb.push_new_drafts(st, Bot(), LINK, TG_NOW) == 0, "another run is sending it right now"
    st.tables[tb.SENT][0]["sent_at"] = (TG_NOW - timedelta(minutes=30)).isoformat()
    assert tb.push_new_drafts(st, Bot(), LINK, TG_NOW) == 1, "a claim a crashed run left is taken again"
    assert len(st.tables[tb.SENT]) == 1 and st.tables[tb.SENT][0]["message_id"]


def test_old_drafts_are_not_flooded_and_the_switch_turns_it_off():
    st = store(**{db.POSTS: [post("p1", created_at="2026-11-03T09:00:00+00:00")]})
    assert tb.push_new_drafts(st, Bot(), LINK, TG_NOW) == 0, "older than three days: not announced now"
    st = store(**{db.POSTS: [post("p1")], db.SETTINGS: [{"key": "telegram_chat", "value": {"draft_alerts": False}}]})
    assert tb.push_new_drafts(st, Bot(), LINK, TG_NOW) == 0


def test_announce_is_quiet_without_a_token_or_a_link(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert tb.announce(store(**{db.POSTS: [post("p1")]}))["pushed"] == 0
    st = store(**{db.POSTS: [post("p1")], "semasa_telegram_link": []})
    assert tb.announce(st, bot=Bot(), now=TG_NOW)["pushed"] == 0
    st = store(**{db.POSTS: [post("p1")]})
    assert tb.announce(st, bot=Bot(), now=TG_NOW)["pushed"] == 1
