"""Every Motion storyboard is shown and approved before anything else is made (Wan, 7 Nov 2026: "make sure all storyboard
appear and approve before proceed for motion creation"). The worker stops at 'review' with the storyboard saved, draws and
renders nothing, and after the approval makes the film from exactly that storyboard, checked again."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from fakestore import FakeStore
from test_motion import GOOD, NOW, SCRIPT, FakeLLM, Store, _row, _runner, fake_speak
from test_motion_templates import STORY

from semasa import motion, motion_review, motion_templates
from semasa import telegram_bot as tb

pytestmark = pytest.mark.storyboard_gate
SETTINGS = {"prompt": "", "cli": "0.8.188"}


@pytest.fixture(autouse=True)
def _no_real_voice(monkeypatch):
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)


SQL = (Path(__file__).resolve().parents[2] / "supabase" / "071_motion_storyboard_review.sql").read_text()


def saved(store, row):
    return store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]


def approve(store, row, storyboard=None):
    got = saved(store, row)
    sb = storyboard if storyboard is not None else got["storyboard"]
    fields = {"status": "pending", "storyboard": sb, "storyboard_approved_at": "2026-10-23T06:30:00+00:00"}
    store.table(motion.TABLE).update(fields).eq("id", row["id"]).execute()
    return {**got, **fields, "status": "working", "attempts": 1}


# ---- the stop ----------------------------------------------------------------------------------------------------------------

def test_a_film_stops_at_its_storyboard_and_nothing_is_drawn_or_rendered(tmp_path):
    store, calls, drawn = Store(), [], []
    r = _row(store, ai_background=True)
    ok = motion.process(store, FakeLLM([SCRIPT]), {**r, "attempts": 1}, SETTINGS, runner=_runner(calls=calls), workdir=tmp_path,
                        now=NOW, picture_provider=lambda *a, **k: drawn.append(a) or (b"", ""))
    got = saved(store, r)
    assert ok and got["status"] == "review" and got["stage"] == "storyboard"
    assert got["storyboard"]["kind"] == "explainer" and len(got["storyboard"]["plan"]["scenes"]) >= 4
    assert got["storyboard_approved_at"] is None
    assert calls == [] and drawn == [], "no render, no check, no AI background before the approval"
    assert not got.get("video_url")


def test_after_the_approval_the_film_is_made_from_the_saved_storyboard_and_the_plan_is_not_asked_again(tmp_path):
    store = Store()
    r = _row(store)
    llm = FakeLLM([SCRIPT])
    motion.process(store, llm, {**r, "attempts": 1}, SETTINGS, runner=_runner(), workdir=tmp_path, now=NOW)
    asked_before = len(llm.asked)
    sb = saved(store, r)["storyboard"]
    sb["plan"]["scenes"][1]["heading"] = "PFAS ialah bahan kimia kekal"           # Wan's own edit in the page
    llm.answers = [{"title": "PFAS: tiga perkara", "html": GOOD}]
    assert motion.process(store, llm, approve(store, r, sb), SETTINGS, runner=_runner(), workdir=tmp_path, now=NOW)
    got = saved(store, r)
    assert got["status"] == "done", got.get("error")
    assert "SCENES, FIXED" in llm.asked[asked_before][1], "the first question after the approval is the film, not a new plan"
    assert any(sc.get("heading") == "PFAS ialah bahan kimia kekal" for sc in got["script"])


@pytest.mark.parametrize("change, why", [
    (lambda sc: sc[1].update(heading=""), "no heading"),
    (lambda sc: sc[2].update(lines=["Sila rujuk laman web NPRA untuk maklumat lanjut"]), "sends the viewer away"),
    (lambda sc: sc.pop(3), "needs 4"),
])
def test_an_edit_that_breaks_a_rule_goes_back_for_review_and_is_never_made(tmp_path, change, why):
    store, calls = Store(), []
    r = _row(store)
    motion.process(store, FakeLLM([SCRIPT]), {**r, "attempts": 1}, SETTINGS, runner=_runner(), workdir=tmp_path, now=NOW)
    sb = saved(store, r)["storyboard"]
    change(sb["plan"]["scenes"])
    motion.process(store, FakeLLM([]), approve(store, r, sb), SETTINGS, runner=_runner(calls=calls), workdir=tmp_path, now=NOW)
    got = saved(store, r)
    assert got["status"] == "review" and got["storyboard_approved_at"] is None and why in got["error"]
    assert calls == []


def test_without_071_the_film_goes_back_to_the_queue_never_made_without_an_approval(tmp_path):
    class Old(Store):
        def table(self, name):
            q = super().table(name)
            real = q.update

            def update(fields):
                if fields.get("status") == "review":
                    raise RuntimeError('new row violates check constraint "semasa_motions_status_check"')
                return real(fields)
            q.update = update
            return q
    store, calls = Old(), []
    r = _row(store)
    motion.process(store, FakeLLM([SCRIPT]), {**r, "attempts": 1}, SETTINGS, runner=_runner(calls=calls), workdir=tmp_path,
                   now=NOW)
    got = saved(store, r)
    assert got["status"] == "waiting" and "071" in got["error"] and calls == []


def test_an_automatic_retry_keeps_the_approved_storyboard():
    row = {"storyboard": {"kind": "explainer", "plan": {}}, "storyboard_approved_at": "2026-11-07T00:00:00Z"}
    assert motion_review.approved(row, "explainer") is row["storyboard"]
    assert motion_review.approved({**row, "storyboard_approved_at": None}, "explainer") is None
    assert motion_review.approved(row, "story") is None, "an approval belongs to the kind of film it was given for"


# ---- template films ------------------------------------------------------------------------------------------------------

def _story_row(store):
    return store.table(motion.TABLE).insert({"status": "working", "stream": "regulab", "language": "bm", "brief": "Malaysia",
                                             "options": {"template": "story"}, "attempts": 1}).execute().data[0]


def test_a_template_film_also_stops_at_its_storyboard(tmp_path, monkeypatch):
    store = FakeStore(semasa_motions=[])
    r = _story_row(store)
    good = motion_templates.validate_story(STORY, lang="bm", stream="regulab")
    monkeypatch.setattr(motion_templates, "write_storyboard", lambda *a, **k: (good, "Storyboard by Gemini"))
    monkeypatch.setattr(motion_templates, "draw", lambda *a, **k: pytest.fail("a picture was drawn before the approval"))
    assert motion.template_film(store, None, r, SETTINGS, tmp_path, gpt_login=object())
    got = saved(store, r)
    assert got["status"] == "review" and got["storyboard"]["kind"] == "story" and got["storyboard"]["sb"] == good


def test_an_approved_template_storyboard_is_checked_again_then_goes_on_to_the_pictures(tmp_path, monkeypatch):
    store = FakeStore(semasa_motions=[])
    r = _story_row(store)
    good = motion_templates.validate_story(STORY, lang="bm", stream="regulab")
    monkeypatch.setattr(motion_templates, "write_storyboard", lambda *a, **k: pytest.fail("asked for a new storyboard"))

    class Reached(Exception):
        pass

    def draw(store_, row_, kind, sb, *a, **k):
        raise Reached(sb["title"])
    monkeypatch.setattr(motion_templates, "draw", draw)
    row = {**r, "storyboard": {"kind": "story", "sb": {**good, "title": "Pulau"}, "note": "Storyboard by Gemini"},
           "storyboard_approved_at": "2026-11-07T00:00:00Z"}
    with pytest.raises(Reached, match="Pulau"):
        motion.template_film(store, None, row, SETTINGS, tmp_path, gpt_login=object())
    bad = {**row, "storyboard": {"kind": "story", "sb": {**good, "subtitle": "Lihat www.contoh.com sekarang"}}}
    assert motion.template_film(store, None, bad, SETTINGS, tmp_path, gpt_login=object())
    got = saved(store, r)
    assert got["status"] == "review" and "link" in got["error"] and got["storyboard_approved_at"] is None


# ---- Telegram ------------------------------------------------------------------------------------------------------------

class Bot:
    def __init__(self):
        self.calls, self.n = [], 100

    def call(self, method, **p):
        self.calls.append((method, p))
        self.n += 1
        return {"message_id": self.n}

    send, drop_buttons = tb.Bot.send, tb.Bot.drop_buttons


LINK = {"id": 1, "telegram_user_id": 111, "chat_id": 111, "user_id": "u-wan", "linked_at": "2026-11-07T00:00:00+00:00"}


def _review(store):
    sb = {"kind": "explainer", "written_at": "2026-11-07T01:00:00+00:00", "note": "Storyboard by Gemini",
          "plan": {"title": "PFAS", "scenes": [{"id": "s1", "kicker": "Hook", "heading": "Tiga perkara", "lines": ["satu"],
                                                "narration": "Hai.", "shot": "A lab bench"}]}}
    return store.table(motion.TABLE).insert({"status": "review", "brief": "PFAS", "storyboard": sb}).execute().data[0]


def test_the_storyboard_reaches_telegram_once_with_approve_and_rewrite_buttons():
    store = FakeStore(semasa_motions=[], semasa_settings=[], semasa_telegram_link=[LINK])
    r = _review(store)
    bot = Bot()
    assert tb.push_storyboards(store, bot, LINK) == 1
    assert tb.push_storyboards(store, bot, LINK) == 0, "sent once"
    p = [p for m, p in bot.calls if m == "sendMessage"][0]
    assert "Tiga perkara" in p["text"] and "A lab bench" in p["text"] and "selepas anda luluskan" in p["text"]
    data = [b.get("callback_data") for row in p["reply_markup"]["inline_keyboard"] for b in row]
    epoch = motion_review.written_epoch(r["storyboard"])
    assert epoch and f"sbok:{r['id']}:{epoch}" in data and f"sbre:{r['id']}:{epoch}" in data
    assert all(len(d.encode()) <= 64 for d in data if d), "Telegram's 64-byte callback limit"


def test_a_tap_on_approve_goes_through_the_database_decision_as_the_linked_account():
    class S(FakeStore):
        rpcs: list = []

        def rpc(self, name, args):
            self.rpcs.append((name, args))
            return SimpleNamespace(execute=lambda: SimpleNamespace(data="ok"))
    store = S(semasa_motions=[], semasa_settings=[], semasa_telegram_link=[LINK])
    bot = Bot()
    row = {"id": 1, "payload": {"callback_query": {"data": "sbok:m-1:1762477200", "message": {"message_id": 7,
                                                                                         "chat": {"id": 111}}}}}
    assert tb.handle_callback(store, bot, LINK, row) == "storyboard approve: ok"
    assert store.rpcs == [("semasa_telegram_motion_decide", {"p_motion": "m-1", "p_action": "approve",
                                                              "p_telegram_user_id": 111, "p_written": 1762477200})]
    assert any("Diluluskan" in p.get("text", "") for m, p in bot.calls if m == "sendMessage")


# ---- the database --------------------------------------------------------------------------------------------------------

def test_071_keeps_every_status_adds_review_and_guards_done():
    statuses = re.search(r"check \(status in \(([^)]*)\)\)", SQL).group(1)
    assert all(f"'{s}'" in statuses for s in ("waiting", "pending", "working", "review", "done", "error"))
    assert "new.status = 'done' and old.status is distinct from 'done' and new.storyboard_approved_at is null" in SQL
    assert ("revoke execute on function public.semasa_telegram_motion_decide(uuid, text, bigint, bigint) "
            "from public, anon, authenticated") in SQL
    assert "grant execute on function public.semasa_motion_storyboard_decide(uuid, text, jsonb, bigint) to authenticated" in SQL
    assert "return 'changed'" in SQL, "a decision on an older storyboard is refused, never applied to the newer one"
    assert "semasa_is_uploader()" in SQL and "if m.status <> 'review'" in SQL


# ---- found by the bug sweep (7 Nov 2026) ---------------------------------------------------------------------------------

def test_a_template_storyboard_that_passed_passes_again_after_the_approval_even_when_speak_adds_a_word():
    def adds(t):
        return t.replace("faktanya", "fakta sebenar")                          # what malaysian() does to one word
    hook = "Takde sapa cakap pasal kabus pagi tapi faktanya ni sebab aku balik"  # 12 words before, 13 after
    first = {**STORY, "hook": hook}
    with pytest.raises(motion_templates.StoryboardError, match="1 to 12 words, not 13"):
        motion_templates.validate_story(first, lang="bm", stream="regulab", speak=adds)
    short = {**STORY, "hook": "Takde sapa cakap pasal kabus tapi faktanya ni sebab aku balik"}
    sb = motion_templates.validate_story(short, lang="bm", stream="regulab", speak=adds)
    assert motion_templates.validate_story(sb, lang="bm", stream="regulab", speak=adds) == sb, "stable on the re-check"


def test_an_approved_showcase_keeps_wans_own_product_words():
    from test_motion_templates import PRODUCTS, SHOW
    mine = [{**PRODUCTS[0], "name": "Serum Cahaya", "benefits": "lembap, cerah"}, PRODUCTS[1]]
    sb = motion_templates.validate_showcase(SHOW, mine, lang="bm", stream="regulab")
    assert sb["products"][0]["name"] == "Serum Cahaya"
    edited = {**sb, "products": [{**sb["products"][0], "name": "Serum Cahaya Plus", "benefits": ["Untuk kulit kusam"]},
                                 sb["products"][1]]}
    again = motion_templates.validate_showcase(edited, mine, lang="bm", stream="regulab", approved=True)
    assert again["products"][0]["name"] == "Serum Cahaya Plus" and again["products"][0]["benefits"] == ["Untuk kulit kusam"]


def test_a_passing_database_fault_is_retried_never_parked_as_071_missing(tmp_path):
    class Flaky(Store):
        def table(self, name):
            q = super().table(name)
            real = q.update

            def update(fields):
                if fields.get("status") == "review":
                    raise RuntimeError("502 Bad Gateway")
                return real(fields)
            q.update = update
            return q
    store = Flaky()
    r = _row(store)
    assert not motion.process(store, FakeLLM([SCRIPT]), {**r, "attempts": 1}, SETTINGS, runner=_runner(), workdir=tmp_path,
                              now=NOW)
    got = saved(store, r)
    assert got["status"] == "pending" and "071" not in got["error"] and "502" in got["error"]


def test_a_bounced_storyboard_is_stamped_anew_and_telegram_is_told_why(tmp_path):
    store, told = Store(), []
    r = _row(store)
    motion.process(store, FakeLLM([SCRIPT]), {**r, "attempts": 1}, SETTINGS, runner=_runner(), workdir=tmp_path, now=NOW)
    before = saved(store, r)["storyboard"]["written_at"]
    row = {**saved(store, r), "storyboard": {**saved(store, r)["storyboard"], "written_at": "2026-01-01T00:00:00+00:00"}}
    motion_review.send_back(store, row, "scene 2 has no heading", notify=lambda s, x: told.append(x))
    got = saved(store, r)
    assert got["storyboard"]["written_at"] not in ("2026-01-01T00:00:00+00:00",) and before
    assert told and "scene 2 has no heading" in told[0]["error"]
    assert "scene 2 has no heading" in motion_review.telegram_text(told[0], told[0]["storyboard"])


def test_a_teasers_call_to_action_cannot_be_edited_away():
    row = {"seconds": 10, "voice": "off", "stream": "regulab", "language": "bm", "options": {"mode": "teaser"}}
    if motion.motion_styles.duration(row) != 10:
        pytest.skip("this row shape is not a teaser here")
    cta = motion.motion_styles.cta(row)
    sb = {"kind": "explainer", "plan": {"scenes": [{"id": "s1", "heading": "Hook baharu", "lines": [], "narration": ""}]}}
    out = motion.approved_plan(row, sb)
    assert out["scenes"][0]["heading"] == f"Hook baharu · {cta}" and out["hook"] == "Hook baharu"


def test_the_storyboards_sent_list_has_its_own_settings_row_and_the_old_one_is_read_once():
    from semasa import telegram_tools as tt
    store = FakeStore(semasa_motions=[], semasa_telegram_link=[LINK],
                      semasa_settings=[{"key": "telegram_chat", "value": {"thread_id": "t-1", "storyboards_sent": ["old@x"]}}])
    r = _review(store)
    assert motion_review.sent_keys(store) == ["old@x"], "before the new row exists, the old list counts"
    assert tb.push_storyboards(store, Bot(), LINK) == 1
    row = next(x for x in store.tables["semasa_settings"] if x["key"] == motion_review.SENT_KEY)["value"]
    assert row["sent"] == ["old@x", motion_review.sent_key(r["id"], r["storyboard"])]
    assert tt.chat_state(store) == {"thread_id": "t-1", "storyboards_sent": ["old@x"]}, "telegram_chat is not rewritten"
    tt.save_chat_state(store, {"pending": "poster"})   # the Telegram worker's own write cannot lose the list any more
    assert motion_review.due(store) == []
