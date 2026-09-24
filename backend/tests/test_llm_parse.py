import pytest

from semasa.config import LLMSettings
from semasa.llm import LLM, _parse_json, _pythonish_to_json


@pytest.mark.parametrize("answer,expected", [
    ('{"ok":True}', {"ok": True}),                       # the exact probe failure on run 36026074962
    ('{"ok": True}', {"ok": True}),
    ("{'ok': True, 'x': None, 'y': False}", {"ok": True, "x": None, "y": False}),
    ("```python\n{'ok': True}\n```", {"ok": True}),
    ('```json\n{"ok": true}\n```', {"ok": True}),
    ('<think>the user wants {json}</think>\n{"ok": true}', {"ok": True}),
    ('Here you go: {"ok": true} hope that helps', {"ok": True}),
    ('{"items": [{"i": 0, "summary": "It is True that None came", "category": "lain"}]}',
     {"items": [{"i": 0, "summary": "It is True that None came", "category": "lain"}]}),
    ("{'summary': 'He said \"hi\"', 'n': 1}", {"summary": 'He said "hi"', "n": 1}),
    ("{'summary': 'it\\'s fine'}", {"summary": "it's fine"}),
])
def test_parse_tolerates_real_answers(answer, expected):
    assert _parse_json(answer) == expected


def test_words_inside_strings_are_never_rewritten():
    assert _pythonish_to_json('{"a": "True False None", "b": True}') == '{"a": "True False None", "b": true}'
    assert _pythonish_to_json('{"TrueNorth": 1, "x": NoneSuch}') == '{"TrueNorth": 1, "x": NoneSuch}'


@pytest.mark.parametrize("answer", ["", "   ", "no json here", "{not: valid, at all"])
def test_unparsable_still_raises(answer):
    with pytest.raises(ValueError):
        _parse_json(answer)


class _Resp:
    status_code = 200

    def __init__(self, content):
        self._content = content
        self.text = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}

    def raise_for_status(self):
        pass


def test_probe_passes_on_python_style_answer(monkeypatch):
    monkeypatch.setattr("semasa.llm.requests.post", lambda *a, **k: _Resp('{"ok":True}'))
    llm = LLM(LLMSettings(provider="openai", api_key="k", base_url="https://rootsys.cloud/v1",
                          model="deepseek-v4.1-flash", timeout=5))
    assert llm.probe() is True


def test_unparsable_answer_is_logged_with_its_opening(monkeypatch, caplog):
    monkeypatch.setattr("semasa.llm.requests.post", lambda *a, **k: _Resp("Sorry, I cannot do that." * 20))
    monkeypatch.setattr("semasa.llm.time.sleep", lambda s: None)
    llm = LLM(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))
    with caplog.at_level("WARNING", logger="semasa.llm"):
        assert llm.chat_json("s", "u", retries=0) is None
    assert any("it starts: 'Sorry, I cannot do that." in r.getMessage() for r in caplog.records)
