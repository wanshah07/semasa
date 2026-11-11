"""The dry run of every queued post (Wan, 11 Nov 2026)."""

from datetime import UTC, datetime, timedelta

import pytest

from semasa import preflight, senders


def _req(channel, text, pictures=(), video=None):
    return preflight.request_for(channel, text, list(pictures), video, "2026-11-12T05:00:00+00:00")


def _msgs(channel, body):
    return [m for _, m in preflight.check_request(channel, body)]


def test_the_failed_threads_caption_is_not_a_blocker_now_and_a_tag_only_post_is():
    cap = "Wanita 38 tahun kena kecederaan mata selepas HIFU.\n\n#KeselamatanProsedur"
    assert _msgs("threads", _req("threads", cap, ["https://x/1.jpg"])) == []
    bad = {"content": "Ayat.", "platforms": [{"platformSpecificData": {"threadItems": [
        {"content": "Ayat.", "mediaItems": []}, {"content": "#Tag", "mediaItems": []}]}}]}
    assert any("hashtags alone" in m for m in _msgs("threads", bad))
    empty = {"platforms": [{"platformSpecificData": {"threadItems": [{"content": "  ", "mediaItems": []}]}}]}
    assert any("no text and no picture" in m for m in _msgs("threads", empty))


def test_each_platform_rule():
    pics = [f"https://x/{i}.jpg" for i in range(11)]
    assert any("11 pictures" in m for m in _msgs("threads", _req("threads", "Ayat.", pics)))        # Threads: 10
    assert _msgs("instagram", _req("instagram", "Ayat.", pics)) == []                              # Instagram: 20
    assert any("needs a picture" in m for m in _msgs("instagram", _req("instagram", "Ayat.")))
    assert any("characters" in m for m in _msgs("instagram", _req("instagram", "a" * 2300, ["https://x/1.jpg"])))
    with pytest.raises(senders.SendError):                       # the sender itself refuses pictures on TikTok
        _req("tiktok", "Ayat.", ["https://x/1.jpg"])
    film = {"url": "https://x/f.mp4", "vertical": True}
    assert _msgs("tiktok", _req("tiktok", "Ayat.", video=film)) == []
    assert any("not https" in m for m in _msgs("facebook", _req("facebook", "Ayat.", ["http://x/1.jpg"])))
    assert _msgs("linkedin", _req("linkedin", "Ayat.")) == []                                       # text-only is fine here


def test_a_duplicate_on_one_channel_and_too_many_in_a_day():
    t0 = datetime(2026, 11, 12, 0, tzinfo=UTC)
    rows = [{"label": "a", "channel": "linkedin", "due": t0, "text": "Same words."},
            {"label": "b", "channel": "linkedin", "due": t0 + timedelta(days=3), "text": "Same words."},
            {"label": "c", "channel": "linkedin", "due": t0 + timedelta(days=4), "text": "Other words."}]
    out = preflight.queue_findings(rows)
    assert [(f["label"], f["level"]) for f in out] == [("b", "block")]
    many = [{"label": f"t{i}", "channel": "tiktok", "due": t0 + timedelta(minutes=i), "text": f"w{i}"} for i in range(16)]
    assert any(f["level"] == "warn" and "16 posts" in f["message"] for f in preflight.queue_findings(many))
