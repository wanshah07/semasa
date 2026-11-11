"""The post-slot checker (Wan, 11 Nov 2026)."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import db, publisher, slotcheck

NOW = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)            # 11:00 MYT: the 10:30 slot (02:30 UTC) is 30 minutes ago


def _rec(status, route="zernio"):
    return {"id": "z1", "route": route, "status": status, "account": "a1", "dueAt": "2026-11-11T02:30:00.000Z"}


def _post(pid="p1", status="scheduled", slot="10:30", published=None, errors=None):
    return {"id": pid, "stream": "regulab", "status": status, "date": "2026-11-11", "slot": slot, "hook": "Hook ayat",
            "lang": "bm", "channels": ["threads"], "text": {"bm": {"threads": "Ayat."}}, "media_ids": [],
            "published": published if published is not None else {}, "errors": errors or {}}


def _store(*posts):
    return FakeStore(semasa_posts=list(posts), semasa_log=[], semasa_settings=[])


def _run(monkeypatch, store, sent):
    monkeypatch.setattr(publisher, "load_settings", lambda s: {})
    monkeypatch.setattr(publisher, "post_channels", lambda settings, p, has_video=None: ["threads"])
    return slotcheck.run(store, None, NOW, notify=lambda s, text: sent.append(text))


def test_a_failed_channel_is_reported_once_with_the_platforms_own_words(monkeypatch):
    store = _store(_post(published={"threads": _rec("error")},
                         errors={"threads": {"message": "threads: The parameter text is required"}}))
    sent = []
    first = _run(monkeypatch, store, sent)
    assert (first["problems"], first["new"]) == (1, 1) and len(sent) == 1
    assert "The parameter text is required" in sent[0] and "Gagal di threads" in sent[0]
    again = _run(monkeypatch, store, sent)
    assert (again["problems"], again["new"]) == (1, 0) and len(sent) == 1           # told once, not every run
    assert any(r["event"] == "slotcheck.alert" for r in store.tables["semasa_log"])


def test_a_channel_still_not_sent_twenty_minutes_after_its_slot_is_stuck(monkeypatch):
    store = _store(_post(published={"threads": _rec("scheduled")}))
    sent = []
    res = _run(monkeypatch, store, sent)
    assert res["new"] == 1 and "still not sent 30 minutes" in sent[0]
    early = _store(_post(slot="10:50", published={"threads": _rec("scheduled")}))        # due 02:50: only 10 minutes ago
    assert _run(monkeypatch, early, []) ["problems"] == 0


def test_an_approved_post_whose_slot_passed_with_a_channel_never_handed_over_is_named(monkeypatch):
    store = _store(_post(status="approved", slot="08:00", published={}))
    sent = []
    res = _run(monkeypatch, store, sent)
    assert res["new"] == 1 and "Terlepas slot di threads" in sent[0]


def test_a_clean_run_tells_nobody_and_logs_that_it_ran(monkeypatch):
    store = _store(_post(status="posted", published={"threads": _rec("sent")}))
    sent = []
    res = _run(monkeypatch, store, sent)
    assert res["problems"] == 0 and sent == []
    assert [r["event"] for r in store.tables["semasa_log"]] == ["slotcheck.ok"]
    assert store.tables["semasa_posts"][0]["status"] == "posted"                       # nothing is written to a post


def test_a_slot_not_yet_due_is_left_alone(monkeypatch):
    store = _store(_post(slot="13:00", published={"threads": _rec("scheduled")}))
    assert _run(monkeypatch, store, [])["problems"] == 0
    assert db.POSTS == "semasa_posts"
