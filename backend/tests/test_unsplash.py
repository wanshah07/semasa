"""Unsplash: a search, then a pick, on one media row; the key stays on the worker; the download is reported; the
photographer is credited; a missing key or a used-up hour says so and stops."""

import io

import pytest
from fakestore import FakeStore
from PIL import Image
from test_studio_cards import _settings

from semasa import media_generator, unsplash

PHOTO = {"id": "abc", "width": 4000, "height": 3000, "color": "#aabbcc", "alt_description": "a clean laboratory",
         "urls": {"raw": "https://images.unsplash.com/photo-abc?ixid=1", "small": "https://images.unsplash.com/photo-abc?w=400"},
         "links": {"html": "https://unsplash.com/photos/abc", "download_location": "https://api.unsplash.com/photos/abc/download?ixid=1"},
         "user": {"name": "Aina Rahman", "username": "aina", "links": {"html": "https://unsplash.com/@aina"}}}


def _jpeg():
    b = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 20, 30)).save(b, "JPEG")
    return b.getvalue()


class R:
    def __init__(self, status=200, js=None, content=b"", headers=None, text=""):
        self.status_code, self._js, self.content, self.headers, self.text = status, js, content, headers or {}, text

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise unsplash.requests.HTTPError(str(self.status_code))


@pytest.fixture
def api(monkeypatch):
    calls = []

    def get(url, params=None, timeout=0, headers=None):
        calls.append((url, params, (headers or {}).get("Authorization")))
        if url.endswith("/search/photos"):
            return R(js={"results": [PHOTO, {"id": "x", "urls": {}}]})
        if "download_location" in url or "/download" in url:
            return R(js={"url": "https://images.unsplash.com/photo-abc?dl"})
        if url.startswith("https://images.unsplash.com/"):
            return R(content=_jpeg())
        raise AssertionError(url)

    monkeypatch.setenv("UNSPLASH_ACCESS_KEY", "unsplash-key")
    monkeypatch.setattr(unsplash.requests, "get", get)
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: f"https://cdn/{path}")
    return calls


def _store(meta=None, attempts=1, prompt="makmal kosmetik"):
    return FakeStore(media_generations=[{"id": "u1", "mode": "prompt", "type": "image", "provider": "unsplash",
                                         "status": "processing", "attempts": attempts, "prompt": prompt,
                                         "meta": {"flow": "unsplash", "orientation": "squarish", **(meta or {})}}])


def _run(store):
    return media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None)


def test_a_search_lists_photos_for_the_page_with_the_key_kept_on_the_worker(api):
    store = _store()
    assert _run(store) is True
    row = store.tables["media_generations"][0]
    assert row["status"] == "done" and row["generated_media_url"] is None and row["meta"]["step"] == "choose"
    [p] = row["meta"]["results"]                                    # a result with no picture is dropped
    assert p["id"] == "abc" and p["thumb"].startswith("https://images.unsplash.com/") and p["name"] == "Aina Rahman"
    assert p["profile"].endswith("utm_source=semasa&utm_medium=referral")
    url, params, auth = api[0]
    assert params["query"] == "makmal kosmetik" and params["orientation"] == "squarish" and auth == "Client-ID unsplash-key"


def test_a_pick_reports_the_download_stores_the_photo_and_credits_the_photographer(api):
    store = _store()
    _run(store)
    row = store.tables["media_generations"][0]
    row.update(status="processing", meta={**row["meta"], "pick": "abc"})
    assert _run(store) is True
    row = store.tables["media_generations"][0]
    assert row["status"] == "done" and row["generated_media_url"].startswith("https://cdn/") and row["model"] == "photo"
    assert row["meta"]["credit"]["name"] == "Aina Rahman" and row["meta"]["step"] == "picked"
    urls = [u for u, _, _ in api]
    assert any("/download" in u for u in urls)                      # Unsplash's rule: report the download
    assert any("w=2160" in u and u.startswith("https://images.unsplash.com/photo-abc") for u in urls)


def test_no_key_is_a_final_error_that_says_where_it_goes(api, monkeypatch):
    monkeypatch.delenv("UNSPLASH_ACCESS_KEY")
    store = _store()
    assert _run(store) is False
    row = store.tables["media_generations"][0]
    assert row["status"] == "error" and "UNSPLASH_ACCESS_KEY is not set" in row["error"]


def test_a_used_up_hour_says_so(api, monkeypatch):
    monkeypatch.setattr(unsplash.requests, "get", lambda *a, **k: R(status=403, text="Rate Limit Exceeded",
                                                                     headers={"X-Ratelimit-Remaining": "0"}))
    store = _store()
    _run(store)
    assert "hourly limit" in store.tables["media_generations"][0]["error"]
    monkeypatch.setattr(unsplash.requests, "get", lambda *a, **k: R(status=401, text="OAuth error: invalid token"))
    store = _store()
    _run(store)
    assert "Unsplash refused the key (401)" in store.tables["media_generations"][0]["error"]


def test_a_pick_that_is_not_in_the_results_is_named(api):
    store = _store(meta={"pick": "zzz", "results": []})
    assert _run(store) is False
    assert "not among this search's results" in store.tables["media_generations"][0]["error"]


def test_a_network_blip_is_tried_again(api, monkeypatch):
    def boom(*a, **k):
        raise unsplash.requests.ConnectionError("reset")
    monkeypatch.setattr(unsplash.requests, "get", boom)
    store = _store(attempts=1)
    _run(store)
    assert store.tables["media_generations"][0]["status"] == "pending"
