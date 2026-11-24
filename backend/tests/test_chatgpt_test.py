"""The manual ChatGPT live test (semasa.chatgpt_test): its picture, and that one failing step does not hide the others."""

import io

from PIL import Image

from semasa import chatgpt_login as cl
from semasa import chatgpt_test as ct


class Login:
    def __init__(self, read="A red circle, a blue square and the text WS 4821", draw_exc=None):
        self.read, self.draw_exc, self.asked = read, draw_exc, []

    def settings(self):
        return {"model": "gpt-6.1-sol"}

    def write(self, system, user, *, model, timeout):
        self.asked.append("write")
        return "Na"

    def read_image(self, system, prompt, data, mime, *, model, timeout):
        self.asked.append("read")
        assert mime == "image/png" and Image.open(io.BytesIO(data)).size == (800, 460)
        return self.read

    def draw(self, prompt, *, model, timeout):
        self.asked.append("draw")
        if self.draw_exc:
            raise self.draw_exc
        buf = io.BytesIO()
        Image.new("RGB", (512, 512), "blue").save(buf, "PNG")
        return buf.getvalue()


def test_the_test_picture_is_a_real_png_with_the_things_a_reader_must_name():
    img = Image.open(io.BytesIO(ct.test_picture())).convert("RGB")
    assert img.size == (800, 460)
    assert img.getpixel((160, 180)) == (220, 30, 30) and img.getpixel((420, 180)) == (30, 60, 220)


def test_all_three_steps_pass_and_the_drawn_picture_is_saved(tmp_path):
    res = ct.run(Login(), tmp_path)
    assert [res[n]["ok"] for n in ("write", "read", "draw")] == [True, True, True]
    assert (tmp_path / "chatgpt-drawn.png").exists() and "512x512" in res["draw"]["detail"] and res["model"] == "gpt-6.1-sol"


def test_a_wrong_reading_and_a_refused_draw_are_reported_and_do_not_stop_the_other_steps(tmp_path):
    lg = Login(read="I see a picture", draw_exc=cl.ChatGPTError("usage limit reached", limit=True))
    res = ct.run(lg, tmp_path)
    assert res["write"]["ok"] and not res["read"]["ok"] and not res["draw"]["ok"]
    assert "usage limit" in res["draw"]["detail"] and lg.asked == ["write", "read", "draw"]
    assert not (tmp_path / "chatgpt-drawn.png").exists()


def test_the_result_is_recorded_for_the_api_tab_and_a_failed_step_says_so():
    from fakestore import FakeStore

    from semasa import db
    st = FakeStore()
    res = {"write": {"ok": True, "detail": "Na"}, "read": {"ok": True, "detail": "red blue 4821"},
           "draw": {"ok": False, "detail": "HTTP 402"}, "model": "gpt-6.2-sol"}
    value = ct.record(res, st)
    row = [r for r in st.tables[db.SETTINGS] if r["key"] == "ai_test_result"][0]["value"]
    assert row == value and row["ok"] is False and row["steps"]["draw"] == {"ok": False, "detail": "HTTP 402"}
    assert row["what"] == "chatgpt" and row["model"] == "gpt-6.2-sol" and row["at"]
    assert ct.record({k: {"ok": True, "detail": ""} for k in ("write", "read", "draw")}, st)["ok"] is True


def test_the_picture_is_drawn_with_the_model_pinned_for_the_picture_maker():
    from fakestore import FakeStore

    asked = {}

    class L(Login):
        def draw(self, prompt, *, model, timeout):
            asked["model"] = model
            return super().draw(prompt, model=model, timeout=timeout)

    res = ct.run(L(), draw_model="gpt-6-astra")
    assert asked["model"] == "gpt-6-astra" and res["draw_model"] == "gpt-6-astra"
    assert ct.run(L())["draw_model"] == "gpt-6.1-sol"                                 # no pin: the login's saved model
    pin = {"key": "ai_team", "value": {"pins": {"image_gen": {"gateway": "chatgpt", "model": "gpt-6-astra"}}}}
    assert ct.pinned_draw_model(FakeStore(semasa_settings=[pin])) == "gpt-6-astra"
    assert ct.pinned_draw_model(FakeStore()) == ""


# ---- which picture models the login draws with (24 Nov 2026) ----------------------------------------------------------------

def _png(size=(512, 512)):
    buf = io.BytesIO()
    Image.new("RGB", size, "blue").save(buf, "PNG")
    return buf.getvalue()


def test_the_probe_keeps_only_the_picture_models_that_really_drew_and_stops_when_the_allowance_is_used_up():
    from fakestore import FakeStore

    from semasa import db

    class L:
        def __init__(self):
            self.asked = []

        def settings(self):
            return {"model": "gpt-6.2-sol"}

        def draw_once(self, prompt, *, model, image_model, info=None):
            self.asked.append((model, image_model))
            if image_model == "gpt-image-2.5":
                raise cl.ChatGPTError("ChatGPT answered 400: Unknown parameter: 'tools[0].model'")
            if image_model == "gpt-image-2":
                info.update(model="gpt-image-2", size="1024x1024")
                return _png()
            if image_model == "gpt-image-1.5":                 # the server ignored the field and drew with its default
                info.update(model="gpt-image-2")
                return _png()
            raise cl.ChatGPTError("usage limit reached", limit=True)

    login = L()
    res = ct.probe_image_models(login, ("gpt-image-2.5", "gpt-image-2", "gpt-image-1.5", "gpt-image-1", "never-asked"))
    assert res["models"] == ["gpt-image-2"] and res["chat_model"] == "gpt-6.2-sol"
    assert [m for _c, m in login.asked] == ["gpt-image-2.5", "gpt-image-2", "gpt-image-1.5", "gpt-image-1"]   # then stopped
    assert all(c == "gpt-6.2-sol" for c, _m in login.asked)             # every picture asked through the login's chat model
    assert "Unknown parameter" in res["tried"]["gpt-image-2.5"]["error"]
    assert res["tried"]["gpt-image-1.5"]["ok"] is False and "drew with gpt-image-2" in res["tried"]["gpt-image-1.5"]["error"]
    st = FakeStore()
    ct.record_image_models(res, st)
    kept = {r["key"]: r["value"] for r in st.tables[db.SETTINGS]}
    assert kept[cl.IMAGE_MODELS_KEY]["models"] == ["gpt-image-2"]
    assert kept["ai_test_result"]["what"] == ct.MODE_IMAGE_MODELS and kept["ai_test_result"]["ok"] is True
    # a probe that could try nothing (allowance already gone) keeps the last good list
    ct.record_image_models({"chat_model": "x", "tried": {}, "models": []}, st)
    assert {r["key"]: r["value"] for r in st.tables[db.SETTINGS]}[cl.IMAGE_MODELS_KEY]["models"] == ["gpt-image-2"]


def test_a_pinned_picture_model_is_the_tools_model_and_the_chat_model_stays_the_logins():
    asked = {}

    class L(Login):
        def draw(self, prompt, *, model, timeout, image_model=""):
            asked.update(model=model, image_model=image_model)
            return super().draw(prompt, model=model, timeout=timeout)

    ct.run(L(), draw_model="gpt-image-2")
    assert asked == {"model": "gpt-6.1-sol", "image_model": "gpt-image-2"}
    ct.run(L(), draw_model="gpt-6-astra")
    assert asked == {"model": "gpt-6-astra", "image_model": ""}


def test_the_mode_comes_from_the_workflow_input_or_the_pages_request(monkeypatch):
    from fakestore import FakeStore
    req = FakeStore(semasa_settings=[{"key": "ai_test", "value": {"what": "chatgpt_image_models"}}])
    monkeypatch.delenv("CHATGPT_TEST_MODE", raising=False)
    monkeypatch.delenv("GITHUB_EVENT_NAME", raising=False)
    assert ct.wanted_mode(req, ["x"]) == ""                              # run by hand: the page's old request is not obeyed
    monkeypatch.setenv("GITHUB_EVENT_NAME", "repository_dispatch")
    assert ct.wanted_mode(req, ["x"]) == ct.MODE_IMAGE_MODELS            # the page's button
    assert ct.wanted_mode(FakeStore(), ["x"]) == ""
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("CHATGPT_TEST_MODE", "image-models")
    assert ct.wanted_mode(FakeStore(), ["x"]) == ct.MODE_IMAGE_MODELS    # the workflow's own input
