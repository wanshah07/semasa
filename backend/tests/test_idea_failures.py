"""A failed idea is handled by itself (Wan, 26 Nov 2026): the hook retried, an autofill idea with no fit deleted, a post that went
out everywhere moved to posted."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import autofill, idea_failures, ideas, publisher
from semasa.ideas import IdeaError

NOW = datetime(2026, 11, 26, 7, 0, tzinfo=UTC)
HOOK = "the writer did not build the hook on one of the 25 hook shapes (asked twice): press Cuba lagi"
TWIN = ("the same event is already written up for this stream (Adakah semua premis makanan boleh dimasuki?), so it is not "
        "written again. For a follow-up, add a note saying what the new post should say, then Cuba lagi.")
NOFIT = "the writer judged this headline no fit for regulab: The source page is only a cookie notice. Add a note, then Cuba lagi."


def _store(idea):
    return FakeStore(semasa_ideas=[idea], semasa_settings=[], semasa_log=[], semasa_posts=[])


def _idea(auto=True, **brief):
    return {"id": "i1", "stream": "regulab", "status": "error", "source_url": "https://npra.gov.my/1", "source_title": "Notis",
            "brief": {**({"auto": True} if auto else {}), **brief}}


def test_kinds():
    kind = idea_failures.kind_of
    assert kind(HOOK) == "hook" and kind(TWIN) == "twin" and kind(NOFIT) == "nofit"
    assert idea_failures.kind_of("this news already has a posted post for this stream (x), so it is not written again.") == "twin"
    assert idea_failures.kind_of("the writer did not answer (see the run log); ask again") is None


def test_a_hook_failure_goes_back_in_the_queue_with_a_firmer_ask_and_stops_after_three():
    store = _store(_idea(hook_style="mine"))
    assert idea_failures.settle(store, store.tables["semasa_ideas"][0], HOOK, NOW) == "retry"
    row = store.tables["semasa_ideas"][0]
    assert row["status"] == "new" and row["error"] is None and row["brief"]["hook_retry"] == 1
    assert row["brief"]["hook_style"] == "mine"
    assert idea_failures.settle(store, row, HOOK, NOW) == "retry"
    row = store.tables["semasa_ideas"][0]
    assert row["brief"]["hook_retry"] == 2 and "hook_style" not in row["brief"]            # from the second: the built-in 25
    assert idea_failures.settle(store, row, HOOK, NOW) == "retry"
    row = store.tables["semasa_ideas"][0]
    row["status"] = "error"
    assert idea_failures.settle(store, row, HOOK, NOW) == "" and row["status"] == "error"   # the fourth: the card stays for Wan


def test_a_hook_retry_asks_the_writer_more_firmly():
    idea = {"stream": "regulab", "source_title": "t", "brief": {"hook_retry": 1}}
    user = ideas.build_request(idea, {"ok": False}, {})[1]
    assert "ATTEMPT 2" in user and "hook_shape" in user
    assert "ATTEMPT" not in ideas.build_request({"stream": "regulab", "source_title": "t", "brief": {}}, {"ok": False}, {})[1]


def test_an_autofill_idea_with_no_fit_or_a_twin_is_deleted_and_not_picked_again():
    for message in (NOFIT, TWIN):
        store = _store(_idea())
        assert idea_failures.settle(store, store.tables["semasa_ideas"][0], message, NOW) == "deleted"
        assert store.tables["semasa_ideas"] == []
        assert "https://npra.gov.my/1" in idea_failures.skipped(store)
        rows = [{"id": "w1", "section": "regulatory", "title": "Notis tentang label baharu", "url": "https://npra.gov.my/1",
                 "summary": "s", "domain": "kosmetik", "relevant": True, "dismissed": False,
                 "created_at": "2026-11-25T00:00:00+00:00"}]
        store.tables["semasa_watch"] = rows
        assert autofill.candidates(store, NOW) == []


def test_an_idea_wan_typed_keeps_its_error_card():
    store = _store(_idea(auto=False))
    assert idea_failures.settle(store, store.tables["semasa_ideas"][0], NOFIT, NOW) == ""
    assert len(store.tables["semasa_ideas"]) == 1


def test_an_faq_idea_is_remembered_by_its_faq_id():
    idea = {**_idea(faq_id="q7"), "source_url": None}
    store = _store(idea)
    idea_failures.settle(store, store.tables["semasa_ideas"][0], NOFIT, NOW)
    assert "faq://q7" in idea_failures.skipped(store)


def test_the_run_loop_settles_a_failed_idea(monkeypatch):
    store = _store({**_idea(), "status": "new"})
    monkeypatch.setattr(ideas, "process_idea", lambda *a, **k: (_ for _ in ()).throw(IdeaError(HOOK)))
    monkeypatch.setattr(ideas, "load_settings", lambda s: {})
    monkeypatch.setattr(ideas, "recover_stale", lambda s: 0)
    ideas.run(store, object(), 1)
    row = store.tables["semasa_ideas"][0]
    assert row["status"] == "new" and row["brief"]["hook_retry"] == 1


def _post(status, channels, **over):
    return {"id": "p1", "stream": "regulab", "status": status, "date": "2026-10-02", "slot": "09:15", "hook": "H",
            "published": {c: {"status": s} for c, s in channels.items()}, **over}


def test_a_post_sent_on_every_channel_is_moved_to_posted_whatever_status_it_kept(monkeypatch):
    monkeypatch.setattr(publisher, "post_channels", lambda settings, post, has_video=None: ["facebook", "instagram", "threads"])
    sent = {"facebook": "sent", "instagram": "sent", "threads": "sent"}
    store = FakeStore(semasa_posts=[_post("scheduled", sent), _post("draft", sent, id="p2"),
                                    _post("approved", {**sent, "threads": "scheduled"}, id="p3"),
                                    _post("approved", {}, id="p4"), _post("posted", sent, id="p5")], semasa_log=[])
    assert publisher.promote_sent(store, {}) == 2
    got = {p["id"]: p["status"] for p in store.tables["semasa_posts"]}
    assert got == {"p1": "posted", "p2": "posted", "p3": "approved", "p4": "approved", "p5": "posted"}
