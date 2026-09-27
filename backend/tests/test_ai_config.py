"""AI settings from the page (supabase/016_ai_settings.sql) laid over GitHub's: an empty slot changes nothing, a key is
used only at the host it was entered for, and a picture reader of its own is asked before the writer's endpoint."""

import pytest

from semasa import ai_config
from semasa import llm as llm_mod
from semasa.config import LLMSettings, MediaSettings
from semasa.llm import LLM
from tests.fakestore import FakeStore
from tests.test_llm_backup import Resp


@pytest.fixture
def env(monkeypatch):
    for n in ("LLM_ALLOWED_HOSTS", "LLM_FALLBACK_API_KEY", "LLM_PROVIDER", "LLM_MODEL", "VISION_MODEL",
              "MEDIA_PROVIDER", "REPLICATE_API_TOKEN", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("LLM_API_KEY", "rootsys-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://rootsys.cloud/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek")
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "a" * 32)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "cf-github")
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    return monkeypatch


def test_nothing_saved_changes_nothing(env):
    s, m = LLMSettings.load(), MediaSettings.load()
    assert ai_config.llm_settings(s, {}) == s and ai_config.media_settings(m, {}) == m
    assert ai_config.describe({}) == "AI settings: GitHub only"


def test_the_tables_missing_means_github_settings(env):
    class Broken:
        def table(self, name):
            raise RuntimeError('relation "semasa_ai_config" does not exist')
    assert ai_config.read(Broken()) == {}


def test_read_joins_the_key_to_its_slot(env):
    store = FakeStore(semasa_ai_config=[{"slot": "reader", "model": "m", "key_host": "x.y"}],
                      semasa_ai_secrets=[{"slot": "reader", "api_key": "sk-1234567890"}])
    cfg = ai_config.read(store)
    assert cfg["reader"]["api_key"] == "sk-1234567890"
    assert "sk-" not in ai_config.describe(cfg) and "+key" in ai_config.describe(cfg)


def test_a_reader_key_goes_to_its_own_endpoint_even_off_the_allowed_list(env):
    cfg = {"reader": {"provider": "openai", "base_url": "https://api.mireld.my/v1", "model": "kimi",
                      "api_key": "mireld-key", "key_host": "api.mireld.my"}}
    s = ai_config.llm_settings(LLMSettings.load(), cfg)
    assert (s.base_url, s.api_key, s.model, s.blocked) == ("https://api.mireld.my/v1", "mireld-key", "kimi", "")


def test_a_new_endpoint_without_its_own_key_never_gets_the_github_key(env):
    cfg = {"reader": {"base_url": "https://evil.example/v1", "model": "x"}}
    s = ai_config.llm_settings(LLMSettings.load(), cfg)
    assert "not an allowed writer" in s.blocked and not LLM(s).primary_ok


def test_a_key_saved_for_another_host_is_not_used(env):
    cfg = {"reader": {"base_url": "https://evil.example/v1", "model": "x", "api_key": "k-12345678",
                      "key_host": "rootsys.cloud"}}
    s = ai_config.llm_settings(LLMSettings.load(), cfg)
    assert s.api_key == "rootsys-key" and s.blocked


def test_only_a_model_keeps_the_github_endpoint_and_key(env):
    s = ai_config.llm_settings(LLMSettings.load(), {"reader": {"model": "deepseek-v5"}})
    assert (s.base_url, s.api_key, s.model, s.blocked) == ("https://rootsys.cloud/v1", "rootsys-key", "deepseek-v5", "")


def test_cloudflare_account_key_and_models(env):
    acct = "b" * 32
    cfg = {"image_gen": {"provider": "cloudflare", "base_url": acct, "model": "@cf/t2i", "edit_model": "@cf/edit",
                         "api_key": "cf-page", "key_host": f"cloudflare:{acct}"}}
    m = ai_config.media_settings(MediaSettings.load(), cfg)
    assert (m.provider, m.cloudflare_account_id, m.cloudflare_token) == ("cloudflare", acct, "cf-page")
    assert (m.cloudflare_t2i_model, m.cloudflare_edit_model) == ("@cf/t2i", "@cf/edit")


def test_openai_images_on_another_host_drop_the_github_key(env):
    env.setenv("OPENAI_API_KEY", "openai-github")
    m = ai_config.media_settings(MediaSettings.load(),
                                 {"image_gen": {"provider": "openai", "base_url": "https://gw.example/v1"}})
    assert m.provider == "openai" and m.openai_key is None and m.openai_base_url == "https://gw.example/v1"
    m = ai_config.media_settings(MediaSettings.load(), {"image_gen": {
        "provider": "openai", "base_url": "https://gw.example/v1", "model": "img-2", "api_key": "gw-key",
        "key_host": "gw.example"}})
    assert (m.openai_key, m.openai_image_model) == ("gw-key", "img-2")


def test_replicate_key_has_one_home(env):
    m = ai_config.media_settings(MediaSettings.load(), {"image_gen": {
        "provider": "replicate", "api_key": "r8_12345678", "key_host": "api.replicate.com",
        "model": "bfl/t2i", "edit_model": "bfl/kontext"}})
    assert (m.provider, m.replicate_token, m.replicate_t2i_model, m.replicate_image_model) == \
        ("replicate", "r8_12345678", "bfl/t2i", "bfl/kontext")


def _posts(env, answer):
    sent = []

    def post(url, headers=None, json=None, timeout=None):
        sent.append((url, (headers or {}).get("Authorization") or (headers or {}).get("x-api-key"), json["model"]))
        return answer(url)
    env.setattr(llm_mod.requests, "post", post)
    return sent


def test_the_picture_reader_is_asked_first_with_its_own_key(env):
    cfg = {"image_reader": {"provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o",
                            "api_key": "sk-vision1", "key_host": "api.openai.com"}}
    sent = _posts(env, lambda url: Resp(200, '{"reads": "Valorith"}'))
    w = LLM(ai_config.llm_settings(LLMSettings.load(), cfg))
    assert w.describe_image("s", "p", b"\xff\xd8x", "image/jpeg") == {"reads": "Valorith"}
    assert sent == [("https://api.openai.com/v1/chat/completions", "Bearer sk-vision1", "gpt-4o")]
    assert w.last_model == "gpt-4o"


def test_when_the_picture_reader_fails_the_writer_reads_with_its_own_model(env):
    env.setenv("VISION_MODEL", "deepseek-vl")
    cfg = {"image_reader": {"provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o",
                            "api_key": "sk-vision1", "key_host": "api.openai.com"}}
    sent = _posts(env, lambda url: Resp(502, text="down") if "openai" in url else Resp(200, '{"reads": "x"}'))
    w = LLM(ai_config.llm_settings(LLMSettings.load(), cfg))
    assert w.describe_image("s", "p", b"\xff\xd8x", "image/jpeg") == {"reads": "x"}
    assert sent[-1] == ("https://rootsys.cloud/v1/chat/completions", "Bearer rootsys-key", "deepseek-vl")
    assert all(auth == "Bearer sk-vision1" for url, auth, _ in sent if "openai" in url)


def test_a_reader_model_alone_changes_the_writers_vision_model(env):
    s = ai_config.llm_settings(LLMSettings.load(), {"image_reader": {"model": "qwen-vl"}})
    assert s.vision_model == "qwen-vl" and not s.vision_key


# --- what GitHub says, shown in the page (Wan: "can this part display what in github secret") --------------------

def test_the_github_snapshot_never_carries_a_key(env):
    import json
    env.setenv("LLM_FALLBACK_API_KEY", "mireld-secret-key-9876")
    env.setenv("LLM_FALLBACK_BASE_URL", "https://api.mireld.my/v1")
    env.setenv("LLM_FALLBACK_MODEL", "mireld-chat")
    env.setenv("LLM_API_KEY", "rootsys-secret-key-1234")
    env.setenv("CLOUDFLARE_API_TOKEN", "cf-secret-token-5678")
    snap = ai_config.github_snapshot(LLMSettings.load(), MediaSettings.load())
    text = json.dumps(snap)
    for secret in ("rootsys-secret-key", "mireld-secret-key", "cf-secret-token", "a" * 32):
        assert secret not in text
    assert snap["reader"]["key"] == "…1234" and snap["reader"]["model"] == "deepseek"
    assert snap["reader"]["base_url"] == "https://rootsys.cloud/v1"
    assert snap["reader"]["fallback"] == {"base_url": "https://api.mireld.my/v1", "model": "mireld-chat",
                                          "key": "…9876", "blocked": None}
    cf = snap["image_gen"]["cloudflare"]
    assert snap["image_gen"]["provider"] == "cloudflare" and cf["key"] == "…5678" and cf["account"] == "…aaaa"
    assert snap["image_reader"]["model"] == "deepseek"


def test_a_short_or_missing_key_says_only_set_or_nothing(env):
    assert ai_config.key_hint(None) is None and ai_config.key_hint("") is None
    assert ai_config.key_hint("short-key") == "set"          # 4 of 9 characters would give too much away
    assert ai_config.key_hint("x" * 11 + "WXYZ") == "…WXYZ"


def test_each_workflow_writes_its_own_row_and_the_scrape_has_no_image_slot(env):
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"x": 1}}])
    ai_config.record_github(store, "scrape", LLMSettings.load())
    ai_config.record_github(store, "media", LLMSettings.load(), MediaSettings.load())
    ai_config.record_github(store, "media", LLMSettings.load(), MediaSettings.load())   # a second run replaces it
    rows = {r["key"]: r["value"] for r in store.tables["semasa_settings"]}
    assert set(rows) == {"brand", "ai_github_scrape", "ai_github_media"}
    assert "image_gen" not in rows["ai_github_scrape"] and "image_gen" in rows["ai_github_media"]
    assert rows["ai_github_media"]["at"] and rows["brand"] == {"x": 1}


def test_a_failed_record_never_stops_the_run(env):
    class Broken:
        def table(self, name):
            raise RuntimeError("permission denied")
    ai_config.record_github(Broken(), "media", LLMSettings.load(), MediaSettings.load())   # no exception


def test_moving_the_reader_moves_the_picture_model_with_it(env):
    env.setenv("VISION_MODEL", "deepseek-vl")
    cfg = {"reader": {"slot": "reader", "provider": "openai", "base_url": "https://api.openai.com/v1",
                      "model": "gpt-4o-mini", "api_key": "sk-page-key-123456", "key_host": "api.openai.com"}}
    s = ai_config.llm_settings(LLMSettings.load(), cfg)
    assert s.base_url == "https://api.openai.com/v1" and s.vision_model == "gpt-4o-mini"   # not rootsys's deepseek-vl
    # an image-reader model named in the page still wins
    cfg["image_reader"] = {"slot": "image_reader", "model": "gpt-4.1"}
    assert ai_config.llm_settings(LLMSettings.load(), cfg).vision_model == "gpt-4.1"
    # a reader slot that keeps GitHub's endpoint and model leaves GitHub's VISION_MODEL alone
    same = {"reader": {"slot": "reader", "provider": "openai", "base_url": "", "model": ""}}
    assert ai_config.llm_settings(LLMSettings.load(), same).vision_model == "deepseek-vl"
