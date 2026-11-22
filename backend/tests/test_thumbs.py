"""Library thumbnails (Wan, 22 Nov 2026: "Fix what you recommend"): a small JPEG beside each stored picture, so a tile does not
download a 2 MB PNG. semasa/thumbs.py."""

import io
from datetime import UTC, datetime, timedelta

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import archive, db, housekeeping, thumbs

NOW = datetime(2026, 11, 22, 19, 47, tzinfo=UTC)
BASE = "https://x.supabase.co/storage/v1/object/public/semasa-generated/"


def _png(w, h, mode="RGBA"):
    buf = io.BytesIO()
    Image.new(mode, (w, h), (200, 30, 30, 128) if mode == "RGBA" else (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_the_thumbnail_path_is_derived_from_the_picture_and_back():
    assert thumbs.thumb_path("2026/11/a.png") == "thumbs/2026/11/a.png.jpg"
    assert thumbs.thumb_path("2026/11/a.JPG?x=1") == "thumbs/2026/11/a.JPG.jpg"
    assert thumbs.original_of("thumbs/2026/11/a.png.jpg") == "2026/11/a.png"
    assert thumbs.original_of("2026/11/a.png") == ""


@pytest.mark.parametrize("path", ["", None, "2026/11/film.mp4", "motion/storyboard/x/s1.jpg", "imports/v.jpg",
                                  "thumbs/2026/11/a.png.jpg", "2026/11/doc.pdf"])
def test_no_thumbnail_for_what_is_never_a_library_tile(path):
    assert thumbs.thumb_path(path) == ""


def test_a_thumbnail_is_a_jpeg_with_its_short_side_400_and_far_smaller():
    big = _png(1024, 1536)
    small = thumbs.make_thumb(big)
    im = Image.open(io.BytesIO(small))
    assert im.format == "JPEG" and im.size == (400, 600)
    assert len(small) < len(big)


def test_a_small_picture_is_never_enlarged_and_bytes_that_are_no_picture_make_none():
    im = Image.open(io.BytesIO(thumbs.make_thumb(_png(200, 100, "RGB"))))
    assert im.size == (200, 100)
    assert thumbs.make_thumb(b"not a picture") is None


def test_storing_a_picture_stores_its_thumbnail_and_a_video_or_failure_never_breaks_the_upload():
    store = FakeStore()
    url = db.upload_generated(store, "2026/11/a.png", _png(1024, 1024), "image/png")
    assert url == BASE + "2026/11/a.png"
    assert set(store.uploaded) == {"2026/11/a.png", "thumbs/2026/11/a.png.jpg"}
    db.upload_generated(store, "2026/11/b.mp4", b"video", "video/mp4")
    db.upload_generated(store, "2026/11/c.png", b"broken", "image/png")      # not decodable: the picture is still stored
    assert "2026/11/c.png" in store.uploaded and "thumbs/2026/11/c.png.jpg" not in store.uploaded
    assert "thumbs/2026/11/b.mp4.jpg" not in store.uploaded


def _media(mid, path, **extra):
    row = {"id": mid, "type": "image", "status": "done", "created_at": NOW.isoformat(), "generated_media_url": BASE + path,
           "meta": {}}
    row.update(extra)
    return row


def test_the_backfill_makes_only_the_missing_ones_and_counts_in_a_dry_run():
    rows = [_media("m1", "2026/11/a.png"), _media("m2", "2026/11/b.png"), _media("m3", "2026/11/c.mp4", type="video"),
            _media("m4", "2026/11/gone.png"), _media("m5", "2026/11/run.png", status="processing"),
            _media("m6", "", generated_media_url=None, meta={"slide_urls": [BASE + "2026/11/s1.jpg"]})]
    names = {"2026/11/a.png", "2026/11/b.png", "thumbs/2026/11/b.png.jpg", "2026/11/c.mp4", "2026/11/run.png", "2026/11/s1.jpg"}
    store = FakeStore(media_generations=rows)
    assert thumbs.backfill(store, names, dry=True) == {"found": 2, "made": 0, "bytes": 0}
    assert store.uploaded == {}
    got = []
    out = thumbs.backfill(store, names, dry=False, fetch=lambda u: got.append(u) or _png(800, 800))
    assert out["found"] == 2 and out["made"] == 2
    assert sorted(store.uploaded) == ["thumbs/2026/11/a.png.jpg", "thumbs/2026/11/s1.jpg.jpg"]
    assert sorted(got) == [BASE + "2026/11/a.png", BASE + "2026/11/s1.jpg"]


def test_the_backfill_stops_at_its_cap_and_a_failed_read_is_tried_next_run():
    rows = [_media(f"m{i}", f"2026/11/{i}.png") for i in range(5)]
    names = {f"2026/11/{i}.png" for i in range(5)}
    store = FakeStore(media_generations=rows)
    assert thumbs.backfill(store, names, dry=False, cap=2, fetch=lambda u: _png(500, 500))["made"] == 2
    store2 = FakeStore(media_generations=rows)
    assert thumbs.backfill(store2, names, dry=False)["made"] == 0           # the network refuses: nothing made, nothing raised


def test_housekeeping_reports_the_missing_thumbnails():
    store = FakeStore(media_generations=[_media("m1", "2026/11/a.png")], semasa_posts=[], semasa_ideas=[], semasa_motions=[],
                      semasa_settings=[], semasa_log=[])
    store.listing[""] = [{"name": "2026/11/a.png", "id": "x", "created_at": NOW.isoformat(), "metadata": {"size": 10}}]
    report = housekeeping.run(store, NOW, dry=True)
    assert report["thumbs"] == {"found": 1, "made": 0, "bytes": 0}
    assert "library thumbnails missing: 1" in housekeeping.summary(report)


def test_the_orphan_sweep_keeps_a_thumbnail_while_its_picture_is_named_and_deletes_it_after():
    old = (NOW - timedelta(hours=30)).isoformat()
    f = lambda n: {"name": n, "id": "x", "created_at": old, "metadata": {"size": 1000}}  # noqa: E731
    store = FakeStore(media_generations=[_media("m1", "2026/11/kept.png")], semasa_posts=[], semasa_log=[], semasa_motions=[])
    store.listing[""] = [{"name": "2026", "id": None}, {"name": "thumbs", "id": None}]
    store.listing["2026"] = [{"name": "11", "id": None}]
    store.listing["2026/11"] = [f("kept.png")]
    store.listing["thumbs"] = [{"name": "2026", "id": None}]
    store.listing["thumbs/2026"] = [{"name": "11", "id": None}]
    store.listing["thumbs/2026/11"] = [f("kept.png.jpg"), f("gone.png.jpg")]
    out = archive.sweep_orphans(store, NOW, mode="delete")
    assert out.startswith("orphans: 1 unreferenced file(s) deleted")
    assert store.removed[0][1] == ["thumbs/2026/11/gone.png.jpg"]
