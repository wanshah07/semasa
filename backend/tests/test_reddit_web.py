"""Reddit read with Wan's own saved login (semasa.reddit_web, 24 Nov 2026): the secret is read like the Instagram one, the
search is the cell's own, the answer comes back in the cell's shape, and anything that is not Reddit's list is reported in its
own words."""

import base64
import gzip
import json
from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import community, intake, reddit_web

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)


def _secret(cookies, gz=False):
    raw = json.dumps({"cookies": cookies, "origins": []}).encode()
    return base64.b64encode(gzip.compress(raw) if gz else raw).decode()


def _cookie(name, domain=".reddit.com", value="v", expires=None):
    return {"name": name, "domain": domain, "value": value, "path": "/",
            "expires": NOW.timestamp() + 86400 * 30 if expires is None else expires}


LISTING = {"kind": "Listing", "data": {"children": [
    {"kind": "t3", "data": {"id": "a1", "title": "Sunscreen SPF50 cukup sekali sehari?", "score": 55, "num_comments": 260,
                            "permalink": "/r/malaysia/comments/a1/x/", "created_utc": 1795500000, "subreddit": "malaysia",
                            "selftext": "Ramai kata cukup."}},
    {"kind": "t3", "data": {"id": "a2", "title": "No link here"}},                       # no permalink: dropped
    {"kind": "t3", "data": {"id": "a3", "title": "Halal logo", "permalink": "https://www.reddit.com/r/malaysia/comments/a3/y/",
                            "created_utc": "not a number"}}]}}


class Page:
    def __init__(self, body, status=200):
        self.body, self.status, self.urls = body, status, []

    def goto(self, url, wait_until=None, timeout=None):
        self.urls.append(url)
        return type("R", (), {"status": self.status})()

    def evaluate(self, js):
        return self.body


def test_the_secret_is_read_plain_or_gzipped_and_only_reddit_cookies_with_a_login_count(monkeypatch):
    monkeypatch.delenv(reddit_web.SECRET, raising=False)
    assert reddit_web.saved_login() == (None, "absent") and reddit_web.configured() is False
    monkeypatch.setenv(reddit_web.SECRET, "not base64 json")
    assert reddit_web.saved_login() == (None, "unreadable")
    monkeypatch.setenv(reddit_web.SECRET, _secret([_cookie("sessionid", ".instagram.com"), _cookie("csv")]))
    assert reddit_web.saved_login() == (None, "no reddit login")                       # cookies, but nobody is logged in
    monkeypatch.setenv(reddit_web.SECRET, _secret([_cookie("reddit_session"), _cookie("sessionid", ".instagram.com")], gz=True))
    state, how = reddit_web.saved_login()
    assert how == "gzip" and [c["name"] for c in state["cookies"]] == ["reddit_session"]   # another site's cookie is left out
    assert reddit_web.configured() is True


def test_the_log_line_names_cookies_and_days_and_never_a_value(monkeypatch):
    monkeypatch.setenv(reddit_web.SECRET, _secret([_cookie("reddit_session", value="SECRETVALUE"), _cookie("loid")]))
    state, how = reddit_web.saved_login()
    line = reddit_web.describe(state, how, NOW)
    assert "2 reddit cookie(s)" in line and "reddit_session present, 30.0 day(s) left" in line and "token_v2 missing" in line
    assert "SECRETVALUE" not in line
    assert reddit_web.describe(None, "absent") == "reddit login: not used (absent)"


def test_the_search_is_the_cells_own_and_the_answer_is_in_the_cells_shape():
    url = reddit_web.search_url("malaysia", ["halal", "kosmetik"], "week", 15)
    assert url.startswith("https://www.reddit.com/r/malaysia/search.json?")
    assert "restrict_sr=1" in url and "sort=top" in url and "t=week" in url and "%28halal+OR+kosmetik%29" in url
    posts, err = reddit_web.parse(json.dumps(LISTING))
    assert err == "" and [p["id"] for p in posts] == ["a1", "a3"]
    first = posts[0]
    assert first["permalink"] == "https://www.reddit.com/r/malaysia/comments/a1/x/" and first["num_comments"] == 260
    assert first["created"].startswith("2026-") and first["text"] == "Ramai kata cukup." and posts[1]["created"] is None
    rows = community.candidates({"posts": posts}, datetime.fromtimestamp(1795500000, UTC), 72)
    assert rows and rows[0]["platform"] == "reddit" and rows[0]["metrics"] == "260 komen"       # the sweep reads it as before


def test_what_is_not_reddits_list_is_reported_in_its_own_words():
    assert "whoa there, pardner" in reddit_web.parse("whoa there, pardner! Your request has been blocked")[1]
    assert reddit_web.parse("")[1].endswith("(an empty page)")
    assert reddit_web.parse(json.dumps({"error": 403, "message": "Forbidden"}))[1] == "Reddit answered 403: Forbidden"
    posts, err = reddit_web.read(Page("blocked", status=403), "https://x")
    assert posts == [] and err.startswith("Reddit answered HTTP 403 to the saved login")
    assert reddit_web.parse(json.dumps({"data": {"children": []}})) == ([], "")              # an empty week is not an error


def test_fetch_uses_the_login_only_when_one_is_saved(monkeypatch):
    monkeypatch.delenv(reddit_web.SECRET, raising=False)
    def never(state):
        raise AssertionError("no browser without a login")

    assert reddit_web.fetch({}, NOW, opener=never) == ([], "")
    monkeypatch.setenv(reddit_web.SECRET, "junk")
    got, why = reddit_web.fetch({}, NOW, opener=lambda s: None)
    assert got == [] and "not used (unreadable)" in why                                    # a broken secret is said, never silent
    monkeypatch.setenv(reddit_web.SECRET, _secret([_cookie("reddit_session")]))
    page = Page(json.dumps(LISTING))
    seen = {}

    def opener(state):
        seen["cookies"] = [c["name"] for c in state["cookies"]]
        return page

    got, why = reddit_web.fetch({"subreddit": "malaysia", "terms": ["halal"], "window": "day", "limit": 99}, NOW, opener=opener)
    assert why == "" and len(got) == 2 and seen["cookies"] == ["reddit_session"]
    assert "t=day" in page.urls[0] and "limit=25" in page.urls[0]                           # the limit is capped


# ---- the sweep: own login first, the shared app only when it gave nothing ------------------------------------------------------

class Client:
    def __init__(self, out):
        self.out, self.params = out, None

    def cell(self, body, params, **kw):
        self.params = params
        return dict(self.out)


class NoLLM:
    def ask(self, *a, **k):
        return None

    def ask_json(self, *a, **k):
        return None


def _run(monkeypatch, own, shared):
    monkeypatch.setattr(reddit_web, "fetch", lambda cfg, now: own)
    monkeypatch.setattr(community, "annotate", lambda llm, batch: ([], []))
    client = Client({"posts": shared[0], "videos": [], "threads": [{"id": "t"}], "reddit_error": shared[1], "youtube_error": "",
                     "threads_error": ""})
    cfg = {"threads": {"enabled": False}, "facebook": {"enabled": False}, "instagram": {"enabled": False}}
    rep = intake.do_community(FakeStore(), NoLLM(), client, cfg, NOW, True)
    return rep, client


def test_with_its_own_login_the_sweep_does_not_ask_the_shared_reddit_app(monkeypatch):
    posts, _ = reddit_web.parse(json.dumps(LISTING))
    rep, client = _run(monkeypatch, (posts, ""), ([], "rate limit (429)"))
    assert client.params["reddit"] is False                                                 # the shared app is left alone
    assert rep["read"]["reddit"] == 2 and rep["reddit_error"] is None and rep["reddit_via"] == "login"


def test_a_failed_login_read_is_named_and_the_shared_app_is_still_asked(monkeypatch):
    rep, client = _run(monkeypatch, ([], "Reddit answered HTTP 403 to the saved login (blocked)"), ([], "rate limit (429)"))
    assert client.params["reddit"] is True
    assert rep["reddit_error"].startswith("own login: Reddit answered HTTP 403")
    assert "shared app: rate limit (429)" in rep["reddit_error"]
    rep, client = _run(monkeypatch, ([], ""), ([{"id": "s1", "title": "x", "permalink": "https://r/x"}], ""))
    assert client.params["reddit"] is True and rep["reddit_via"] == "shared app" and rep["reddit_error"] is None   # no login
