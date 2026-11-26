"""Apify as Instagram's last resort (Wan, 26 Nov 2026): limits kept from Apify's own numbers, never a run past them, and only a
failed saved login ever calls it."""

from datetime import UTC, datetime, timedelta

import pytest

from semasa import apify_budget, instagram_api, social_web

REAL_FETCH = social_web.fetch                 # captured before conftest stubs it (the sweep must not open a browser)

NOW = datetime(2026, 11, 26, 6, 0, tzinfo=UTC)


class Apify:
    """A fake Apify: the account's usage, the actor's run list, and a record of every run asked for."""

    def __init__(self, used=0.0, cap=10.0, runs=(), code=200, run_code=200, items=None):
        self.used, self.cap, self.runs, self.code, self.run_code = used, cap, list(runs), code, run_code
        self.items = items if items is not None else []
        self.gets, self.posts = [], []

    def get(self, path, tok):
        self.gets.append(path)
        if self.code != 200:
            return self.code, {}
        if path.startswith("/v2/users/me/limits"):
            return 200, {"data": {"current": {"monthlyUsageUsd": self.used}, "limits": {"maxMonthlyUsageUsd": self.cap}}}
        return 200, {"data": {"items": [{"startedAt": r.isoformat().replace("+00:00", "Z")} for r in self.runs]}}

    def post(self, path, tok, body):
        self.posts.append((path, body))
        return self.run_code, self.items


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for k in ("APIFY_TOKEN", "APIFY_MONTHLY_CAP_USD", "APIFY_MONTHLY_RUNS", "APIFY_ITEMS_PER_RUN", "APIFY_MIN_GAP_HOURS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APIFY_TOKEN", "tok")


def item(code="C0JD3tntcmy", caption="A caption long enough to be an argument", at="2026-11-26T01:00:00.000Z", **kw):
    return {"id": "1_2", "code": code, "url": f"https://www.instagram.com/p/{code}/", "createdAt": at, "likeCount": 114,
            "commentCount": 5, "caption": caption, "owner": {"username": "labmuffinbeautyscience"}, "isVideo": False, **kw}


def test_the_limits_default_to_the_free_plans_and_an_environment_variable_raises_them(monkeypatch):
    assert apify_budget.limits() == {"cap_usd": 5.0, "runs": 5, "items": 10, "gap_hours": 24}
    monkeypatch.setenv("APIFY_MONTHLY_RUNS", "30")
    monkeypatch.setenv("APIFY_ITEMS_PER_RUN", "100")
    monkeypatch.setenv("APIFY_MONTHLY_CAP_USD", "20")
    monkeypatch.setenv("APIFY_MIN_GAP_HOURS", "")             # an unset repository variable arrives empty
    assert apify_budget.limits() == {"cap_usd": 20.0, "runs": 30, "items": 100, "gap_hours": 24}
    monkeypatch.setenv("APIFY_MONTHLY_RUNS", "many")
    assert apify_budget.limits()["runs"] == 5


def test_a_run_is_allowed_with_room_and_costs_posts_times_the_price():
    ok, why, info = apify_budget.check(None, NOW, Apify(used=0.5).get)
    assert ok and why == "" and info["cost_usd"] == 0.005 and info["items"] == 10 and info["runs"] == 0


def test_no_token_refuses_without_asking_apify(monkeypatch):
    monkeypatch.delenv("APIFY_TOKEN")
    fake = Apify()
    ok, why, _ = apify_budget.check(None, NOW, fake.get)
    assert not ok and "APIFY_TOKEN" in why and fake.gets == []


@pytest.mark.parametrize("fake, words", [
    (Apify(runs=[NOW - timedelta(days=d) for d in (3, 5, 7, 9, 11)]), "5 of 5 runs"),
    (Apify(used=4.999), "used of $5.00"),
    (Apify(used=0.0, cap=0.001), "account's own"),
    (Apify(runs=[NOW - timedelta(hours=5)]), "minimum 24 h"),
    (Apify(code=500), "could not be asked"),
])
def test_a_spent_month_a_recent_run_or_an_unreadable_account_refuses(fake, words):
    ok, why, _ = apify_budget.check(None, NOW, fake.get)
    assert not ok and words in why


def test_runs_of_last_month_do_not_count_against_this_month():
    old = [datetime(2026, 10, d, 1, 0, tzinfo=UTC) for d in (20, 21, 22, 23, 24)]
    ok, _, info = apify_budget.check(None, NOW, Apify(runs=old).get)
    assert ok and info["runs"] == 0


def test_a_post_row_matches_the_shape_every_other_reader_returns():
    row = instagram_api.post_row(item(video={"playCount": 3321}))
    assert row["id"] == "C0JD3tntcmy" and row["username"] == "labmuffinbeautyscience"
    assert row["permalink"] == "https://www.instagram.com/p/C0JD3tntcmy/" and row["timestamp"].startswith("2026-11-26T01:00")
    assert row["counts"] == {"likes": 114, "comments": 5, "plays": 3321} and row["shown"] == {"likes": "114", "comments": "5"}
    assert social_web.score(row) == 5 + 114 // 10
    assert instagram_api.post_row(item(caption="too short")) is None
    assert instagram_api.post_row(item(code="")) is None and instagram_api.post_row(item(at="not a date")) is None


def test_fetch_makes_no_run_when_the_budget_refuses():
    fake = Apify(used=5.0)
    rows, note = instagram_api.fetch(["https://www.instagram.com/x/"], NOW, fake.get, fake.post)
    assert rows == [] and note.startswith("not run") and fake.posts == []


def test_fetch_asks_for_the_free_plans_ten_posts_with_a_hard_charge_ceiling_and_maps_them():
    fake = Apify(items=[item(), item(code="C2", at="2026-11-25T01:00:00.000Z"), {"junk": True}])
    rows, note = instagram_api.fetch(["https://www.instagram.com/x/"], NOW, fake.get, fake.post)
    [(path, body)] = fake.posts
    assert body == {"startUrls": ["https://www.instagram.com/x/"], "resultsLimit": 10, "maxItems": 10}
    assert "apidojo~instagram-scraper/run-sync-get-dataset-items" in path and "maxTotalChargeUsd=0.01" in path
    assert [r["id"] for r in rows] == ["C0JD3tntcmy", "C2"] and "3 item(s)" in note


def test_fetch_reports_a_refused_run_and_never_raises():
    fake = Apify(run_code=402)
    rows, note = instagram_api.fetch(["https://www.instagram.com/x/"], NOW, fake.get, fake.post)
    assert rows == [] and "HTTP 402" in note
    rows, note = instagram_api.fetch([], NOW, Apify().get, Apify().post)
    assert rows == [] and "no account" in note


def test_apify_urls_rotate_through_the_watched_accounts_and_fall_back_to_a_hashtag():
    cfg = {"instagram": {"accounts": ["@a", "b", "c"], "queries": ["#halal"]}}
    assert social_web.apify_urls(cfg, runs=0) == ["https://www.instagram.com/a/"]
    assert social_web.apify_urls(cfg, runs=1) == ["https://www.instagram.com/b/"]
    assert social_web.apify_urls(cfg, runs=3) == ["https://www.instagram.com/a/"]
    assert social_web.apify_urls(cfg, runs=1, per_run=2) == ["https://www.instagram.com/b/", "https://www.instagram.com/c/"]
    assert social_web.apify_urls({"instagram": {"queries": ["#halal"]}}) == ["https://www.instagram.com/explore/tags/halal/"]
    assert social_web.apify_urls({}) == []


def _wire(monkeypatch, fake, browser):
    monkeypatch.setattr(social_web, "_fetch_browser", lambda platform, cfg, now: browser)
    monkeypatch.setattr(apify_budget, "http_get", fake.get)
    monkeypatch.setattr(instagram_api, "http_post", fake.post)


CFG = {"instagram": {"accounts": ["labmuffinbeautyscience"], "hours": 72}}


@pytest.mark.parametrize("err", ["Instagram needs a saved login (the secret PW_STORAGE_STATE_B64); it shows a login wall",
                                 "Instagram asked for a login (save one as the secret PW_STORAGE_STATE_IG_B64)",
                                 "no browser to read Instagram with (Error: x)", "Playwright is not installed"])
def test_a_failed_saved_login_falls_back_to_apify(monkeypatch, err):
    fake = Apify(items=[item(), item(code="C2", at="2026-11-10T01:00:00.000Z")])
    _wire(monkeypatch, fake, ([], err))
    posts, error = REAL_FETCH("instagram", CFG, NOW)
    assert error == "" and [p["id"] for p in posts] == ["C0JD3tntcmy"]            # the 16-day-old post is outside the 72 h window
    assert len(fake.posts) == 1 and social_web.LAST["instagram"]["too_old"] == 1
    assert social_web.LAST["instagram"]["notes"][0].startswith("via Apify")


@pytest.mark.parametrize("browser", [([], ""), ([], "TimeoutError: page took too long"), ([{"id": "x"}], "")])
def test_an_empty_result_a_timeout_or_a_good_read_never_calls_apify(monkeypatch, browser):
    fake = Apify(items=[item()])
    _wire(monkeypatch, fake, browser)
    assert REAL_FETCH("instagram", CFG, NOW) == browser
    assert fake.posts == [] and fake.gets == []


def test_facebook_never_falls_back(monkeypatch):
    fake = Apify(items=[item()])
    _wire(monkeypatch, fake, ([], "Facebook asked for a login"))
    assert REAL_FETCH("facebook", CFG, NOW) == ([], "Facebook asked for a login")
    assert fake.posts == []


def test_a_refused_fallback_keeps_the_browsers_error_and_adds_why(monkeypatch):
    fake = Apify(used=5.0)
    _wire(monkeypatch, fake, ([], "Instagram asked for a login (save one ...)"))
    posts, error = REAL_FETCH("instagram", CFG, NOW)
    assert posts == [] and error.startswith("Instagram asked for a login") and "Apify fallback: not run" in error
    assert fake.posts == []


def test_no_token_or_the_switch_off_says_so_and_asks_nothing(monkeypatch):
    fake = Apify(items=[item()])
    _wire(monkeypatch, fake, ([], "Playwright is not installed"))
    monkeypatch.delenv("APIFY_TOKEN")
    assert "not set up" in REAL_FETCH("instagram", CFG, NOW)[1]
    monkeypatch.setenv("APIFY_TOKEN", "tok")
    off = {"instagram": {**CFG["instagram"], "apify": False}}
    assert "switched off" in REAL_FETCH("instagram", off, NOW)[1]
    assert fake.posts == [] and fake.gets == []


def test_main_prints_the_state_and_no_secret(monkeypatch, capsys):
    fake = Apify(used=0.2, runs=[NOW - timedelta(days=2)])
    monkeypatch.setattr(apify_budget, "http_get", fake.get)
    monkeypatch.setenv("APIFY_TOKEN", "super-secret-token-value")
    assert apify_budget.main() == 0
    out = capsys.readouterr().out
    assert "super-secret-token-value" not in out and "WOULD be allowed" in out and "1 run(s)" in out
    monkeypatch.delenv("APIFY_TOKEN")
    assert apify_budget.main() == 1
