"""The writer over a CHAIN of gateways (feature C, 8 Nov 2026): when the chosen robot is not live, the call falls over to
the next live one — on a timeout, a 5xx, a 429, a model the gateway does not serve, or an empty answer; never on a refusal
that is the request's own fault, which every gateway would repeat."""

import pytest
from test_llm_backup import Resp

from semasa import llm as llm_mod
from semasa.config import LLMSettings
from semasa.llm import LLM

ROOT, MIRELD, KIOS = "https://rootsys.cloud/v1", "https://api.mireld.my/v1", "https://kiosapi.com/v1"


def _settings(**kw):
    base = dict(provider="openai", api_key="k1", base_url=ROOT, model="m1", timeout=5, vision_model="m1-vl",
                fallback_base_url=MIRELD, fallback_key="k2", fallback_model="m2")
    base.update(kw)
    return LLMSettings(**base)


def _chain():
    return [{"slug": "rootsys", "provider": "openai", "base_url": ROOT, "key": "k1", "model": "m1", "vision_model": ""},
            {"slug": "mireld", "provider": "openai", "base_url": MIRELD, "key": "k2", "model": "m2", "vision_model": "m2-vl"},
            {"slug": "kiosapi", "provider": "openai", "base_url": KIOS, "key": "k3", "model": "m3", "vision_model": ""}]


@pytest.fixture
def quiet(monkeypatch):
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    return monkeypatch


def _posts(monkeypatch, answer):
    """`answer(url, model)` returns a Resp or raises. Records (host, key, model) of every call."""
    sent = []

    def post(url, headers, json, timeout):
        sent.append((url.split("/")[2], headers["Authorization"], json["model"]))
        out = answer(url, json["model"])
        if isinstance(out, Exception):
            raise out
        return out
    monkeypatch.setattr(llm_mod.requests, "post", post)
    return sent


def _writer(chain=None, **kw):
    return LLM(_settings(**kw), chain=chain if chain is not None else _chain())


def test_the_chain_is_read_from_the_settings_and_labels_the_primary_and_the_backup():
    w = LLM(_settings(chain=tuple(_chain())))
    assert [x["label"] for x in w.links] == ["primary", "backup", "kiosapi"]
    assert w.links[0]["vision_model"] == "m1-vl", "the first link reads pictures with VISION_MODEL, as before"
    assert w.links[1]["vision_model"] == "m2-vl" and w.links[2]["vision_model"] == ""
    assert w.configured and w.can_see


def test_without_a_chain_the_primary_and_the_backup_are_a_two_link_chain():
    w = LLM(_settings())
    assert [(x["label"], x["base_url"]) for x in w.links] == [("primary", ROOT), ("backup", MIRELD)]
    assert w.links[1]["vision_model"] == "", "nothing says the backup's model can see"


def test_the_first_link_times_out_and_the_second_answers(quiet):
    sent = _posts(quiet, lambda url, m: llm_mod.requests.Timeout("slow") if "rootsys" in url else Resp(200, '{"ok": "two"}'))
    w = _writer()
    assert w.chat_json("s", "u") == {"ok": "two"}
    assert w.last_model == "m2" and w.last_gateway == MIRELD
    assert w.misses["primary"] == 1 and w.answers["backup"] == 1 and w.backup_answers == 1
    assert [h for h, _, _ in sent] == ["rootsys.cloud"] * 3 + ["api.mireld.my"], "three tries on the first link, then the next"
    assert {k for _, k, _ in sent} == {"Bearer k1", "Bearer k2"}, "each key went to its own host only"


def test_a_429_on_the_first_link_moves_to_the_second(quiet):
    sent = _posts(quiet, lambda url, m: Resp(429, text="rate limit exceeded") if "rootsys" in url else Resp(200, '{"ok": 2}'))
    assert _writer().chat_json("s", "u", retries=0) == {"ok": 2}
    assert [h for h, _, _ in sent] == ["rootsys.cloud", "api.mireld.my"]


def test_a_model_the_gateway_does_not_serve_moves_on(quiet):
    body = '{"error": {"code": "model_not_found", "message": "The model m1 does not exist or you do not have access"}}'
    sent = _posts(quiet, lambda url, m: Resp(400, text=body) if "rootsys" in url else Resp(200, '{"ok": 2}'))
    assert _writer().chat_json("s", "u") == {"ok": 2}
    assert [h for h, _, _ in sent] == ["rootsys.cloud", "api.mireld.my"], "a 400 is never retried on the same link"


def test_a_400_that_is_the_requests_own_fault_is_not_failed_over(quiet):
    body = "context_length_exceeded: this request has too many tokens, the maximum context length is 8192 tokens"
    sent = _posts(quiet, lambda url, m: Resp(400, text=body))
    w = _writer()
    assert w.chat_json("s", "u") is None
    assert [h for h, _, _ in sent] == ["rootsys.cloud"], "the other links would refuse it too"
    assert w.failures == 1 and w.misses["primary"] == 1


def test_a_400_nobody_can_read_gets_one_more_link_and_no_more(quiet):
    sent = _posts(quiet, lambda url, m: Resp(400, text="something odd"))
    assert _writer().chat_json("s", "u") is None
    assert [h for h, _, _ in sent] == ["rootsys.cloud", "api.mireld.my"]


def test_an_empty_answer_is_a_miss_and_the_next_link_is_asked(quiet):
    sent = _posts(quiet, lambda url, m: Resp(200, "") if "rootsys" in url else Resp(200, '{"ok": 2}'))
    assert _writer().chat_json("s", "u", retries=0) == {"ok": 2}
    assert len(sent) == 2


def test_at_most_four_links_are_asked(quiet):
    chain = _chain() + [{"slug": f"g{i}", "provider": "openai", "base_url": f"https://g{i}.example/v1", "key": "k",
                         "model": "m", "vision_model": ""} for i in range(4)]
    sent = _posts(quiet, lambda url, m: Resp(502, text="down"))
    assert _writer(chain=chain).chat_json("s", "u", retries=0) is None
    assert len({h for h, _, _ in sent}) == LLM.MAX_LINKS


def test_the_time_budget_stops_the_walk(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down") if "rootsys" in url else Resp(200, '{"ok": 2}'))
    w = _writer()
    w.budget_s = 0.0                                    # spent the moment the first link has answered nothing
    assert w.chat_json("s", "u", retries=0) is None
    assert [h for h, _, _ in sent] == ["rootsys.cloud"]
    w.budget_s = 60.0
    assert w.chat_json("s", "u", retries=0) == {"ok": 2}


def test_a_link_that_misses_twice_goes_to_the_back_for_the_rest_of_the_run(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down") if "rootsys" in url else Resp(200, '{"ok": 2}'))
    w = _writer()
    assert w.chat_json("s", "u", retries=0) == {"ok": 2} and not w.primary_down
    assert w.chat_json("s", "u", retries=0) == {"ok": 2} and w.primary_down
    sent.clear()
    assert w.chat_json("s", "u", retries=0) == {"ok": 2}
    assert [h for h, _, _ in sent] == ["api.mireld.my"], "the cooled-off link is not waited on"
    # the other two dead as well: the cooled-off one is asked once, last
    _posts(quiet, lambda url, m: Resp(200, '{"ok": 1}') if "rootsys" in url else Resp(502, text="down"))
    assert w.chat_json("s", "u", retries=0) == {"ok": 1} and not w.primary_down


def test_an_explicit_model_names_a_model_on_the_first_link_only(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down") if "rootsys" in url else Resp(200, '{"ok": 2}'))
    _writer().chat_json("s", "u", retries=0, model="m1-special")
    assert [m for _, _, m in sent] == ["m1-special", "m2"]


def test_chat_text_walks_the_chain_too(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down") if "rootsys" in url else Resp(200, "<html>ok</html>"))
    w = _writer()
    assert w.chat_text("s", "u") == "<html>ok</html>" and w.last_gateway == MIRELD
    assert [h for h, _, _ in sent] == ["rootsys.cloud", "api.mireld.my"], "one try per link for text"


def test_backup_false_asks_the_first_link_only(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down"))
    assert _writer().chat_json("s", "u", retries=0, backup=False) is None
    assert [h for h, _, _ in sent] == ["rootsys.cloud"]


def test_a_picture_is_read_by_the_next_link_that_has_a_vision_model(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down") if "rootsys" in url else Resp(200, '{"scene": "jar"}'))
    w = _writer()
    assert w.describe_image("s", "p", b"\xff\xd8", "image/jpeg") == {"scene": "jar"}
    assert w.last_model == "m2-vl" and w.vision.get("backup") == 1 and w.vision["primary"] == 0
    hosts = [h for h, _, _ in sent]
    assert hosts[:2] == ["rootsys.cloud", "rootsys.cloud"] and hosts[2:] == ["api.mireld.my"]
    assert "kiosapi.com" not in hosts, "a link with no vision model is never sent a picture"
    assert [m for h, _, m in sent if h == "rootsys.cloud"] == ["m1-vl", "m1-vl"]


def test_a_picture_nobody_can_read_is_none_and_kiosapi_is_still_not_asked(quiet):
    sent = _posts(quiet, lambda url, m: Resp(502, text="down"))
    assert _writer().describe_image("s", "p", b"\xff\xd8", "image/jpeg") is None
    assert "kiosapi.com" not in {h for h, _, _ in sent}


def test_a_blocked_or_keyless_link_in_the_chain_is_dropped():
    chain = _chain()
    chain[1]["blocked"] = "gpt-image-2 is an image model"
    chain[2]["key"] = None
    assert [x["slug"] for x in LLM(_settings(), chain=chain).links] == ["rootsys"]


@pytest.mark.parametrize("status,body,verdict", [
    (400, "The model `x` does not exist", llm_mod._MISS),
    (400, "This model is not supported on the Chat Completions endpoint", llm_mod._MISS),
    (400, "maximum context length is 128000 tokens", llm_mod._STOP),
    (400, "Your request was rejected as a result of our safety system", llm_mod._STOP),
    (400, "???", llm_mod._UNSURE),
    (401, "bad key", llm_mod._MISS),
    (404, "", llm_mod._MISS),
    (413, "payload too large", llm_mod._STOP),
    (429, "slow down", llm_mod._MISS),
    (503, "", llm_mod._MISS),
])
def test_classify_http(status, body, verdict):
    assert llm_mod.classify_http(status, body) == verdict


# ---- ChatGPT as a link of the chain (Wan, 8 Nov 2026: ChatGPT writes and reads) ------------------------------------------

class FakeLogin:
    """Stands in for chatgpt_login.Login: remembers what it was asked, answers or raises."""

    def __init__(self, text='{"ok": "gpt"}', exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def write(self, system, user, *, model, timeout):
        self.calls.append(("write", user, model))
        if self.exc:
            raise self.exc
        return self.text

    def read_image(self, system, prompt, data, mime, *, model, timeout):
        self.calls.append(("read", prompt, data, mime, model))
        if self.exc:
            raise self.exc
        return self.text


def _gpt(login, vision="gpt-5.5"):
    return {"slug": "chatgpt", "provider": "chatgpt", "base_url": "https://chatgpt.com/backend-api/codex", "key": login,
            "model": "gpt-5.5", "vision_model": vision}


def test_chatgpt_writes_as_a_link_and_the_other_gateways_are_not_asked(quiet):
    sent = _posts(quiet, lambda url, m: Resp(200, '{"ok": "other"}'))
    login = FakeLogin()
    w = _writer(chain=[_gpt(login), *_chain()])
    assert w.chat_json("sys", "hello") == {"ok": "gpt"}
    assert login.calls[0][0] == "write" and "hello" in login.calls[0][1] and login.calls[0][2] == "gpt-5.5"
    assert sent == [] and w.last_model == "gpt-5.5" and w.last_gateway == "https://chatgpt.com/backend-api/codex"


def test_a_chatgpt_refusal_is_no_answer_and_the_next_gateway_writes(quiet):
    from semasa.chatgpt_login import ChatGPTError
    sent = _posts(quiet, lambda url, m: Resp(200, '{"ok": "other"}'))
    login = FakeLogin(exc=ChatGPTError("ChatGPT refused the model (400)", model=True))
    w = _writer(chain=[_gpt(login), *_chain()])
    assert w.chat_json("sys", "hello") == {"ok": "other"}
    assert sent and sent[0][0] == "rootsys.cloud", "the key of one robot goes only to its own host"
    assert all("Bearer" not in str(c) for c in login.calls)


def test_chatgpt_reads_a_picture_when_it_is_the_link_with_vision(quiet):
    sent = _posts(quiet, lambda url, m: Resp(200, '{"ok": "other"}'))
    login = FakeLogin(text='{"seen": "a jar"}')
    w = _writer(chain=[_gpt(login), *_chain()])
    assert w.can_see
    assert w.describe_image("sys", "What is it?", b"\x89PNG-bytes", "image/png") == {"seen": "a jar"}
    kind, prompt, data, mime, model = login.calls[0]
    assert kind == "read" and data == b"\x89PNG-bytes" and mime == "image/png" and model == "gpt-5.5"
    assert "What is it?" in prompt and sent == []


def test_a_chatgpt_link_without_vision_is_never_sent_a_picture(quiet):
    sent = _posts(quiet, lambda url, m: Resp(200, '{"seen": "from mireld"}'))
    login = FakeLogin()
    w = _writer(chain=[_gpt(login, vision=""), *_chain()])
    assert w.describe_image("sys", "What is it?", b"x", "image/png") == {"seen": "from mireld"}
    assert login.calls == [] and sent and sent[0][0] == "rootsys.cloud", "the primary reads it with VISION_MODEL, as before"
