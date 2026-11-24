"""Facebook and Instagram read in a browser (13 Nov 2026): the page's own numbers, a login wall named and never a row."""

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest

from semasa import community, social_web

NOW = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)
REAL_FETCH = social_web.fetch                 # captured before conftest stubs it, so its no-login answer can be tested


def test_a_keyword_becomes_a_hashtag():
    assert social_web.hashtag("halal malaysia") == "halalmalaysia"
    assert social_web.hashtag("#SijilHalal") == "sijilhalal"
    assert social_web.hashtag("  ") == "" and social_web.hashtag(None) == ""


def test_facebook_time_is_the_printed_date_read_in_utc_else_the_short_label():
    text = "Adi is in Johor Bahru · 3 days ago Tuesday, November 10, 2026 at 1:25 AM 3d · TEGUR"
    assert social_web._fb_time(text, "3d", NOW) == datetime(2026, 11, 10, 1, 25, tzinfo=UTC)
    assert social_web._fb_time("no date here", "5h", NOW) == NOW - timedelta(hours=5)
    assert social_web._fb_time("no date here", "just now", NOW) is None


def test_facebook_links_keep_the_post_id_and_drop_the_tracking():
    link, pid = social_web._fb_link("https://www.facebook.com/agc7296/posts/pfbid0dUiv?__cft__[0]=AZ&__tn__=%2CO")
    assert link == "https://www.facebook.com/agc7296/posts/pfbid0dUiv" and pid == "pfbid0dUiv"
    link, pid = social_web._fb_link("https://www.facebook.com/groups/166/?multi_permalinks=4956712967929417&hoisted=1")
    assert link == "https://www.facebook.com/groups/166/?multi_permalinks=4956712967929417" and pid == "4956712967929417"
    assert social_web._fb_link("https://example.com/x") is None


def _fb(message="TEGUR MAMAK, ORANG BUKAN MAMAK PULA YANG MEROYAN!… See more", reactions="All reactions: 42 99", when="3d"):
    return {"href": "https://www.facebook.com/agc7296/posts/pfbid0dUiv?__cft__[0]=AZ", "when": when, "message": message,
            "text": f"Adi Nurrafie · 3 days ago Tuesday, November 10, 2026 at 1:25 AM 3d · {message} {reactions} Like Comment"}


def test_a_facebook_post_keeps_its_words_without_see_more_and_only_the_reaction_count_the_page_labelled():
    p = social_web.facebook_post(_fb(), NOW)
    assert p["text"] == "TEGUR MAMAK, ORANG BUKAN MAMAK PULA YANG MEROYAN!" and p["id"] == "pfbid0dUiv"
    assert p["shown"] == {"reactions": "42"} and p["counts"] == {"reactions": 42}           # the unlabelled "99" is not claimed
    assert p["timestamp"] == "2026-11-10T01:25:00+00:00"
    assert social_web.metrics_text(p) == "42 reactions"


def test_a_facebook_post_with_no_words_no_time_or_no_link_is_dropped():
    assert social_web.facebook_post(_fb(message="Hi"), NOW) is None
    assert social_web.facebook_post({**_fb(), "text": "x", "when": "yesterday"}, NOW) is None
    assert social_web.facebook_post({**_fb(), "href": ""}, NOW) is None


def test_an_instagram_description_gives_the_user_the_date_the_caption_and_the_counts_shown():
    desc = '1,234 likes, 56 comments - ali.halal on November 12, 2026: "Sijil halal bukan sekadar logo, ini semakan sebenar."'
    p = social_web.parse_instagram(desc, "", "/p/Cabc-123/")
    assert p["id"] == "Cabc-123" and p["username"] == "ali.halal" and p["permalink"] == "https://www.instagram.com/p/Cabc-123/"
    assert p["timestamp"] == "2026-11-12T00:00:00+00:00" and p["counts"] == {"likes": 1234, "comments": 56}
    assert social_web.metrics_text(p) == "1,234 likes · 56 comments"
    assert social_web.score(p) == 56 + 123


def test_an_instagram_description_without_counts_still_reads_and_a_login_walls_does_not():
    caption = 'ali on Instagram: "Sunscreen tak perlu disapu semula?"'
    p = social_web.parse_instagram(caption, "2026-11-12T08:00:00.000Z", "/reel/Xyz9/")
    assert p["shown"] == {} and p["counts"] == {"likes": None} and p["timestamp"] == "2026-11-12T08:00:00+00:00"
    assert social_web.parse_instagram("Log into Instagram", "", "/p/Q/") is None
    short = 'ali on Instagram: "Hi"'
    assert social_web.parse_instagram(short, "2026-11-12T08:00:00Z", "/p/Q/") is None       # too short to be an argument


def test_collect_reads_each_hashtag_once_keeps_72_hours_and_ranks_by_the_numbers():
    def post(pid, hours_ago, reactions):
        when = (NOW - timedelta(hours=hours_ago)).isoformat()
        return {"id": pid, "text": f"post {pid} " * 3, "permalink": f"https://www.facebook.com/p/{pid}", "timestamp": when,
                "counts": {"reactions": reactions}, "shown": {"reactions": str(reactions)}}
    pages = {"halalmalaysia": [post("a", 5, 10), post("b", 6, 900)], "sijilhalal": [post("b", 6, 900), post("c", 100, 5000)]}
    seen = []

    def read(page, tag, now):
        seen.append(tag)
        return pages.get(tag, []), ""
    cfg = {"facebook": {"hours": 72, "queries": ["halal malaysia", "#SijilHalal", "sijil halal", ""]}}
    posts, err = social_web.collect(object(), "facebook", cfg, NOW, read)
    assert err == "" and [p["id"] for p in posts] == ["b", "a"]                     # c is older than 72 h, b is not counted twice
    assert seen == ["halalmalaysia", "sijilhalal"]                                  # a repeated hashtag is read once


def test_a_post_from_wans_own_page_or_account_is_never_a_viral_post():
    def post(pid, url, user=""):
        return {"id": pid, "text": f"post {pid} " * 3, "permalink": url, "timestamp": NOW.isoformat(), "username": user,
                "counts": {"reactions": 5}, "shown": {"reactions": "5"}}
    pages = {"halal": [post("own", "https://www.facebook.com/wsregulab/posts/pfbid1"),
                       post("ig", "https://www.instagram.com/p/Z/", "WS.Regulab"),
                       post("other", "https://www.facebook.com/someoneelse/posts/pfbid2")]}
    cfg = {"facebook": {"queries": ["halal"]}, "own_accounts": ["wsregulab", "@ws.regulab"]}
    posts, _ = social_web.collect(object(), "facebook", cfg, NOW, lambda page, tag, now: (pages[tag], ""))
    assert [p["id"] for p in posts] == ["other"]


def test_collect_names_a_login_wall_and_stops_instagram_at_the_first_one():
    seen = []

    def wall(page, tag, now):
        seen.append(tag)
        return [], "Instagram asked for a login (save one as the secret PW_STORAGE_STATE_B64)"
    cfg = {"instagram": {"queries": ["halal", "kosmetik", "skincare"]}}
    posts, err = social_web.collect(object(), "instagram", cfg, NOW, wall)
    assert posts == [] and "asked for a login" in err and seen == ["halal"]


def test_instagram_without_a_saved_login_says_so_and_never_opens_a_browser(monkeypatch):
    monkeypatch.delenv("PW_STORAGE_STATE_B64", raising=False)
    posts, err = REAL_FETCH("instagram", {"instagram": {"queries": ["halal"]}}, NOW)
    assert posts == [] and "PW_STORAGE_STATE_B64" in err


def test_a_saved_login_is_read_from_the_secret_and_a_wrong_one_is_ignored(monkeypatch):
    good = base64.b64encode(json.dumps({"cookies": [{"name": "sessionid"}], "origins": []}).encode()).decode()
    monkeypatch.setenv("PW_STORAGE_STATE_B64", good)
    path = social_web.storage_state_path()
    assert path and json.load(open(path))["cookies"][0]["name"] == "sessionid"
    monkeypatch.setenv("PW_STORAGE_STATE_B64", base64.b64encode(b"not a session").decode())
    assert social_web.storage_state_path() is None
    monkeypatch.delenv("PW_STORAGE_STATE_B64")
    assert social_web.storage_state_path() is None


def test_an_instagram_secret_is_merged_over_the_base_login_and_touches_nothing_else(monkeypatch):
    # Wan, 24 Nov 2026: "add instagram live without kacau other platforms"
    def secret(cookies):
        return base64.b64encode(json.dumps({"cookies": cookies, "origins": []}).encode()).decode()
    fb = {"name": "c_user", "domain": ".facebook.com", "value": "f"}
    old_ig = {"name": "sessionid", "domain": ".instagram.com", "value": "old"}
    new_ig = {"name": "sessionid", "domain": ".instagram.com", "value": "new"}
    junk = {"name": "x", "domain": ".example.com", "value": "j"}
    monkeypatch.setenv("PW_STORAGE_STATE_B64", secret([fb, old_ig]))
    monkeypatch.setenv("PW_STORAGE_STATE_IG_B64", secret([new_ig, junk]))
    merged = json.load(open(social_web.storage_state_path()))["cookies"]
    assert {(c["domain"], c["value"]) for c in merged} == {(".facebook.com", "f"), (".instagram.com", "new")}, merged
    # Instagram alone: no base secret at all
    monkeypatch.delenv("PW_STORAGE_STATE_B64")
    assert [c["value"] for c in json.load(open(social_web.storage_state_path()))["cookies"]] == ["new"]
    # a broken or Instagram-less second secret changes nothing
    monkeypatch.setenv("PW_STORAGE_STATE_B64", secret([fb, old_ig]))
    monkeypatch.setenv("PW_STORAGE_STATE_IG_B64", base64.b64encode(b"not a session").decode())
    assert {c["value"] for c in json.load(open(social_web.storage_state_path()))["cookies"]} == {"f", "old"}
    monkeypatch.setenv("PW_STORAGE_STATE_IG_B64", secret([junk]))
    assert {c["value"] for c in json.load(open(social_web.storage_state_path()))["cookies"]} == {"f", "old"}


def test_malformed_cookie_entries_are_dropped_and_never_fail_the_sweep(monkeypatch):
    # Codex review on #342: a null in the cookies list of the optional secret raised before the protected browser block
    def secret(cookies):
        return base64.b64encode(json.dumps({"cookies": cookies, "origins": []}).encode()).decode()
    good = {"name": "sessionid", "domain": ".instagram.com", "value": "v"}
    monkeypatch.setenv("PW_STORAGE_STATE_IG_B64", secret([None, "x", 5, good]))
    monkeypatch.setenv("PW_STORAGE_STATE_B64", secret([None, {"name": "c_user", "domain": ".facebook.com", "value": "f"}]))
    assert {c["value"] for c in json.load(open(social_web.storage_state_path()))["cookies"]} == {"v", "f"}
    monkeypatch.setenv("PW_STORAGE_STATE_IG_B64", secret([None, "x"]))              # nothing usable left: ignored
    assert {c["value"] for c in json.load(open(social_web.storage_state_path()))["cookies"]} == {"f"}


def test_the_login_diagnostic_prints_counts_and_cookie_names_never_a_value(monkeypatch, caplog):
    # Wan, 24 Nov 2026: "diagnostic": tell a login wall from a login that never arrived, without exposing the login
    def secret(cookies):
        return base64.b64encode(json.dumps({"cookies": cookies, "origins": []}).encode()).decode()
    soon = 4_000_000_000
    ig = [{"name": "sessionid", "domain": ".instagram.com", "value": "TOPSECRETVALUE", "expires": soon},
          {"name": "csrftoken", "domain": ".instagram.com", "value": "ANOTHERSECRET", "expires": soon}]
    fb = {"name": "c_user", "domain": ".facebook.com", "value": "FBSECRET"}
    monkeypatch.setenv("PW_STORAGE_STATE_B64", secret([fb]))
    monkeypatch.setenv("PW_STORAGE_STATE_IG_B64", secret(ig))
    with caplog.at_level("INFO", logger="semasa.social_web"):
        social_web.storage_state_path()
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "base secret: 1 cookie(s), 0 instagram, 1 facebook" in text and "instagram secret: 2 instagram cookie(s)" in text
    assert "sessionid present" in text and "csrftoken present" in text and "ds_user_id absent" in text, text
    assert "TOPSECRETVALUE" not in text and "ANOTHERSECRET" not in text and "FBSECRET" not in text, "no value is ever logged"
    # without the second secret the line says so
    monkeypatch.delenv("PW_STORAGE_STATE_IG_B64")
    caplog.clear()
    with caplog.at_level("INFO", logger="semasa.social_web"):
        social_web.storage_state_path()
    assert "instagram secret: absent" in " ".join(r.getMessage() for r in caplog.records)


def test_social_posts_feed_the_tabs_with_their_own_platform_and_counts():
    fb = social_web.facebook_post(_fb(), NOW)
    ig = social_web.parse_instagram('1.2K likes, 80 comments - ali on November 12, 2026: "Sunscreen tak perlu disapu semula?"',
                                    "", "/p/Zz1/")
    raw = {"facebook": [fb], "instagram": [ig]}
    f = community.facebook_candidates(raw, datetime(2026, 11, 10, 20, 0, tzinfo=UTC))
    i = community.instagram_candidates(raw, NOW)
    assert f[0]["platform"] == "facebook" and f[0]["source"] == "Facebook" and f[0]["metrics"] == "42 reactions"
    assert i[0]["platform"] == "instagram" and i[0]["metrics"] == "1.2K likes · 80 comments" and i[0]["url"].endswith("/p/Zz1/")
    assert community.to_row({**f[0], "summary": "s"})["section"] == "facebook"


# --- the extractor against a page shaped like Facebook's hashtag page (measured 13 Nov 2026), in a real Chromium ------------

_PAGE = """<html><body>
<div role="article"><span>Adi Nurrafie AGc</span><span>is in Johor Bahru, Malaysia.</span>
 <a href="https://www.facebook.com/agc7296/posts/pfbid0dUiv?__cft__[0]=AZ" aria-label="3d">3d</a>
 <span>Tuesday, November 10, 2026 at 1:25 AM</span>
 <div data-ad-preview="message"><div dir="auto">TEGUR MAMAK, ORANG BUKAN MAMAK PULA YANG MEROYAN!… See more</div></div>
 <div><div>All reactions: 42</div><div>99</div><div>Like</div><div>Comment</div></div></div>
<div role="article"><div aria-label="Loading..."></div></div>
</body></html>"""


def test_the_facebook_extractor_reads_words_link_time_and_reactions_and_skips_a_loading_placeholder():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.set_content(_PAGE)
            rows = page.evaluate(social_web._FB_EXTRACT)
            browser.close()
    except Exception as exc:  # noqa: BLE001 - no browser in this environment
        pytest.skip(f"no Chromium here: {str(exc)[:80]}")
    assert len(rows) == 1                                                           # the "Loading..." article has no link
    post = social_web.facebook_post(rows[0], NOW)
    assert post["text"] == "TEGUR MAMAK, ORANG BUKAN MAMAK PULA YANG MEROYAN!" and post["shown"] == {"reactions": "42"}
    assert post["permalink"] == "https://www.facebook.com/agc7296/posts/pfbid0dUiv"


def test_a_hashtag_page_shows_old_top_posts_so_facebook_and_instagram_keep_two_weeks_and_say_what_they_saw():
    from semasa import intake
    assert intake.DEFAULTS["community"]["instagram"]["hours"] == intake.DEFAULTS["community"]["facebook"]["hours"] == 14 * 24
    assert intake.KEEP_HOURS["instagram"] == intake.KEEP_HOURS["facebook"] == 14 * 24 and intake.KEEP_HOURS["threads"] == 72

    def post(pid, hours_ago):
        return {"id": pid, "text": f"post {pid} " * 3, "permalink": f"https://www.instagram.com/p/{pid}/", "username": "x",
                "timestamp": (NOW - timedelta(hours=hours_ago)).isoformat(), "counts": {"likes": 5}, "shown": {"likes": "5"}}

    def read(page, tag, now):
        social_web._NOTES.append(f"#{tag}: 2 post link(s), 2 read at /explore/tags/{tag}/ \"Instagram\"")
        return [post("a", 100), post("b", 200)], ""
    short = {"instagram": {"hours": 72, "queries": ["halal"]}}
    posts, err = social_web.collect(object(), "instagram", short, NOW, read)
    assert posts == [] and err == ""                                              # two posts read, both older than 72 h
    line = social_web.stats_text("instagram")
    assert "found 2 post(s)" in line and "2 older than 72 h" in line and "newest 100 h old" in line and "#halal" in line
    wide = {"instagram": {"hours": 14 * 24, "queries": ["halal"]}}
    posts, _ = social_web.collect(object(), "instagram", wide, NOW, read)
    assert [p["id"] for p in posts] == ["a", "b"] and "older than" not in social_web.stats_text("instagram")


def test_the_page_note_names_the_address_and_title_and_never_fails_a_read():
    class Page:
        url = "https://www.facebook.com/hashtag/halal?__cft__=x"

        def title(self):
            return "Facebook"
    assert social_web._where(Page()) == '/hashtag/halal?__cft__=x "Facebook"'
    assert social_web._where(object()) == "?"            # a page with no title() is "?", not an error


def test_watched_accounts_are_read_after_the_hashtags_and_their_new_posts_are_kept():
    def post(pid, hours_ago):
        return {"id": pid, "text": f"post {pid} " * 3, "permalink": f"https://www.instagram.com/p/{pid}/", "username": "npra.kkm",
                "timestamp": (NOW - timedelta(hours=hours_ago)).isoformat(), "counts": {"likes": 9}, "shown": {"likes": "9"}}
    seen = []

    def tag(page, name, now):
        seen.append(("tag", name))
        return [post("old", 5000)], ""

    def account(page, name, now):
        seen.append(("account", name))
        return [post("fresh", 5)], ""
    cfg = {"instagram": {"hours": 14 * 24, "queries": ["halal malaysia"], "accounts": ["@npra.kkm", "bad handle!", "npra.kkm"]}}
    posts, err = social_web.collect(object(), "instagram", cfg, NOW, tag, account)
    assert [p["id"] for p in posts] == ["fresh"] and err == ""                    # the old top post is dropped, the new one kept
    assert seen == [("tag", "halalmalaysia"), ("account", "npra.kkm")]            # a malformed or repeated handle is never opened
    assert "1 older than 336 h" in social_web.stats_text("instagram") and social_web.LAST["instagram"]["accounts"] == 1
    only = {"facebook": {"queries": [], "accounts": ["KementerianKesihatanMalaysia"]}}
    posts, _ = social_web.collect(object(), "facebook", only, NOW, tag, account)
    assert [p["id"] for p in posts] == ["fresh"]                                  # accounts alone are enough to read
    assert social_web.collect(object(), "facebook", {"facebook": {"queries": [], "accounts": []}}, NOW) == ([], "")


def test_facebook_searches_the_words_as_posts_when_its_hashtag_page_shows_no_post():
    class Page:
        url = "https://www.facebook.com/hashtag/halal"
        visited = []

        def goto(self, url, **kw):
            self.visited.append(url)
            self.url = url

        def wait_for_timeout(self, ms):
            pass

        def title(self):
            return "(4) Facebook"

        class mouse:                       # noqa: N801 - a stand-in for page.mouse
            @staticmethod
            def wheel(x, y):
                pass

        def evaluate(self, js):
            return [] if "/hashtag/" in self.url else [_fb()]
    page = Page()
    got, err = social_web.read_facebook(page, "halal", NOW)
    assert err == "" and len(got) == 1
    assert page.visited[-1].startswith("https://www.facebook.com/search/posts/?q=halal")
    assert "searched instead: 1 block(s)" in social_web._NOTES[-1]


# --- the post as the content (Expert content, 15 Nov 2026): whole, with its paragraphs, not the feed's 500 characters ---------

_CUT = """<html><body>
<div role="article">
  <a href="https://www.facebook.com/halalguru/posts/pfbidWHOLE" aria-label="2d">2d</a>
  <div data-ad-preview="message"><div id="m">Perenggan satu tentang MPPHM.</div>
    <div role="button" id="more"
      onclick="document.getElementById('m').innerText='Perenggan satu tentang MPPHM.\\n\\nPerenggan dua dengan klausa 40(2).';
               this.remove()">See more</div></div>
  <span>All reactions: 12</span>
</div></body></html>"""


def test_an_expert_facebook_post_is_opened_past_see_more_and_keeps_its_paragraphs():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.set_content(_CUT)
            cut = social_web._fb_rows(page, scrolls=0)
            page.set_content(_CUT)
            whole = social_web._fb_rows(page, scrolls=0, expand=True)
            browser.close()
    except Exception as exc:  # noqa: BLE001 - no browser in this environment
        pytest.skip(f"no Chromium here: {str(exc)[:80]}")
    assert social_web.facebook_post(cut[0], NOW)["text"] == "Perenggan satu tentang MPPHM.", "the feed's reader is unchanged"
    full = social_web.facebook_post(whole[0], NOW, cap=4000, keep_lines=True)
    assert full["text"] == "Perenggan satu tentang MPPHM.\n\nPerenggan dua dengan klausa 40(2)."


def test_the_pages_own_labels_at_the_end_of_a_message_are_dropped_and_the_cap_is_the_callers():
    long = "Ayat panjang. " * 200
    p = social_web.facebook_post(_fb(message=long + "… See more See translation"), NOW, cap=4000)
    assert p["text"].endswith("Ayat panjang.") and 2700 < len(p["text"]) <= 4000
    assert len(social_web.facebook_post(_fb(message=long), NOW)["text"]) == 500
    desc = '12 likes, 3 comments - dr.aiman on November 12, 2026: "' + "Kapsyen panjang. " * 100 + '"'
    assert len(social_web.parse_instagram(desc, "2026-11-12T10:00:00.000Z", "/p/ABC/")["text"]) == 500
    assert len(social_web.parse_instagram(desc, "2026-11-12T10:00:00.000Z", "/p/ABC/", cap=4000)["text"]) > 1500


# --- a logged-in Facebook shows no post on a hashtag page (16 Nov 2026) ---------------------------------------------------------

def _fake_playwright(monkeypatch):
    """A stand-in for playwright.sync_api that records how each context was opened."""
    import sys
    import types

    opened: list[dict] = []

    class Page:
        def __init__(self, opts):
            self.opts = opts

    class Context:
        def __init__(self, opts):
            self.opts = opts

        def new_page(self):
            return Page(self.opts)

    class Browser:
        def new_context(self, **opts):
            opened.append(opts)
            return Context(opts)

        def close(self):
            pass

    class PW:
        class chromium:                                  # noqa: N801 - mirrors the real attribute
            @staticmethod
            def launch():
                return Browser()

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    mod = types.ModuleType("playwright.sync_api")
    mod.sync_playwright = lambda: PW()
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", mod)
    return opened


def test_facebook_hashtags_are_read_without_the_login_and_only_accounts_with_it(monkeypatch):
    opened = _fake_playwright(monkeypatch)
    monkeypatch.setattr(social_web, "storage_state_path", lambda: "/nonexistent/state.json")
    seen = {}

    def fake_collect(page, platform, cfg, now, read=None, read_account=None, account_page=None):
        seen.update(page=page, account_page=account_page)
        return [], ""

    monkeypatch.setattr(social_web, "collect", fake_collect)
    REAL_FETCH("facebook", {"facebook": {"queries": ["halal"], "accounts": ["x"]}}, NOW)
    assert len(opened) == 2
    assert "storage_state" not in seen["page"].opts, "the hashtag page is anonymous"
    assert seen["account_page"].opts["storage_state"] == "/nonexistent/state.json", "accounts keep the login"


def test_instagram_still_reads_everything_with_the_login(monkeypatch):
    opened = _fake_playwright(monkeypatch)
    monkeypatch.setattr(social_web, "storage_state_path", lambda: "/nonexistent/state.json")
    seen = {}

    def fake_collect(page, platform, cfg, now, read=None, read_account=None, account_page=None):
        seen.update(page=page, account_page=account_page)
        return [], ""

    monkeypatch.setattr(social_web, "collect", fake_collect)
    REAL_FETCH("instagram", {"instagram": {"queries": ["halal"]}}, NOW)
    assert len(opened) == 1
    assert seen["page"].opts["storage_state"] == "/nonexistent/state.json" and seen["account_page"] is None


def test_facebook_without_any_saved_login_still_reads_one_anonymous_page(monkeypatch):
    opened = _fake_playwright(monkeypatch)
    monkeypatch.setattr(social_web, "storage_state_path", lambda: None)
    seen = {}

    def fake_collect(page, platform, cfg, now, read=None, read_account=None, account_page=None):
        seen.update(page=page, account_page=account_page)
        return [], ""

    monkeypatch.setattr(social_web, "collect", fake_collect)
    REAL_FETCH("facebook", {"facebook": {"queries": ["halal"]}}, NOW)
    assert len(opened) == 1 and "storage_state" not in seen["page"].opts and seen["account_page"] is None


def test_collect_reads_accounts_with_the_account_page_and_hashtags_with_the_other():
    hashtag_page, account_page = object(), object()
    used = []

    def tag(page, name, now):
        used.append(("tag", page))
        return [], ""

    def account(page, name, now):
        used.append(("account", page))
        return [], ""

    cfg = {"facebook": {"queries": ["halal"], "accounts": ["someone"]}}
    social_web.collect(hashtag_page, "facebook", cfg, NOW, tag, account, account_page=account_page)
    assert used == [("tag", hashtag_page), ("account", account_page)]
