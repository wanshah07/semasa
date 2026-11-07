"""Motion's ChatGPT login (Wan, 5 Nov 2026): the saved tokens are kept fresh and a picture is drawn for each scene of the
storyboard. Every test uses fake HTTP and an in-memory store; nothing here reaches OpenAI."""

import base64
import io
import json
import os
from datetime import UTC, datetime, timedelta

import pytest
import requests
from fakestore import FakeStore
from PIL import Image

from semasa import chatgpt_login as cl
from semasa import motion_gpt_images as gi

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)


def jwt(**claims) -> str:
    def part(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part(claims)}.sig"


def picture(side=400) -> bytes:
    """A real picture that does not compress to nothing (the 'empty picture' check is a byte floor)."""
    buf = io.BytesIO()
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(buf, "PNG")
    return buf.getvalue()


def sse(*events) -> list[str]:
    out = []
    for ev in events:
        out += [f"event: {ev.get('type')}", "data: " + json.dumps(ev), ""]
    return out


def done_event(png: bytes) -> list[str]:
    return sse({"type": "response.created", "response": {}},
               {"type": "response.output_item.done",
                "item": {"type": "image_generation_call", "result": base64.b64encode(png).decode()}},
               {"type": "response.completed", "response": {"output": []}})


class Resp:
    def __init__(self, code=200, lines=None, text="", body=None):
        self.status_code, self.lines, self.text, self.body = code, lines or [], text, body or {}

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)

    def json(self):
        return self.body


class Http:
    """Answers each post() from a queue and remembers what was sent."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def tokens(minutes_left=600, refresh="r-1", access=None):
    exp = int((NOW + timedelta(minutes=minutes_left)).timestamp())
    return {"access_token": access or jwt(exp=exp), "refresh_token": refresh, "id_token": jwt(exp=exp, email="wan@example.com"),
            "account_id": "acct-1"}


def store(minutes_left=600, **row):
    base = {"id": "main", "auth": {"tokens": tokens(minutes_left)}, "enabled": True, "model": "gpt-5", "max_images": 6}
    return FakeStore(**{cl.TABLE: [{**base, **row}]})


def login(st, http=None):
    return cl.Login(st, http=http or Http(), sleep=lambda s: None, now=lambda: NOW)


# ---- tokens ----------------------------------------------------------------------------------------------------------------

def test_claims_expiry_and_account_are_read_off_the_tokens():
    t = jwt(exp=1_900_000_000, **{"https://api.openai.com/auth": {"chatgpt_account_id": "acct-9"}})
    assert cl.expiry(t) == datetime.fromtimestamp(1_900_000_000, UTC)
    assert cl.account_of({"id_token": t}) == "acct-9"
    assert cl.account_of({"account_id": "acct-1", "id_token": t}) == "acct-1"          # the saved one wins
    assert cl.claims("not a token") == {} and cl.expiry("not a token") is None


def test_settings_are_none_until_a_login_is_saved():
    assert login(FakeStore()).settings() is None
    assert login(FakeStore(**{cl.TABLE: [{"id": "main", "auth": {"tokens": {"access_token": "x"}}}]})).settings() is None
    assert login(store(max_images=3, model="gpt-5.1")).settings() == {"enabled": True, "model": "gpt-5.1", "max_images": 3}


# ---- refresh ---------------------------------------------------------------------------------------------------------------

def test_a_fresh_access_token_is_used_without_a_refresh():
    http = Http()
    access, acct = login(store(600), http).refresh()
    assert acct == "acct-1" and access and http.calls == []


def test_an_ending_access_token_is_refreshed_and_the_new_pair_saved_at_once():
    st = store(minutes_left=2)
    new_access = jwt(exp=int((NOW + timedelta(days=9)).timestamp()))
    http = Http(Resp(200, body={"access_token": new_access, "refresh_token": "r-2", "id_token": "idt"}))
    access, _ = login(st, http).refresh()
    assert access == new_access
    url, kw = http.calls[0]
    assert url == cl.ISSUER + "/oauth/token"
    assert kw["json"]["client_id"] == cl.CLIENT_ID and kw["json"]["grant_type"] == "refresh_token"
    assert kw["json"]["refresh_token"] == "r-1"
    saved = st.tables[cl.TABLE][0]
    assert saved["auth"]["tokens"]["refresh_token"] == "r-2" and saved["auth"]["tokens"]["account_id"] == "acct-1"
    assert saved["access_expires_at"].startswith("2026-11-14")


def test_a_refused_refresh_uses_what_another_run_just_saved():
    st = store(minutes_left=2)

    class Racing(Http):
        def post(self, url, **kw):                       # while this run waits on OpenAI, another run refreshes and saves
            st.tables[cl.TABLE][0]["auth"] = {"tokens": tokens(600, refresh="r-2")}
            return super().post(url, **kw)

    access, _ = login(st, Racing(Resp(400, text="refresh_token_reused"))).refresh()
    assert access == st.tables[cl.TABLE][0]["auth"]["tokens"]["access_token"]


def test_a_refused_refresh_with_nothing_newer_says_to_log_in_again():
    lg = login(store(minutes_left=2), Http(Resp(401, text="invalid_grant")))
    with pytest.raises(cl.ChatGPTError) as e:
        lg.refresh()
    assert e.value.auth and "codex login" in str(e.value)


def test_check_refreshes_for_real_and_records_the_outcome_without_claiming_a_picture():
    st = store(600)
    new_access = jwt(exp=int((NOW + timedelta(days=9)).timestamp()))
    http = Http(Resp(200, body={"access_token": new_access, "refresh_token": "r-2"}))
    assert login(st, http).check() == "ChatGPT login: accepted"
    assert len(http.calls) == 1                                         # a fresh token is still refreshed: that is the proof
    row = st.tables[cl.TABLE][0]
    assert row["checked_at"] and row["last_error"] is None and not row.get("last_ok_at"), "no picture has been drawn yet"
    assert row["auth"]["tokens"]["refresh_token"] == "r-2"
    bad = store(2)
    assert "refused" in login(bad, Http(Resp(401))).check()
    assert "refused" in bad.tables[cl.TABLE][0]["last_error"]


# ---- the stream ------------------------------------------------------------------------------------------------------------

def test_read_stream_takes_the_picture_off_the_item_done_event():
    png = picture()
    assert cl.read_stream(done_event(png)) == png


def test_read_stream_falls_back_to_the_completed_output():
    png = picture()
    lines = sse({"type": "response.completed", "response": {"output": [
        {"type": "image_generation_call", "result": base64.b64encode(png).decode()}]}})
    assert cl.read_stream(lines) == png


def test_read_stream_raises_on_an_error_event_and_marks_a_limit():
    with pytest.raises(cl.ChatGPTError) as e:
        cl.read_stream(sse({"type": "response.failed", "response": {"error": {"message": "You have hit the usage limit"}}}))
    assert e.value.limit and "usage limit" in str(e.value)
    with pytest.raises(cl.ChatGPTError) as e2:
        cl.read_stream(sse({"type": "error", "message": "bad request"}))
    assert not e2.value.limit


def test_read_stream_with_no_picture_names_what_the_model_said_instead():
    lines = sse({"type": "response.output_text.delta", "delta": "I cannot draw that."},
                {"type": "response.completed", "response": {}})
    with pytest.raises(cl.ChatGPTError) as e:
        cl.read_stream(lines)
    assert "without a picture" in str(e.value) and "cannot draw" in str(e.value)


def test_a_tiny_picture_is_refused():
    tiny = base64.b64encode(b"x" * 20).decode()
    with pytest.raises(cl.ChatGPTError):
        cl.read_stream(sse({"type": "response.output_item.done", "item": {"type": "image_generation_call", "result": tiny}}))


# ---- drawing ---------------------------------------------------------------------------------------------------------------

def test_draw_sends_the_codex_call_with_the_account_and_the_forced_picture_tool():
    png = picture()
    http = Http(Resp(200, done_event(png)))
    assert login(store(), http).draw("a lab bench", size="1024x1536", model="gpt-5") == png
    url, kw = http.calls[0]
    assert url == cl.RESPONSES and kw["stream"] is True
    assert kw["headers"]["chatgpt-account-id"] == "acct-1" and kw["headers"]["Authorization"].startswith("Bearer ")
    body = kw["json"]
    assert body["model"] == "gpt-5" and body["store"] is False and body["stream"] is True
    assert body["tools"] == [{"type": "image_generation", "size": "1024x1536"}]
    assert body["tool_choice"] == {"type": "image_generation"}
    assert body["input"][0]["content"][0]["text"] == "a lab bench"


def test_a_400_steps_down_to_a_plainer_call_and_never_loops():
    png = picture()
    http = Http(Resp(400, text="unknown parameter size"), Resp(400, text="tool_choice"), Resp(200, done_event(png)))
    assert login(store(), http).draw("x") == png
    bodies = [c[1]["json"] for c in http.calls]
    assert "size" in bodies[0]["tools"][0] and "size" not in bodies[1]["tools"][0]
    assert "tool_choice" in bodies[0] and "tool_choice" in bodies[1] and "tool_choice" not in bodies[2]
    with pytest.raises(cl.ChatGPTError):
        login(store(), Http(Resp(400), Resp(400), Resp(400))).draw("x")


def test_a_401_refreshes_once_and_tries_again():
    png = picture()
    new_access = jwt(exp=int((NOW + timedelta(days=9)).timestamp()))
    http = Http(Resp(401), Resp(200, body={"access_token": new_access, "refresh_token": "r-2"}), Resp(200, done_event(png)))
    assert login(store(), http).draw("x") == png
    assert http.calls[2][1]["headers"]["Authorization"] == f"Bearer {new_access}"
    # a second 401 is the login, not luck
    with pytest.raises(cl.ChatGPTError) as e:
        login(store(), Http(Resp(401), Resp(200, body={"access_token": new_access}), Resp(401))).draw("x")
    assert e.value.auth


def test_a_429_is_a_limit_and_a_5xx_is_retried_once():
    with pytest.raises(cl.ChatGPTError) as e:
        login(store(), Http(Resp(429, text="usage limit reached"))).draw("x")
    assert e.value.limit
    png = picture()
    assert login(store(), Http(Resp(503), Resp(200, done_event(png)))).draw("x") == png
    with pytest.raises(cl.ChatGPTError):
        login(store(), Http(Resp(503), Resp(503))).draw("x")
    assert login(store(), Http(requests.ConnectionError("down"), Resp(200, done_event(png)))).draw("x") == png


# ---- the storyboard --------------------------------------------------------------------------------------------------------

PAL = {"ground": "#e5f6ed", "ink": "#143e35", "accent": "#287b65"}
SCENES = [
    {"id": "s1", "role": "hook", "heading": "Tahukah anda?", "lines": ["Notifikasi bukan kelulusan"],
     "narration": "Satu perkara penting."},
    {"id": "s2", "role": "fact", "heading": "Fakta", "lines": [], "narration": "Bahan ini dihadkan."},
    {"id": "s3", "role": "why", "heading": "Kenapa", "lines": [], "narration": "Sebab keselamatan."},
    {"id": "s4", "role": "solution", "heading": "Solusi", "lines": [], "narration": "Semak label."},
    {"id": "brand-outro", "heading": "Follow", "lines": [], "narration": ""},
]
ROW = {"id": "m1", "stream": "regulab", "brief": "label rules for cosmetics"}


def test_a_scene_prompt_carries_the_story_the_style_and_the_rules():
    p = gi.scene_prompt(ROW, SCENES[0], design="continuous-line", palette=PAL, ambient="lime", style_name="acme/line-style")
    assert "Tahukah anda?" in p and "Notifikasi bukan kelulusan" in p and "Satu perkara penting" in p
    assert "label rules for cosmetics" in p and "arresting establishing image" in p
    assert "continuous hand-drawn line" in p and "#e5f6ed" in p and "lime ambient" in p and "acme/line-style" in p
    assert "No text" in p and "no logos" in p and "never evidence" in p
    li = gi.scene_prompt({**ROW, "stream": "linkedin"}, SCENES[1], design="bright-editorial", palette=PAL, ambient="")
    assert "sober, credible" in li and "editorial" in li and "ambient" not in li


def test_the_storyboard_skips_the_closing_card_and_respects_the_limit():
    assert [s["id"] for s in gi.storyboard(SCENES, 6)] == ["s1", "s2", "s3", "s4"]
    assert [s["id"] for s in gi.storyboard(SCENES, 2)] == ["s1", "s2"]
    assert gi.storyboard(SCENES, 0) == []


class FakeLogin:
    def __init__(self, cfg=None, errors=None):
        self.cfg, self.errors, self.asked, self.sizes = cfg, list(errors or []), [], []
        self.oks, self.fails = 0, []

    def settings(self):
        return self.cfg

    def draw(self, prompt, *, size, model):
        self.asked.append(prompt)
        self.sizes.append((size, model))
        if self.errors:
            e = self.errors.pop(0)
            if e:
                raise e
        return picture(300)

    def ok(self):
        self.oks += 1

    def failed(self, m):
        self.fails.append(m)


CFG = {"enabled": True, "model": "gpt-5", "max_images": 6}


def draw(tmp_path, lg, scenes=None, resolution="portrait", clock=None):
    return gi.draw_scenes(None, ROW, scenes or SCENES, tmp_path, design="bright-editorial", palette=PAL, ambient="mint",
                          resolution=resolution, style_name="", login=lg, clock=clock)


def test_one_picture_is_drawn_per_scene_and_saved_as_a_jpeg(tmp_path):
    lg = FakeLogin(CFG)
    drawn, note = draw(tmp_path, lg)
    assert list(drawn) == ["s1", "s2", "s3", "s4"] and len(lg.asked) == 4 and lg.oks == 1
    assert lg.sizes[0] == ("1024x1536", "gpt-5")
    assert drawn["s2"]["path"] == "assets/scene-s2.jpg" and drawn["s2"]["generated"] and drawn["s2"]["credit"] == ""
    assert Image.open(tmp_path / "assets/scene-s2.jpg").format == "JPEG"
    assert note == "ChatGPT pictures: 4 of 4 scenes drawn"


def test_the_frame_shape_follows_the_film(tmp_path):
    lg = FakeLogin(CFG)
    draw(tmp_path, lg, scenes=SCENES[:1], resolution="landscape")
    draw(tmp_path, lg, scenes=SCENES[:1], resolution="square")
    assert [s for s, _ in lg.sizes] == ["1536x1024", "1024x1024"]


def test_no_login_and_switched_off_draw_nothing(tmp_path):
    assert draw(tmp_path, FakeLogin(None)) == ({}, "")
    drawn, note = draw(tmp_path, FakeLogin({**CFG, "enabled": False}))
    assert drawn == {} and "switched off" in note


def test_a_scene_that_fails_keeps_the_others_and_says_so(tmp_path):
    lg = FakeLogin(CFG, errors=[None, cl.ChatGPTError("picture came back empty"), None, None])
    drawn, note = draw(tmp_path, lg)
    assert list(drawn) == ["s1", "s3", "s4"] and "3 of 4" in note and "s2 (ChatGPT): picture came back empty" in note


def test_a_limit_or_a_refused_login_stops_the_rest_of_the_film(tmp_path):
    lg = FakeLogin(CFG, errors=[None, cl.ChatGPTError("usage limit", limit=True)])
    drawn, note = draw(tmp_path, lg)
    assert list(drawn) == ["s1"] and len(lg.asked) == 2 and "usage limit" in note and lg.fails
    lg2 = FakeLogin(CFG, errors=[cl.ChatGPTError("refused", auth=True)])
    assert draw(tmp_path, lg2)[0] == {} and len(lg2.asked) == 1


def test_the_time_budget_stops_drawing(tmp_path):
    ticks = iter([0, 1, gi.BUDGET_S + 5, gi.BUDGET_S + 6, gi.BUDGET_S + 7])
    drawn, note = draw(tmp_path, FakeLogin(CFG), clock=lambda: next(ticks))
    assert list(drawn) == ["s1"] and "out of time" in note


def test_max_images_limits_the_scenes(tmp_path):
    lg = FakeLogin({**CFG, "max_images": 2})
    assert list(draw(tmp_path, lg)[0]) == ["s1", "s2"]


def test_a_picture_that_is_not_a_picture_is_a_note_not_a_crash(tmp_path):
    class Junk(FakeLogin):
        def draw(self, prompt, *, size, model):
            return b"not an image at all" * 200
    drawn, note = draw(tmp_path, Junk(CFG), scenes=SCENES[:1])
    assert drawn == {} and "s1 (ChatGPT):" in note


def test_pin_replaces_the_scene_photo_and_drops_the_pair_partner():
    scenes = [{"id": "s1", "photo": "assets/photo-1.jpg", "photo2": "assets/photo-2.jpg", "photo_credit": "A / Unsplash"},
              {"id": "s2", "photo": "assets/photo-3.jpg", "photo_credit": "B / Unsplash"}]
    drawn = {"s1": {"path": "assets/scene-s1.jpg", "credit": ""}}
    gi.pin(scenes, drawn)
    assert scenes[0] == {"id": "s1", "photo": "assets/scene-s1.jpg", "photo_credit": ""}
    assert scenes[1]["photo"] == "assets/photo-3.jpg"                          # a scene that was not drawn is left alone
    photos = [{"path": "assets/photo-1.jpg"}, {"path": "assets/photo-2.jpg"}, {"path": "assets/photo-3.jpg"}]
    assert gi.used(scenes, photos) == [{"path": "assets/photo-3.jpg"}]


# ---- in the worker ---------------------------------------------------------------------------------------------------------

@pytest.mark.composed
def test_a_film_shows_the_picture_drawn_for_each_scene_and_reports_it(tmp_path, monkeypatch):
    from test_motion import NOW, FakeLLM, Store, _row, _runner, fake_speak

    from semasa import motion
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)
    store = Store()
    row = _row(store, language="bm", voice="male")
    plan = {"title": "t", "photo_query": "lab", "scenes": [
        {"heading": f"Tajuk {i}", "lines": ["Denda 50% kes", "Sejak 2018 dan 2026 syarat baharu"],
         "narration": "Satu dua tiga empat lima enam."} for i in range(4)]}
    lg = FakeLogin(CFG)
    assert motion.process(store, FakeLLM([plan]), {**row, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                          runner=_runner(), workdir=tmp_path, now=NOW, gpt_login=lg)
    got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "done" and "ChatGPT pictures: 4 of 4 scenes drawn" in got["style_note"]
    assert len(lg.asked) == 4 and all("Tajuk" in p for p in lg.asked)
    ids = [p["id"] for p in got["check_report"]["photos"]]
    assert sorted(ids) == [f"chatgpt-s{i}" for i in range(1, 5)]
    html = next(tmp_path.rglob("index.html")).read_text(encoding="utf-8")
    assert all(f"assets/scene-s{i}.jpg" in html for i in range(1, 5))


@pytest.mark.composed
def test_a_film_without_the_login_is_made_exactly_as_before(tmp_path, monkeypatch):
    from test_motion import NOW, FakeLLM, Store, _row, _runner, fake_speak

    from semasa import motion
    monkeypatch.setattr(motion.voice_mod, "speak", fake_speak)
    store = Store()
    row = _row(store, language="bm", voice="male")
    plan = {"title": "t", "photo_query": "lab", "scenes": [
        {"heading": f"Tajuk {i}", "lines": ["Denda 50% kes"], "narration": "Satu dua tiga empat lima enam."} for i in range(4)]}
    assert motion.process(store, FakeLLM([plan]), {**row, "attempts": 1}, {"prompt": "", "cli": "0.8.188"},
                          runner=_runner(), workdir=tmp_path, now=NOW)
    got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert got["status"] == "done" and "ChatGPT" not in got["style_note"]


# ---- a refused model (7 Nov 2026: "The 'gpt-5' model is not supported when using Codex with a ChatGPT account") ---------------

REFUSED = ('{"detail":"The \'gpt-5\' model is not supported when using Codex with a ChatGPT account.","error":{"type":'
           '"invalid_request_error","code":"model_not_found"}}')


def words(text):
    return sse({"type": "response.output_text.delta", "delta": text}, {"type": "response.completed", "response": {}})


class Http2(Http):
    """Http plus get() for the account's model list."""

    def __init__(self, *answers, listed=None):
        super().__init__(*answers)
        self.listed, self.gets = listed, []

    def get(self, url, **kw):
        self.gets.append((url, kw))
        if self.listed is None:
            return Resp(404, text="no list")
        return Resp(200, body={"models": [{"slug": m} for m in self.listed]})


def test_a_refused_model_moves_to_one_the_account_lists_and_is_saved():
    st = store()
    http = Http2(Resp(400, text=REFUSED), Resp(200, lines=words("OK")), listed=["gpt-5.5", "gpt-5.4"])
    assert login(st, http).write("sys", "user", model="gpt-5") == "OK"
    assert [kw["json"]["model"] for _, kw in http.calls] == ["gpt-5", "gpt-5.5"]
    assert st.tables[cl.TABLE][0]["model"] == "gpt-5.5", "the next call starts on the model that answered"
    assert http.gets[0][0].endswith("/backend-api/codex/models")


def test_with_no_list_the_fallbacks_are_tried_and_a_picture_is_drawn():
    st, png = store(), picture()
    http = Http2(Resp(400, text=REFUSED), Resp(400, text=REFUSED.replace("gpt-5", "gpt-5.5")), Resp(200, lines=done_event(png)))
    assert login(st, http).draw("a lab", model="gpt-5") == png
    assert [kw["json"]["model"] for _, kw in http.calls] == ["gpt-5", "gpt-5.5", "gpt-5.4"]
    assert st.tables[cl.TABLE][0]["model"] == "gpt-5.4"


def test_every_model_refused_says_which_were_tried_and_another_error_is_not_retried_as_a_model():
    st = store()
    http = Http2(*[Resp(400, text=REFUSED) for _ in range(6)], listed=[])
    with pytest.raises(cl.ChatGPTError) as e:
        login(st, http).write("s", "u", model="gpt-5")
    assert e.value.model and "Tried gpt-5, gpt-5.5, gpt-5.4, gpt-5.3-codex, gpt-5.2-codex" in str(e.value)
    assert len(http.calls) == 1 + cl.MODEL_TRIES
    http2 = Http2(Resp(429, text="usage limit reached"))
    with pytest.raises(cl.ChatGPTError) as e2:
        login(store(), http2).write("s", "u")
    assert e2.value.limit and not e2.value.model and len(http2.calls) == 1


def test_chatgpt_is_a_robot_on_the_api_page():
    st = store()
    http = Http2(Resp(400, text=REFUSED), Resp(200, lines=words("OK")), listed=["gpt-5.5"])
    row = login(st, http).probe_row()
    assert row["slug"] == "chatgpt" and row["name"] == "ChatGPT (Wanshah 5)"
    assert row["chat_ok"] and row["key_ok"] and row["model"] == "gpt-5.5" and row["models"] == ["gpt-5.5"] and row["model_listed"]
    off = cl.Login(FakeStore(**{cl.TABLE: []}), http=Http2(), sleep=lambda s: None, now=lambda: NOW).probe_row()
    assert not off["chat_ok"] and "not connected" in off["error"]


def test_the_default_model_is_one_a_chatgpt_account_accepts():
    # 7 Nov 2026: "The 'gpt-5' model is not supported when using Codex with a ChatGPT account"
    assert cl.DEFAULT_MODEL == "gpt-5.5" == cl.FALLBACK_MODELS[0]
