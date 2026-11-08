"""Gemini with several API keys, picked automatically (Wan, 6 Nov 2026): the pool, the AI-team candidate, the picture call,
and the provider chain Motion draws its scene pictures with. Fake HTTP and an in-memory store; nothing here reaches Google."""
from __future__ import annotations

import base64
import io
import os
from datetime import UTC, datetime, timedelta

import pytest
import requests
from fakestore import FakeStore
from PIL import Image

from semasa import ai_team, chatgpt_login, db, gemini_images, gemini_keys, motion_gpt_images
from semasa.config import LLMSettings

NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)


def key(i, **over):
    return {"id": f"k{i}", "label": f"Key {i}", "hint": f"…{i}{i}{i}{i}", "api_key": f"AIza-secret-{i}", "enabled": True,
            "status": "new", "cooldown_until": None, "last_ok_at": None, "last_used_at": None, "calls": 0, "failures": 0, **over}


def store(*keys, settings=None):
    t = {gemini_keys.TABLE: list(keys)}
    if settings is not None:
        t[db.SETTINGS] = [{"key": "gemini", "value": settings}]
    return FakeStore(**t)


def png(side=300) -> bytes:
    buf = io.BytesIO()
    Image.frombytes("RGB", (side, side), os.urandom(side * side * 3)).save(buf, "PNG")
    return buf.getvalue()


# ---- classifying what Google said --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text,kind", [
    ("429 RESOURCE_EXHAUSTED: quota exceeded for metric", "limited"),
    ("You exceeded your current quota", "limited"),
    ("429 Too Many Requests", "limited"),
    ('400 {"error": {"message": "API key not valid. Please pass a valid API key."}}', "bad"),
    ("403 PERMISSION_DENIED: the API key has been disabled", "bad"),
    ("401 UNAUTHENTICATED", "bad"),
    ("500 Internal error", "retry"), ("could not reach Gemini: timed out", "retry"), ("", "retry"), (None, "retry")])
def test_classify(text, kind):
    assert gemini_keys.classify(text) == kind


# ---- the pool ----------------------------------------------------------------------------------------------------------------

def test_usable_skips_off_bad_and_cooling_keys_and_goes_least_recently_used_first():
    soon, later = (NOW + timedelta(minutes=5)).isoformat(), (NOW - timedelta(minutes=5)).isoformat()
    rows = [key(1, last_used_at=(NOW - timedelta(minutes=1)).isoformat()),
            key(2, last_used_at=(NOW - timedelta(hours=2)).isoformat()),
            key(3), key(4, enabled=False), key(5, status="bad"), key(6, status="limited", cooldown_until=soon),
            key(7, status="limited", cooldown_until=later, last_used_at=(NOW - timedelta(hours=3)).isoformat())]
    assert [r["id"] for r in gemini_keys.usable(rows, NOW)] == ["k3", "k7", "k2", "k1"]


def test_note_marks_a_key_by_what_happened_to_it():
    st = store(key(1), key(2), key(3), key(4))
    rows = st.tables[gemini_keys.TABLE]
    assert gemini_keys.note(st, rows[0], True, now=NOW) == "ok"
    assert rows[0]["status"] == "ok" and rows[0]["last_ok_at"] == NOW.isoformat() and rows[0]["calls"] == 1
    assert gemini_keys.note(st, rows[1], False, "429 RESOURCE_EXHAUSTED", NOW) == "limited"
    assert rows[1]["status"] == "limited" and rows[1]["cooldown_until"] == (NOW + timedelta(minutes=30)).isoformat()
    assert gemini_keys.note(st, rows[2], False, "400 API key not valid", NOW) == "bad"
    assert rows[2]["status"] == "bad" and rows[2]["cooldown_until"] is None and "not valid" in rows[2]["last_error"]
    assert gemini_keys.note(st, rows[3], False, "503 busy", NOW) == "retry"
    assert rows[3]["cooldown_until"] == (NOW + timedelta(minutes=2)).isoformat() and rows[3]["failures"] == 1
    gemini_keys.note(st, rows[1], True, now=NOW)                                  # a key that answers again is clean
    assert rows[1]["status"] == "ok" and rows[1]["cooldown_until"] is None and rows[1]["last_error"] is None


def test_pick_takes_a_recently_good_key_without_a_question_and_asks_any_other():
    fresh = key(1, status="ok", last_ok_at=(NOW - timedelta(minutes=3)).isoformat())
    asked = []

    def ask(row):
        asked.append(row["id"])
        return True, 200, ""
    got, ms = gemini_keys.pick(store(fresh), NOW, ask)
    assert got["id"] == "k1" and ms is None and asked == []
    got, ms = gemini_keys.pick(store(key(2)), NOW, ask)
    assert got["id"] == "k2" and ms == 200 and asked == ["k2"]


def test_pick_moves_on_from_a_key_that_fails_and_remembers_why():
    st = store(key(1), key(2), key(3))

    def ask(row):
        return (row["id"] == "k3"), 150, "429 quota exceeded" if row["id"] == "k1" else "400 API key not valid"
    got, ms = gemini_keys.pick(st, NOW, ask)
    assert got["id"] == "k3" and ms == 150
    rows = {r["id"]: r for r in st.tables[gemini_keys.TABLE]}
    assert rows["k1"]["status"] == "limited" and rows["k2"]["status"] == "bad" and rows["k3"]["status"] == "ok"


def test_pick_gives_up_after_three_keys_and_returns_none_when_nothing_works():
    st = store(*(key(i) for i in range(1, 6)))
    asked = []

    def ask(row):
        asked.append(row["id"])
        return False, None, "503"
    assert gemini_keys.pick(st, NOW, ask) == (None, None) and len(asked) == gemini_keys.TRIES
    assert gemini_keys.pick(store(), NOW, ask) == (None, None)
    assert gemini_keys.pick(FakeStore(), NOW, ask) == (None, None), "061 not applied: Gemini is simply off"


def test_without_a_question_the_first_usable_key_is_taken():
    got, ms = gemini_keys.pick(store(key(1), key(2)), NOW, None)
    assert got["id"] == "k1" and ms is None


def test_settings_default_and_are_cleaned():
    base = gemini_keys.load_settings(FakeStore())
    assert {k: base[k] for k in gemini_keys.DEFAULTS if k not in ("model", "image_model")} == {
        **{k: v for k, v in gemini_keys.DEFAULTS.items() if k not in ("model", "image_model")}, "jobs": ["motion", "ideas"]}
    assert base["model_setting"] == base["image_model_setting"] == "auto"
    assert base["model"] == gemini_keys.FALLBACK_TEXT, "auto, nothing listed yet"
    assert base["image_model"] == gemini_keys.FALLBACK_IMAGE
    got = gemini_keys.load_settings(store(settings={"jobs": ["reader", "weird", "motion"], "max_images": 99,
                                                    "model": "gemini-x", "enabled": False}))
    assert got["jobs"] == ["reader", "motion"] and got["max_images"] == 8 and got["model"] == "gemini-x"
    assert got["enabled"] is False
    assert gemini_keys.load_settings(store(settings={"model": ""}))["model"] == gemini_keys.FALLBACK_TEXT


# ---- the AI team -------------------------------------------------------------------------------------------------------------

class Live:
    def __init__(self, works=True):
        self.works, self.asked = works, []

    def chat(self, c, model, timeout=12):
        self.asked.append((c["slug"], c["key"], model))
        ok = self.works(c["key"]) if callable(self.works) else self.works
        return (True, 120, "") if ok else (False, 30, "429 RESOURCE_EXHAUSTED")

    def models(self, c, timeout=12):
        return []


def slow():
    """rootsys and Mireld probed an hour ago and DOWN, so a healthy Gemini is the first robot that can write (Wan's order,
    8 Nov 2026, puts it last, so only the others being down brings it forward)."""
    return [{"slug": s, "chat_ok": False, "chat_ms": 5000, "error": "502", "checked_at": (NOW - timedelta(hours=1)).isoformat()}
            for s in ("rootsys", "mireld")]


def github(**kw):
    base = dict(provider="openai", api_key="sk-root", base_url="https://rootsys.cloud/v1", model="gpt-4.1-mini", timeout=30,
                fallback_base_url="https://api.mireld.my/v1", fallback_key="mk-1", fallback_model="claude-sonnet-5.5")
    base.update(kw)
    return LLMSettings(**base)


def test_gemini_is_a_candidate_only_for_the_jobs_wan_allows():
    st = store(key(1))
    for job, expect in (("motion", True), ("ideas", True), ("reader", False)):
        cand, _ = gemini_keys.candidate(st, job, None, NOW)
        assert (cand is not None) is expect, job
    cand, _ = gemini_keys.candidate(st, "motion", None, NOW)
    assert cand["slug"] == "gemini" and cand["robot"] == "W4" and cand["name"] == "Wanshah 4"
    assert cand["base_url"] == gemini_keys.BASE and cand["key"] == "AIza-secret-1" and cand["model"] == gemini_keys.FALLBACK_TEXT
    wide = store(key(1), settings={"jobs": ["reader", "motion", "ideas"]})
    assert gemini_keys.candidate(wide, "reader", None, NOW)[0] is not None
    assert gemini_keys.candidate(store(key(1), settings={"enabled": False}), "motion", None, NOW) == (None, None)
    assert gemini_keys.candidate(store(), "motion", None, NOW) == (None, None)


def test_the_key_goes_only_to_the_gemini_host():
    cand, _ = gemini_keys.candidate(store(key(1)), "motion", None, NOW)
    assert cand["base_url"].startswith("https://generativelanguage.googleapis.com/") and not cand["blocked"]


def test_the_motion_job_can_route_to_gemini_and_a_reader_job_never_does(monkeypatch):
    # Gemini is last in Wan's order: it writes the motion job only when rootsys and Mireld are down
    st = store(key(1))
    st.tables[db.API_STATUS] = slow()
    live = Live(works=lambda k: k.startswith("AIza"))          # the live question also finds rootsys and Mireld down
    got = ai_team.route(st, github(), {}, NOW, job="motion", live=live)
    assert got.base_url == gemini_keys.BASE and got.api_key == "AIza-secret-1" and got.model == gemini_keys.FALLBACK_TEXT
    assert got.fallback_base_url in ("https://rootsys.cloud/v1", "https://api.mireld.my/v1")
    state = [r for r in st.tables[db.SETTINGS] if r["key"] == ai_team.STATE_KEY][0]["value"]["motion"]
    assert state["chosen"]["robot"] == "W4" and [o["slug"] for o in state["order"]][0] == "gemini"
    assert len([a for a in live.asked if a[0] == "gemini"]) == 1, "the key was asked once, not twice"
    reader = ai_team.route(st, github(), {}, NOW, job="reader", live=Live())
    assert reader.base_url != gemini_keys.BASE and reader.fallback_base_url != gemini_keys.BASE


def test_a_gemini_key_that_fails_its_check_is_skipped_for_the_next_one_and_noted():
    st = store(key(1), key(2))
    st.tables[db.API_STATUS] = slow()
    got = ai_team.route(st, github(), {}, NOW, job="motion", live=Live(works=lambda k: k.endswith("-2")))
    assert got.api_key == "AIza-secret-2"
    rows = {r["id"]: r for r in st.tables[gemini_keys.TABLE]}
    assert rows["k1"]["status"] == "limited" and rows["k2"]["status"] == "ok"


def test_with_no_gemini_key_the_team_is_exactly_what_it_was():
    st = FakeStore()
    got = ai_team.route(st, github(), {}, NOW, job="motion", live=None)
    assert got.base_url == "https://rootsys.cloud/v1" and got.fallback_base_url == "https://api.mireld.my/v1"


def test_the_probe_names_geminis_host_and_lists_its_models_without_the_prefix():
    from semasa import api_status
    assert api_status.slug_of(gemini_keys.BASE) == ("gemini", "Gemini (Wanshah 4)")
    gw = gemini_keys.gateway(store(key(1)), NOW)
    assert gw["slug"] == "gemini" and gw["key"] == "AIza-secret-1" and gw["base_url"] == gemini_keys.BASE
    assert gemini_keys.gateway(store(), NOW) is None
    assert gemini_keys.gateway(store(key(1), settings={"enabled": False}), NOW) is None


# ---- the picture call --------------------------------------------------------------------------------------------------------

def answer(raw: bytes) -> dict:
    return {"candidates": [{"content": {"parts": [{"text": "here"}, {"inlineData": {"mimeType": "image/png",
                                                                                  "data": base64.b64encode(raw).decode()}}]}}]}


class Resp:
    def __init__(self, code=200, body=None, text=""):
        self.status_code, self.body, self.text = code, body if body is not None else {}, text

    def json(self):
        return self.body


class Http:
    def __init__(self, *posts, gets=()):
        self.posts, self.gets, self.calls = list(posts), list(gets), []

    def post(self, url, **kw):
        self.calls.append(("post", url, kw))
        a = self.posts.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    def get(self, url, **kw):
        self.calls.append(("get", url, kw))
        return self.gets.pop(0)


def drawer(st, http):
    return gemini_images.Drawer(st, http=http, sleep=lambda s: None, now=lambda: NOW)


def test_a_picture_comes_back_with_the_key_in_the_header_and_the_aspect_ratio():
    raw = png()
    st = store(key(1))
    http = Http(Resp(200, answer(raw)))
    assert drawer(st, http).draw("a lab bench", resolution="portrait") == raw
    _, url, kw = http.calls[0]
    assert url == f"{gemini_keys.NATIVE}/models/gemini-2.5-flash-image:generateContent"
    assert kw["headers"]["x-goog-api-key"] == "AIza-secret-1" and "AIza" not in url
    assert kw["json"]["contents"][0]["parts"][0]["text"] == "a lab bench"
    assert kw["json"]["generationConfig"] == {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}}
    assert st.tables[gemini_keys.TABLE][0]["status"] == "ok"


def test_the_aspect_follows_the_film():
    raw = png()
    for res, ratio in (("landscape", "16:9"), ("square", "1:1"), ("weird", "1:1")):
        http = Http(Resp(200, answer(raw)))
        drawer(store(key(1)), http).draw("x", resolution=res)
        assert http.calls[0][2]["json"]["generationConfig"]["imageConfig"]["aspectRatio"] == ratio


def test_a_limited_key_is_marked_and_the_next_key_draws():
    raw = png()
    st = store(key(1), key(2))
    http = Http(Resp(429, text="RESOURCE_EXHAUSTED quota"), Resp(200, answer(raw)))
    assert drawer(st, http).draw("x") == raw
    assert http.calls[1][2]["headers"]["x-goog-api-key"] == "AIza-secret-2"
    rows = {r["id"]: r for r in st.tables[gemini_keys.TABLE]}
    assert rows["k1"]["status"] == "limited" and rows["k1"]["cooldown_until"] and rows["k2"]["status"] == "ok"


def test_a_refused_key_is_marked_bad_and_never_used_again():
    st = store(key(1), key(2))
    d = drawer(st, Http(Resp(400, text='API key not valid. Please pass a valid API key.'), Resp(200, answer(png()))))
    d.draw("x")
    assert st.tables[gemini_keys.TABLE][0]["status"] == "bad"
    assert [r["id"] for r in gemini_keys.usable(gemini_keys.keys(st), NOW)] == ["k2"]


def test_every_key_failing_is_a_limit_that_stops_the_film_asking():
    st = store(key(1), key(2))
    with pytest.raises(gemini_images.GeminiError) as e:
        drawer(st, Http(Resp(429, text="quota"), Resp(403, text="PERMISSION_DENIED"))).draw("x")
    assert e.value.limit and "every Gemini key failed" in str(e.value)
    with pytest.raises(gemini_images.GeminiError) as e2:
        drawer(store(), Http()).draw("x")
    assert e2.value.limit and "no Gemini key" in str(e2.value)


def test_a_400_steps_down_to_text_and_image_without_the_aspect_ratio():
    raw = png()
    http = Http(Resp(400, text="Unknown name imageConfig"), Resp(200, answer(raw)))
    assert drawer(store(key(1)), http).draw("x") == raw
    assert http.calls[1][2]["json"]["generationConfig"] == {"responseModalities": ["TEXT", "IMAGE"]}


def test_a_missing_model_is_replaced_by_an_image_model_from_the_keys_own_list():
    raw = png()
    models = Resp(200, {"models": [{"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                                   {"name": "models/gemini-9-image", "supportedGenerationMethods": ["generateContent"]}]})
    http = Http(Resp(404, text="models/gemini-2.5-flash-image is not found"), Resp(200, answer(raw)), gets=[models])
    d = drawer(store(key(1)), http)
    assert d.draw("x") == raw and d.model == "gemini-9-image" and d.discovered
    assert http.calls[2][1].endswith("/models/gemini-9-image:generateContent")


def test_a_5xx_is_tried_once_more_and_then_the_next_key_is():
    raw = png()
    st = store(key(1), key(2))
    assert drawer(st, Http(Resp(503), Resp(200, answer(raw)))).draw("x") == raw
    st2 = store(key(1), key(2))
    http = Http(Resp(503), Resp(503), Resp(200, answer(raw)))
    assert drawer(st2, http).draw("x") == raw
    assert http.calls[2][2]["headers"]["x-goog-api-key"] == "AIza-secret-2"
    st3 = store(key(1), key(2))
    assert drawer(st3, Http(requests.ConnectionError("down"), Resp(200, answer(raw)))).draw("x") == raw


def test_a_declined_prompt_is_the_prompts_fault_and_blames_no_key():
    st = store(key(1))
    blocked = {"candidates": [{"finishReason": "IMAGE_SAFETY", "content": {"parts": [{"text": "I can't draw that"}]}}]}
    with pytest.raises(gemini_images.GeminiError) as e:
        drawer(st, Http(Resp(200, blocked))).draw("x")
    assert not e.value.limit and "IMAGE_SAFETY" in str(e.value)
    assert st.tables[gemini_keys.TABLE][0]["status"] == "new" and st.tables[gemini_keys.TABLE][0]["failures"] == 0
    with pytest.raises(gemini_images.GeminiError, match="empty"):
        drawer(store(key(1)), Http(Resp(200, answer(b"tiny")))).draw("x")


def test_pictures_can_be_switched_off_and_ready_says_so():
    assert drawer(store(key(1)), Http()).ready() is True
    assert drawer(store(key(1), settings={"images": False}), Http()).ready() is False
    assert drawer(store(key(1), settings={"enabled": False}), Http()).ready() is False
    assert drawer(store(), Http()).ready() is False
    with pytest.raises(gemini_images.GeminiError, match="switched off"):
        drawer(store(key(1), settings={"images": False}), Http()).draw("x")


# ---- Motion's provider chain -------------------------------------------------------------------------------------------------

SCENES = [{"id": f"s{i}", "role": r, "heading": f"Tajuk {i}", "lines": ["Satu fakta"], "narration": "Cerita."}
          for i, r in enumerate(("hook", "fact", "why", "solution"), 1)] + [{"id": "brand-outro", "heading": "x", "lines": []}]
ROW = {"id": "m1", "stream": "regulab", "brief": "label rules"}
PAL = {"ground": "#e5f6ed", "ink": "#143e35", "accent": "#287b65"}
CFG = {"enabled": True, "model": "gpt-5", "max_images": 6}


class ChatGPT:
    def __init__(self, cfg=CFG, errors=None):
        self.cfg, self.errors, self.asked, self.fails, self.oks = cfg, list(errors or []), 0, [], 0

    def settings(self):
        return self.cfg

    def draw(self, prompt, *, size, model):
        self.asked += 1
        e = self.errors.pop(0) if self.errors else None
        if e:
            raise e
        return png(300)

    def ok(self):
        self.oks += 1

    def failed(self, m):
        self.fails.append(m)


class Gemini:
    def __init__(self, ready=True, errors=None, max_images=6):
        self._ready, self.errors, self.asked, self.max = ready, list(errors or []), 0, max_images

    def ready(self):
        return self._ready

    def max_images(self):
        return self.max

    def draw(self, prompt, *, resolution):
        self.asked += 1
        e = self.errors.pop(0) if self.errors else None
        if e:
            raise e
        return png(300)


class NoFlare:
    """Cloudflare not set up: the chain these tests were written for has two makers."""
    def ready(self):
        return False


def chain(tmp_path, gpt, gem, **kw):
    kw.setdefault("cloudflare", NoFlare())
    return motion_gpt_images.draw_scenes(None, ROW, SCENES, tmp_path, design="bright-editorial", palette=PAL, ambient="mint",
                                         resolution="portrait", login=gpt, gemini=gem, **kw)


def test_chatgpt_draws_first_and_gemini_is_not_asked_when_it_works(tmp_path):
    gpt, gem = ChatGPT(), Gemini()
    drawn, note = chain(tmp_path, gpt, gem)
    assert list(drawn) == ["s1", "s2", "s3", "s4"] and gpt.asked == 4 and gem.asked == 0
    assert drawn["s1"]["id"] == "chatgpt-s1" and note == "Pictures: 4 of 4 scenes drawn (ChatGPT 4, Gemini 0)"


def test_gemini_draws_the_scene_chatgpt_could_not_and_then_stops_chatgpt_if_it_hit_a_limit(tmp_path):
    gpt = ChatGPT(errors=[None, chatgpt_login.ChatGPTError("usage limit", limit=True)])
    gem = Gemini()
    drawn, note = chain(tmp_path, gpt, gem)
    assert list(drawn) == ["s1", "s2", "s3", "s4"]
    assert [drawn[s]["id"] for s in drawn] == ["chatgpt-s1", "gemini-s2", "gemini-s3", "gemini-s4"]
    assert gpt.asked == 2 and gem.asked == 3, "after the limit ChatGPT is not asked again for this film"
    assert "ChatGPT 1, Gemini 3" in note and "usage limit" in note and gpt.fails


def test_gemini_draws_every_scene_when_chatgpt_is_not_connected(tmp_path):
    drawn, note = chain(tmp_path, ChatGPT(cfg=None), Gemini())
    assert [drawn[s]["id"] for s in drawn] == ["gemini-s1", "gemini-s2", "gemini-s3", "gemini-s4"]
    assert note.startswith("Pictures: 4 of 4") and "ChatGPT 0, Gemini 4" in note
    assert Image.open(tmp_path / "assets/scene-s1.jpg").format == "JPEG"


def test_gemini_alone_uses_its_own_picture_count(tmp_path):
    drawn, _ = chain(tmp_path, ChatGPT(cfg=None), Gemini(max_images=2))
    assert list(drawn) == ["s1", "s2"]


def test_chatgpt_switched_off_leaves_gemini_to_draw(tmp_path):
    drawn, _ = chain(tmp_path, ChatGPT(cfg={**CFG, "enabled": False}), Gemini())
    assert [drawn[s]["id"] for s in drawn][0] == "gemini-s1"


def test_both_failing_for_a_scene_keeps_the_film_and_says_why_for_each(tmp_path):
    gpt = ChatGPT(errors=[chatgpt_login.ChatGPTError("picture came back empty")] + [None] * 5)
    gem = Gemini(errors=[gemini_images.GeminiError("Gemini gave no picture (IMAGE_SAFETY)")])
    drawn, note = chain(tmp_path, gpt, gem)
    assert list(drawn) == ["s2", "s3", "s4"] and "s1 (ChatGPT): picture came back empty" in note and "s1 (Gemini)" in note


def test_both_spent_stops_the_film_asking(tmp_path):
    gpt = ChatGPT(errors=[chatgpt_login.ChatGPTError("limit", limit=True)])
    gem = Gemini(errors=[gemini_images.GeminiError("every Gemini key failed", limit=True)])
    drawn, note = chain(tmp_path, gpt, gem)
    assert drawn == {} and gpt.asked == 1 and gem.asked == 1 and "limit" in note


def test_nothing_connected_draws_nothing_and_says_nothing(tmp_path):
    assert chain(tmp_path, ChatGPT(cfg=None), Gemini(ready=False)) == ({}, "")
    assert chain(tmp_path, ChatGPT(cfg={**CFG, "enabled": False}), Gemini(ready=False)) == ({}, "ChatGPT pictures: switched off")
