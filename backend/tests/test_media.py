from semasa import media_generator
from semasa.config import MediaSettings
from semasa.providers import Generated, ProviderError


def _settings(**over):
    base = dict(provider="replicate", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1, max_wait_video=1,
                replicate_token="t", replicate_image_model="a/b", replicate_video_model="c/d",
                replicate_image_input_key="input_image", replicate_video_input_key="start_image",
                openai_key=None, openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                openai_video_size="1280x720")
    base.update(over)
    return MediaSettings(**base)


class FakeProvider:
    name = "fake"

    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.calls = result, exc, []

    def generate(self, kind, reference_url, prompt, options):
        self.calls.append((kind, reference_url, prompt, options))
        if self.exc:
            raise self.exc
        return self.result


def _patch_db(monkeypatch):
    writes = {}
    uploads = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: uploads.setdefault(path, (data, ct)) and f"https://cdn/{path}")
    monkeypatch.setattr(media_generator.db, "finish_media", lambda store, rid, **f: writes.setdefault(rid, f))
    return writes, uploads


def test_done_row_carries_url_sha_and_model(monkeypatch):
    writes, uploads = _patch_db(monkeypatch)
    prov = FakeProvider(Generated(b"\x89PNG...", "image/png", "a/b", {"prediction_id": "p1"}))
    row = {"id": "r1", "type": "image", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1,
           "meta": {"options": {"input": {"aspect_ratio": "1:1"}}}}
    assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is True
    assert prov.calls[0][3] == {"input": {"aspect_ratio": "1:1"}}
    w = writes["r1"]
    assert w["status"] == "done" and w["generated_media_url"].endswith("/r1.png") and w["model"] == "a/b"
    assert w["meta"]["sha256"] and w["meta"]["bytes"] == 7 and w["meta"]["prediction_id"] == "p1"
    assert list(uploads.values())[0][1] == "image/png"


def test_transient_failure_goes_back_to_pending_until_max(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    prov = FakeProvider(exc=TimeoutError("slow"))
    row = {"id": "r2", "type": "video", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1,
           "provider": "replicate"}
    media_generator.process_row(None, row, _settings(max_attempts=3), {"replicate": prov})
    assert writes["r2"]["status"] == "pending" and "TimeoutError" in writes["r2"]["error"]
    writes.clear()
    row["attempts"] = 3
    media_generator.process_row(None, row, _settings(max_attempts=3), {"replicate": prov})
    assert writes["r2"]["status"] == "error"


def test_provider_refusal_is_final(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    prov = FakeProvider(exc=ProviderError("rejected"))
    row = {"id": "r3", "type": "image", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1}
    media_generator.process_row(None, row, _settings(), {"replicate": prov})
    assert writes["r3"]["status"] == "error"


def test_unknown_provider_is_recorded_not_raised(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    row = {"id": "r4", "type": "image", "reference_url": "https://ref/x.png", "prompt": "p", "attempts": 1, "provider": "nope"}
    assert media_generator.process_row(None, row, _settings(), {}) is False
    assert writes["r4"]["status"] == "error" and "unknown provider" in writes["r4"]["error"]


def test_non_image_reference_is_refused_before_any_provider_call(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    prov = FakeProvider(Generated(b"x", "image/png", "a/b"))
    for rid, row in {
        "pdf": {"reference_url": "https://s/ref/x.pdf", "meta": {"mime": "application/pdf"}},
        "txt": {"reference_url": "https://s/ref/notes.txt"},
    }.items():
        row.update(id=rid, type="image", prompt="p", attempts=1)
        assert media_generator.process_row(None, row, _settings(), {"replicate": prov}) is False
        assert writes[rid]["status"] == "error" and "must be an image" in writes[rid]["error"]
    assert prov.calls == []                                # no credits spent on a doomed job


def test_image_reference_detection():
    assert media_generator.reference_is_image({"meta": {"mime": "image/webp"}, "reference_url": "u"})
    assert media_generator.reference_is_image({"reference_url": "https://s/r/a.JPG?token=1"})
    assert not media_generator.reference_is_image({"reference_url": "https://s/r/a.pdf"})
