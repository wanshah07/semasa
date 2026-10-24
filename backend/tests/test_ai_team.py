"""The AI team router: who writes text, in what order, and why (semasa.ai_team)."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import ai_config, ai_team, api_status, db
from semasa.config import LLMSettings, MediaSettings

NOW = datetime(2026, 10, 23, 6, 0, tzinfo=UTC)


def _github(**kw):
    base = dict(provider="openai", api_key="sk-root", base_url="https://rootsys.cloud/v1", model="gpt-4.1-mini", timeout=30,
                fallback_base_url="https://api.mireld.my/v1", fallback_key="mk-1", fallback_model="claude-sonnet-5.5")
    base.update(kw)
    return LLMSettings(**base)


def _media(**kw):
    base = dict(provider="openai", batch=1, max_attempts=1, poll_seconds=1, max_wait_image=60, max_wait_video=60,
                replicate_token=None, replicate_image_model="a/b", replicate_video_model="c/d",
                replicate_image_input_key="input_image", replicate_video_input_key="start_image", openai_key="kk-1",
                openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1", openai_video_model="sora-2",
                openai_image_size="1024x1024", openai_video_seconds="8", openai_video_size="1280x720")
    base.update(kw)
    return MediaSettings(**base)


def _probe(store, slug, *, chat_ok=True, chat_ms=800, age_h=1, error=""):
    store.tables.setdefault(db.API_STATUS, []).append({"slug": slug, "chat_ok": chat_ok, "chat_ms": chat_ms, "error": error,
                                                        "checked_at": (NOW - timedelta(hours=age_h)).isoformat()})


def _usage(store, slug, ms, ok=True, n=1, age_h=1):
    for _ in range(n):
        store.tables.setdefault(db.API_USAGE, []).append({"gateway": slug, "ms": ms, "ok": ok,
                                                           "created_at": (NOW - timedelta(hours=age_h)).isoformat()})


def _state(store):
    rows = [r for r in store.tables.get(db.SETTINGS, []) if r.get("key") == ai_team.STATE_KEY]
    return rows[0]["value"] if rows else None


def test_nothing_measured_keeps_the_configured_order():
    store = FakeStore()
    s = ai_team.route(store, _github(), {}, NOW)
    assert s.base_url == "https://rootsys.cloud/v1" and s.fallback_base_url == "https://api.mireld.my/v1"
    st = _state(store)["reader"]
    assert st["chosen"]["robot"] == "W1" and st["backup"]["robot"] == "W2" and st["why"] == "not measured yet"
    assert st["backup"]["name"] == "Wanshah 2"


def test_the_fastest_measured_robot_writes_first():
    store = FakeStore()
    _probe(store, "rootsys", chat_ms=2400)
    _probe(store, "mireld", chat_ms=600)
    s = ai_team.route(store, _github(), {}, NOW)
    assert s.base_url == "https://api.mireld.my/v1" and s.api_key == "mk-1" and s.model == "claude-sonnet-5.5"
    assert s.fallback_base_url == "https://rootsys.cloud/v1" and s.fallback_key == "sk-root"
    assert _state(store)["reader"]["chosen"]["slug"] == "mireld"


def test_measured_calls_beat_the_probe_once_there_are_enough():
    store = FakeStore()
    _probe(store, "rootsys", chat_ms=300)
    _probe(store, "mireld", chat_ms=900)
    _usage(store, "rootsys", 9000, n=3)          # slow in real work
    _usage(store, "mireld", 1000, n=3)
    s = ai_team.route(store, _github(), {}, NOW)
    assert s.base_url == "https://api.mireld.my/v1"
    # two calls are not enough to overrule the probe
    store2 = FakeStore()
    _probe(store2, "rootsys", chat_ms=300)
    _probe(store2, "mireld", chat_ms=900)
    _usage(store2, "rootsys", 9000, n=2)
    assert ai_team.route(store2, _github(), {}, NOW).base_url == "https://rootsys.cloud/v1"


def test_a_robot_the_probe_found_down_goes_last_but_is_still_a_backup():
    store = FakeStore()
    _probe(store, "rootsys", chat_ok=False, chat_ms=100, error="402 overage limit")
    _probe(store, "mireld", chat_ms=1500)
    s = ai_team.route(store, _github(), {}, NOW)
    assert s.base_url == "https://api.mireld.my/v1" and s.fallback_base_url == "https://rootsys.cloud/v1"
    assert _state(store)["reader"]["order"][1]["why"].startswith("down: 402")


def test_a_stale_probe_says_nothing_about_now():
    store = FakeStore()
    _probe(store, "rootsys", chat_ok=False, chat_ms=100, age_h=30)
    _probe(store, "mireld", chat_ms=1500, age_h=30)
    assert ai_team.route(store, _github(), {}, NOW).base_url == "https://rootsys.cloud/v1"


def test_more_than_half_failed_calls_is_down():
    store = FakeStore()
    _usage(store, "rootsys", 500, ok=False, n=4)
    _usage(store, "rootsys", 500, ok=True, n=2)
    _usage(store, "mireld", 3000, ok=True, n=3)
    assert ai_team.route(store, _github(), {}, NOW).base_url == "https://api.mireld.my/v1"


def test_a_pin_goes_first_while_healthy_and_its_model_is_used():
    store = FakeStore()
    _probe(store, "rootsys", chat_ms=300)
    _probe(store, "mireld", chat_ms=3000)
    store.tables[db.SETTINGS] = [{"key": "ai_team", "value": {"pins": {"reader": {"gateway": "mireld", "model": "gpt-4.1"}}}}]
    s = ai_team.route(store, _github(), {}, NOW)
    assert s.base_url == "https://api.mireld.my/v1" and s.model == "gpt-4.1"
    assert _state(store)["reader"]["why"].startswith("pinned")


def test_a_pinned_robot_that_is_down_is_switched_away_from():
    store = FakeStore()
    _probe(store, "rootsys", chat_ms=300)
    _probe(store, "mireld", chat_ok=False, chat_ms=10, error="502")
    store.tables[db.SETTINGS] = [{"key": "ai_team", "value": {"pins": {"reader": {"gateway": "mireld"}}}}]
    s = ai_team.route(store, _github(), {}, NOW)
    assert s.base_url == "https://rootsys.cloud/v1"
    assert "switched away" in _state(store)["reader"]["order"][-1]["why"]


def test_an_image_gateway_on_the_reader_slot_never_writes_text():
    """Screenshot 54, 23 Oct 2026: the reader slot was kiosapi.com + gpt-image-2 and every text call answered 400."""
    store = FakeStore()
    cfg = {"reader": {"slot": "reader", "provider": "openai", "base_url": "https://kiosapi.com/v1", "model": "gpt-image-2",
                      "api_key": "kk-1", "key_host": "kiosapi.com"}}
    s = ai_team.route(store, _github(), cfg, NOW)
    assert s.base_url == "https://rootsys.cloud/v1" and s.api_key == "sk-root" and not s.blocked
    st = _state(store)["reader"]
    assert st["skipped"][0]["robot"] == "W3" and "image model" in st["skipped"][0]["why"]
    assert [o["slug"] for o in st["order"]] == ["rootsys", "mireld"]


def test_an_image_model_on_a_text_host_is_skipped_too():
    cands = ai_team.candidates(_github(model="flux-1-schnell"), {})
    assert "image model" in cands[0]["blocked"] and not cands[1]["blocked"]


def test_the_pages_reader_key_is_a_candidate_with_its_own_key():
    store = FakeStore()
    _probe(store, "openai", chat_ms=200)
    _probe(store, "rootsys", chat_ms=900)
    cfg = {"reader": {"slot": "reader", "provider": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini",
                      "api_key": "sk-page", "key_host": "api.openai.com"}}
    s = ai_team.route(store, _github(), cfg, NOW)
    assert s.base_url == "https://api.openai.com/v1" and s.api_key == "sk-page" and s.vision_model == "gpt-4o-mini"
    assert s.fallback_base_url == "https://rootsys.cloud/v1"
    # a key saved for another host is not carried to this one
    cfg["reader"]["key_host"] = "evil.example"
    assert ai_team.route(store, _github(), cfg, NOW).base_url == "https://rootsys.cloud/v1"


def test_no_usable_robot_keeps_the_blocked_reason_for_why_off():
    store = FakeStore()
    cfg = {"reader": {"slot": "reader", "provider": "openai", "base_url": "https://kiosapi.com/v1", "model": "gpt-image-2",
                      "api_key": "kk-1", "key_host": "kiosapi.com"}}
    s = ai_team.route(store, _github(api_key=None, fallback_key=None), cfg, NOW)
    assert "image model" in s.blocked
    assert _state(store)["reader"]["chosen"] is None


def test_an_anthropic_robot_is_never_the_openai_dialect_backup():
    store = FakeStore()
    _probe(store, "mireld", chat_ms=100)
    _probe(store, "anthropic", chat_ms=900)
    g = _github(provider="anthropic", base_url="https://api.anthropic.com", model="claude-haiku-4-5")
    s = ai_team.route(store, g, {}, NOW)
    assert s.base_url == "https://api.mireld.my/v1" and s.fallback_base_url == ""


def test_a_store_that_cannot_be_read_changes_nothing():
    class Broken:
        def table(self, *_a):
            raise RuntimeError("down")
    s = ai_team.route(Broken(), _github(), {}, NOW)
    assert s.base_url == "https://rootsys.cloud/v1" and s.fallback_base_url == "https://api.mireld.my/v1"


def test_llm_for_and_media_for_go_through_the_router(monkeypatch):
    store = FakeStore()
    _probe(store, "mireld", chat_ms=100)
    _probe(store, "rootsys", chat_ms=900)
    monkeypatch.setattr(LLMSettings, "load", classmethod(lambda cls: _github()))
    assert ai_config.llm_for(store).base_url == "https://api.mireld.my/v1"
    pin = {"image_gen": {"gateway": "kiosapi", "model": "gpt-image-2"}}
    store.tables[db.SETTINGS] = [{"key": "ai_team", "value": {"pins": pin}}]
    m = _media(openai_base_url="https://kiosapi.com/v1")
    assert ai_team.route_media(store, m).openai_image_model == "gpt-image-2"
    m = _media(openai_base_url="https://api.openai.com/v1")
    assert ai_team.route_media(store, m).openai_image_model == "gpt-image-1", "a pin for KiosAPI does not move OpenAI"


def test_the_probe_lists_the_painter_without_a_chat_question(monkeypatch):
    posted = []

    class R:
        def __init__(self, status, body):
            self.status_code, self._b, self.text = status, body, str(body)

        def json(self):
            return self._b

    monkeypatch.setattr(api_status.requests, "get",
                        lambda url, **k: R(200, {"data": [{"id": "gpt-image-2"}]}) if url.endswith("/models") else R(404, {}))
    monkeypatch.setattr(api_status.requests, "post", lambda url, **k: posted.append(url) or R(400, "not supported"))
    m = _media(openai_base_url="https://kiosapi.com/v1", openai_image_model="gpt-image-2")
    gws = api_status.gateways(_github(fallback_key=None), m)
    assert [(g["slug"], g["role"]) for g in gws] == [("rootsys", "primary"), ("kiosapi", "image")]
    row = api_status.probe(gws[1])
    assert row["chat_ok"] is True and row["model_listed"] is True and row["error"] == "" and posted == []


def test_kiosapi_may_write_text_with_a_text_model_and_is_judged_by_speed():
    """Wan's reader slot is kiosapi.com + gpt-5.6-sol: a chat model on a gateway that also draws pictures. Judging by the host
    skipped his own text model; the model's name is what decides."""
    store = FakeStore()
    _probe(store, "kiosapi", chat_ms=300)
    _probe(store, "rootsys", chat_ms=2400)
    cfg = {"reader": {"slot": "reader", "provider": "openai", "base_url": "https://kiosapi.com/v1", "model": "gpt-5.6-sol",
                      "api_key": "kk-1", "key_host": "kiosapi.com"}}
    s = ai_team.route(store, _github(), cfg, NOW)
    assert s.base_url == "https://kiosapi.com/v1" and s.model == "gpt-5.6-sol" and s.api_key == "kk-1"
    st = _state(store)["reader"]
    assert st["chosen"]["robot"] == "W3" and st["skipped"] == []


def test_the_motion_job_asks_the_motion_api_first_then_the_team():
    store = FakeStore()
    _probe(store, "mireld", chat_ms=100)
    _probe(store, "rootsys", chat_ms=200)
    _probe(store, "kiosapi", chat_ms=900)
    cfg = {"motion": {"slot": "motion", "provider": "openai", "base_url": "https://kiosapi.com/v1", "model": "gpt-5.6-sol",
                      "api_key": "kk-1", "key_host": "kiosapi.com"}}
    s = ai_team.route(store, _github(), cfg, NOW, job="motion")
    assert s.base_url == "https://kiosapi.com/v1" and s.model == "gpt-5.6-sol", "its own API first even though slower"
    assert s.fallback_base_url == "https://api.mireld.my/v1", "the fastest of the team is the backup"
    st = _state(store)["motion"]
    assert st["chosen"]["slug"] == "kiosapi" and [o["slug"] for o in st["order"]] == ["kiosapi", "mireld", "rootsys"]
    # the reader job ignores the motion slot
    assert ai_team.route(store, _github(), cfg, NOW).base_url == "https://api.mireld.my/v1"
    assert _state(store)["reader"]["order"][0]["slug"] == "mireld"
    # the motion API down: the team answers
    _probe(store, "kiosapi", chat_ok=False, chat_ms=50, error="402 overage")
    store.tables[db.API_STATUS] = [r for r in store.tables[db.API_STATUS] if not (r["slug"] == "kiosapi" and r["chat_ok"])]
    assert ai_team.route(store, _github(), cfg, NOW, job="motion").base_url == "https://api.mireld.my/v1"
