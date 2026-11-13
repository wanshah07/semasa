"""Wan's own Threads app (supabase/080, 13 Nov 2026): public posts by keyword from Meta, the token kept fresh."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import community, threads_api

NOW = datetime(2026, 11, 13, 6, 0, tzinfo=UTC)
CFG = {"threads": {"enabled": True, "queries": ["halal", "kosmetik"], "hours": 72, "max_results": 8}}


class Resp:
    def __init__(self, status=200, body=None, reason="OK"):
        self.status_code, self._body, self.reason = status, body or {}, reason

    def json(self):
        return self._body


class Http:
    """Answers by URL path and records every call."""

    def __init__(self, **by_path):
        self.by_path, self.calls = by_path, []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        for path, resp in self.by_path.items():
            if url.endswith(path):
                return resp(params) if callable(resp) else resp
        return Resp(404, {}, "Not Found")


def _store(expires_in_days=50, username=None, enabled=True):
    return FakeStore(semasa_threads_auth=[{
        "id": "main", "app_id": "123456789", "app_secret": "s" * 32, "access_token": "t" * 60, "enabled": enabled,
        "expires_at": (NOW + timedelta(days=expires_in_days)).isoformat(), "username": username,
        "connected_at": (NOW - timedelta(days=10)).isoformat(), "updated_at": (NOW - timedelta(days=10)).isoformat()}])


def _posts(*rows):
    return Resp(200, {"data": [{"id": i, "text": t, "username": u, "permalink": f"https://www.threads.com/@{u}/post/{i}",
                                "timestamp": "2026-11-13T04:00:00+0000"} for i, t, u in rows]})


def test_no_saved_connection_reads_nothing_and_says_nothing():
    http = Http()
    assert threads_api.fetch(FakeStore(semasa_threads_auth=[]), CFG, NOW, http) == ([], "")
    assert http.calls == []


def test_a_switched_off_connection_is_not_read():
    assert threads_api.load(_store(enabled=False)) is None


def test_public_posts_come_back_in_the_shape_the_sweep_reads_and_the_accounts_own_posts_are_left_out():
    store = _store()
    http = Http(**{"/v1.0/me": Resp(200, {"id": "9", "username": "wan"}),
                   "/v1.0/keyword_search": _posts(("a1", "Halal jadi isu lagi", "ali"), ("a2", "my own post", "wan"),
                                                  ("a1", "Halal jadi isu lagi", "ali"))})
    posts, err = threads_api.fetch(store, CFG, NOW, http)
    assert err == "" and [p["id"] for p in posts] == ["a1"]                       # the duplicate and the own post are dropped
    rows = community.thread_candidates({"threads": posts}, NOW)
    assert rows[0]["platform"] == "threads" and rows[0]["title"] == "Halal jadi isu lagi" and rows[0]["url"].endswith("/post/a1")
    search = [c for c in http.calls if c[0].endswith("keyword_search")][0][1]
    assert search["q"] == "halal" and search["search_type"] == "TOP"
    assert search["since"] == int((NOW - timedelta(hours=72)).timestamp())
    saved = store.tables["semasa_threads_auth"][0]
    assert saved["username"] == "wan" and saved["last_ok_at"] and not saved["last_error"]


def test_a_search_that_returns_only_the_accounts_own_posts_is_reported_as_not_approved_and_makes_no_row():
    store = _store(username="wan")
    http = Http(**{"/v1.0/keyword_search": _posts(("b1", "my first", "wan"), ("b2", "my second", "WAN"))})
    posts, err = threads_api.fetch(store, CFG, NOW, http)
    assert posts == [] and "threads_keyword_search is not approved" in err
    assert "threads_keyword_search" in store.tables["semasa_threads_auth"][0]["last_error"]


def test_a_refused_token_is_reported_without_the_token_in_it():
    store = _store()
    http = Http(**{"/v1.0/me": Resp(400, {"error": {"message": "Invalid OAuth access token", "code": 190}}, "Bad Request")})
    posts, err = threads_api.fetch(store, CFG, NOW, http)
    assert posts == [] and "Invalid OAuth access token" in err and "t" * 20 not in err
    assert store.tables["semasa_threads_auth"][0]["last_error"] == err


def test_a_search_refusal_is_reported_and_stops_the_other_keywords():
    store = _store(username="wan")
    refusal = {"error": {"message": "no permission", "code": 10, "error_subcode": 4279067}}
    http = Http(**{"/v1.0/keyword_search": Resp(403, refusal, "Forbidden")})
    posts, err = threads_api.fetch(store, CFG, NOW, http)
    assert posts == [] and "no permission" in err and len([c for c in http.calls if "keyword_search" in c[0]]) == 1


def test_the_token_is_renewed_in_its_last_two_weeks_and_left_alone_before():
    soon = _store(expires_in_days=10, username="wan")
    http = Http(**{"/refresh_access_token": Resp(200, {"access_token": "n" * 60, "expires_in": 5183944}),
                   "/v1.0/keyword_search": _posts(("c1", "Halal", "ali"))})
    threads_api.fetch(soon, CFG, NOW, http)
    row = soon.tables["semasa_threads_auth"][0]
    assert row["access_token"] == "n" * 60 and row["expires_at"].startswith("2027-01-")
    assert http.calls[0][1]["grant_type"] == "th_refresh_token" and "client_secret" not in http.calls[0][1]
    far = _store(expires_in_days=50, username="wan")
    http2 = Http(**{"/v1.0/keyword_search": _posts(("c1", "Halal", "ali"))})
    threads_api.fetch(far, CFG, NOW, http2)
    assert not [c for c in http2.calls if "refresh_access_token" in c[0]]


def test_a_failed_refresh_keeps_the_old_token_and_still_searches():
    store = _store(expires_in_days=5, username="wan")
    http = Http(**{"/refresh_access_token": Resp(400, {"error": {"message": "too young", "code": 190}}, "Bad Request"),
                   "/v1.0/keyword_search": _posts(("d1", "Halal", "ali"))})
    posts, err = threads_api.fetch(store, CFG, NOW, http)
    assert [p["id"] for p in posts] == ["d1"] and err == ""
    assert store.tables["semasa_threads_auth"][0]["access_token"] == "t" * 60
