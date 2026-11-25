"""How much API credit is left and until when (api_credit.py, api_status.credit_run): the shapes the gateways really answer, the
expiry forms, the status thresholds, and that `tried` carries key names and never a value."""

import json
from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import api_credit as ac
from semasa import api_status, db

NOW = datetime(2026, 11, 23, 15, 31, 50, tzinfo=UTC)          # 23 Nov 2026 23:31:50 MYT, when Wan read Mireld's dashboard

# what Mireld answers, read from the table on 23 Nov 2026
MIRELD = {"object": "credit_summary", "total_used": 1185.886891, "total_granted": 1275, "total_available": 89.113109}
# what KiosAPI answers on /dashboard/billing/subscription: a sentinel hard limit, no expiry, no remaining figure
KIOS = {"object": "billing_subscription", "has_payment_method": True, "access_until": 0, "hard_limit_usd": 100000000,
        "soft_limit_usd": 100000000, "system_hard_limit_usd": 100000000}


class R:
    def __init__(self, status, body):
        self.status_code, self._b = status, body

    def json(self):
        if isinstance(self._b, Exception):
            raise self._b
        return self._b


def _gw(slug="mireld", base="https://api.mireld.my/v1", key="sk-live-SECRETVALUE1234567890"):
    return {"slug": slug, "name": slug, "role": "backup", "base_url": base, "key": key, "model": "m", "provider": "openai"}


# ---- the shapes ----------------------------------------------------------------------------------------------------------------

def test_mireld_credit_summary_is_read_and_scaled_like_its_dashboard():
    f = ac.facts_of(MIRELD)
    assert (f["remaining"], f["total"], f["used"]) == (89.113109, 1275.0, 1185.886891)
    c = ac.credit_from("mireld", [("/dashboard/billing/credit_grants", f)], NOW)
    assert c["percent_left"] == 7.0                       # the dashboard says 93% used
    assert c["source"] == "/dashboard/billing/credit_grants" and c["unit"] == "credit"
    assert c["display_scale"] == 1_000_000                # 89.11 x 1e6 = 89.1M, the dashboard's 88.83M a few minutes later
    assert round(c["remaining"] * c["display_scale"] / 1e6) == 89 and c["total"] * c["display_scale"] == 1_275_000_000
    assert c["status"] == "low"                           # under 15% left
    assert c["expires_at"] is None                        # this answer carries no date


def test_no_dashboard_factor_for_a_gateway_it_was_not_measured_on():
    c = ac.credit_from("rootsys", [("/x", ac.facts_of(MIRELD))], NOW)
    assert c["display_scale"] is None and c["remaining"] == 89.113109


def test_kiosapi_subscription_has_no_remaining_figure_and_is_unknown():
    assert ac.facts_of(KIOS) == {}                        # a 100,000,000 USD limit is "no limit", access_until 0 is "no date"
    c = ac.credit_from("kiosapi", [], NOW)
    assert c["status"] == "unknown" and c["remaining"] is None and c["source"] is None and c["expires_at"] is None


def test_an_empty_object_says_nothing():
    assert ac.facts_of({}) == {} and ac.facts_of([]) == {} and ac.facts_of(None) == {} and ac.facts_of("<html>") == {}


def test_new_api_token_usage_is_unwrapped_from_data_and_zero_expiry_means_none():
    j = {"code": True, "message": "ok", "data": {"object": "billing_token_usage", "name": "k", "total_granted": 500,
                                                   "total_used": 125, "total_available": 375, "unlimited_quota": False,
                                                   "expires_at": 0}}
    c = ac.credit_from("rootsys", [("/api/usage/token", ac.facts_of(j))], NOW)
    assert (c["remaining"], c["total"], c["used"], c["percent_left"]) == (375.0, 500.0, 125.0, 75.0)
    assert c["expires_at"] is None and c["status"] == "ok"


def test_new_api_user_self_quota_is_what_is_left_beside_used_quota():
    f = ac.facts_of({"success": True, "data": {"quota": 545_100_000, "used_quota": 2_030_000_000, "request_count": 71908}})
    assert f["remaining"] == 545_100_000 and f["used"] == 2_030_000_000
    c = ac.credit_from("rootsys", [("/api/user/self", f)], NOW)
    assert c["total"] == 2_575_100_000 and c["percent_left"] == 21.2        # Wan's rootsys dashboard: 545.1M, 21% left


def test_a_total_and_what_is_used_give_what_is_left():
    c = ac.credit_from("x", [("/p", ac.facts_of({"hard_limit_usd": 100, "total_usage": 2500}))], NOW)   # 2500 hundredths = 25 USD
    assert c["remaining"] == 75.0 and c["unit"] == "USD" and c["percent_left"] == 75.0


def test_openai_style_grants_give_the_earliest_future_expiry_and_skip_a_spent_grant():
    j = {"object": "credit_summary", "total_granted": 100, "total_used": 60, "total_available": 40,
         "grants": {"object": "list", "data": [
             {"grant_amount": 10, "used_amount": 10, "effective_at": 1700000000, "expires_at": 1766000000},
             {"grant_amount": 90, "used_amount": 50, "effective_at": 1760000000, "expires_at": "2026-12-09T15:31:50Z"},
             {"grant_amount": 5, "used_amount": 0, "effective_at": 1760000000, "expires_at": 1999999999}]}}
    c = ac.credit_from("mireld", [("/dashboard/billing/credit_grants", ac.facts_of(j))], NOW)
    assert c["expires_at"] == "2026-12-09T15:31:50Z"      # 1766000000 is a spent grant, 1999999999 is later
    assert len(c["grants"]) == 3 and c["grants"][0]["amount"] == 10.0


def test_an_expiry_found_on_another_path_is_used_when_the_balance_path_has_none():
    a = ("/dashboard/billing/credit_grants", ac.facts_of(MIRELD))
    b = ("/api/usage/token", ac.facts_of({"data": {"expires_at": 1796830310}}))
    c = ac.credit_from("mireld", [a, b], NOW)
    assert c["remaining"] == 89.113109 and c["expires_at"] == "2026-12-09T15:31:50Z"


# ---- expiry forms --------------------------------------------------------------------------------------------------------------

def test_parse_expiry_reads_seconds_milliseconds_iso_and_zero():
    iso = "2026-12-09T15:31:50Z"
    assert ac.parse_expiry(1796830310) == iso
    assert ac.parse_expiry(1796830310000) == iso
    assert ac.parse_expiry("1796830310") == iso
    assert ac.parse_expiry("2026-12-09T15:31:50Z") == iso
    assert ac.parse_expiry("2026-12-09T23:31:50+08:00") == iso
    assert ac.parse_expiry("2026-12-09 15:31:50") == iso           # no zone: UTC
    for none in (0, "0", None, "", False, -1, "never", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z", 4102444800000000, [], {}):
        assert ac.parse_expiry(none) is None, none


# ---- status --------------------------------------------------------------------------------------------------------------------

def test_status_thresholds():
    s = ac.status_of
    assert s({"remaining": 50, "percent_left": 50}, NOW) == "ok"
    assert s({"remaining": 15, "percent_left": 15.0}, NOW) == "ok"
    assert s({"remaining": 14.9, "percent_left": 14.9}, NOW) == "low"
    assert s({"remaining": 0, "percent_left": 0}, NOW) == "low"
    assert s({"remaining": 50, "percent_left": 50, "expires_at": (NOW + timedelta(days=6, hours=23)).isoformat()}, NOW) == "low"
    assert s({"remaining": 50, "percent_left": 50, "expires_at": (NOW + timedelta(days=7, hours=1)).isoformat()}, NOW) == "ok"
    assert s({"remaining": 50, "percent_left": 50, "expires_at": (NOW - timedelta(seconds=1)).isoformat()}, NOW) == "expired"
    assert s({"remaining": None, "expires_at": None}, NOW) == "unknown"
    assert s({}, NOW) == "unknown"
    assert s({"remaining": None, "expires_at": (NOW + timedelta(days=30)).isoformat()}, NOW) == "ok", "a date alone is a reading"
    assert s({"remaining": None, "unlimited": True}, NOW) == "ok"


def test_a_stored_reading_ages_into_expired_on_its_own():
    c = ac.credit_from("mireld", [("/p", {**ac.facts_of(MIRELD), "expiries": ["2026-12-09T15:31:50Z"],
                                          "live_expiries": ["2026-12-09T15:31:50Z"]})], NOW)
    assert c["status"] == "low"                                   # 7% left (and 16 days to run)
    assert ac.status_of(c, datetime(2026, 12, 9, 15, 31, 51, tzinfo=UTC)) == "expired"


# ---- asking --------------------------------------------------------------------------------------------------------------------

def _fake_get(table, log):
    def get(url, headers=None, timeout=None, allow_redirects=True, **_):
        log.append((url, dict(headers or {}), allow_redirects))
        for tail, resp in table.items():
            if url.endswith(tail):
                return resp if not isinstance(resp, Exception) else (_ for _ in ()).throw(resp)
        return R(404, {"error": "no"})
    return get


def test_check_reads_mireld_and_never_sends_the_key_to_another_host_nor_follows_a_redirect():
    log = []
    get = _fake_get({"/dashboard/billing/credit_grants": R(200, MIRELD)}, log)
    bal = ac.check(_gw(), now=NOW, get=get)
    assert bal["credit"]["remaining"] == 89.113109
    assert bal["credit"]["source"] == "/dashboard/billing/credit_grants"
    assert bal["path"] == "/dashboard/billing/credit_grants" and bal["total_available"] == 89.113109   # the API page's one line
    assert bal["checked_at"] == "2026-11-23T15:31:50Z"
    assert all(url.startswith("https://api.mireld.my/") for url, _h, _r in log)
    assert all(h["Authorization"].startswith("Bearer sk-live") for _u, h, _r in log)
    assert all(r is False for _u, _h, r in log), "a redirect could lead to another host"
    # no expiry yet, so it keeps asking the remaining paths (and records them)
    paths = [t["path"] for t in bal["tried"]]
    assert "/api/usage/token" in paths and "/api/user/self" in paths and "/dashboard/billing/subscription" in paths
    assert len(paths) == len(set(paths)), "/v1/credits is the same address as /credits under a /v1 base: asked once"


def test_check_stops_when_it_has_both_a_figure_and_a_date():
    log = []
    body = {**MIRELD, "grants": {"data": [{"grant_amount": 1275, "used_amount": 1185, "expires_at": 1796830310}]}}
    bal = ac.check(_gw(), now=NOW, get=_fake_get({"/dashboard/billing/credit_grants": R(200, body)}, log))
    assert bal["credit"]["expires_at"] == "2026-12-09T15:31:50Z" and bal["credit"]["status"] == "low"
    assert len(log) == 1


def test_tried_carries_key_names_only_never_a_value():
    secret = "sk-9f8e7d6c5b4a39281706f5e4d3c2b1a0"
    body = {"success": True, "models": [{"id": "gpt-x", "owner": "someone"}],
            "data": {"access_token": secret, "email": "wan@example.com", "quota": 0, "username": "wanshah", secret: 1}}
    get = _fake_get({"/api/user/self": R(200, body), "/api/status": R(200, {})}, [])
    bal = ac.check(_gw("rootsys", "https://rootsys.cloud/v1"), now=NOW, get=get)
    blob = json.dumps(bal["tried"])
    for value in (secret, "wan@example.com", "wanshah", "someone", "gpt-x"):
        assert value not in blob, value
    me = next(t for t in bal["tried"] if t["path"] == "/api/user/self")
    assert "data.access_token" in me["keys"] and "data.email" in me["keys"] and "models[].id" in me["keys"]
    assert "data.(id)" in me["keys"], "a key NAME that is itself a token is hidden"
    assert me["http"] == 200 and me["shape"] == "json"
    empty = next(t for t in bal["tried"] if t["path"] == "/api/status")
    assert empty["shape"] == "{}" and empty["keys"] == [] and empty["read"] is False
    assert "SECRETVALUE" not in json.dumps(bal), "the gateway's own key is never stored"


def test_tried_records_errors_html_and_redirects_by_kind():
    get = _fake_get({"/balance": R(200, ValueError("html")), "/credits": R(302, {}), "/usage": R(500, {"error": "x"}),
                     "/key": ac.requests.ConnectionError("down with sk-secret-url")}, [])
    bal = ac.check(_gw(), now=NOW, get=get)
    by = {t["path"]: t for t in bal["tried"]}
    assert by["/balance"]["shape"] == "not JSON" and by["/credits"]["shape"] == "redirect" and by["/usage"]["http"] == 500
    assert by["/key"]["http"] is None and by["/key"]["shape"] == "error: ConnectionError"
    assert "sk-secret-url" not in json.dumps(bal), "an exception's text can carry a URL: only its class is kept"
    assert bal["credit"]["status"] == "unknown"


def test_kiosapi_and_rootsys_today_show_every_path_and_an_honest_unknown():
    log = []
    get = _fake_get({"/dashboard/billing/subscription": R(200, KIOS)}, log)
    bal = ac.check(_gw("kiosapi", "https://kiosapi.com/v1"), now=NOW, get=get)
    assert bal["credit"]["status"] == "unknown" and bal["credit"]["source"] is None and "path" not in bal
    sub = next(t for t in bal["tried"] if t["path"] == "/dashboard/billing/subscription")
    assert sub["http"] == 200 and "hard_limit_usd" in sub["keys"] and sub["read"] is False
    assert len(bal["tried"]) >= 10
    root = ac.check(_gw("rootsys", "https://rootsys.cloud/v1"), now=NOW, get=_fake_get({}, []))
    assert {t["http"] for t in root["tried"]} == {404} and root["credit"]["status"] == "unknown"


def test_usage_endpoint_is_asked_with_this_months_dates():
    log = []
    ac.check(_gw(), now=NOW, get=_fake_get({}, log))
    assert any("/dashboard/billing/usage?start_date=2026-11-01&end_date=2026-11-24" in u for u, _h, _r in log)


# ---- a check that could not reach the gateway keeps the last good figure ------------------------------------------------------

def test_a_gateway_that_cannot_be_reached_keeps_its_last_figure_marked_stale():
    good = ac.check(_gw(), now=NOW, get=_fake_get({"/dashboard/billing/credit_grants": R(200, MIRELD)}, []))
    down = ac.requests.ConnectionError("down")
    later = NOW + timedelta(minutes=15)
    bad = ac.check(_gw(), now=later, prev=good, get=lambda *a, **k: (_ for _ in ()).throw(down))
    assert bad["credit"]["remaining"] == 89.113109 and bad["credit"]["stale"] is True
    assert bad["credit"]["stale_since"] == "2026-11-23T15:31:50Z" and bad["tried"][0]["http"] is None
    # a gateway that ANSWERED but no longer shows a figure is not kept: the page must not show a number the gateway stopped giving
    answered = ac.check(_gw(), now=later, prev=good, get=_fake_get({}, []))
    assert answered["credit"]["remaining"] is None and not answered["credit"].get("stale")


# ---- the credit-only run -------------------------------------------------------------------------------------------------------

def test_credit_run_writes_only_balance_and_only_for_the_three_gateways(monkeypatch):
    store = FakeStore(**{db.API_STATUS: [
        {"slug": "mireld", "name": "Mireld", "chat_ok": True, "models": ["a"], "checked_at": "2026-11-23T15:30:00Z",
         "balance": {}},
        {"slug": "gemini", "name": "Gemini", "chat_ok": True, "balance": {}}]})
    monkeypatch.setattr(api_status.requests, "get", _fake_get({"/dashboard/billing/credit_grants": R(200, MIRELD)}, []))
    gws = [_gw(), _gw("gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
           _gw("rootsys", "https://rootsys.cloud/v1", key=""), _gw("kiosapi", "https://kiosapi.com/v1")]
    done = api_status.credit_run(store, gws, now=NOW)
    assert [d["slug"] for d in done] == ["mireld", "kiosapi"]       # gemini is not one of the three, rootsys has no key here
    rows = {r["slug"]: r for r in store.tables[db.API_STATUS]}
    assert rows["mireld"]["balance"]["credit"]["remaining"] == 89.113109
    assert rows["mireld"]["chat_ok"] is True and rows["mireld"]["models"] == ["a"]
    assert rows["mireld"]["checked_at"] == "2026-11-23T15:30:00Z"
    assert rows["gemini"]["balance"] == {}
    assert "kiosapi" not in rows, "no row is invented: the 6-hourly probe makes it"


def test_the_full_probe_gives_the_three_gateways_the_credit_reading_and_others_the_old_one(monkeypatch):
    seen = []

    def fake_get(url, headers=None, timeout=None, **_):
        seen.append(url)
        if url.endswith("/models"):
            return R(200, {"data": [{"id": "m"}]})
        if url.endswith("/dashboard/billing/credit_grants"):
            return R(200, MIRELD)
        return R(404, {})

    monkeypatch.setattr(api_status.requests, "get", fake_get)
    monkeypatch.setattr(api_status.requests, "post", lambda *a, **k: R(200, {"choices": []}))
    row = api_status.probe(_gw())
    assert row["balance"]["credit"]["remaining"] == 89.113109 and row["balance"]["tried"]
    other = api_status.probe(_gw("openai", "https://api.openai.com/v1"))
    assert "credit" not in other["balance"] and "tried" not in other["balance"]


# ---- the watchdog (health.py reports it with the other problems) ---------------------------------------------------------------

def test_the_watchdog_names_a_low_or_expired_credit_and_stays_quiet_about_an_unreadable_one():
    from semasa import health

    def row(slug, name, credit, key_set=True):
        return {"slug": slug, "name": name, "key_set": key_set, "balance": {"credit": credit} if credit is not None else {}}

    mireld = ac.credit_from("mireld", [("/p", {**ac.facts_of(MIRELD), "live_expiries": ["2026-12-09T15:31:50Z"],
                                               "expiries": ["2026-12-09T15:31:50Z"]})], NOW)
    ok_body = {"data": {"total_granted": 100, "total_available": 80, "total_used": 20}}
    healthy = ac.credit_from("rootsys", [("/p", ac.facts_of(ok_body))], NOW)
    unknown = ac.credit_from("kiosapi", [], NOW)
    store = FakeStore(**{db.API_STATUS: [row("mireld", "Mireld", mireld), row("rootsys", "rootsys (Afiq)", healthy),
                                         row("kiosapi", "KiosAPI", unknown), row("gemini", "Gemini", {**mireld})]})
    out = health.check_credit(store, NOW)
    assert [p["what"] for p in out] == ["Mireld: its credit is running low (89.11M left, 7% of the plan, valid until 2026-12-09)"]
    later = datetime(2026, 12, 10, tzinfo=UTC)
    gone = health.check_credit(store, later)
    assert [p["what"].split(":")[0] for p in gone] == ["Mireld"] and "has expired" in gone[0]["what"]
    assert health.check_credit(FakeStore(**{db.API_STATUS: [row("mireld", "Mireld", mireld, key_set=False)]}), NOW) == []


# ---- rootsys and KiosAPI (Wan, 23 Nov 2026: "fix rootsys and Kioskapi") --------------------------------------------------------

# what https://rootsys.cloud/v1/quota answered on 23 Nov 2026 (Wan's dashboard: 545.1M left, 21%)
ROOTSYS = {"tokens_remaining": "537588605", "tokens_total": "2570880000", "tokens_used": "2033291395",
           "expires_at": "2026-12-19T17:07:35.382Z", "seconds_remaining": 2251368.586, "days_remaining": 26.05, "active": True,
           "status": "active", "snapshot_at": "2026-11-23T15:44:46.796Z"}


def test_rootsys_quota_gives_tokens_left_of_the_total_and_its_validity():
    f = ac.facts_of(ROOTSYS)
    assert (f["remaining"], f["total"], f["used"], f["unit"]) == (537588605.0, 2570880000.0, 2033291395.0, "tokens")
    c = ac.credit_from("rootsys", [("/quota", f)], NOW)
    assert c["percent_left"] == 20.9 and c["unit"] == "tokens" and c["display_scale"] is None
    assert c["expires_at"] == "2026-12-19T17:07:35Z" or c["expires_at"].startswith("2026-12-19T17:07:35")
    assert c["status"] == "ok"


def test_rootsys_is_read_through_its_quota_path_and_stops_there():
    log = []
    bal = ac.check(_gw("rootsys", "https://rootsys.cloud/v1"), now=NOW, get=_fake_get({"/v1/quota": R(200, ROOTSYS)}, log))
    assert bal["credit"]["source"] == "/quota" and bal["credit"]["remaining"] == 537588605.0
    assert any(t["path"] == "/quota" and t["read"] for t in bal["tried"])


def test_a_new_api_key_with_no_limit_is_not_a_balance_and_the_slash_path_is_asked():
    token = {"data": {"name": "k", "total_granted": 0, "total_used": 0, "total_available": 0, "unlimited_quota": True,
                      "expires_at": 0}, "message": "ok", "success": True}
    assert ac.facts_of(token) == {}, "an unlimited key says nothing about the account's top-up"
    slash = ac.ROOT_PATHS.index("/api/usage/token/")
    assert slash < ac.ROOT_PATHS.index("/api/usage/token")
    limited = {"data": {"total_granted": 500000, "total_used": 125000, "total_available": 375000, "unlimited_quota": False,
                        "expires_at": 1798000000}, "success": True}
    f = ac.facts_of(limited)
    assert f["remaining"] == 375000.0 and f["total"] == 500000.0


def test_the_account_is_asked_with_the_access_token_and_user_id_and_read_in_dollars():
    env = {"KIOSAPI_ACCESS_TOKEN": "tok-SECRET", "KIOSAPI_USER_ID": "42"}
    assert ac.account_headers("kiosapi", {}) is None and ac.account_headers("kiosapi", {"KIOSAPI_ACCESS_TOKEN": "x"}) is None
    hdr = ac.account_headers("kiosapi", env)
    assert hdr["New-Api-User"] == "42" and hdr["Authorization"] == "Bearer tok-SECRET"
    seen = {}

    def get(url, headers=None, **kw):
        seen[url] = headers
        if url.endswith("/api/user/self"):
            return R(200, {"success": True, "data": {"quota": 2500000, "used_quota": 7500000, "username": "x"}})
        if url.endswith("/api/status"):
            return R(200, {"data": {"quota_per_unit": 500000}})
        return R(404, {"error": "no"})
    import os
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        bal = ac.check(_gw("kiosapi", "https://kiosapi.com/v1"), now=NOW, get=get)
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
    c = bal["credit"]
    assert c["unit"] == "USD" and c["remaining"] == 5.0 and c["total"] == 20.0 and c["percent_left"] == 25.0
    assert seen["https://kiosapi.com/api/user/self"]["New-Api-User"] == "42"
    assert not any("tok-SECRET" in json.dumps(t) for t in bal["tried"]), "the token never reaches the stored reading"


# ---- what a New-API key says of itself (KiosAPI, 24 Nov 2026) ------------------------------------------------------------------

KIOS_TOKEN = {"code": True, "message": "ok", "data": {"object": "token_usage", "name": "semasa", "total_granted": 0,
                                                       "total_used": 1250000, "total_available": 0, "unlimited_quota": True,
                                                       "model_limits": {}, "model_limits_enabled": False, "expires_at": 0}}


def test_an_unlimited_key_with_no_end_date_says_so_and_what_it_spent_and_is_never_a_balance(monkeypatch):
    monkeypatch.delenv("KIOSAPI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KIOSAPI_USER_ID", raising=False)
    get = _fake_get({"/api/usage/token/": R(200, KIOS_TOKEN), "/dashboard/billing/subscription": R(200, KIOS),
                     "/api/status": R(200, {"success": True, "data": {"quota_per_unit": 500000}})}, [])
    bal = ac.check(_gw("kiosapi", "https://kiosapi.com/v1"), now=NOW, get=get)
    c = bal["credit"]
    assert c["remaining"] is None and c["source"] is None and c["status"] == "unknown"       # still no BALANCE: honest
    assert c["key"] == {"unlimited": True, "never_expires": True, "used": 2.5, "unit": "USD", "account_read": False}
    assert ac.key_facts({"data": {"unlimited_quota": False, "expires_at": 1798761600, "total_used": 5}}) == {
        "unlimited": False, "used_points": 5.0}                                              # a dated, capped key: no "never"
    assert ac.key_facts({"total_available": 5}) == {} and ac.key_facts(None) == {}           # any other answer: nothing
    plain = ac.check(_gw(), now=NOW, get=_fake_get({"/dashboard/billing/credit_grants": R(200, MIRELD)}, []))
    assert "key" not in plain["credit"]                                                      # one with a balance: unchanged


# ---- the account key typed into Semasa (supabase/096, 24 Nov 2026) ----------------------------------------------------

def test_an_account_key_typed_in_semasa_reads_the_account_and_goes_only_to_that_gateways_host(monkeypatch):
    from fakestore import FakeStore
    monkeypatch.delenv("KIOSAPI_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KIOSAPI_USER_ID", raising=False)
    store = FakeStore(**{ac.ACCOUNTS_TABLE: [{"slug": "kiosapi", "access_token": "acct-token-typed-1234", "user_id": "77"},
                                             {"slug": "elsewhere", "access_token": "x" * 20, "user_id": "1"},
                                             {"slug": "mireld", "access_token": "", "user_id": "5"}]})
    assert ac.load_accounts(store) == ["kiosapi"]                       # an unknown gateway and an empty token are not keys
    assert ac.account_headers("kiosapi") == {"Authorization": "Bearer acct-token-typed-1234", "New-Api-User": "77",
                                             "Accept": "application/json"}
    assert ac.account_headers("mireld") is None
    log = []
    account = {"success": True, "data": {"quota": 4408500, "used_quota": 1250000}}        # New-API: quota is what is LEFT
    get = _fake_get({"/api/status": R(200, {"data": {"quota_per_unit": 500000}}), "/api/user/self": R(200, account)}, log)
    bal = ac.check(_gw("kiosapi", "https://kiosapi.com/v1"), now=NOW, get=get)
    c = bal["credit"]
    assert c["source"] == "/api/user/self (account)" and c["unit"] == "USD"
    assert c["remaining"] == 8.817 and c["used"] == 2.5 and c["status"] == "ok"
    sent = [(u, h) for u, h, _r in log if h.get("New-Api-User")]
    assert sent and all(u.startswith("https://kiosapi.com/") for u, _h in sent)           # the token never leaves the gateway
    assert all(h["Authorization"] == "Bearer acct-token-typed-1234" for _u, h in sent)
    # the GitHub secrets, when both are set, still win over what was typed
    monkeypatch.setenv("KIOSAPI_ACCESS_TOKEN", "from-secret")
    monkeypatch.setenv("KIOSAPI_USER_ID", "9")
    assert ac.account_headers("kiosapi")["Authorization"] == "Bearer from-secret"
    # a table that is not there is no typed key, never an error
    monkeypatch.delenv("KIOSAPI_ACCESS_TOKEN")

    class Broken:
        def table(self, name):
            raise RuntimeError("relation does not exist")

    assert ac.load_accounts(Broken()) == [] and ac.account_headers("kiosapi") is None
