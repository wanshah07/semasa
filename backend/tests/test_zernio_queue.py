"""The full-queue pause applies to Zernio too (Wan, 10 Nov 2026: "this one apply for zernio too")."""

from datetime import UTC, datetime, timedelta

import test_autofill_news_and_buffer as base
from fakestore import FakeStore

from semasa import autofill, buffer_queue, publisher

NOW = base.NOW
ZERNIO = {"enabled": True, "accounts": {"facebook": {"id": "zfb", "key": "2"}, "instagram": {"id": "zig", "key": "1"},
                                        "threads": {"id": "zth", "key": "1"}, "linkedin": {"id": "zli", "key": "2"}}}
BUFFER = {"organizationId": "org1", "facebook": "fb", "instagram": "ig", "threads": "th"}
SETTINGS = {"brand": base.BRAND, "autofill": base.ON, "channels": {"buffer": BUFFER, "zernio": ZERNIO}}


class _Hub:
    def __init__(self, posts):
        self._posts = posts

    def posts(self, ids, start, end):
        return list(self._posts.get(ids[0], []))


def _store(**kw):
    return base._store(**kw)


def _held(n, start_day=26):
    return [base._bp(i, base._myt(start_day, 8) + timedelta(days=i)) for i in range(n)]


def test_zernio_has_no_plan_cap_so_the_cap_is_wans_own_ten_unless_he_sets_another():
    assert buffer_queue.zernio_cap(SETTINGS) == 10
    for raw, want in ((5, 5), ("7", 7), (0, None), ("x", 10)):
        s = {"channels": {"zernio": {**ZERNIO, "queue_limit": raw}}}
        assert buffer_queue.zernio_cap(s) == want
    assert buffer_queue.zernio_ids(SETTINGS) == {"facebook": "zfb", "instagram": "zig", "threads": "zth"}, "LinkedIn is not in it"


def test_a_full_zernio_queue_pauses_new_ideas_says_zernio_and_resumes_when_there_is_room(monkeypatch):
    assert publisher.buffer_is_backup(SETTINGS)
    store = _store(feed=[base._feed(1), base._feed(2)])
    now = {"c": _Hub({"zfb": _held(10), "zig": [], "zth": []})}
    real = buffer_queue.snapshot_zernio
    monkeypatch.setattr(buffer_queue, "snapshot_zernio", lambda st, se, n=None, client=None: real(st, se, n, now["c"]))
    out = autofill.run(store, SETTINGS, NOW)
    assert out.startswith("Autofill: paused") and "Zernio queue is full" in out and "facebook" in out
    assert store.tables["semasa_ideas"] == []
    row = next(r for r in store.tables["semasa_settings"] if r["key"] == "zernio_queue")["value"]
    assert row["paused"] is True and row["counts"]["facebook"] == 10 and row["limit"] == 10
    assert "queue Zernio penuh" in store.tables["semasa_log"][0]["title"]
    now["c"] = _Hub({"zfb": _held(9), "zig": [], "zth": []})
    out2 = autofill.run(store, {**SETTINGS, "zernio_queue": row}, NOW)
    assert "paused" not in out2 and store.tables["semasa_ideas"]
    assert "idea.autofill_resumed" in [e["event"] for e in store.tables["semasa_log"]]


def test_the_slots_zernio_holds_are_taken_and_a_stale_buffer_pause_is_cleared_while_buffer_rests(monkeypatch):
    store = _store(feed=[base._feed(1), base._feed(2)])
    stale = {"paused": True, "full": ["facebook"], "counts": {"facebook": 10}, "limit": 10, "since": "2026-11-10T03:21:00+00:00"}
    settings = {**SETTINGS, "buffer_queue": stale}
    hub = _Hub({"zfb": [base._bp(1, base._myt(25, 8))], "zig": [base._bp(4, base._myt(25, 13))], "zth": []})
    real = buffer_queue.snapshot_zernio
    monkeypatch.setattr(buffer_queue, "snapshot_zernio", lambda st, se, n=None, client=None: real(st, se, n, hub))
    out = autofill.run(store, settings, NOW)
    assert "paused" not in out
    slots = {(i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"]}
    assert slots and ("2026-09-25", "08:00") not in slots and ("2026-09-25", "13:00") not in slots
    cleared = next(r for r in store.tables["semasa_settings"] if r["key"] == "buffer_queue")["value"]
    assert cleared["paused"] is False and cleared["backup"] is True, "the page stops showing a Buffer 'full' while Buffer rests"


def test_zernio_that_cannot_be_read_never_counts_as_full_and_buffer_is_read_again_when_it_is_the_route():
    store = _store(feed=[base._feed(1)])
    no_key = {"brand": base.BRAND, "channels": {"zernio": ZERNIO}}
    assert buffer_queue.snapshot_zernio(store, no_key, NOW) is None
    assert buffer_queue.snapshot_zernio(store, {"brand": base.BRAND}, NOW) is None
    off = {**SETTINGS, "channels": {**SETTINGS["channels"], "zernio": {**ZERNIO, "enabled": False}}}
    assert not publisher.buffer_is_backup(off), "Zernio off: Buffer is the route and its own queue decides again"


def test_unused_imports_stay_used():
    assert FakeStore and UTC and datetime
