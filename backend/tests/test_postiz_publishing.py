from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from requests.adapters import BaseAdapter, HTTPAdapter

from semasa import postiz, publishing

REAL_REQUEST = requests.Session.request


@pytest.fixture(autouse=True)
def allow_local_postiz(monkeypatch):
    """Keep the global no-network guard; permit only this module's loopback server."""

    def local_only(self, method, url, **kwargs):
        if not str(url).startswith("http://127.0.0.1:"):
            raise AssertionError("external network is forbidden")
        return REAL_REQUEST(self, method, url, **kwargs)

    monkeypatch.setattr(requests.Session, "request", local_only)


class LocalAdapter(BaseAdapter):
    def __init__(self):
        self.real = HTTPAdapter()

    def send(self, request, **kwargs):
        if not request.url.startswith("http://127.0.0.1:"):
            raise AssertionError("external network is forbidden")
        return self.real.send(request, **kwargs)

    def close(self):
        self.real.close()


def local_session():
    session = requests.Session()
    session.mount("http://", LocalAdapter())
    return session


def test_approval_binds_every_field_and_edit_invalidates():
    post = {
        "id": "p1",
        "provider": "postiz",
        "stream": "linkedin",
        "lang": "en",
        "text": {"en": {"linkedin": "hello"}},
        "citation": "NPRA",
        "media_ids": ["m1"],
        "date": "2026-11-02",
        "slot": "08:00",
        "channels": ["linkedin"],
    }
    media = [
        {
            "id": "m1",
            "type": "video",
            "generated_media_url": "https://cdn/film.mp4",
            "meta": {"sha256": "a" * 64, "bytes": 12, "mime": "video/mp4", "seconds": 8},
        }
    ]
    token = publishing.approval_token(post, media, {"linkedin": "personal-1"})
    assert publishing.approval_valid({**post, "approval_token": token}, media, {"linkedin": "personal-1"})
    for key, value in [("date", "2026-11-03"), ("slot", "09:00"), ("provider", "buffer"), ("citation", "other")]:
        assert not publishing.approval_valid({**post, key: value, "approval_token": token}, media, {"linkedin": "personal-1"})
    changed = json.loads(json.dumps(post))
    changed["text"]["en"]["linkedin"] = "changed"
    assert not publishing.approval_valid({**changed, "approval_token": token}, media, {"linkedin": "personal-1"})
    changed_media = json.loads(json.dumps(media))
    changed_media[0]["meta"]["sha256"] = "b" * 64
    assert not publishing.approval_valid({**post, "approval_token": token}, changed_media, {"linkedin": "personal-1"})


def test_provider_default_preserves_legacy_until_staged_cutover():
    assert publishing.provider_for({"stream": "regulab"}, {}) == "buffer"
    assert publishing.provider_for({"stream": "linkedin"}, {}) == "composio"
    assert (
        publishing.provider_for(
            {"stream": "regulab"}, {"publishing": {"default_provider": "postiz"}, "channels": {"postiz": {"enabled": True}}}
        )
        == "postiz"
    )
    assert publishing.provider_for({"provider": "buffer"}, {"publishing": {"default_provider": "postiz"}}) == "buffer"
    assert not publishing.fallback_allowed({"outcome": "unknown"})
    assert not publishing.fallback_allowed({"outcome": "accepted"})
    assert publishing.fallback_allowed({"outcome": "refused", "remote_accepted": False})


class MockPostiz:
    def __init__(self, timeout_create=False):
        self.posts, self.integrations, self.uploads = [], [], []
        self.timeout_create = timeout_create
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def handler(mock):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def reply(self, value, status=200):
                raw = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/public/v1/integrations":
                    return self.reply([{"id": "personal-1", "identifier": "linkedin", "disabled": False}])
                if self.path.startswith("/public/v1/posts"):
                    return self.reply({"posts": mock.posts})
                self.reply({"msg": "not found"}, 404)

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(n)
                if self.path == "/public/v1/upload":
                    mock.uploads.append(body)
                    return self.reply({"id": "asset-1", "path": "https://postiz/media/asset-1.mp4"})
                if self.path == "/public/v1/posts":
                    payload = json.loads(body)
                    record = {
                        "id": "remote-1",
                        "group": payload["posts"][0]["group"],
                        "content": payload["posts"][0]["value"][0]["content"],
                        "image": payload["posts"][0]["value"][0]["image"],
                        "publishDate": payload["date"],
                        "state": "QUEUE",
                        "releaseURL": None,
                        "integration": {"id": "personal-1", "providerIdentifier": "linkedin"},
                    }
                    mock.posts = [record]
                    if mock.timeout_create:
                        self.close_connection = True
                        return
                    return self.reply([{"postId": "remote-1", "integration": "personal-1"}])
                self.reply({"msg": "not found"}, 404)

        return H

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


@pytest.fixture
def mock_postiz():
    server = MockPostiz()
    yield server, server.url
    server.close()


def _package():
    data = b"native-video-bytes"
    return publishing.MediaAsset(
        asset_id="m1",
        url="https://cdn/film.mp4",
        mime="video/mp4",
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        duration=8.0,
    ), publishing.ContentPackage(
        post_id="p1",
        caption="hello",
        channel="linkedin",
        integration_id="personal-1",
        scheduled_at="2026-11-02T00:00:00+00:00",
        timezone="Asia/Kuala_Lumpur",
        idempotency_key="p1:linkedin:" + "a" * 64,
        assets=[
            publishing.MediaAsset(
                asset_id="m1",
                url="https://cdn/film.mp4",
                mime="video/mp4",
                data=data,
                sha256=hashlib.sha256(data).hexdigest(),
                duration=8.0,
            )
        ],
        expected_media=("m1",),
    )


def test_full_video_upload_schedule_and_readback(mock_postiz):
    mock_postiz, url = mock_postiz
    client = postiz.Postiz("secret", url, session=local_session())
    package = _package()[1]
    result = client.publish(package)
    assert result.post_id == "remote-1" and result.status == "scheduled"
    assert mock_postiz.uploads and b"native-video-bytes" in mock_postiz.uploads[0]
    sent = mock_postiz.posts[0]
    assert sent["image"] == [{"id": "asset-1", "path": "https://postiz/media/asset-1.mp4"}]
    assert sent["integration"]["id"] == "personal-1" and sent["publishDate"] == package.scheduled_at
    assert sent["group"] == package.idempotency_key
    confirmed = client.readback(result, package.scheduled_at)
    assert confirmed.post_id == "remote-1" and confirmed.status == "scheduled"
    mock_postiz.posts[0].update(state="PUBLISHED", releaseURL="https://linkedin/feed/1")
    published = client.readback(result, package.scheduled_at)
    assert published.status == "sent" and published.url == "https://linkedin/feed/1"


def test_unknown_create_outcome_never_retries_or_falls_back(mock_postiz):
    mock_postiz, url = mock_postiz
    mock_postiz.timeout_create = True
    client = postiz.Postiz("secret", url, session=local_session())
    package = _package()[1]
    with pytest.raises(postiz.UnknownOutcome):
        client.publish(package)
    # The remote accepted it. The group is the durable idempotency key used by reconciliation.
    assert len(mock_postiz.posts) == 1
    found = client.find_by_key(package.idempotency_key, package.scheduled_at)
    assert found.post_id == "remote-1"


def test_video_cannot_be_silently_dropped(mock_postiz):
    mock_postiz, url = mock_postiz
    client = postiz.Postiz("secret", url, session=local_session())
    package = _package()[1]
    object.__setattr__(package, "assets", [])
    with pytest.raises(postiz.MediaValidationError):
        client.publish(package)
    assert mock_postiz.posts == []


def test_media_integrity_and_capabilities():
    with pytest.raises(ValueError):
        publishing.media_bytes({"id": "m", "type": "video", "meta": {"sha256": "bad"}}, b"video")
    assert publishing.supports("linkedin", ["video/mp4"])
    assert not publishing.supports("instagram", [])
    assert not publishing.supports("linkedin", ["video/mp4", "image/png"])


def test_publisher_wires_postiz_video_and_readback_without_backup(monkeypatch):
    from types import SimpleNamespace

    from fakestore import FakeStore

    from semasa import publisher

    data = b"native-video"
    row = {
        "id": "m1",
        "status": "done",
        "type": "video",
        "generated_media_url": "https://cdn/film.mp4",
        "meta": {"sha256": hashlib.sha256(data).hexdigest(), "content_type": "video/mp4"},
    }
    post = {
        "id": "p1",
        "status": "approved",
        "provider": "postiz",
        "stream": "linkedin",
        "lang": "en",
        "date": "2026-11-02",
        "slot": "08:00",
        "channels": ["linkedin"],
        "text": {"en": {"linkedin": "A notification is not an approval."}},
        "citation": "NPRA",
        "media_ids": ["m1"],
        "published": {},
        "errors": {},
    }
    accounts = {"linkedin": "personal-1"}
    post["approval_token"] = publishing.approval_token(post, [row], accounts)
    store = FakeStore(
        semasa_settings=[
            {"key": "publishing", "value": {"enabled": True}},
            {"key": "brand", "value": {}},
            {"key": "channels", "value": {"postiz": {"enabled": True, **accounts}}},
        ],
        semasa_posts=[post],
        media_generations=[row],
        semasa_publish_log=[],
    )
    monkeypatch.setattr(publisher.requests, "get", lambda *a, **k: SimpleNamespace(content=data, raise_for_status=lambda: None))

    class Client:
        def find_by_key(self, key, at):
            return None

        def publish(self, package):
            assert package.assets[0].data == data and package.integration_id == "personal-1"
            return postiz.Result("remote-1", "scheduled", package.scheduled_at)

    counts = publisher.run(store, datetime(2026, 11, 1, tzinfo=UTC), clients={"postiz": Client()})
    saved = store.tables["semasa_posts"][0]
    assert counts["scheduled"] == 1 and saved["status"] == "scheduled"
    assert saved["published"]["linkedin"]["route"] == "postiz"
    assert store.tables["semasa_publish_log"][-1]["detail"]["readback"] is True


def test_unknown_publisher_outcome_does_not_select_backup(monkeypatch):
    from fakestore import FakeStore

    from semasa import publisher

    post = {
        "id": "p1",
        "status": "approved",
        "provider": "postiz",
        "stream": "regulab",
        "lang": "bm",
        "date": "2026-11-02",
        "slot": "08:00",
        "channels": ["threads"],
        "text": {"bm": {"threads": "Notifikasi bukan kelulusan produk."}},
        "citation": "NPRA",
        "media_ids": [],
        "published": {},
        "errors": {},
    }
    row = []
    post["approval_token"] = publishing.approval_token(post, row, {"threads": "threads-1"})
    store = FakeStore(
        semasa_settings=[
            {"key": "publishing", "value": {"enabled": True}},
            {"key": "brand", "value": {}},
            {"key": "channels", "value": {"postiz": {"enabled": True, "threads": "threads-1"}}},
        ],
        semasa_posts=[post],
        media_generations=[],
        semasa_publish_log=[],
    )

    class Client:
        def find_by_key(self, key, at):
            return None

        def publish(self, package):
            raise postiz.UnknownOutcome("connection lost")

    class Backup:
        def posts(self, *a):
            raise AssertionError("Buffer must not be read as automatic fallback")

    publisher.run(store, datetime(2026, 11, 1, tzinfo=UTC), clients={"postiz": Client(), "buffer": Backup()})
    saved = store.tables["semasa_posts"][0]
    assert saved["published"] == {} and saved["errors"]["threads"]["outcome"] == "unknown"
