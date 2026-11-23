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


def test_autofill_opens_by_itself_at_enabled_from():
    s = {"autofill": {"enabled": False, "enabled_from": "2026-10-02T12:00:00Z"}}
    assert autofill.config(s, datetime(2026, 10, 2, 11, 0, tzinfo=UTC))["enabled"] is False
    assert autofill.config(s, datetime(2026, 10, 2, 12, 0, tzinfo=UTC))["enabled"] is True


def test_a_linkedin_slot_set_to_video_is_a_single_card_never_a_film():
    """Wan, 11 Nov 2026: "for linkedn, no need to do motion, only carousel or single card"."""
    brand = {"linkedin": {"slot_formats": {"06:00": "carousel", "19:00": "video"}},
             "regulab": {"slot_formats": {"08:00": "video"}}}
    assert autofill.slot_format(brand, "linkedin", "19:00") == "single"
    assert autofill.slot_format(brand, "linkedin", "06:00") == "carousel"
    assert autofill.slot_format(brand, "regulab", "08:00") == "video", "ws.regulab still has its film slots"


def test_a_linkedin_gap_written_by_autofill_is_an_idea_never_a_motion_film():
    brand = {**BRAND, "linkedin": {"slots": ["06:00"], "days": [0, 1, 2, 3, 4, 5, 6], "slot_formats": {"06:00": "video"}}}
    store = FakeStore(semasa_watch=[_w(1, "kosmetik")], semasa_ideas=[], semasa_posts=[], semasa_log=[], semasa_motions=[])
    cfg = {"enabled": True, "days_ahead": 3, "per_run": 4, "streams": ["linkedin"]}
    autofill.run(store, {"brand": brand, "autofill": cfg}, NOW)
    assert not [m for m in store.tables["semasa_motions"] if m.get("stream") == "linkedin"], "no LinkedIn film is queued"
    assert [i for i in store.tables["semasa_ideas"] if i.get("stream") == "linkedin"], "the slot gets an idea for a post instead"


# --- LinkedIn from official sources, and posters (Wan, 20 Nov 2026) ---------------------------------------

def test_linkedin_takes_only_official_sections_never_a_headline_or_a_social_post():
    for section in ("regulatory", "publication", "website", "folder"):
        assert autofill.fits({"section": section}, "linkedin", None), section
    for section in ("news", "linkedin", "expert", "reddit", "youtube", "threads", "instagram", "facebook", ""):
        assert not autofill.fits({"section": section}, "linkedin", None), section
    assert autofill.fits({"section": "news", "domain": "halal_my"}, "regulab", ["halal_my"])      # ws.regulab is unchanged


def test_a_poster_slot_makes_a_poster_idea_not_a_carousel_or_a_single_card():
    brand = {"linkedin": {"slots": ["06:00", "19:00"], "slot_formats": {"06:00": "carousel", "19:00": "poster"}}}
    assert autofill.slot_format(brand, "linkedin", "19:00") == "poster"
    assert autofill.slot_format(brand, "linkedin", "06:00") == "carousel"
    from semasa import ideas
    assert ideas.format_of({"brief": {"format": "poster"}}) == "poster"


def test_linkedin_takes_an_updated_circular_before_an_existing_guideline_before_research():
    # Wan, 23 Nov 2026: "updated circular/guideline > existing guideline > research"
    def row(i, section, title, summary="s"):
        return {**_w(i, "kosmetik", section), "title": title, "summary": summary,
                "created_at": f"2026-09-23T0{9 - i}:00:00+00:00"}              # the research paper is the newest
    store = _store([row(1, "publication", "A new trial of a cream"),
                    row(2, "website", "Garis panduan sedia ada"),
                    row(3, "regulatory", "Kenyataan tentang kilang"),
                    row(4, "folder", "Nota rujukan"),
                    row(5, "regulatory", "NPRA updates the cosmetic guideline", "Pindaan Garis Panduan Notifikasi")])
    brand = {"linkedin": {"slots": ["06:00", "11:00", "19:00"], "days": [0, 1, 2, 3, 4, 5, 6]}}
    cfg = {"enabled": True, "days_ahead": 2, "per_run": 5, "streams": ["linkedin"]}
    autofill.run(store, {"brand": brand, "autofill": cfg}, NOW)
    got = [i["source_url"][-1] for i in sorted(store.tables["semasa_ideas"], key=lambda i: (
        i["brief"]["position"]["date"], i["brief"]["position"]["slot"]))]
    assert got == ["5", "3", "2", "4", "1"], got
    assert [autofill.linkedin_tier(x) for x in (row(5, "regulatory", "Updated guideline"), row(3, "regulatory", "Kenyataan"),
                                                row(2, "website", "x"), row(4, "folder", "x"),
                                                row(1, "publication", "x"))] == [0, 1, 2, 3, 4]


def test_ws_regulab_keeps_its_own_order_when_linkedin_has_one():
    paper, notice = _w(1, "kosmetik", "publication"), _w(2, "kosmetik", "regulatory")
    ranked = autofill.rank_candidates([paper, notice])
    assert autofill.pick(ranked, "regulab", ["kosmetik"], "2026-09-25") is notice


def test_inside_a_linkedin_tier_the_newest_item_wins_even_when_an_older_one_is_an_announcement():
    # Codex review on #327: an "Updated guideline" notice and a recall are both tier 0 for LinkedIn, and the shared ranking
    # puts the recall first whatever its date
    older = {**_w(1, "kosmetik"), "title": "Recall of a cream", "summary": "s", "created_at": "2026-09-20T00:00:00+00:00"}
    newer = {**_w(2, "kosmetik"), "title": "Updated guideline on labels", "summary": "s",
             "created_at": "2026-09-23T00:00:00+00:00"}
    assert autofill.linkedin_tier(older) == autofill.linkedin_tier(newer) == 0
    ranked = autofill.rank_candidates([older, newer])
    assert ranked[0] is older, "the shared order puts the announcement first"
    assert autofill.pick(ranked, "linkedin", None, "2026-09-25") is newer
