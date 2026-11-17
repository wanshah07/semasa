"""The post-slot checker (Wan, 11 Nov 2026)."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import db, publisher, senders, slotcheck

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


# --- sending again after a move, and a post Zernio no longer holds (16 Nov 2026) --------------------------------------------

def _settings(monkeypatch):
    monkeypatch.setattr(publisher, "load_settings", lambda s: {})
    monkeypatch.setattr(publisher, "post_channels", lambda settings, p, has_video=None: ["threads"])


class Gone:
    """A Zernio that answers "Post not found" for everything, in every login."""

    def get(self, post_id, account_id=""):
        raise senders.SendError("refused", "Zernio refused (404): Post not found", status=404)

    def gone(self, post_id):
        return True


def test_a_post_zernio_no_longer_holds_is_settled_and_told_as_failed_not_left_stuck(monkeypatch):
    _settings(monkeypatch)
    rec = {"id": "a" * 24, "route": "zernio", "status": "scheduled", "account": "a1", "dueAt": "2026-11-10T11:00:00.000Z"}
    store = _store(_post(slot="19:00", published={"threads": rec}) | {"date": "2026-11-10"})     # 16 hours ago: a late run
    store.tables["semasa_publish_log"] = []
    sent = []
    res = slotcheck.run(store, Gone(), NOW, notify=lambda s, text: sent.append(text))
    p = store.tables["semasa_posts"][0]
    assert res["confirmed"] == 1 and p["published"]["threads"]["status"] == "error" and p["published"]["threads"]["lost"]
    assert res["new"] == 1 and "Gagal di threads" in sent[0] and "no longer holds this post" in sent[0]
    assert "Belum keluar" not in sent[0]                                               # settled, so no longer "stuck"


def test_a_late_run_still_reads_back_every_due_record_however_old(monkeypatch):
    _settings(monkeypatch)

    class Sent:
        def get(self, post_id, account_id=""):
            return {"id": post_id, "status": "sent", "externalLink": "https://t/1"}

    rec = {"id": "b" * 24, "route": "zernio", "status": "scheduled", "account": "a1", "dueAt": "2026-11-05T02:30:00.000Z"}
    store = _store(_post(published={"threads": rec}) | {"date": "2026-11-05"})          # six days ago: far outside WINDOW
    store.tables["semasa_publish_log"] = []
    res = slotcheck.run(store, Sent(), NOW, notify=lambda s, text: None)
    p = store.tables["semasa_posts"][0]
    assert res["confirmed"] == 1 and p["published"]["threads"]["status"] == "sent" and p["status"] == "posted"


def test_a_post_moved_to_go_again_is_quiet_until_its_new_slot_and_named_if_the_slot_is_missed(monkeypatch):
    failed = {"id": "c" * 24, "route": "zernio", "status": "error", "account": "a1", "dueAt": "2026-11-10T02:30:00.000Z"}
    errors = {"threads": {"message": "threads: token refresh failed"}}
    waiting = _store(_post(slot="13:00", published={"threads": failed}, errors=errors))      # moved to 13:00, two hours ahead
    assert _run(monkeypatch, waiting, [])["problems"] == 0
    missed = _store(_post(slot="08:00", published={"threads": failed}, errors=errors))       # moved to 08:00: three hours gone
    sent = []
    res = _run(monkeypatch, missed, sent)
    assert res["new"] == 1 and "Terlepas slot di threads" in sent[0] and "sent again" in sent[0]
    assert "Gagal di threads" not in sent[0]                                           # the old failure is not told twice


def test_a_channel_that_fails_again_at_a_new_slot_is_told_again(monkeypatch):
    first = _post(published={"threads": _rec("error")}, errors={"threads": {"message": "threads: refused"}})
    store, sent = _store(first), []
    assert _run(monkeypatch, store, sent)["new"] == 1
    assert _run(monkeypatch, store, sent)["new"] == 0                                    # the same slot: told once
    # the post is moved (10:30 to 08:00 here, both gone by NOW) and the channel fails at the new slot as well
    p = store.tables["semasa_posts"][0]
    p.update(slot="08:00", published={"threads": {**_rec("error"), "dueAt": "2026-11-11T00:00:00.000Z"}})
    assert _run(monkeypatch, store, sent)["new"] == 1 and len(sent) == 2
