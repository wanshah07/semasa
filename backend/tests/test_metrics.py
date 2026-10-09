"""Prestasi: Buffer's per-post figures → semasa_post_metrics rows, joined to the Semasa post that sent them."""
from datetime import UTC, datetime

import pytest
from fakestore import FakeStore

from semasa import db, metrics
from semasa.senders import SendError

NOW = datetime(2026, 10, 9, 5, 10, tzinfo=UTC)
CHANNELS = {"key": "channels",
            "value": {"buffer": {"organizationId": "org1", "facebook": "fb1", "instagram": "ig1", "threads": "th1"}}}


def _node(**kw):
    base = {"id": "b1", "status": "sent", "channelId": "th1", "channelService": "threads", "dueAt": "2026-10-08T13:00:00.000Z",
            "sentAt": "2026-10-08T13:04:20.192Z", "text": "Kod macam LM10 bukan bukti lemak babi. " * 10,
            "externalLink": "https://www.threads.com/@ws.regulab/post/x", "metricsUpdatedAt": "2026-10-09T01:29:13.026Z",
            "metrics": [{"type": "reactions", "value": 10, "unit": "count"}, {"type": "comments", "value": 0, "unit": "count"},
                        {"type": "engagementRate", "value": 5.11, "unit": "percentage"},
                        {"type": "views", "value": 274, "unit": "count"}, {"type": "quotes", "value": 0, "unit": "count"},
                        {"type": "reposts", "value": 4, "unit": "count"}]}
    base.update(kw)
    return base


class FakeBuffer:
    def __init__(self, nodes):
        self.nodes, self.asked = nodes, []

    def sent_with_metrics(self, channel_ids, start, end):
        self.asked.append((channel_ids, start, end))
        return self.nodes


def _store(posts=()):
    return FakeStore(**{db.SETTINGS: [CHANNELS, {"key": "metrics", "value": {"days_back": 30}}], db.POSTS: list(posts),
                        db.POST_METRICS: [], db.LOG: []})


def test_normalise_maps_each_network_and_leaves_the_rest_null():
    th = metrics.normalise(_node()["metrics"])
    assert th["views"] == 274 and th["reactions"] == 10 and th["reposts"] == 4 and th["engagement"] == 5.11
    assert th["reach"] is None and th["impressions"] is None
    fb = metrics.normalise([{"type": "impressions", "value": 34.0}, {"type": "clicks", "value": 1},
                            {"type": "unknownThing", "value": 9}])
    assert fb["impressions"] == 34 and fb["clicks"] == 1 and fb["views"] is None
    assert metrics.normalise(None)["views"] is None


def test_rows_are_written_linked_to_the_semasa_post_and_asked_in_the_window():
    posts = [{"id": "p1", "status": "posted", "published": {"threads": {"id": "b1", "status": "sent"}, "facebook": {"id": "b2"}}},
             {"id": "p2", "status": "draft", "published": {}}]
    store = _store(posts)
    buf = FakeBuffer([_node(), _node(id="b9", channelId="fb1", channelService="facebook", metrics=[]),
                      _node(id="li", channelService="linkedin")])
    counts = metrics.run(store, NOW, buf)
    assert counts == {"read": 2, "written": 2, "linked": 1, "no_figures": 1}
    rows = {r["external_id"]: r for r in store.tables[db.POST_METRICS]}
    assert rows["b1"]["post_id"] == "p1" and rows["b1"]["views"] == 274 and rows["b1"]["channel"] == "threads"
    assert rows["b1"]["sent_at"] == "2026-10-08T13:04:20.192Z" and len(rows["b1"]["text_head"]) == 200
    assert rows["b9"]["post_id"] is None and rows["b9"]["views"] is None and rows["b9"]["metrics"] == []
    assert buf.asked[0][0] == ["fb1", "ig1", "th1"] and buf.asked[0][1].startswith("2026-09-09")
    assert store.tables[db.LOG][-1]["event"] == "metrics.read"
    # a second run updates the same rows rather than adding
    buf.nodes[0]["metrics"][3]["value"] = 300
    metrics.run(store, NOW, buf)
    assert len(store.tables[db.POST_METRICS]) == 2
    assert {r["external_id"]: r for r in store.tables[db.POST_METRICS]}["b1"]["views"] == 300


def test_no_channel_ids_is_a_refusal_that_is_logged():
    store = FakeStore(**{db.SETTINGS: [{"key": "channels", "value": {}}], db.POSTS: [], db.POST_METRICS: [], db.LOG: []})
    with pytest.raises(SendError):
        metrics.run(store, NOW, FakeBuffer([]))
    assert store.tables[db.LOG][-1]["event"] == "metrics.failed"


def test_no_key_skips_with_a_warning(monkeypatch):
    monkeypatch.delenv("BUFFER_API_KEY", raising=False)
    store = _store()
    assert metrics.run(store, NOW)["written"] == 0
    assert store.tables[db.LOG][-1]["event"] == "metrics.skipped"
