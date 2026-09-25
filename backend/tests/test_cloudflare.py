"""Cloudflare Workers AI: the right call per model, a spent allowance or a refused token is final and says what to do,
a busy moment is retried, a video never reaches it, and the reference is shrunk under Cloudflare's 512 limit."""

import base64
import io

import pytest
from PIL import Image

from semasa import media_generator
from semasa.config import MediaSettings
from semasa.providers import ProviderError, cloudflare
from semasa.providers.cloudflare import CloudflareProvider

JPEG = b"\xff\xd8\xff\xe0 fake jpeg"


def _settings(**over):
    base = dict(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1, max_wait_video=1,
                replicate_token=None, replicate_image_model="a/b", replicate_video_model="c/d",
                replicate_image_input_key="input_image", replicate_video_input_key="start_image",
                openai_key=None, openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                openai_video_size="1280x720", cloudflare_account_id="acc", cloudflare_token="tok")
    base.update(over)
    return MediaSettings(**base)


class Resp:
    def __init__(self, status, body):
        self.status_code, self.body, self.text = status, body, str(body)

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise cloudflare.requests.HTTPError(f"HTTP {self.status_code}")


def ok(data=JPEG):
    return Resp(200, {"success": True, "result": {"image": base64.b64encode(data).decode()}, "errors": []})


def _png(w, h):
    out = io.BytesIO()
    Image.new("RGB", (w, h), (200, 30, 30)).save(out, format="PNG")
    return out.getvalue()


def test_schnell_is_called_with_json_and_the_picture_comes_back(monkeypatch):
    calls = []
    monkeypatch.setattr(cloudflare.requests, "post", lambda url, **k: calls.append((url, k)) or ok())
    gen = CloudflareProvider(_settings()).generate_from_text("a lab bench", {})
    url, k = calls[0]
    assert url == "https://api.cloudflare.com/client/v4/accounts/acc/ai/run/@cf/black-forest-labs/flux-1-schnell"
    assert k["json"] == {"prompt": "a lab bench", "steps": 4} and k["headers"]["Authorization"] == "Bearer tok"
    assert gen.data == JPEG and gen.content_type == "image/jpeg" and gen.model.endswith("flux-1-schnell")


def test_flux2_takes_multipart_even_for_words(monkeypatch):
    calls = []
    monkeypatch.setattr(cloudflare.requests, "post", lambda url, **k: calls.append((url, k)) or ok(b"\x89PNG x"))
    gen = CloudflareProvider(_settings(cloudflare_t2i_model="@cf/black-forest-labs/flux-2-klein-4b")) \
        .generate_from_text("p", {})
    files = calls[0][1]["files"]
    assert files["prompt"] == (None, "p") and files["width"] == (None, "1024") and "json" not in calls[0][1]
    assert gen.content_type == "image/png"


def test_reference_is_shrunk_under_512_and_sent_as_input_image_0(monkeypatch):
    calls = []
    monkeypatch.setattr(cloudflare, "fetch_reference", lambda url: (_png(1600, 900), "image/png", "x.png"))
    monkeypatch.setattr(cloudflare.requests, "post", lambda url, **k: calls.append((url, k)) or ok())
    CloudflareProvider(_settings()).generate("image", "https://ref/x.png", "make it blue", {})
    url, k = calls[0]
    assert url.endswith("/@cf/black-forest-labs/flux-2-klein-4b")
    name, data, ct = k["files"]["input_image_0"]
    with Image.open(io.BytesIO(data)) as im:
        assert max(im.size) < 512 and im.size[0] > im.size[1]      # shape kept
    assert ct == "image/jpeg" and k["files"]["prompt"] == (None, "make it blue")


def test_a_schnell_edit_model_is_refused_before_any_call(monkeypatch):
    monkeypatch.setattr(cloudflare, "fetch_reference", lambda url: (_png(10, 10), "image/png", "x.png"))
    monkeypatch.setattr(cloudflare.requests, "post", lambda *a, **k: pytest.fail("no call"))
    with pytest.raises(ProviderError, match="cannot take a reference"):
        CloudflareProvider(_settings(cloudflare_edit_model="@cf/black-forest-labs/flux-1-schnell")) \
            .generate("image", "https://ref/x.png", "p", {})


def test_spent_allowance_is_final_and_names_the_reset(monkeypatch):
    body = {"success": False, "errors": [{"code": 3036, "message": "You have used up your daily free allocation "
                                                                 "of 10,000 neurons."}]}
    monkeypatch.setattr(cloudflare.requests, "post", lambda *a, **k: Resp(429, body))
    with pytest.raises(ProviderError, match="08:00 MYT"):
        CloudflareProvider(_settings()).generate_from_text("p", {})


def test_busy_is_not_final(monkeypatch):
    body = {"success": False, "errors": [{"code": 3040, "message": "Capacity temporarily exceeded"}]}
    monkeypatch.setattr(cloudflare.requests, "post", lambda *a, **k: Resp(429, body))
    with pytest.raises(cloudflare.requests.HTTPError):
        CloudflareProvider(_settings()).generate_from_text("p", {})


def test_refused_token_and_paid_only_model_say_what_to_fix(monkeypatch):
    monkeypatch.setattr(cloudflare.requests, "post",
                        lambda *a, **k: Resp(401, {"success": False, "errors": [{"code": 10000, "message": "Auth"}]}))
    with pytest.raises(ProviderError, match="CLOUDFLARE_API_TOKEN"):
        CloudflareProvider(_settings()).generate_from_text("p", {})
    monkeypatch.setattr(cloudflare.requests, "post",
                        lambda *a, **k: Resp(403, {"success": False, "errors": [{"code": 5035, "message": "Paid"}]}))
    with pytest.raises(ProviderError, match="Workers Paid"):
        CloudflareProvider(_settings()).generate_from_text("p", {})


def test_missing_secrets_are_named():
    with pytest.raises(ProviderError, match="CLOUDFLARE_ACCOUNT_ID"):
        CloudflareProvider(_settings(cloudflare_token=None))


def test_a_video_job_stops_before_anything_is_spent(monkeypatch):
    writes = {}
    monkeypatch.setattr(media_generator.db, "finish_media", lambda store, rid, **f: writes.setdefault(rid, f))
    monkeypatch.setattr(cloudflare.requests, "post", lambda *a, **k: pytest.fail("no call"))
    row = {"id": "v1", "type": "video", "mode": "prompt", "prompt": "a lab", "attempts": 1}
    assert media_generator.process_row(None, row, _settings(), {}) is False
    assert writes["v1"]["status"] == "error" and "pictures only" in writes["v1"]["error"]


def test_default_provider_is_cloudflare_only_when_its_secrets_are_there(monkeypatch):
    for n in ("MEDIA_PROVIDER", "REPLICATE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"):
        monkeypatch.delenv(n, raising=False)
    assert MediaSettings.load().provider == "replicate"
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acc")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    assert MediaSettings.load().provider == "cloudflare"
    monkeypatch.setenv("REPLICATE_API_TOKEN", "r")
    assert MediaSettings.load().provider == "replicate"
    monkeypatch.setenv("MEDIA_PROVIDER", "cloudflare")
    assert MediaSettings.load().provider == "cloudflare"
