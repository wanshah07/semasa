"""Image provider failover (feature C, 8 Nov 2026): a provider that is down, out of neurons or credits, or refuses its
own key hands the row to the next provider with credentials; a refusal about the picture itself is final."""

import pytest
import requests
from test_media import _patch_db

from semasa import media_generator
from semasa.config import MediaSettings
from semasa.providers import Generated, OutOfTime, ProviderError


def _settings(**over):
    base = dict(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1, max_wait_video=1,
                replicate_token=None, replicate_image_model="a/b", replicate_video_model="c/d",
                replicate_image_input_key="input_image", replicate_video_input_key="start_image",
                openai_key="ok-1", openai_base_url="https://kiosapi.com/v1", openai_image_model="gpt-image-2",
                openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                openai_video_size="1280x720", cloudflare_account_id="a" * 32, cloudflare_token="cf-1")
    base.update(over)
    return MediaSettings(**base)


class Fake:
    video = True

    def __init__(self, name, result=None, exc=None):
        self.name, self.result, self.exc, self.calls = name, result, exc, []

    def generate_from_text(self, prompt, options):
        self.calls.append(("text", prompt))
        if self.exc:
            raise self.exc
        return self.result

    def generate(self, kind, reference_url, prompt, options):
        self.calls.append((kind, reference_url))
        if self.exc:
            raise self.exc
        return self.result


PIC = Generated(b"\x89PNG....", "image/png", "gpt-image-2", {})
ROW = {"id": "m1", "type": "image", "mode": "prompt", "prompt": "a jar on a shelf", "attempts": 1, "provider": "cloudflare"}


def test_cloudflare_down_the_openai_dialect_gateway_draws_and_the_row_says_so(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=requests.ConnectionError("could not reach Cloudflare"))
    oai = Fake("openai", result=PIC)
    assert media_generator.process_row(None, dict(ROW), _settings(), {"cloudflare": cf, "openai": oai}) is True
    w = writes["m1"]
    assert w["status"] == "done" and w["provider"] == "openai" and w["model"] == "gpt-image-2"
    assert w["meta"]["provider"] == "openai"
    assert w["meta"]["failover"] == [{"provider": "cloudflare", "why": "could not reach Cloudflare", "kind": "transient"}]
    assert cf.calls and oai.calls


@pytest.mark.parametrize("exc", [
    ProviderError("the free 10,000 neurons for today are used up; they come back at 08:00 MYT."),
    ProviderError("Cloudflare refused the token (HTTP 401): check CLOUDFLARE_API_TOKEN"),
    ProviderError("@cf/x needs the Cloudflare Workers Paid plan; choose a model the free plan runs"),
    ProviderError("Cloudflare answered without a picture: 3040: out of capacity"),
    ProviderError("anything", kind="unavailable"),
])
def test_a_refusal_that_is_the_providers_own_moves_the_row_on(monkeypatch, exc):
    writes, _ = _patch_db(monkeypatch)
    cf, oai = Fake("cloudflare", exc=exc), Fake("openai", result=PIC)
    assert media_generator.process_row(None, dict(ROW), _settings(), {"cloudflare": cf, "openai": oai}) is True
    assert writes["m1"]["provider"] == "openai"


def test_a_refusal_about_the_picture_itself_is_final_and_nobody_else_is_asked(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=ProviderError("OpenAI rejected the request: rejected by our safety system"))
    oai = Fake("openai", result=PIC)
    assert media_generator.process_row(None, dict(ROW), _settings(), {"cloudflare": cf, "openai": oai}) is False
    assert writes["m1"]["status"] == "error" and "safety" in writes["m1"]["error"]
    assert oai.calls == [], "a content refusal is not retried elsewhere"
    assert writes["m1"]["provider"] == "cloudflare", "the row keeps the provider it was given"


def test_when_every_provider_fails_the_error_names_them_all(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=TimeoutError("slow"))
    oai = Fake("openai", exc=ProviderError("OpenAI refused the key (HTTP 401): check the OPENAI_API_KEY secret"))
    media_generator.process_row(None, dict(ROW), _settings(), {"cloudflare": cf, "openai": oai})
    w = writes["m1"]
    assert w["status"] == "error" and "refused the key" in w["error"] and "also failed: cloudflare: slow" in w["error"]


def test_a_video_row_skips_providers_that_make_pictures_only():
    s = _settings(replicate_token="rt")
    assert media_generator.provider_chain(s, "openai", kind="video") == ["openai", "replicate"]
    assert media_generator.provider_chain(s, "cloudflare", kind="image") == ["cloudflare", "openai", "replicate"]
    assert media_generator.provider_chain(s, "replicate", kind="image", needs_edit=True) == ["replicate", "cloudflare", "openai"]
    assert media_generator.provider_chain(_settings(openai_key=None), "cloudflare") == ["cloudflare"]
    assert media_generator.provider_chain(_settings(openai_key=None), "nope") == ["nope", "cloudflare"]


def test_gemini_joins_the_chain_only_when_its_pictures_are_on_and_a_key_can_be_used(monkeypatch):
    from fakestore import FakeStore

    from semasa import db, gemini_keys
    on = FakeStore(**{gemini_keys.TABLE: [{"id": "k1", "api_key": "AIza-1", "enabled": True, "status": "new"}]})
    assert media_generator.provider_chain(_settings(), "cloudflare", store=on) == ["cloudflare", "openai", "gemini"]
    off = FakeStore(**{gemini_keys.TABLE: [{"id": "k1", "api_key": "AIza-1", "enabled": True, "status": "new"}],
                       db.SETTINGS: [{"key": "gemini", "value": {"images": False}}]})
    assert media_generator.provider_chain(_settings(), "cloudflare", store=off) == ["cloudflare", "openai"]
    assert media_generator.provider_chain(_settings(), "cloudflare", store=None) == ["cloudflare", "openai"]
    assert media_generator.provider_chain(_settings(), "cloudflare", store=on, needs_edit=True) == ["cloudflare", "openai"]


def test_the_gemini_provider_draws_from_words_and_reads_a_limit_as_a_limit(monkeypatch):
    from fakestore import FakeStore

    from semasa import gemini_images, gemini_keys
    st = FakeStore(**{gemini_keys.TABLE: [{"id": "k1", "api_key": "AIza-1", "enabled": True, "status": "new"}]})
    monkeypatch.setattr(gemini_images.Drawer, "draw", lambda self, prompt, resolution="portrait": b"\x89PNG" + b"x" * 40)
    p = media_generator.make_provider("gemini", _settings(), st)
    gen = p.generate_from_text("a jar", {})
    assert gen.content_type == "image/png" and gen.meta["gemini_model"]
    with pytest.raises(ProviderError) as e:
        p.generate("image", "https://ref/x.png", "a jar", {})
    assert e.value.kind == "request"

    def spent(self, prompt, resolution="portrait"):
        raise gemini_images.GeminiError("every Gemini key failed", limit=True)
    monkeypatch.setattr(gemini_images.Drawer, "draw", spent)
    with pytest.raises(ProviderError) as e:
        p.generate_from_text("a jar", {})
    assert e.value.kind == "limit"
    with pytest.raises(ProviderError):
        media_generator.make_provider("gemini", _settings(), None)


def test_out_of_time_is_never_failed_over(monkeypatch):
    cf, oai = Fake("cloudflare", exc=OutOfTime("run over")), Fake("openai", result=PIC)
    with pytest.raises(OutOfTime):
        media_generator.generate_with_failover({"cloudflare": cf, "openai": oai}, ["cloudflare", "openai"], _settings(), None,
                                               lambda p: p.generate_from_text("x", {}))
    assert oai.calls == []


@pytest.mark.parametrize("exc,kind", [
    (TimeoutError("slow"), "transient"),
    (requests.Timeout("slow"), "transient"),
    (ProviderError("Replicate refused the token (HTTP 401)"), "auth"),
    (ProviderError("REPLICATE_API_TOKEN is not set"), "auth"),
    (ProviderError("OpenAI rejected the request: You exceeded your current quota"), "limit"),
    (ProviderError("Replicate failed: NSFW content detected"), "content"),
    (ProviderError("OpenAI rejected the request: model gpt-image-9 does not exist"), "model"),
    (ProviderError("Cloudflare rejected the request: 5006: width must be between"), "request"),
    (ProviderError("unknown provider 'nope'"), "request"),
    (ProviderError("x", kind="content"), "content"),
])
def test_error_kind(exc, kind):
    assert media_generator.error_kind(exc) == kind


def test_an_http_error_is_read_by_its_status():
    def err(code):
        e = requests.HTTPError(f"HTTP {code}")
        e.response = type("R", (), {"status_code": code})()
        return e
    assert [media_generator.error_kind(err(c)) for c in (429, 503, 401, 404)] == ["limit", "unavailable", "auth", "model"]


# ---- ChatGPT draws too (Wan, 8 Nov 2026) ---------------------------------------------------------------------------------

def test_chatgpt_is_a_picture_provider_that_takes_words_only_and_is_the_last_resort():
    from fakestore import FakeStore

    from semasa import chatgpt_login as cl
    tokens = {"access_token": "a", "refresh_token": "r"}
    on = FakeStore(**{cl.TABLE: [{"id": "main", "auth": {"tokens": tokens}, "enabled": True}]})
    assert media_generator.has_credentials("chatgpt", _settings(), on)
    assert not media_generator.has_credentials("chatgpt", _settings(), FakeStore(**{cl.TABLE: []}))
    assert not media_generator.has_credentials("chatgpt", _settings(), None)
    s = _settings()
    assert media_generator.provider_chain(s, "cloudflare", store=on)[-1] == "chatgpt"
    assert "chatgpt" not in media_generator.provider_chain(s, "cloudflare", needs_edit=True, store=on), "no reference picture"
    assert "chatgpt" not in media_generator.provider_chain(s, "cloudflare", kind="video", store=on)


def test_when_the_others_cannot_draw_chatgpt_does_and_the_row_says_so(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=ProviderError("the free 10,000 neurons for today are used up"))
    gpt = Fake("chatgpt", result=Generated(b"\x89PNG....", "image/png", "gpt-5.5", {}))
    s = _settings(openai_key=None)
    monkeypatch.setattr(media_generator, "has_credentials", lambda name, s, store=None: name in ("cloudflare", "chatgpt"))
    assert media_generator.process_row(None, dict(ROW), s, {"cloudflare": cf, "chatgpt": gpt}) is True
    w = writes["m1"]
    assert w["status"] == "done" and w["provider"] == "chatgpt" and w["meta"]["failover"][0]["provider"] == "cloudflare"


def test_the_chatgpt_provider_maps_its_errors_to_failover_kinds_and_sizes_the_picture():
    from semasa import chatgpt_login as cl

    class Login:
        def __init__(self, exc=None):
            self.exc, self.sizes = exc, []

        def connected(self):
            return True

        def settings(self):
            return {"model": "gpt-5.5"}

        def draw(self, prompt, size):
            self.sizes.append(size)
            if self.exc:
                raise self.exc
            return b"\x89PNG\r\n\x1a\n" + b"0" * 50

    p = media_generator.ChatGPTImageProvider.__new__(media_generator.ChatGPTImageProvider)
    p.login = Login()
    out = p.generate_from_text("a lab", {"resolution": "portrait"})
    assert out.content_type == "image/png" and out.model == "gpt-5.5" and p.login.sizes == [cl.SIZES["portrait"]]
    for exc, kind in ((cl.ChatGPTError("usage limit", limit=True), "limit"), (cl.ChatGPTError("login", auth=True), "auth"),
                      (cl.ChatGPTError("model", model=True), "model"), (cl.ChatGPTError("boom"), "unavailable")):
        p.login = Login(exc)
        with pytest.raises(ProviderError) as e:
            p.generate_from_text("a lab", {})
        assert e.value.kind == kind
    with pytest.raises(ProviderError) as e2:
        p.generate("edit", "http://x/y.png", "p", {})
    assert e2.value.kind == "request"
