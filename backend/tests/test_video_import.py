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
        pytest.skip("needs ffmpeg and ffprobe")  # the CI runner has neither on PATH; the repo's other video tests skip the same way
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
                "channels": ["instagram", "facebook", "threads"],
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
        post["stream"] == "regulab" and post["lang"] == "bm" and sorted(post["channels"]) == ["facebook", "instagram", "threads"]
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
    assert told == ["Video import siap, menunggu lulus: Notifikasi kosmetik (2026-11-18 08:00, instagram, facebook, threads)"]
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


def test_a_silent_h264_film_needs_no_copy_and_a_wide_one_only_warns(clips):
    store, bucket = setup()
    received(store, bucket, clips["silent"])
    received(store, bucket, clips["wide"])
    step(store, bucket)
    posts = store.tables["semasa_posts"]
    assert len(posts) == 2 and all(m["meta"]["compressed"] is False for m in store.tables["media_generations"])
    wide = next(p for p in posts if any("not upright" in f["msg"] for f in p["flags"]))
    assert wide["hard_flags"] == 0 and wide["status"] == "draft"
    assert {p["slot"] for p in posts} == {"08:00", "13:00"} or len({(p["date"], p["slot"]) for p in posts}) == 2, (
        "one post to a slot"
    )


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
    iid = received(store, bucket, clips["good"], caption="", title="Video tanpa kapsyen")
    step(store, bucket)
    post = store.tables["semasa_posts"][0]
    assert post["status"] == "draft" and post["text"] == {"bm": {}} and post["hook"] == "Video tanpa kapsyen"
    assert post["hard_flags"] >= 1 and any("no caption" in f["msg"] for f in post["flags"] if f["hard"])
    assert "no caption" in row(store, iid)["note"]


def test_a_caption_per_channel_is_kept_exactly(clips):
    store, bucket = setup()
    caps = {"instagram": GOOD_BM, "threads": "Notifikasi NPRA sebelum jual."}
    received(store, bucket, clips["good"], caption=caps, channels=["instagram", "threads"])
    step(store, bucket)
    post = store.tables["semasa_posts"][0]
    assert post["text"]["bm"] == caps and sorted(post["channels"]) == ["instagram", "threads"]


def test_a_linkedin_import_is_english_and_a_malay_caption_is_a_flagged_draft(clips):
    store, bucket = setup()
    ok = received(store, bucket, clips["good"], stream="linkedin", lang="en", channels=["linkedin"], caption=GOOD_EN)
    bad = received(store, bucket, clips["good"], stream="linkedin", lang="en", channels=["linkedin"], caption=LONG_BM)
    step(store, bucket)
    assert row(store, ok)["status"] == "done" and row(store, bad)["status"] == "done"
    flagged = next(p for p in store.tables["semasa_posts"] if p["id"] == row(store, bad)["post_id"])
    assert flagged["status"] == "draft" and flagged["hard_flags"] > 0
    assert any("Bahasa Malaysia" in f["msg"] for f in flagged["flags"] if f["hard"])
    post = next(p for p in store.tables["semasa_posts"] if p["id"] == row(store, ok)["post_id"])
    assert post["hard_flags"] == 0
    assert (
        post["stream"] == "linkedin" and post["lang"] == "en" and post["channels"] == ["linkedin"] and post["status"] == "draft"
    )
    assert (post["date"], post["slot"]) == ("2026-11-18", "06:00"), "LinkedIn's own slots"


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
