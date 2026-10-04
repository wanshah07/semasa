"""The Canva bridge (4 Oct 2026): what the bot is told to build next, and how the pages it exports come back."""

import io

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import canva_bridge as cb
from semasa import db

URL = "https://export-download.canva.com/x/page{n}.png"


def _png(w=1080, h=1350, rgba=False):
    b = io.BytesIO()
    Image.new("RGBA" if rgba else "RGB", (w, h), (240, 235, 220, 255) if rgba else (240, 235, 220)).save(b, "PNG")
    return b.getvalue()


class _Resp:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def iter_content(self, n):
        for i in range(0, len(self.data), n):
            yield self.data[i:i + n]


def _get(png):
    return lambda url, **kw: _Resp(png)


def _slides(n=3):
    return [{"title": f"Slaid {i + 1}", "points": ["Satu", "Dua"]} for i in range(n)]


def _store(**posts):
    base = {"id": "p1", "status": "draft", "stream": "linkedin", "date": "2026-10-05", "slot": "06:00", "slides": _slides(),
            "media_ids": [], "created_by": "u1", "citation": "NPRA"}
    rows = [{**base, **v} for v in posts.values()] if posts else [base]
    return FakeStore(semasa_posts=rows, media_generations=[])


@pytest.fixture(autouse=True)
def _up(monkeypatch):
    got = {}
    monkeypatch.setattr(db, "upload_generated", lambda store, path, data, ct: got.setdefault(path, data) and f"https://cdn/{path}")
    return got


def test_the_queue_offers_open_carousels_soonest_first_and_skips_the_rest():
    store = _store(a={"id": "late", "date": "2026-10-09"}, b={"id": "sooner", "date": "2026-10-05", "slot": "19:00"},
                   c={"id": "one", "slides": _slides(1)}, d={"id": "sent", "status": "scheduled"},
                   e={"id": "past", "date": "2026-10-01"}, f={"id": "no-slides", "slides": []})
    got = [p["id"] for p in cb.next_carousels(store, "2026-10-04")]
    assert got == ["sooner", "late"]          # one slide is a card, scheduled is in Buffer, past is gone


def test_a_post_that_already_has_a_canva_set_is_not_offered_again():
    store = _store(a={"id": "done", "media_ids": ["m1"]}, b={"id": "fresh", "date": "2026-10-06"})
    store.tables["media_generations"].append({"id": "m1", "meta": {"look": "canva"}})
    assert [p["id"] for p in cb.next_carousels(store, "2026-10-04")] == ["fresh"]


def test_the_queue_prints_the_first_post_in_full_and_the_others_as_a_line():
    store = _store(a={"id": "a"}, b={"id": "b", "date": "2026-10-06", "stream": "regulab"})
    q = cb.render_queue(cb.next_carousels(store, "2026-10-04"))
    assert q["next"]["id"] == "a" and q["next"]["size"] == [1080, 1350] and len(q["next"]["slides"]) == 3
    assert q["next"]["slides"][0] == {"title": "Slaid 1", "points": ["Satu", "Dua"]}
    assert q["after"] == [{"id": "b", "status": "draft", "stream": "regulab", "date": "2026-10-06", "slot": "06:00",
                           "lang": None, "pages": 3, "size": [1080, 1080]}]
    assert cb.render_queue([]) == {"next": None, "after": []}


def test_pages_come_back_as_the_posts_slide_set_and_a_draft_takes_them():
    store = _store()
    got = cb.import_design(store, "p1", [URL.format(n=i) for i in range(3)], "https://www.canva.com/design/DAx", get=_get(_png()))
    assert got["pages"] == 3 and got["attached"] is True
    media = store.tables["media_generations"][0]
    assert media["status"] == "done" and media["provider"] == "canva" and media["mode"] == "slides"
    assert media["meta"]["look"] == "canva" and media["meta"]["count"] == 3 and len(media["meta"]["slide_urls"]) == 3
    assert media["meta"]["design_url"].endswith("DAx") and media["generated_media_url"] == media["meta"]["slide_urls"][0]
    assert store.tables["semasa_posts"][0]["media_ids"] == [media["id"]]


def test_a_two_times_export_is_brought_to_the_cards_size_and_a_transparent_one_is_flattened(_up):
    store = _store()
    cb.import_design(store, "p1", [URL.format(n=i) for i in range(3)], get=_get(_png(2160, 2700, rgba=True)))
    assert len(_up) == 3
    for data in _up.values():
        im = Image.open(io.BytesIO(data))
        assert im.format == "JPEG" and im.size == (1080, 1350) and im.mode == "RGB"
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["content_type"] == "image/jpeg" and meta["bytes"] == sum(len(d) for d in _up.values())


def test_the_wrong_shape_is_refused_by_name_and_nothing_is_written():
    store = _store()
    with pytest.raises(cb.BridgeError, match="1080×1350"):
        cb.import_design(store, "p1", [URL.format(n=i) for i in range(3)], get=_get(_png(1080, 1080)))
    assert store.tables["media_generations"] == []


def test_the_page_count_must_match_the_slides():
    with pytest.raises(cb.BridgeError, match="same number of pages"):
        cb.import_design(_store(), "p1", [URL.format(n=1)], get=_get(_png()))


@pytest.mark.parametrize("url", ["http://export.canva.com/a.png", "https://evil.example/a.png", "https://canva.com.evil.io/a.png",
                                 "file:///etc/passwd", "https://169.254.169.254/latest"])
def test_only_canvas_own_https_hosts_are_fetched(url):
    with pytest.raises(cb.BridgeError, match="not a Canva export address"):
        cb.import_design(_store(), "p1", [url] * 3, get=lambda *a, **k: pytest.fail("fetched"))


def test_an_approved_post_keeps_its_pictures_until_wan_moves_it_back():
    store = _store(a={"status": "approved", "media_ids": ["old"]})
    got = cb.import_design(store, "p1", [URL.format(n=i) for i in range(3)], get=_get(_png()))
    assert got["attached"] is False and got["status"] == "approved"
    assert store.tables["semasa_posts"][0]["media_ids"] == ["old"]
    assert len(store.tables["media_generations"]) == 1                  # stored, ready for Use this set


def test_no_such_post_and_too_many_pages():
    with pytest.raises(cb.BridgeError, match="no such post"):
        cb.import_design(_store(), "nope", [URL.format(n=1)] * 3, get=_get(_png()))
    with pytest.raises(cb.BridgeError, match="1 to 10"):
        cb.import_design(_store(), "p1", [URL.format(n=1)] * 11, get=_get(_png()))


# --- a reference design uploaded in the Design tab ------------------------------------------------------------------

def _ref_store():
    job = {"id": "j1", "status": "done", "mode": "slides", "post_id": "p9", "created_by": "u1",
           "created_at": "2026-10-03T01:00:00Z",
           "reference_url": "https://sb/ref.png", "reference_path": "u/ref.png",
           "meta": {"design": "poster", "format": "portrait", "size": [1080, 1350], "stream": "regulab", "citation": "NPRA",
                    "slides": _slides(1), "style_ref": {"url": "https://sb/ref.png", "path": "u/ref.png", "name": "ref.png"},
                    "review": {"summary": "bold", "keep": ["tone"], "change": ["brand"], "brands": ["Acme"]},
                    "awaiting_confirm": True}}
    plain = {"id": "j0", "status": "done", "mode": "slides", "created_at": "2026-10-02T01:00:00Z", "meta": {"design": "poster"}}
    return FakeStore(semasa_posts=[], media_generations=[job, plain])


def test_the_queue_offers_the_newest_uploaded_reference_not_yet_rebuilt():
    store = _ref_store()
    q = cb.render_references(cb.next_references(store))
    assert q["next"]["job"] == "j1" and q["next"]["reference"] == "https://sb/ref.png" and q["next"]["size"] == [1080, 1350]
    assert q["next"]["reading"]["brands_not_to_copy"] == ["Acme"] and q["after"] == []
    store.tables["media_generations"].append({"id": "t", "status": "done", "mode": "slides", "created_at": "2026-10-04T01:00:00Z",
                                              "meta": {"flow": "canva", "canva_for": "j1"}})
    assert cb.next_references(store) == []                           # it has its Canva twin now


def test_a_canva_rebuild_of_a_reference_waits_for_wans_save_and_leaves_the_original():
    store = _ref_store()
    got = cb.import_reference(store, "j1", [URL.format(n=1)], "https://www.canva.com/design/DAy", get=_get(_png()))
    new = next(r for r in store.tables["media_generations"] if r["id"] == got["media_id"])
    m = new["meta"]
    assert m["canva_for"] == "j1" and m["awaiting_confirm"] is True and m["look"] == "canva"
    assert m["style_ref"]["name"] == "ref.png"
    assert new["post_id"] == "p9" and new["reference_url"] == "https://sb/ref.png" and m["slide_urls"]
    old = next(r for r in store.tables["media_generations"] if r["id"] == "j1")
    assert old["meta"].get("flow") != "canva" and "slide_urls" not in old["meta"]


def test_a_reference_rebuild_of_the_wrong_shape_is_refused():
    with pytest.raises(cb.BridgeError, match="1080×1350"):
        cb.import_reference(_ref_store(), "j1", [URL.format(n=1)], get=_get(_png(1080, 1080)))
    with pytest.raises(cb.BridgeError, match="no such reference design"):
        cb.import_reference(_ref_store(), "j0", [URL.format(n=1)], get=_get(_png()))
