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


def test_linkedin_prefers_halal_then_cosmetic_then_pharma_then_research_whatever_the_tier():
    # Wan, 23 Nov 2026: "for linkedn, add more about halal>cosmetic>pharma>research"
    def row(i, domain, section, title="Kenyataan", created="2026-09-20T00:00:00+00:00"):
        return {**_w(i, domain, section), "title": title, "summary": "s", "created_at": created}
    halal_site = row(1, "halal_my", "website", "Garis panduan sedia ada")           # tier 2, but halal
    cosmetic_new = row(2, "kosmetik", "regulatory", "Updated guideline", "2026-09-23T00:00:00+00:00")   # tier 0
    pharma = row(3, "farmaseutikal", "regulatory", "Updated circular", "2026-09-23T00:00:00+00:00")
    paper = row(4, "sains_kosmetik", "publication", "A trial", "2026-09-23T00:00:00+00:00")
    food = row(5, "makanan", "regulatory", "Updated circular", "2026-09-23T00:00:00+00:00")
    assert [autofill.linkedin_subject(x) for x in (halal_site, cosmetic_new, pharma, paper, food)] == [0, 1, 2, 3, 4]
    pool = [food, paper, pharma, cosmetic_new, halal_site]
    order = []
    while pool:
        got = autofill.pick(autofill.rank_candidates(pool), "linkedin", None, "2026-09-25")
        order.append(got["id"])
        pool.remove(got)
    assert order == [halal_site["id"], cosmetic_new["id"], pharma["id"], paper["id"], food["id"]], order
    assert [autofill.linkedin_angle(x) for x in (halal_site, cosmetic_new, paper)] == ["B", "A", "F"]


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


def test_a_slot_with_no_format_is_a_carousel_and_only_a_single_slot_is_one_card():
    got = [autofill.auto_format(f) for f in ("", "carousel", "single", "poster", "video")]
    assert got == ["carousel", "carousel", "poster", "poster", "video"]


# ---- the floor of waiting drafts (Wan, 25 Nov 2026) -------------------------------------------------------------------------
def _full_friday():
    """Approved posts on every ws.regulab and LinkedIn position of Fri 25 Sep: the gap pass (days_ahead 1) has nothing to do."""
    return [{"id": f"f{n}", "stream": s, "status": "approved", "date": "2026-09-25", "slot": slot}
            for n, (s, slot) in enumerate([("regulab", "08:00"), ("regulab", "13:00"), ("linkedin", "06:00")])]


def _floor_settings(**over):
    return {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 1, "per_run": 5, "streams": ["regulab"], **over}}


def test_floor_config_defaults_and_clamps():
    assert autofill.config({"autofill": {"enabled": True}})["min_drafts"] == 2
    assert autofill.config({"autofill": {"enabled": True}})["floor_days"] == 14
    cfg = autofill.config({"autofill": {"enabled": True, "min_drafts": 0, "days_ahead": 5, "floor_days": 2}})
    assert cfg["min_drafts"] == 0 and cfg["floor_days"] == 5            # off; never fewer days than the gap pass looks
    assert autofill.config({"autofill": {"enabled": True, "min_drafts": 99, "floor_days": 99}})["min_drafts"] == 10
    assert autofill.config({"autofill": {"enabled": True, "min_drafts": 99, "floor_days": 99}})["floor_days"] == 30
    assert autofill.config({"autofill": {"enabled": True, "min_drafts": "x"}})["min_drafts"] == 2


def test_floor_writes_two_ideas_for_positions_beyond_the_gap_window():
    store = _store([_w(1, "halal_my"), _w(2, "fatwa"), _w(3, "halal_my")], posts=_full_friday())
    out = autofill.run(store, _floor_settings(), NOW)
    got = sorted((i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"])
    assert got == [("2026-09-27", "08:00"), ("2026-09-27", "13:00")]        # the next free positions, rota-true (Sunday: halal)
    assert "floor: 2 idea(s) so 2 drafts are waiting" in out
    assert all(i["status"] == "new" and i["brief"]["auto"] is True for i in store.tables["semasa_ideas"])
    assert [p["status"] for p in store.tables["semasa_posts"]] == ["approved"] * 3      # nothing approved, nothing scheduled


def test_floor_counts_drafts_and_open_ideas_already_waiting():
    draft = {"id": "d", "stream": "regulab", "status": "draft", "date": "2026-09-30", "slot": "08:00"}
    idea = {"id": "i", "stream": "linkedin", "status": "working", "source_url": "https://x/1",
            "brief": {"position": {"date": "2026-10-01", "slot": "06:00"}}}
    store = _store([_w(1, "halal_my")], ideas=[idea], posts=_full_friday() + [draft])
    out = autofill.run(store, _floor_settings(streams=["regulab", "linkedin"]), NOW)
    assert [i["id"] for i in store.tables["semasa_ideas"]] == ["i"] and "floor" not in out        # 1 draft + 1 idea = 2


def test_floor_does_not_count_a_past_dated_draft_or_an_approved_one():
    old = {"id": "d", "stream": "regulab", "status": "draft", "date": "2026-09-20", "slot": "08:00"}
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday() + [old])
    autofill.run(store, _floor_settings(), NOW)
    assert len(store.tables["semasa_ideas"]) == 2


def test_floor_tops_up_only_the_shortfall():
    draft = {"id": "d", "stream": "regulab", "status": "draft", "date": "2026-09-30", "slot": "08:00"}
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday() + [draft])
    autofill.run(store, _floor_settings(), NOW)
    assert len(store.tables["semasa_ideas"]) == 1


def test_floor_can_be_switched_off():
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday())
    out = autofill.run(store, _floor_settings(min_drafts=0), NOW)
    assert store.tables["semasa_ideas"] == [] and "floor" not in out and "short" not in out


def test_floor_draws_a_guideline_or_new_circular_first():
    newer = {**_w(1, "halal_my"), "title": "Makluman produk baharu", "created_at": "2026-09-23T12:00:00+00:00"}
    guide = {**_w(2, "halal_my"), "title": "Garis panduan pelabelan halal", "created_at": "2026-09-20T00:00:00+00:00"}
    circular = {**_w(3, "halal_my"), "title": "Pekeliling baharu pensijilan", "created_at": "2026-09-19T00:00:00+00:00"}
    store = _store([newer, guide, circular], posts=_full_friday())
    autofill.run(store, _floor_settings(), NOW)
    by_slot = {i["brief"]["position"]["slot"]: i["source_title"] for i in store.tables["semasa_ideas"]}
    assert sorted(by_slot.values()) == ["Garis panduan pelabelan halal", "Pekeliling baharu pensijilan"]


def test_floor_skips_video_slots_and_never_writes_a_film():
    brand = {**BRAND, "regulab": {**BRAND["regulab"], "slot_formats": {"08:00": "video"}}}
    store = _store([_w(1, "halal_my"), _w(2, "fatwa")], posts=_full_friday())
    autofill.run(store, {**_floor_settings(), "brand": brand}, NOW)
    got = sorted((i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"])
    assert got == [("2026-09-27", "13:00"), ("2026-09-28", "13:00")]      # 08:00 is a film slot: skipped; Mon has no rota
    assert not store.tables.get("semasa_motions")


def test_floor_takes_turns_between_streams():
    store = _store([_w(1, "halal_my"), _w(2, "halal_my")], posts=_full_friday())
    autofill.run(store, _floor_settings(streams=["regulab", "linkedin"]), NOW)
    got = sorted((i["stream"], i["brief"]["position"]["date"], i["brief"]["position"]["slot"])
                 for i in store.tables["semasa_ideas"])
    assert got == [("linkedin", "2026-09-28", "06:00"), ("regulab", "2026-09-27", "08:00")]    # Mon is a LinkedIn day


def test_floor_says_so_when_nothing_fits_and_writes_nothing():
    store = _store([], posts=_full_friday())
    out = autofill.run(store, _floor_settings(), NOW)
    assert store.tables["semasa_ideas"] == []
    assert "still 2 short of 2 waiting drafts" in out


def test_floor_never_reuses_a_position_the_gap_pass_just_filled():
    store = _store([_w(i, "kosmetik") for i in range(1, 7)])
    autofill.run(store, {"brand": BRAND, "autofill": {"enabled": True, "days_ahead": 3, "per_run": 1,
                                                       "streams": ["regulab"], "min_drafts": 3}}, NOW)
    spots = [(i["brief"]["position"]["date"], i["brief"]["position"]["slot"]) for i in store.tables["semasa_ideas"]]
    assert len(spots) == 3 and len(set(spots)) == 3                          # 1 from the gap pass (per_run 1) + 2 from the floor
