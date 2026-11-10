"""A Pinterest pin link as a poster reference (Wan, 10 Nov 2026)."""

import pytest

from semasa import media_generator, pinterest

PAGE = ('<html><head><meta property="og:image" content="https://i.pinimg.com/736x/a7/66/56/a76656e966b1958f568d63c3f1c05aec.jpg"/>'
        '<meta property="og:title" content="A tidy skincare poster"/></head></html>')


class Resp:
    def __init__(self, status=200, text="", ctype="text/html", url="https://www.pinterest.com/pin/1/"):
        self.status_code, self.text, self.headers, self.url = status, text, {"content-type": ctype}, url

    def close(self):
        pass


def getter(original_ok=True, page=PAGE, status=200):
    def get(url, **kw):
        if "pinimg.com/originals" in url:
            return Resp(200 if original_ok else 404, ctype="image/jpeg")
        return Resp(status, page)
    return get


def test_which_links_are_pins():
    assert pinterest.is_pin_link("https://www.pinterest.com/pin/99360735500167749/")
    assert pinterest.is_pin_link("https://my.pinterest.com/pin/123/")
    assert pinterest.is_pin_link("https://pin.it/abc123")
    assert not pinterest.is_pin_link("https://www.pinterest.com/someone/skincare-boards/"), "a board has no single picture"
    assert not pinterest.is_pin_link("https://example.com/pin/123")
    assert not pinterest.is_pinterest("https://notpinterest.com/pin/1")


def test_a_pin_gives_its_picture_at_full_size_when_that_answers_and_the_page_size_when_not():
    got = pinterest.resolve("https://www.pinterest.com/pin/1/", getter())
    assert got["image"] == "https://i.pinimg.com/originals/a7/66/56/a76656e966b1958f568d63c3f1c05aec.jpg"
    assert got["title"] == "A tidy skincare poster"
    got = pinterest.resolve("https://www.pinterest.com/pin/1/", getter(original_ok=False))
    assert got["image"].startswith("https://i.pinimg.com/736x/")


def test_a_board_a_wall_or_a_missing_pin_says_why():
    with pytest.raises(ValueError, match="board or a profile"):
        pinterest.resolve("https://www.pinterest.com/someone/boards/")
    with pytest.raises(ValueError, match="404"):
        pinterest.resolve("https://www.pinterest.com/pin/1/", getter(status=404))
    with pytest.raises(ValueError, match="no picture"):
        pinterest.resolve("https://www.pinterest.com/pin/1/", getter(page="<html></html>"))


def test_the_worker_swaps_a_pin_link_for_its_picture_before_the_image_check(monkeypatch):
    monkeypatch.setattr(pinterest, "resolve", lambda url: {"image": "https://i.pinimg.com/originals/a7/66/x.jpg",
                                                          "title": "t", "pin": url})
    saved = {}

    class T:
        def update(self, v):
            saved.update(v)
            return self

        def eq(self, *a):
            return self

        def execute(self):
            return self

    class Store:
        def table(self, name):
            return T()

    row = {"id": "m1", "reference_url": "https://www.pinterest.com/pin/1/", "meta": {"flow": "A-own"}}
    assert not media_generator.reference_is_image(row), "a pin page is not a picture"
    media_generator._pinterest_reference(Store(), row)
    assert media_generator.reference_is_image(row) and row["meta"]["pinterest_pin"].endswith("/pin/1/")
    assert saved["reference_url"].endswith("x.jpg")
    row2 = {"id": "m2", "reference_url": "https://example.com/a.png"}
    media_generator._pinterest_reference(Store(), row2)
    assert row2["reference_url"] == "https://example.com/a.png", "other references are left alone"
