"""TikTok takes upright 9:16 (Wan, 20 Nov 2026: "fix ratio tiktok for film come from hermes nous, and for now no motion from
approved post for tiktok unless I request for it").

  1. a film of another shape (Hermes / Nexabot: 16:9) goes to TikTok as an upright 1080x1920 copy, the others get the film as is;
  2. a film already 9:16 is left alone and nothing is copied; a second send of the same film reuses the copy;
  3. when the copy cannot be made, TikTok gets nothing (never a landscape film);
  4. an approved film no longer rides to TikTok by itself: only a post that already holds a TikTok record, or the setting
     `channels.zernio.tiktok_with_film`, sends it there.
"""
import subprocess

import pytest

from semasa import publisher, senders, tiktok_ratio, video, zernio_publish

REAL = tiktok_ratio.for_tiktok      # conftest replaces the module's attribute for every other test


def _ff():
    imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


def _clip(path, size):
    ff = _ff()
    cmd = [ff, "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=10:duration=2", "-f", "lavfi", "-i", "sine=duration=2",
           "-shortest", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)
    return path


def _fetcher(src):
    def fetch(url, dest):
        dest.write_bytes(src.read_bytes())
        return dest
    return fetch


class Bucket:
    def __init__(self, store):
        self.store = store

    def get_public_url(self, path):
        return f"https://cdn.test/{path}"

    def upload(self, path, data, opts):
        self.store.uploaded.append((path, len(data), opts))

    def download(self, path):
        raise AssertionError("not used")


class Store:
    def __init__(self):
        self.uploaded = []
        store = self

        class _Storage:
            @staticmethod
            def from_(bucket):
                return Bucket(store)
        self.storage = _Storage()


def test_the_shape_rule_is_nine_by_sixteen_within_three_per_cent():
    assert tiktok_ratio.is_nine_sixteen(1080, 1920) and tiktok_ratio.is_nine_sixteen(720, 1280)
    assert not tiktok_ratio.is_nine_sixteen(1280, 720)          # Nexabot's web route
    assert not tiktok_ratio.is_nine_sixteen(1080, 1350)         # 4:5 is upright but not 9:16
    assert not tiktok_ratio.is_nine_sixteen(0, 0)


def test_a_landscape_film_gets_an_upright_copy_and_is_uploaded_once(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", "320x180")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    monkeypatch.setattr(tiktok_ratio, "_exists", lambda url: False)
    monkeypatch.setattr(tiktok_ratio, "_download", _fetcher(src))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/wide.mp4", "vertical": False})
    assert got["vertical"] is True and got["url"].startswith("https://cdn.test/tiktok/") and got["url"].endswith(".mp4")
    (path, size, opts), = store.uploaded
    assert path.startswith("tiktok/") and size > 10_000 and opts["content-type"] == "video/mp4"


def test_the_upright_copy_is_1080_by_1920(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", "320x180")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    out = tiktok_ratio.vertical_copy(src, tmp_path / "up.mp4")
    assert tiktok_ratio.size_of(out) == (1080, 1920)


def test_a_nine_sixteen_film_is_left_alone(tmp_path, monkeypatch):
    src = _clip(tmp_path / "up.mp4", "180x320")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    monkeypatch.setattr(tiktok_ratio, "_exists", lambda url: False)
    monkeypatch.setattr(tiktok_ratio, "_download", _fetcher(src))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/up.mp4"})
    assert got["url"] == "https://hermes.test/up.mp4" and got["vertical"] is True and store.uploaded == []


def test_a_second_send_reuses_the_copy(monkeypatch):
    monkeypatch.setattr(tiktok_ratio, "_exists", lambda url: True)
    monkeypatch.setattr(tiktok_ratio, "_download", lambda url, dest: pytest.fail("converted twice"))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/wide.mp4"})
    assert got["url"].startswith("https://cdn.test/tiktok/") and store.uploaded == []


def test_when_the_copy_cannot_be_made_tiktok_gets_nothing(monkeypatch):
    monkeypatch.setattr(tiktok_ratio, "_exists", lambda url: False)

    def boom(url, dest):
        raise RuntimeError("the film is gone")
    monkeypatch.setattr(tiktok_ratio, "_download", boom)
    with pytest.raises(senders.SendError) as exc:
        REAL(Store(), {"url": "https://hermes.test/wide.mp4"})
    assert exc.value.kind == "transient" and "upright copy" in exc.value.message


def test_hermes_publish_sends_tiktok_the_upright_copy_and_the_others_the_film(monkeypatch):
    sent = []

    class Hub:
        def create_video(self, account, channel, caption, film, due):
            sent.append((channel, film["url"]))
            return {"id": f"id-{channel}", "status": "scheduled"}

    zcfg = {"enabled": True, "accounts": {c: {"id": f"a-{c}", "key": "1"} for c in ("instagram", "tiktok")},
            "formats": {"instagram": ["video"], "tiktok": ["video"]}}
    monkeypatch.setattr(zernio_publish, "load_settings", lambda store: {"channels": {"zernio": zcfg}})
    monkeypatch.setattr(zernio_publish, "zernio_hub", lambda cfg: Hub())
    monkeypatch.setattr(tiktok_ratio, "for_tiktok", lambda store, film: {**film, "url": "https://cdn.test/tiktok/up.mp4"})
    out = zernio_publish.run(object(), "https://hermes.test/wide.mp4", ["instagram", "tiktok"], {"tiktok": "x", "instagram": "y"})
    assert sent == [("instagram", "https://hermes.test/wide.mp4"), ("tiktok", "https://cdn.test/tiktok/up.mp4")]
    assert out["tiktok"]["status"] == "scheduled"


def test_hermes_publish_fails_only_tiktok_when_the_copy_fails(monkeypatch):
    sent = []

    class Hub:
        def create_video(self, account, channel, caption, film, due):
            sent.append(channel)
            return {"id": "x", "status": "scheduled"}

    zcfg = {"enabled": True, "accounts": {c: {"id": f"a-{c}", "key": "1"} for c in ("instagram", "tiktok")},
            "formats": {"instagram": ["video"], "tiktok": ["video"]}}
    monkeypatch.setattr(zernio_publish, "load_settings", lambda store: {"channels": {"zernio": zcfg}})
    monkeypatch.setattr(zernio_publish, "zernio_hub", lambda cfg: Hub())

    def refuse(store, film):
        raise senders.SendError("transient", "tiktok: the upright copy of the film could not be made (x)")
    monkeypatch.setattr(tiktok_ratio, "for_tiktok", refuse)
    out = zernio_publish.run(object(), "https://hermes.test/wide.mp4", ["tiktok", "instagram"], {})
    assert sent == ["instagram"] and "upright copy" in out["tiktok"]["error"]


# --- TikTok on request -------------------------------------------------------------------------------------------------

ZACC = {"enabled": True, "accounts": {c: {"id": f"a-{c}", "key": "1"} for c in ("instagram", "facebook", "tiktok")},
        "formats": {"instagram": ["video"], "facebook": ["video"], "tiktok": ["video"]}}


def _settings(**extra):
    return {"channels": {"zernio": {**ZACC, **extra}}}


def test_an_approved_film_no_longer_rides_to_tiktok_by_itself():
    post = {"stream": "regulab", "channels": ["instagram", "facebook"]}
    assert publisher.post_channels(_settings(), post, has_video=True) == ["instagram", "facebook"]
    assert publisher.post_channels(_settings(), post, has_video=None) == ["instagram", "facebook"]


def test_a_post_that_already_holds_a_tiktok_record_keeps_it():
    post = {"stream": "regulab", "channels": ["instagram"], "published": {"tiktok": {"id": "z", "status": "error"}}}
    assert publisher.post_channels(_settings(), post, has_video=True) == ["instagram", "tiktok"]       # a failed one is retried
    assert publisher.post_channels(_settings(), post, has_video=None) == ["instagram", "tiktok"]       # the tally counts it


def test_the_setting_brings_the_ride_along_back():
    post = {"stream": "regulab", "channels": ["instagram"]}
    assert publisher.post_channels(_settings(tiktok_with_film=True), post, has_video=True) == ["instagram", "tiktok"]
    assert publisher.post_channels(_settings(tiktok_with_film=True), post, has_video=False) == ["instagram"]
