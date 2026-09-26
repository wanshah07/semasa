"""The one-run Mireld trial: asked first for one scrape run and one worker run, rootsys still answers what Mireld
cannot, the result is written back to the page's switch, and a run with nothing to ask leaves the trial waiting."""

import pytest
from fakestore import FakeStore
from test_llm_backup import Resp, _calls

from semasa import llm as llm_mod
from semasa import trial
from semasa.config import LLMSettings
from semasa.llm import LLM


@pytest.fixture
def env(monkeypatch):
    for n in ("LLM_ALLOWED_HOSTS", "LLM_FALLBACK_ALLOWED_HOSTS", "LLM_FALLBACK_BASE_URL", "LLM_PROVIDER", "LLM_MODEL"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "rootsys-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://rootsys.cloud/v1")
    monkeypatch.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    monkeypatch.setenv("LLM_FALLBACK_MODEL", "kimi-k3")
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(LLM, "backup_models", lambda self: ["kimi-k3", "flux-schnell", "qwen2.5-vl"])
    return monkeypatch


def _row(store):
    return next(r for r in store.tables["semasa_settings"] if r["key"] == trial.KEY)["value"]


def test_in_a_trial_mireld_is_asked_first_and_counted(env):
    sent = _calls(env, lambda url: Resp(200, '{"ok": "x"}'))
    w = LLM(LLMSettings.load())
    w.prefer_backup = True
    assert w.chat_json("s", "u") == {"ok": "x"}
    assert sent[0][0] == "https://api.mireld.my/v1/chat/completions" and sent[0][1] == "Bearer mireld-key"
    assert w.answers == {"primary": 0, "backup": 1} and w.last_model == "kimi-k3"


def test_what_mireld_cannot_answer_rootsys_does_and_three_misses_hand_the_lead_back(env):
    sent = _calls(env, lambda url: Resp(502, text="down") if "mireld" in url else Resp(200, '{"ok": "r"}'))
    w = LLM(LLMSettings.load())
    w.prefer_backup = True
    for _ in range(4):
        assert w.chat_json("s", "u") == {"ok": "r"}
    assert w.misses["backup"] == 3 and w.answers["primary"] == 4
    assert not w.prefer_backup and "missed 3 times" in w.trial_stopped
    assert "rootsys" in sent[-1][0] and not any("mireld" in u for u, _, _ in sent[-1:])


def test_the_trial_asks_mireld_to_read_the_picture_first(env):
    sent = _calls(env, lambda url: Resp(200, '{"scene": "a jar"}'))
    w = LLM(LLMSettings.load())
    w.prefer_backup = True
    assert w.describe_image("s", "p", b"\xff\xd8", "image/jpeg") == {"scene": "a jar"}
    assert "mireld" in sent[0][0] and w.vision["backup"] == 1


def test_a_picture_mireld_cannot_read_is_read_by_rootsys(env):
    _calls(env, lambda url: Resp(400, text="model does not support images") if "mireld" in url else Resp(200, '{"scene": "r"}'))
    w = LLM(LLMSettings.load())
    w.prefer_backup = True
    assert w.describe_image("s", "p", b"\xff\xd8", "image/jpeg") == {"scene": "r"}
    assert w.vision == {"primary": 1, "backup": 0, "backup_missed": 1}


def test_outside_a_trial_pictures_stay_with_rootsys(env):
    sent = _calls(env, lambda url: Resp(200, '{"scene": "r"}'))
    LLM(LLMSettings.load()).describe_image("s", "p", b"\xff\xd8", "image/jpeg")
    assert all("rootsys" in u for u, _, _ in sent)


def test_the_switch_row_is_created_and_nothing_starts_without_it_being_set(env):
    store = FakeStore(semasa_settings=[])
    w = LLM(LLMSettings.load())
    assert trial.start(store, w, "scrape") is False and not w.prefer_backup
    assert _row(store) == {}


def test_a_requested_trial_starts_records_and_switches_itself_off(env):
    _calls(env, lambda url: Resp(200, '{"ok": "x"}'))
    store = FakeStore(semasa_settings=[{"key": trial.KEY, "value": {"scrape": True, "media": True}}])
    w = LLM(LLMSettings.load())
    assert trial.start(store, w, "scrape") is True and w.prefer_backup
    w.chat_json("s", "u")
    line = trial.finish(store, w, "scrape")
    v = _row(store)
    assert v["scrape"] is False and v["media"] is True                     # the worker's half still to run
    r = v["scrape_result"]
    assert r["ok"] and r["mireld_answers"] == 1 and r["model"] == "kimi-k3"
    assert r["image_models"] == ["flux-schnell", "qwen2.5-vl"] and "image-looking" in line


def test_a_run_that_asked_nothing_leaves_the_trial_waiting(env):
    store = FakeStore(semasa_settings=[{"key": trial.KEY, "value": {"media": True}}])
    w = LLM(LLMSettings.load())
    assert trial.start(store, w, "media")
    assert "waiting" in trial.finish(store, w, "media")
    assert _row(store) == {"media": True}


def test_with_the_backup_off_the_trial_says_why_and_does_not_run(env):
    env.delenv("LLM_FALLBACK_API_KEY")
    store = FakeStore(semasa_settings=[{"key": trial.KEY, "value": {"scrape": True}}])
    w = LLM(LLMSettings.load())
    assert trial.start(store, w, "scrape") is False and not w.prefer_backup
    v = _row(store)
    assert v["scrape"] is False and v["scrape_result"]["ok"] is False and "could not start" in v["scrape_result"]["why"]
