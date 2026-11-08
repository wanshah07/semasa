"""Extra AI providers added from the API tab (supabase/074, semasa.ai_providers): a provider is a robot for its jobs only, its key
goes only to its own host, a switched-off one is skipped, Telegram may pin it, and the probe writes its row."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import ai_providers, ai_team, api_status, db, telegram_tools
from semasa.config import LLMSettings

NOW = datetime(2026, 11, 8, 6, 0, tzinfo=UTC)


def github(**kw):
    base = dict(provider="openai", api_key="sk-root", base_url="https://rootsys.cloud/v1", model="gpt-4.1-mini", timeout=30,
                fallback_base_url="https://api.mireld.my/v1", fallback_key="mk-1", fallback_model="claude-sonnet-5.5")
    base.update(kw)
    return LLMSettings(**base)


def provider(pid="claude", **over):
    row = {"id": pid, "name": "Claude", "dialect": "anthropic", "base_url": "https://api.anthropic.com",
           "model": "claude-sonnet-5.5", "key_hint": "…1234", "key_host": "api.anthropic.com", "enabled": True,
           "jobs": ["chat", "reader", "ideas", "motion", "telegram"], "created_at": "2026-11-08T01:00:00+00:00"}
    row.update(over)
    return row


def store(*rows, keys=None, **tables):
    keys = keys if keys is not None else {r["id"]: f"key-{r['id']}-1234" for r in rows}
    return FakeStore(**{ai_providers.TABLE: list(rows),
                        ai_providers.SECRETS: [{"id": k, "api_key": v} for k, v in keys.items()], **tables})


def slow(*slugs):
    """The robots probed an hour ago and DOWN (Wan's order, 8 Nov 2026, puts a provider after the five he ranked)."""
    return [{"slug": s, "chat_ok": False, "chat_ms": 9000, "error": "502", "checked_at": (NOW - timedelta(hours=1)).isoformat()}
            for s in slugs]


# ---- loading and the key rule ------------------------------------------------------------------------------------------------

def test_a_provider_is_a_robot_numbered_after_the_built_in_five_with_its_dialect_and_key():
    st = store(provider(), provider("kios2", name="KiosAPI 2", dialect="openai", base_url="https://kiosapi.com/v1",
                                    key_host="kiosapi.com", model="gpt-5.6-sol", created_at="2026-11-08T02:00:00+00:00"))
    cands = ai_providers.candidates(st, "reader")
    assert [(c["slug"], c["robot"], c["name"], c["provider"], c["key"]) for c in cands] == [
        ("claude", "W6", "Claude", "anthropic", "key-claude-1234"), ("kios2", "W7", "KiosAPI 2", "openai", "key-kios2-1234")]
    assert all(c["source"] == "provider" and not c["blocked"] for c in cands)
    assert ai_team.robots(st)["claude"] == {"robot": "W6", "name": "Claude", "tone": "provider", "does": ["read", "write"],
                                            "added": True}
    assert ai_team.robots(st)["rootsys"]["robot"] == "W1"


def test_the_key_goes_only_to_the_host_it_was_saved_for():
    # the endpoint moved (the database would have dropped the key; a stale key_host must still never follow the address)
    moved = store(provider(base_url="https://evil.example/v1"))
    assert ai_providers.candidates(moved, "reader") == []
    assert ai_providers.gateways(moved) == []
    # no key at all: not a robot
    assert ai_providers.candidates(store(provider(), keys={}), "reader") == []


def test_a_switched_off_provider_is_skipped_and_keeps_its_number():
    st = store(provider(enabled=False), provider("kios2", dialect="openai", base_url="https://kiosapi.com/v1",
                                                 key_host="kiosapi.com", created_at="2026-11-08T02:00:00+00:00"))
    assert [c["slug"] for c in ai_providers.candidates(st, "reader")] == ["kios2"]
    assert ai_providers.candidates(st, "reader")[0]["robot"] == "W7"
    assert [g["slug"] for g in ai_providers.gateways(st)] == ["kios2"]


def test_a_provider_is_a_candidate_for_its_jobs_only():
    st = store(provider(jobs=["motion"]))
    assert [c["slug"] for c in ai_providers.candidates(st, "motion")] == ["claude"]
    assert ai_providers.candidates(st, "reader") == []
    assert ai_providers.candidates(st, "ideas") == []
    # null or an empty list means every job, as the edge functions read it
    assert [c["slug"] for c in ai_providers.candidates(store(provider(jobs=None)), "motion")] == ["claude"]
    assert [c["slug"] for c in ai_providers.candidates(store(provider(jobs=[])), "reader")] == ["claude"]


def test_a_reserved_id_or_a_missing_table_gives_no_robot():
    assert ai_providers.load(store(provider("gemini"))) == []
    assert ai_providers.load(FakeStore()) == []            # 074 not applied: the team is what it was

    class Broken:
        def table(self, name):
            raise RuntimeError("no such table")
    assert ai_providers.load(Broken()) == []
    assert ai_providers.candidates(Broken(), "reader") == []


def test_an_image_model_on_a_provider_is_named_as_skipped_not_dropped():
    painter = provider("painter", dialect="openai", base_url="https://kiosapi.com/v1", key_host="kiosapi.com",
                       model="gpt-image-2")
    c = ai_providers.candidates(store(painter), "reader")[0]
    assert "image model" in c["blocked"]


# ---- the router --------------------------------------------------------------------------------------------------------------

def test_the_router_writes_with_an_anthropic_provider_when_the_ranked_robots_are_down_and_carries_the_dialect():
    st = store(provider())
    st.tables[db.API_STATUS] = slow("rootsys", "mireld") + [{"slug": "claude", "chat_ok": True, "chat_ms": 400, "error": "",
                                                              "checked_at": (NOW - timedelta(hours=1)).isoformat()}]
    got = ai_team.route(st, github(), {}, NOW)
    assert got.provider == "anthropic" and got.base_url == "https://api.anthropic.com" and got.api_key == "key-claude-1234"
    assert got.model == "claude-sonnet-5.5"
    assert got.fallback_base_url in ("https://rootsys.cloud/v1", "https://api.mireld.my/v1")    # the backup speaks OpenAI
    state = [r for r in st.tables[db.SETTINGS] if r["key"] == ai_team.STATE_KEY][0]["value"]["reader"]
    assert state["chosen"] == {"slug": "claude", "robot": "W6", "name": "Claude", "model": "claude-sonnet-5.5"}
    # the usage sink files this provider's calls under its own slug
    assert api_status.slug_of("https://api.anthropic.com") == ("anthropic", "Anthropic"), "a built-in host keeps its name"
    api_status.remember_providers([provider("mygw", base_url="https://gw.example.my/v1")])
    assert api_status.slug_of("https://gw.example.my/v1") == ("mygw", "Claude")
    api_status.remember_providers([])


def test_a_pin_may_name_a_provider_and_a_provider_off_for_the_job_is_not_asked():
    pin = {"key": "ai_team", "value": {"pins": {"reader": {"gateway": "claude", "model": "claude-haiku"}}}}
    st = store(provider(jobs=["reader"]), **{db.SETTINGS: [pin]})
    st.tables[db.API_STATUS] = [{"slug": "claude", "chat_ok": True, "chat_ms": 4000, "error": "",
                                 "checked_at": (NOW - timedelta(hours=1)).isoformat()}] + [
        {"slug": "rootsys", "chat_ok": True, "chat_ms": 300, "error": "", "checked_at": (NOW - timedelta(hours=1)).isoformat()}]
    got = ai_team.route(st, github(), {}, NOW)
    assert got.base_url == "https://api.anthropic.com" and got.model == "claude-haiku" and got.provider == "anthropic"
    motion = ai_team.route(st, github(), {}, NOW, job="motion")
    assert motion.base_url == "https://rootsys.cloud/v1"
    state = [r for r in st.tables[db.SETTINGS] if r["key"] == ai_team.STATE_KEY][0]["value"]["motion"]
    assert "claude" not in [o["slug"] for o in state["order"]]


def test_without_a_provider_the_team_is_exactly_what_it_was():
    st = FakeStore()
    got = ai_team.route(st, github(), {}, NOW)
    assert got.base_url == "https://rootsys.cloud/v1" and got.fallback_base_url == "https://api.mireld.my/v1"
    assert [c["slug"] for c in ai_team.candidates(github(), {})] == ["rootsys", "mireld"]


# ---- the probe ---------------------------------------------------------------------------------------------------------------

def test_the_probe_writes_one_row_per_provider_with_role_provider_and_the_anthropic_calls(monkeypatch):
    asked: list[tuple[str, str, str]] = []

    def models(gw, timeout):
        asked.append(("models", gw["provider"], gw["base_url"]))
        return ["claude-sonnet-5.5", "claude-haiku"], 200, 120, ""

    def chat(gw, timeout):
        asked.append(("chat", gw["provider"], gw["base_url"]))
        return True, 350, {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}, ""

    monkeypatch.setattr(api_status, "_models", models)
    monkeypatch.setattr(api_status, "_chat", chat)
    monkeypatch.setattr(api_status, "_balance", lambda gw, timeout: {})
    st = store(provider(), **{db.SETTINGS: [], db.LOG: []})
    rows = api_status.run(st, github(fallback_key=None), extra=ai_providers.gateways(st))
    row = next(r for r in rows if r["slug"] == "claude")
    assert row["role"] == "provider" and row["name"] == "Claude" and row["chat_ok"] is True and row["key_last4"] == "1234"
    assert row["model_listed"] is True and row["models"] == ["claude-sonnet-5.5", "claude-haiku"]
    assert ("models", "anthropic", "https://api.anthropic.com") in asked
    assert ("chat", "anthropic", "https://api.anthropic.com") in asked
    stored = {r["slug"]: r for r in st.tables[db.API_STATUS]}
    assert stored["claude"]["role"] == "provider" and "rootsys" in stored


def test_the_anthropic_dialect_uses_x_api_key_and_v1_messages(monkeypatch):
    calls: list[dict] = []

    class R:
        status_code = 200
        text = "{}"

        def json(self):
            return {"data": [{"id": "claude-haiku"}], "usage": {"input_tokens": 3, "output_tokens": 2}}

    def fake(method, url, **kw):
        calls.append({"method": method, "url": url, **kw})
        return R()

    monkeypatch.setattr(api_status.requests, "get", lambda url, **kw: fake("GET", url, **kw))
    monkeypatch.setattr(api_status.requests, "post", lambda url, **kw: fake("POST", url, **kw))
    gw = ai_providers.gateways(store(provider()))[0]
    assert api_status._models(gw, 5)[0] == ["claude-haiku"]
    ok, _ms, usage, err = api_status._chat(gw, 5)
    assert ok and usage["total_tokens"] == 5 and not err
    assert calls[0]["url"] == "https://api.anthropic.com/v1/models" and calls[0]["headers"]["x-api-key"] == "key-claude-1234"
    assert calls[1]["url"] == "https://api.anthropic.com/v1/messages" and calls[1]["headers"]["anthropic-version"]
    assert "Authorization" not in calls[0]["headers"] and "Authorization" not in calls[1]["headers"]


# ---- Telegram ----------------------------------------------------------------------------------------------------------------

def test_telegram_may_pin_an_enabled_provider_and_not_a_switched_off_one():
    off = provider("off", enabled=False, dialect="openai", base_url="https://gw.example.my/v1", key_host="gw.example.my")
    st = store(provider(), off)
    assert telegram_tools.pinnable(st) == ("rootsys", "mireld", "kiosapi", "gemini", "claude")
    assert telegram_tools.pinnable(FakeStore()) == telegram_tools.PINNABLE
    def srow(slug, model, role, ms):
        return {"slug": slug, "name": slug, "model": model, "chat_ok": True, "chat_ms": ms, "role": role, "error": ""}
    st.tables[db.API_STATUS] = [srow("claude", "claude-sonnet-5.5", "provider", 400), srow("off", "m", "provider", 400),
                                srow("rootsys", "glm-5.3", "primary", 1800)]
    st.tables[db.SETTINGS] = []
    rows = {r["slug"]: r for r in telegram_tools.team(st)["rows"]}
    assert rows["claude"]["pinnable"] and rows["claude"]["robot"] == "W6" and rows["claude"]["name"] == "Claude"
    assert not rows["off"]["pinnable"] and rows["off"]["robot"] == "W7"
    assert telegram_tools.set_pin(st, "claude").startswith("📌 W6 Claude")
    pins = [r for r in st.tables[db.SETTINGS] if r["key"] == "ai_team"][0]["value"]["pins"]
    assert pins["reader"] == {"gateway": "claude", "model": "claude-sonnet-5.5"}
