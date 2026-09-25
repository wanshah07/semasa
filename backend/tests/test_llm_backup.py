"""The backup writer (Mireld): asked only when rootsys gives nothing usable, with its own key and its own allowed
host, never for reading pictures, and a half-set-up backup says what is missing."""

import pytest

from semasa import llm as llm_mod
from semasa.config import LLMSettings
from semasa.llm import LLM


class Resp:
    def __init__(self, status, content="", text=""):
        self.status_code, self._content, self.text = status, content, text

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self):
        if self.status_code >= 400:
            err = llm_mod.requests.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


@pytest.fixture
def env(monkeypatch):
    for n in ("LLM_ALLOWED_HOSTS", "LLM_FALLBACK_ALLOWED_HOSTS", "LLM_FALLBACK_BASE_URL", "LLM_FALLBACK_MODEL",
              "LLM_FALLBACK_API_KEY", "LLM_PROVIDER", "LLM_MODEL"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "rootsys-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://rootsys.cloud/v1")
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    return monkeypatch


def _calls(monkeypatch, answers):
    sent = []

    def post(url, headers, json, timeout):
        sent.append((url, headers["Authorization"], json["model"]))
        return answers(url)
    monkeypatch.setattr(llm_mod.requests, "post", post)
    return sent


def test_rootsys_answers_and_the_backup_is_never_asked(env):
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    sent = _calls(env, lambda url: Resp(200, '{"ok": "yes"}'))
    w = LLM(LLMSettings.load())
    assert w.chat_json("s", "u") == {"ok": "yes"}
    assert all(url.startswith("https://rootsys.cloud/") for url, _, _ in sent) and w.backup_answers == 0


def test_the_backup_answers_when_rootsys_fails_and_each_key_stays_home(env):
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    sent = _calls(env, lambda url: Resp(502, text="bad gateway") if "rootsys" in url else Resp(200, '{"ok": "m"}'))
    w = LLM(LLMSettings.load())
    assert w.chat_json("s", "u") == {"ok": "m"}
    assert w.backup_answers == 1 and w.last_model == "mireld-chat"
    for url, auth, model in sent:
        if "rootsys" in url:
            assert auth == "Bearer rootsys-key"
        else:
            assert url == "https://api.mireld.my/v1/chat/completions" and auth == "Bearer mireld-key" and model == "mireld-chat"


def test_no_backup_key_means_no_backup_call(env):
    sent = _calls(env, lambda url: Resp(502, text="down"))
    assert LLM(LLMSettings.load()).chat_json("s", "u") is None
    assert all("rootsys" in url for url, _, _ in sent)


def test_a_backup_without_a_model_or_on_another_host_is_off_and_says_why(env):
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    s = LLMSettings.load()
    assert "LLM_FALLBACK_MODEL" in s.fallback_blocked and not LLM(s).backup_ok
    env.setenv("LLM_FALLBACK_MODEL", "m")
    env.setenv("LLM_FALLBACK_BASE_URL", "https://api.openai.com/v1")
    s = LLMSettings.load()
    assert "not an allowed writer" in s.fallback_blocked and not LLM(s).backup_ok


def test_mireld_is_a_backup_never_the_main_writer(env):
    env.setenv("LLM_BASE_URL", "https://api.mireld.my/v1")
    s = LLMSettings.load()
    assert s.blocked and not LLM(s).primary_ok


def test_the_backup_alone_still_writes_when_rootsys_has_no_key(env):
    env.delenv("LLM_API_KEY")
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    sent = _calls(env, lambda url: Resp(200, '{"ok": "m"}'))
    w = LLM(LLMSettings.load())
    assert w.configured and w.chat_json("s", "u") == {"ok": "m"}
    assert [u for u, _, _ in sent] == ["https://api.mireld.my/v1/chat/completions"]


def test_pictures_are_read_by_rootsys_only(env):
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    sent = _calls(env, lambda url: Resp(502, text="down"))
    assert LLM(LLMSettings.load()).describe_image("s", "p", b"\xff\xd8", "image/jpeg") is None
    assert sent and all("rootsys" in url for url, _, _ in sent)
