"""API gateway status: the gateways a configuration names, the probe row, and the usage sink every runner attaches."""

from datetime import UTC, datetime

import pytest
from fakestore import FakeStore

from semasa import api_status, db, llm
from semasa.config import LLMSettings


def _settings(**kw):
    base = dict(
        provider="openai",
        api_key="sk-rootsys-1234",
        base_url="https://rootsys.cloud/v1",
        model="gpt-4.1-mini",
        timeout=30,
        fallback_base_url="https://api.mireld.my/v1",
        fallback_key="mk-5678",
        fallback_model="claude-sonnet-5.5",
    )
    base.update(kw)
    return LLMSettings(**base)


def test_gateways_names_primary_and_backup_once():
    gws = api_status.gateways(_settings())
    assert [(g["slug"], g["role"], g["key"][-4:]) for g in gws] == [("rootsys", "primary", "1234"), ("mireld", "backup", "5678")]
    assert gws[0]["name"] == "rootsys (Afiq)" and gws[1]["name"] == "Mireld"
    # the same host twice is one gateway
    gws = api_status.gateways(_settings(fallback_base_url="https://rootsys.cloud/v1"))
    assert [g["slug"] for g in gws] == ["rootsys"]
    # no backup key: no backup row
    assert [g["slug"] for g in api_status.gateways(_settings(fallback_key=None))] == ["rootsys"]


def test_usage_of_reads_both_dialects():
    assert api_status.usage_of({"usage": {"prompt_tokens": 10, "completion_tokens": 5}}) == {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
    }
    assert api_status.usage_of({"usage": {"input_tokens": 7, "output_tokens": 3}})["total_tokens"] == 10
    assert api_status.usage_of({})["total_tokens"] == 0


def test_probe_without_a_key_says_so(monkeypatch):
    row = api_status.probe(
        {
            "slug": "mireld",
            "name": "Mireld",
            "role": "backup",
            "base_url": "https://api.mireld.my/v1",
            "key": "",
            "model": "x",
            "provider": "openai",
        }
    )
    assert row["key_set"] is False and row["reachable"] is False and row["error"] == "no key set"


def test_probe_reads_models_chat_and_balance(monkeypatch):
    calls = []

    class R:
        def __init__(self, status, body):
            self.status_code, self._b, self.text = status, body, str(body)

        def json(self):
            if isinstance(self._b, Exception):
                raise self._b
            return self._b

    def fake_get(url, headers=None, timeout=None, **_):
        calls.append(url)
        if url.endswith("/models"):
            return R(200, {"data": [{"id": "claude-sonnet-5.5"}, {"id": "gpt-4.1"}]})
        if url.endswith("/balance"):
            return R(200, {"balance": 12.5, "currency": "USD"})
        return R(404, {})

    def fake_post(url, headers=None, json=None, timeout=None, **_):
        calls.append(url)
        assert json["max_tokens"] == 5
        return R(200, {"choices": [{"message": {"content": "OK"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1}})

    monkeypatch.setattr(api_status.requests, "get", fake_get)
    monkeypatch.setattr(api_status.requests, "post", fake_post)
    row = api_status.probe(
        {
            "slug": "mireld",
            "name": "Mireld",
            "role": "backup",
            "base_url": "https://api.mireld.my/v1",
            "key": "mk-5678",
            "model": "claude-sonnet-5.5",
            "provider": "openai",
        }
    )
    assert row["reachable"] and row["key_ok"] and row["chat_ok"] and row["http"] == 200
    assert row["models"] == ["claude-sonnet-5.5", "gpt-4.1"] and row["model_listed"] is True
    assert row["balance"]["balance"] == 12.5 and row["balance"]["path"] == "/balance"
    assert row["key_last4"] == "5678" and "mk-5678" not in str({k: v for k, v in row.items() if k != "key_last4"})


def test_probe_marks_a_refused_key(monkeypatch):
    class R:
        status_code, text = 401, "Invalid API key"

        def json(self):
            return {"error": "Invalid API key"}

    monkeypatch.setattr(api_status.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(api_status.requests, "post", lambda *a, **k: R())
    row = api_status.probe(
        {
            "slug": "rootsys",
            "name": "rootsys (Afiq)",
            "role": "primary",
            "base_url": "https://rootsys.cloud/v1",
            "key": "bad",
            "model": "m",
            "provider": "openai",
        }
    )
    assert row["reachable"] is True and row["key_ok"] is False and row["chat_ok"] is False and row["model_listed"] is None
    assert row["balance"] == {}


def test_run_upserts_status_and_logs(monkeypatch):
    monkeypatch.setattr(
        api_status,
        "probe",
        lambda gw, timeout=30: {
            "slug": gw["slug"],
            "name": gw["name"],
            "role": gw["role"],
            "base_url": gw["base_url"],
            "model": gw["model"],
            "chat_ok": gw["slug"] == "rootsys",
            "chat_ms": 300,
            "models": ["m"],
            "error": "",
        },
    )
    store = FakeStore(**{db.SETTINGS: [{"key": "api_probe", "value": {"keep_days": 90}}]})
    rows = api_status.run(store, _settings())
    assert [r["slug"] for r in rows] == ["rootsys", "mireld"]
    assert {r["slug"] for r in store.tables[db.API_STATUS]} == {"rootsys", "mireld"}
    assert [u["area"] for u in store.tables[db.API_USAGE]] == ["probe"]  # only the gateway that answered
    assert store.tables[db.LOG][0]["level"] == "warn" and "Mireld GAGAL" in store.tables[db.LOG][0]["title"]
    api_status.run(store, _settings())
    assert len(store.tables[db.API_STATUS]) == 2


def test_attach_records_every_call_through_the_llm(monkeypatch):
    store = FakeStore()
    api_status.attach(store, "scrape")
    try:

        class R:
            status_code, text = 200, ""

            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 8},
                }

        monkeypatch.setattr(llm.requests, "post", lambda *a, **k: R())
        w = llm.LLM(_settings())
        assert w._call("sys", "hi", 50, "gpt-4.1-mini") == '{"ok": true}'
        rows = store.tables[db.API_USAGE]
        assert (
            len(rows) == 1
            and rows[0]["gateway"] == "rootsys"
            and rows[0]["total_tokens"] == 48
            and rows[0]["ok"]
            and rows[0]["area"] == "scrape"
        )
        # a failed call is a row too, with the error and no tokens

        def boom(*a, **k):
            raise llm.requests.ConnectionError("down")

        monkeypatch.setattr(llm.requests, "post", boom)
        with pytest.raises(llm.requests.ConnectionError):
            w._call("sys", "hi", 50, "m", base="https://api.mireld.my/v1", key="k")
        assert (
            rows[1]["gateway"] == "mireld"
            and rows[1]["ok"] is False
            and "down" in rows[1]["error"]
            and rows[1]["total_tokens"] == 0
        )
    finally:
        llm.set_usage_sink(None)


def test_prune_drops_old_usage():
    store = FakeStore(
        **{
            db.SETTINGS: [{"key": "api_probe", "value": {"keep_days": 10}}],
            db.API_USAGE: [{"created_at": "2026-09-01T00:00:00+00:00"}, {"created_at": "2026-10-08T00:00:00+00:00"}],
        }
    )
    api_status.prune(store, datetime(2026, 10, 9, tzinfo=UTC))
    assert len(store.tables[db.API_USAGE]) == 1
