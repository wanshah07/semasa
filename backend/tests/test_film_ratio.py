"""A film is posted in the shape its platform takes (Wan, 20 Nov 2026: "fix all import film especially from hermes nous, so before
post make sure follow platform ratio which is already set in semasa"), and TikTok is on request only.

  1. the shape is Semasa's own per-stream table (motion.PLATFORM_SIZE): ws.regulab upright 9:16, LinkedIn square 1:1;
  2. a film of another shape (Hermes / Nexabot: 16:9) is fitted over a blurred copy of itself; a film already in the shape is left
     alone and nothing is copied; a second send of the same film reuses the copy;
  3. when the copy cannot be made the film is not sent in the wrong shape;
  4. the import worker, the publisher and Hermes's zernio_publish all do it;
  5. an approved film no longer rides to TikTok by itself: only a post that asked for it, one that already holds a TikTok
     record, or the setting `channels.zernio.tiktok_with_film`, sends it there.
"""
import subprocess

import pytest

from semasa import film_ratio, motion, publisher, senders, video, zernio_publish

REAL = film_ratio.for_stream      # conftest replaces the module's attribute for every other test
PORTRAIT, SQUARE = (1080, 1920), (1080, 1080)


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


def test_the_shape_follows_the_streams_own_table():
    assert film_ratio.size_for("regulab") == PORTRAIT and film_ratio.size_for(None) == PORTRAIT
    assert film_ratio.size_for("linkedin") == SQUARE
    assert motion.PLATFORM_SIZE == {"regulab": "portrait", "linkedin": "square"}      # the table it reads


def test_the_shape_rule_is_within_three_per_cent():
    assert film_ratio.fits(1080, 1920, PORTRAIT) and film_ratio.fits(720, 1280, PORTRAIT)
    assert not film_ratio.fits(1280, 720, PORTRAIT)          # Nexabot's web route
    assert not film_ratio.fits(1080, 1350, PORTRAIT)         # 4:5 is upright but not 9:16
    assert not film_ratio.fits(0, 0, PORTRAIT)
    assert film_ratio.fits(1080, 1080, SQUARE) and film_ratio.fits(720, 730, SQUARE)
    assert not film_ratio.fits(1080, 1920, SQUARE)


def test_a_landscape_film_gets_an_upright_copy_and_is_uploaded_once(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", "320x180")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    monkeypatch.setattr(film_ratio, "_exists", lambda url: False)
    monkeypatch.setattr(film_ratio, "_download", _fetcher(src))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/wide.mp4", "vertical": False}, "regulab")
    assert got["vertical"] is True and (got["width"], got["height"]) == PORTRAIT
    assert got["url"].startswith("https://cdn.test/ratio/1080x1920/") and got["url"].endswith(".mp4")
    (path, size, opts), = store.uploaded
    assert path.startswith("ratio/1080x1920/") and size > 10_000 and opts["content-type"] == "video/mp4"


def test_a_linkedin_film_is_fitted_square(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", "320x180")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    monkeypatch.setattr(film_ratio, "_exists", lambda url: False)
    monkeypatch.setattr(film_ratio, "_download", _fetcher(src))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/wide.mp4"}, "linkedin")
    assert (got["width"], got["height"]) == SQUARE and got["vertical"] is False
    assert store.uploaded[0][0].startswith("ratio/1080x1080/")


def test_the_copy_is_exactly_the_platform_frame(tmp_path, monkeypatch):
    src = _clip(tmp_path / "wide.mp4", "320x180")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    assert film_ratio.size_of(film_ratio.fit_copy(src, tmp_path / "up.mp4", PORTRAIT)) == PORTRAIT
    assert film_ratio.size_of(film_ratio.fit_copy(src, tmp_path / "sq.mp4", SQUARE)) == SQUARE


def test_a_film_already_in_the_shape_is_left_alone(tmp_path, monkeypatch):
    src = _clip(tmp_path / "up.mp4", "180x320")
    monkeypatch.setattr(video, "ffmpeg", _ff)
    monkeypatch.setattr(film_ratio, "_exists", lambda url: False)
    monkeypatch.setattr(film_ratio, "_download", _fetcher(src))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/up.mp4"}, "regulab")
    assert got["url"] == "https://hermes.test/up.mp4" and got["vertical"] is True and store.uploaded == []


def test_a_known_size_is_judged_without_a_download(monkeypatch):
    monkeypatch.setattr(film_ratio, "_download", lambda url, dest: pytest.fail("downloaded a film whose size is known"))
    store = Store()
    got = REAL(store, {"url": "https://cdn.test/m.mp4", "width": 1080, "height": 1920}, "regulab")
    assert got["url"] == "https://cdn.test/m.mp4" and store.uploaded == []


def test_a_second_send_reuses_the_copy(monkeypatch):
    monkeypatch.setattr(film_ratio, "_exists", lambda url: True)
    monkeypatch.setattr(film_ratio, "_download", lambda url, dest: pytest.fail("converted twice"))
    store = Store()
    got = REAL(store, {"url": "https://hermes.test/wide.mp4"}, "regulab")
    assert got["url"].startswith("https://cdn.test/ratio/1080x1920/") and store.uploaded == []


def test_when_the_copy_cannot_be_made_the_film_is_not_sent(monkeypatch):
    monkeypatch.setattr(film_ratio, "_exists", lambda url: False)

    def boom(url, dest):
        raise RuntimeError("the film is gone")
    monkeypatch.setattr(film_ratio, "_download", boom)
    with pytest.raises(senders.SendError) as exc:
        REAL(Store(), {"url": "https://hermes.test/wide.mp4"}, "regulab")
    assert exc.value.kind == "transient" and "fitted to 1080x1920" in exc.value.message


def _hub(sent):
    class Hub:
        def create_video(self, account, channel, caption, film, due):
            sent.append((channel, film["url"]))
            return {"id": f"id-{channel}", "status": "scheduled"}
    return Hub()


def _hermes(monkeypatch, sent):
    zcfg = {"enabled": True, "accounts": {c: {"id": f"a-{c}", "key": "1"} for c in ("instagram", "tiktok")},
            "formats": {"instagram": ["video"], "tiktok": ["video"]}}
    monkeypatch.setattr(zernio_publish, "load_settings", lambda store: {"channels": {"zernio": zcfg}})
    monkeypatch.setattr(zernio_publish, "zernio_hub", lambda cfg: _hub(sent))


def test_hermes_publish_sends_every_channel_the_fitted_film_made_once(monkeypatch):
    sent, asked = [], []
    _hermes(monkeypatch, sent)

    def fit(store, film, stream):
        asked.append(stream)
        return {**film, "url": "https://cdn.test/ratio/1080x1920/up.mp4"}
    monkeypatch.setattr(film_ratio, "for_stream", fit)
    out = zernio_publish.run(object(), "https://hermes.test/wide.mp4", ["instagram", "tiktok"], {"tiktok": "x", "instagram": "y"})
    assert sent == [("instagram", "https://cdn.test/ratio/1080x1920/up.mp4"), ("tiktok", "https://cdn.test/ratio/1080x1920/up.mp4")]
    assert asked == ["regulab"], "the copy is made once for all the channels"
    assert out["tiktok"]["status"] == "scheduled"


def test_hermes_publish_sends_nothing_in_the_wrong_shape_when_the_copy_fails(monkeypatch):
    sent = []
    _hermes(monkeypatch, sent)

    def refuse(store, film, stream):
        raise senders.SendError("transient", "the film could not be fitted to 1080x1920 (x)")
    monkeypatch.setattr(film_ratio, "for_stream", refuse)
    out = zernio_publish.run(object(), "https://hermes.test/wide.mp4", ["tiktok", "instagram"], {})
    assert sent == [] and all("fitted" in out[c]["error"] for c in ("tiktok", "instagram"))


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


def _cats(monkeypatch, sent, extra=True):
    """settings with the cat series' own TikTok account as an extra (Wan, 22 Nov 2026), beside the main TikTok."""
    zcfg = {"enabled": True, "accounts": {c: {"id": f"a-{c}", "key": "1"} for c in ("instagram", "tiktok")},
            "formats": {"instagram": ["video"], "tiktok": ["video"]}}
    if extra:
        zcfg["extra"] = {"tiktok_cats": {"id": "6b02e881c90d45ebb59674bd", "key": "3", "platform": "tiktok", "label": "Cats"}}
    monkeypatch.setattr(zernio_publish, "load_settings", lambda store: {"channels": {"zernio": zcfg}})

    class Hub:
        def create_video(self, account, service, caption, film, due):
            sent.append((account, service, caption))
            return {"id": f"id-{account}", "status": "scheduled"}
    monkeypatch.setattr(zernio_publish, "zernio_hub", lambda cfg: Hub())
    monkeypatch.setattr(film_ratio, "for_stream", lambda store, film, stream: {**film, "url": "https://cdn.test/up.mp4"})


def test_the_cat_series_tiktok_is_its_own_account_on_the_tiktok_platform(monkeypatch):
    sent = []
    _cats(monkeypatch, sent)
    out = zernio_publish.run(object(), "https://x/f.mp4", ["tiktok_cats"], {"tiktok_cats": "Comot dan kawan-kawan"})
    assert sent == [("6b02e881c90d45ebb59674bd", "tiktok", "Comot dan kawan-kawan")], "its own account id, sent as TikTok"
    assert out["tiktok_cats"]["status"] == "scheduled"
    assert "tiktok" not in out, "the main TikTok is not touched"


def test_the_cat_series_account_takes_the_tiktok_caption_when_it_has_none_and_the_main_tiktok_is_unaffected(monkeypatch):
    sent = []
    _cats(monkeypatch, sent)
    zernio_publish.run(object(), "https://x/f.mp4", ["tiktok", "tiktok_cats"], {"tiktok": "Satu"})
    assert sent == [("a-tiktok", "tiktok", "Satu"), ("6b02e881c90d45ebb59674bd", "tiktok", "Satu")]


def test_an_extra_account_settings_does_not_hold_is_refused_not_guessed(monkeypatch):
    sent = []
    _cats(monkeypatch, sent, extra=False)
    out = zernio_publish.run(object(), "https://x/f.mp4", ["tiktok_cats"], {})
    assert sent == [] and "no Zernio account id" in out["tiktok_cats"]["error"]


def test_channel_names_are_checked_and_the_extra_accounts_stay_out_of_the_publishers_platforms():
    assert zernio_publish._channels("instagram,tiktok_cats") == ["instagram", "tiktok_cats"]
    for bad in ("threads", "linkedin", "tiktok cats", "x"):
        with pytest.raises(SystemExit):
            zernio_publish._channels(bad)
    zcfg = {"enabled": True, "accounts": {"tiktok": {"id": "t", "key": "3"}},
            "extra": {"tiktok_cats": {"id": "c", "key": "3", "platform": "tiktok"}, "no_platform": {"id": "z"}}}
    assert set(publisher.zernio_accounts(zcfg)) == {"tiktok"}, "the publisher's queue, tally and figures never see it"
    assert set(publisher.zernio_extra_accounts(zcfg)) == {"tiktok_cats"}
    assert publisher.zernio_extra_accounts({**zcfg, "enabled": False}) == {}
