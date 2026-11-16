"""Wan's own websites and LinkedIn posts as sources for LinkedIn ideas (own_links.py). Pages are read from fixtures and from
made-up LinkedIn markup in the shape LinkedIn gives a visitor who is not signed in (measured 16 Nov 2026); nothing here
touches the network."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fakestore import FakeStore

from semasa import intake, own_links

FIX = Path(__file__).parent / "fixtures" / "own_links"
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
LOM = "https://lom.agc.gov.my/index.php"


class Writer:
    """A writer that calls an item relevant only when its title carries one of `words`."""
    configured = True

    def __init__(self, *words):
        self.words, self.asked = words, 0

    def chat_json(self, system, user, max_tokens=0):
        self.asked += 1
        items = [json.loads(line) for line in user.splitlines()[1:]]
        return {"items": [{"i": it["i"], "relevant": any(w in it["title"].upper() for w in self.words), "domain": "halal_my",
                           "summary": f"Ringkasan: {it['title'][:40]}", "why": "Sebab."} for it in items]}


def _store(**kw):
    return FakeStore(semasa_watch=[], semasa_settings=[], semasa_log=[], **kw)


def _ld(*posts):
    return '<html><head><script type="application/ld+json">' + json.dumps(
        posts[0] if len(posts) == 1 else {"@context": "http://schema.org", "@graph": list(posts)}) + "</script></head></html>"


def _post(slug, text, likes, when="2026-11-10T08:00:00.000Z", author="Contoh Sdn Bhd", comments=None, page=False):
    base = {"@type": "SocialMediaPosting", "datePublished": when, "headline": text.splitlines()[0],
            "author": {"@type": "Organization", "name": author}}
    url = f"https://www.linkedin.com/posts/{slug}"
    if page:   # a company page lists its posts with `text`, `url` and one counter
        return {**base, "text": text, "url": url + "?trk=x",
                "interactionStatistic": {"@type": "InteractionCounter", "interactionType": "http://schema.org/LikeAction",
                                         "userInteractionCount": str(likes)}}
    return {**base, "@id": url, "articleBody": text, "commentCount": str(comments or 0),
            "interactionStatistic": [{"@type": "InteractionCounter", "interactionType": "http://schema.org/LikeAction",
                                      "userInteractionCount": likes}]}


# --- websites ---------------------------------------------------------------------------------------------------------

def test_a_listing_page_gives_its_headlines_once_and_no_menu_links():
    name, links = own_links.site_links((FIX / "lom.html").read_text(encoding="utf-8"), LOM)
    titles = [k["title"] for k in links]
    assert name == "Malaysia Federal Legislation"
    assert any(t.startswith("P.U. (A) 392/2026 - TRADE DESCRIPTIONS (CERTIFICATION AND MARKING OF HALAL)") for t in titles)
    # the page lists that order a second time without its number: the same item, kept once
    assert sum("TRADE DESCRIPTIONS (CERTIFICATION AND MARKING OF HALAL)" in t for t in titles) == 1
    assert all(20 <= len(t) <= 300 for t in titles) and len({k["url"] for k in links}) == len(links)
    assert all(k["url"].startswith("https://lom.agc.gov.my/") for k in links)


def test_only_http_addresses_are_read():
    assert own_links.web_url("https://Example.com/a#top") == "https://example.com/a"
    assert [own_links.web_url(x) for x in ("javascript:void(0)", "mailto:a@b.c", "lom")] == ["", "", ""]


def test_a_new_site_shows_a_few_links_then_only_what_is_new_and_never_the_same_one_twice():
    html = (FIX / "lom.html").read_text(encoding="utf-8")
    store, llm = _store(), Writer("HALAL")
    cfg = {"sites": [LOM, LOM, "not a link"], "max_new": 4}
    first = own_links.do_websites(store, llm, None, cfg, NOW, False, get=lambda url: html)
    rows = store.tables["semasa_watch"]
    assert first["sites"] == 1 and first["new"] == 4 == len(rows) and first["read"][LOM] > 10
    assert {r["section"] for r in rows} == {"website"} and {r["source"] for r in rows} == {"Malaysia Federal Legislation"}
    assert all(r["summary"].startswith("Ringkasan:") and r["summary_source"] == "llm" for r in rows)
    seen = next(r["value"] for r in store.tables["semasa_settings"] if r["key"] == own_links.SEEN_KEY)
    assert len(seen[LOM]) == first["read"][LOM], "every link the page showed is remembered, not only the four put in the feed"
    # the same page again: nothing new, and the writer is not asked
    asked = llm.asked
    again = own_links.do_websites(store, llm, None, cfg, NOW, False, get=lambda url: html)
    assert again["new"] == 0 and len(store.tables["semasa_watch"]) == 4 and llm.asked == asked
    # the feed is pruned and the page gains one order: only that one is new
    store.tables["semasa_watch"].clear()
    link = '<a href="act-view.php?id=999">P.U. (A) 400/2026 - FOOD (AMENDMENT) REGULATIONS 2026</a>'
    more = html.replace("<body", f"<body><main>{link}</main><x", 1)
    third = own_links.do_websites(store, llm, None, cfg, NOW, False, get=lambda url: more)
    assert third["new"] == 1 and store.tables["semasa_watch"][0]["title"].startswith("P.U. (A) 400/2026")


def test_an_item_the_writer_calls_irrelevant_is_kept_hidden_and_a_dead_site_does_not_stop_the_others():
    html = (FIX / "lom.html").read_text(encoding="utf-8")
    store = _store()

    def get(url):
        if "dead" in url:
            raise OSError("no answer")
        return html
    rep = own_links.do_websites(store, Writer("HALAL"), None, {"sites": ["https://dead.example/", LOM], "max_new": 20},
                                NOW, False, get=get)
    rows = store.tables["semasa_watch"]
    assert rep["sites"] == 2 and "https://dead.example/" in rep["errors"] and rep["new"] == len(rows) > 5
    shown = [r for r in rows if r["relevant"]]
    assert rep["shown"] == len(shown) >= 1 and all("HALAL" in r["title"] for r in shown)


def test_a_dry_run_writes_nothing():
    store = _store()
    rep = own_links.do_websites(store, None, None, {"sites": [LOM]}, NOW, True,
                                get=lambda url: (FIX / "lom.html").read_text(encoding="utf-8"))
    assert rep["new"] > 0 and not store.tables["semasa_watch"] and not store.tables["semasa_settings"]


# --- LinkedIn ---------------------------------------------------------------------------------------------------------

def test_what_kind_of_linkedin_address_it_is():
    kind = own_links.linkedin_kind
    assert kind("https://www.linkedin.com/posts/contoh_halal-activity-7506241313038831617-EKDA/?utm_source=share") == (
        "post", "https://www.linkedin.com/posts/contoh_halal-activity-7506241313038831617-EKDA")
    assert kind("https://my.linkedin.com/company/contoh-sdn-bhd/posts/?feedView=all") == (
        "page", "https://www.linkedin.com/company/contoh-sdn-bhd/")
    assert kind("https://www.linkedin.com/in/seseorang/")[0] == "profile"
    assert kind("https://www.linkedin.com/feed/update/urn:li:activity:7506241313038831617/")[0] == "post"
    assert kind("https://example.com/posts/x") == ("", "") and kind("https://notlinkedin.com/company/x") == ("", "")


def test_a_pasted_post_is_read_with_its_numbers_and_always_shown():
    url = "https://www.linkedin.com/posts/contoh_repack-activity-1-AbCd"
    page = _ld(_post("contoh_repack-activity-1-AbCd", "Produk tiada sijil halal, tetapi bukan produk haram.\nBoleh repack?", 182,
                     comments=6, author="Puan Contoh"))
    store = _store()
    rep = own_links.do_linkedin(store, Writer("TIADA-PADANAN"), None, {"posts": [url + "/?utm_source=share"], "pages": []},
                                NOW, False, get=lambda u: page)
    (row,) = store.tables["semasa_watch"]
    assert rep == {"posts": 1, "pages": 0, "read": {}, "new": 1, "shown": 1}
    assert row["section"] == "linkedin" and row["url"] == url and row["source"] == "LinkedIn · Puan Contoh"
    assert row["relevant"] is True, "Wan pasted it himself: shown whatever the writer made of it"
    assert row["raw"]["metrics"] == "182 reactions · 6 comments" and row["raw"]["pasted"] is True
    assert row["raw"]["original"].startswith("Produk tiada sijil halal") and row["published_at"] == "2026-11-10"
    # the feed is pruned later: the pasted link is still in the list, and it is not put in the feed a second time
    store.tables["semasa_watch"].clear()
    again = own_links.do_linkedin(store, None, None, {"posts": [url]}, NOW, False, get=lambda u: pytest.fail("read again"))
    assert again["new"] == 0 and not store.tables["semasa_watch"]


def test_a_watched_page_gives_only_its_recent_loud_posts_loudest_first():
    page = "https://www.linkedin.com/company/contoh-sdn-bhd/"
    html = _ld(_post("contoh_quiet-activity-2", "Hari keluarga syarikat.", 12, page=True),
               _post("contoh_loud-activity-3", "NPRA batalkan 12 notifikasi kosmetik.", 480, page=True),
               _post("contoh_old-activity-4", "Kes lama.", 900, when="2026-08-01T00:00:00.000Z", page=True),
               _post("contoh_mid-activity-5", "Garis panduan halal baharu.", 75, page=True),
               {"@type": "Organization", "name": "Contoh Sdn Bhd"})
    store = _store()
    rep = own_links.do_linkedin(store, None, None, {"pages": [page + "posts/", "https://www.linkedin.com/in/seseorang/"],
                                                    "min_reactions": 50, "days": 30}, NOW, False, browse=lambda u: html)
    rows = store.tables["semasa_watch"]
    assert [r["url"].rsplit("/", 1)[1] for r in rows] == ["contoh_loud-activity-3", "contoh_mid-activity-5"]
    assert rep["read"] == {page: 4} and rep["new"] == 2 and rep["profiles_skipped"] == 1
    assert rows[0]["raw"]["metrics"] == "480 reactions" and "pasted" not in rows[0]["raw"]


def test_a_page_linkedin_will_not_show_is_reported_and_nothing_is_made_up():
    store = _store()
    rep = own_links.do_linkedin(store, None, None, {"posts": ["https://www.linkedin.com/posts/x_y-activity-9"],
                                                    "pages": ["https://www.linkedin.com/company/tutup/"]}, NOW, False,
                                get=lambda u: "<html><title>Sign Up | LinkedIn</title></html>",
                                browse=lambda u: "<html><title>Sign Up | LinkedIn</title></html>")
    assert not store.tables["semasa_watch"] and rep["new"] == 0 and len(rep["errors"]) == 2
    assert all("not signed in" in e for e in rep["errors"].values())


# --- in the sweep -----------------------------------------------------------------------------------------------------

def test_both_are_parts_of_the_own_sources_sweep_with_empty_lists_by_default():
    names = [n for n, _ in intake.PARTS]
    assert names[-2:] == ["websites", "linkedin"]
    assert intake.DEFAULTS["websites"]["sites"] == [] and intake.DEFAULTS["linkedin"]["posts"] == []
    assert intake.KEEP_HOURS["website"] == intake.KEEP_HOURS["linkedin"] == 45 * 24
    store = _store()
    rep = intake.run(store, None, None, now=NOW, only=["websites", "linkedin"])
    assert rep["websites"]["ok"] and rep["websites"]["sites"] == 0 and rep["linkedin"]["ok"] and rep["linkedin"]["posts"] == 0


def test_the_migration_adds_both_sections_and_keeps_every_older_one():
    root = Path(__file__).resolve().parents[2] / "supabase"
    new = (root / "083_linkedin_sources.sql").read_text(encoding="utf-8")
    old = (root / "082_expert_content.sql").read_text(encoding="utf-8")
    import re
    sections = lambda sql: set(re.findall(r"'([a-z]+)'", sql.split("check (section in (", 1)[1].split("));", 1)[0]))  # noqa: E731
    assert sections(new) == sections(old) | {"website", "linkedin"}
