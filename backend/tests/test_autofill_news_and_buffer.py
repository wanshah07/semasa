"""Auto-fill (Wan, 9 Nov 2026): current newspaper issues first and tied to the rules; a full Buffer queue pauses new ideas and
every post Buffer already holds is a taken slot."""

from datetime import UTC, datetime, timedelta

from fakestore import FakeStore

from semasa import autofill, buffer_queue, ideas

NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)            # Thu 24 Sep, 10:00 MYT
ROTA = ["kosmetik", "halal_my", "makanan", "farmaseutikal"]
BRAND = {"regulab": {"slots": ["08:00", "13:00", "21:00"], "schedule": {str(d): ROTA for d in range(7)}},
         "linkedin": {"slots": ["06:00"]}}
ON = {"enabled": True, "days_ahead": 2, "per_run": 3, "streams": ["regulab"]}


def _news(i, category, title, hours_ago=3, summary=""):
    at = (NOW - timedelta(hours=hours_ago)).isoformat()
    return {"id": f"n{i}", "title": title, "source": "Berita Harian", "url": f"https://bh.example/{i}", "summary": summary,
            "category": category, "published_at": at, "created_at": at}


def _feed(i, domain="kosmetik"):
    return {"id": f"w{i}", "section": "regulatory", "source": "NPRA", "title": f"Notis {i}", "url": f"https://npra.gov.my/{i}",
            "summary": "s", "domain": domain, "relevant": True, "dismissed": False, "created_at": "2026-09-23T00:00:00+00:00"}


def _store(news=(), feed=(), ideas_=(), posts=()):
    return FakeStore(isu_semasa_trends=list(news), semasa_watch=list(feed), semasa_ideas=list(ideas_), semasa_posts=list(posts),
                     semasa_log=[], semasa_settings=[])


# ---------------------------------------------------------------- newspaper issues first, tied to the rules
def test_a_current_newspaper_issue_that_names_a_regulator_beats_the_regulator_feed():
    store = _store(news=[_news(1, "kosmetik", "NPRA tarik balik krim pemutih mengandungi merkuri", summary="Produk dibatalkan")],
                   feed=[_feed(1)])
    autofill.run(store, {"brand": BRAND, "autofill": {**ON, "per_run": 1}}, NOW)
    first = store.tables["semasa_ideas"][0]
    assert first["source_url"] == "https://bh.example/1" and first["trend_id"] == "n1"
    brief = first["brief"]
    assert brief["relate_regulatory"] is True and brief["news"] is True and brief["hook_required"] is True
    assert brief["story_mode"] is True and "watch_id" not in brief
    assert first["domain"] == "kosmetik" and first["note"] == ""


def test_news_that_names_a_rule_ranks_above_news_that_does_not_and_both_above_the_feed():
    pool = autofill.rank_candidates([
        {**_feed(1), "created_at": NOW.isoformat()},
        {"section": "news", "title": "Harga barang naik", "created_at": NOW.isoformat(), "regulatory_link": False},
        {"section": "news", "title": "JAKIM sahkan sijil halal", "created_at": (NOW - timedelta(hours=9)).isoformat(),
         "regulatory_link": True}], NOW)
    assert [x.get("title") for x in pool] == ["JAKIM sahkan sijil halal", "Harga barang naik", "Notis 1"]


def test_only_regulatory_adjacent_categories_and_fresh_unused_headlines_are_candidates():
    used = {"id": "i0", "stream": "regulab", "status": "drafted", "source_url": "https://bh.example/4", "brief": {}}
    store = _store(news=[_news(1, "politik", "Menteri bertemu"), _news(2, "makanan", "Label makanan wajib ada alergen"),
                         _news(3, "makanan", "Lama", hours_ago=60), _news(4, "halal", "Sijil halal tamat")], ideas_=[used])
    got = autofill.news_candidates(store, NOW)
    assert [x["title"] for x in got] == ["Label makanan wajib ada alergen"]
    assert got[0]["domain"] == "makanan" and got[0]["regulatory_link"] is True        # "label" names an instrument step


def test_no_trends_table_is_no_news_not_a_crash():
    store = FakeStore(semasa_watch=[_feed(1)], semasa_ideas=[], semasa_posts=[], semasa_log=[])
    assert autofill.news_candidates(store, NOW) == []


def test_the_writer_is_told_to_relate_a_news_story_to_the_rule_and_to_tell_it_as_a_story():
    idea = {"stream": "regulab", "source_title": "NPRA tarik balik krim", "source_name": "Berita Harian", "source_summary": "x",
            "brief": {"relate_regulatory": True, "story_mode": True, "hook_required": True}}
    system, user = ideas.build_request(idea, {"ok": False, "why": "no article"}, {})
    assert "RELATE TO THE RULES" in user and "STORY MODE" in user and "HOOK REQUIRED" in user
    plain = ideas.build_request({"stream": "regulab", "source_title": "t", "brief": {}}, {"ok": False}, {})[1]
    assert "RELATE TO THE RULES" not in plain and "STORY MODE" not in plain


def test_the_writer_voice_is_casual_with_a_hook_and_exactly_one_follow_line():
    for stream in ("regulab", "linkedin"):
        idea = {"stream": stream, "source_title": "t", "brief": {}}
        system, _ = ideas.build_request(idea, {"ok": False}, {"linkedin": {"angles": {}}})
        assert "follow" in system.lower() and "casual" in system.lower()
    assert "HOW IT SOUNDS" in ideas.REGULAB_SYSTEM and "FIRST LINE is the hook" in ideas.REGULAB_SYSTEM
    from semasa import compliance
    # the shared rulebook no longer treats a follow invitation as a banned call to action, and still bans the other asks
    follows = ("Follow untuk tip regulatori yang senang faham.", "Follow me for more like this.", "Follow kami untuk tip lagi.")
    for caption in follows:
        flags = compliance.scan({"stream": "regulab", "lang": "bm", "text": {"bm": {"instagram": caption}}})
        assert not [f for f in flags if "follow" in f["msg"].lower()], caption
    for ask in ("Komen di bawah ya.", "Hubungi kami sekarang.", "Share this dengan kawan."):
        flags = compliance.scan({"stream": "regulab", "lang": "bm", "text": {"bm": {"instagram": ask}}})
        assert [f for f in flags if f["hard"] and f["msg"].startswith("CTA")], ask


# ---------------------------------------------------------------- the Buffer queue
def _bp(i, due, status="scheduled"):
    return {"id": f"{i:024x}", "status": status, "dueAt": due.isoformat(), "text": f"t{i}"}


class _Client:
    org = "org1"

    def __init__(self, posts, limit=10):
        self._posts, self.limit = posts, limit

    def _gql(self, query, variables=None):
        return {"account": {"organizations": [{"id": "org1", "limits": {"scheduledPosts": self.limit}}]}}

    def posts(self, ids, start, end):
        return list(self._posts.get(ids[0], []))


SETTINGS = {"brand": BRAND, "autofill": ON,
            "channels": {"buffer": {"organizationId": "org1", "facebook": "fb", "instagram": "ig", "threads": "th"}}}


def _myt(day, hh):
    """A UTC moment for `hh`:00 Malaysia time on 2026-09-`day`."""
    return datetime(2026, 9, day, hh, 0, tzinfo=UTC) - timedelta(hours=8)


def test_every_scheduled_post_buffer_holds_is_a_taken_slot_even_one_semasa_does_not_know(monkeypatch):
    store = _store(feed=[_feed(1), _feed(2)])
    client = _Client({"fb": [_bp(1, _myt(25, 8)), _bp(2, _myt(25, 14), "sent"), _bp(3, _myt(25, 3))],
                      "ig": [_bp(4, _myt(25, 13))], "th": []})
    q = buffer_queue.snapshot(store, SETTINGS, NOW, client)
    # a sent post and a 03:00 one hold no slot
    assert sorted(map(tuple, q["taken"])) == [("2026-09-25", "08:00"), ("2026-09-25", "13:00")]
    assert q["counts"] == {"facebook": 2, "instagram": 1, "threads": 0} and q["is_full"] is False
    # auto-fill then plans around them: Buffer holds 25 Sep 08:00 and 13:00, so neither is given an idea
    real = buffer_queue.snapshot
    monkeypatch.setattr(buffer_queue, "snapshot", lambda st, se, n=None, client=None: real(st, se, n, _Client(
        {"fb": [_bp(1, _myt(25, 8))], "ig": [_bp(4, _myt(25, 13))], "th": []})))
    autofill.run(store, SETTINGS, NOW)
    slots = {(i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"]}
    assert slots and ("2026-09-25", "08:00") not in slots and ("2026-09-25", "13:00") not in slots


def test_a_full_buffer_queue_pauses_new_ideas_says_so_and_resumes_when_there_is_room(monkeypatch):
    store = _store(feed=[_feed(1), _feed(2)])
    full = _Client({"fb": [_bp(i, _myt(26, 8) + timedelta(days=i)) for i in range(10)], "ig": [], "th": []})
    room = _Client({"fb": [_bp(i, _myt(26, 8) + timedelta(days=i)) for i in range(9)], "ig": [], "th": []})
    now = {"c": full}
    real = buffer_queue.snapshot
    monkeypatch.setattr(buffer_queue, "snapshot", lambda st, se, n=None, client=None: real(st, se, n, now["c"]))
    out = autofill.run(store, SETTINGS, NOW)
    assert out.startswith("Autofill: paused") and "facebook" in out and store.tables["semasa_ideas"] == []
    row = next(r for r in store.tables["semasa_settings"] if r["key"] == "buffer_queue")["value"]
    assert row["paused"] is True and row["counts"]["facebook"] == 10 and row["limit"] == 10 and row["since"]
    assert [e["event"] for e in store.tables["semasa_log"]] == ["idea.autofill_paused"]
    # the queue moves: a post went out, so there is room again and ideas resume
    now["c"] = room
    settings2 = {**SETTINGS, "buffer_queue": row}
    out2 = autofill.run(store, settings2, NOW)
    assert out2.startswith("Autofill: ") and "paused" not in out2 and store.tables["semasa_ideas"]
    events = [e["event"] for e in store.tables["semasa_log"]]
    assert events[0] == "idea.autofill_paused" and "idea.autofill_resumed" in events


def test_unknown_is_never_full_and_a_full_queue_does_not_stop_linkedin(monkeypatch):
    store = _store(feed=[_feed(1)])
    assert buffer_queue.snapshot(store, {"brand": BRAND}, NOW) is None                  # no key, no channels: carry on as before
    full = _Client({"fb": [_bp(i, _myt(26, 8) + timedelta(days=i)) for i in range(10)], "ig": [], "th": []})
    real = buffer_queue.snapshot
    monkeypatch.setattr(buffer_queue, "snapshot", lambda st, se, n=None, client=None: real(st, se, n, full))
    out = autofill.run(store, {**SETTINGS, "autofill": {**ON, "streams": ["regulab", "linkedin"]}}, NOW)
    assert "paused" not in out
    assert {i["stream"] for i in store.tables["semasa_ideas"]} == {"linkedin"}         # LinkedIn has no Buffer queue


def test_a_post_at_an_odd_hour_still_counts_toward_the_cap_but_holds_no_slot():
    assert buffer_queue.slot_of(_myt(25, 3), ["08:00", "13:00", "21:00"]) is None
    assert buffer_queue.slot_of(_myt(25, 8) + timedelta(minutes=20), ["08:00", "13:00"]) == ("2026-09-25", "08:00")


# ---------------------------------------------------------------- one idea per story, whatever the link
def test_the_same_story_under_two_links_is_one_idea():
    # 9 Nov 2026: Google News and the paper both carried "Jakim investigating The Weeknd's concerts";
    # two LinkedIn slots got one each
    twice = [_news(1, "halal", "Jakim investigating The Weeknd's concerts - Free Malaysia Today", summary="Jakim"),
             {**_news(2, "halal", "Jakim investigating The Weeknd’s concerts", summary="Jakim"),
              "url": "https://news.google.com/rss/articles/abc"}]
    store = _store(news=twice)
    autofill.run(store, {"brand": BRAND, "autofill": {**ON, "streams": ["linkedin"], "per_run": 2}}, NOW)
    made = store.tables["semasa_ideas"]
    assert len(made) == 1, [m["source_title"] for m in made]
    assert "news.google.com" not in made[0]["source_url"]          # the paper's own link wins: the writer can read it


def test_a_story_already_written_up_under_another_link_is_not_written_again():
    old = {"id": "i0", "source_title": "Jakim investigating The Weeknd's concerts", "source_url": "https://other.example/x",
           "created_at": (NOW - timedelta(days=2)).isoformat()}
    store = _store(news=[_news(1, "halal", "Jakim investigating The Weeknd's concerts - FMT")], ideas_=[old])
    autofill.run(store, {"brand": BRAND, "autofill": {**ON, "streams": ["linkedin"], "per_run": 2}}, NOW)
    assert len(store.tables["semasa_ideas"]) == 1                    # only the old one


def test_story_key_ignores_the_paper_tail_case_and_punctuation():
    assert autofill.story_key("Jakim investigating The Weeknd’s concerts - Free Malaysia Today") == autofill.story_key(
        "JAKIM investigating the Weeknd's concerts")
    assert autofill.story_key("Minyak sapu - NPRA - FMT") == "minyak sapu npra"      # one tail is cut, never the whole
    assert autofill.story_key("") == "" and autofill.story_key(None) == ""
