"""Health report (Wan, 7 Nov 2026): fix what is safe, report the rest, e-mail Wan when something is new and once a day."""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fakestore import FakeStore  # noqa: E402

from semasa import db, health  # noqa: E402

NOW = datetime(2026, 11, 7, 9, 30, tzinfo=UTC)          # 17:30 MYT: not the morning run
MORNING = datetime(2026, 11, 8, 1, 0, tzinfo=UTC)        # 09:00 MYT
THUMB = ("Buffer refused: Invalid post: Video thumbnailUrl is not supported: social networks do not accept custom video "
         "thumbnail images")


class Sender:
    def __init__(self, fail_account=False, fail_send=False):
        self.sent, self.fail_account, self.fail_send = [], fail_account, fail_send

    def account(self):
        if self.fail_account:
            raise RuntimeError("expected exactly 1 active Gmail connection, found 0")
        return "acct"

    def send(self, **kw):
        if self.fail_send:
            raise RuntimeError("GMAIL_SEND_EMAIL refused")
        self.sent.append(kw)
        return {"id": "m1"}


def store(**extra):
    base = {
        db.SETTINGS: [{"key": "billing", "value": {"company": {"name": "WS Regulab", "email": "info@kkmhalalconsultant.com"}}}],
        db.POSTS: [], db.IDEAS: [], db.API_STATUS: [], "semasa_gemini_keys": [], "semasa_chatgpt_auth": [],
        "semasa_billing_outbox": [], "semasa_log": [], "semasa_businesses": [],
    }
    base.update(extra)
    return FakeStore(**base)


def test_a_publisher_error_from_a_fixed_bug_is_cleared_and_a_linkedin_restriction_is_only_reported():
    st = store(**{db.POSTS: [
        {"id": "p1", "date": "2026-11-08", "slot": "21:00", "stream": "regulab", "status": "approved",
         "errors": {"threads": {"message": THUMB, "fingerprint": "f"}, "facebook": {"message": THUMB}, "at": "x"}},
        {"id": "p2", "date": "2026-11-03", "slot": "06:00", "stream": "linkedin", "status": "approved",
         "errors": {"linkedin": {"message": 'LinkedIn refused: {"code":"RESTRICTED_MEMBER","message":"Member is restricted"}'}}},
        {"id": "p3", "date": "2026-11-09", "slot": "08:00", "stream": "regulab", "status": "approved",
         "errors": {"instagram": {"message": "Instagram needs a picture and this post has none"}}},
    ]})
    out = health.run(st, NOW, sender=Sender())
    p1 = next(p for p in st.tables[db.POSTS] if p["id"] == "p1")
    assert p1["errors"] == {}, "both channels cleared, and the stray 'at' with them"
    p2 = next(p for p in st.tables[db.POSTS] if p["id"] == "p2")
    assert "linkedin" in p2["errors"], "a LinkedIn restriction is LinkedIn's own decision: never cleared"
    state = next(r for r in st.tables[db.SETTINGS] if r["key"] == health.STATE_KEY)["value"]
    assert len(state["fixed"]) == 2 and all("tried again at its slot" in x for x in state["fixed"])
    whats = " | ".join(p["what"] for p in state["problems"])
    assert "LinkedIn refuses 1 post(s)" in whats and "Instagram needs a picture" in whats
    assert out["emailed"] and out["kind"] == "attention"


def test_an_idea_the_writer_did_not_answer_is_retried_but_a_no_fit_idea_is_not():
    st = store(**{db.IDEAS: [
        {"id": "i1", "source_title": "A", "status": "error", "attempts": 1, "error": "the writer did not answer (the run log)",
         "updated_at": "2026-11-06T10:00:00Z"},
        {"id": "i2", "source_title": "B", "status": "error", "attempts": 1, "error": "the writer judged this headline no fit",
         "updated_at": "2026-11-06T10:00:00Z"},
        {"id": "i3", "source_title": "C", "status": "error", "attempts": 3, "error": "the writer did not answer",
         "updated_at": "2026-11-06T10:00:00Z"},
        {"id": "i4", "source_title": "D", "status": "error", "attempts": 0, "error": "the writer did not answer",
         "updated_at": "2026-10-01T10:00:00Z"},
    ]})
    health.run(st, NOW, sender=Sender())
    status = {r["id"]: r["status"] for r in st.tables[db.IDEAS]}
    assert status == {"i1": "new", "i2": "error", "i3": "error", "i4": "error"}, "only a recent, transient, not-worn-out failure"


def test_the_same_problems_are_not_emailed_twice_but_the_morning_summary_always_goes():
    st = store(**{db.API_STATUS: [{"slug": "gemini", "name": "Gemini", "role": "primary", "key_set": True, "key_ok": True,
                                   "reachable": True, "chat_ok": False, "model": "gemini-3.6-flash", "error": "Read timed out"}]})
    s = Sender()
    assert health.run(st, NOW, sender=s)["kind"] == "attention"
    assert health.run(st, NOW, sender=s)["kind"] == "", "nothing new: no second e-mail"
    assert len(s.sent) == 1 and s.sent[0]["to"] == "info@kkmhalalconsultant.com"
    assert s.sent[0]["subject"] == "Semasa watchdog: needs attention"
    assert s.sent[0]["html"].startswith("<p>PROBLEM: AI: Gemini: listed its models but its model gemini-3.6-flash did not answer")
    assert health.run(st, MORNING, sender=s)["kind"] == "summary"
    assert health.run(st, MORNING, sender=s)["kind"] == "", "one summary a day"
    assert len(s.sent) == 2 and s.sent[1]["subject"] == "Semasa watchdog: daily check, 1 need attention"
    assert "PROBLEM (since 2026-11-07T09:30:00Z)" in s.sent[1]["html"], "the daily check says how long it has been open"


def test_a_dead_gmail_connection_is_a_problem_and_a_clean_system_says_all_is_well_once_a_day():
    st = store()
    out = health.run(st, NOW, sender=Sender(fail_account=True))
    state = next(r for r in st.tables[db.SETTINGS] if r["key"] == health.STATE_KEY)["value"]
    assert any("Gmail connection did not answer" in p["what"] for p in state["problems"]) and out["kind"] == "attention"
    st2, s = store(), Sender()
    assert health.run(st2, NOW, sender=s)["kind"] == "", "a clean system at 17:30 sends nothing"
    assert health.run(st2, MORNING, sender=s)["kind"] == "summary"
    assert s.sent[0]["subject"] == "Semasa watchdog: daily check, all working"


def test_a_report_that_cannot_be_sent_is_kept_and_says_so():
    st = store(**{db.API_STATUS: [{"slug": "x", "name": "X", "key_set": True, "key_ok": False, "reachable": True}]})
    out = health.run(st, NOW, sender=Sender(fail_send=True))
    state = next(r for r in st.tables[db.SETTINGS] if r["key"] == health.STATE_KEY)["value"]
    assert not out["emailed"] and any("could not be e-mailed" in p["what"] for p in state["problems"])
    assert "emailed_fingerprint" not in state and not state.get("open"), "it tries again next run"


def test_failed_workflows_are_read_from_github_and_cancelled_ones_are_not_problems(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "wanshah07/semasa")
    monkeypatch.setenv("GITHUB_TOKEN", "t")

    class R:
        status_code = 200

        def json(self):
            return {"workflow_runs": [
                {"name": "Publish", "conclusion": "failure", "html_url": "https://github.com/x/runs/1"},
                {"name": "Publish", "conclusion": "failure", "html_url": "https://github.com/x/runs/2"},
                {"name": "Generate media", "conclusion": "cancelled", "html_url": "https://github.com/x/runs/3"},
                {"name": "Scrape", "conclusion": "success", "html_url": "https://github.com/x/runs/4"}]}

    class S:
        def get(self, url, **kw):
            assert "created" in kw["params"] and kw["headers"]["Authorization"] == "Bearer t"
            return R()

    got = health.check_workflows(NOW, S())
    assert len(got) == 1 and got[0]["what"].startswith("Publish: 2 run(s) failed")
    assert health.fingerprint(got) == health.fingerprint([{**got[0], "what": got[0]["what"].replace("runs/1", "runs/9")}]), \
        "a new run address alone is not a new problem"


def test_a_business_whose_own_gmail_is_not_connected_is_reported_and_a_connected_one_is_not():
    val = {"valorith": {"company": {"name": "Valorith", "email": "muhammad.ridzuan22222@gmail.com"}},
           "wsregulab": {"company": {"name": "WS Regulab", "email": "info@kkmhalalconsultant.com"}}}

    class Box:
        def __init__(self, address):
            self.address = address

        def mailbox(self):
            return self.address
    connected = health.check_business_gmail(val, "info@kkmhalalconsultant.com", lambda e: Box(e))
    assert connected == [], "WS REGULAB is the default inbox, Valorith's own is connected"
    missing = health.check_business_gmail(val, "info@kkmhalalconsultant.com", lambda e: Box("info@kkmhalalconsultant.com"))
    assert len(missing) == 1 and "Valorith's Gmail (muhammad.ridzuan22222@gmail.com) is not connected" in missing[0]["what"]
    assert "go out from info@kkmhalalconsultant.com" in missing[0]["what"]
    assert health.check_business_gmail(val, "info@kkmhalalconsultant.com", None) == [], "no Composio key: check_gmail says so"


def test_a_problem_that_clears_says_fixed_with_the_moment_it_started_in_the_watchdogs_plain_words():
    down = {"slug": "gemini", "name": "Gemini", "role": "primary", "key_set": True, "key_ok": True, "reachable": True,
            "chat_ok": False, "model": "gemini-3.6-flash", "error": "Read timed out"}
    st, s = store(**{db.API_STATUS: [down]}), Sender()
    health.run(st, NOW, sender=s)
    st.tables[db.API_STATUS][0].update(chat_ok=True, error="")
    later = datetime(2026, 11, 7, 13, 17, tzinfo=UTC)
    assert health.run(st, later, sender=s)["kind"] == "fixed"
    mail = s.sent[-1]
    assert mail["subject"] == "Semasa watchdog: all working again"
    assert "FIXED: " in mail["html"] and "is working again (problem started 2026-11-07T09:30:00Z)" in mail["html"]
    assert mail["html"].rstrip().endswith("<p>Semasa → Log shows every check.</p>")
    assert health.run(st, later, sender=s)["kind"] == "", "said once"


def _gemini_down():
    return {"slug": "gemini", "name": "Gemini", "role": "primary", "key_set": True, "key_ok": True, "reachable": True,
            "chat_ok": False, "model": "gemini-3.6-flash", "error": "Read timed out"}


def test_the_telegram_copy_carries_the_new_problem_and_is_rendered_before_the_state_moves(monkeypatch):
    from semasa import telegram_bot
    told = []
    monkeypatch.setattr(telegram_bot, "notify", lambda store, text, bot=None: told.append(text) or True)
    st, s = store(**{db.API_STATUS: [_gemini_down()]}), Sender()
    health.run(st, NOW, sender=s)
    assert "PROBLEM: " in told[0] and "Gemini" in told[0] and "PROBLEM: " in s.sent[0]["html"]
    st.tables[db.API_STATUS][0].update(chat_ok=True, error="")
    health.run(st, datetime(2026, 11, 7, 13, 17, tzinfo=UTC), sender=s)
    assert "FIXED: " in told[1] and "problem started 2026-11-07T09:30:00Z" in told[1]


def test_with_no_email_a_telegram_alert_is_enough_and_is_not_repeated(monkeypatch):
    from semasa import telegram_bot
    told = []
    monkeypatch.setattr(telegram_bot, "notify", lambda store, text, bot=None: told.append(text) or True)
    st = store(**{db.API_STATUS: [_gemini_down()], db.SETTINGS: []})       # no company address: no e-mail at all
    assert health.run(st, NOW, sender=Sender())["kind"] == "attention" and len(told) == 1
    assert "No e-mail copy" in told[0]
    assert health.run(st, NOW, sender=Sender())["kind"] == "", "Wan was told on Telegram: not every run again"
    assert len(told) == 1


def test_a_failed_email_still_goes_to_telegram_once_and_neither_means_try_again(monkeypatch):
    from semasa import telegram_bot
    told = []
    monkeypatch.setattr(telegram_bot, "notify", lambda store, text, bot=None: told.append(text) or True)
    st = store(**{db.API_STATUS: [_gemini_down()]})
    health.run(st, NOW, sender=Sender(fail_send=True))
    assert len(told) == 1 and "e-mail copy could not be sent" in told[0]
    assert health.run(st, NOW, sender=Sender(fail_send=True))["kind"] == ""
    monkeypatch.setattr(telegram_bot, "notify", lambda store, text, bot=None: False)
    st2 = store(**{db.API_STATUS: [_gemini_down()]})
    health.run(st2, NOW, sender=Sender(fail_send=True))
    assert health.run(st2, NOW, sender=Sender(fail_send=True))["kind"] == "attention", "nobody was told: it says it again"


def test_failed_workflows_are_asked_for_by_status_and_paged_past_the_newest_hundred(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "wanshah07/semasa")
    monkeypatch.setenv("GITHUB_TOKEN", "t")
    asked = []

    class R:
        status_code = 200

        def __init__(self, runs):
            self.runs = runs

        def json(self):
            return {"workflow_runs": self.runs}

    class S:
        def get(self, url, **kw):
            p = kw["params"]
            asked.append((p["status"], p["page"]))
            if p["status"] != "failure":
                return R([])
            n = 100 if p["page"] == 1 else 7               # a busy day: more than one page of failures
            return R([{"id": p["page"] * 1000 + i, "name": "Publish", "conclusion": "failure",
                       "html_url": f"https://github.com/x/runs/{p['page']}-{i}", "created_at": "2026-11-07T01:00:00Z"}
                      for i in range(n)])

    got = health.check_workflows(NOW, S())
    assert asked == [("failure", 1), ("failure", 2), ("timed_out", 1), ("startup_failure", 1)]
    assert got[0]["what"].startswith("Publish: 107 run(s) failed in 24 h")


def test_hermes_transport_does_not_need_a_semasa_webhook():
    bot = {"transport": "hermes", "webhook": "", "last_error": ""}
    st = store(**{db.SETTINGS: [{"key": "telegram_bot", "value": bot}], "semasa_telegram_inbox": []})
    assert health.check_telegram(st, NOW) == []
    st.tables["semasa_telegram_inbox"].append({"id": 1, "kind": "private", "status": "new",
                                               "created_at": (NOW - timedelta(minutes=40)).isoformat()})
    assert any("not answered" in p["what"] for p in health.check_telegram(st, NOW))


def test_a_telegram_webhook_error_older_than_an_answered_message_is_not_a_problem():
    # Telegram reports its LAST webhook error for ever; ten messages answered after it prove the webhook works
    bot = {"webhook": "https://x/functions/v1/semasa-telegram", "last_error": "Wrong response from the webhook: 404 Not Found",
           "last_error_at": int(NOW.timestamp()) - 3600}
    st = store(**{db.SETTINGS: [{"key": "telegram_bot", "value": bot}], "semasa_telegram_inbox": []})
    assert any("could not deliver" in p["what"] for p in health.check_telegram(st, NOW))
    st.tables["semasa_telegram_inbox"].append({"id": 1, "kind": "private", "status": "done",
                                               "created_at": (NOW - timedelta(minutes=10)).isoformat()})
    assert not any("could not deliver" in p["what"] for p in health.check_telegram(st, NOW))
