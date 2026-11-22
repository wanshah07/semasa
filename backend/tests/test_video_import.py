"""Import video (Wan, 17 Nov 2026): an MP4 made outside Semasa becomes a DRAFT post and nothing more. Real tiny MP4s made with
ffmpeg; no network, no Telegram, no storage: the bucket is a dict."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fakestore import FakeStore

from semasa import motion, video_import

NOW = datetime(2026, 11, 17, 2, 0, tzinfo=UTC)  # 10:00 Tue 17 Nov 2026, Malaysia
GOOD_BM = (
    "Notifikasi produk kosmetik di NPRA mesti siap sebelum produk dijual. "
    "Peraturan 7 Peraturan Kawalan Dadah dan Kosmetik 1984 menetapkannya."
)
GOOD_EN = (
    "A cosmetic product must be notified to NPRA before it is sold. "
    "Regulation 7 of the Control of Drugs and Cosmetics Regulations 1984 sets that out."
)
LONG_BM = (
    "Produk kosmetik yang akan dijual mesti dinotifikasi kepada NPRA sebelum produk itu dipasarkan. "
    "Syarikat boleh membuat pendaftaran "
    "dengan sistem Quest3+ kerana tidak ada cara lain untuk produk ini."
)
SETTINGS = {"brand": {"regulab": {"slots": ["08:00", "13:00", "21:00"]}, "linkedin": {"slots": ["06:00", "19:00"]}}}
PLAIN_TOKEN = "smi_" + "ab" * 24


def ffmpeg(tmp_path, name, *args):
    out = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(out)], check=True, capture_output=True, timeout=120)
    return out.read_bytes()


@pytest.fixture(scope="module")
def clips(tmp_path_factory):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        # the CI runner has neither on PATH; the repo's other video tests skip the same way
        pytest.skip("needs ffmpeg and ffprobe")
    tmp = tmp_path_factory.mktemp("clips")
    src = ["-f", "lavfi", "-i", "testsrc=size=270x480:rate=10:duration=2", "-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    return {
        # already what the platforms take: H.264, yuv420p, AAC
        "good": ffmpeg(tmp, "good.mp4", *src, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"),
        # an MP4 the platforms would refuse: MPEG-4 part 2 video, so a copy must be made
        "old": ffmpeg(tmp, "old.mp4", *src, "-c:v", "mpeg4", "-c:a", "aac", "-shortest"),
        # a picture with no sound is fine
        "silent": ffmpeg(
            tmp,
            "silent.mp4",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=270x480:rate=10:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ),
        # landscape
        "wide": ffmpeg(
            tmp,
            "wide.mp4",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=480x270:rate=10:duration=2",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ),
        # 100 s: over the 90 s a short film may be
        "long": ffmpeg(
            tmp,
            "long.mp4",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=64x64:rate=2:duration=100",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ),
        # an MP4 container with sound only
        "audio": ffmpeg(tmp, "audio.mp4", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac"),
    }


class Bucket:
    """The public bucket as a dict: path to bytes."""

    def __init__(self, files=None):
        self.files = dict(files or {})
        self.removed: list[str] = []

    def download(self, path):
        return self.files[path]

    def upload(self, path, data, content_type):
        self.files[path] = data
        return f"https://bucket.test/{path}"

    def url(self, path):
        return f"https://bucket.test/{path}"

    def remove(self, paths):
        self.removed += list(paths)
        for p in paths:
            self.files.pop(p, None)


def received(store, bucket, data, **params):
    """A row the Edge Function would have written, with its file already in the bucket."""
    iid = f"imp{len(store.tables.get('semasa_video_imports', [])) + 1}"
    path = f"imports/{iid}.mp4"
    bucket.files[path] = data
    store.tables.setdefault("semasa_video_imports", []).append(
        {
            "id": iid,
            "status": "received",
            "token_id": "tok1",
            "token_label": "hermes",
            "source": "hermes",
            "idempotency_key": "k-" + iid,
            "source_url": "",
            "stored_path": path,
            "bytes": len(data),
            "attempts": 0,
            "created_at": "2026-11-17T01:59:00+00:00",
            "params": {
                "stream": "regulab",
                "lang": "bm",
                "channels": ["instagram", "facebook"],
                "caption": GOOD_BM,
                "title": "Notifikasi kosmetik",
                "date": "",
                "slot": "",
                **params,
            },
        }
    )
    return iid


def setup():
    store = FakeStore(semasa_settings=[{"key": k, "value": v} for k, v in SETTINGS.items()])
    return store, Bucket()


def step(store, bucket, **kw):
    told: list[str] = []
    out = video_import.run(store, SETTINGS, NOW, storage=bucket, notify=lambda s, text: told.append(text), **kw)
    return out, told


def row(store, iid):
    return next(r for r in store.tables["semasa_video_imports"] if r["id"] == iid)


def test_a_good_video_becomes_a_draft_post_and_is_never_approved(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"])
    out, told = step(store, bucket)
    assert out == "1 import(s) drafted"
    r = row(store, iid)
    assert r["status"] == "done" and r["error"] == "" and r["post_id"] and r["motion_id"]
    posts = store.tables["semasa_posts"]
    assert len(posts) == 1
    post = posts[0]
    assert post["status"] == "draft", "the gate is Wan's Approve click"
    assert not any(p["status"] in ("approved", "scheduled", "posted") for p in posts)
    assert "approved_by" not in post and "approved_at" not in post and post["created_by"] is None
    assert (post["date"], post["slot"]) == ("2026-11-18", "08:00"), "the next free slot, from tomorrow"
    assert (
        post["stream"] == "regulab" and post["lang"] == "bm" and sorted(post["channels"]) == ["facebook", "instagram"]
    )
    assert post["text"]["bm"]["instagram"] == GOOD_BM and post["hard_flags"] == 0
    media = store.tables["media_generations"]
    assert len(media) == 1 and post["media_ids"] == [media[0]["id"]] and media[0]["post_id"] == post["id"]
    assert media[0]["type"] == "video" and media[0]["meta"]["flow"] == "import" and media[0]["meta"]["compressed"] is False
    assert media[0]["generated_media_url"] == f"https://bucket.test/imports/{iid}.mp4"
    film = store.tables["semasa_motions"][0]
    assert film["status"] == "done" and film["options"]["template"] == "import" and film["options"]["via"] == "import"
    assert film["options"]["import"]["source"] == "hermes" and film["options"]["import"]["token_label"] == "hermes"
    assert (
        film["queued_post_id"] == post["id"] and film["width"] == 270 and film["height"] == 480 and 1.5 < film["duration_s"] < 2.5
    )
    assert told == ["Video import siap, menunggu lulus: Notifikasi kosmetik (2026-11-18 08:00, instagram, facebook)"]
    assert any(f"imports/{iid}.jpg" in p for p in bucket.files), "a poster frame is kept"


def test_a_file_the_platforms_would_refuse_gets_the_motion_platform_copy(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["old"])
    step(store, bucket)
    m = store.tables["media_generations"][0]
    assert m["meta"]["compressed"] is True and m["generated_media_url"].endswith(f"imports/{iid}-social.mp4")
    assert m["reference_url"].endswith(f"imports/{iid}.mp4")
    copy = bucket.files[f"imports/{iid}-social.mp4"]
    assert copy[4:8] == b"ftyp" and b"avc1" in copy[:4096] + copy[-4096:] or b"avc1" in copy, "the copy is H.264"
    assert "platform copy" in row(store, iid)["note"]


def test_a_silent_h264_film_needs_no_copy(clips):
    store, bucket = setup()
    received(store, bucket, clips["silent"])
    step(store, bucket)
    (post,) = store.tables["semasa_posts"]
    assert store.tables["media_generations"][0]["meta"]["compressed"] is False and post["hard_flags"] == 0


def test_a_wide_film_is_fitted_to_the_streams_shape_before_the_draft_not_just_warned_about(clips):
    # Wan, 20 Nov 2026: a film from Hermes / Nous follows the platform ratio already set in Semasa
    store, bucket = setup()
    iid = received(store, bucket, clips["wide"])
    step(store, bucket)
    (post,) = store.tables["semasa_posts"]
    m = store.tables["media_generations"][0]
    assert m["meta"]["compressed"] is True and m["generated_media_url"].endswith(f"imports/{iid}-social.mp4")
    assert (m["meta"]["width"], m["meta"]["height"]) == (1080, 1920), "the media row is what is posted"
    assert m["reference_url"].endswith(f"imports/{iid}.mp4"), "the sender's own file is kept"
    assert not any("not upright" in f["msg"] for f in post["flags"]), "nothing left to warn about"
    assert post["hard_flags"] == 0 and post["status"] == "draft"
    film = store.tables["semasa_motions"][0]
    assert (film["width"], film["height"]) == (1080, 1920) and film["resolution"] == "portrait"
    assert "fitted from" in row(store, iid)["note"] and "1080x1920" in row(store, iid)["note"]


def test_a_linkedin_film_is_refused_a_film_goes_only_to_instagram_facebook_and_tiktok(clips):
    # Wan, 22 Nov 2026: "Make sure film and motion only for ig reel, facebook and tiktok"
    store, bucket = setup()
    iid = received(store, bucket, clips["wide"], stream="linkedin", lang="en", channels=["linkedin"], caption=GOOD_EN)
    step(store, bucket)
    r = row(store, iid)
    assert r["status"] == "error" and "Instagram (Reel), Facebook and TikTok" in r["error"]
    assert not store.tables.get("semasa_posts")


def test_a_film_asked_for_threads_goes_to_instagram_and_facebook_and_tiktok_only_when_asked(clips):
    store, bucket = setup()
    received(store, bucket, clips["good"], channels=["threads"])
    received(store, bucket, clips["good"], channels=["instagram", "threads", "tiktok"])
    step(store, bucket)
    a, b = store.tables["semasa_posts"]
    assert sorted(a["channels"]) == ["facebook", "instagram"], "Threads is never a film's platform: the defaults instead"
    assert b["channels"] == ["instagram", "tiktok"]


def test_an_upright_film_is_not_refitted(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"])
    step(store, bucket)
    assert f"imports/{iid}-social.mp4" not in bucket.files and "fitted" not in row(store, iid)["note"]


def test_a_file_that_is_not_an_mp4_is_refused_with_a_reason_and_deleted(clips):
    store, bucket = setup()
    iid = received(store, bucket, b"\x00\x00\x00\x18" + b"not an mp4 at all" * 40)
    out, told = step(store, bucket)
    r = row(store, iid)
    assert out == "1 import(s) refused" and r["status"] == "error" and "not an MP4" in r["error"] and r["stored_path"] == ""
    assert f"imports/{iid}.mp4" in bucket.removed and not bucket.files, "a refused file is not left in a public bucket"
    assert not store.tables.get("semasa_posts") and not store.tables.get("semasa_motions") and not told


def test_an_mp4_with_only_sound_is_refused(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["audio"])
    step(store, bucket)
    assert row(store, iid)["status"] == "error" and "no picture" in row(store, iid)["error"]


def test_a_file_longer_than_the_channels_take_is_refused_with_the_limit(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["long"])
    step(store, bucket)
    r = row(store, iid)
    assert r["status"] == "error" and "100" in r["error"] and "90 s" in r["error"] and "Instagram" in r["error"]
    assert not store.tables.get("semasa_posts")


def test_a_file_too_big_even_after_the_copy_is_refused(clips, monkeypatch):
    store, bucket = setup()
    monkeypatch.setattr(
        video_import, "LIMITS", {c: {"seconds": 90, "bytes": 2000} for c in ("instagram", "facebook", "threads", "linkedin")}
    )
    iid = received(store, bucket, clips["old"])
    step(store, bucket)
    r = row(store, iid)
    assert r["status"] == "error" and "even after compressing" in r["error"]
    assert not any(k.startswith("imports/") for k in bucket.files), "every file the try wrote is gone"


def test_a_file_over_the_stored_ceiling_is_refused(clips, monkeypatch):
    store, bucket = setup()
    monkeypatch.setattr(video_import, "MAX_FILE_BYTES", 1000)
    iid = received(store, bucket, clips["good"])
    step(store, bucket)
    assert "over" in row(store, iid)["error"] and "MB" in row(store, iid)["error"]


@pytest.mark.parametrize(
    "caption,needle",
    [
        ("Semak kelayakan produk anda di www.kkmhalalconsultant.com sekarang.", "website"),
        ("Komen SAHKAN di bawah untuk tahu lebih lanjut. " + GOOD_BM, "CTA"),
        ("Produk ini dijamin lulus NPRA, " + GOOD_BM, "approval"),
    ],
)
def test_a_caption_with_a_cta_or_the_website_is_a_flagged_draft_never_an_error_and_never_approved(clips, caption, needle):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"], caption=caption)
    told = step(store, bucket)[1]
    r = row(store, iid)
    assert r["status"] == "done" and r["error"] == "" and r["post_id"], "Wan decided: a bad caption is his to fix in the page"
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "draft" and post["id"] == r["post_id"]
    assert post["hard_flags"] > 0 and post["hard_flags"] == sum(1 for f in post["flags"] if f["hard"])
    assert any(f["hard"] and needle.lower() in f["msg"].lower() for f in post["flags"]), post["flags"]
    assert post["text"]["bm"]["instagram"] == caption, "the caption is kept exactly as sent, for Wan to edit"
    assert f"{post['hard_flags']} blocking flag(s) to fix" in r["note"]
    assert not any(p["status"] in ("approved", "scheduled", "posted") for p in store.tables["semasa_posts"])
    assert "approved_by" not in post and "approved_at" not in post
    assert len(store.tables["semasa_motions"]) == 1 and len(store.tables["media_generations"]) == 1
    assert "betulkan kapsyen" in told[0]


def test_a_bad_file_still_ends_in_error_while_a_bad_caption_does_not(clips):
    store, bucket = setup()
    bad_file = received(
        store, bucket, b"\x00\x00\x00\x18" + b"not an mp4" * 40, caption="Semak kelayakan di www.kkmhalalconsultant.com"
    )
    step(store, bucket)
    assert row(store, bad_file)["status"] == "error" and not store.tables.get("semasa_posts")


def test_a_link_in_the_caption_is_a_warning_on_the_draft_not_a_refusal(clips):
    store, bucket = setup()
    received(store, bucket, clips["good"], caption=GOOD_BM + " Rujuk https://www.npra.gov.my untuk senarai penuh.")
    step(store, bucket)
    post = store.tables["semasa_posts"][0]
    assert (
        post["status"] == "draft" and post["hard_flags"] == 0 and any(not f["hard"] and "link" in f["msg"] for f in post["flags"])
    )


def test_no_caption_is_a_draft_with_a_blocking_flag_for_wan_to_fill(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"], caption="", title="")  # a title would be written up (see below)
    step(store, bucket)
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "draft" and post["text"] == {"bm": {}} and post["hook"] == "Video import (hermes)"
    assert post["hard_flags"] >= 1 and any("no caption" in f["msg"] for f in post["flags"] if f["hard"])
    assert "no caption" in row(store, iid)["note"]


def test_a_caption_per_channel_is_kept_exactly(clips):
    store, bucket = setup()
    caps = {"instagram": GOOD_BM, "facebook": "Notifikasi NPRA sebelum jual."}
    received(store, bucket, clips["good"], caption=caps, channels=["instagram", "facebook"])
    step(store, bucket)
    post = store.tables["semasa_posts"][0]
    assert post["text"]["bm"] == caps and sorted(post["channels"]) == ["facebook", "instagram"]


def test_a_linkedin_import_is_refused_whatever_its_caption(clips):
    store, bucket = setup()
    ok = received(store, bucket, clips["good"], stream="linkedin", lang="en", channels=["linkedin"], caption=GOOD_EN)
    bad = received(store, bucket, clips["good"], stream="linkedin", lang="en", channels=["linkedin"], caption=LONG_BM)
    step(store, bucket)
    assert row(store, ok)["status"] == "error" and row(store, bad)["status"] == "error"
    assert not store.tables.get("semasa_posts"), "a film never becomes a LinkedIn post"


def test_the_next_free_slot_skips_what_is_held_and_a_taken_slot_asked_for_is_refused(clips):
    store, bucket = setup()
    store.tables["semasa_posts"] = [{"id": "held", "stream": "regulab", "date": "2026-11-18", "slot": "08:00", "status": "draft"}]
    a = received(store, bucket, clips["good"])
    b = received(store, bucket, clips["silent"], date="2026-11-18", slot="08:00")
    c = received(store, bucket, clips["silent"], date="2026-11-20", slot="13:00")
    step(store, bucket)
    posts = {p["id"]: p for p in store.tables["semasa_posts"]}
    assert (posts[row(store, a)["post_id"]]["date"], posts[row(store, a)["post_id"]]["slot"]) == ("2026-11-18", "13:00")
    assert row(store, b)["status"] == "error" and "already holds a post" in row(store, b)["error"]
    assert (posts[row(store, c)["post_id"]]["date"], posts[row(store, c)["post_id"]]["slot"]) == ("2026-11-20", "13:00")


def test_a_slot_in_the_past_or_not_a_slot_is_refused(clips):
    store, bucket = setup()
    past = received(store, bucket, clips["good"], date="2026-11-17", slot="08:00")
    odd = received(store, bucket, clips["good"], date="2026-11-20", slot="09:30")
    step(store, bucket)
    assert "already past" in row(store, past)["error"] and "not one of the regulab slots" in row(store, odd)["error"]


# ---- a link instead of a file -------------------------------------------------------------------------------------------------


class Resp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code, self.body, self.headers, self.closed = status, body, headers or {}, False

    def iter_content(self, chunk_size=1):
        yield self.body

    def close(self):
        self.closed = True


def public(host, port, proto=0):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def test_a_link_is_fetched_kept_in_the_bucket_and_made_a_draft(clips):
    store, bucket = setup()
    store.tables["semasa_video_imports"] = [
        {
            "id": "imp1",
            "status": "received",
            "token_label": "hermes",
            "source": "hermes",
            "source_url": "https://cdn.example.com/a.mp4",
            "stored_path": "",
            "attempts": 0,
            "created_at": "2026-11-17T01:00:00+00:00",
            "params": {"stream": "regulab", "channels": [], "caption": GOOD_BM, "title": "Dari pautan"},
        }
    ]
    calls = []

    def get(url, **k):
        calls.append(url)
        return Resp(200, clips["good"], {"content-type": "video/mp4"})

    out, _ = step(store, bucket, get=get, resolve=public)
    assert out == "1 import(s) drafted" and calls == ["https://cdn.example.com/a.mp4"]
    assert "imports/imp1.mp4" in bucket.files and store.tables["semasa_posts"][0]["status"] == "draft"
    assert store.tables["semasa_motions"][0]["video_url"] == "https://bucket.test/imports/imp1.mp4"


@pytest.mark.parametrize(
    "url,resolve,get,needle",
    [
        ("http://cdn.example.com/a.mp4", public, None, "https"),
        ("https://cdn.example.com/a.mp4", lambda *a, **k: [(2, 1, 6, "", ("10.0.0.5", 443))], None, "private network"),
        ("https://cdn.example.com/a.mp4", lambda *a, **k: [(2, 1, 6, "", ("169.254.169.254", 443))], None, "private network"),
        (
            "https://cdn.example.com/a.mp4",
            public,
            lambda u, **k: Resp(200, b"<html>", {"content-type": "text/html"}),
            "not a video",
        ),
        ("https://cdn.example.com/a.mp4", public, lambda u, **k: Resp(404), "404"),
        (
            "https://cdn.example.com/a.mp4",
            public,
            lambda u, **k: Resp(200, b"x", {"content-type": "video/mp4", "content-length": "999999999"}),
            "over",
        ),
    ],
)
def test_a_bad_link_is_refused(url, resolve, get, needle):
    with pytest.raises(video_import.Reject) as e:
        video_import.fetch_url(url, get=get or (lambda u, **k: Resp(200, b"x")), resolve=resolve)
    assert needle in str(e.value)


def test_a_redirect_to_a_private_address_is_refused():
    hops = {"https://cdn.example.com/a": Resp(302, headers={"location": "https://internal.example.com/b"})}

    def resolve(host, *a, **k):
        return [(2, 1, 6, "", ("192.168.1.9" if host == "internal.example.com" else "93.184.216.34", 443))]

    with pytest.raises(video_import.Reject) as e:
        video_import.fetch_url("https://cdn.example.com/a", get=lambda u, **k: hops[u], resolve=resolve)
    assert "private network" in str(e.value)


# ---- the step itself ----------------------------------------------------------------------------------------------------------


def test_a_failure_worth_trying_again_goes_back_and_ends_after_three_tries(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"])
    bucket.files.clear()  # the stored file cannot be read back
    for n in (1, 2):
        step(store, bucket)
        assert row(store, iid)["status"] == "received" and row(store, iid)["attempts"] == n
    step(store, bucket)
    assert row(store, iid)["status"] == "error" and "3 tries" in row(store, iid)["error"]


class Blink(FakeStore):
    """A database whose first insert of a post fails, after the film row and the media row were written."""

    fail = True

    def table(self, name):
        q = super().table(name)
        if name == "semasa_posts" and self.fail:
            real = q.execute

            def execute():
                if q.op == "insert":
                    self.fail = False
                    raise RuntimeError("the database blinked")
                return real()

            q.execute = execute
        return q


def test_a_retry_after_a_half_finished_try_reuses_the_film_row(clips):
    store, bucket = Blink(semasa_settings=[{"key": "brand", "value": SETTINGS["brand"]}]), Bucket()
    iid = received(store, bucket, clips["good"])
    step(store, bucket)
    assert row(store, iid)["status"] == "received" and row(store, iid)["motion_id"] and not store.tables.get("media_generations")
    step(store, bucket)
    assert row(store, iid)["status"] == "done"
    assert (
        len(store.tables["semasa_posts"]) == 1
        and len(store.tables["semasa_motions"]) == 1
        and len(store.tables["media_generations"]) == 1
    )


def test_a_half_made_film_row_is_reused_not_doubled(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"])
    store.tables["semasa_motions"] = [{"id": "m-old", "status": "done"}]
    row(store, iid)["motion_id"] = "m-old"
    step(store, bucket)
    assert (
        len(store.tables["semasa_motions"]) == 1
        and store.tables["semasa_motions"][0]["queued_post_id"] == row(store, iid)["post_id"]
    )


def test_a_dead_runners_import_is_put_back(clips):
    store, bucket = setup()
    iid = received(store, bucket, clips["good"])
    row(store, iid).update({"status": "working", "attempts": 1, "updated_at": "2026-11-17T00:00:00+00:00"})
    out, _ = step(store, bucket)
    assert out == "1 import(s) drafted"


def test_telegram_being_down_never_stops_the_draft(clips):
    store, bucket = setup()
    received(store, bucket, clips["good"])

    def down(s, text):
        raise RuntimeError("telegram is down")

    out = video_import.run(store, SETTINGS, NOW, storage=bucket, notify=down)
    assert out == "1 import(s) drafted" and store.tables["semasa_posts"][0]["status"] == "draft"


def test_the_step_never_raises_and_the_motion_hook_is_wired(clips, monkeypatch):
    assert video_import.run(SimpleNamespace(table=lambda n: (_ for _ in ()).throw(RuntimeError("down"))), {}, NOW) == "error"
    store, bucket = setup()
    received(store, bucket, clips["good"])
    seen = {}
    monkeypatch.setattr(video_import, "run", lambda st, settings, now: seen.setdefault("ran", True) and "1 import(s) drafted")
    assert motion.video_import_step(store, NOW) == "1 import(s) drafted" and seen["ran"]
    monkeypatch.setattr(video_import, "run", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    assert motion.video_import_step(store, NOW) == ""


def test_the_token_never_reaches_a_row_a_log_line_or_a_file(clips, caplog):
    """The worker never sees a token (the function keeps only a hash); this proves nothing it writes could carry one."""
    store, bucket = setup()
    received(store, bucket, clips["good"])
    received(store, bucket, b"junk" * 10)
    with caplog.at_level("DEBUG"):
        step(store, bucket)
    dump = json.dumps(store.tables, default=str) + caplog.text
    assert PLAIN_TOKEN not in dump and "smi_" not in dump


# ---- no caption sent: Semasa writes one from the title alone (Wan, 17 Nov 2026) ----------------------------------------------

TITLE = "a warm cup of Malaysian teh tarik on a wooden table, steam rising, cozy cafe"
WRITTEN = {
    "instagram": "Secawan teh tarik panas atas meja kayu, wapnya naik perlahan di kafe yang selesa.",
    "facebook": "Secawan teh tarik panas atas meja kayu di kafe yang selesa. Wap masih naik dari cawan.",
    "threads": "Teh tarik panas, meja kayu, kafe yang selesa.",
}
PLAIN = "A warm cup of Malaysian teh tarik on a wooden table, steam rising, cozy cafe."


class Writer:
    """The caption writer's model: records what it was asked, answers with `reply`."""

    def __init__(self, reply=None, boom=False):
        self.reply, self.boom, self.calls = reply, boom, []

    def chat_json(self, system, user, max_tokens=0):
        self.calls.append((system, user))
        if self.boom:
            raise RuntimeError("the model is down")
        return self.reply


def untitled(store, bucket, data, **params):
    return received(store, bucket, data, caption="", title=TITLE, **params)


def test_no_caption_sent_the_writer_writes_one_per_channel_from_the_title_only_and_the_draft_is_never_approved(clips):
    store, bucket = setup()
    llm = Writer({"captions": WRITTEN})
    iid = untitled(store, bucket, clips["good"])
    out, told = step(store, bucket, llm=llm)
    assert out == "1 import(s) drafted"
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "draft" and post["id"] == row(store, iid)["post_id"]
    assert not any(p["status"] in ("approved", "scheduled", "posted") for p in store.tables["semasa_posts"])
    assert "approved_by" not in post and "approved_at" not in post
    got = post["text"]["bm"]
    assert sorted(got) == ["facebook", "instagram"]
    assert got["instagram"] == WRITTEN["instagram"] and got["facebook"] == WRITTEN["facebook"]
    assert post["hard_flags"] == 0 and not any("no caption" in f["msg"] for f in post["flags"])
    assert any(not f["hard"] and "Semasa wrote this caption from the title only" in f["msg"] for f in post["flags"])
    assert any("written by Semasa from the title only" in d["action"] for d in post["decisions"])
    assert not any(d["by"] == "wan" for d in post["decisions"])
    note = row(store, iid)["note"]
    assert "Semasa wrote it from the title only" in note and "read it before approving" in note
    assert "Kapsyen ditulis oleh Semasa daripada tajuk sahaja" in told[0] and "betulkan" not in told[0]
    assert store.tables["semasa_motions"][0]["captions"] == got


def test_the_writer_is_given_nothing_but_the_title_and_the_source(clips):
    store, bucket = setup()
    llm = Writer({"captions": WRITTEN})
    untitled(store, bucket, clips["good"], date="", slot="")
    step(store, bucket, llm=llm)
    assert len(llm.calls) == 1
    system, user = llm.calls[0]
    assert user == f"TITLE: {TITLE}", "the brief is the sender's title and no scene, no script, no idea"
    assert "THIS FILM WAS MADE OUTSIDE SEMASA" in system and "Never invent anything" in system
    assert "hermes" in system and "is not named in the caption" in system
    assert "No call to action" in system and "Bahasa Malaysia" in system
    assert "GOOD_BM" not in system and "NPRA" not in user


@pytest.mark.parametrize(
    "bad",
    [
        "Jangan lupa follow kami untuk lagi teh tarik!",
        "Layari www.kkmhalalconsultant.com untuk menu penuh.",
        "Teh tarik ini dijamin lulus NPRA.",
        "Komen SAHKAN di bawah untuk tahu lebih lanjut.",
        "Teh tarik panas, 3 sudu gula dan 250 ml susu.",
        "Teh tarik ini halal dan selamat diminum.",
    ],
)
def test_a_writer_that_asks_promises_links_or_invents_falls_back_to_the_plain_caption(clips, bad):
    store, bucket = setup()
    iid = untitled(store, bucket, clips["good"])
    step(store, bucket, llm=Writer({"captions": {c: bad for c in WRITTEN}}))
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "draft" and post["hard_flags"] == 0
    assert set(post["text"]["bm"].values()) == {PLAIN}, post["text"]
    assert "plain caption from the title" in row(store, iid)["note"]
    assert any("Semasa wrote this caption from the title only" in f["msg"] for f in post["flags"])


def test_a_writer_that_is_down_or_missing_or_answers_nothing_falls_back_to_the_plain_caption(clips):
    for llm in (Writer(boom=True), None, Writer({"captions": "nothing"}), Writer({"captions": {}})):
        store, bucket = setup()
        untitled(store, bucket, clips["good"])
        step(store, bucket, llm=llm)
        post = store.tables["semasa_posts"][0]
        assert post["status"] == "draft" and set(post["text"]["bm"].values()) == {PLAIN}


def test_one_good_channel_is_kept_and_a_bad_one_is_plain(clips):
    store, bucket = setup()
    untitled(store, bucket, clips["good"])
    step(store, bucket, llm=Writer({"captions": {**WRITTEN, "facebook": "Follow kami untuk lagi!"}}))
    t = store.tables["semasa_posts"][0]["text"]["bm"]
    assert t["instagram"] == WRITTEN["instagram"] and t["facebook"] == PLAIN


def test_a_caption_the_sender_gave_is_never_touched_and_the_writer_is_never_asked(clips):
    store, bucket = setup()
    llm = Writer({"captions": WRITTEN})
    caps = {"instagram": GOOD_BM, "facebook": "Notifikasi NPRA sebelum jual."}
    received(store, bucket, clips["good"], caption=caps, channels=["instagram", "facebook"], title=TITLE)
    received(store, bucket, clips["good"], caption=GOOD_BM, title=TITLE)
    step(store, bucket, llm=llm)
    a, b = store.tables["semasa_posts"]
    assert a["text"]["bm"] == caps and b["text"]["bm"]["facebook"] == GOOD_BM
    assert llm.calls == []
    for p in (a, b):
        assert not any("Semasa wrote" in f["msg"] for f in p["flags"])
        assert not any("written by Semasa" in d["action"] for d in p["decisions"])


def test_a_per_channel_caption_sent_as_a_json_string_in_a_form_field_is_the_senders_own(clips):
    store, bucket = setup()
    llm = Writer({"captions": WRITTEN})
    caps = {"instagram": GOOD_BM, "facebook": "Notifikasi NPRA sebelum jual."}
    received(store, bucket, clips["good"], caption=json.dumps(caps), channels=["instagram", "facebook"], title=TITLE)
    step(store, bucket, llm=llm)
    assert store.tables["semasa_posts"][0]["text"]["bm"] == caps and llm.calls == []
    assert video_import.texts_of({"caption": '{"oops": "x"}'}, ["instagram"]) == {"instagram": '{"oops": "x"}'}
    assert video_import.texts_of({"caption": "{not json"}, ["instagram"]) == {"instagram": "{not json"}


def test_no_title_and_no_caption_is_the_old_flagged_draft_and_the_writer_is_not_asked(clips):
    store, bucket = setup()
    llm = Writer({"captions": WRITTEN})
    received(store, bucket, clips["good"], caption="", title="")
    step(store, bucket, llm=llm)
    post = store.tables["semasa_posts"][0]
    assert llm.calls == [] and post["text"] == {"bm": {}}
    assert any("no caption" in f["msg"] for f in post["flags"] if f["hard"])


def test_the_motion_hook_hands_its_llm_to_the_import_step(monkeypatch):
    seen = {}
    monkeypatch.setattr(video_import, "run", lambda st, settings, now, **kw: seen.update(kw) or "")
    llm = Writer({})
    motion.video_import_step(FakeStore(), NOW, llm)
    assert seen == {"llm": llm}


# ---- an import whose draft is gone ------------------------------------------------------------------------------------------


def lose_the_draft(store, iid):
    """What deleting the draft in the page leaves behind (supabase/087 and 051: both references are on delete set null)."""
    r = row(store, iid)
    store.tables["semasa_posts"] = [p for p in store.tables["semasa_posts"] if p["id"] != r["post_id"]]
    for m in store.tables["media_generations"]:
        if m.get("post_id") == r["post_id"]:
            m["post_id"] = None
    for f in store.tables["semasa_motions"]:
        if f["id"] == r["motion_id"]:
            f["queued_post_id"] = None
    r["post_id"] = None


def test_a_done_import_whose_draft_is_gone_gets_exactly_one_new_draft_with_written_captions(clips):
    store, bucket = setup()
    llm = Writer({"captions": WRITTEN})
    kept = received(store, bucket, clips["good"])
    gone = untitled(store, bucket, clips["good"])
    step(store, bucket, llm=Writer({"captions": {c: "Follow kami!" for c in WRITTEN}}))  # first made with the plain caption
    assert len(store.tables["semasa_posts"]) == 2
    lose_the_draft(store, gone)
    out, told = step(store, bucket, llm=llm)
    assert out == "1 draft(s) made again"
    posts = store.tables["semasa_posts"]
    assert len(posts) == 2, "one for the import that kept its draft, one made again"
    new = next(p for p in posts if p["id"] == row(store, gone)["post_id"])
    assert new["status"] == "draft" and not any(p["status"] != "draft" for p in posts)
    assert row(store, kept)["post_id"] and sum(1 for p in posts if p["id"] == row(store, kept)["post_id"]) == 1
    film = next(f for f in store.tables["semasa_motions"] if f["id"] == row(store, gone)["motion_id"])
    assert film["queued_post_id"] == new["id"] and len(store.tables["semasa_motions"]) == 2
    assert new["text"]["bm"]["instagram"] == PLAIN, "the captions the film already carried are kept, never rewritten"
    assert (new["date"], new["slot"]) not in {(p["date"], p["slot"]) for p in posts if p is not new}
    assert any("made again from the stored film" in d["action"] for d in new["decisions"])
    assert row(store, gone)["note"].startswith("[draft made again 2026-11-17]")
    assert len(told) == 1 and "dibuat semula sebagai draf" in told[0] and TITLE[:30] in told[0]
    # the second run finds nothing to do: once per import
    out, told = step(store, bucket, llm=llm)
    assert out == "" and told == [] and len(store.tables["semasa_posts"]) == 2


def test_the_recovered_draft_is_written_from_the_title_when_the_film_has_no_captions(clips):
    store, bucket = setup()
    iid = untitled(store, bucket, clips["good"])
    step(store, bucket)  # no writer: a plain caption
    lose_the_draft(store, iid)
    film = store.tables["semasa_motions"][0]
    film["captions"] = {}  # what the stored film of the first import looked like: nothing was written then
    step(store, bucket, llm=Writer({"captions": WRITTEN}))
    new = store.tables["semasa_posts"][0]
    assert new["status"] == "draft" and new["text"]["bm"]["instagram"] == WRITTEN["instagram"]
    assert any("Semasa wrote this caption" in f["msg"] for f in new["flags"])
    assert store.tables["semasa_motions"][0]["captions"]["facebook"] == WRITTEN["facebook"]


def test_an_import_older_than_seven_days_or_already_recovered_or_failed_is_left_alone(clips):
    store, bucket = setup()
    old = untitled(store, bucket, clips["good"])
    step(store, bucket)
    lose_the_draft(store, old)
    row(store, old)["created_at"] = "2026-11-09T01:00:00+00:00"  # 8 days
    assert video_import.recover_missing_drafts(store, SETTINGS, NOW) == 0 and not store.tables["semasa_posts"]
    row(store, old)["created_at"] = "2026-11-17T01:59:00+00:00"
    row(store, old)["note"] = "[draft made again 2026-11-16] x"
    assert video_import.recover_missing_drafts(store, SETTINGS, NOW) == 0 and not store.tables["semasa_posts"]
    row(store, old)["note"] = ""
    row(store, old)["status"] = "error"
    assert video_import.recover_missing_drafts(store, SETTINGS, NOW) == 0 and not store.tables["semasa_posts"]


def test_a_recovery_that_fails_is_never_tried_twice_and_never_raises(clips):
    store, bucket = Blink(semasa_settings=[{"key": "brand", "value": SETTINGS["brand"]}]), Bucket()
    store.fail = False
    iid = untitled(store, bucket, clips["good"])
    step(store, bucket)
    lose_the_draft(store, iid)
    store.fail = True  # the first post insert of the recovery blinks
    assert video_import.recover_missing_drafts(store, SETTINGS, NOW) == 0
    assert row(store, iid)["note"].startswith("[draft made again"), "marked before the draft: no loop"
    assert video_import.recover_missing_drafts(store, SETTINGS, NOW) == 0 and not store.tables["semasa_posts"]


def test_a_draft_made_again_from_an_old_import_is_fitted_to_the_streams_ratio(monkeypatch):
    # Wan, 21 Nov 2026: the film from Hermes / Nous follows each platform's ratio before it posts, drafts made again included
    from semasa import film_ratio
    asked = []

    def fake(store, film, stream):
        asked.append((film["url"], stream))
        return {**film, "url": "https://x/ratio/1080x1920/a.mp4", "width": 1080, "height": 1920}

    monkeypatch.setattr(film_ratio, "for_stream", fake)
    info = {"width": 1280, "height": 720, "duration_s": 15.0, "bytes": 4_000_000}
    out, url, size = video_import.fitted_for_recovery(None, "https://x/old.mp4", info, "regulab", "", 0)
    assert asked == [("https://x/old.mp4", "regulab")]
    assert (out["width"], out["height"]) == (1080, 1920) and url == "https://x/ratio/1080x1920/a.mp4" and size == 0
    upright = {"width": 1080, "height": 1920, "duration_s": 15.0, "bytes": 1}
    assert video_import.fitted_for_recovery(None, "https://x/ok.mp4", upright, "regulab", "u", 5) == (upright, "u", 5)
    assert len(asked) == 1, "a film already in shape is not touched"
    square = video_import.fitted_for_recovery(None, "https://x/sq.mp4", info, "linkedin", "", 0)
    assert (square[0]["width"], square[0]["height"]) == (1080, 1080), "LinkedIn is square"

    def boom(store, film, stream):
        raise RuntimeError("no ffmpeg")

    monkeypatch.setattr(film_ratio, "for_stream", boom)
    assert video_import.fitted_for_recovery(None, "https://x/old.mp4", info, "regulab", "s", 7) == (info, "s", 7)
