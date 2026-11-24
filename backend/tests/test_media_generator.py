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


def _picked():
    """ROW as a row whose provider was PICKED (Cloudflare first, then the rest): what the failover tests start from. A row
    whose provider is only Tetapan's default follows IMAGE_PRIORITY instead (ChatGPT, Cloudflare, ...; 24 Nov 2026)."""
    return {**ROW, "meta": {"provider_explicit": True}}


def test_cloudflare_down_the_openai_dialect_gateway_draws_and_the_row_says_so(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=requests.ConnectionError("could not reach Cloudflare"))
    oai = Fake("openai", result=PIC)
    assert media_generator.process_row(None, _picked(), _settings(), {"cloudflare": cf, "openai": oai}) is True
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
    ProviderError("Cloudflare rejected the request: 8007: AiError: Input prompt contains NSFW content", kind="filter"),
])
def test_a_refusal_that_is_the_providers_own_moves_the_row_on(monkeypatch, exc):
    writes, _ = _patch_db(monkeypatch)
    cf, oai = Fake("cloudflare", exc=exc), Fake("openai", result=PIC)
    assert media_generator.process_row(None, _picked(), _settings(), {"cloudflare": cf, "openai": oai}) is True
    assert writes["m1"]["provider"] == "openai"


def test_a_refusal_about_the_picture_itself_is_final_and_nobody_else_is_asked(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=ProviderError("OpenAI rejected the request: rejected by our safety system"))
    oai = Fake("openai", result=PIC)
    assert media_generator.process_row(None, _picked(), _settings(), {"cloudflare": cf, "openai": oai}) is False
    assert writes["m1"]["status"] == "error" and "safety" in writes["m1"]["error"]
    assert oai.calls == [], "a content refusal is not retried elsewhere"
    assert writes["m1"]["provider"] == "cloudflare", "the row keeps the provider it was given"


def test_when_every_provider_fails_the_error_names_them_all(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=TimeoutError("slow"))
    oai = Fake("openai", exc=ProviderError("OpenAI refused the key (HTTP 401): check the OPENAI_API_KEY secret"))
    media_generator.process_row(None, _picked(), _settings(), {"cloudflare": cf, "openai": oai})
    w = writes["m1"]
    assert w["status"] == "error" and "refused the key" in w["error"] and "also failed: cloudflare: slow" in w["error"]


def test_a_video_row_skips_providers_that_make_pictures_only():
    s = _settings(replicate_token="rt")
    assert media_generator.provider_chain(s, "openai", kind="video") == ["openai", "replicate"]
    assert media_generator.provider_chain(s, "cloudflare", kind="image") == ["cloudflare", "replicate", "openai"]
    assert media_generator.provider_chain(s, "replicate", kind="image", needs_edit=True) == ["replicate", "cloudflare", "openai"]
    assert media_generator.provider_chain(_settings(openai_key=None), "cloudflare") == ["cloudflare"]
    assert media_generator.provider_chain(_settings(openai_key=None), "nope") == ["nope", "cloudflare"]


def test_gemini_joins_the_chain_only_when_its_pictures_are_on_and_a_key_can_be_used(monkeypatch):
    from fakestore import FakeStore

    from semasa import db, gemini_keys
    on = FakeStore(**{gemini_keys.TABLE: [{"id": "k1", "api_key": "AIza-1", "enabled": True, "status": "new"}]})
    assert media_generator.provider_chain(_settings(), "cloudflare", store=on) == ["cloudflare", "gemini", "openai"]
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

def test_chatgpt_is_a_picture_provider_that_takes_words_only_and_comes_first_with_kiosapi_last():
    from fakestore import FakeStore

    from semasa import chatgpt_login as cl
    tokens = {"access_token": "a", "refresh_token": "r"}
    on = FakeStore(**{cl.TABLE: [{"id": "main", "auth": {"tokens": tokens}, "enabled": True}]})
    assert media_generator.has_credentials("chatgpt", _settings(), on)
    assert not media_generator.has_credentials("chatgpt", _settings(), FakeStore(**{cl.TABLE: []}))
    assert not media_generator.has_credentials("chatgpt", _settings(), None)
    s = _settings()
    assert media_generator.provider_chain(s, "cloudflare", store=on) == ["cloudflare", "chatgpt", "openai"]
    assert media_generator.provider_chain(s, "cloudflare", store=on, explicit=False) == ["chatgpt", "cloudflare", "openai"]
    assert "chatgpt" not in media_generator.provider_chain(s, "cloudflare", needs_edit=True, store=on), "no reference picture"
    assert "chatgpt" not in media_generator.provider_chain(s, "cloudflare", kind="video", store=on)


def test_a_chatgpt_pin_for_the_picture_maker_puts_chatgpt_first_and_the_others_still_follow():
    from fakestore import FakeStore

    from semasa import chatgpt_login as cl
    tokens = {"access_token": "a", "refresh_token": "r"}
    login = {cl.TABLE: [{"id": "main", "auth": {"tokens": tokens}, "enabled": True}]}
    pin = {"key": "ai_team", "value": {"pins": {"image_gen": {"gateway": "chatgpt", "model": ""}}}}
    pinned = FakeStore(**login, semasa_settings=[pin])
    s = _settings()
    got = media_generator.provider_chain(s, "openai", store=pinned, explicit=False)
    assert got[0] == "chatgpt" and "cloudflare" in got and len(got) == len(set(got))          # first, and the rest still follow
    assert media_generator.provider_chain(s, "openai", store=pinned, explicit=True)[0] == "openai"   # a row's own choice is first
    assert "chatgpt" not in media_generator.provider_chain(s, "cloudflare", needs_edit=True, store=pinned)
    other = {"key": "ai_team", "value": {"pins": {"image_gen": {"gateway": "mireld", "model": "x"}}}}
    unpinned = media_generator.provider_chain(s, "openai", store=FakeStore(**login, semasa_settings=[other]), explicit=False)
    assert unpinned == ["chatgpt", "cloudflare", "openai"]     # no pin on ChatGPT: Wan's order already puts it first
    assert media_generator.pinned_picture_maker(None) == ""


def test_when_the_others_cannot_draw_chatgpt_does_and_the_row_says_so(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf = Fake("cloudflare", exc=ProviderError("the free 10,000 neurons for today are used up"))
    gpt = Fake("chatgpt", result=Generated(b"\x89PNG....", "image/png", "gpt-5.5", {}))
    s = _settings(openai_key=None)
    monkeypatch.setattr(media_generator, "has_credentials", lambda name, s, store=None: name in ("cloudflare", "chatgpt"))
    assert media_generator.process_row(None, _picked(), s, {"cloudflare": cf, "chatgpt": gpt}) is True
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

        def draw(self, prompt, size, model=None):
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


# ---- Wan's picture order (24 Nov 2026): ChatGPT > Cloudflare > Gemini > Replicate, KiosAPI LAST to save credit ---------

def test_the_picture_order_is_chatgpt_cloudflare_and_kiosapi_last_and_a_picked_provider_goes_first(monkeypatch):
    monkeypatch.setattr(media_generator, "has_credentials", lambda name, s, store=None: True)
    s = _settings()
    order = ["chatgpt", "cloudflare", "gemini", "replicate", "openai"]
    assert media_generator.provider_chain(s, "openai", explicit=False) == order
    picked = media_generator.provider_chain(s, "gemini", explicit=True)
    assert picked == ["gemini", "chatgpt", "cloudflare", "replicate", "openai"]
    # a reference picture: ChatGPT and Gemini draw from words only, so Cloudflare is the first asked and KiosAPI still the last
    assert media_generator.provider_chain(s, "openai", needs_edit=True, explicit=False) == ["cloudflare", "replicate", "openai"]
    video = media_generator.provider_chain(s, "gemini", kind="video", explicit=False)
    assert video == ["openai", "replicate"], "only video makers"


def test_a_row_stamped_with_the_default_provider_follows_wans_order_not_the_stamp(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf, oai = Fake("cloudflare", result=PIC), Fake("openai", result=PIC)
    row = {**ROW, "provider": "openai"}                     # Tetapan's stamp when the row was queued: a default, not a choice
    assert media_generator.process_row(None, row, _settings(), {"cloudflare": cf, "openai": oai}) is True
    assert writes["m1"]["provider"] == "cloudflare" and cf.calls and oai.calls == []    # no ChatGPT login: Cloudflare first


def test_a_provider_the_row_says_was_picked_keeps_its_place_and_an_unknown_one_is_still_reported(monkeypatch):
    writes, _ = _patch_db(monkeypatch)
    cf, oai = Fake("cloudflare", result=PIC), Fake("openai", result=PIC)
    row = {**ROW, "provider": "openai", "meta": {"provider_explicit": True}}
    assert media_generator.process_row(None, row, _settings(), {"cloudflare": cf, "openai": oai}) is True
    assert writes["m1"]["provider"] == "openai" and oai.calls and cf.calls == []
    row2 = {**ROW, "id": "m2", "provider": "nope"}
    assert media_generator.process_row(None, row2, _settings(), {"cloudflare": cf}) is False
    assert "unknown provider" in writes["m2"]["error"]


def test_cloudflares_nsfw_filter_is_marked_as_its_own_and_the_next_provider_draws_it():
    class R:
        status_code = 400
        text = ""

        def json(self):
            return {"success": False, "errors": [{"code": 8007, "message": "AiError: Input prompt contains NSFW content"}]}
    from semasa.providers.cloudflare import CloudflareProvider
    with pytest.raises(ProviderError) as e:
        CloudflareProvider._answer(object.__new__(CloudflareProvider), R(), "@cf/x")
    assert e.value.kind == "filter" and media_generator.error_kind(e.value) in media_generator.FAILOVER_KINDS


def test_chatgpt_draws_with_the_pinned_model_else_the_saved_one_and_reports_the_one_that_drew(monkeypatch):
    from fakestore import FakeStore

    from semasa import chatgpt_login as cl

    class Login:
        def __init__(self, store):
            self.saved, self.asked = "gpt-6.2-sol", []

        def connected(self):
            return True

        def settings(self):
            return {"model": self.saved}

        def draw(self, prompt, *, size, model):
            self.asked.append(model)
            if model == "gpt-refused":                 # the account refuses it: the login moves to another and saves it
                self.saved = "gpt-6.1-sol"
            return b"\x89PNG\r\n\x1a\n" + b"0" * 64

    monkeypatch.setattr(cl, "Login", Login)
    plain = media_generator.ChatGPTImageProvider(FakeStore())
    got = plain.generate_from_text("a flask", {})
    assert plain.login.asked == ["gpt-6.2-sol"] and got.model == "gpt-6.2-sol"       # the saved model, not DEFAULT_MODEL

    def pinned(model, gateway="chatgpt"):
        pin = {"key": "ai_team", "value": {"pins": {"image_gen": {"gateway": gateway, "model": model}}}}
        return media_generator.ChatGPTImageProvider(FakeStore(semasa_settings=[pin]))

    p = pinned("gpt-6-astra")
    assert p.generate_from_text("a flask", {}).model == "gpt-6-astra" and p.login.asked == ["gpt-6-astra"]
    other = pinned("gpt-image-2", gateway="kiosapi")                                  # another robot's pin is not ChatGPT's model
    assert other.generate_from_text("a flask", {}).model == "gpt-6.2-sol"
    moved = pinned("gpt-refused")
    assert moved.generate_from_text("a flask", {}).model == "gpt-6.1-sol"             # says the one that actually drew


def test_a_pinned_picture_model_is_drawn_by_the_image_tool_through_the_logins_chat_model(monkeypatch):
    from fakestore import FakeStore

    from semasa import chatgpt_login as cl

    class Login:
        def __init__(self, store):
            self.asked = []

        def connected(self):
            return True

        def settings(self):
            return {"model": "gpt-6.2-sol"}

        def draw(self, prompt, *, size, model, image_model=""):
            self.asked.append((model, image_model))
            return b"\x89PNG\r\n\x1a\n" + b"0" * 64

    monkeypatch.setattr(cl, "Login", Login)
    pin = {"key": "ai_team", "value": {"pins": {"image_gen": {"gateway": "chatgpt", "model": "gpt-image-2"}}}}
    p = media_generator.ChatGPTImageProvider(FakeStore(semasa_settings=[pin]))
    got = p.generate_from_text("a flask", {})
    assert p.login.asked == [("gpt-6.2-sol", "gpt-image-2")]
    assert got.model == "gpt-image-2" and got.meta == {"chatgpt_model": "gpt-6.2-sol", "chatgpt_image_model": "gpt-image-2"}
