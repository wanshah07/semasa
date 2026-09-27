"""The Studio link: a Studio post that went out takes its Semasa copy out of the drafts, into the Arkib."""

import json

import pytest
from fakestore import FakeStore

from semasa import studio_link as sl

SID = "y59n20rc7o"


def _copy(status="draft", **over):
    return {"id": sl.semasa_id(SID), "status": status, "stream": "regulab", "lang": "bm", "hook": "Notifikasi NPRA",
            "text": {"bm": {"instagram": "IG", "facebook": "FB", "threads": "TH"}, "en": {"instagram": "EN"}},
            "flags": [{"hard": True, "where": "Post", "msg": "instagram needs an image"}], "hard_flags": 1,
            "published": {}, "errors": {}, "posted_at": None, "archived_at": None, **over}


POSTED = {SID: {"facebook": {"id": "b1", "at": "2026-09-28 08:00 MYT"}, "instagram": {"id": "b2", "at": "2026-09-28 08:02 MYT"}}}


def test_the_id_is_the_one_the_import_used():
    # 020_import_studio_*: uuid5(uuid5(URL, <artifact url>), "drafts/<studio id>")
    assert sl.semasa_id("y59n20rc7o") == "bf3c27e0-53a1-5776-819a-b3ad4dadec63"      # its row in part 2
    assert sl.semasa_id("a") == sl.semasa_id("a") != sl.semasa_id("b")


def test_a_posted_studio_draft_leaves_the_drafts_for_the_archive():
    store = FakeStore(semasa_posts=[_copy()], semasa_log=[])
    out = sl.apply(store, POSTED)
    row = store.tables["semasa_posts"][0]
    assert out["moved"] == 1 and row["status"] == "posted" and row["archived_at"]
    assert row["published"]["facebook"] == {"id": "b1", "at": "2026-09-28 08:00 MYT", "via": "ws.regulab Studio"}
    assert row["text"] == {"bm": {"instagram": "IG", "facebook": "FB"}}      # what went out, like archive.py
    assert row["flags"] == [] and row["hard_flags"] == 0
    assert row["posted_at"].startswith("2026-09-28T00:02")                    # 08:02 MYT, the later channel
    assert any(r["event"] == "studio.posted" for r in store.tables["semasa_log"])


@pytest.mark.parametrize("status", ["approved", "scheduled", "rejected"])
def test_every_queue_state_is_filed(status):
    store = FakeStore(semasa_posts=[_copy(status)], semasa_log=[])
    assert sl.apply(store, POSTED)["moved"] == 1
    assert store.tables["semasa_posts"][0]["status"] == "posted"


def test_history_and_unknown_drafts_are_left_alone():
    kept = _copy("posted", published={"threads": {"id": "old"}}, archived_at="2026-09-20T00:00:00+00:00")
    store = FakeStore(semasa_posts=[kept], semasa_log=[])
    out = sl.apply(store, {**POSTED, "newdraft01": {"linkedin": {"id": "urn:li:share:1"}}})
    assert out == {"moved": 0, "already": 1, "unknown": 1, "moved_ids": [], "unknown_ids": ["newdraft01"]}
    assert store.tables["semasa_posts"][0]["published"] == {"threads": {"id": "old"}}
    assert store.tables["semasa_log"] == []


def test_running_twice_changes_nothing_the_second_time():
    store = FakeStore(semasa_posts=[_copy()], semasa_log=[])
    sl.apply(store, POSTED)
    first = json.dumps(store.tables["semasa_posts"][0], sort_keys=True, default=str)
    assert sl.apply(store, POSTED)["moved"] == 0
    assert json.dumps(store.tables["semasa_posts"][0], sort_keys=True, default=str) == first


@pytest.mark.parametrize("raw", ["", "[]", '{"x": {}}', '{"x": {"tiktok": {}}}', '{"../x": {"facebook": {}}}',
                                 '{"x": {"facebook": {}}, "y": "no"}'])
def test_a_message_that_cannot_be_read_changes_nothing(raw):
    with pytest.raises(sl.LinkError):
        sl.parse(raw)


def test_parse_keeps_only_the_delivery_fields():
    got = sl.parse(json.dumps({SID: {"linkedin": {"id": "urn:li:share:9", "at": "2026-09-27 19:25 MYT",
                                                  "slides": 8, "route": "composio+image"}}}))
    assert got == {SID: {"linkedin": {"id": "urn:li:share:9", "at": "2026-09-27 19:25 MYT"}}}


def test_studio_stamps_are_read_as_malaysia_time():
    assert sl.when_utc("2026-09-24 19:25 MYT").isoformat() == "2026-09-24T11:25:00+00:00"
    assert sl.when_utc("2026-09-22T22:29:00.000Z").isoformat() == "2026-09-22T22:29:00+00:00"
    assert sl.when_utc("15 Sep") is None and sl.when_utc("2026-09-24T19:25") is None
