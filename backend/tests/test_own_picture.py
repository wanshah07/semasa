"""Wan's own picture into a post: checked, made a clean JPEG, hosted for good, attached, the temporary copy removed."""

import io
from types import SimpleNamespace

from fakestore import FakeStore
from PIL import Image

from semasa import db, own_picture


def _png(size=(40, 30), mode="RGBA", colour=(200, 0, 0, 0)):
    buf = io.BytesIO()
    Image.new(mode, size, colour).save(buf, "PNG")
    return buf.getvalue()


def test_normalise_makes_an_upright_rgb_jpeg_within_the_edge():
    data, info = own_picture.normalise(_png((4000, 1000), "RGB", (10, 20, 30)))
    img = Image.open(io.BytesIO(data))
    assert img.format == "JPEG" and img.mode == "RGB" and max(img.size) == own_picture.MAX_EDGE
    assert info["original_size"] == [4000, 1000] and info["width"] == 2160 and info["height"] == 540


def test_transparency_is_laid_on_white_and_a_small_picture_is_not_enlarged():
    data, info = own_picture.normalise(_png((40, 30)))
    img = Image.open(io.BytesIO(data))
    assert img.size == (40, 30)
    r, g, b = img.getpixel((20, 15))
    assert min(r, g, b) > 240                      # fully transparent red became white, never black


def test_a_phone_photo_is_turned_the_right_way_up():
    img = Image.new("RGB", (60, 20), (0, 0, 0))
    exif = img.getexif()
    exif[0x0112] = 6                               # "rotate 90° clockwise to view"
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif)
    _, info = own_picture.normalise(buf.getvalue())
    assert (info["width"], info["height"]) == (20, 60)


def test_a_file_that_is_not_a_picture_fails_for_good():
    for bad in (b"", b"%PDF-1.7 not a picture"):
        try:
            own_picture.normalise(bad)
        except own_picture.NotAPicture:
            continue
        raise AssertionError("accepted a non-picture")


def _store():
    return FakeStore(media_generations=[{"id": "m1", "mode": "upload", "status": "processing", "post_id": "p1",
                                         "reference_url": "https://ref.test/u/a.png", "reference_path": "u/a.png",
                                         "attempts": 1, "meta": {"alt": "Botol di rak", "flow": "B"}}],
                     semasa_posts=[{"id": "p1", "status": "draft", "media_ids": ["x0"]}])


def test_process_hosts_attaches_and_removes_the_temporary_copy(monkeypatch):
    store = _store()
    monkeypatch.setattr(own_picture, "get", lambda url, timeout=60: SimpleNamespace(content=_png((100, 80), "RGB", (1, 2, 3))))
    put = []
    monkeypatch.setattr(db, "upload_generated", lambda st, path, data, ct: put.append((path, ct)) or f"https://pub.test/{path}")
    assert own_picture.process(store, store.tables["media_generations"][0]) is True
    m = store.tables["media_generations"][0]
    assert m["status"] == "done" and m["provider"] == "own" and m["generated_media_url"].endswith("/m1.jpg")
    assert m["meta"]["alt"] == "Botol di rak" and m["meta"]["own"] is True and m["reference_path"] is None
    assert put[0][1] == "image/jpeg"
    assert store.removed == [("semasa-reference", ["u/a.png"])]
    assert store.tables["semasa_posts"][0]["media_ids"] == ["x0", "m1"]


def test_process_never_touches_an_approved_post(monkeypatch):
    store = _store()
    store.tables["semasa_posts"][0]["status"] = "approved"
    monkeypatch.setattr(own_picture, "get", lambda url, timeout=60: SimpleNamespace(content=_png((10, 10), "RGB", (1, 2, 3))))
    monkeypatch.setattr(db, "upload_generated", lambda st, path, data, ct: "https://pub.test/x.jpg")
    own_picture.process(store, store.tables["media_generations"][0])
    assert store.tables["semasa_posts"][0]["media_ids"] == ["x0"]


def test_process_records_a_bad_file_as_a_final_error(monkeypatch):
    store = _store()
    monkeypatch.setattr(own_picture, "get", lambda url, timeout=60: SimpleNamespace(content=b"<html>not found</html>"))
    assert own_picture.process(store, store.tables["media_generations"][0]) is False
    m = store.tables["media_generations"][0]
    assert m["status"] == "error" and "not a picture" in m["error"] and store.removed == []
