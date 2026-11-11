"""Wan, 10 Nov 2026: a scheduled post can be pulled back to draft so it can be edited, for ws.regulab and for LinkedIn."""
from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import pullback, senders

NOW = datetime(2026, 11, 10, 15, 0, tzinfo=UTC)


class Hub:
    def __init__(self, fail=None):
        self.deleted, self.fail = [], fail

    def delete(self, post_id, account_id=""):
        if self.fail:
            raise senders.SendError("refused", self.fail)
        self.deleted.append((post_id, account_id))
        return {}


def _store(published, status="scheduled"):
    post = {"id": "p1", "status": status, "stream": "linkedin", "published": published, "errors": {}, "approved_by": "u",
            "approved_at": "t", "date": "2026-11-12", "slot": "06:00"}
    ask = {"id": "r1", "post_id": "p1", "state": "pending", "requested_at": "2026-11-10T14:00:00Z"}
    return FakeStore(semasa_posts=[post], semasa_post_pullbacks=[ask], semasa_publish_log=[])


def _rec(route="zernio", status="scheduled", i="z1", acc="acc1"):
    return {"id": i, "status": status, "route": route, "account": acc}


def test_a_scheduled_zernio_post_is_taken_out_of_the_queue_and_goes_back_to_draft():
    store, hub = _store({"linkedin": _rec(), "facebook": _rec(i="z2", acc="acc2")}), Hub()
    assert pullback.run(store, NOW, {"zernio": hub}) == {"done": 1, "refused": 0, "failed": 0}
    assert sorted(hub.deleted) == [("z1", "acc1"), ("z2", "acc2")]
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "draft" and post["published"] == {} and post["errors"] == {}
    assert post["approved_by"] is None and post["approved_at"] is None                 # it must be approved again
    assert post["date"] == "2026-11-12" and post["slot"] == "06:00"                    # its position is kept
    row = store.tables["semasa_post_pullbacks"][0]
    assert row["state"] == "done" and "approve it again" in row["note"]
    # logged to the app's log: semasa_publish_log's CHECK has no 'pulled_back' action (the real table refused it, 11 Nov 2026)
    assert [r["event"] for r in store.tables["semasa_log"]] == ["publish.pulled_back", "publish.pulled_back"]
    assert not store.tables.get("semasa_publish_log")


def test_a_post_with_a_published_channel_is_refused_and_left_exactly_as_it_was():
    store, hub = _store({"linkedin": _rec(status="sent"), "facebook": _rec(i="z2")}), Hub()
    assert pullback.run(store, NOW, {"zernio": hub})["refused"] == 1
    assert hub.deleted == [] and store.tables["semasa_posts"][0]["status"] == "scheduled"
    assert "already published on linkedin" in store.tables["semasa_post_pullbacks"][0]["note"]


def test_a_buffer_channel_and_a_missing_sender_are_refused_with_the_reason():
    store = _store({"instagram": _rec(route="buffer", i="b1")})
    pullback.run(store, NOW, {"zernio": Hub()})
    assert "held by buffer" in store.tables["semasa_post_pullbacks"][0]["note"].lower()
    store2 = _store({"linkedin": _rec()})
    pullback.run(store2, NOW, {})
    assert "no Zernio sender" in store2.tables["semasa_post_pullbacks"][0]["note"]
    assert store2.tables["semasa_posts"][0]["status"] == "scheduled"


def test_zernio_refusing_leaves_the_post_scheduled_and_says_why():
    store = _store({"linkedin": _rec()})
    pullback.run(store, NOW, {"zernio": Hub(fail="Zernio refused (409): already publishing")})
    assert store.tables["semasa_posts"][0]["status"] == "scheduled"
    assert "would not take it out of the queue" in store.tables["semasa_post_pullbacks"][0]["note"]


def test_a_posted_or_editable_post_is_refused_plainly():
    for status, word in (("posted", "cannot be taken back"), ("draft", "can already be edited")):
        store = _store({}, status)
        pullback.run(store, NOW, {"zernio": Hub()})
        assert word in store.tables["semasa_post_pullbacks"][0]["note"]


def test_zernio_delete_treats_an_already_gone_post_as_done_and_anything_else_as_a_refusal():
    from types import SimpleNamespace

    class Http:
        def __init__(self, status, body):
            self.status, self.body, self.calls = status, body, []

        def request(self, method, url, **kw):
            self.calls.append((method, url))
            return SimpleNamespace(status_code=self.status, json=lambda: self.body)
    gone = senders.Zernio("k", session=Http(404, {"error": "Post not found", "code": "post_not_found"}))
    assert gone.delete("z1") == {"gone": True}
    assert gone.http.calls[0][0] == "DELETE" and gone.http.calls[0][1].endswith("/posts/z1")
    ok = senders.Zernio("k", session=Http(200, {"message": "deleted"}))
    assert ok.delete("z1") == {"message": "deleted"}
    no = senders.Zernio("k", session=Http(409, {"error": "post is already published"}))
    try:
        no.delete("z1")
        raise AssertionError("should have refused")
    except senders.SendError as exc:
        assert "409" in str(exc)
    hub = senders.ZernioHub({"acc1": ok})
    assert hub.delete("z1", "acc1") == {"message": "deleted"}
