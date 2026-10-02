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


def test_the_instructions_ride_in_the_user_turn_too(env, monkeypatch):
    bodies = []

    def post(url, headers=None, json=None, timeout=None):
        bodies.append(json)
        return Resp(200, '{"ok": 1}')
    monkeypatch.setattr(llm_mod.requests, "post", post)
    LLM(LLMSettings.load()).chat_json("Answer in JSON only.", "item 1")
    msgs = bodies[0]["messages"]
    assert msgs[0] == {"role": "system", "content": "Answer in JSON only."}
    assert msgs[1]["content"].startswith("INSTRUCTIONS") and "Answer in JSON only." in msgs[1]["content"]
    assert msgs[1]["content"].endswith("item 1")


def test_a_picture_turn_gets_the_instructions_as_its_first_part():
    parts = llm_mod.with_instructions("Read the label.", [{"type": "image_url", "image_url": {"url": "data:x"}}])
    assert parts[0]["type"] == "text" and "Read the label." in parts[0]["text"] and parts[1]["type"] == "image_url"
    assert llm_mod.with_instructions("", "u") == "u"


def test_rootsys_down_for_the_run_the_backup_goes_first_after_two_empty_calls(env):
    """Run 48 (1 Oct 2026): rootsys timed out 3 x 60s on every batch before the backup answered; four batches ate the
    25-minute job limit. After two calls in a row where rootsys gave nothing, the backup is asked first."""
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    sent = _calls(env, lambda url: Resp(502, text="down") if "rootsys" in url else Resp(200, '{"ok": "m"}'))
    w = LLM(LLMSettings.load())
    assert w.chat_json("s", "u") == {"ok": "m"} and not w.primary_down       # call 1: rootsys tried 3 times, then the backup
    assert w.chat_json("s", "u") == {"ok": "m"} and w.primary_down           # call 2: the same, and now rootsys is written off
    before = len(sent)
    for _ in range(4):
        assert w.chat_json("s", "u") == {"ok": "m"}
    later = sent[before:]
    assert len(later) == 4 and all(url.startswith("https://api.mireld.my/") for url, _, _ in later), "no more waiting on rootsys"


def test_rootsys_asked_once_as_a_last_resort_when_it_is_down_and_the_backup_fails_too(env):
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-key")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    alive = {"backup": False}

    def answers(url):
        if "rootsys" in url:
            return Resp(502, text="down") if not alive.get("primary") else Resp(200, '{"ok": "r"}')
        return Resp(200, '{"ok": "m"}') if alive["backup"] else Resp(502, text="down")
    sent = _calls(env, answers)
    w = LLM(LLMSettings.load())
    alive["backup"] = True
    w.chat_json("s", "u")
    w.chat_json("s", "u")
    assert w.primary_down
    alive["backup"] = False
    alive["primary"] = True                                                    # rootsys is back while the backup is down
    sent.clear()
    assert w.chat_json("s", "u") == {"ok": "r"}                                # the last-resort ask reaches it
    assert [("rootsys" in u) for u, _, _ in sent] == [False, False, True], "backup (1 try + 1 retry), then rootsys once"
    assert not w.primary_down, "an answer from rootsys clears the write-off"


def test_a_run_without_a_backup_never_writes_rootsys_off(env):
    sent = _calls(env, lambda url: Resp(502, text="down"))
    w = LLM(LLMSettings.load())
    for _ in range(3):
        assert w.chat_json("s", "u") is None
    assert not w.primary_down and all("rootsys" in u for u, _, _ in sent)
    assert len(sent) == 9, "three attempts every call: with no backup there is nothing else to wait for"
