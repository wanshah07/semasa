"""Filling empty slots: off unless switched on, rota-true, never two ideas for one slot, drafts only."""

from datetime import UTC, datetime

from fakestore import FakeStore

from semasa import autofill

NOW = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)            # Thu 24 Sep, 10:00 MYT
BRAND = {"regulab": {"slots": ["08:00", "13:00"], "schedule": {"5": ["kosmetik", "sains_kosmetik"], "6": [],
                                                                "0": ["halal_my", "fatwa"]}},
         "linkedin": {"slots": ["06:00"], "days": [1, 3, 5]}}


def _store(watch, ideas=(), posts=()):
    return FakeStore(semasa_watch=list(watch), semasa_ideas=list(ideas), semasa_posts=list(posts), semasa_log=[])


def _w(i, domain, section="regulatory"):
    return {"id": f"w{i}", "section": section, "source": "NPRA", "title": f"Notis {i}", "url": f"https://npra.gov.my/{i}",
            "summary": "s", "domain": domain, "relevant": True, "dismissed": False, "created_at": "2026-09-23T00:00:00+00:00"}


def test_off_by_default_writes_nothing():
    store = _store([_w(1, "kosmetik")])
    assert autofill.run(store, {"brand": BRAND}, NOW).startswith("Autofill: off")
    assert autofill.run(store, {"brand": BRAND, "autofill": {"enabled": "yes"}}, NOW).startswith("Autofill: off")
    assert store.tables["semasa_ideas"] == []


def test_fills_rota_true_positions_from_tomorrow_and_leaves_the_rest_as_gaps():
    store = _store([_w(1, "halal_my"), _w(2, "kosmetik"), _w(3, "farmaseutikal")],
                   posts=[{"id": "p", "stream": "regulab", "status": "draft", "date": "2026-09-25", "slot": "08:00"}])
    out = autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 5,
                                                             "streams": ["regulab"]}}, NOW)
    got = sorted((i["brief"]["position"]["date"], i["brief"]["position"]["slot"], i["domain"], i["source_url"][-1])
                 for i in store.tables["semasa_ideas"])
    # Fri 25: 08:00 taken, 13:00 → the kosmetik item; Sat: no posting; Sun 27: halal item at 08:00, 13:00 has nothing
    assert got == [("2026-09-25", "13:00", "kosmetik", "2"), ("2026-09-27", "08:00", "halal_my", "1")]
    assert "1 gap(s) had no fitting item" in out
    assert all(i["status"] == "new" and i["brief"]["auto"] is True for i in store.tables["semasa_ideas"])


def test_never_two_ideas_for_one_slot_nor_one_item_twice():
    waiting = {"id": "i0", "stream": "regulab", "status": "new", "source_url": "https://npra.gov.my/2",
               "brief": {"position": {"date": "2026-09-25", "slot": "08:00"}}}
    store = _store([_w(2, "kosmetik"), _w(4, "kosmetik")], ideas=[waiting])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 5,
                                                       "streams": ["regulab"]}}, NOW)
    new = [i for i in store.tables["semasa_ideas"] if i["id"] != "i0"]
    assert [(i["brief"]["position"]["slot"], i["source_url"][-1]) for i in new] == [("13:00", "4")]


def test_per_run_cap_and_linkedin_days():
    store = _store([_w(i, "kosmetik", "publication") for i in range(6)])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 7, "per_run": 2,
                                                       "streams": ["linkedin"]}}, NOW)
    ideas = store.tables["semasa_ideas"]
    assert len(ideas) == 2 and all(i["angle"] == "F" and i["domain"] is None for i in ideas)
    assert [i["brief"]["position"]["date"] for i in ideas] == ["2026-09-25", "2026-09-28"]   # Fri, then Mon


def test_a_case_study_fits_any_posting_day():
    store = _store([_w(1, "kajian_kes")])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 1,
                                                       "streams": ["regulab"]}}, NOW)
    assert store.tables["semasa_ideas"][0]["domain"] == "kajian_kes"


def test_an_autofilled_idea_carries_no_note_so_the_published_guard_still_holds():
    store = _store([_w(1, "kosmetik")])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 1,
                                                       "streams": ["regulab"]}}, NOW)
    assert store.tables["semasa_ideas"][0]["note"] == ""
