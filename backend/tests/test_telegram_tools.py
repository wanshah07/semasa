"""Semasa on Telegram, round two (Wan, 7 Nov 2026): /robot shows and pins the writer, every answer names the robot that wrote it,
standing notes and 👎 corrections make it improve, and /poster /karusel /motion /laporan make things."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_telegram_bot import CHAT, LINK, NOW, Bot, msg, store, tap  # noqa: E402

from semasa import db  # noqa: E402
from semasa import llm as llm_mod
from semasa import telegram_bot as tb
from semasa import telegram_tools as tt

STATUS = [
    {"slug": "rootsys", "name": "rootsys", "model": "glm-5.3", "chat_ok": True, "chat_ms": 1831, "role": "primary", "error": ""},
    {"slug": "mireld", "name": "Mireld", "model": "kimi-k3", "chat_ok": True, "chat_ms": 17940, "role": "primary", "error": ""},
    {"slug": "gemini", "name": "Gemini", "model": "gemini-3.6-flash", "chat_ok": False, "chat_ms": None, "role": "primary",
     "error": "Read timed out"},
    {"slug": "chatgpt", "name": "ChatGPT", "model": "gpt-5.5", "chat_ok": True, "chat_ms": 2100, "role": "primary", "error": ""},
]
STATE = {"key": "ai_team_state", "value": {"reader": {"chosen": {"slug": "rootsys", "name": "Wanshah 1", "model": "glm-5.3"}}}}
TEAM = {"key": "ai_team", "value": {"pins": {"reader": None, "image_gen": {"gateway": "kiosapi", "model": "gpt-image-2"}}}}


def team_store(**extra):
    return store(**{db.API_STATUS: STATUS, db.SETTINGS: [STATE, TEAM], tt.MEMORY: [], tt.THREADS: [], tt.MESSAGES: [],
                    tt.MOTIONS: [], **extra})


def run(st, bot, llm=None):
    return tb.run(st, bot=bot, now=NOW, webhook=False, push=False, llm_factory=(lambda s: llm) if llm else None)


def test_robot_shows_who_writes_and_pins_a_healthy_robot_but_never_one_that_is_down():
    st, bot = team_store(**{tb.INBOX: [msg(1, "/robot")]}), Bot()
    run(st, bot)
    m = bot.sent()[0]
    assert "Sedang menulis: Wanshah 1 · glm-5.3" in m["text"] and "Pilihan anda: Auto" in m["text"]
    assert "🔴 W4 Wanshah 4 · gemini-3.6-flash" in m["text"] and "Read timed out" in m["text"]
    datas = [b["callback_data"] for row in m["reply_markup"]["inline_keyboard"] for b in row]
    assert datas == ["pin:auto", "pin:rootsys", "pin:mireld"], "a robot that is down, or ChatGPT (Motion only), is not a pin"
    st.tables[tb.INBOX].append(tap(2, "pin:mireld"))
    run(st, bot)
    pins = next(r for r in st.tables[db.SETTINGS] if r["key"] == "ai_team")["value"]["pins"]
    assert pins["reader"] == {"gateway": "mireld", "model": "kimi-k3"}
    assert pins["image_gen"]["gateway"] == "kiosapi", "other pins kept"
    assert tt.set_pin(st, "gemini").startswith("Wanshah 4 tidak menjawab")
    st.tables[tb.INBOX].append(tap(3, "pin:auto"))
    run(st, bot)
    assert next(r for r in st.tables[db.SETTINGS] if r["key"] == "ai_team")["value"]["pins"]["reader"] is None


class LLM:
    """Answers like llm.LLM does: the usage record names the gateway that answered."""

    def __init__(self, text="Jawapan.", base="https://rootsys.cloud/v1", model="glm-5.3"):
        self.text, self.base, self.model, self.asked = text, base, model, []

    def chat_text(self, system, user, max_tokens):
        self.asked.append((system, user))
        llm_mod._record_usage({"base": self.base, "model": self.model})
        return self.text


def test_an_answer_names_the_robot_that_wrote_it_and_the_model_is_told_who_it_is():
    st, bot, llm = team_store(**{tb.INBOX: [msg(1, "hang guna model apa sekarang")]}), Bot(), LLM("Saya Wanshah 1, glm-5.3.")
    run(st, bot, llm)
    m = bot.sent()[0]
    assert m["text"].endswith("— Wanshah 1 · glm-5.3"), "read off the call itself"
    assert "running the model glm-5.3" in llm.asked[0][0]
    assert [b["callback_data"] for b in m["reply_markup"]["inline_keyboard"][0]] == ["fb:up:1", "fb:down:1"]
    msgs = st.tables[tt.MESSAGES]
    assert [x["role"] for x in msgs] == ["user", "assistant"] and st.tables[tt.THREADS][0]["title"] == "Telegram", \
        "kept in the AI chat page's Telegram thread"


def test_a_thumbs_down_turns_the_next_message_into_a_standing_note_that_every_answer_reads():
    st, bot, llm = team_store(**{tb.INBOX: [msg(1, "terangkan notifikasi"), tap(2, "fb:down:1")]}), Bot(), LLM()
    run(st, bot, llm)
    assert "Apa patut saya ubah" in bot.sent()[-1]["text"]
    st.tables[tb.INBOX].append(msg(3, "jawab lebih ringkas dan beri rujukan NPRA"))
    run(st, bot, llm)
    assert st.tables[tt.MEMORY][0]["note"] == "Pembetulan Wan: jawab lebih ringkas dan beri rujukan NPRA"
    assert st.tables[tt.MEMORY][0]["user_id"] == LINK["user_id"] and st.tables[tt.MEMORY][0]["source"] == "chat"
    st.tables[tb.INBOX] += [msg(4, "/ingat caption ws.regulab maksimum 120 patah perkataan"), msg(5, "apa khabar")]
    run(st, bot, llm)
    assert "- caption ws.regulab maksimum 120 patah perkataan" in llm.asked[-1][1]
    assert "- Pembetulan Wan: jawab lebih ringkas" in llm.asked[-1][1]
    assert "Wan: terangkan notifikasi" in llm.asked[-1][1], "the earlier turns come from the shared thread"
    for i, r in enumerate(st.tables[tt.MEMORY]):   # the database stamps created_at on insert; the fake does not
        r.setdefault("created_at", f"2026-11-07T10:00:0{i}+00:00")
    st.tables[tb.INBOX].append(msg(6, "/memori"))
    run(st, bot)
    m = bot.sent()[-1]
    assert "1. Pembetulan Wan" in m["text"] and m["reply_markup"]["inline_keyboard"][0][0]["callback_data"].startswith("forget:")
    note_id = st.tables[tt.MEMORY][0]["id"]
    st.tables[tb.INBOX].append(tap(7, f"forget:{note_id}"))
    run(st, bot)
    assert len(st.tables[tt.MEMORY]) == 1


def test_poster_and_carousel_write_ideas_and_motion_queues_a_film_that_starts_on_a_tap():
    st, bot = team_store(**{tb.INBOX: [msg(1, "/poster amaran label krim pemutih"), msg(2, "/karusel 5 mitos sunscreen"),
                                       msg(3, "/motion 3 perkara sebelum notifikasi https://www.npra.gov.my/x")]}), Bot()
    run(st, bot)
    poster, carousel = st.tables[db.IDEAS]
    assert poster["brief"] == {"via": "telegram", "format": "poster"} and not poster["make_slides"]
    assert carousel["make_slides"] and "format" not in carousel["brief"] and carousel["created_by"] == LINK["user_id"]
    film = st.tables[tt.MOTIONS][0]
    assert film["status"] == "waiting" and film["source_url"] == "https://www.npra.gov.my/x"
    assert film["options"]["via"] == "telegram"
    buttons = bot.sent()[-1]["reply_markup"]["inline_keyboard"]
    assert buttons[0][0]["callback_data"] == f"mgo:{film['id']}" and buttons[1][0]["url"].endswith("/#video")
    st.tables[tb.INBOX].append(tap(4, f"mgo:{film['id']}"))
    run(st, bot)
    assert st.tables[tt.MOTIONS][0]["status"] == "pending"
    assert "sudah bermula" in tt.start_motion(st, film["id"]), "a second tap does nothing"


def test_a_finished_telegram_film_is_sent_back_once():
    films = [{"id": "f1", "status": "done", "video_url": "https://cdn/f1.mp4", "title": "Notifikasi",
              "options": {"via": "telegram"}, "updated_at": "2026-11-07T11:00:00+00:00"},
             {"id": "f2", "status": "done", "video_url": "https://cdn/f2.mp4", "title": "Page film", "options": {},
              "updated_at": "2026-11-07T11:00:00+00:00"}]
    st, bot = team_store(**{tt.MOTIONS: films}), Bot()
    tb.push_videos(st, bot, LINK, NOW)
    tb.push_videos(st, bot, LINK, NOW)
    videos = [p for m, p in bot.calls if m == "sendVideo"]
    assert [v["video"] for v in videos] == ["https://cdn/f1.mp4"] and videos[0]["chat_id"] == CHAT


def test_a_report_is_written_and_sent_as_a_file():
    st, llm = team_store(**{tb.INBOX: [msg(1, "/laporan prestasi minggu ini")]}), LLM("# Laporan\n\nRingkasan...")

    class FileBot(Bot):
        def __init__(self):
            super().__init__()
            self.files = []

        def document(self, chat, name, data, caption=""):
            self.files.append((name, data))
    bot = FileBot()
    run(st, bot, llm)
    assert bot.sent()[0]["text"].startswith("# Laporan") and bot.sent()[0]["text"].endswith("— Wanshah 1 · glm-5.3")
    name, data = bot.files[0]
    assert name == "semasa-prestasi-minggu-ini-20261107.md" and data.startswith(b"# Laporan")
    assert "Malaysian Bahasa Malaysia (never Bahasa Indonesia)" in llm.asked[0][0]


def test_the_command_menu_follows_the_code(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    st, bot = team_store(), Bot(webhook="https://x.supabase.co/functions/v1/semasa-telegram")
    tb.ensure_webhook(st, bot, NOW)
    cmds = [p for m, p in bot.calls if m == "setMyCommands"]
    assert len(cmds) == 1 and [c["command"] for c in cmds[0]["commands"]][:3] == ["robot", "draf", "poster"]
    tb.ensure_webhook(st, bot, NOW)
    assert len([1 for m, _ in bot.calls if m == "setMyCommands"]) == 1, "unchanged: not sent again"


def test_start_shows_the_english_catalogue_and_idea_intake_queues_a_real_idea():
    st, bot = team_store(**{tb.INBOX: [msg(1, "/start")]}), Bot()
    run(st, bot)
    m = bot.sent()[0]
    datas = [b.get("callback_data") for row in m["reply_markup"]["inline_keyboard"] for b in row]
    assert datas == ["c:model", "c:repo", "c:idea", "c:style", "c:post"]
    st.tables[tb.INBOX].append(tap(2, "c:idea"))
    run(st, bot)
    assert "Send a link" in bot.sent()[-1]["text"]
    st.tables[tb.INBOX].append(msg(3, "https://example.com/recall focus on the hook"))
    run(st, bot)
    idea = st.tables[db.IDEAS][0]
    assert (idea["status"] == "new" and idea["brief"]["hook_required"]
            and idea["brief"]["requirements"]["source"])


def test_a_menu_button_that_needs_no_words_runs_at_once():
    st, bot = team_store(**{tb.INBOX: [tap(1, "menu:status")]}), Bot()
    run(st, bot)
    assert bot.sent()[0]["text"].startswith("Semasa sekarang")


def test_the_newest_forty_notes_are_read_oldest_first():
    rows = [{"id": f"n{i}", "user_id": "u-wan", "note": f"nota {i}", "source": "user",
             "created_at": f"2026-11-{1 + i // 24:02d}T{i % 24:02d}:00:00+00:00"} for i in range(45)]
    st = team_store(**{tt.MEMORY: rows})
    got = [r["note"] for r in tt.notes(st, "u-wan")]
    assert len(got) == tt.NOTES_MAX == 40
    assert got[0] == "nota 5" and got[-1] == "nota 44", "the five oldest drop out, never the newest"


def test_a_chat_state_write_keeps_keys_another_writer_set_meanwhile():
    st = team_store()
    tt.save_chat_state(st, {"thread_id": "t-1", "pending": "poster"})
    stale = tt.chat_state(st)                      # read by one writer...
    tt.save_chat_state(st, {"videos_sent": ["v1"]})  # ...while another writes its own key
    assert stale.get("videos_sent") is None
    tt.take_pending(st, "kulit sensitif")          # the first writer clears only what it owns
    st_now = tt.chat_state(st)
    assert st_now == {"thread_id": "t-1", "pending": None, "videos_sent": ["v1"]}
