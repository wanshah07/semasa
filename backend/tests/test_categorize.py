import json

import pytest

from semasa import categorize
from semasa.categorize import CATEGORIES, detect_lang, rules_category
from semasa.config import LLMSettings
from semasa.llm import LLM


@pytest.mark.parametrize("text,expected", [
    ("NPRA batal notifikasi 12 produk kosmetik mengandungi merkuri", "kosmetik"),
    ("JAKIM sahkan restoran tiada sijil halal", "halal"),
    ("KKM rampas produk tidak berdaftar di Klang", "farmaseutikal"),
    ("Keracunan makanan: 40 pelajar dimasukkan ke hospital", "makanan"),
    ("Anthony Loke tetap mahu letak jawatan", "politik"),
    ("Wanita OKU ditemukan maut dengan kesan tusukan", "jenayah"),
    ("Ringgit kukuh berbanding dolar", "ekonomi"),
    ("Harimau Malaya tewas 2-1", "sukan"),
    ("Cuaca cerah di Langkawi", "alam_sekitar"),
    ("Sesuatu yang tidak sepadan dengan apa-apa", "lain"),
])
def test_rules_category(text, expected):
    assert rules_category(text) == expected
    assert expected in CATEGORIES


def test_regulated_categories_win_over_general():
    # 'mahkamah' is jenayah, but a cosmetics case is a cosmetics story first
    assert rules_category("Pengedar krim pemutih mengandungi merkuri didakwa di mahkamah") == "kosmetik"


@pytest.mark.parametrize("text,expected", [
    ("Dua pelajar didakwa di mahkamah berkaitan kes buli yang berlaku di sekolah", "ms"),
    ("Two students charged in court over the bullying case at the school", "en"),
    ("Anthony Loke", "ms"),  # no signal → default
])
def test_detect_lang(text, expected):
    assert detect_lang(text) == expected


class _Resp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code), response=self)


def _llm():
    return LLM(LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5))


def test_llm_annotate_accepts_valid_rows_only(monkeypatch):
    answer = {"items": [
        {"i": 0, "summary": "Ringkasan satu.", "category": "kosmetik", "lang": "ms"},
        {"i": 1, "summary": "", "category": "halal", "lang": "ms"},          # empty summary → dropped
        {"i": 2, "summary": "x", "category": "not_a_category", "lang": "ms"},  # bad category → dropped
        {"i": 99, "summary": "x", "category": "halal", "lang": "ms"},        # not in batch → dropped
        "garbage",
    ]}
    content = "```json\n" + json.dumps(answer) + "\n```"  # fenced, as many endpoints do
    monkeypatch.setattr("semasa.llm.requests.post", lambda *a, **k: _Resp(200, {
        "choices": [{"message": {"content": content}}]}))
    out = categorize.llm_annotate(_llm(), [{"i": i, "title": f"t{i}", "snippet": None, "source": "s"} for i in range(3)])
    assert out == {0: {"summary": "Ringkasan satu.", "category": "kosmetik", "lang": "ms"}}


def test_llm_failure_is_none_not_exception(monkeypatch):
    monkeypatch.setattr("semasa.llm.requests.post", lambda *a, **k: _Resp(500, {"error": "boom"}))
    monkeypatch.setattr("semasa.llm.time.sleep", lambda s: None)
    llm = _llm()
    assert llm.chat_json("s", "u") is None
    assert llm.failures == 1
    assert categorize.llm_annotate(llm, [{"i": 0, "title": "t", "snippet": None, "source": "s"}]) == {}


def test_llm_unconfigured_never_calls(monkeypatch):
    called = []
    monkeypatch.setattr("semasa.llm.requests.post", lambda *a, **k: called.append(1))
    llm = LLM(LLMSettings(provider="openai", api_key=None, base_url="https://x/v1", model="m", timeout=5))
    assert llm.probe() is False and llm.chat_json("s", "u") is None and called == []


def test_llm_anthropic_dialect(monkeypatch):
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, body=json)
        return _Resp(200, {"content": [{"type": "text", "text": '{"category": "ekonomi"}'}]})

    monkeypatch.setattr("semasa.llm.requests.post", fake_post)
    llm = LLM(LLMSettings(provider="anthropic", api_key="k", base_url="https://api.anthropic.com", model="m", timeout=5))
    assert llm.probe() is True
    assert seen["url"].endswith("/v1/messages") and seen["headers"]["x-api-key"] == "k"
    assert seen["body"]["system"] and seen["body"]["messages"][0]["role"] == "user"
