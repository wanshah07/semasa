"""Threads read in a plain browser, no login (13 Nov 2026): the page's own counts, no number the page did not show."""

from datetime import UTC, datetime, timedelta

import pytest

from semasa import community, threads_web

NOW = datetime(2026, 11, 13, 8, 0, tzinfo=UTC)


def _stamp(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _raw(user, pid, body, hours_ago=5, **counts):
    return {"href": f"/@{user}/post/{pid}", "datetime": _stamp(hours_ago), "body": body,
            "counts": {"Like": counts.get("likes", ""), "Comment": counts.get("replies", ""),
                       "Repost": counts.get("reposts", ""), "Share": counts.get("shares", "")}}


def test_counts_are_read_the_way_threads_abbreviates_them_and_a_blank_is_not_a_number():
    assert threads_web.parse_count("158") == 158
    assert threads_web.parse_count("1.3K") == 1300
    assert threads_web.parse_count("9K") == 9000
    assert threads_web.parse_count("2.1M") == 2_100_000
    assert threads_web.parse_count("1,204") == 1204
    assert threads_web.parse_count("") is None and threads_web.parse_count(None) is None
    assert threads_web.parse_count("Like") is None


def test_a_post_keeps_the_numbers_shown_and_leaves_the_rest_unclaimed():
    p = threads_web._post(_raw("ali", "AbC-1", ["Halal jadi isu lagi", "Sijil mana satu?"], likes="9K", replies="280"))
    assert p["permalink"] == "https://www.threads.com/@ali/post/AbC-1" and p["username"] == "ali"
    assert p["text"] == "Halal jadi isu lagi\nSijil mana satu?"
    assert p["counts"] == {"likes": 9000, "replies": 280, "reposts": None, "shares": None}      # no repost count was shown
    assert threads_web.metrics_text(p) == "9K likes · 280 replies" and "repost" not in threads_web.metrics_text(p)


def test_a_quote_posts_trailing_author_name_is_not_part_of_its_words():
    p = threads_web._post(_raw("nur", "Q1", ["Halal itu flex", "ducku.ramen"]))
    assert p["text"] == "Halal itu flex"
    one_word = threads_web._post(_raw("nur", "Q2", ["Halal"]))
    assert one_word["text"] == "Halal"                                  # a lone word is the post, not a name


def test_a_post_with_no_words_or_a_odd_address_is_dropped():
    assert threads_web._post(_raw("ali", "Z1", [])) is None
    assert threads_web._post({"href": "/explore", "body": ["x"], "counts": {}}) is None


def test_the_loudest_argument_ranks_first_replies_before_likes():
    quiet = threads_web._post(_raw("a", "P1", ["tenang"], likes="900"))
    loud = threads_web._post(_raw("b", "P2", ["bising"], likes="50", replies="300", reposts="20"))
    assert threads_web.score(loud) > threads_web.score(quiet)


def test_collect_keeps_the_last_72_hours_once_each_loudest_first_and_reads_each_keyword_and_handle():
    pages = {
        "https://www.threads.com/search?q=halal%20kosmetik&serp_type=default": [
            threads_web._post(_raw("a", "P1", ["kecil"], likes="10")),
            threads_web._post(_raw("b", "P2", ["besar"], replies="200")),
            threads_web._post(_raw("c", "P3", ["lama"], hours_ago=100, replies="999"))],       # older than 72 h
        "https://www.threads.com/@wan.ridzuan": [threads_web._post(_raw("b", "P2", ["besar"], replies="200")),    # a duplicate
                                                  threads_web._post(_raw("wan.ridzuan", "P4", ["wan"], replies="5"))]}
    seen = []

    def read(page, url):
        seen.append(url)
        return pages.get(url, []), ""

    cfg = {"threads": {"hours": 72, "queries": ["halal kosmetik"], "accounts": ["@wan.ridzuan", "bad handle!"]}}
    posts, err = threads_web.collect(object(), cfg, NOW, read)
    assert err == "" and [p["id"] for p in posts] == ["P2", "P4", "P1"]
    assert len(seen) == 2 and seen[1].endswith("/@wan.ridzuan")                    # the malformed handle is never opened


def test_a_login_wall_on_every_page_is_reported_by_name_and_makes_no_post():
    posts, err = threads_web.collect(object(), {"threads": {"queries": ["halal"]}}, NOW,
                                     lambda page, url: ([], "Threads asked for a login"))
    assert posts == [] and err == "Threads asked for a login"


def test_one_failed_page_does_not_hide_the_posts_the_others_returned():
    ok = [threads_web._post(_raw("a", "P1", ["ok"], replies="3"))]

    def read(page, url):
        return ([], "TimeoutError: slow") if "sunscreen" in url else (ok, "")

    posts, err = threads_web.collect(object(), {"threads": {"queries": ["sunscreen", "halal"]}}, NOW, read)
    assert err == "" and [p["id"] for p in posts] == ["P1"]


def test_eight_keywords_and_ten_accounts_are_read_and_no_more():
    seen = []
    cfg = {"threads": {"queries": [f"kata {i}" for i in range(12)], "accounts": [f"akaun{i}" for i in range(15)]}}
    threads_web.collect(object(), cfg, NOW, lambda page, url: (seen.append(url), ([], ""))[1])
    assert len([u for u in seen if "/search?" in u]) == 8 and len([u for u in seen if "/@" in u]) == 10


def test_nothing_to_read_is_not_an_error():
    assert threads_web.collect(object(), {"threads": {"queries": [], "accounts": []}}, NOW) == ([], "")
    assert threads_web.fetch({"threads": {"web": False}}, NOW) == ([], "")


def test_a_page_read_post_feeds_the_feed_with_the_platforms_own_numbers_and_ranks_by_them():
    quiet = threads_web._post(_raw("a", "P1", ["Halal kecil"], likes="10"))
    loud = threads_web._post(_raw("b", "P2", ["Halal besar"], replies="280", likes="9K"))
    rows = community.thread_candidates({"threads": [quiet, loud]}, NOW)
    assert [r["title"] for r in rows] == ["Halal besar", "Halal kecil"]
    assert rows[0]["metrics"] == "9K likes · 280 replies" and rows[0]["url"].endswith("/@b/post/P2")
    # Composio's posts carry no counts: rank position, no metrics line, as before
    composio = community.thread_candidates({"threads": [{"id": "1", "text": "Satu", "permalink": "https://x/1",
                                                          "timestamp": _stamp(3)}]}, NOW)
    assert composio[0]["metrics"] is None and composio[0]["weight"] == 100


# --- the extractor against a page shaped like Threads' (measured 13 Nov 2026), in a real Chromium -----------------------

_PAGE = """<html><body>
<div id="feed">
 <div class="post"><span dir="auto"><a href="/@nurzarinazee">nurzarinazee</a></span><span dir="auto">Halal</span>
  <span dir="auto"><a href="/@nurzarinazee/post/Dfo4W"><time datetime="2026-11-12T10:49:57.000Z">20h</time></a></span>
  <span dir="auto">In Malaysia, getting Halal-certified is a flex.</span><span dir="auto">Dah lah, JAKIM is a challenge.</span>
  <div class="quoted"><a href="/@ducku.ramen/post/Dfolg"><span dir="auto">ducku.ramen</span></a></div>
  <div role="button"><svg><title>Like</title></svg><span>9K</span></div>
  <div role="button"><svg><title>Comment</title></svg><span>280</span></div>
  <div role="button"><svg><title>Repost</title></svg><span>1K</span></div>
  <div role="button"><svg><title>Share</title></svg><span>158</span></div>
 </div>
</div></body></html>"""


def test_the_extractor_reads_the_words_the_time_and_the_four_counts_from_a_threads_shaped_page():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        with sync_api.sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page()
            page.set_content(_PAGE)
            rows = page.evaluate(threads_web._EXTRACT)
            browser.close()
    except Exception as exc:  # noqa: BLE001 - no browser in this environment
        pytest.skip(f"no Chromium here: {str(exc)[:80]}")
    assert len(rows) == 1                                      # the quoted copy has no <time> of its own: skipped
    post = threads_web._post(rows[0])
    assert post["username"] == "nurzarinazee" and post["timestamp"] == "2026-11-12T10:49:57.000Z"
    assert post["text"] == "In Malaysia, getting Halal-certified is a flex.\nDah lah, JAKIM is a challenge."
    assert post["shown"] == {"likes": "9K", "replies": "280", "reposts": "1K", "shares": "158"}
    assert post["counts"]["likes"] == 9000
