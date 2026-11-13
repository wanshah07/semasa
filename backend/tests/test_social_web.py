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
